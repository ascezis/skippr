import pytest
import subprocess
import json
from pathlib import Path
from grab import Downloader, process, probe


class MockDownloader(Downloader):
    def __init__(self, sample_video_path: Path):
        self.sample_video_path = sample_video_path

    def search(self, query: str, args):
        return [{"url": "mock://sample", "title": "Mock Sample", "dur": 10.0, "chan": "Test", "live": False}]

    def fetch_info(self, url: str, args):
        return {"id": "mock_sample", "title": "Mock Sample", "duration": 10.0, "width": 640, "height": 360}

    def download(self, url: str, stem: Path, args, label: str, ranges=None) -> Path:
        target = stem.with_suffix(".mp4")
        import shutil
        shutil.copy2(self.sample_video_path, target)
        return target


@pytest.fixture
def mock_source_video(tmp_path):
    # Generates a 10-second test video with both video and audio using FFmpeg
    vid_file = tmp_path / "mock_raw.mp4"
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc=duration=10:size=640x360:rate=25",
        "-f", "lavfi", "-i", "sine=frequency=1000:duration=10",
        "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p",
        str(vid_file),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode == 0, f"FFmpeg failed: {r.stderr}"
    assert vid_file.exists()
    return vid_file


def test_grab_strips_audio_and_handles(tmp_path, mock_source_video):
    downloader = MockDownloader(mock_source_video)

    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    final_file = out_dir / "Block" / "01_sample.mp4"

    # Settings: duration = 3.0s, handle_sec = 1.5s -> total expected duration = 6.0s
    item = {
        "n": 1,
        "block": "Block",
        "title": "Sample Clip",
        "query": "mock://sample",
        "tc": None,
        "duration": 3.0,
        "kind": "клип",
    }

    class MockArgs:
        handle_sec = 1.5
        fps = 25.0
        max_min = 20.0
        allow_long = False
        resolved_cache = out_dir / ".cache"

    notes, info = process(
        item=item,
        url="mock://sample",
        tc=None,
        args=MockArgs(),
        out=out_dir,
        final=final_file,
        label="[1/1]",
        downloader=downloader,
    )

    assert final_file.exists(), "Final clip file was not generated"

    # Criteria 5: No audio stream, duration = 3.0 + 2*1.5 = 6.0s +- 1 frame (0.04s)
    pr = probe(final_file)
    assert pr is not None
    assert pr["v"] == "h264"
    assert pr["a"] is None, "Audio stream MUST be stripped (-an)"
    assert pr["dur"] == pytest.approx(6.0, abs=0.05), f"Duration {pr['dur']} != 6.0s (+- 1 frame)"

    # Sidecar check
    sidecar_file = final_file.with_name(final_file.name + ".json")
    assert sidecar_file.exists(), "Sidecar JSON was not generated"

    sidecar = json.loads(sidecar_file.read_text(encoding="utf-8"))
    assert sidecar["handle_in"] == pytest.approx(1.5, 0.05)
    assert sidecar["handle_out"] == pytest.approx(1.5, 0.05)
    assert sidecar["useful_in"] == pytest.approx(1.5, 0.05)
    assert sidecar["useful_out"] == pytest.approx(4.5, 0.05)
    assert sidecar["useful_out"] - sidecar["useful_in"] == pytest.approx(3.0, 0.05)
