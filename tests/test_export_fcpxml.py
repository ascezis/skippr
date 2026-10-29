import pytest
import xml.etree.ElementTree as ET
from pathlib import Path
from skippr_core.export_fcpxml import generate_fcpxml, file_to_uri, validate_xml_string
from skippr_core.config import ProjectSettings


def test_file_to_uri_encoding():
    # Cyrillic and spaces in Windows path
    p = Path(r"C:\Users\test\папка ролика с пробелами\01_клип.mp4")
    uri = file_to_uri(p)
    assert uri.startswith("file://")
    # Must not contain unencoded spaces or raw Cyrillic characters in standard URI
    assert " " not in uri
    assert "%20" in uri
    assert "%D0" in uri or "%D1" in uri


def test_fcpxml_validity_and_counts(tmp_path):
    settings = ProjectSettings(fps=25.0, width=1920, height=1080)

    # Create dummy voiceover and clip files on disk
    vo_file = tmp_path / "voiceover.wav"
    vo_file.write_bytes(b"RIFF dummy wav")

    clip1 = tmp_path / "01_clip.mp4"
    clip1.write_bytes(b"dummy mp4")

    clip2_v2 = tmp_path / "02_v2_clip.mp4"
    clip2_v2.write_bytes(b"dummy mp4")

    plan_data = [
        # Clip 1 on V1 (starts at 2.0s, dur 3.0s) -> gap from 0 to 2.0s
        {
            "n": 1,
            "block": "Intro",
            "kind": "клип",
            "phrase": "Привет мир",
            "reference": "Отсылка 1",
            "file": str(clip1),
            "track": "V1",
            "timeline_start": 2.0,
            "timeline_duration": 3.0,
            "timeline_start_frame": 50,
            "timeline_duration_frame": 75,
            "source_in": 1.5,
            "source_out": 4.5,
            "source_in_frame": 38,
            "source_out_frame": 113,
            "speed": 1.0,
            "flags": ["needs_review"],
        },
        # Placeholder on V1 (starts at 6.0s, dur 2.0s) -> gap from 5.0 to 6.0s
        {
            "n": 2,
            "block": "Intro",
            "kind": "placeholder",
            "phrase": "Скриншот статьи",
            "reference": "Статья LWN",
            "file": None,
            "track": "V1",
            "timeline_start": 6.0,
            "timeline_duration": 2.0,
            "timeline_start_frame": 150,
            "timeline_duration_frame": 50,
            "source_in": 0.0,
            "source_out": 2.0,
            "source_in_frame": 0,
            "source_out_frame": 50,
            "speed": 1.0,
            "flags": ["placeholder_картинка"],
        },
        # Clip on V2 (Priority C)
        {
            "n": 3,
            "block": "B2",
            "kind": "клип",
            "phrase": "Опциональный мем",
            "reference": "Мем",
            "file": str(clip2_v2),
            "track": "V2",
            "timeline_start": 2.5,
            "timeline_duration": 2.0,
            "timeline_start_frame": 63,
            "timeline_duration_frame": 50,
            "source_in": 0.0,
            "source_out": 2.0,
            "source_in_frame": 0,
            "source_out_frame": 50,
            "speed": 1.0,
            "flags": [],
        },
    ]

    xml_text = generate_fcpxml(plan_data, settings, voiceover_path=vo_file)

    # 1. Must be valid XML
    assert validate_xml_string(xml_text) is True
    assert "<!DOCTYPE fcpxml>" in xml_text

    # Parse and inspect structure
    root = ET.fromstring(xml_text)
    assert root.tag == "fcpxml"
    assert root.attrib.get("version") == "1.9"

    # Resources check
    resources = root.find("resources")
    assert resources is not None
    assets = resources.findall("asset")
    # vo_file + clip1 + clip2_v2 = 3 assets
    assert len(assets) == 3

    # Sequence / Spine check
    spine = root.find(".//spine")
    assert spine is not None

    # Check V1 elements in spine
    # 0 to 2s gap, clip 1 (2s to 5s), 5s to 6s gap, placeholder 2 (6s to 8s), trailing gap
    gaps = spine.findall("gap")
    asset_clips = spine.findall("asset-clip")

    # In spine directly: at least 1 asset-clip (clip 1)
    assert len(asset_clips) >= 1

    # Check connected audio (lane="-1") and V2 clip (lane="1")
    all_asset_clips = spine.findall(".//asset-clip")
    audio_clips = [c for c in all_asset_clips if c.attrib.get("lane") == "-1"]
    v2_clips = [c for c in all_asset_clips if c.attrib.get("lane") == "1"]
    assert len(audio_clips) == 1
    assert len(v2_clips) == 1

    # Check markers
    all_markers = spine.findall(".//marker")
    all_chapters = spine.findall(".//chapter-marker")
    assert len(all_markers) >= 3  # Clip marker + review flag marker + placeholder marker
    assert len(all_chapters) >= 1  # Block marker
