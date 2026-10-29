#!/usr/bin/env python3
"""
export_fcpxml.py — Generates DaVinci Resolve Studio 20 compatible timeline.fcpxml (FCPXML 1.9).
- Project format: fps and resolution from settings
- A1: full voiceover starting at 0s
- V1: clips (without audio), separated by gaps
- V2: priority C clips
- Markers: block names, row numbers, needs_review, shortage, overlap, placeholders
- File paths: absolute with file:/// URI encoding (Windows, Cyrillic, spaces safe)
- Validates XML before saving
- Generates report.md
"""
import argparse
import json
from pathlib import Path
import sys
from typing import List, Dict, Any, Optional, Tuple
import xml.etree.ElementTree as ET

for _s in (sys.stdout, sys.stderr):
    if _s and hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

from skippr_core.config import ProjectSettings, load_settings
from skippr_core.fps import sec_to_frames, frames_to_sec, format_fcpxml_time, format_fcpxml_frame_duration


def file_to_uri(file_path: str | Path) -> str:
    """Encodes a local file path into a standards-compliant file:/// URI."""
    p = Path(file_path).resolve()
    return p.as_uri()


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".gif"}


def get_media_duration_frames(file_path: Path, fps: float) -> int:
    """
    Returns actual frame count for DaVinci Resolve FCPXML asset duration.
    - Still images: 1 frame (Resolve expects 1 frame for still image assets).
    - Video clips: actual frame count probed via cv2 / ffprobe.
    """
    ext = file_path.suffix.lower()
    if ext in IMAGE_EXTS:
        return 1

    try:
        import cv2
        cap = cv2.VideoCapture(str(file_path))
        if cap.isOpened():
            frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            cap.release()
            if frames > 0:
                return frames
    except Exception:
        pass

    try:
        import subprocess, json as _j
        cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0",
               "-show_entries", "stream=nb_frames,duration", "-of", "json", str(file_path)]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            d = _j.loads(res.stdout)
            streams = d.get("streams", [])
            if streams:
                st = streams[0]
                nb = st.get("nb_frames")
                if nb and str(nb).isdigit():
                    return int(nb)
                dur = st.get("duration")
                if dur:
                    return int(round(float(dur) * fps))
    except Exception:
        pass

    return sec_to_frames(10.0, fps)


def get_audio_duration_frames(audio_path: Path, fps: float) -> int:
    """Returns duration in video frames for audio voiceover."""
    ext = audio_path.suffix.lower()
    if ext == ".wav":
        try:
            import wave
            with wave.open(str(audio_path), "rb") as w:
                frames = w.getnframes()
                rate = w.getframerate()
                if rate > 0:
                    dur_sec = frames / float(rate)
                    return int(round(dur_sec * fps))
        except Exception:
            pass

    try:
        import subprocess, json as _j
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(audio_path)]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            d = _j.loads(res.stdout)
            dur = d.get("format", {}).get("duration")
            if dur:
                return int(round(float(dur) * fps))
    except Exception:
        pass

    return sec_to_frames(30.0, fps)


def resolve_clip_bounds(fpath: str, s_in: int, dur: int, fps: float) -> Tuple[int, int, int]:
    """
    Ensures source_in + duration never exceeds actual file frames.
    Returns: (safe_s_in, safe_dur, shortage_frames)
    - safe_s_in: adjusted in-point (shifted earlier if needed to fit dur)
    - safe_dur: actual frames the video file can safely supply
    - shortage_frames: leftover frames (if file is strictly shorter than dur)
    """
    p = Path(fpath)
    if p.suffix.lower() in IMAGE_EXTS:
        return 0, dur, 0
    tot = get_media_duration_frames(p, fps)
    if s_in + dur <= tot:
        return s_in, dur, 0
    if dur <= tot:
        safe_in = max(0, tot - dur)
        return safe_in, dur, 0
    return 0, tot, dur - tot


