#!/usr/bin/env python3
"""
align.py — Synchronizes cue sheet phrases with voiceover audio using faster-whisper.
Features:
- Transcribes voiceover with word-level timestamps (faster-whisper)
- Caches transcript in cache/transcript.json
- Two-stage matching: Exact normalized tokens -> Fuzzy token match (rapidfuzz)
- Monotonic anchor constraint: anchors strictly increase over time
- Manual overrides via anchors_override.json or table column
- Outputs phrases.json
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
from skippr_core.text import normalize_text, tokenize_text
from skippr_core.models import RowItem, PhraseAnchor
from skippr_core.config import load_settings, ProjectSettings


def detect_device() -> Tuple[str, str]:
    """Detects available compute device for faster-whisper."""
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"


def get_transcript(
    voiceover_path: str | Path,
    cache_path: str | Path = "cache/transcript.json",
    model_name: str = "large-v3",
    language: str = "ru",
    device: Optional[str] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Returns word-level transcript from cache or computes via faster-whisper.
    """
    c_path = Path(cache_path)
    if not force and c_path.exists():
        try:
            return json.loads(c_path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"Кэш {c_path} повреждён ({e}), перезапускаю распознавание...")

    v_path = Path(voiceover_path)
    if not v_path.exists():
        raise FileNotFoundError(f"Файл озвучки не найден: {v_path}")

    from faster_whisper import WhisperModel

    if not device:
        dev, comp = detect_device()
    else:
        dev = device
        comp = "float16" if dev == "cuda" else "int8"

    print(f"Запуск faster-whisper (модель: {model_name}, устройство: {dev}, точность: {comp})...")
    model = WhisperModel(model_name, device=dev, compute_type=comp)

    segments, info = model.transcribe(str(v_path), language=language, word_timestamps=True)

    words = []
    text_segments = []
    for s in segments:
        text_segments.append({"start": s.start, "end": s.end, "text": s.text})
        if s.words:
            for w in s.words:
                words.append({
                    "word": w.word,
                    "start": round(w.start, 3),
                    "end": round(w.end, 3),
                    "probability": round(w.probability, 3),
                })

    result = {
        "duration": info.duration if hasattr(info, "duration") else (words[-1]["end"] if words else 0.0),
        "language": language,
        "segments": text_segments,
        "words": words,
    }

    c_path.parent.mkdir(parents=True, exist_ok=True)
    c_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Расшифровка сохранена в кэш: {c_path}")
    return result


def align_phrases(
    items: List[RowItem],
    transcript_words: List[Dict[str, Any]],
    overrides: Optional[Dict[int, Any]] = None,
    fuzzy_threshold: float = 65.0,
) -> List[PhraseAnchor]:
    """
    Matches each cue-sheet item phrase to transcript words.
    Enforces strictly monotonic time anchors.
    """
    import rapidfuzz

    if overrides is None:
        overrides = {}

    # Prepare normalized words stream
    norm_words: List[Dict[str, Any]] = []
    for idx, w in enumerate(transcript_words):
        nw = normalize_text(w["word"])
        if nw:
            norm_words.append({
                "orig_idx": idx,
                "norm": nw,
                "start": float(w["start"]),
                "end": float(w["end"]),
            })

    anchors: List[PhraseAnchor] = []
    last_anchor_end = 0.0
    current_word_idx = 0

    for it in items:
        # Check override
        if it.n in overrides:
            ov = overrides[it.n]
            if isinstance(ov, (int, float)):
                st = float(ov)
                en = st + it.duration
            elif isinstance(ov, dict):
                st = float(ov.get("anchor_start", last_anchor_end))
                en = float(ov.get("anchor_end", st + it.duration))
            else:
                st = last_anchor_end
                en = st + it.duration

            anchors.append(PhraseAnchor(
                n=it.n,
                anchor_start=st,
                anchor_end=en,
                confidence=1.0,
                method="override",
            ))
            last_anchor_end = max(last_anchor_end, en)
            # Advance word pointer to match monotonic anchor
            while current_word_idx < len(norm_words) and norm_words[current_word_idx]["start"] < st:
                current_word_idx += 1
            continue

        phrase_tokens = tokenize_text(it.phrase)
        if not phrase_tokens or not norm_words:
            # Cannot match empty phrase
            st = last_anchor_end
            en = st + it.duration
            anchors.append(PhraseAnchor(
                n=it.n,
                anchor_start=round(st, 3),
                anchor_end=round(en, 3),
                confidence=0.0,
                method="failed",
            ))
            last_anchor_end = en
            continue

        p_len = len(phrase_tokens)
        matched = False

        # 1. Exact match search starting from current_word_idx
        for i in range(current_word_idx, len(norm_words) - p_len + 1):
            window = [norm_words[i + k]["norm"] for k in range(p_len)]
            if window == phrase_tokens:
                st = norm_words[i]["start"]
                en = norm_words[i + p_len - 1]["end"]
                # Must be monotonic
                if st >= last_anchor_end - 0.2:  # allow slight sub-word tolerance
                    st = max(last_anchor_end, st)
                    anchors.append(PhraseAnchor(
                        n=it.n,
                        anchor_start=round(st, 3),
                        anchor_end=round(en, 3),
                        confidence=1.0,
                        method="exact",
                    ))
                    last_anchor_end = max(last_anchor_end, en)
                    current_word_idx = i + p_len
                    matched = True
                    break

        if matched:
            continue

        # 2. Fuzzy match search using sliding window
        target_str = " ".join(phrase_tokens)
        best_score = 0.0
        best_indices = None

        min_win = max(1, p_len - 2)
        max_win = p_len + 3

        for i in range(current_word_idx, len(norm_words)):
            w_start_time = norm_words[i]["start"]
            if w_start_time < last_anchor_end - 0.2:
                continue

            for w_size in range(min_win, max_win + 1):
                if i + w_size > len(norm_words):
                    break
                candidate_str = " ".join(norm_words[i + k]["norm"] for k in range(w_size))
                score = rapidfuzz.fuzz.token_sort_ratio(target_str, candidate_str)
                if score > best_score:
                    best_score = score
                    best_indices = (i, i + w_size - 1)

        if best_score >= fuzzy_threshold and best_indices is not None:
            s_idx, e_idx = best_indices
            st = max(last_anchor_end, norm_words[s_idx]["start"])
            en = norm_words[e_idx]["end"]
            anchors.append(PhraseAnchor(
                n=it.n,
                anchor_start=round(st, 3),
                anchor_end=round(en, 3),
                confidence=round(best_score / 100.0, 3),
                method="fuzzy",
            ))
            last_anchor_end = max(last_anchor_end, en)
            current_word_idx = e_idx + 1
        else:
            # Match failed -> set anchor at last_anchor_end with 0 confidence
            st = last_anchor_end
            en = st + it.duration
            anchors.append(PhraseAnchor(
                n=it.n,
                anchor_start=round(st, 3),
                anchor_end=round(en, 3),
                confidence=round(best_score / 100.0, 3) if best_score > 0 else 0.0,
                method="failed",
            ))
            last_anchor_end = en

    return anchors


