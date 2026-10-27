#!/usr/bin/env python3
"""
export_edl.py: CMX 3600 EDL exporter for skippr automated assembly timelines.
Generates an EDL file from plan.json for DaVinci Resolve and other NLEs as a backup format.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from skippr_core.config import ProjectSettings, load_settings_from_workbook
from skippr_core.fps import frames_to_timecode, sec_to_frames

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("export_edl")


def build_edl(
    plan_path: Path,
    table_path: Optional[Path] = None,
    out_path: Optional[Path] = None,
    settings: Optional[ProjectSettings] = None,
    title: str = "Skippr Timeline",
) -> str:
    """
    Builds a CMX 3600 EDL string and writes to out_path if specified.
    """
    if not plan_path.exists():
        raise FileNotFoundError(f"Plan file not found: {plan_path}")

    with open(plan_path, "r", encoding="utf-8") as f:
        plan_items: List[Dict[str, Any]] = json.load(f)

    if settings is None:
        if table_path and table_path.exists():
            try:
                settings = load_settings_from_workbook(table_path)
            except Exception as e:
                logger.warning("Could not read settings from table: %s. Using default 25 fps.", e)
                settings = ProjectSettings()
        else:
            settings = ProjectSettings()

    fps = settings.fps

    lines = [
        f"TITLE: {title}",
        "FCM: NON-DROP FRAME",
        "",
    ]

    event_idx = 1
    last_block = None

    for item in plan_items:
        kind = item.get("kind", "clip")
        block = item.get("block", "")
        n = item.get("n", 0)
        file_path_str = item.get("file")
        flags = item.get("flags", [])

        # Start and duration frames
        rec_start_f = item.get("timeline_start_frames")
        if rec_start_f is None:
            rec_start_f = sec_to_frames(item.get("timeline_start", 0.0), fps)

        rec_dur_f = item.get("timeline_duration_frames")
        if rec_dur_f is None:
            rec_dur_f = sec_to_frames(item.get("timeline_duration", 0.0), fps)

        rec_end_f = rec_start_f + rec_dur_f

        src_start_f = item.get("source_in_frames")
        if src_start_f is None:
            src_start_f = sec_to_frames(item.get("source_in", 0.0), fps)

        src_dur_f = item.get("source_duration_frames")
        if src_dur_f is None:
            src_dur_f = sec_to_frames(item.get("source_duration", 0.0), fps)
            if src_dur_f == 0:
                src_dur_f = rec_dur_f

        src_end_f = src_start_f + src_dur_f

        src_in_tc = frames_to_timecode(src_start_f, fps)
        src_out_tc = frames_to_timecode(src_end_f, fps)
        rec_in_tc = frames_to_timecode(rec_start_f, fps)
        rec_out_tc = frames_to_timecode(rec_end_f, fps)

        reel = "AX"
        if file_path_str:
            p = Path(file_path_str)
            clip_name = p.name
        else:
            clip_name = f"PLACEHOLDER_{kind.upper()}"
            reel = "BL"

        event_str = f"{event_idx:03d}  {reel:<8s} V     C        {src_in_tc} {src_out_tc} {rec_in_tc} {rec_out_tc}"
        lines.append(event_str)
        lines.append(f"* FROM CLIP NAME: {clip_name}")

        # Block marker
        if block and block != last_block:
            last_block = block
            lines.append(f"* RESOLVE MARKER: {rec_in_tc} Cyan Block: {block}")

        # Row marker
        marker_color = "Blue"
        if "needs_review" in flags:
            marker_color = "Red"
        elif "shortage" in flags:
            marker_color = "Orange"
        elif "overlap" in flags:
            marker_color = "Yellow"
        elif kind == "placeholder":
            marker_color = "Purple"

        desc_parts = [f"Row #{n}"]
        if flags:
            desc_parts.append(f"[{','.join(flags)}]")
        if kind == "placeholder":
            desc_parts.append("(Placeholder)")

        lines.append(f"* RESOLVE MARKER: {rec_in_tc} {marker_color} {' '.join(desc_parts)}")
        lines.append("")

        event_idx += 1

    content = "\n".join(lines) + "\n"

    if out_path:
        out_path = Path(out_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info("EDL exported successfully: %s", out_path)

    return content


def main() -> int:
    parser = argparse.ArgumentParser(description="Export plan.json to CMX 3600 EDL for DaVinci Resolve.")
    parser.add_argument("--plan", type=Path, default=Path("plan.json"), help="Path to plan.json")
    parser.add_argument("--table", type=Path, default=None, help="Path to cue sheet (to read fps)")
    parser.add_argument("-o", "--out", type=Path, default=Path("timeline.edl"), help="Output EDL file path")
    parser.add_argument("--title", type=str, default="Skippr Timeline", help="Timeline title")

    args = parser.parse_args()

    try:
        build_edl(
            plan_path=args.plan,
            table_path=args.table,
            out_path=args.out,
            title=args.title,
        )
        print(f"EDL exported: {args.out}")
        return 0
    except Exception as e:
        logger.error("Failed to export EDL: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