def num_to_alpha(n: int, length: int = 5) -> str:
    """Converts an integer to a pure alphabetic string (e.g. 0 -> 'aaaaa', 1 -> 'aaaab')."""
    res = []
    for _ in range(length):
        res.append(chr(ord('a') + (n % 26)))
        n //= 26
    return "".join(reversed(res))


def ensure_safe_media_link(file_path: Path, media_dir: Optional[Path]) -> Path:
    """
    Creates a clean, short ASCII hardlink (or copy) for media files to avoid
    DaVinci Resolve MAX_PATH / URI encoding buffer overflow (>250 chars) on Windows.
    For still images, uses a pure alphabetic filename (no digits 0-9) so DaVinci
    Resolve NEVER detects them as image sequences.
    """
    if not media_dir:
        return file_path
    try:
        p = Path(file_path).resolve()
        media_dir_resolved = media_dir.resolve()
        if p.parent == media_dir_resolved:
            return p
        media_dir_resolved.mkdir(parents=True, exist_ok=True)
        import hashlib, os, shutil
        h = hashlib.md5(str(p).encode("utf-8")).hexdigest()[:10]
        ext = p.suffix.lower()
        if ext in IMAGE_EXTS:
            alpha_h = h.translate(str.maketrans("0123456789", "ghijklmnop"))
            clean_name = f"still_{alpha_h}{ext}"
        else:
            clean_name = f"vid_{h}{ext}"
        link_path = media_dir_resolved / clean_name
        if not link_path.exists():
            try:
                os.link(p, link_path)
            except Exception:
                shutil.copy2(p, link_path)
        return link_path
    except Exception:
        return file_path


