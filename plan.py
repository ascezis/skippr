#!/usr/bin/env python3
"""
plan.py — Builds timeline assembly plan (plan.json) from cue sheet, speech alignment, and clip sidecars.
Rules:
- timeline_start = anchor_start + Смещение
- Quantized to integer frames on project fps grid (no drift)
- Clip length >= Duration -> take needed section, remaining is handles
- Shortage -> apply shortage_policy: slow, gap, flag
- Overlap -> truncate previous clip to next start, but not below 0.5s, else flag 'overlap'
- Priority C -> track V2, else track V1
- Placeholder for image/original/text -> kind='placeholder', file=None
"""
import argparse
import json
from pathlib import Path
import sys
from typing import List, Dict, Any, Optional, Tuple

for _s in (sys.stdout, sys.stderr):
    if _s and hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

from skippr_core.table import load_table
from skippr_core.models import RowItem, PlanItem, SidecarData
from skippr_core.config import ProjectSettings, load_settings
from skippr_core.fps import sec_to_frames, frames_to_sec


def find_clip_and_sidecar(
    item: RowItem, clips_dir: Path
) -> Tuple[Optional[Path], Optional[SidecarData]]:
    """Finds downloaded mp4 file and its sidecar metadata."""
    if not clips_dir.exists():
        return None, None

    # Search in block folder or globally by №
    patterns = [
        f"{item.block}/{item.n:02d}_*.mp4",
        f"{item.block}/{item.n}_*.mp4",
        f"**/{item.n:02d}_*.mp4",
        f"**/{item.n}_*.mp4",
    ]
    matched_file = None
    for pat in patterns:
        matches = [
            m for m in clips_dir.glob(pat)
            if not any(part.startswith(('_', '.')) for part in m.relative_to(clips_dir).parts)
        ]
        if matches:
            with_sidecar = [
                m for m in matches
                if m.with_name(m.name + ".json").exists() or m.with_suffix(".json").exists()
            ]
            matched_file = with_sidecar[0] if with_sidecar else matches[0]
            break

    if not matched_file:
        return None, None

    # Look for sidecar json
    sidecar_path = matched_file.with_name(matched_file.name + ".json")
    if not sidecar_path.exists():
        sidecar_path = matched_file.with_suffix(".json")

    sidecar_data = None
    if sidecar_path.exists():
        try:
            raw = json.loads(sidecar_path.read_text(encoding="utf-8"))
            sidecar_data = SidecarData(
                source_in=float(raw.get("source_in", 0.0)),
                source_out=float(raw.get("source_out", 0.0)),
                useful_in=float(raw.get("useful_in", 0.0)),
                useful_out=float(raw.get("useful_out", 0.0)),
                handle_in=float(raw.get("handle_in", 0.0)),
                handle_out=float(raw.get("handle_out", 0.0)),
                src_url=str(raw.get("src_url", "")),
                src_fps=float(raw.get("src_fps", 25.0)),
            )
        except Exception:
            sidecar_data = None

    return matched_file, sidecar_data


