#!/usr/bin/env python3
"""
skippr_core/resolve.py — Direct DaVinci Resolve Studio 20 Integration via Scripting API.

Features:
1. One-click timeline import into running DaVinci Resolve Studio instance.
2. Auto-organization of Media Pool into clean Bins:
   - 01_Audio (Voiceover / sound)
   - 02_Clips (B-roll footage)
   - 03_Images (Memes, photos, logos)
   - 04_Cards (Storyboard placeholders / graphics to produce)
3. Color-coding of timeline items:
   - Orange: Storyboard cards & missing graphics (high visibility action items)
   - Teal: B-roll video footage
   - Green: Still graphics, memes, photos
   - Purple: Track V2 overlays
4. Range / Duration markers for story blocks (e.g. [Вступление], [BDFL], [Мауро], [Финал]).
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

for _s in (sys.stdout, sys.stderr):
    if _s and hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


class ResolveConnectionError(Exception):
    """Raised when unable to connect to running DaVinci Resolve Studio."""
    pass


def get_resolve_module():
    """Dynamically locates and imports DaVinciResolveScript module."""
    if "DaVinciResolveScript" in sys.modules:
        return sys.modules["DaVinciResolveScript"]

    # 1. Check if already in PYTHONPATH
    try:
        import DaVinciResolveScript as bmd
        return bmd
    except ImportError:
        pass

    # 2. Platform default locations
    paths_to_try = []
    if sys.platform.startswith("win"):
        prog_data = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        scripting_dir = Path(prog_data) / "Blackmagic Design" / "DaVinci Resolve" / "Support" / "Developer" / "Scripting"
        paths_to_try.append(scripting_dir / "Modules")
        # Ensure DLL location is in PATH
        install_dir = Path(r"C:\Program Files\Blackmagic Design\DaVinci Resolve")
        if install_dir.exists() and str(install_dir) not in os.environ.get("PATH", ""):
            os.environ["PATH"] = f"{install_dir};{os.environ.get('PATH', '')}"
    elif sys.platform.startswith("darwin"):
        paths_to_try.append(Path("/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"))
    else:
        paths_to_try.append(Path("/opt/resolve/Developer/Scripting/Modules"))

    for p in paths_to_try:
        if p.exists() and str(p) not in sys.path:
            sys.path.insert(0, str(p))
            try:
                import DaVinciResolveScript as bmd
                return bmd
            except Exception:
                pass

    raise ResolveConnectionError(
        "Модуль DaVinciResolveScript не найден.\n"
        "Убедитесь, что установлен DaVinci Resolve Studio 18/19/20."
    )


def connect_resolve():
    """
    Connects to running DaVinci Resolve Studio instance.
    Returns (resolve_app, project_manager).
    """
    bmd = get_resolve_module()
    resolve = bmd.scriptapp("Resolve")
    if not resolve:
        raise ResolveConnectionError(
            "Не удалось подключиться к DaVinci Resolve Studio.\n"
            "1. Запустите DaVinci Resolve Studio.\n"
            "2. В меню перейдите: Preferences -> System -> General.\n"
            "3. Убедитесь, что 'External scripting using' установлено в 'Local' или 'Network'."
        )

    pm = resolve.GetProjectManager()
    if not pm:
        raise ResolveConnectionError("Не удалось получить ProjectManager из DaVinci Resolve.")

    return resolve, pm


def get_or_create_project(pm, project_name: Optional[str] = None):
    """Returns currently open project or creates/loads the requested one."""
    current = pm.GetCurrentProject()
    if current:
        if not project_name or current.GetName() == project_name:
            return current

    # Try loading existing project
    if project_name:
        loaded = pm.LoadProject(project_name)
        if loaded:
            return loaded
        # Create new project
        created = pm.CreateProject(project_name)
        if created:
            return created

    return current or pm.CreateProject("skippr_rough_cut")


def organize_media_pool_bins(media_pool, backup_folder_path: Optional[Path] = None) -> Dict[str, int]:
    """
    Organizes clips in Root Folder into structured bins:
      - 01_Audio
      - 02_Clips
      - 03_Images
      - 04_Cards
      - 00_Backup_Originals (if backup source path is provided)
    Returns count of clips moved per bin.
    """
    root = media_pool.GetRootFolder()
    existing_folders = {f.GetName(): f for f in (root.GetSubFolderList() or [])}

    target_bin_names = {
        "audio": "01_Audio",
        "clips": "02_Clips",
        "images": "03_Images",
        "cards": "04_Cards",
        "backup": "00_Backup_Originals",
    }

    folders = {}
    for key, name in target_bin_names.items():
        if key == "backup" and not backup_folder_path:
            continue
        if name in existing_folders:
            folders[key] = existing_folders[name]
        else:
            try:
                folders[key] = media_pool.AddSubFolder(root, name)
            except Exception:
                folders[key] = None

    clips = root.GetClipList() or []
    audio_clips = []
    video_clips = []
    image_clips = []
    card_clips = []

    for c in clips:
        name = c.GetName().lower()
        if any(name.endswith(ext) for ext in [".wav", ".mp3", ".m4a", ".aac", ".flac"]):
            audio_clips.append(c)
        elif "_card_" in name or name.endswith("_card.png"):
            card_clips.append(c)
        elif any(name.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"]):
            image_clips.append(c)
        elif any(name.endswith(ext) for ext in [".mp4", ".mov", ".mkv", ".avi"]):
            video_clips.append(c)

    counts = {}
    if audio_clips and folders.get("audio"):
        media_pool.MoveClips(audio_clips, folders["audio"])
        counts["01_Audio"] = len(audio_clips)
    if video_clips and folders.get("clips"):
        media_pool.MoveClips(video_clips, folders["clips"])
        counts["02_Clips"] = len(video_clips)
    if image_clips and folders.get("images"):
        media_pool.MoveClips(image_clips, folders["images"])
        counts["03_Images"] = len(image_clips)
    if card_clips and folders.get("cards"):
        media_pool.MoveClips(card_clips, folders["cards"])
        counts["04_Cards"] = len(card_clips)

    if backup_folder_path and backup_folder_path.exists() and folders.get("backup"):
        try:
            media_pool.SetCurrentFolder(folders["backup"])
            raw_vids = [str(f.resolve()) for f in backup_folder_path.rglob("*.mp4")]
            if raw_vids:
                imported = media_pool.ImportMedia(raw_vids)
                if imported:
                    counts["00_Backup_Originals"] = len(imported)
        except Exception:
            pass
        finally:
            media_pool.SetCurrentFolder(root)

    return counts


def colorize_timeline(timeline) -> Dict[str, int]:
    """
    Applies meaningful clip colors across timeline tracks:
      - Orange: Storyboard cards / placeholders (action items for editor)
      - Teal: B-roll video footage
      - Green: Still graphics, memes, photos
      - Purple: Track V2 overlays
    """
    counts = {"Orange": 0, "Teal": 0, "Green": 0, "Purple": 0}

    # Track V1
    v1_items = timeline.GetItemListInTrack("video", 1) or []
    for it in v1_items:
        try:
            name = (it.GetName() or "").lower()
            if "_card_" in name or name.endswith("_card.png"):
                it.SetClipColor("Orange")
                counts["Orange"] += 1
            elif any(name.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"]):
                it.SetClipColor("Green")
                counts["Green"] += 1
            elif any(name.endswith(ext) for ext in [".mp4", ".mov", ".mkv", ".avi"]):
                it.SetClipColor("Teal")
                counts["Teal"] += 1
        except Exception:
            pass

    # Track V2 (overlays / picture-in-picture)
    try:
        v2_items = timeline.GetItemListInTrack("video", 2) or []
        for it in v2_items:
            try:
                it.SetClipColor("Purple")
                counts["Purple"] += 1
            except Exception:
                pass
    except Exception:
        pass

    return counts


def add_block_markers(timeline, plan_items: List[Dict[str, Any]], fps: float = 25.0) -> int:
    """
    Adds range / duration markers to timeline for each major block/chapter.
    In Resolve, a marker with duration > 1 appears as a colored span on the ruler!
    """
    if not plan_items:
        return 0

    start_frame_base = timeline.GetStartFrame()

    # Group items by block
    blocks: Dict[str, Dict[str, Any]] = {}
    for p in plan_items:
        blk = p.get("block", "Блок")
        s_f = p.get("timeline_start_frame", 0)
        d_f = p.get("timeline_duration_frame", 0)
        end_f = s_f + d_f

        if blk not in blocks:
            blocks[blk] = {
                "name": blk,
                "start_frame": s_f,
                "end_frame": end_f,
                "count": 1,
            }
        else:
            blocks[blk]["start_frame"] = min(blocks[blk]["start_frame"], s_f)
            blocks[blk]["end_frame"] = max(blocks[blk]["end_frame"], end_f)
            blocks[blk]["count"] += 1

    # Marker colors to cycle through
    palette = ["Cyan", "Sky", "Mint", "Blue", "Lavender", "Yellow"]
    marker_count = 0

    for idx, (blk_name, info) in enumerate(blocks.items()):
        color = palette[idx % len(palette)]
        f_start = start_frame_base + info["start_frame"]
        dur = max(1, info["end_frame"] - info["start_frame"])
        note = f"{info['count']} элементов ({round(dur / fps, 1)}с)"
        try:
            ok = timeline.AddMarker(
                f_start,
                color,
                f"[{blk_name}]",
                note,
                dur,
                ""
            )
            if ok:
                marker_count += 1
        except Exception:
            pass

    return marker_count


def push_to_resolve(
    fcpxml_path: str | Path,
    plan_path: Optional[str | Path] = None,
    project_name: Optional[str] = None,
    timeline_name: Optional[str] = None,
    organize_bins: bool = True,
    colorize: bool = True,
    markers: bool = True,
) -> Dict[str, Any]:
    """
    Main entry point: imports FCPXML into DaVinci Resolve Studio and enriches it.
    """
    p_xml = Path(fcpxml_path).resolve()
    if not p_xml.exists():
        raise FileNotFoundError(f"Файл FCPXML не найден: {p_xml}")

    resolve, pm = connect_resolve()
    project = get_or_create_project(pm, project_name)
    media_pool = project.GetMediaPool()

    tl_name = timeline_name or p_xml.stem
    print(f"🎬 Подключение к DaVinci Resolve Studio успешно!")
    print(f"   Проект:   {project.GetName()}")
    print(f"   Импорт:   {p_xml.name} -> Таймлайн '{tl_name}'...")

    import_opts = {
        "timelineName": tl_name,
        "importSourceClips": True,
    }

    timeline = media_pool.ImportTimelineFromFile(str(p_xml), import_opts)
    if not timeline:
        # Check if timeline with this name already exists
        count = project.GetTimelineCount() or 0
        for i in range(1, count + 1):
            cand = project.GetTimelineByIndex(i)
            if cand and cand.GetName() == tl_name:
                timeline = cand
                project.SetCurrentTimeline(timeline)
                print(f"   ℹ️  Использован существующий таймлайн '{tl_name}'")
                break

    if not timeline:
        raise RuntimeError(
            f"Не удалось импортировать таймлайн '{tl_name}' в DaVinci Resolve.\n"
            "Проверьте, нет ли конфликта имён таймлайнов в открытом проекте."
        )

    project.SetCurrentTimeline(timeline)
    results = {
        "project": project.GetName(),
        "timeline": timeline.GetName(),
        "bins_organized": {},
        "colors_applied": {},
        "markers_added": 0,
    }

    # 1. Organize Media Pool into Bins
    if organize_bins:
        backup_dir = None
        plan_p = Path(plan_path).resolve() if plan_path else (p_xml.parent / "plan.json")
        candidate_clips = plan_p.parent / "clips"
        if candidate_clips.exists():
            backup_dir = candidate_clips
        bin_counts = organize_media_pool_bins(media_pool, backup_folder_path=backup_dir)
        results["bins_organized"] = bin_counts
        if bin_counts:
            bins_summary = ", ".join(f"{k}: {v}" for k, v in bin_counts.items())
            print(f"   📁 Media Pool разложен по бинам ({bins_summary})")

    # 2. Colorize Timeline Clips
    if colorize:
        color_counts = colorize_timeline(timeline)
        results["colors_applied"] = color_counts
        total_colored = sum(color_counts.values())
        print(f"   🎨 Цветовая разметка клипов применена ({total_colored} клипов: Orange/Teal/Green/Purple)")

    # 3. Add Block Markers
    if markers:
        plan_p = Path(plan_path).resolve() if plan_path else (p_xml.parent / "plan.json")
        if plan_p.exists():
            try:
                plan_data = json.loads(plan_p.read_text(encoding="utf-8"))
                m_count = add_block_markers(timeline, plan_data)
                results["markers_added"] = m_count
                print(f"   🚩 Расставлено {m_count} маркеров глав на таймлайне")
            except Exception as e:
                print(f"   ⚠️  Не удалось расставить маркеры: {e}")

    print(f"\n✓ Таймлайн '{timeline.GetName()}' готов к монтажу в DaVinci Resolve Studio!")
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Push FCPXML timeline directly into DaVinci Resolve Studio 20 via Scripting API."
    )
    parser.add_argument("fcpxml", help="Path to timeline.fcpxml")
    parser.add_argument("--plan", help="Path to plan.json (for markers and block metadata)")
    parser.add_argument("--project", help="DaVinci Resolve project name (default: active project)")
    parser.add_argument("--timeline", help="Custom timeline name in Resolve")
    parser.add_argument("--no-bins", action="store_true", help="Do not organize media pool into bins")
    parser.add_argument("--no-colors", action="store_true", help="Do not color-code timeline items")
    parser.add_argument("--no-markers", action="store_true", help="Do not add chapter markers")

    args = parser.parse_args()

    try:
        push_to_resolve(
            fcpxml_path=args.fcpxml,
            plan_path=args.plan,
            project_name=args.project,
            timeline_name=args.timeline,
            organize_bins=not args.no_bins,
            colorize=not args.no_colors,
            markers=not args.no_markers,
        )
    except ResolveConnectionError as e:
        sys.exit(f"\n❌ Ошибка подключения к DaVinci Resolve:\n{e}")
    except Exception as e:
        sys.exit(f"\n❌ Ошибка импорта: {e}")


if __name__ == "__main__":
    main()
