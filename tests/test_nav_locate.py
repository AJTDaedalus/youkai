"""Tests for locate_bottom_nav_button — offline, no live game needed."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
from PIL import Image

from youkai_ocr.capture import calibrate
from youkai_ocr.cli import (
    ScreenAssertError,
    _NAV_AGENTS_CENTER,
    _NAV_STORAGE_CENTER,
    locate_bottom_nav_button,
)

_DIAG_NAV = Path(__file__).parent.parent / "archive" / "diag_nav"
_FRAME_A = _DIAG_NAV / "live_20260615_202624" / "nav_pre_storage.png"
_FRAME_B = _DIAG_NAV / "live_20260615_203054" / "nav_pre_storage.png"

_TOLERANCE_PX = 15   # ref-coord tolerance for OCR-located vs true center


def _load(path: Path):
    frame = Image.open(path)
    calib = calibrate(frame)
    return frame, calib


# ── Locator accuracy on real main-menu frames ──────────────────────────────────

@pytest.mark.parametrize("path", [_FRAME_A, _FRAME_B])
def test_locate_storage_near_true_center(path):
    frame, calib = _load(path)
    result = locate_bottom_nav_button(frame, calib, "storage")
    assert result is not None, "Storage label not found in nav strip"
    assert abs(result[0] - _NAV_STORAGE_CENTER[0]) <= _TOLERANCE_PX


@pytest.mark.parametrize("path", [_FRAME_A, _FRAME_B])
def test_locate_agents_tracks_real_position(path):
    frame, calib = _load(path)
    result = locate_bottom_nav_button(frame, calib, "agents")
    assert result is not None, "Agents label not found in nav strip"
    # Hard-coded _NAV_AGENTS_CENTER is 33px stale; OCR result should be
    # clearly different from it (further right), proving OCR tracks the real position.
    assert result[0] > _NAV_AGENTS_CENTER[0] + 10, (
        f"OCR x={result[0]} should be right of stale constant {_NAV_AGENTS_CENTER[0]}"
    )


# ── Non-main-menu frame returns None ──────────────────────────────────────────

def test_locate_returns_none_on_blank_frame():
    blank = Image.fromarray(np.zeros((1080, 1920, 3), dtype=np.uint8))
    calib = calibrate(blank)
    assert locate_bottom_nav_button(blank, calib, "storage") is None
    assert locate_bottom_nav_button(blank, calib, "agents") is None


# ── Retry loop re-clicks when first click is dropped ─────────────────────────

def test_navigate_to_storage_retries_on_dropped_click():
    """navigate_to_storage re-clicks when the screen doesn't transition."""
    from youkai_ocr.cli import _NavDriver, _is_storage_screen

    frame, calib = _load(_FRAME_A)
    # Frames: first N frames look like main-menu (not storage), last frame is storage.
    storage_frame = Image.fromarray(np.zeros((1080, 1920, 3), dtype=np.uint8))

    call_count = [0]
    frames_before_confirm = 12   # force at least one re-click (re-click at poll=10)

    def capture_fn():
        call_count[0] += 1
        if call_count[0] <= frames_before_confirm:
            return frame     # still main menu
        return storage_frame  # triggers _is_storage_screen via storage-tab check

    driver = _NavDriver(calib, capture_fn)
    driver._focus = lambda: None   # no-op
    driver._click = MagicMock()    # record clicks without mouse

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