def build_plan(
    items: List[RowItem],
    phrases_data: List[Dict[str, Any]],
    clips_dir: Path,
    settings: ProjectSettings,
) -> List[PlanItem]:
    fps = settings.fps
    anchors_map = {int(p["n"]): p for p in phrases_data}

    raw_plan: List[PlanItem] = []

    for it in items:
        p_info = anchors_map.get(it.n)
        anchor_start = float(p_info["anchor_start"]) if p_info else 0.0
        p_flags = []
        if p_info:
            if p_info.get("method") == "failed" or float(p_info.get("confidence", 1.0)) < 0.65:
                p_flags.append("needs_review")

        # 1. Timeline start
        t_start_sec = anchor_start + it.offset
        t_start_frame = sec_to_frames(t_start_sec, fps)
        t_start_sec = frames_to_sec(t_start_frame, fps)

        # 2. Track
        track = "V2" if it.priority.upper() == "C" else "V1"

        # 3. Handle by kind
        if it.kind != "клип":
            # Placeholder (картинка, оригинал, текст)
            dur_frames = sec_to_frames(it.duration, fps)
            dur_sec = frames_to_sec(dur_frames, fps)
            flags = list(p_flags)
            flags.append(f"placeholder_{it.kind}")

            plan_item = PlanItem(
                n=it.n,
                block=it.block,
                kind="placeholder",
                file=None,
                track=track,
                timeline_start=t_start_sec,
                timeline_duration=dur_sec,
                timeline_start_frame=t_start_frame,
                timeline_duration_frame=dur_frames,
                source_in=0.0,
                source_out=dur_sec,
                source_in_frame=0,
                source_out_frame=dur_frames,
                speed=1.0,
                flags=flags,
                phrase=it.phrase,
                reference=it.reference,
            )
            raw_plan.append(plan_item)
            continue

        # 4. Clip
        clip_file, sidecar = find_clip_and_sidecar(it, clips_dir)
        flags = list(p_flags)

        # Useful boundaries
        if sidecar:
            useful_in = sidecar.useful_in
            useful_out = sidecar.useful_out
            useful_dur = useful_out - useful_in
        else:
            # Fallback if sidecar not found
            useful_in = settings.handle_sec
            useful_out = useful_in + it.duration
            useful_dur = it.duration
            if clip_file is None:
                flags.append("missing_file")

        target_dur_sec = it.duration
        speed = 1.0
        final_timeline_dur = target_dur_sec

        if useful_dur >= target_dur_sec:
            # Clip is long enough
            s_in = useful_in
            s_out = useful_in + target_dur_sec
            final_timeline_dur = target_dur_sec
        else:
            # Shortage!
            shortage_handled = False
            for policy in settings.shortage_policy:
                pol = policy.strip().lower()
                if pol == "slow" and not shortage_handled:
                    needed_speed = useful_dur / target_dur_sec
                    if needed_speed >= settings.min_speed:
                        speed = round(needed_speed, 3)
                        s_in = useful_in
                        s_out = useful_out
                        final_timeline_dur = target_dur_sec
                        flags.append("slowed")
                        shortage_handled = True
                    else:
                        # Cannot slow down all the way, slow down to min_speed
                        speed = settings.min_speed
                        final_timeline_dur = round(useful_dur / speed, 3)
                        s_in = useful_in
                        s_out = useful_out
                        flags.append("slowed")
                elif pol == "gap" and not shortage_handled:
                    final_timeline_dur = round(useful_dur / speed, 3)
                    s_in = useful_in
                    s_out = useful_out
                    shortage_handled = True
                elif pol == "flag":
                    flags.append("shortage")

            if not shortage_handled:
                s_in = useful_in
                s_out = useful_out
                final_timeline_dur = useful_dur

        # Quantize frames
        dur_frames = sec_to_frames(final_timeline_dur, fps)
        final_timeline_dur = frames_to_sec(dur_frames, fps)

        s_in_frame = sec_to_frames(s_in, fps)
        s_out_frame = sec_to_frames(s_out, fps)

        plan_item = PlanItem(
            n=it.n,
            block=it.block,
            kind="клип",
            file=str(clip_file.resolve()) if clip_file else None,
            track=track,
            timeline_start=t_start_sec,
            timeline_duration=final_timeline_dur,
            timeline_start_frame=t_start_frame,
            timeline_duration_frame=dur_frames,
            source_in=s_in,
            source_out=s_out,
            source_in_frame=s_in_frame,
            source_out_frame=s_out_frame,
            speed=speed,
            flags=flags,
            phrase=it.phrase,
            reference=it.reference,
        )
        raw_plan.append(plan_item)

    # 5. Overlap resolution per track
    # Sort by timeline_start_frame
    for trk in ("V1", "V2"):
        track_items = [p for p in raw_plan if p.track == trk]
        track_items.sort(key=lambda x: x.timeline_start_frame)

        for i in range(len(track_items) - 1):
            curr_item = track_items[i]
            next_item = track_items[i + 1]

            curr_end_frame = curr_item.timeline_start_frame + curr_item.timeline_duration_frame
            if curr_end_frame > next_item.timeline_start_frame:
                # Overlap detected
                avail_frames = next_item.timeline_start_frame - curr_item.timeline_start_frame
                min_frames = sec_to_frames(0.5, fps)

                if avail_frames >= min_frames:
                    # Truncate
                    curr_item.timeline_duration_frame = avail_frames
                    curr_item.timeline_duration = frames_to_sec(avail_frames, fps)
                    # Adjust source_out
                    new_source_dur = curr_item.timeline_duration * curr_item.speed
                    curr_item.source_out = curr_item.source_in + new_source_dur
                    curr_item.source_out_frame = sec_to_frames(curr_item.source_out, fps)
                    if "truncated_overlap" not in curr_item.flags:
                        curr_item.flags.append("truncated_overlap")
                else:
                    if "overlap" not in curr_item.flags:
                        curr_item.flags.append("overlap")

    # Sort final plan by timeline_start_frame, then track
    raw_plan.sort(key=lambda x: (x.timeline_start_frame, 0 if x.track == "V1" else 1))
    return raw_plan


