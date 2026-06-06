"""Tests for B3 matchers."""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from youkai_ocr.matchers import detect_lock_from_text, detect_rarity


# ── detect_rarity ─────────────────────────────────────────────────────────────

def _solid(rgb: tuple[int, int, int], size: int = 10) -> Image.Image:
    return Image.fromarray(
        np.full((size, size, 3), rgb, dtype=np.uint8), "RGB"
    )


def test_rarity_s():
    img = _solid((245, 200, 33))
    assert detect_rarity(img) == 4


def test_rarity_a():
    img = _solid((160, 80, 220))
    assert detect_rarity(img) == 3


def test_rarity_b():
    img = _solid((80, 140, 200))
    assert detect_rarity(img) == 2


def test_rarity_noisy_s():
    # Slightly off from the S centroid — should still match.
    img = _solid((240, 195, 40))
    assert detect_rarity(img) == 4


def test_rarity_unrecognized():
    img = _solid((255, 0, 0))  # pure red — not any rarity
    with pytest.raises(ValueError, match="Rarity unrecognized"):
        detect_rarity(img)


# ── detect_lock_from_text ─────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("Lv. 15 L",   True),
    ("Lv. 4",      False),
    ("Lv. 12 L",   True),
    ("Lv 9 L",     True),
    ("Lv. 0",      False),
    ("",           False),
    ("15 L bonus", True),   # unusual but should trigger
])
def test_detect_lock(text, expected):
    assert detect_lock_from_text(text) is expected
