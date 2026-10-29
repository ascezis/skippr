"""
skippr_core.images — Модуль автоматического поиска и скачивания картинок/мемов
Находит изображения по поисковым запросам из монтажного листа (вид 'картинка'),
скачивает оригиналы высокого разрешения, опционально форматирует под 1080p (ambient blur),
создаёт sidecar-файлы метаданных и сохраняет в структуру папок clips/<Блок>/.
"""
from __future__ import annotations

import io
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from PIL import Image, ImageFilter

from skippr_core.models import RowItem
from skippr_core.table import load_table

# Search engine import
try:
    from ddgs import DDGS
except ImportError:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        DDGS = None

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
}


def sanitize_filename(name: str, max_len: int = 50) -> str:
    s = re.sub(r"[^\w\-_]+", "_", name.strip())
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:max_len] if s else "image"


def sanitize_block_name(block: str) -> str:
    s = re.sub(r"[^\w\-]+", "_", block.strip())
    return s.strip("_") if s else "General"


def make_ambient_blur(img: Image.Image, target_w: int = 1920, target_h: int = 1080) -> Image.Image:
    """Форматирует изображение под 1920x1080 с кинематографичным размытым фоном для не-16:9 картинок."""
    # Нормализуем режим: корректно обрабатываем P (палитра), CMYK, 1-bit, grayscale и альфа-канал
    has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
    if has_alpha:
        fg_img = img.convert("RGBA")
        # Для фона композитим альфу на темный нейтральный фон перед размытием
        bg_source = Image.new("RGB", fg_img.size, (20, 24, 33))
        bg_source.paste(fg_img, mask=fg_img.split()[3])
    else:
        fg_img = img.convert("RGB")
        bg_source = fg_img

    orig_w, orig_h = img.size
    aspect = orig_w / max(1, orig_h)
    target_aspect = target_w / target_h

    # Если уже близко к 16:9 (в пределах 5%) и нет прозрачности, не трогаем
    if abs(aspect - target_aspect) < 0.05 and not has_alpha:
        return fg_img

    # Фон: масштабируем с заполнением кадра и размываем
    bg_ratio = max(target_w / orig_w, target_h / orig_h)
    bg_w, bg_h = int(orig_w * bg_ratio), int(orig_h * bg_ratio)
    bg = bg_source.resize((bg_w, bg_h), Image.Resampling.LANCZOS)

    left = (bg_w - target_w) // 2
    top = (bg_h - target_h) // 2
    bg = bg.crop((left, top, left + target_w, top + target_h))
    bg = bg.convert("RGB")
    bg = bg.filter(ImageFilter.GaussianBlur(radius=35))

    # Затемняем фон на 35% для фокуса на основном контенте
    dim = Image.new("RGB", (target_w, target_h), (0, 0, 0))
    bg = Image.blend(bg, dim, alpha=0.35)

    # Передний план: масштабируем по центру без обрезки (до 92% экрана)
    pad_h = int(target_h * 0.92)
    pad_w = int(target_w * 0.92)
    fg_ratio = min(pad_w / orig_w, pad_h / orig_h)
    fg_w, fg_h = int(orig_w * fg_ratio), int(orig_h * fg_ratio)
    fg = fg_img.resize((fg_w, fg_h), Image.Resampling.LANCZOS)

    pos_x = (target_w - fg_w) // 2
    pos_y = (target_h - fg_h) // 2

    if fg.mode == "RGBA":
        bg.paste(fg, (pos_x, pos_y), fg)
    else:
        bg.paste(fg, (pos_x, pos_y))

    return bg


def download_image_bytes(url: str, min_w: int = 300, min_h: int = 200, timeout: int = 10) -> Optional[Tuple[Image.Image, str]]:
    """Скачивает и проверяет изображение по URL."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code == 200 and len(r.content) > 1024:
            img = Image.open(io.BytesIO(r.content))
            img.load()
            w, h = img.size
            if w >= min_w and h >= min_h:
                return img, url
    except Exception:
        pass
    return None


def search_images(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Выполняет поиск картинок через ddgs."""
    if DDGS is None:
        raise RuntimeError("Модуль 'ddgs' не установлен. Установите: pip install ddgs")

    ddg = DDGS(timeout=15)
    return list(ddg.images(query, max_results=max_results))


