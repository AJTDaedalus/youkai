"""G5 acceptance test — two-pass panel slot fallback (D-slot-panel-fallback).

The 12 archived panels in ``tests/fixtures/disc_slot_panels/`` are the genuine
structural ``no_slot`` critical-fails from the 2026-06-05 live scan: 8 Fanged
Metal (long name clips the title "[N]" past the title bbox) and 4 Dawn's Bloom
(long name wraps the title to two lines, dropping the "["). The slot is visible
and correct on every one; only the tier-1 title-text parse fails.

This test asserts the tier-3 fallback recovers all 12 (the offline acceptance
gate from TASKS_ocr.md G5).
"""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from youkai_ocr.disc_scanner import parse_slot_from_panel
from youkai_ocr.normalizer import parse_panel_slot, parse_slot
from youkai_ocr.recognize import make_recognizer

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "disc_slot_panels"

# (panel fixture, expected slot) — ground truth read from the bracketed digit
# visible in each panel title.
_PANELS: list[tuple[str, int]] = [
    ("disc_0558", 3),
    ("disc_0562", 4),
    ("disc_0563", 4),
    ("disc_0564", 5),
    ("disc_1068", 6),
    ("disc_1069", 6),
    ("disc_1071", 6),
    ("disc_1074", 6),
    ("disc_2176", 1),
    ("disc_2179", 4),
    ("disc_2180", 5),
    ("disc_2185", 6),
]


@pytest.fixture(scope="module")
def recognizer():
    try:
        return make_recognizer("tesseract")
    except RuntimeError:
        pytest.skip("tesseract not installed")


@pytest.mark.parametrize("name,expected", _PANELS)
def test_panel_slot_fallback_recovers_each(name: str, expected: int, recognizer):
    panel = Image.open(_FIXTURES / f"{name}.png")
    assert parse_slot_from_panel(panel, recognizer) == expected


def test_panel_slot_fallback_recovers_all_twelve(recognizer):
    """The full acceptance gate: 12/12 recovered, none missed."""
    recovered = sum(
        parse_slot_from_panel(Image.open(_FIXTURES / f"{name}.png"), recognizer) == exp
        for name, exp in _PANELS
    )
    assert recovered == 12, f"recovered {recovered}/12"


# ── parse_panel_slot unit cases (pure, no OCR) ────────────────────────────────

@pytest.mark.parametrize(
    "texts,expected",
    [
        (("[3]4", ""), 3),          # Fanged Metal: bracketed slot + trailing noise
        (("[6]4", ""), 6),
        (("", "[6]"), 6),           # Dawn's Bloom: clean bracket in pass B
        (("", "6]"), 6),            # partial bracket (no opening)
        (("", "16]"), 6),           # leading noise digit; "6]" still wins
        (("", "[6"), 6),            # partial bracket (no closing)
        (("", ""), None),           # nothing recoverable
        (("789", "0"), None),       # bare digits, no bracket → no slot
    ],
)
def test_parse_panel_slot(texts, expected):
    assert parse_panel_slot(*texts) == expected


def test_parse_panel_slot_prefers_bracketed_over_partial():
    # A fully-bracketed [4] in a later pass beats a partial "1]" in an earlier one.
    assert parse_panel_slot("1]", "[4]") == 4


def test_fallback_is_gated_to_title_miss():
    """Tier-1 parse_slot still handles clean titles; the fallback is only for misses."""
    assert parse_slot("Fanged Metal [3]") == 3
