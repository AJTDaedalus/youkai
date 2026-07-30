"""Tests for locate_bottom_nav_button — offline, no live game needed."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
from PIL import Image

from youkai_ocr.capture import calibrate
from youkai_ocr.cli import (
    _NAV_AGENTS_CENTER,
    _NAV_STORAGE_CENTER,
    locate_bottom_nav_button,
)

_DIAG_NAV = Path(__file__).parent.parent / "archive" / "diag_nav"
_FRAME_A = _DIAG_NAV / "live_20260615_202624" / "nav_pre_storage.png"
_FRAME_B = _DIAG_NAV / "live_20260615_203054" / "nav_pre_storage.png"

# ZZZ 3.1 hub, committed so the current geometry is covered in CI (archive/ is not).
_REF_31 = Path(__file__).parent.parent / "reference" / "reference_20_main_menu_3_1.png"

needs_archive = pytest.mark.skipif(
    not _FRAME_A.exists(),
    reason="live archive fixtures not present (archive/ is local-only)",
)

_TOLERANCE_PX = 15  # ref-coord tolerance for OCR-located vs true center

# True label centres measured per fixture.  They differ by 56px between the two game
# versions because the bottom-nav row re-centres when a patch adds an entry — which is
# precisely why these tests must NOT be written against _NAV_*_CENTER.
_TRUE_CENTERS = {
    _FRAME_A: {"storage": 1179, "agents": 1307},  # ZZZ 1.5
    _FRAME_B: {"storage": 1179, "agents": 1307},  # ZZZ 1.5
}


def _load(path: Path):
    frame = Image.open(path)
    calib = calibrate(frame)
    return frame, calib


# ── Locator accuracy on real main-menu frames ──────────────────────────────────


@needs_archive
@pytest.mark.parametrize("path", [_FRAME_A, _FRAME_B])
@pytest.mark.parametrize("label", ["storage", "agents"])
def test_locate_near_true_center(path, label):
    frame, calib = _load(path)
    result = locate_bottom_nav_button(frame, calib, label)
    assert result is not None, f"{label} label not found in nav strip"
    assert abs(result[0] - _TRUE_CENTERS[path][label]) <= _TOLERANCE_PX


@needs_archive
@pytest.mark.parametrize("path", [_FRAME_A, _FRAME_B])
@pytest.mark.parametrize(
    ("label", "constant"),
    [("storage", _NAV_STORAGE_CENTER), ("agents", _NAV_AGENTS_CENTER)],
)
def test_locate_tracks_frame_not_constant(path, constant, label):
    """OCR must follow the frame even when the hard-coded fallback has gone stale.

    These fixtures are ZZZ 1.5; the constants are ZZZ 3.1.  A locator that agreed with
    the constant here would be reading the constant, not the screen.
    """
    frame, calib = _load(path)
    result = locate_bottom_nav_button(frame, calib, label)
    assert result is not None
    assert abs(result[0] - constant[0]) > _TOLERANCE_PX, (
        f"OCR x={result[0]} should differ from the 3.1 constant {constant[0]} on a 1.5-era frame"
    )


@pytest.mark.skipif(not _REF_31.exists(), reason="3.1 hub reference frame not present")
@pytest.mark.parametrize(
    ("label", "constant"),
    [("storage", _NAV_STORAGE_CENTER), ("agents", _NAV_AGENTS_CENTER)],
)
def test_fallback_constants_match_current_hub(label, constant):
    """The fallback centres must agree with the newest hub frame we have.

    When this fails, ZZZ has re-centred the bottom nav again: re-measure from a fresh
    main-menu capture, add it as reference_NN, and update _NAV_*_CENTER.
    """
    frame, calib = _load(_REF_31)
    result = locate_bottom_nav_button(frame, calib, label)
    assert result is not None, f"{label} label not found in the 3.1 hub frame"
    assert abs(result[0] - constant[0]) <= _TOLERANCE_PX, (
        f"_NAV_{label.upper()}_CENTER x={constant[0]} is stale; live frame has {result[0]}"
    )


# ── Non-main-menu frame returns None ──────────────────────────────────────────


def test_locate_returns_none_on_blank_frame():
    blank = Image.fromarray(np.zeros((1080, 1920, 3), dtype=np.uint8))
    calib = calibrate(blank)
    assert locate_bottom_nav_button(blank, calib, "storage") is None
    assert locate_bottom_nav_button(blank, calib, "agents") is None


# ── Retry loop re-clicks when first click is dropped ─────────────────────────


@needs_archive
def test_navigate_to_storage_retries_on_dropped_click():
    """navigate_to_storage re-clicks when the screen doesn't transition."""
    from youkai_ocr.cli import _NavDriver

    frame, calib = _load(_FRAME_A)
    # Frames: first N frames look like main-menu (not storage), last frame is storage.
    storage_frame = Image.fromarray(np.zeros((1080, 1920, 3), dtype=np.uint8))

    call_count = [0]
    frames_before_confirm = 12  # force at least one re-click (re-click at poll=10)

    def capture_fn():
        call_count[0] += 1
        if call_count[0] <= frames_before_confirm:
            return frame  # still main menu
        return storage_frame  # triggers _is_storage_screen via storage-tab check

    driver = _NavDriver(calib, capture_fn)
    driver._focus = lambda: None  # no-op
    driver._click = MagicMock()  # record clicks without mouse

    # Patch _is_storage_screen to return True only once storage_frame is returned
    import youkai_ocr.cli as cli_mod

    original = cli_mod._is_storage_screen

    def patched_is_storage(f, c):
        return f is storage_frame

    cli_mod._is_storage_screen = patched_is_storage
    try:
        driver.navigate_to_storage()
    finally:
        cli_mod._is_storage_screen = original

    # Should have clicked more than once (initial + at least one retry)
    assert driver._click.call_count >= 2, (
        f"Expected ≥2 clicks (initial + retry); got {driver._click.call_count}"
    )


# ── Retry loop does NOT blind-click once we have left the hub ────────────────


def test_retry_nav_click_skipped_off_the_hub():
    """A frame that is not the main-menu hub must not be clicked at the stale constant.

    Regression for the 2026-07-29 run: the Agents click had worked, the screen check was
    what failed, and the retries then fired the stale (1274,1041) constant into the open
    agent screen.
    """
    from youkai_ocr.cli import _NavDriver

    off_hub = Image.fromarray(np.zeros((1080, 1920, 3), dtype=np.uint8))
    calib = calibrate(off_hub)

    driver = _NavDriver(calib, lambda: off_hub)
    driver._focus = lambda: None
    driver._click = MagicMock()

    driver._retry_nav_click(off_hub, "Agents", _NAV_AGENTS_CENTER)
    assert driver._click.call_count == 0


@pytest.mark.skipif(not _REF_31.exists(), reason="3.1 hub reference frame not present")
def test_retry_nav_click_fires_on_the_hub():
    from youkai_ocr.cli import _NavDriver

    frame, calib = _load(_REF_31)
    driver = _NavDriver(calib, lambda: frame)
    driver._focus = lambda: None
    driver._click = MagicMock()

    driver._retry_nav_click(frame, "Agents", _NAV_AGENTS_CENTER)
    assert driver._click.call_count == 1
    # Located from the frame, not read off the constant.
    assert abs(driver._click.call_args[0][0] - _NAV_AGENTS_CENTER[0]) <= _TOLERANCE_PX