def generate_fcpxml(
    plan_data: List[Dict[str, Any]],
    settings: ProjectSettings,
    voiceover_path: Optional[str | Path] = None,
    project_name: str = "Skippr Timeline",
    media_dir: Optional[Path] = None,
) -> str:
    fps = settings.fps
    frame_dur_str = format_fcpxml_frame_duration(fps)

    # 1. Root element
    root = ET.Element("fcpxml", version="1.9")
    resources = ET.SubElement(root, "resources")

    # Format resource
    ET.SubElement(
        resources,
        "format",
        id="r1",
        name=f"FFVideoFormat{settings.height}p{int(fps)}",
        frameDuration=frame_dur_str,
        width=str(settings.width),
        height=str(settings.height),
    )

    # 2. Register media assets
    # Asset for voiceover
    vo_asset_id = None
    vo_p = Path(voiceover_path) if voiceover_path else None
    vo_duration_frames = 0
    if vo_p and vo_p.exists():
        vo_asset_id = "r_vo"
        vo_duration_frames = get_audio_duration_frames(vo_p, fps)
        safe_vo_path = ensure_safe_media_link(vo_p, media_dir)
        ET.SubElement(
            resources,
            "asset",
            id=vo_asset_id,
            name=vo_p.name,
            src=file_to_uri(safe_vo_path),
            start="0s",
            duration=format_fcpxml_time(vo_duration_frames, fps),
            hasAudio="1",
            audioSources="1",
            audioChannels="2",
        )

    file_max_out: Dict[str, int] = {}
    for p in plan_data:
        fpath = p.get("file")
        if fpath:
            needed = p.get("source_in_frame", 0) + p.get("timeline_duration_frame", 0)
            file_max_out[fpath] = max(file_max_out.get(fpath, 0), needed)

    # Asset for each unique video clip / image
    clip_assets: Dict[str, str] = {}
    asset_counter = 2
    for p in plan_data:
        fpath = p.get("file")
        if fpath and fpath not in clip_assets:
            p_file = Path(fpath)
            if p_file.exists():
                aid = f"r_{asset_counter}"
                asset_counter += 1
                clip_assets[fpath] = aid
                if p_file.suffix.lower() in IMAGE_EXTS:
                    # Still images must have asset duration matching or exceeding the needed duration
                    clip_dur_f = max(file_max_out.get(fpath, sec_to_frames(10.0, fps)), 1)
                else:
                    clip_dur_f = max(get_media_duration_frames(p_file, fps), file_max_out.get(fpath, 0))
                safe_clip_path = ensure_safe_media_link(p_file, media_dir)
                ET.SubElement(
                    resources,
                    "asset",
                    id=aid,
                    name=p.get("orig_name") or p_file.name,
                    src=file_to_uri(safe_clip_path),
                    format="r1",
                    start="0s",
                    duration=format_fcpxml_time(clip_dur_f, fps),
                    hasVideo="1",
                    hasAudio="0",
                )

    # Total timeline duration
    max_end_frame = max(
        (p["timeline_start_frame"] + p["timeline_duration_frame"] for p in plan_data),
        default=sec_to_frames(10.0, fps),
    )
    if vo_duration_frames:
        timeline_total_frames = max(max_end_frame, vo_duration_frames)
    else:
        timeline_total_frames = max_end_frame

    # 3. Library & Sequence
    library = ET.SubElement(root, "library")
    event = ET.SubElement(library, "event", name="Skippr Rough Cuts")
    project = ET.SubElement(event, "project", name=project_name)
    sequence = ET.SubElement(
        project,
        "sequence",
        format="r1",
        duration=format_fcpxml_time(timeline_total_frames, fps),
        tcStart="0s",
        tcFormat="NDF",
    )
    spine = ET.SubElement(sequence, "spine")

    # 4. Separate tracks V1 and V2
    v1_items = [p for p in plan_data if p.get("track") == "V1"]
    v2_items = [p for p in plan_data if p.get("track") == "V2"]
    v1_items.sort(key=lambda x: x["timeline_start_frame"])
    v2_items.sort(key=lambda x: x["timeline_start_frame"])

    # 5. Build Spine (V1 primary storyline)
    current_frame = 0
    first_spine_elem = None
    seen_blocks = set()

    for p in v1_items:
        st_frame = p["timeline_start_frame"]
        dur_frame = p["timeline_duration_frame"]

        # Insert Gap if needed
        if st_frame > current_frame:
            gap_dur_f = st_frame - current_frame
            gap_el = ET.SubElement(
                spine,
                "gap",
                name="Gap",
                offset=format_fcpxml_time(current_frame, fps),
                duration=format_fcpxml_time(gap_dur_f, fps),
                start="0s",
            )
            if first_spine_elem is None:
                first_spine_elem = gap_el
            current_frame = st_frame

        # Check block marker
        block_name = p.get("block", "")
        is_new_block = block_name and block_name not in seen_blocks
        if is_new_block:
            seen_blocks.add(block_name)

        fpath = p.get("file")
        aid = clip_assets.get(fpath) if fpath else None

        if aid:
            # Asset clip with boundary protection against Media Offline
            clip_name = p.get("orig_name") or Path(fpath).name
            s_in_orig = p["source_in_frame"]
            safe_in, safe_dur, shortage = resolve_clip_bounds(fpath, s_in_orig, dur_frame, fps)

            clip_el = ET.SubElement(
                spine,
                "asset-clip",
                ref=aid,
                name=clip_name,
                offset=format_fcpxml_time(current_frame, fps),
                duration=format_fcpxml_time(safe_dur, fps),
                start=format_fcpxml_time(safe_in, fps),
            )
            if first_spine_elem is None:
                first_spine_elem = clip_el

            # Markers inside clip
            # 1. Main clip marker with row info
            m_val = f"№{p['n']}: {p.get('phrase', '')}"
            ET.SubElement(
                clip_el,
                "marker",
                start=format_fcpxml_time(safe_in, fps),
                duration=format_fcpxml_time(1, fps),
                value=m_val,
                completed="0",
                note=p.get("reference", ""),
            )

            # 2. Block marker if starting here
            if is_new_block:
                ET.SubElement(
                    clip_el,
                    "chapter-marker",
                    start=format_fcpxml_time(safe_in, fps),
                    duration=format_fcpxml_time(1, fps),
                    value=f"Блок: {block_name}",
                    posterOffset="0s",
                )

            # 3. Warning flags marker
            flags = list(p.get("flags", []))
            if shortage > 0 and "shortage" not in flags:
                flags.append("shortage")
            if flags:
                flag_str = ", ".join(flags)
                ET.SubElement(
                    clip_el,
                    "marker",
                    start=format_fcpxml_time(safe_in, fps),
                    duration=format_fcpxml_time(1, fps),
                    value=f"[{flag_str.upper()}] №{p['n']}",
                    completed="0",
                    note=flag_str,
                )

            # 4. If genuine shortage, fill remainder with Gap so timeline doesn't drift or go offline
            if shortage > 0:
                shortage_el = ET.SubElement(
                    spine,
                    "gap",
                    name=f"[Нехватка: {shortage}к] №{p['n']}",
                    offset=format_fcpxml_time(current_frame + safe_dur, fps),
                    duration=format_fcpxml_time(shortage, fps),
                    start="0s",
                )
                ET.SubElement(
                    shortage_el,
                    "marker",
                    start="0s",
                    duration=format_fcpxml_time(1, fps),
                    value=f"[SHORTAGE] №{p['n']} нехватка {shortage/fps:.2f}с",
                    completed="0",
                )
        else:
            # Placeholder or missing clip
            p_kind = p.get("kind", "placeholder")
            gap_el = ET.SubElement(
                spine,
                "gap",
                name=f"[Заглушка: {p_kind}] №{p['n']}",
                offset=format_fcpxml_time(current_frame, fps),
                duration=format_fcpxml_time(dur_frame, fps),
                start="0s",
            )
            if first_spine_elem is None:
                first_spine_elem = gap_el

            ET.SubElement(
                gap_el,
                "marker",
                start="0s",
                duration=format_fcpxml_time(1, fps),
                value=f"№{p['n']} [Заглушка: {p_kind}] {p.get('phrase', '')}",
                completed="0",
                note=p.get("reference", ""),
            )
            if is_new_block:
                ET.SubElement(
                    gap_el,
                    "chapter-marker",
                    start="0s",
                    duration=format_fcpxml_time(1, fps),
                    value=f"Блок: {block_name}",
                    posterOffset="0s",
                )

        current_frame += dur_frame

    # Trailing gap on spine
    if current_frame < timeline_total_frames:
        trail_dur = timeline_total_frames - current_frame
        trail_gap = ET.SubElement(
            spine,
            "gap",
            name="End Gap",
            offset=format_fcpxml_time(current_frame, fps),
            duration=format_fcpxml_time(trail_dur, fps),
            start="0s",
        )
        if first_spine_elem is None:
            first_spine_elem = trail_gap

    # If spine was completely empty
    if first_spine_elem is None:
        first_spine_elem = ET.SubElement(
            spine,
            "gap",
            name="Empty Spine",
            offset="0s",
            duration=format_fcpxml_time(timeline_total_frames, fps),
            start="0s",
        )

    # 6. Attach Audio (A1) to the first element on spine (lane="-1")
    if vo_asset_id:
        ET.SubElement(
            first_spine_elem,
            "asset-clip",
            lane="-1",
            name=Path(voiceover_path).name,
            ref=vo_asset_id,
            offset="0s",
            duration=format_fcpxml_time(vo_duration_frames, fps),
            start="0s",
            audioRole="dialogue",
        )

    # 7. Attach V2 clips (Priority C) to the first element on spine with lane="1"
    for p in v2_items:
        fpath = p.get("file")
        aid = clip_assets.get(fpath) if fpath else None
        st_f = p["timeline_start_frame"]
        dur_f = p["timeline_duration_frame"]

        if aid:
            s_in_orig = p["source_in_frame"]
            safe_in, safe_dur, _ = resolve_clip_bounds(fpath, s_in_orig, dur_f, fps)
            clip_el = ET.SubElement(
                first_spine_elem,
                "asset-clip",
                lane="1",
                ref=aid,
                name=f"[V2] {p.get('orig_name') or Path(fpath).name}",
                offset=format_fcpxml_time(st_f, fps),
                duration=format_fcpxml_time(safe_dur, fps),
                start=format_fcpxml_time(safe_in, fps),
            )
            ET.SubElement(
                clip_el,
                "marker",
                start=format_fcpxml_time(safe_in, fps),
                duration=format_fcpxml_time(1, fps),
                value=f"[V2] №{p['n']}: {p.get('phrase', '')}",
                completed="0",
                note=p.get("reference", ""),
            )
        else:
            p_kind = p.get("kind", "placeholder")
            gap_el = ET.SubElement(
                first_spine_elem,
                "gap",
                lane="1",
                name=f"[V2 Заглушка] №{p['n']}",
                offset=format_fcpxml_time(st_f, fps),
                duration=format_fcpxml_time(dur_f, fps),
                start="0s",
            )
            ET.SubElement(
                gap_el,
                "marker",
                start="0s",
                duration=format_fcpxml_time(1, fps),
                value=f"[V2 Заглушка: {p_kind}] №{p['n']}",
                completed="0",
            )

    # Convert to XML string with standard XML declaration and DOCTYPE
    xml_str = ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")
    # Insert DOCTYPE fcpxml right after xml declaration
    if "<!DOCTYPE fcpxml>" not in xml_str:
        decl_end = xml_str.find("?>")
        if decl_end != -1:
            xml_str = xml_str[:decl_end + 2] + "\n<!DOCTYPE fcpxml>\n" + xml_str[decl_end + 2:].lstrip()

    return xml_str


