#!/usr/bin/env python3
"""
skippr — Automated Rough-Cut Assembly Pipeline for DaVinci Resolve Studio 20.
CLI steps:
  skippr template [-o template.xlsx]
  skippr validate <table.xlsx> [--script script.txt]
  skippr align <table.xlsx> [--voiceover voiceover.wav]
  skippr grab <table.xlsx> [-o out_dir] [--dry-run]
  skippr plan <table.xlsx> [-o out_dir]
  skippr export <plan.json> [-o timeline.fcpxml]
  skippr all <table.xlsx> [-o out_dir] [--dry-run]
"""
import argparse
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if _s and hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import grab
from make_template import create_template
from validate import validate_cue_sheet, print_validation_report
from align import run_align
from plan import run_plan
from export_fcpxml import run_export


def step_all(
    table_path: str,
    out_dir: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    only: str | None = None,
    edl: bool = False,
):
    p_tab = Path(table_path)
    if not p_tab.exists():
        sys.exit(f"Таблица не найдена: {p_tab}")

    out = Path(out_dir) if out_dir else p_tab.parent
    out.mkdir(parents=True, exist_ok=True)

    print("════════════════════════════════════════════════════════════════════════")
    print(f"🎬 skippr: Запуск полного конвейера монтажа для {p_tab.name}")
    print(f"   Рабочая папка: {out.resolve()}")
    print("════════════════════════════════════════════════════════════════════════\n")

    # 1. Валидация
    print("[1/5] 📋 Валидация таблицы и сценария...")
    items, errors = validate_cue_sheet(p_tab, allow_missing_script=dry_run)
    code = print_validation_report(errors)
    if code != 0 and not dry_run:
        sys.exit("Исправьте критические ошибки в таблице перед запуском.")

    # 2. Выравнивание озвучки
    print("\n[2/5] 🎙️ Выравнивание фраз сценария со звуковой дорожкой...")
    phrases_file = run_align(table_path=p_tab, out_dir=out, force=force)

    # 3. Скачивание и нарезка клипов
    print("\n[3/5] ✂️ Сбор и нарезка видеоклипов...")
    # Prepare argv for grab.main()
    grab_argv = ["grab.py", str(p_tab), "-o", str(out / "clips")]
    if dry_run:
        grab_argv.append("--dry-run")
    if only:
        grab_argv.extend(["--only", only])

    old_argv = sys.argv
    try:
        sys.argv = grab_argv
        grab.main()
    finally:
        sys.argv = old_argv

    # 4. Построение плана монтажа
    print("\n[4/5] 📐 Расчёт плана таймлайна (plan.json)...")
    plan_file = run_plan(table_path=p_tab, phrases_path=phrases_file, clips_dir=out / "clips", out_dir=out)

    # 5. Экспорт в DaVinci Resolve (FCPXML 1.9)
    print("\n[5/5] 🎞️ Экспорт таймлайна FCPXML и отчёта...")
    xml_file, report_file = run_export(plan_path=plan_file, out_xml_path=out / "timeline.fcpxml", table_path=p_tab)

    if edl:
        from export_edl import build_edl
        edl_file = out / "timeline.edl"
        build_edl(plan_path=plan_file, table_path=p_tab, out_path=edl_file)
        print(f"   ✓ Резервный таймлайн EDL:        {edl_file.resolve()}")

    print("\n════════════════════════════════════════════════════════════════════════")
    print("🎉 Конвейер успешно завершён!")
    print(f"   ✓ Готовый таймлайн для Resolve: {xml_file.resolve()}")
    print(f"   ✓ Отчёт с замечаниями:          {report_file.resolve()}")
    print("════════════════════════════════════════════════════════════════════════")