def load_overrides(path: str | Path) -> Dict[int, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return {int(k): v for k, v in raw.items()}
    except Exception as e:
        print(f"Предупреждение: ошибка чтения {p}: {e}", file=sys.stderr)
        return {}


def run_align(
    table_path: str | Path,
    voiceover_path: Optional[str | Path] = None,
    transcript_path: Optional[str | Path] = None,
    overrides_path: Optional[str | Path] = None,
    out_dir: Optional[str | Path] = None,
    force: bool = False,
    fuzzy_threshold: Optional[float] = None,
    model_name: Optional[str] = None,
    device: Optional[str] = None,
) -> Path:
    p_tab = Path(table_path)
    items, settings, _ = load_table(p_tab)

    out = Path(out_dir) if out_dir else p_tab.parent
    out.mkdir(parents=True, exist_ok=True)
    cache_dir = out / "cache"

    # Audio path
    vo = voiceover_path or settings.voiceover_path
    if not Path(vo).is_absolute() and not Path(vo).exists():
        cand = p_tab.parent / vo
        if cand.exists():
            vo = cand

    if transcript_path and Path(transcript_path).exists():
        transcript_data = json.loads(Path(transcript_path).read_text(encoding="utf-8"))
    else:
        cache_file = cache_dir / "transcript.json"
        transcript_data = get_transcript(
            voiceover_path=vo,
            cache_path=cache_file,
            model_name=model_name or settings.whisper_model,
            language=settings.language,
            device=device,
            force=force,
        )

    # Overrides
    ov_file = overrides_path or (p_tab.parent / "anchors_override.json")
    overrides = load_overrides(ov_file)

    thresh = fuzzy_threshold if fuzzy_threshold is not None else settings.fuzzy_threshold
    anchors = align_phrases(items, transcript_data.get("words", []), overrides, thresh)

    phrases_file = out / "phrases.json"
    data = [
        {
            "n": a.n,
            "anchor_start": a.anchor_start,
            "anchor_end": a.anchor_end,
            "confidence": a.confidence,
            "method": a.method,
        }
        for a in anchors
    ]
    phrases_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    exact_c = sum(1 for a in anchors if a.method == "exact")
    fuzzy_c = sum(1 for a in anchors if a.method == "fuzzy")
    fail_c = sum(1 for a in anchors if a.method == "failed")
    over_c = sum(1 for a in anchors if a.method == "override")

    print(f"\nВыравнивание завершено: {len(anchors)} позиций")
    print(f"  Точных совпадений:   {exact_c}")
    print(f"  Нечётких (fuzzy):    {fuzzy_c}")
    print(f"  Переопределений:     {over_c}")
    print(f"  Требуют проверки:    {fail_c}")
    print(f"Результат сохранён: {phrases_file.resolve()}")
    return phrases_file


def main():
    parser = argparse.ArgumentParser(description="Align cue-sheet phrases with voiceover audio.")
    parser.add_argument("table", help="Path to cue sheet (xlsx)")
    parser.add_argument("--voiceover", help="Path to voiceover audio (wav/mp3)")
    parser.add_argument("--transcript", help="Path to existing transcript.json")
    parser.add_argument("--override", help="Path to anchors_override.json")
    parser.add_argument("-o", "--out", help="Output directory for phrases.json")
    parser.add_argument("--force", action="store_true", help="Force recalculate transcription and alignment")
    parser.add_argument("--device", choices=["cuda", "cpu"], help="Compute device for Whisper")
    parser.add_argument("--model", help="Whisper model name (default: large-v3)")
    parser.add_argument("--threshold", type=float, default=65.0, help="Fuzzy match threshold (default: 65.0)")
    args = parser.parse_args()

    run_align(
        table_path=args.table,
        voiceover_path=args.voiceover,
        transcript_path=args.transcript,
        overrides_path=args.override,
        out_dir=args.out,
        force=args.force,
        fuzzy_threshold=args.threshold,
        model_name=args.model,
        device=args.device,
    )


if __name__ == "__main__":
    main()
