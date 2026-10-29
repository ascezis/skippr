"""
tests/test_resolve.py — Unit tests for DaVinci Resolve Studio API integration (skippr_core/resolve.py).
Uses mocks to verify API logic without requiring DaVinci Resolve to be running.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from skippr_core.resolve import (
    ResolveConnectionError,
    connect_resolve,
    get_or_create_project,
    organize_media_pool_bins,
    colorize_timeline,
    add_block_markers,
    push_to_resolve,
)


def test_connect_resolve_failure_when_not_running():
    mock_bmd = MagicMock()
    mock_bmd.scriptapp.return_value = None

    with patch("skippr_core.resolve.get_resolve_module", return_value=mock_bmd):
        with pytest.raises(ResolveConnectionError) as exc_info:
            connect_resolve()
        assert "Не удалось подключиться к DaVinci Resolve" in str(exc_info.value)


def test_connect_resolve_success():
    mock_bmd = MagicMock()
    mock_resolve = MagicMock()
    mock_pm = MagicMock()
    mock_resolve.GetProjectManager.return_value = mock_pm
    mock_bmd.scriptapp.return_value = mock_resolve

    with patch("skippr_core.resolve.get_resolve_module", return_value=mock_bmd):
        res, pm = connect_resolve()
        assert res == mock_resolve
        assert pm == mock_pm


def test_get_or_create_project():
    mock_pm = MagicMock()
    # Case 1: current project exists
    mock_current = MagicMock()
    mock_current.GetName.return_value = "TestProj"
    mock_pm.GetCurrentProject.return_value = mock_current

    proj = get_or_create_project(mock_pm, "TestProj")
    assert proj == mock_current

    # Case 2: create new project when current is None
    mock_pm.GetCurrentProject.return_value = None
    mock_pm.LoadProject.return_value = None
    mock_new = MagicMock()
    mock_pm.CreateProject.return_value = mock_new

    proj2 = get_or_create_project(mock_pm, "NewProj")
    assert proj2 == mock_new
    mock_pm.CreateProject.assert_called_with("NewProj")


def test_organize_media_pool_bins():
    mock_mp = MagicMock()
    mock_root = MagicMock()
    mock_root.GetSubFolderList.return_value = []

    mock_audio_bin = MagicMock()
    mock_clip_bin = MagicMock()
    mock_card_bin = MagicMock()
    mock_img_bin = MagicMock()

    def add_subfolder(parent, name):
        if "Audio" in name: return mock_audio_bin
        if "Clips" in name: return mock_clip_bin
        if "Cards" in name: return mock_card_bin
        if "Images" in name: return mock_img_bin
        return MagicMock()

    mock_mp.AddSubFolder.side_effect = add_subfolder
    mock_mp.GetRootFolder.return_value = mock_root

    # Fake clips
    clip_audio = MagicMock()
    clip_audio.GetName.return_value = "voiceover.wav"
    clip_video = MagicMock()
    clip_video.GetName.return_value = "001_intro.mp4"
    clip_card = MagicMock()
    clip_card.GetName.return_value = "004_card_letter.png"
    clip_img = MagicMock()
    clip_img.GetName.return_value = "029_always_has_been.jpg"

    mock_root.GetClipList.return_value = [clip_audio, clip_video, clip_card, clip_img]

    counts = organize_media_pool_bins(mock_mp)
    assert counts.get("01_Audio") == 1
    assert counts.get("02_Clips") == 1
    assert counts.get("03_Images") == 1
    assert counts.get("04_Cards") == 1
    assert mock_mp.MoveClips.call_count == 4


def test_colorize_timeline():
    mock_tl = MagicMock()

    it_card = MagicMock()
    it_card.GetName.return_value = "004_card_title.png"

    it_video = MagicMock()
    it_video.GetName.return_value = "001_clip.mp4"

    it_img = MagicMock()
    it_img.GetName.return_value = "029_meme.jpg"

    it_v2 = MagicMock()
    it_v2.GetName.return_value = "overlay.png"

    mock_tl.GetItemListInTrack.side_effect = lambda t, idx: (
        [it_card, it_video, it_img] if idx == 1 else [it_v2]
    )

    counts = colorize_timeline(mock_tl)
    assert counts["Orange"] == 1
    assert counts["Teal"] == 1
    assert counts["Green"] == 1
    assert counts["Purple"] == 1

    it_card.SetClipColor.assert_called_with("Orange")
    it_video.SetClipColor.assert_called_with("Teal")
    it_img.SetClipColor.assert_called_with("Green")
    it_v2.SetClipColor.assert_called_with("Purple")


def test_add_block_markers():
    mock_tl = MagicMock()
    mock_tl.GetStartFrame.return_value = 90000  # standard 01:00:00:00

    plan_items = [
        {"block": "Intro", "timeline_start_frame": 0, "timeline_duration_frame": 100},
        {"block": "Intro", "timeline_start_frame": 100, "timeline_duration_frame": 150},
        {"block": "Main", "timeline_start_frame": 250, "timeline_duration_frame": 200},
    ]

    mock_tl.AddMarker.return_value = True

    count = add_block_markers(mock_tl, plan_items, fps=25.0)
    assert count == 2
    assert mock_tl.AddMarker.call_count == 2

    # Verify first marker arguments (frameId = 90000 + 0, dur = 250)
    calls = mock_tl.AddMarker.call_args_list
    assert calls[0][0][0] == 90000
    assert calls[0][0][2] == "[Intro]"
    assert calls[0][0][4] == 250  # duration span

    # Second marker (frameId = 90000 + 250, dur = 200)
    assert calls[1][0][0] == 90250
    assert calls[1][0][2] == "[Main]"
    assert calls[1][0][4] == 200


def test_push_to_resolve_e2e(tmp_path):
    fcpxml = tmp_path / "timeline.fcpxml"
    fcpxml.write_text("<fcpxml version='1.9'><resources/><library/></fcpxml>", encoding="utf-8")

    plan_file = tmp_path / "plan.json"
    plan_file.write_text('[{"block": "Test", "timeline_start_frame": 0, "timeline_duration_frame": 50}]', encoding="utf-8")

    mock_resolve = MagicMock()
    mock_pm = MagicMock()
    mock_proj = MagicMock()
    mock_proj.GetName.return_value = "MockProject"
    mock_mp = MagicMock()
    mock_tl = MagicMock()
    mock_tl.GetName.return_value = "timeline"
    mock_tl.GetStartFrame.return_value = 0
    mock_tl.GetItemListInTrack.return_value = []
    mock_tl.AddMarker.return_value = True

    mock_mp.ImportTimelineFromFile.return_value = mock_tl
    mock_root = MagicMock()
    mock_root.GetSubFolderList.return_value = []
    mock_root.GetClipList.return_value = []
    mock_mp.GetRootFolder.return_value = mock_root

    mock_proj.GetMediaPool.return_value = mock_mp
    mock_pm.GetCurrentProject.return_value = mock_proj

    with patch("skippr_core.resolve.connect_resolve", return_value=(mock_resolve, mock_pm)):
        res = push_to_resolve(fcpxml, plan_path=plan_file)
        assert res["project"] == "MockProject"
        assert res["timeline"] == "timeline"
        assert res["markers_added"] == 1