def main():
    # Backwards compatibility: if invoked directly with file or url without subcommand
    first_arg = sys.argv[1].lower() if len(sys.argv) > 1 else ""
    known_commands = {"template", "validate", "align", "grab", "plan", "export", "all", "-h", "--help"}

    if first_arg not in known_commands and not first_arg.startswith("-"):
        # Legacy direct grab call
        grab.main()
        return

    parser = argparse.ArgumentParser(
        prog="skippr",
        description="skippr — Automated Rough-Cut Assembly Pipeline for DaVinci Resolve Studio 20",
    )
    subparsers = parser.add_subparsers(dest="command")

    # template
    sub_tpl = subparsers.add_parser("template", help="Создать пустой шаблон монтажного листа")
    sub_tpl.add_argument("-o", "--output", default="montazhny_list_template.xlsx", help="Выходной xlsx файл")

    # validate
    sub_val = subparsers.add_parser("validate", help="Проверить таблицу перед запуском")
    sub_val.add_argument("table", help="Путь к таблице (xlsx)")
    sub_val.add_argument("--script", help="Путь к script.txt")
    sub_val.add_argument("--allow-missing-script", action="store_true")

    # align
    sub_aln = subparsers.add_parser("align", help="Синхронизировать фразы таблицы со звуком озвучки")
    sub_aln.add_argument("table", help="Путь к таблице (xlsx)")
    sub_aln.add_argument("--voiceover", help="Файл озвучки (wav/mp3)")
    sub_aln.add_argument("--transcript", help="Предварительная расшифровка transcript.json")
    sub_aln.add_argument("-o", "--out", help="Папка выгрузки phrases.json")
    sub_aln.add_argument("--force", action="store_true")

    # grab
    sub_grb = subparsers.add_parser("grab", help="Скачать и нарезать клипы по таблице")
    sub_grb.add_argument("table", help="Путь к таблице (xlsx)")
    sub_grb.add_argument("-o", "--out", help="Папка для клипов")
    sub_grb.add_argument("--dry-run", action="store_true")
    sub_grb.add_argument("--redo", action="store_true", help="Перерезать/перекачать существующие клипы")
    sub_grb.add_argument("--only", help="Номера строк: 1,3-5")
    sub_grb.add_argument("--priority", help="Приоритет: A, B")
    sub_grb.add_argument("--proxy", help="HTTP/SOCKS5 прокси")
    sub_grb.add_argument("--cookies-from-browser", dest="cfb")
    sub_grb.add_argument("--cookies", help="cookies.txt")


    # plan
    sub_pln = subparsers.add_parser("plan", help="Рассчитать план таймлайна (plan.json)")
    sub_pln.add_argument("table", help="Путь к таблице (xlsx)")
    sub_pln.add_argument("--phrases", help="Путь к phrases.json")
    sub_pln.add_argument("--clips", help="Папка с клипами")
    sub_pln.add_argument("-o", "--out", help="Папка выгрузки plan.json")

    # export
    sub_exp = subparsers.add_parser("export", help="Сгенерировать timeline.fcpxml для DaVinci Resolve")
    sub_exp.add_argument("plan", help="Путь к plan.json")
    sub_exp.add_argument("-o", "--out", help="Путь к timeline.fcpxml")
    sub_exp.add_argument("--table", help="Таблица (для настроек)")
    sub_exp.add_argument("--voiceover", help="Файл озвучки")
    sub_exp.add_argument("--edl", action="store_true", help="Также экспортировать резервный timeline.edl")

    # all
    sub_all = subparsers.add_parser("all", help="Запустить полный конвейер (validate -> align -> grab -> plan -> export)")
    sub_all.add_argument("table", help="Путь к таблице (xlsx)")
    sub_all.add_argument("-o", "--out", help="Рабочая папка проекта")
    sub_all.add_argument("--dry-run", action="store_true", help="Режим симуляции без загрузки видео")
    sub_all.add_argument("--force", action="store_true", help="Пересчитать существующие кэши")
    sub_all.add_argument("--only", help="Ограничить номерами строк: 1,3-5")
    sub_all.add_argument("--edl", action="store_true", help="Также экспортировать резервный timeline.edl")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "template":
        create_template(args.output)
        print(f"Шаблон создан: {args.output}")
    elif args.command == "validate":
        _, errors = validate_cue_sheet(args.table, args.script, args.allow_missing_script)
        code = print_validation_report(errors)
        sys.exit(code)
    elif args.command == "align":
        run_align(args.table, voiceover_path=args.voiceover, transcript_path=args.transcript, out_dir=args.out, force=args.force)
    elif args.command == "grab":
        # Pass through to grab.main()
        argv = ["grab.py", args.table]
        if args.out: argv.extend(["-o", args.out])
        if args.dry_run: argv.append("--dry-run")
        if args.only: argv.extend(["--only", args.only])
        if args.priority: argv.extend(["--priority", args.priority])
        if getattr(args, "redo", False): argv.append("--redo")
        if getattr(args, "proxy", None): argv.extend(["--proxy", args.proxy])
        if getattr(args, "cfb", None): argv.extend(["--cookies-from-browser", args.cfb])
        if getattr(args, "cookies", None): argv.extend(["--cookies", args.cookies])
        sys.argv = argv
        grab.main()

    elif args.command == "plan":
        run_plan(args.table, phrases_path=args.phrases, clips_dir=args.clips, out_dir=args.out)
    elif args.command == "export":
        xml_p, _ = run_export(args.plan, out_xml_path=args.out, table_path=args.table, voiceover_path=args.voiceover)
        if args.edl:
            from export_edl import build_edl
            edl_p = xml_p.parent / "timeline.edl"
            build_edl(Path(args.plan), table_path=Path(args.table) if args.table else None, out_path=edl_p)
            print(f"  ✓ EDL:      {edl_p.resolve()}")
    elif args.command == "all":
        step_all(args.table, out_dir=args.out, dry_run=args.dry_run, force=args.force, only=args.only, edl=args.edl)



if __name__ == "__main__":
    main()
