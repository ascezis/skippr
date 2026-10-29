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

from skippr_core import grab
from skippr_core.make_template import create_template
from skippr_core.validate import validate_cue_sheet, print_validation_report
from skippr_core.align import run_align
from skippr_core.plan import run_plan
from skippr_core.export_fcpxml import run_export
from skippr_core.prep_audio import normalize_audio, print_audio_report


def step_all(
    table_path: str,
    out_dir: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    only: str | None = None,
    edl: bool = False,
    voiceover: str | None = None,
    normalize_lufs: bool = False,
    resolve: bool = False,
):
    p_tab = Path(table_path)
    if not p_tab.exists():
        sys.exit(f"Таблица не найдена: {p_tab}")

    out = Path(out_dir) if out_dir else p_tab.parent
    out.mkdir(parents=True, exist_ok=True)

    vo_path = Path(voiceover).resolve() if voiceover else None
    if vo_path and normalize_lufs:
        print("════════════════════════════════════════════════════════════════════════")
        print("🎙️ skippr: Нормализация громкости озвучки перед монтажом (-14 LUFS)...")
        print("════════════════════════════════════════════════════════════════════════\n")
        norm_vo, stats = normalize_audio(vo_path)
        print_audio_report(vo_path, norm_vo, stats)
        vo_path = norm_vo

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
    phrases_file = run_align(table_path=p_tab, voiceover_path=vo_path, out_dir=out, force=force)

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
    xml_file, report_file = run_export(plan_path=plan_file, out_xml_path=out / "timeline.fcpxml", table_path=p_tab, voiceover_path=vo_path)

    if edl:
        from skippr_core.export_edl import build_edl
        edl_file = out / "timeline.edl"
        build_edl(plan_path=plan_file, table_path=p_tab, out_path=edl_file)
        print(f"   ✓ Резервный таймлайн EDL:        {edl_file.resolve()}")

    if resolve:
        print("\n════════════════════════════════════════════════════════════════════════")
        print("🚀 [Resolve] Отправка таймлайна напрямую в DaVinci Resolve Studio...")
        print("════════════════════════════════════════════════════════════════════════")
        from skippr_core.resolve import push_to_resolve, ResolveConnectionError
        try:
            push_to_resolve(xml_file, plan_path=plan_file)
        except ResolveConnectionError as e:
            print(f"\n⚠️  Не удалось подключиться к DaVinci Resolve: {e}")
        except Exception as e:
            print(f"\n⚠️  Ошибка при импорте в DaVinci Resolve: {e}")

    print("\n════════════════════════════════════════════════════════════════════════")
    print("🎉 Конвейер успешно завершён!")
    print(f"   ✓ Готовый таймлайн для Resolve: {xml_file.resolve()}")
    print(f"   ✓ Отчёт с замечаниями:          {report_file.resolve()}")
    print("════════════════════════════════════════════════════════════════════════")



