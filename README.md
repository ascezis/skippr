# skippr 🎬⚡

> **Skip the manual B-roll grind.** Turn video scripts and cue sheets into organized, ready-to-edit footage and DaVinci Resolve rough cuts.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)]()
[![yt--dlp](https://img.shields.io/badge/powered%20by-yt--dlp-red.svg)](https://github.com/yt-dlp/yt-dlp)
[![NLE Ready](https://img.shields.io/badge/NLE-DaVinci%20%7C%20Premiere-orange.svg)]()

`skippr` — инструмент для ютуберов и видеомонтажёров. Он принимает монтажный лист (сгенерированный ИИ или написанный вручную), находит нужные фрагменты на YouTube, точно нарезает таймкоды, нормализует кодеки и раскладывает всё по папкам блоков сценария.

---

## ✨ Возможности

- 📋 **Любые источники**: читает `.xlsx` (с авто-детектом колонок), `.csv`, `.txt` со списком запросов или одиночные ссылки.
- ✂️ **Точная нарезка без глитчей**: поддержка любых форматов таймкодов (`1:23-1:40`, `85-110`, `0:45+15s`, объекты времени Excel).
- 🎞️ **NLE-Ready (DaVinci / Premiere)**: автоматически перекодирует видео в **H.264 + AAC** (`yuv420p`, `+faststart`). Никаких чёрных экранов и проблем с Opus/VP9/AV1.
- 📁 **Структура по сценам**: сохраняет файлы вида `<out>/<Блок>/<NN>_<название>.mp4`.
- 🔄 **Двусторонняя синхронизация с Excel**: сам обновляет статус строк на «скачано» (с зелёной заливкой), вписывает прямые ссылки и пути к файлам. Если Excel открыт — безопасно пишет в копию `*_results.xlsx`.
- 🛡️ **Защита от брака**: проверка целостности через `ffprobe` перед утверждением клипа, пропуск уже скачанных, фильтрация прямых эфиров и мусора.
- 🧠 **Умное кэширование**: если из одного длинного ролика режется несколько кусков, исходник скачивается только один раз.

---

## 🛠️ Установка

### 1. Зависимости системы
- **Python 3.10+**
- **ffmpeg** и **ffprobe** в системном `PATH`
- **Deno** (для решения JS-челленджей YouTube):
  ```bash
  # Windows
  winget install DenoLand.Deno
  ```

### 2. Установка библиотек
```bash
pip install -r requirements.txt
```

---

## 🚀 Использование

### С монтажным листом (Excel / CSV)
```bash
# Базовый запуск: обработка всех строк со статусом «найти»
python grab.py montazhny_list.xlsx

# Только проверить кандидатов без скачивания
python grab.py montazhny_list.xlsx --dry-run

# Скачать только конкретные номера строк
python grab.py montazhny_list.xlsx --only 5,9-14

# Скачать только приоритет A с ручным выбором кандидата
python grab.py montazhny_list.xlsx --priority A --pick

# С авторизацией через браузер (для 18+ роликов)
python grab.py montazhny_list.xlsx --cookies-from-browser chrome
```

### С текстовым файлом (`clips.txt`)
Формат строки: `запрос или ссылка | таймкод | название`
```text
Gordon Ramsay idiot sandwich | 0:02-0:15 | Прожарка Рамзи
https://www.youtube.com/watch?v=JOeY07qKU9c | 0:40-0:55 | UNIX system
```
```bash
python grab.py clips.txt --out D:\MyVideo\Clips
```

### Одиночный клип из терминала
```bash
python grab.py "https://youtu.be/XXXX" --tc 1:23-1:40 --name "epic_moment"
```

---

## 🗺️ Roadmap развития

- [ ] **Экспорт чернового монтажа в DaVinci Resolve**: генерация `.xml` / `FCPXML` таймлайна с маркерами сценария и расставленными клипами.
- [ ] **AI-анализатор сценария**: генерация готового монтажного листа напрямую из текста сценария через Claude / GPT.
- [ ] **Автопоиск таймкодов по субтитрам**: вырезка момента по цитате персонажа без ручного ввода таймкодов.
- [ ] **Скриншотер веб-страниц**: сохранение скриншотов статей, твитов и писем через headless-браузер прямо в проект.
- [ ] **Нормализация громкости (EBU R128 / -16 LUFS)**: выравнивание уровня звука всех клипов перед монтажом.

---

## 📄 Лицензия

Распространяется под лицензией [MIT](LICENSE).
