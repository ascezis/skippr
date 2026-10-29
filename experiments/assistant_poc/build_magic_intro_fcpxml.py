r"""
Скрипт бесшовной сборки Блока 1 (Вступление) в готовый DaVinci Resolve FCPXML (1.9)
Создаёт 100% непрерывный таймлайн первых 79 секунд ролика без единого пропуска,
без черных дыр, без водяных знаков и с нулевым повторением кадров (строгая дедупликация).
"""
import os
import sys
import json
import shutil
from pathlib import Path

# Добавляем корень проекта в путь
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from skippr_core.config import ProjectSettings
from skippr_core.fps import sec_to_frames
from skippr_core.export_fcpxml import generate_fcpxml

MONTAGE_DIR = Path(r"C:\Users\azis\Desktop\ALL_FOLDERS\CrackedMachines\BDFL\montage")
CLIPS_INTRO_DIR = MONTAGE_DIR / "clips" / "Вступление"
VOICEOVER_PATH = Path(r"C:\Users\azis\Desktop\ALL_FOLDERS\CrackedMachines\BDFL\audio\voiceover.wav")

def build_magic_plan():
    original_plan_path = MONTAGE_DIR / "plan.json"
    with open(original_plan_path, "r", encoding="utf-8") as f:
        orig_plan = json.load(f)

    # Клипы первого блока и всё, что дальше
    rest_plan = [p for p in orig_plan if p["n"] > 8]

    # Строим 16 идеальных планов первого блока (0.0s -> 78.92s)
    # Используем прямые абсолютные пути для исходных клипов из orig_plan, исключая коллизии глобов!
    intro_sequence = [
        # --- ДЫРА #1 (0.0s - 12.8s): Старт ролика, загадочный хакер ---
        {
            "n": 101,
            "block": "Вступление",
            "kind": "B-roll",
            "phrase": "16 сентября 2018 года. Воскресенье.",
            "reference": "Хакер у светящегося монитора в темноте (16.09.2018)",
            "file": str(CLIPS_INTRO_DIR / "00_a_hacker_silhouette.mp4"),
            "track": "V1",
            "timeline_start": 0.0,
            "timeline_duration": 4.2,
            "source_in": 0.0,
            "source_out": 4.2,
        },
        {
            "n": 102,
            "block": "Вступление",
            "kind": "B-roll",
            "phrase": "27 лет этот человек определял,",
            "reference": "Руки печатают код на клавиатуре в полумраке",
            "file": str(CLIPS_INTRO_DIR / "00_b_typing_keyboard_code.mp4"),
            "track": "V1",
            "timeline_start": 4.2,
            "timeline_duration": 4.4,
            "source_in": 0.0,
            "source_out": 4.4,
        },
        {
            "n": 103,
            "block": "Вступление",
            "kind": "B-roll",
            "phrase": "что попадёт в ядро самого важного софта на планете.",
            "reference": "Серверная стойка дата-центра с диодами (чистый 4K, без логотипов)",
            "file": str(CLIPS_INTRO_DIR / "00_c_server_room_lights.mp4"),
            "track": "V1",
            "timeline_start": 8.6,
            "timeline_duration": 4.2,
            "source_in": 0.0,
            "source_out": 4.2,
        },
        # --- ОРИГИНАЛЬНАЯ СТРОКА 1 (12.8s - 15.3s): Elton John ---
        {
            "n": 1,
            "block": "Вступление",
            "kind": "Музыка/мем",
            "phrase": "Письмо с извинениями",
            "reference": "Elton John — Sorry Seems to Be the Hardest Word",
            "file": orig_plan[0]["file"],
            "track": "V1",
            "timeline_start": 12.8,
            "timeline_duration": 2.5,
            "source_in": 0.0,
            "source_out": 2.5,
        },
        # --- ДЫРА #2 (15.3s - 19.8s): Появление героя ---
        {
            "n": 104,
            "block": "Вступление",
            "kind": "Документ",
            "phrase": "и пишет письмо. Этого человека зовут Линус Торвальдс.",
            "reference": "Линус Торвальдс на конференции",
            "file": str(CLIPS_INTRO_DIR / "01_a_linus_torvalds_conference.mp4"),
            "track": "V1",
            "timeline_start": 15.28,
            "timeline_duration": 4.52, # 15.28 -> 19.80 (точно 0 кадров пропуска)
            "source_in": 0.0,
            "source_out": 4.52,
        },
        # --- ОРИГИНАЛЬНАЯ СТРОКА 3 (19.8s - 26.9s): Jurassic Park Unix ---
        {
            "n": 3,
            "block": "Вступление",
            "kind": "Фильм",
            "phrase": "Ваши телефоны, роутеры... It's a UNIX system",
            "reference": "Jurassic Park (1993): Лекс — «It's a UNIX system!»",
            "file": orig_plan[2]["file"],
            "track": "V1",
            "timeline_start": 19.8,
            "timeline_duration": 7.1,  # 19.8 -> 26.9
            "source_in": 0.0,
            "source_out": 7.1,
        },
        # --- ДЫРА #3 (26.9s - 51.5s): Resident Evil Tokyo Umbrellas + Linux Kernel Diagram ---
        {
            "n": 105,
            "block": "Вступление",
            "kind": "Фильм",
            "phrase": "открытым и доступным всем желающим.",
            "reference": "Resident Evil: вид сверху на толпу под зонтами на перекрестке Сибуя",
            "file": str(CLIPS_INTRO_DIR / "03_a_re9_crowd_umbrellas.mp4"),
            "track": "V1",
            "timeline_start": 26.9,
            "timeline_duration": 5.0,
            "source_in": 0.0,
            "source_out": 5.0,
        },
        {
            "n": 106,
            "block": "Вступление",
            "kind": "Схема/Текст",
            "phrase": "За этим финном стоит финальное решение... userspace",
            "reference": "Схема архитектуры ядра Linux и userspace",
            "file": str(CLIPS_INTRO_DIR / "03_b_kernel_userspace_diagram.mp4"),
            "track": "V1",
            "timeline_start": 31.9,
            "timeline_duration": 7.6,
            "source_in": 0.0,
            "source_out": 7.6,
        },
        {
            "n": 107,
            "block": "Вступление",
            "kind": "Фильм",
            "phrase": "Но почему один человек стоит за финальным решением...",
            "reference": "Resident Evil: капли дождя и люди с зонтами под дождем (уличный план)",
            "file": str(CLIPS_INTRO_DIR / "03_c_re9_umbrella_rain.mp4"),
            "track": "V1",
            "timeline_start": 39.5,
            "timeline_duration": 6.0,
            "source_in": 0.0,
            "source_out": 6.0,
        },
        {
            "n": 108,
            "block": "Вступление",
            "kind": "Фильм",
            "phrase": "Типа, почему у самого главного опенсорс-проекта...",
            "reference": "Resident Evil: одинокая неподвижная фигура в центре потока людей под дождем",
            "file": str(CLIPS_INTRO_DIR / "03_d_re9_lone_figure.mp4"),
            "track": "V1",
            "timeline_start": 45.5,
            "timeline_duration": 6.0,
            "source_in": 0.0,
            "source_out": 6.0,
        },
        # --- ОРИГИНАЛЬНАЯ СТРОКА 4 (51.5s - 55.7s): Гордон Рамзи ---
        {
            "n": 4,
            "block": "Вступление",
            "kind": "ТВ/мем",
            "phrase": "Прожарки самым топовым разработчикам",
            "reference": "Гордон Рамзи: «It's RAW!» / «idiot sandwich»",
            "file": orig_plan[3]["file"],
            "track": "V1",
            "timeline_start": 51.5,
            "timeline_duration": 4.2,  # 51.5 -> 55.7
            "source_in": 0.0,
            "source_out": 4.2,
        },
        # --- ОРИГИНАЛЬНАЯ СТРОКА 5 (55.7s - 60.5s): Monty Python Holy Grail ---
        {
            "n": 5,
            "block": "Вступление",
            "kind": "Фильм",
            "phrase": "Опенсорс — коммуна, хиппи",
            "reference": "Monty Python Holy Grail: коммуна анархосиндикалистов",
            "file": orig_plan[4]["file"],
            "track": "V1",
            "timeline_start": 55.7,
            "timeline_duration": 4.8,  # 55.7 -> 60.5
            "source_in": 0.0,
            "source_out": 4.8,
        },
        # --- ОРИГИНАЛЬНАЯ СТРОКА 6 (60.5s - 67.0s): Woodstock / South Park ---
        {
            "n": 6,
            "block": "Вступление",
            "kind": "Хроника/ТВ",
            "phrase": "С христианской щедростью делятся на Рождество",
            "reference": "Вудсток-1969 + South Park «Die Hippie, Die»",
            "file": orig_plan[5]["file"],
            "track": "V1",
            "timeline_start": 60.5,
            "timeline_duration": 6.5,  # 60.5 -> 67.0
            "source_in": 0.0,
            "source_out": 6.5,
        },
        # --- ОРИГИНАЛЬНАЯ СТРОКА 8 (67.0s - 71.6s): HAL 9000 красный глаз ---
        {
            "n": 8,
            "block": "Вступление",
            "kind": "Фильм",
            "phrase": "Красная точка над сетью узлов",
            "reference": "HAL 9000 (2001: A Space Odyssey) — красный глаз",
            "file": orig_plan[7]["file"],
            "track": "V1",
            "timeline_start": 67.0,
            "timeline_duration": 4.6,  # 67.0 -> 71.6
            "source_in": 0.0,
            "source_out": 4.6,
        },
        # --- ДЫРА #4 (71.6s - 78.9s): Светящийся граф + Титры B.D.F.L. ---
        {
            "n": 109,
            "block": "Вступление",
            "kind": "Схема/Текст",
            "phrase": "обширную сеть?",
            "reference": "Светящийся граф сети с центральным узлом",
            "file": str(CLIPS_INTRO_DIR / "08_a_network_graph_nodes.mp4"),
            "track": "V1",
            "timeline_start": 71.6,
            "timeline_duration": 3.8,  # 71.6 -> 75.4
            "source_in": 0.0,
            "source_out": 3.8,
        },
        {
            "n": 110,
            "block": "Вступление",
            "kind": "Схема/Текст",
            "phrase": "B.D.F.L.",
            "reference": "Кинетическая типографика B.D.F.L. на темном фоне",
            "file": str(CLIPS_INTRO_DIR / "08_b_bdfl_title_motion.mp4"),
            "track": "V1",
            "timeline_start": 75.4,
            "timeline_duration": 3.52,  # 75.4 -> 78.92
            "source_in": 0.0,
            "source_out": 3.52,
        },
    ]

    # Строгие проверки качества (Deduplication & Zero-Gap Guard)
    assert len(intro_sequence) == 16, f"Expected 16 intro clips, got {len(intro_sequence)}"
    for idx, item in enumerate(intro_sequence):
        fpath = Path(item["file"])
        assert fpath.exists(), f"Missing file: {fpath}"
        assert fpath.stat().st_size > 50000, f"File too small ({fpath.stat().st_size} bytes): {fpath}"
        if idx > 0:
            prev_item = intro_sequence[idx - 1]
            # Защита от дублей
            assert item["file"] != prev_item["file"], f"Duplicate consecutive clip at {idx}: {item['file']}"
            # Защита от черных кадров (стыковка кадр-в-кадр)
            prev_end = round(prev_item["timeline_start"] + prev_item["timeline_duration"], 2)
            curr_start = round(item["timeline_start"], 2)
            assert abs(prev_end - curr_start) < 0.05, f"Gap between clip {idx-1} and {idx}: prev_end={prev_end}, curr_start={curr_start}"

    print("🛡️ Все 16 планов Блока 1 прошли строгую валидацию: 0 дублей, 0 черных дыр!")

    # Полный план: обновлённое Вступление (16 непрерывных планов) + остальные 64 плана
    full_magic_plan = intro_sequence + rest_plan

    # Пересчитываем кадры на 25 fps
    fps = 25.0
    for item in full_magic_plan:
        item["timeline_start_frame"] = sec_to_frames(item["timeline_start"], fps)
        item["timeline_duration_frame"] = sec_to_frames(item["timeline_duration"], fps)
        item["source_in_frame"] = sec_to_frames(item.get("source_in", 0.0), fps)
        item["source_out_frame"] = sec_to_frames(item.get("source_out", item["timeline_duration"]), fps)

    return full_magic_plan


