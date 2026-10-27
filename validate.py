#!/usr/bin/env python3
"""
validate.py — Pre-flight validator for skippr cue sheet.
Validates:
- Unique '№'
- Non-empty Block, Phrase, Kind, Duration
- Dropdown choices (Kind, Priority, Status)
- Parseable Timecodes
- Every Phrase exists in script.txt (normalized case, punctuation, ё/е)
Exits with code != 0 on errors. Does not modify any file.
"""
import argparse
from pathlib import Path
import sys
from typing import List, Tuple

for _s in (sys.stdout, sys.stderr):
    if _s and hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

from skippr_core.table import load_table
from skippr_core.text import normalize_text
from skippr_core.models import RowItem
from grab import parse_tc

VALID_KINDS = {"клип", "картинка", "оригинал", "текст"}
VALID_PRIORITIES = {"A", "B", "C"}
VALID_STATUSES = {"найти", "скачано", "ошибка", "пропуск"}


class ValidationError:
    def __init__(self, n: int, field: str, message: str, is_warning: bool = False):
        self.n = n
        self.field = field
        self.message = message
        self.is_warning = is_warning


def validate_cue_sheet(
    table_path: str | Path,
    script_path: str | Path | None = None,
    allow_missing_script: bool = False,
) -> Tuple[List[RowItem], List[ValidationError]]:
    p = Path(table_path)
    if not p.exists():
        return [], [ValidationError(0, "Файл", f"Файл таблицы не найден: {p}")]

    try:
        items, settings, is_legacy = load_table(p)
    except Exception as e:
        return [], [ValidationError(0, "Таблица", f"Ошибка чтения таблицы: {e}")]

    if not items:
        return [], [ValidationError(0, "Таблица", "В таблице нет строк для обработки")]

    errors: List[ValidationError] = []

    # Determine script path
    s_path = None
    if script_path:
        s_path = Path(script_path)
    elif settings.script_path:
        cand = p.parent / settings.script_path
        if cand.exists():
            s_path = cand
        else:
            s_path = Path(settings.script_path)

    script_normalized = ""
    if s_path and s_path.exists():
        try:
            raw_script = s_path.read_text(encoding="utf-8-sig")
            script_normalized = normalize_text(raw_script)
        except Exception as e:
            errors.append(ValidationError(0, "Сценарий", f"Не удалось прочитать {s_path}: {e}"))
    else:
        if not allow_missing_script:
            errors.append(ValidationError(0, "Сценарий", f"Файл сценария не найден: {s_path or 'script.txt'}"))

    # 1. Check uniqueness of №
    seen_n = set()
    for it in items:
        if it.n in seen_n:
            errors.append(ValidationError(it.n, "№", f"Дублирующийся номер №{it.n}"))
        seen_n.add(it.n)

    # 2. Check each item
    for it in items:
        # Non-empty block
        if not it.block:
            errors.append(ValidationError(it.n, "Блок", "Поле 'Блок' пустое"))

        # Non-empty phrase
        if not it.phrase:
            errors.append(ValidationError(it.n, "Фраза", "Поле 'Фраза' пустое"))
        elif script_normalized:
            norm_phrase = normalize_text(it.phrase)
            if norm_phrase and norm_phrase not in script_normalized:
                errors.append(
                    ValidationError(
                        it.n,
                        "Фраза",
                        f"Фраза не найдена в сценарии (нормализовано: '{norm_phrase[:40]}...')",
                    )
                )

        # Kind
        if not it.kind:
            errors.append(ValidationError(it.n, "Вид", "Поле 'Вид' пустое"))
        elif it.kind not in VALID_KINDS:
            errors.append(
                ValidationError(
                    it.n,
                    "Вид",
                    f"Недопустимое значение '{it.kind}'. Ожидается одно из: {', '.join(sorted(VALID_KINDS))}",
                )
            )

        # Duration
        if it.duration is None or it.duration <= 0:
            errors.append(ValidationError(it.n, "Длительность", f"Некорректная длительность: {it.duration}"))

        # Priority
        if it.priority and it.priority not in VALID_PRIORITIES:
            errors.append(
                ValidationError(
                    it.n,
                    "Приоритет",
                    f"Недопустимый приоритет '{it.priority}'. Ожидается A, B или C",
                )
            )

        # Status
        norm_status = it.status.lower() if it.status else ""
        if norm_status and not any(norm_status.startswith(v) for v in VALID_STATUSES):
            errors.append(
                ValidationError(
                    it.n,
                    "Статус",
                    f"Неизвестный статус '{it.status}'. Ожидается: найти, скачано, ошибка, пропуск",
                    is_warning=True,
                )
            )

        # Timecode
        if it.tc:
            try:
                tc_res = parse_tc(it.tc)
                if tc_res is not None:
                    st, en = tc_res
                    if en is not None and en <= st:
                        errors.append(ValidationError(it.n, "Таймкод", f"Конец таймкода ({en}) раньше начала ({st})"))
            except Exception as e:
                errors.append(ValidationError(it.n, "Таймкод", f"Не удалось разобрать таймкод '{it.tc}': {e}"))

    return items, errors


def print_validation_report(errors: List[ValidationError]) -> int:
    crit_errors = [e for e in errors if not e.is_warning]
    warnings = [e for e in errors if e.is_warning]

    print(f"\nРезультаты валидации: {len(crit_errors)} ошибок, {len(warnings)} предупреждений\n")

    if not errors:
        print("  ✓ Все проверки успешно пройдены. Таблица готова к обработке!")
        return 0

    header = f"{'№':^6} | {'Поле':^15} | {'Тип':^8} | {'Сообщение'}"
    print(header)
    print("-" * 80)
    for err in errors:
        type_str = "ПРЕДУПР" if err.is_warning else "ОШИБКА"
        n_str = f"№{err.n}" if err.n > 0 else "-"
        print(f"{n_str:^6} | {err.field:^15} | {type_str:^8} | {err.message}")

    return 1 if crit_errors else 0


def main():
    parser = argparse.ArgumentParser(description="Validate cue sheet for skippr auto-assembly pipeline.")
    parser.add_argument("table", help="Path to montazhny_list.xlsx")
    parser.add_argument("--script", help="Path to script.txt")
    parser.add_argument("--allow-missing-script", action="store_true", help="Do not fail if script.txt is missing")
    args = parser.parse_args()

    _, errors = validate_cue_sheet(args.table, args.script, args.allow_missing_script)
    exit_code = print_validation_report(errors)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
