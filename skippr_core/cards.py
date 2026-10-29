"""
skippr_core.cards — Генератор визуальных раскадровочных карточек (Storyboard Cards)
Создаёт стильные 1080p PNG-заглушки для всех не-видео элементов (картинки, титры, текст, документы),
чтобы на таймлайне монтажки никогда не было черных провалов.
"""
from pathlib import Path
import textwrap
from typing import Optional
from PIL import Image, ImageDraw, ImageFont


def _wrap_text(text: str, width: int = 50) -> str:
    lines = []
    for paragraph in text.split("\n"):
        lines.extend(textwrap.wrap(paragraph, width=width))
    return "\n".join(lines)


def generate_storyboard_card(
    n: int,
    block: str,
    kind: str,
    phrase: str,
    reference: str,
    query: str,
    out_path: Path,
    width: int = 1920,
    height: int = 1080,
) -> Path:
    # Sanitize folder path
    safe_parent = out_path.parent
    safe_parent.mkdir(parents=True, exist_ok=True)

    bg_color = (18, 21, 28)
    card_bg = (26, 32, 44)

    # Accent color by kind
    k_lower = str(kind).lower()
    if "картин" in k_lower or "фото" in k_lower or "скрин" in k_lower:
        accent_color = (56, 161, 105)  # Clean emerald green
        kind_label = "КАРТИНКА / ДОКУМЕНТ"
    elif "текст" in k_lower or "плашк" in k_lower or "титр" in k_lower:
        accent_color = (221, 107, 32)  # Amber orange
        kind_label = "ТИПОГРАФИКА / ПЛАШКА"
    elif "оригинал" in k_lower:
        accent_color = (159, 122, 234)  # Purple
        kind_label = "ОРИГИНАЛЬНАЯ ЗАПИСЬ"
    else:
        accent_color = (49, 130, 206)  # Blue
        kind_label = str(kind).upper()

    img = Image.new("RGB", (width, height), color=bg_color)
    draw = ImageDraw.Draw(img)

    margin = 100
    draw.rounded_rectangle(
        [margin, margin, width - margin, height - margin],
        radius=20,
        fill=card_bg,
        outline=accent_color,
        width=3,
    )

    try:
        font_badge = ImageFont.truetype("arial.ttf", 30)
        font_title = ImageFont.truetype("arial.ttf", 46)
        font_quote = ImageFont.truetype("arial.ttf", 34)
        font_label = ImageFont.truetype("arial.ttf", 24)
        font_small = ImageFont.truetype("arial.ttf", 26)
    except Exception:
        font_badge = font_title = font_quote = font_label = font_small = ImageFont.load_default()

    # 1. Top Badge
    badge_text = f"№{n:03d}  •  БЛОК: {block.upper()}  •  {kind_label}"
    draw.text((margin + 60, margin + 50), badge_text, font=font_badge, fill=accent_color)

    # 2. Main Reference / Title (wrapped)
    ref_clean = reference.strip() or "(Графический элемент / Заставка)"
    wrapped_ref = _wrap_text(ref_clean, width=48)
    draw.text((margin + 60, margin + 115), wrapped_ref, font=font_title, fill=(245, 247, 250))

    # 3. Spoken phrase
    y_quote = margin + 340
    draw.text((margin + 60, y_quote), "ЗВУЧИТ В КАДРЕ:", font=font_label, fill=(140, 155, 175))
    wrapped_quote = _wrap_text(f"«{phrase.strip()}»", width=55)
    draw.text((margin + 60, y_quote + 35), wrapped_quote, font=font_quote, fill=(215, 225, 240))

    # 4. Search query or Action
    y_query = margin + 570
    draw.text((margin + 60, y_query), "ЗАМЕТКА / ПОИСКОВЫЙ ЗАПРОС:", font=font_label, fill=(140, 155, 175))
    query_clean = query.strip() if query else "графика создаётся на таймлайне"
    wrapped_query = _wrap_text(query_clean, width=65)
    draw.text((margin + 60, y_query + 35), wrapped_query, font=font_small, fill=(180, 200, 225))

    img.save(out_path)
    return out_path