def plan_to_dict(plan: List[PlanItem]) -> List[Dict[str, Any]]:
    return [
        {
            "n": p.n,
            "block": p.block,
            "kind": p.kind,
            "phrase": p.phrase,
            "reference": p.reference,
            "file": p.file,
            "track": p.track,
            "timeline_start": p.timeline_start,
            "timeline_duration": p.timeline_duration,
            "timeline_start_frame": p.timeline_start_frame,
            "timeline_duration_frame": p.timeline_duration_frame,
            "source_in": p.source_in,
            "source_out": p.source_out,
            "source_in_frame": p.source_in_frame,
            "source_out_frame": p.source_out_frame,
            "speed": p.speed,
            "flags": p.flags,
        }
        for p in plan
    ]


def run_plan(
    table_path: str | Path,
    phrases_path: Optional[str | Path] = None,
    clips_dir: Optional[str | Path] = None,
    out_dir: Optional[str | Path] = None,
) -> Path:
    tab_p = Path(table_path)
    items, settings, _ = load_table(tab_p)

    out = Path(out_dir) if out_dir else tab_p.parent
    out.mkdir(parents=True, exist_ok=True)

    phr_p = Path(phrases_path) if phrases_path else (out / "phrases.json")
    if not phr_p.exists():
        phr_p = tab_p.parent / "phrases.json"
    if not phr_p.exists():
        raise FileNotFoundError(f"Файл phrases.json не найден: {phr_p}. Сначала выполните skippr align.")

    phrases_data = json.loads(phr_p.read_text(encoding="utf-8"))

    c_dir = Path(clips_dir) if clips_dir else (out / "clips")
    if not c_dir.exists():
        c_dir = tab_p.parent / "clips"

    plan = build_plan(items, phrases_data, c_dir, settings)

    plan_file = out / "plan.json"
    plan_file.write_text(json.dumps(plan_to_dict(plan), ensure_ascii=False, indent=2), encoding="utf-8")

    v1_cnt = sum(1 for p in plan if p.track == "V1")
    v2_cnt = sum(1 for p in plan if p.track == "V2")
    flag_cnt = sum(1 for p in plan if p.flags)

    print(f"\nПлан монтажа построен: {len(plan)} элементов")
    print(f"  Дорожка V1: {v1_cnt}")
    print(f"  Дорожка V2: {v2_cnt}")
    print(f"  С флагами/метками: {flag_cnt}")
    print(f"План сохранён в: {plan_file.resolve()}")
    return plan_file


def main():
    parser = argparse.ArgumentParser(description="Build assembly plan.json for skippr pipeline.")
    parser.add_argument("table", help="Path to cue sheet (xlsx)")
    parser.add_argument("--phrases", help="Path to phrases.json")
    parser.add_argument("--clips", help="Clips directory")
    parser.add_argument("-o", "--out", help="Output directory")
    args = parser.parse_args()

    run_plan(args.table, args.phrases, args.clips, args.out)


if __name__ == "__main__":
    main()
