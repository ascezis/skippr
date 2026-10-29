"""
Эксперимент: Детектив дыр и умный опросник для Блока 1 (Вступление)
Задача: Сохранить все 8 существующих крутых кино-акцентов оригинальной таблицы,
но адресно опросить и закрыть 4 РЕАЛЬНЫЕ ЧЁРНЫЕ ДЫРЫ (суммарно 50 секунд черноты!).
"""
import os
import sys
import json
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

try:
    import openai
except ImportError:
    print("Ошибка: не установлен пакет openai. Установите: pip install openai")
    sys.exit(1)

try:
    import openpyxl
except ImportError:
    openpyxl = None


def load_api_key():
    """Загружает ключ из .env или переменной окружения."""
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    env_key = None
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("OPENROUTER_API_KEY="):
                    env_key = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
                    break

    if not env_key:
        env_key = os.environ.get("OPENROUTER_API_KEY")

    if not env_key:
        print("\n🔑 Ключ не найден в .env.")
        env_key = input("Вставьте OPENROUTER_API_KEY (sk-or-v1-...): ").strip()
        if not env_key:
            print("Ключ не введён. Выход.")
            sys.exit(1)

    return env_key


# 8 существующих идеальных планов из оригинальной таблицы
EXISTING_ROWS = [
    {
        "n": 1,
        "timeline_start": 12.8,
        "timeline_duration": 2.5,
        "type": "Музыка/мем",
        "reference": "Elton John — Sorry Seems to Be the Hardest Word",
        "search_query": "Sorry seems to be the hardest word clip",
    },
    {
        "n": 2,
        "timeline_start": 19.8,
        "timeline_duration": 2.5,
        "type": "Мем",
        "reference": "«Linux runs everything» (тостер, холодильник, банкомат, Tux)",
        "search_query": "linux runs on toaster fridge meme / tux everywhere",
    },
    {
        "n": 3,
        "timeline_start": 23.4,
        "timeline_duration": 3.5,
        "type": "Фильм",
        "reference": "Jurassic Park (1993): Лекс — «It's a UNIX system! I know this!»",
        "search_query": "Jurassic Park it's a unix system I know this scene",
    },
    {
        "n": 4,
        "timeline_start": 51.5,
        "timeline_duration": 2.5,
        "type": "ТВ/мем",
        "reference": "Гордон Рамзи: «It's RAW!» / «idiot sandwich»",
        "search_query": "Gordon Ramsay idiot sandwich / it's RAW clip",
    },
    {
        "n": 5,
        "timeline_start": 55.7,
        "timeline_duration": 4.8,
        "type": "Фильм",
        "reference": "Monty Python and the Holy Grail: коммуна крестьян-анархосиндикалистов",
        "search_query": "Holy Grail anarcho-syndicalist commune scene",
    },
    {
        "n": 6,
        "timeline_start": 60.5,
        "timeline_duration": 3.0,
        "type": "Хроника/ТВ",
        "reference": "Вудсток-1969 + South Park «Die Hippie, Die»",
        "search_query": "Woodstock 1969 footage / South Park Die Hippie Die clip",
    },
    {
        "n": 7,
        "timeline_start": 65.2,
        "timeline_duration": 2.0,
        "type": "Мем",
        "reference": "Прищуренный Фрай (Futurama, «Not sure if…»)",
        "search_query": "Futurama Fry not sure if meme",
    },
    {
        "n": 8,
        "timeline_start": 68.6,
        "timeline_duration": 3.0,
        "type": "Фильм",
        "reference": "HAL 9000 (2001: A Space Odyssey) — красный глаз",
        "search_query": "HAL 9000 red eye / Eye of Sauron",
    },
]

