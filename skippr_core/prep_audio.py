#!/usr/bin/env python3
"""
prep_audio.py — Professional EBU R128 Loudness Normalization for YouTube/Podcasts.

Uses two-pass ffmpeg loudnorm:
- Pass 1: Measures exact integrated loudness (LUFS), True Peak (dBFS), and Loudness Range (LRA).
- Pass 2: Applies clean linear gain correction (linear=true) with True Peak limiting,
          ensuring zero dynamic distortion, pumping, or color shift.

Default Targets (YouTube Standard):
- Integrated Loudness: -14.0 LUFS
- True Peak: -1.0 dBFS
- Loudness Range: 11.0 LU
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, Tuple, Optional

for _s in (sys.stdout, sys.stderr):
    if _s and hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def check_ffmpeg() -> str:
    """Verifies ffmpeg binary is available in PATH."""
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("ffmpeg не найден в системном PATH. Установите ffmpeg для нормализации звука.")
    return path


def measure_loudness(
    audio_path: str | Path,
    target_i: float = -14.0,
    target_tp: float = -1.0,
    target_lra: float = 11.0,
) -> Dict[str, Any]:
    """
    Pass 1: Measures input audio loudness parameters using ffmpeg loudnorm.
    Returns parsed dictionary of measured stats.
    """
    check_ffmpeg()
    src = Path(audio_path)
    if not src.exists():
        raise FileNotFoundError(f"Аудиофайл не найден: {src}")

    cmd = [
        "ffmpeg",
        "-nostdin",
        "-y",
        "-i",
        str(src),
        "-af",
        f"loudnorm=I={target_i:.1f}:TP={target_tp:.1f}:LRA={target_lra:.1f}:print_format=json",
        "-f",
        "null",
        "-",
    ]

    res = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", res.stderr, re.DOTALL)
    if not m:
        raise RuntimeError(f"Не удалось извлечь данные замера loudnorm:\n{res.stderr[-500:]}")

    try:
        data = json.loads(m.group(0))
        return {
            "input_i": float(data.get("input_i", 0.0)),
            "input_tp": float(data.get("input_tp", 0.0)),
            "input_lra": float(data.get("input_lra", 0.0)),
            "input_thresh": float(data.get("input_thresh", 0.0)),
            "output_i": float(data.get("output_i", 0.0)),
            "output_tp": float(data.get("output_tp", 0.0)),
            "output_lra": float(data.get("output_lra", 0.0)),
            "output_thresh": float(data.get("output_thresh", 0.0)),
            "normalization_type": data.get("normalization_type", "linear"),
            "target_offset": float(data.get("target_offset", 0.0)),
        }
    except Exception as e:
        raise RuntimeError(f"Ошибка парсинга JSON loudnorm: {e}\nДанные: {m.group(0)}")


def normalize_audio(
    input_path: str | Path,
    output_path: Optional[str | Path] = None,
    target_i: float = -14.0,
    target_tp: float = -1.0,
    target_lra: float = 11.0,
    linear: bool = True,
    sample_rate: int = 48000,
) -> Tuple[Path, Dict[str, Any]]:
    """
    Two-pass EBU R128 loudness normalization.
    Returns (output_path, stats_dict).
    """
    src = Path(input_path).resolve()
    if not src.exists():
        raise FileNotFoundError(f"Файл не найден: {src}")

    if output_path:
        out = Path(output_path).resolve()
    else:
        out = src.with_name(f"{src.stem}_norm{src.suffix}")

    if out.resolve() == src.resolve():
        raise ValueError("Выходной путь не должен перезаписывать исходный файл напрямую.")

    out.parent.mkdir(parents=True, exist_ok=True)

    # 1. Pass 1: Measure
    stats = measure_loudness(src, target_i=target_i, target_tp=target_tp, target_lra=target_lra)

    # 2. Pass 2: Apply linear gain correction
    linear_str = "true" if linear else "false"
    af_filter = (
        f"loudnorm=I={target_i:.1f}:TP={target_tp:.1f}:LRA={target_lra:.1f}:"
        f"measured_I={stats['input_i']:.2f}:"
        f"measured_TP={stats['input_tp']:.2f}:"
        f"measured_LRA={stats['input_lra']:.2f}:"
        f"measured_thresh={stats['input_thresh']:.2f}:"
        f"offset={stats['target_offset']:.2f}:"
        f"linear={linear_str}"
    )

    cmd = [
        "ffmpeg",
        "-nostdin",
        "-y",
        "-i",
        str(src),
        "-af",
        af_filter,
        "-ar",
        str(sample_rate),
    ]

    # Preserve PCM format if wav
    if out.suffix.lower() == ".wav":
        cmd.extend(["-c:a", "pcm_s24le"])
    elif out.suffix.lower() == ".mp3":
        cmd.extend(["-c:a", "libmp3lame", "-b:a", "320k"])

    cmd.append(str(out))

    res = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if res.returncode != 0:
        raise RuntimeError(f"Ошибка ffmpeg при нормализации:\n{res.stderr[-500:]}")

    gain_applied = target_i - stats["input_i"]
    stats["gain_applied"] = round(gain_applied, 2)
    stats["target_i"] = target_i
    stats["target_tp"] = target_tp
    stats["target_lra"] = target_lra

    return out, stats


def print_audio_report(src: Path, out: Path, stats: Dict[str, Any]):
    """Pretty prints the loudness normalization report."""
    print("════════════════════════════════════════════════════════════════════════")
    print("🎙️ skippr: Нормализация громкости аудио (EBU R128 / YouTube)")
    print(f"   Исходный файл: {src.name}")
    print("════════════════════════════════════════════════════════════════════════\n")

    gain = stats.get("gain_applied", 0.0)
    sign = "+" if gain >= 0 else ""

    print("📊 Результаты замера и коррекции:")
    print(f"   • Исходная громкость:   {stats['input_i']:+.1f} LUFS")
    print(f"   • Исходный True Peak:   {stats['input_tp']:+.1f} dBFS")
    print(f"   • Динамический размах:  {stats['input_lra']:.1f} LU")
    print("   ─────────────────────────────────────────────────")
    print(f"   • Целевой стандарт:     {stats['target_i']:.1f} LUFS (YouTube)")
    print(f"   • Предел True Peak:     {stats['target_tp']:.1f} dBFS")
    print(f"   • Коррекция громкости:  {sign}{gain:.1f} dB (чистая линейная)")
    print("\n✅ Нормализованный звук сохранён:")
    print(f"   📁 {out.resolve()}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Двухпроходная нормализация громкости аудио по стандарту YouTube (EBU R128 -14 LUFS)."
    )
    parser.add_argument("audio", help="Путь к исходному аудиофайлу (wav / mp3 / flac / aac)")
    parser.add_argument("-o", "--output", help="Путь к результирующему файлу (по умолчанию: <имя>_norm.<расширение>)")
    parser.add_argument("--lufs", type=float, default=-14.0, help="Целевая интегральная громкость LUFS (по умолчанию -14.0)")
    parser.add_argument("--tp", type=float, default=-1.0, help="Максимальный True Peak dBFS (по умолчанию -1.0)")
    parser.add_argument("--lra", type=float, default=11.0, help="Целевой диапазон громкости LRA (по умолчанию 11.0)")
    parser.add_argument("--nonlinear", action="store_true", help="Разрешить динамическую компрессию вместо чистого линейного гейна")

    args = parser.parse_args()

    src = Path(args.audio)
    if not src.exists():
        sys.exit(f"Файл не найден: {src}")

    try:
        out, stats = normalize_audio(
            input_path=src,
            output_path=args.output,
            target_i=args.lufs,
            target_tp=args.tp,
            target_lra=args.lra,
            linear=not args.nonlinear,
        )
        print_audio_report(src, out, stats)
    except Exception as e:
        sys.exit(f"❌ Ошибка нормализации аудио: {e}")


if __name__ == "__main__":
    main()
