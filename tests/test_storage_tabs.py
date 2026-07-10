"""H7b: active_storage_tab() fixture tests.

Verifies that the glow-stripe bboxes correctly identify the active category tab
from reference screenshots without touching the live game.

ref_1 = Drive Disc Storage (disc tab active → index 1)
ref_2 = W-Engine Storage   (engine tab active → index 0)
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from youkai_ocr.capture import CalibrationResult
from youkai_ocr.cli import STORAGE_TAB_ACTIVE_LUMA, active_storage_tab

REF = Path(__file__).resolve().parent.parent / "reference"

# 1920×1080 identity calibration (reference screenshot native resolution).
_CALIB = CalibrationResult(scale_x=1.0, scale_y=1.0, frame_width=1920, frame_height=1080)


def _load_ref(name: str) -> Image.Image:
    path = REF / name
    if not path.exists():
        pytest.skip(f"reference screenshot not found: {path}")
    # Raw PNG is 1922×1112; strip the 1-px left border and 32-px top chrome.
    return Image.open(path).crop((1, 32, 1921, 1112))


# ── Drive Disc Storage (ref_1) ────────────────────────────────────────────────


def test_disc_tab_active_on_ref1():
    """Drive Disc Storage → disc tab (index 1) must be active."""
    frame = _load_ref("reference_1_disc_menu.png")
    result = active_storage_tab(frame, _CALIB)
    assert result == 1, f"Expected disc tab (index 1) active on ref_1, got index {result}"


def test_disc_glow_luma_above_threshold_on_ref1():
    """Disc glow region must exceed the active threshold on ref_1."""
    import numpy as np

    frame = _load_ref("reference_1_disc_menu.png")
    arr = np.array(frame)
    # Disc glow bbox (index 1): (1413, 304, 1430, 325)
    region = arr[304:325, 1413:1430]
    luma = float(
        0.299 * region[..., 0].mean()
        + 0.587 * region[..., 1].mean()
        + 0.114 * region[..., 2].mean()
    )
    assert luma > STORAGE_TAB_ACTIVE_LUMA, (
        f"Disc glow luma {luma:.1f} ≤ threshold {STORAGE_TAB_ACTIVE_LUMA} on ref_1"
    )


# ── W-Engine Storage (ref_2) ──────────────────────────────────────────────────


def test_engine_tab_active_on_ref2():
    """W-Engine Storage → engine tab (index 0) must be active."""
    frame = _load_ref("reference_2_wengine_inventory.png")
    result = active_storage_tab(frame, _CALIB)
    assert result == 0, f"Expected engine tab (index 0) active on ref_2, got index {result}"


def test_engine_glow_luma_above_threshold_on_ref2():
    """Engine glow region must exceed the active threshold on ref_2."""
    import numpy as np

    frame = _load_ref("reference_2_wengine_inventory.png")
    arr = np.array(frame)
    # Engine glow bbox (index 0): (1413, 135, 1430, 203)
    region = arr[135:203, 1413:1430]
    luma = float(
        0.299 * region[..., 0].mean()
        + 0.587 * region[..., 1].mean()
        + 0.114 * region[..., 2].mean()
    )
    assert luma > STORAGE_TAB_ACTIVE_LUMA, (
        f"Engine glow luma {luma:.1f} ≤ threshold {STORAGE_TAB_ACTIVE_LUMA} on ref_2"
    )


# ── Cross-check: inactive tabs must be dark ───────────────────────────────────


def test_engine_glow_dark_on_ref1():
    """Engine glow bbox must be well below disc glow bbox on ref_1 (engine inactive)."""
    import numpy as np

    frame = _load_ref("reference_1_disc_menu.png")
    arr = np.array(frame)

    def mean_luma(y1, y2):
        r = arr[y1:y2, 1413:1430]
        return float(0.299 * r[..., 0].mean() + 0.587 * r[..., 1].mean() + 0.114 * r[..., 2].mean())

    disc_luma = mean_luma(304, 325)
    engine_luma = mean_luma(135, 203)
    assert disc_luma > engine_luma, (
        f"Disc luma ({disc_luma:.1f}) should exceed engine luma ({engine_luma:.1f}) on ref_1"
    )


def test_disc_glow_dark_on_ref2():
    """Disc glow bbox must be well below engine glow bbox on ref_2 (disc inactive)."""
    import numpy as np

    frame = _load_ref("reference_2_wengine_inventory.png")
    arr = np.array(frame)

    def mean_luma(y1, y2):
        r = arr[y1:y2, 1413:1430]
        return float(0.299 * r[..., 0].mean() + 0.587 * r[..., 1].mean() + 0.114 * r[..., 2].mean())

    disc_luma = mean_luma(304, 325)
    engine_luma = mean_luma(135, 203)
    assert engine_luma > disc_luma, (
        f"Engine luma ({engine_luma:.1f}) should exceed disc luma ({disc_luma:.1f}) on ref_2"
    )