def fetch_image_for_item(
    item: RowItem,
    clips_dir: Path,
    force: bool = False,
    ambient: bool = True,
    dry_run: bool = False,
) -> Tuple[bool, Optional[Path], str]:
    """
    Ищет и скачивает картинку для конкретной строки таблицы.
    Возвращает (success, file_path, message).
    """
    safe_block = sanitize_block_name(item.block)
    block_dir = clips_dir / safe_block
    block_dir.mkdir(parents=True, exist_ok=True)

    # Имя файла: <№>_<референс>.jpg
    ref_title = item.reference or item.query or f"image_{item.n}"
    safe_title = sanitize_filename(ref_title, max_len=45)
    out_base = block_dir / f"{item.n:03d}_{safe_title}"

    # Проверка существующего файла
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        cand = out_base.with_suffix(ext)
        if cand.exists() and not force:
            return True, cand, f"Уже существует: {cand.name}"

    query = (item.query or item.reference or "").strip()
    if not query:
        return False, None, "Пустой поисковый запрос"

    if dry_run:
        return True, out_base.with_suffix(".jpg"), f"[Dry-run] Будет выполнен поиск: '{query}'"

    # Поиск
    try:
        results = search_images(query, max_results=5)
    except Exception as e:
        return False, None, f"Ошибка поиска '{query}': {e}"

    if not results:
        return False, None, f"По запросу '{query}' ничего не найдено"

    downloaded_img = None
    source_url = ""
    is_fallback_thumb = False

    # 1. Пробуем оригиналы
    for res in results:
        img_url = res.get("image")
        if not img_url:
            continue
        res_tuple = download_image_bytes(img_url, min_w=350, min_h=250)
        if res_tuple:
            downloaded_img, source_url = res_tuple
            break

    # 2. Если все оригиналы заблокированы (403 hotlink protection), пробуем Bing CDN thumbnail
    if downloaded_img is None:
        for res in results:
            thumb_url = res.get("thumbnail")
            if not thumb_url:
                continue
            res_tuple = download_image_bytes(thumb_url, min_w=150, min_h=150)
            if res_tuple:
                downloaded_img, source_url = res_tuple
                is_fallback_thumb = True
                break

    if downloaded_img is None:
        return False, None, f"Не удалось скачать ни один из {len(results)} кандидатов"

    # Обработка размера и сохранение
    if ambient:
        try:
            final_img = make_ambient_blur(downloaded_img)
        except Exception:
            final_img = downloaded_img.convert("RGB")
    else:
        final_img = downloaded_img

    target_path = out_base.with_suffix(".jpg")
    if final_img.mode in ("RGBA", "P") and not ambient:
        target_path = out_base.with_suffix(".png")
        final_img.save(target_path, "PNG")
    else:
        final_img = final_img.convert("RGB")
        final_img.save(target_path, "JPEG", quality=95)

    # Сохраняем sidecar metadata JSON
    sidecar_path = target_path.with_name(target_path.name + ".json")
    meta = {
        "n": item.n,
        "block": item.block,
        "phrase": item.phrase,
        "reference": item.reference,
        "query": query,
        "src_url": source_url,
        "is_thumbnail_fallback": is_fallback_thumb,
        "orig_width": downloaded_img.width,
        "orig_height": downloaded_img.height,
        "canvas_width": final_img.width,
        "canvas_height": final_img.height,
        "source_in": 0.0,
        "source_out": float(item.duration or 4.0),
        "useful_in": 0.0,
        "useful_out": float(item.duration or 4.0),
        "handle_in": 0.0,
        "handle_out": 0.0,
        "src_fps": 25.0,
    }
    sidecar_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    status_tag = "⚠️ Thumbnail fallback" if is_fallback_thumb else "✓ Оригинал"
    return True, target_path, f"{status_tag} ({downloaded_img.width}x{downloaded_img.height}) -> {target_path.name}"


