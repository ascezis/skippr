import pytest
from skippr_core.align import align_phrases
from skippr_core.models import RowItem


def test_align_monotonic_and_match_types():
    # Synthetic words sequence from speech
    # "Привет всем это история о том как создавался Linux и открытый код"
    words = [
        {"word": "Привет", "start": 0.0, "end": 0.5},
        {"word": "всем", "start": 0.5, "end": 0.9},
        {"word": "это", "start": 1.0, "end": 1.2},
        {"word": "история", "start": 1.2, "end": 1.8},
        {"word": "о", "start": 1.8, "end": 1.9},
        {"word": "том", "start": 1.9, "end": 2.2},
        {"word": "как", "start": 2.2, "end": 2.4},
        {"word": "создавался", "start": 2.4, "end": 3.1},
        {"word": "Линукс", "start": 3.1, "end": 3.7},  # "Линукс" vs "Linux" -> fuzzy
        {"word": "и", "start": 3.7, "end": 3.8},
        {"word": "открытый", "start": 3.8, "end": 4.5},
        {"word": "код", "start": 4.5, "end": 5.0},
    ]

    items = [
        RowItem(n=1, block="Intro", phrase="это история о том", kind="клип", duration=2.0),
        RowItem(n=2, block="Intro", phrase="как создавался Linux", kind="клип", duration=2.0),
        RowItem(n=3, block="Intro", phrase="открытый код", kind="клип", duration=2.0),
    ]

    anchors = align_phrases(items, words, fuzzy_threshold=60.0)

    assert len(anchors) == 3
    # Item 1 is exact match
    assert anchors[0].n == 1
    assert anchors[0].method == "exact"
    assert anchors[0].anchor_start == pytest.approx(1.0, 0.05)
    assert anchors[0].anchor_end == pytest.approx(2.2, 0.05)

    # Item 2 has "Линукс" vs "Linux" -> fuzzy match
    assert anchors[1].n == 2
    assert anchors[1].method in ("fuzzy", "exact")

    # Item 3 is exact match
    assert anchors[2].n == 3
    assert anchors[2].method == "exact"
    assert anchors[2].anchor_start == pytest.approx(3.8, 0.05)

    # Monotonicity check
    assert anchors[0].anchor_start <= anchors[1].anchor_start <= anchors[2].anchor_start


def test_align_permuted_row_cannot_violate_monotonicity():
    # If a line in table refers to words that occurred BEFORE previous anchor,
    # it must NOT jump backwards in time.
    words = [
        {"word": "Альфа", "start": 1.0, "end": 2.0},
        {"word": "Бета", "start": 3.0, "end": 4.0},
        {"word": "Гамма", "start": 5.0, "end": 6.0},
    ]

    items = [
        RowItem(n=1, block="B", phrase="Бета", kind="клип", duration=1.0),
        RowItem(n=2, block="B", phrase="Альфа", kind="клип", duration=1.0),  # occurred earlier!
    ]

    anchors = align_phrases(items, words)

    assert anchors[0].n == 1
    assert anchors[0].method == "exact"
    assert anchors[0].anchor_start == pytest.approx(3.0, 0.05)

    # Item 2 cannot match at 1.0 because anchor 0 ended at 4.0
    assert anchors[1].n == 2
    assert anchors[1].method == "failed"
    assert anchors[1].anchor_start >= anchors[0].anchor_start


def test_align_overrides():
    words = [
        {"word": "Раз", "start": 1.0, "end": 2.0},
        {"word": "Два", "start": 2.0, "end": 3.0},
    ]
    items = [
        RowItem(n=1, block="B", phrase="Несуществующая фраза", kind="клип", duration=2.0),
    ]

    overrides = {1: 15.5}
    anchors = align_phrases(items, words, overrides=overrides)

    assert anchors[0].n == 1
    assert anchors[0].method == "override"
    assert anchors[0].anchor_start == pytest.approx(15.5, 0.01)
