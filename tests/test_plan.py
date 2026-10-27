import pytest
from pathlib import Path
from plan import build_plan
from skippr_core.models import RowItem, SidecarData
from skippr_core.config import ProjectSettings


def test_plan_clip_longer_than_duration(tmp_path):
    settings = ProjectSettings(fps=25.0, handle_sec=1.5)

    # 1 item, duration 3.0s
    items = [
        RowItem(n=1, block="B", phrase="Hello", kind="клип", duration=3.0, offset=0.0, priority="A")
    ]
    phrases = [{"n": 1, "anchor_start": 5.0, "anchor_end": 7.0, "confidence": 1.0, "method": "exact"}]

    # Create dummy clip and sidecar in tmp_path
    clip_file = tmp_path / "B" / "01_Hello.mp4"
    clip_file.parent.mkdir(parents=True, exist_ok=True)
    clip_file.write_bytes(b"dummy")

    sidecar = tmp_path / "B" / "01_Hello.mp4.json"
    sidecar.write_text('{"useful_in": 1.5, "useful_out": 6.5, "handle_in": 1.5, "handle_out": 1.5}')  # 5.0s useful > 3.0s

    plan = build_plan(items, phrases, tmp_path, settings)

    assert len(plan) == 1
    p = plan[0]
    assert p.timeline_start == pytest.approx(5.0)
    assert p.timeline_duration == pytest.approx(3.0)
    assert p.source_in == pytest.approx(1.5)
    assert p.source_out == pytest.approx(4.5)
    assert p.speed == 1.0
    assert "slowed" not in p.flags
    assert "shortage" not in p.flags


def test_plan_shortage_policies(tmp_path):
    # Useful is 2.0s, target is 2.5s (shortage of 0.5s)
    # 2.0 / 2.5 = 0.8 speed (exact match for min_speed 0.8)
    settings_slow = ProjectSettings(fps=25.0, min_speed=0.8, shortage_policy=["slow", "flag"])

    items = [
        RowItem(n=1, block="B", phrase="P", kind="клип", duration=2.5, priority="A")
    ]
    phrases = [{"n": 1, "anchor_start": 0.0, "anchor_end": 2.0, "confidence": 1.0, "method": "exact"}]

    clip_file = tmp_path / "B" / "01_P.mp4"
    clip_file.parent.mkdir(parents=True, exist_ok=True)
    clip_file.write_bytes(b"dummy")

    sidecar = tmp_path / "B" / "01_P.mp4.json"
    sidecar.write_text('{"useful_in": 1.0, "useful_out": 3.0}')  # 2.0s useful

    # Test with slow policy
    plan_slow = build_plan(items, phrases, tmp_path, settings_slow)
    assert len(plan_slow) == 1
    assert plan_slow[0].speed == pytest.approx(0.8, abs=0.01)
    assert plan_slow[0].timeline_duration == pytest.approx(2.5, abs=0.05)
    assert "slowed" in plan_slow[0].flags

    # Test with gap policy
    settings_gap = ProjectSettings(fps=25.0, shortage_policy=["gap", "flag"])
    plan_gap = build_plan(items, phrases, tmp_path, settings_gap)
    assert len(plan_gap) == 1
    assert plan_gap[0].timeline_duration == pytest.approx(2.0)  # stays at available length
    assert "shortage" in plan_gap[0].flags


def test_plan_overlap_truncation_and_flag(tmp_path):
    settings = ProjectSettings(fps=25.0)

    # Item 1 starts at 2.0s, dur 3.0s -> ends at 5.0s
    # Item 2 starts at 4.0s (overlap by 1.0s)
    items = [
        RowItem(n=1, block="B", phrase="One", kind="клип", duration=3.0, priority="A"),
        RowItem(n=2, block="B", phrase="Two", kind="клип", duration=2.0, priority="A"),
    ]
    phrases = [
        {"n": 1, "anchor_start": 2.0, "anchor_end": 3.0, "confidence": 1.0, "method": "exact"},
        {"n": 2, "anchor_start": 4.0, "anchor_end": 5.0, "confidence": 1.0, "method": "exact"},
    ]

    plan = build_plan(items, phrases, tmp_path, settings)

    assert len(plan) == 2
    # Item 1 was truncated from 3.0s to 2.0s (from 2.0s to 4.0s)
    assert plan[0].timeline_start == pytest.approx(2.0)
    assert plan[0].timeline_duration == pytest.approx(2.0)
    assert "truncated_overlap" in plan[0].flags

    # Second item starts at 4.0s
    assert plan[1].timeline_start == pytest.approx(4.0)

    # Now test severe overlap (< 0.5s space left)
    phrases_severe = [
        {"n": 1, "anchor_start": 2.0, "anchor_end": 3.0, "confidence": 1.0, "method": "exact"},
        {"n": 2, "anchor_start": 2.2, "anchor_end": 3.0, "confidence": 1.0, "method": "exact"},  # only 0.2s space!
    ]
    plan_severe = build_plan(items, phrases_severe, tmp_path, settings)
    assert "overlap" in plan_severe[0].flags


def test_plan_frame_quantization(tmp_path):
    settings = ProjectSettings(fps=25.0)
    # Odd fractional time: 1.137 seconds
    items = [
        RowItem(n=1, block="B", phrase="Q", kind="клип", duration=2.333, offset=0.123, priority="A")
    ]
    phrases = [{"n": 1, "anchor_start": 1.111, "anchor_end": 2.0, "confidence": 1.0, "method": "exact"}]

    plan = build_plan(items, phrases, tmp_path, settings)
    p = plan[0]

    # Must be exact frame multiple
    assert p.timeline_start_frame == round(p.timeline_start * 25.0)
    assert p.timeline_duration_frame == round(p.timeline_duration * 25.0)
    assert p.timeline_start == p.timeline_start_frame / 25.0
    assert p.timeline_duration == p.timeline_duration_frame / 25.0