def validate_xml_string(xml_str: str) -> bool:
    """Verifies that the generated XML is well-formed."""
    try:
        ET.fromstring(xml_str)
        return True
    except ET.ParseError as e:
        raise ValueError(f"Ошибка валидации XML: {e}")


def generate_report(
    plan_data: List[Dict[str, Any]],
    settings: ProjectSettings,
    xml_file: Path,
) -> str:
    """Builds report.md detailing results and items requiring review."""
    total = len(plan_data)
    v1_cnt = sum(1 for p in plan_data if p.get("track") == "V1")
    v2_cnt = sum(1 for p in plan_data if p.get("track") == "V2")
    placeholders = sum(1 for p in plan_data if p.get("kind") == "placeholder" or not p.get("file"))
    clips_cnt = total - placeholders

    review_items = [p for p in plan_data if p.get("flags")]

    lines = [
        "# Отчёт конвейера skippr (Rough Cut Report)",
        "",
        "## 1. Сводка проекта",
        f"- **Таймлайн FCPXML:** `{xml_file.name}`",
        f"- **Частота кадров (FPS):** {settings.fps}",
        f"- **Разрешение:** {settings.width}x{settings.height}",
        f"- **Всего элементов на таймлайне:** {total}",
        f"  - Основная дорожка (V1): {v1_cnt}",
        f"  - Дополнительная дорожка (V2, приоритет C): {v2_cnt}",
        f"  - Скачанных клипов: {clips_cnt}",
        f"  - Заглушек под графику/текст: {placeholders}",
        f"- **Позиций, требующих внимания:** {len(review_items)}",
        "",
    ]

    if review_items:
        lines.append("## 2. ⚠️ Требуют ручной проверки в DaVinci Resolve")
        lines.append("| № | Блок | Фраза | Дорожка | Флаги | Причина / Заметка |")
        lines.append("|---|---|---|---|---|---|")
        for p in review_items:
            flags_str = ", ".join(p.get("flags", []))
            lines.append(f"| №{p['n']} | {p['block']} | {p.get('phrase', '')[:35]} | {p['track']} | **{flags_str}** | {p.get('reference', '')} |")
        lines.append("")
    else:
        lines.append("## 2. ✓ Замечаний нет")
        lines.append("Все элементы таймлайна собраны без конфликтов, рассинхронов и нехватки хронометража.")
        lines.append("")

    lines.append("## 3. Таблица элементов таймлайна")
    lines.append("| № | Блок | Фраза | Начало (с) | Длина (с) | Дорожка | Файл / Тип |")
    lines.append("|---|---|---|---|---|---|---|")
    for p in plan_data:
        file_label = Path(p['file']).name if p.get('file') else f"[{p.get('kind', 'заглушка')}]"
        lines.append(
            f"| №{p['n']} | {p['block']} | {p.get('phrase', '')[:30]} | {p['timeline_start']:.2f}s | {p['timeline_duration']:.2f}s | {p['track']} | {file_label} |"
        )

    return "\n".join(lines)