def main():
    # Backwards compatibility: if invoked directly with file or url without subcommand
    first_arg = sys.argv[1].lower() if len(sys.argv) > 1 else ""
    known_commands = {"template", "validate", "align", "grab", "images", "plan", "export", "resolve", "all", "prep-audio", "-h", "--help"}

    if first_arg not in known_commands and not first_arg.startswith("-"):
        # Legacy direct grab call
        grab.main()
        return

    parser = argparse.ArgumentParser(
        prog="skippr",
        description="skippr — Automated Rough-Cut Assembly Pipeline for DaVinci Resolve Studio 20",
    )
    subparsers = parser.add_subparsers(dest="command")

    # prep-audio
    sub_aud = subparsers.add_parser("prep-audio", help="Двухпроходная нормализация громкости (EBU R128 -14 LUFS для YouTube)")
    sub_aud.add_argument("audio", help="Исходный файл озвучки (wav/mp3/flac)")
    sub_aud.add_argument("-o", "--output", help="Выходной файл (по умолчанию: <имя>_norm.<расширение>)")
    sub_aud.add_argument("--lufs", type=float, default=-14.0, help="Целевой LUFS (по умолчанию -14.0)")
    sub_aud.add_argument("--tp", type=float, default=-1.0, help="Максимальный True Peak (по умолчанию -1.0 dBFS)")
    sub_aud.add_argument("--lra", type=float, default=11.0, help="Диапазон LRA (по умолчанию 11.0)")
    sub_aud.add_argument("--nonlinear", action="store_true", help="Разрешить динамическую компрессию вместо чистого линейного гейна")

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
    sub_aln.add_argument("--normalize-lufs", action="store_true", help="Нормализовать аудио до -14 LUFS перед выравниванием")
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

    # images
    sub_img = subparsers.add_parser("images", help="Автоматический поиск и скачивание картинок по поисковым запросам монтажного листа")
    sub_img.add_argument("table", nargs="?", default="montazhny_list_100pct.xlsx", help="Путь к таблице (xlsx)")
    sub_img.add_argument("-o", "--out", default="clips", help="Папка для сохранения (по умолчанию clips)")
    sub_img.add_argument("--block", help="Фильтр по названию блока (например, 'Вступление')")
    sub_img.add_argument("--only", help="Фильтр по номерам строк (например, '5,9,15' или '1-20')")
    sub_img.add_argument("--force", action="store_true", help="Перекачивать даже существующие файлы")
    sub_img.add_argument("--no-ambient", action="store_true", help="Не применять 1080p ambient blur для не-16:9 картинок")
    sub_img.add_argument("--dry-run", action="store_true", help="Показать план без скачивания")

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

    # resolve
    sub_res = subparsers.add_parser("resolve", help="Импортировать таймлайн FCPXML напрямую в DaVinci Resolve Studio 20")
    sub_res.add_argument("fcpxml", nargs="?", default="timeline.fcpxml", help="Путь к timeline.fcpxml (по умолчанию: timeline.fcpxml)")
    sub_res.add_argument("--plan", help="Путь к plan.json (для расстановки маркеров и метаданных)")
    sub_res.add_argument("--project", help="Имя проекта в DaVinci Resolve")
    sub_res.add_argument("--timeline", help="Имя создаваемого таймлайна в Resolve")
    sub_res.add_argument("--no-bins", action="store_true", help="Не раскладывать клипы по бинам")
    sub_res.add_argument("--no-colors", action="store_true", help="Не раскрашивать клипы на таймлайне")
    sub_res.add_argument("--no-markers", action="store_true", help="Не расставлять маркеры глав на таймлайне")

    # all
    sub_all = subparsers.add_parser("all", help="Запустить полный конвейер (validate -> align -> grab -> plan -> export)")
    sub_all.add_argument("table", help="Путь к таблице (xlsx)")
    sub_all.add_argument("-o", "--out", help="Рабочая папка проекта")
    sub_all.add_argument("--voiceover", help="Файл озвучки (wav/mp3)")
    sub_all.add_argument("--normalize-lufs", action="store_true", help="Нормализовать аудио до -14 LUFS перед монтажом")
    sub_all.add_argument("--dry-run", action="store_true", help="Режим симуляции без загрузки видео")
    sub_all.add_argument("--force", action="store_true", help="Пересчитать существующие кэши")
    sub_all.add_argument("--only", help="Ограничить номерами строк: 1,3-5")
    sub_all.add_argument("--edl", action="store_true", help="Также экспортировать резервный timeline.edl")
    sub_all.add_argument("--resolve", action="store_true", help="Автоматически отправить готовый таймлайн в DaVinci Resolve Studio")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "prep-audio":
        out, stats = normalize_audio(
            args.audio,
            output_path=args.output,
            target_i=args.lufs,
            target_tp=args.tp,
            target_lra=args.lra,
            linear=not args.nonlinear,
        )
        print_audio_report(Path(args.audio), out, stats)
    elif args.command == "template":
        create_template(args.output)
        print(f"Шаблон создан: {args.output}")
    elif args.command == "validate":
        _, errors = validate_cue_sheet(args.table, args.script, args.allow_missing_script)
        code = print_validation_report(errors)
        sys.exit(code)
    elif args.command == "align":
        vo = args.voiceover
        if vo and getattr(args, "normalize_lufs", False):
            vo_p = Path(vo)
            norm_vo, stats = normalize_audio(vo_p)
            print_audio_report(vo_p, norm_vo, stats)
            vo = str(norm_vo)
        run_align(args.table, voiceover_path=vo, transcript_path=args.transcript, out_dir=args.out, force=args.force)
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

    elif args.command == "images":
        from skippr_core.images import download_images
        t_path = Path(args.table)
        if not t_path.exists():
            alt = Path("C:/Users/azis/Desktop/ALL_FOLDERS/CrackedMachines/BDFL/montage/montazhny_list_100pct.xlsx")
            if alt.exists():
                t_path = alt
        download_images(
            table_path=t_path,
            clips_dir=args.out,
            block=args.block,
            only=args.only,
            force=args.force,
            ambient=not args.no_ambient,
            dry_run=args.dry_run,
        )
    elif args.command == "plan":
        run_plan(args.table, phrases_path=args.phrases, clips_dir=args.clips, out_dir=args.out)
    elif args.command == "export":
        xml_p, _ = run_export(args.plan, out_xml_path=args.out, table_path=args.table, voiceover_path=args.voiceover)
        if args.edl:
            from skippr_core.export_edl import build_edl
            edl_p = xml_p.parent / "timeline.edl"
            build_edl(Path(args.plan), table_path=Path(args.table) if args.table else None, out_path=edl_p)
            print(f"  ✓ EDL:      {edl_p.resolve()}")
    elif args.command == "resolve":
        from skippr_core.resolve import push_to_resolve, ResolveConnectionError
        xml_p = Path(args.fcpxml)
        if not xml_p.exists():
            alt = Path("C:/Users/azis/Desktop/ALL_FOLDERS/CrackedMachines/BDFL/montage/timeline.fcpxml")
            if alt.exists():
                xml_p = alt
        if not xml_p.exists():
            sys.exit(f"Файл таймлайна не найден: {xml_p}")
        try:
            push_to_resolve(
                fcpxml_path=xml_p,
                plan_path=args.plan,
                project_name=args.project,
                timeline_name=args.timeline,
                organize_bins=not args.no_bins,
                colorize=not args.no_colors,
                markers=not args.no_markers,
            )
        except ResolveConnectionError as e:
            sys.exit(f"\n❌ {e}")
        except Exception as e:
            sys.exit(f"\n❌ Ошибка импорта в DaVinci Resolve: {e}")
    elif args.command == "all":
        step_all(
            args.table,
            out_dir=args.out,
            dry_run=args.dry_run,
            force=args.force,
            only=args.only,
            edl=args.edl,
            voiceover=getattr(args, "voiceover", None),
            normalize_lufs=getattr(args, "normalize_lufs", False),
            resolve=getattr(args, "resolve", False),
        )



if __name__ == "__main__":
    main()
