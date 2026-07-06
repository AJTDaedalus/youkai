"""Acceptance tests for A4: calibration logic.

grab_window() is not tested here (requires a live Windows display).
Calibration is pure math — tested against the real reference screenshots.
"""

from pathlib import Path

import pytest
from PIL import Image

from youkai_ocr.capture import (
    REFERENCE_H,
    REFERENCE_W,
    calibrate,
)

REFERENCE_DIR = Path(__file__).parent.parent / "reference"

# navigation.yaml: raw screenshot is 1922×1112, offset (1, 32) → game area 1920×1080.
_RAW_OFFSET = (1, 32)


def _load_game_area() -> Image.Image:
    """Crop reference_1 to the 1920×1080 game client area."""
    raw = Image.open(REFERENCE_DIR / "reference_1_disc_menu.png").convert("RGB")
    x, y = _RAW_OFFSET
    return raw.crop((x, y, x + REFERENCE_W, y + REFERENCE_H))


# ── Core acceptance criteria ──────────────────────────────────────────────────


def test_calibrate_reference_is_identity():
    """Given the 1920×1080 reference screenshot, calibration must return identity."""
    cal = calibrate(_load_game_area())
    assert cal.frame_width == REFERENCE_W
    assert cal.frame_height == REFERENCE_H
    assert cal.scale_x == pytest.approx(1.0)
    assert cal.scale_y == pytest.approx(1.0)
    assert cal.is_identity


def test_calibrate_1600x900_correct_scale():
    """Given a 1600×900 frame, scale must equal 1600/1920."""
    frame = _load_game_area().resize((1600, 900), Image.LANCZOS)
    cal = calibrate(frame)
    assert cal.frame_width == 1600
    assert cal.frame_height == 900
    assert cal.scale_x == pytest.approx(1600 / REFERENCE_W)
    assert cal.scale_y == pytest.approx(900 / REFERENCE_H)
    assert not cal.is_identity


def test_calibrate_rejects_ultrawide():
    """2560×1080 (21:9) must raise ValueError mentioning aspect ratio."""
    ultrawide = Image.new("RGB", (2560, 1080))
    with pytest.raises(ValueError, match="aspect ratio"):
        calibrate(ultrawide)


def test_calibrate_rejects_portrait():
    """1080×1920 (portrait) must raise ValueError."""
    portrait = Image.new("RGB", (1080, 1920))
    with pytest.raises(ValueError, match="aspect ratio"):
        calibrate(portrait)


# ── CalibrationResult helpers ─────────────────────────────────────────────────


def test_scale_bbox_identity():
    """scale_bbox on identity calibration must return the input unchanged."""
    cal = calibrate(_load_game_area())
    bbox = (100, 200, 300, 400)
    assert cal.scale_bbox(bbox) == bbox


def test_scale_bbox_1600x900_edge():
    """Full-reference bbox corners must map to 1600×900 corners exactly."""
    frame = _load_game_area().resize((1600, 900), Image.LANCZOS)
    cal = calibrate(frame)
    x1, y1, x2, y2 = cal.scale_bbox((REFERENCE_W, REFERENCE_H, REFERENCE_W, REFERENCE_H))
    assert x1 == 1600
    assert y1 == 900


def test_to_frame_identity():
    """to_frame on identity must return the same coords."""
    cal = calibrate(_load_game_area())
    assert cal.to_frame(500, 300) == (500, 300)


def test_to_frame_1600x900():
    """to_frame(1920, 1080) on a 1600×900 cal must map to (1600, 900)."""
    frame = _load_game_area().resize((1600, 900), Image.LANCZOS)
    cal = calibrate(frame)
    assert cal.to_frame(REFERENCE_W, REFERENCE_H) == (1600, 900)