def download_images(
    table_path: str | Path,
    clips_dir: str | Path,
    block: Optional[str] = None,
    only: Optional[str] = None,
    force: bool = False,
    ambient: bool = True,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Пакетная выкачка картинок для монтажного листа.
    """
    table_p = Path(table_path)
    clips_p = Path(clips_dir)
    items, _, _ = load_table(table_p)

    # Фильтруем только строки типа 'картинка'
    target_items = [it for it in items if "картин" in str(it.kind).lower() or "скрин" in str(it.kind).lower() or "фото" in str(it.kind).lower()]

    if block:
        b_clean = block.strip().lower()
        target_items = [it for it in target_items if b_clean in it.block.strip().lower()]

    if only:
        allowed_nums = set()
        for chunk in only.split(","):
            chunk = chunk.strip()
            if "-" in chunk:
                parts = chunk.split("-")
                allowed_nums.update(range(int(parts[0]), int(parts[1]) + 1))
            elif chunk.isdigit():
                allowed_nums.add(int(chunk))
        target_items = [it for it in target_items if it.n in allowed_nums]

    print(f"\n🖼️ Запуск скачивания картинок skippr...")
    print(f"   Таблица: {table_p.name} | Найдено целевых строк: {len(target_items)}")
    print(f"   Папка:   {clips_p.resolve()} | Режим 1080p ambient blur: {'ВКЛ' if ambient else 'ВЫКЛ'}\n")

    stats = {"total": len(target_items), "downloaded": 0, "skipped": 0, "failed": 0, "items": []}

    for idx, it in enumerate(target_items, start=1):
        prefix = f"[{idx:02d}/{len(target_items):02d}] №{it.n:03d} [{it.block}]"
        ok, fpath, msg = fetch_image_for_item(
            item=it,
            clips_dir=clips_p,
            force=force,
            ambient=ambient,
            dry_run=dry_run,
        )
        if ok:
            if "Уже существует" in msg:
                stats["skipped"] += 1
                print(f"{prefix} ⏭️  {msg}")
            else:
                stats["downloaded"] += 1
                print(f"{prefix} 💾 {msg}")
        else:
            stats["failed"] += 1
            print(f"{prefix} ❌ {msg}")

        stats["items"].append({"n": it.n, "block": it.block, "success": ok, "file": str(fpath) if fpath else None, "msg": msg})

    print(f"\n✨ Завершено: Скачано: {stats['downloaded']} | Пропущено: {stats['skipped']} | Ошибок: {stats['failed']}")
    return stats


def main():
    import argparse

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        prog="skippr images",
        description="Автоматический поиск и скачивание картинок по поисковым запросам монтажного листа",
    )
    parser.add_argument("table", nargs="?", default="montazhny_list_100pct.xlsx", help="Путь к таблице xlsx")
    parser.add_argument("-o", "--output", default="clips", help="Папка для сохранения (по умолчанию clips)")
    parser.add_argument("--block", help="Фильтр по названию блока (например, 'Вступление')")
    parser.add_argument("--only", help="Фильтр по номерам строк (например, '5,9,15' или '1-20')")
    parser.add_argument("--force", action="store_true", help="Перекачивать даже существующие файлы")
    parser.add_argument("--no-ambient", action="store_true", help="Не применять 1080p ambient blur для не-16:9 картинок")
    parser.add_argument("--dry-run", action="store_true", help="Показать план без скачивания")

    args = parser.parse_args()

    table_path = Path(args.table)
    if not table_path.exists():
        # Fallback check
        alt = Path("C:/Users/azis/Desktop/ALL_FOLDERS/CrackedMachines/BDFL/montage/montazhny_list_100pct.xlsx")
        if alt.exists():
            table_path = alt

    download_images(
        table_path=table_path,
        clips_dir=args.output,
        block=args.block,
        only=args.only,
        force=args.force,
        ambient=not args.no_ambient,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