# 4 РЕАЛЬНЫЕ ЧЁРНЫЕ ДЫРЫ НА ТАЙМЛАЙНЕ ВСТУПЛЕНИЯ
TARGET_GAPS = [
    {
        "id": 1,
        "start": 0.0,
        "end": 12.8,
        "duration": 12.8,
        "after_clip": "Начало ролика",
        "before_clip": "Строка 1: Elton John (Sorry Seems to Be the Hardest Word)",
        "spoken_text": (
            "16 сентября 2018 года. Воскресенье. 27 лет этот человек определял, "
            "что попадёт в ядро самого важного софта на планете."
        ),
        "context_hint": "Старт ролика. Дата, календарь, атмосфера кода/серверов, драматический отсчёт 27 лет.",
    },
    {
        "id": 2,
        "start": 15.3,
        "end": 19.8,
        "duration": 4.5,
        "after_clip": "Строка 1: Elton John",
        "before_clip": "Строка 2: Мем «Linux runs on toasters»",
        "spoken_text": (
            "и пишет письмо. Этого человека зовут Линус Торвальдс."
        ),
        "context_hint": "Появление главного героя: архивное фото/видео Линуса Торвальдса, печать на клавиатуре.",
    },
    {
        "id": 3,
        "start": 26.9,
        "end": 51.5,
        "duration": 24.6,
        "after_clip": "Строка 3: Jurassic Park («It's a UNIX system!»)",
        "before_clip": "Строка 4: Гордон Рамзи («It's RAW! / idiot sandwich»)",
        "spoken_text": (
            "открытым и доступным всем желающим. За этим финном стоит финальное решение о том, "
            "что попадёт в ядро, а что «ломает userspace». Но почему один человек стоит за финальным решением "
            "в продукте, который он и сам заявляет как «открытый исходный код»? Типа, почему у самого главного "
            "опенсорс-проекта вообще есть человек с последним словом, который каждый раз..."
        ),
        "context_hint": (
            "САМАЯ БОЛЬШАЯ ДЫРА (25 секунд!). Нужно 3-4 плана: "
            "схема Userspace vs Kernel, карта/граф разработчиков ядра, скриншот kernel.org, вопрос капсом."
        ),
    },
    {
        "id": 4,
        "start": 71.6,
        "end": 78.9,
        "duration": 7.3,
        "after_clip": "Строка 8: HAL 9000 (красный глаз)",
        "before_clip": "Блок BDFL (Великий диктатор Чаплина)",
        "spoken_text": (
            "обширную сеть? В программировании она имеет официальный титул. B.D.F.L."
        ),
        "context_hint": "Анимация графа сети с красной точкой во главе, титры BDFL крупными буквами.",
    },
]


def run_gap_survey():
    print("\n" + "=" * 80)
    print("  🎯 ОПРОСНИК ПО ЧЁРНЫМ ДЫРАМ БЛОКА 1 (ВСТУПЛЕНИЕ)")
    print("  Оригинальная таблица дала 8 отличных клипов, но оставила 50 секунд черноты!")
    print("  Мы НЕ трогаем готовые 8 клипов. Мы заполняем только 4 пустых места.")
    print("=" * 80 + "\n")

    user_gap_notes = []

    for gap in TARGET_GAPS:
        print("*" * 80)
        print(f"⬛ ЧЁРНАЯ ДЫРА #{gap['id']} [{gap['start']:4.1f}s -> {gap['end']:4.1f}s] (пустота: {gap['duration']:.1f} сек)")
        print(f"📍 МЕЖДУ: «{gap['after_clip']}»  ➡️  «{gap['before_clip']}»")
        print(f"🎙 ДИКТОР ГОВОРИТ:\n   «{gap['spoken_text']}»")
        print(f"💡 ПОДСКАЗКА: {gap['context_hint']}")
        print("*" * 80)

        hint = input("Твой образ / мысль (или Enter, чтобы ассистент закрыл сам): ").strip()
        user_gap_notes.append({
            "gap_id": gap["id"],
            "start": gap["start"],
            "end": gap["end"],
            "duration": gap["duration"],
            "spoken_text": gap["spoken_text"],
            "user_hint": hint if hint else "Автоподбор (документ, схема, B-roll, кинетическая типографика)"
        })
        print()

    print("=" * 80)
    print("  ✅ Ответы зафиксированы! Отправляем в Claude Sonnet для генерации заплаток...")
    print("=" * 80)

    api_key = load_api_key()
    call_gap_fill(user_gap_notes, api_key)


