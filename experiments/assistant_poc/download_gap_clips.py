"""
Автоматический загрузчик 10 клипов-заплаток для Блока 1 (Вступление)
Качает ТОЛЬКО нужные 5-10 секундные фрагменты через yt-dlp без звука в 1080p,
создаёт sidecar json файлы под стандарт skippr.
"""
import os
import sys
import json
import subprocess
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

CLIPS_DIR = Path(r"C:\Users\azis\Desktop\ALL_FOLDERS\CrackedMachines\BDFL\montage\clips\Вступление")
CLIPS_DIR.mkdir(parents=True, exist_ok=True)

# 10 заплаток из block_01_gap_fill.json с точными запросами
PATCHES = [
    {
        "id": "00_a_hacker_silhouette",
        "title": "Хакер силуэт у монитора",
        "query": "hacker silhouette dark room hoodie monitor glow stock footage",
        "dur": 4.5,
    },
    {
        "id": "00_b_typing_keyboard_code",
        "title": "Руки печатают код на клавиатуре",
        "query": "hands typing keyboard code on screen close up dark cinematic stock footage",
        "dur": 4.5,
    },
    {
        "id": "00_c_server_room_lights",
        "title": "Серверная стойки дата-центра",
        "query": "data center server room corridor dolly shot blinking lights stock footage",
        "dur": 4.5,
    },
    {
        "id": "01_a_linus_torvalds_conference",
        "title": "Линус Торвальдс на конференции",
        "query": "Linus Torvalds interview conference footage",
        "dur": 5.0,
    },
    {
        "id": "03_a_re9_crowd_umbrellas",
        "title": "Resident Evil 9 толпа под зонтами",
        "query": "Resident Evil 9 Requiem trailer",
        "dur": 6.0,
        "start_sec": 20,
    },
    {
        "id": "03_b_kernel_userspace_diagram",
        "title": "Архитектура ядра и userspace",
        "query": "Linux kernel architecture diagram animation",
        "dur": 8.0,
        "start_sec": 5,
    },
    {
        "id": "03_c_re9_umbrella_rain",
        "title": "Resident Evil 9 зонты под дождем",
        "query": "Resident Evil 9 Requiem trailer",
        "dur": 6.0,
        "start_sec": 35,
    },
    {
        "id": "03_d_re9_lone_figure",
        "title": "Resident Evil 9 одинокая фигура",
        "query": "Resident Evil 9 Requiem trailer",
        "dur": 6.0,
        "start_sec": 50,
    },
    {
        "id": "08_a_network_graph_nodes",
        "title": "Граф сети светящиеся узлы",
        "query": "network graph nodes animation background stock footage",
        "dur": 4.0,
    },
    {
        "id": "08_b_bdfl_title_motion",
        "title": "Кинетическая типографика BDFL",
        "query": "abstract technology data motion background 4k",
        "dur": 4.0,
    },
]

def download_patch(patch):
    out_file = CLIPS_DIR / f"{patch['id']}.mp4"
    sidecar = CLIPS_DIR / f"{patch['id']}.mp4.json"

    if out_file.exists() and out_file.stat().st_size > 50000:
        print(f"✅ Уже скачан: {patch['id']} ({patch['title']})")
        return out_file

    print(f"\n📥 Скачивание: {patch['id']} — «{patch['title']}»")
    print(f"   Запрос: {patch['query']}")

    # Опции секции в секундах
    start_sec = patch.get("start_sec", 5)
    dur_sec = int(patch["dur"] + 3.0)
    end_sec = start_sec + dur_sec
    section_arg = f"*{start_sec}-{end_sec}"

    temp_target = CLIPS_DIR / f"temp_{patch['id']}.mp4"

    cmd = [
        "yt-dlp",
        f"ytsearch1:{patch['query']}",
        "--no-playlist",
        "--download-sections", section_arg,
        "--force-keyframes-at-cuts",
        "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio/best[height<=1080]/best",
        "-o", str(temp_target),
        "--no-warnings"
    ]

    try:
        subprocess.run(cmd, check=True, timeout=60)
    except Exception as e:
        print(f"⚠️ Ошибка yt-dlp секции: {e}. Пробуем скачать первые 10 секунд...")
        # Запасной вариант: скачать без секций лимитом по времени
        cmd_fallback = [
            "yt-dlp",
            f"ytsearch1:{patch['query']}",
            "--no-playlist",
            "-f", "bestvideo[height<=1080][ext=mp4]/best[height<=1080]/best",
            "-o", str(temp_target),
            "--quiet", "--no-warnings"
        ]
        try:
            subprocess.run(cmd_fallback, check=True, timeout=60)
        except Exception as e2:
            print(f"❌ Не удалось скачать: {e2}")
            return None

    if not temp_target.exists():
        # yt-dlp мог добавить расширение
        candidates = list(CLIPS_DIR.glob(f"temp_{patch['id']}.*"))
        if candidates:
            temp_target = candidates[0]
        else:
            print(f"❌ Файл не найден после загрузки: {temp_target}")
            return None

    # Конвертируем в чистый mp4 без аудио через ffmpeg (H.264, 1080p, yuv420p)
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-ss", "0",
        "-i", str(temp_target),
        "-t", str(patch["dur"] + 2.0),
        "-an", # без аудио!
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "fast",
        "-crf", "20",
        "-movflags", "+faststart",
        str(out_file)
    ]

    subprocess.run(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Удаляем temp
    try:
        temp_target.unlink()
    except Exception:
        pass

    if out_file.exists():
        # Пишем sidecar json
        sidecar_data = {
            "query": patch["query"],
            "title": patch["title"],
            "requested_dur": patch["dur"],
            "file": str(out_file),
            "generated_at": "2026-10-28",
            "type": "patch"
        }
        with open(sidecar, "w", encoding="utf-8") as sf:
            json.dump(sidecar_data, sf, ensure_ascii=False, indent=2)
        print(f"✅ Готово: {out_file.name} ({out_file.stat().st_size / 1024:.0f} KB)")
        return out_file
    else:
        print(f"❌ Ошибка сборки ffmpeg для {patch['id']}")
        return None


def main():
    print("=" * 80)
    print("🚀 СКАЧИВАНИЕ 10 ЗАПЛАТОК ДЛЯ БЛОКА 1...")
    print(f"Папка: {CLIPS_DIR}")
    print("=" * 80)

    success = 0
    for p in PATCHES:
        res = download_patch(p)
        if res:
            success += 1

    print("\n" + "=" * 80)
    print(f"🎉 СКАЧАНО: {success} из {len(PATCHES)} клипов-заплаток!")
    print("=" * 80)

if __name__ == "__main__":
    main()