def run_export(
    plan_path: str | Path,
    out_xml_path: Optional[str | Path] = None,
    table_path: Optional[str | Path] = None,
    voiceover_path: Optional[str | Path] = None,
) -> Tuple[Path, Path]:
    p_plan = Path(plan_path)
    if not p_plan.exists():
        raise FileNotFoundError(f"Файл plan.json не найден: {p_plan}")

    plan_data = json.loads(p_plan.read_text(encoding="utf-8"))

    # Load settings from table if provided
    settings = ProjectSettings()
    if table_path and Path(table_path).exists():
        settings = load_settings(table_path)

    vo = voiceover_path or settings.voiceover_path
    if vo:
        p_vo = Path(vo)
        if not p_vo.is_file():
            candidates = [
                p_plan.parent / vo,
                p_plan.parent.parent / "audio" / p_vo.name,
                p_plan.parent.parent / "audio" / "voiceover.wav",
                p_plan.parent / "audio" / p_vo.name,
                p_plan.parent / "audio" / "voiceover.wav",
                p_vo,
            ]
            for c in candidates:
                if c.is_file():
                    vo = c.resolve()
                    break
        else:
            vo = p_vo.resolve()

    xml_p = Path(out_xml_path) if out_xml_path else (p_plan.parent / "timeline.fcpxml")
    xml_p.parent.mkdir(parents=True, exist_ok=True)

    media_dir = xml_p.parent / "_media"
    media_dir.mkdir(parents=True, exist_ok=True)

    linked_files = {}
    plan_data_linked = []
    for it in plan_data:
        it_copy = dict(it)
        fpath = it.get("file")
        if fpath:
            p = Path(fpath)
            if p.exists():
                it_copy["orig_name"] = p.name
                if fpath not in linked_files:
                    ext = p.suffix.lower()
                    if ext in IMAGE_EXTS:
                        clean_name = f"still_{num_to_alpha(len(linked_files))}{ext}"
                    else:
                        clean_name = f"vid_{len(linked_files):03d}{ext}"
                    link_path = media_dir / clean_name
                    if not link_path.exists():
                        try:
                            import os
                            os.link(p, link_path)
                        except Exception:
                            import shutil
                            shutil.copy2(p, link_path)
                    linked_files[fpath] = link_path
                it_copy["file"] = str(linked_files[fpath].resolve())
        plan_data_linked.append(it_copy)

    xml_content = generate_fcpxml(
        plan_data_linked,
        settings,
        voiceover_path=vo,
        project_name="Skippr Rough Cut",
    )
    validate_xml_string(xml_content)

    xml_p.write_text(xml_content, encoding="utf-8")

    report_p = xml_p.parent / "report.md"
    report_content = generate_report(plan_data, settings, xml_p)
    report_p.write_text(report_content, encoding="utf-8")

    print(f"\nЭкспорт FCPXML 1.9 завершен:")
    print(f"  ✓ Таймлайн: {xml_p.resolve()}")
    print(f"  ✓ Отчёт:    {report_p.resolve()}")
    return xml_p, report_p


def main():
    parser = argparse.ArgumentParser(description="Export skippr plan.json to DaVinci Resolve timeline.fcpxml.")
    parser.add_argument("plan", help="Path to plan.json")
    parser.add_argument("-o", "--out", help="Output timeline.fcpxml path")
    parser.add_argument("--table", help="Path to cue sheet (xlsx) for settings")
    parser.add_argument("--voiceover", help="Path to voiceover audio file")
    args = parser.parse_args()

    run_export(args.plan, args.out, args.table, args.voiceover)


if __name__ == "__main__":
    main()