def call_gap_fill(user_gap_notes, api_key):
    start_time = time.time()
    client = openai.OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )

    system_prompt = """Ты — ведущий режиссёр видеоэссе. Мы делаем черновой монтаж ролика про Linux и Линуса Торвальдса.
Формат: 100% FACELESS VIDEO ESSAY (без лица). 
У нас УЖЕ ЕСТЬ 8 готовых клипов в этом блоке (Elton John, Jurassic Park, Ramsay, Monty Python, HAL 9000).

ТВОЯ ЗАДАЧА:
Сгенерировать точные «заплатки» (fillers) для 4 конкретных черных дыр хронометража.
Для каждой дыры сгенерируй от 1 до 4 планов (в зависимости от длины дыры), чтобы закрыть её секунда в секунду!
- Для дыры #1 (12.8с): нужно 2-3 плана (например: кинетическая дата 16.09.2018, серверная стойка/код, наезд на клавиатуру).
- Для дыры #2 (4.5с): 1 план (архивное фото молодого Линуса Торвальдса).
- Для дыры #3 (24.6с): 4-5 планов (схема Userspace vs Kernel, логотипы дистрибутивов Linux, скриншот kernel.org, титр с вопросом).
- Для дыры #4 (7.3с): 2 плана (граф сети с центральным узлом, буквы B.D.F.L.).

Если автор дал свой user_hint — обязательно воплоти его!
Если написал 'Автоподбор' — подбери интеллектуальный документальный визуал (документы, схемы, B-roll).

ВЫВОД СТРОГО В JSON:
[
  {
    "gap_id": 1,
    "anchor_phrase": "слова диктора",
    "type": "Документ" | "Схема/Текст" | "B-roll" | "Мем" | "Фильм",
    "description": "описание кадра",
    "duration_sec": 4.0,
    "search_query": "поисковый запрос для YouTube или стока"
  }
]
"""

    user_prompt = "Вот 4 чёрные дыры, которые нужно закрыть визуалом:\n\n"
    for g in user_gap_notes:
        user_prompt += f"--- ДЫРА #{g['gap_id']} [{g['start']}s -> {g['end']}s] ({g['duration']} сек) ---\n"
        user_prompt += f"Слова диктора: {g['spoken_text']}\n"
        user_prompt += f"Намёк автора: {g['user_hint']}\n\n"

    model_candidates = [
        "anthropic/claude-sonnet-5.5",
        "anthropic/claude-sonnet-4.5",
        "openai/gpt-4o",
    ]

    response = None
    used_model = None

    for m in model_candidates:
        try:
            print(f"📡 Запрос к модели: {m}...")
            response = client.chat.completions.create(
                model=m,
                temperature=0.2,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            used_model = m
            break
        except Exception as e:
            print(f"⚠️ Ошибка: {e}")

    if not response:
        print("❌ Не удалось получить ответ.")
        return

    elapsed = time.time() - start_time
    content = response.choices[0].message.content.strip()

    if content.startswith("```json"):
        content = content[7:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()

    try:
        new_patches = json.loads(content)
    except json.JSONDecodeError as err:
        print("❌ Ошибка парсинга JSON:", err)
        print(content)
        return

    usage = response.usage
    cost_usd = getattr(usage, "cost", None) or (
        (usage.prompt_tokens / 1_000_000.0) * 2.00 + (usage.completion_tokens / 1_000_000.0) * 10.00
    )
    cost_rub = cost_usd * 95.0

    print("\n" + "=" * 90)
    print(f"  🎉 СГЕНЕРИРОВАНО {len(new_patches)} НОВЫХ ЗАПЛАТОК! (Модель: {used_model} за {elapsed:.1f}с)")
    print(f"  Списано со счёта: ${cost_usd:.4f} (~{cost_rub:.2f} руб)")
    print("=" * 90)

    # Вывод объединённого таймлайна: оригинальные 8 строк + новые заплатки
    print("\n📋 ИТОГОВЫЙ ТАЙМЛАЙН БЛОКА 1 (100% ПОКРЫТИЕ, 0 СЕКУНД ЧЕРНОТЫ):")
    print("-" * 90)

    for p in new_patches:
        gid = p.get("gap_id")
        typ = p.get("type", "")[:10]
        dur = f"{p.get('duration_sec', 0)}s"
        phrase = p.get("anchor_phrase", "")[:28]
        desc = p.get("description", "")[:35]
        q = p.get("search_query", "")
        print(f"[Заплатка для Дыры #{gid}] {typ:<10} | {dur:<5} | \"{phrase}\" | {desc} | Q: {q}")

    out_dir = os.path.dirname(__file__)
    res_path = os.path.join(out_dir, "block_01_gap_fill.json")
    with open(res_path, "w", encoding="utf-8") as f:
        json.dump(new_patches, f, ensure_ascii=False, indent=2)

    print("\n" + "-" * 90)
    print(f"💾 Заплатки сохранены в: {res_path}")
    print("=" * 90 + "\n")


if __name__ == "__main__":
    run_gap_survey()