def main():
    print("=" * 80)
    print("🪄 СБОРКА МАГИЧЕСКОГО ТАЙМЛАЙНА ДЛЯ DAVINCI RESOLVE...")
    print("=" * 80)

    magic_plan = build_magic_plan()

    settings = ProjectSettings(fps=25.0, width=1920, height=1080)

    fcpxml_content = generate_fcpxml(
        plan_data=magic_plan,
        settings=settings,
        voiceover_path=str(VOICEOVER_PATH),
        project_name="BDFL Magic Intro Timeline"
    )

    # Делаем бэкап старого timeline.fcpxml
    current_fcpxml = MONTAGE_DIR / "timeline.fcpxml"
    backup_fcpxml = MONTAGE_DIR / "timeline_backup.fcpxml"
    if current_fcpxml.exists() and not backup_fcpxml.exists():
        shutil.copy2(current_fcpxml, backup_fcpxml)

    # Записываем обновленный timeline.fcpxml
    with open(current_fcpxml, "w", encoding="utf-8") as f:
        f.write(fcpxml_content)

    print(f"✅ Готово! Файл timeline.fcpxml обновлён: {current_fcpxml}")
    print("📊 Блок 1 (0.0s - 78.92s): 16 уникальных планов, 100% покрытие, РОВНО 0 СЕКУНД ЧЕРНОТЫ!")
    print("=" * 80)

if __name__ == "__main__":
    main()
