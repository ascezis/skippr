import subprocess
import pytest
from pathlib import Path

from prep_audio import measure_loudness, normalize_audio


@pytest.fixture
def sample_wav(tmp_path: Path) -> Path:
    """Generates a short synthetic sine wave for testing."""
    wav_path = tmp_path / "test_sine.wav"
    cmd = [
        "ffmpeg",
        "-nostdin",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:duration=2",
        "-c:a",
        "pcm_s16le",
        "-ar",
        "48000",
        str(wav_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"FFmpeg failed: {res.stderr}"
    assert wav_path.exists()
    return wav_path


def test_measure_loudness(sample_wav: Path):
    stats = measure_loudness(sample_wav)
    assert "input_i" in stats
    assert "input_tp" in stats
    assert "input_lra" in stats
    assert isinstance(stats["input_i"], float)
    assert isinstance(stats["input_tp"], float)


def test_normalize_audio(sample_wav: Path, tmp_path: Path):
    out_path = tmp_path / "normalized.wav"
    out_file, stats = normalize_audio(
        sample_wav,
        output_path=out_path,
        target_i=-14.0,
        target_tp=-1.0,
    )
    assert out_file.exists()
    assert out_file == out_path
    assert "gain_applied" in stats

    # Measure normalized file to verify target compliance
    norm_stats = measure_loudness(out_file)
    # Sine wave without harmonics should land right around -14 LUFS (+- 0.5)
    assert abs(norm_stats["input_i"] - (-14.0)) < 1.0


def test_normalize_audio_same_file_rejected(sample_wav: Path):
    with pytest.raises(ValueError, match="не должен перезаписывать"):
        normalize_audio(sample_wav, output_path=sample_wav)


def test_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        measure_loudness(tmp_path / "non_existent.wav")
