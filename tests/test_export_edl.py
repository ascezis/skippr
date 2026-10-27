import json
from pathlib import Path
from export_edl import build_edl
from skippr_core.config import ProjectSettings


def test_export_edl(tmp_path: Path):
    plan_data = [
        {
            "n": 1,
            "block": "Intro",
            "kind": "clip",
            "file": str(tmp_path / "01_test.mp4"),
            "track": "V1",
            "timeline_start": 0.0,
            "timeline_start_frames": 0,
            "timeline_duration": 4.0,
            "timeline_duration_frames": 100,
            "source_in": 1.5,
            "source_in_frames": 38,
            "source_duration": 4.0,
            "source_duration_frames": 100,
            "speed": 1.0,
            "flags": [],
        },
        {
            "n": 2,
            "block": "Main",
            "kind": "placeholder",
            "file": None,
            "track": "V1",
            "timeline_start": 5.0,
            "timeline_start_frames": 125,
            "timeline_duration": 3.0,
            "timeline_duration_frames": 75,
            "source_in": 0.0,
            "source_in_frames": 0,
            "source_duration": 3.0,
            "source_duration_frames": 75,
            "speed": 1.0,
            "flags": ["needs_review"],
        },
    ]

    plan_path = tmp_path / "plan.json"
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan_data, f)

    out_edl = tmp_path / "timeline.edl"
    settings = ProjectSettings(fps=25.0)

    content = build_edl(plan_path, out_path=out_edl, settings=settings, title="Test Timeline")

    assert out_edl.exists()
    assert "TITLE: Test Timeline" in content
    assert "FCM: NON-DROP FRAME" in content
    assert "001  AX       V     C        00:00:01:13 00:00:05:13 00:00:00:00 00:00:04:00" in content
    assert "* FROM CLIP NAME: 01_test.mp4" in content
    assert "* RESOLVE MARKER: 00:00:00:00 Cyan Block: Intro" in content
    assert "002  BL       V     C        00:00:00:00 00:00:03:00 00:00:05:00 00:00:08:00" in content
    assert "* RESOLVE MARKER: 00:00:05:00 Red Row #2 [needs_review] (Placeholder)" in content
