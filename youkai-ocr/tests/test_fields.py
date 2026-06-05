"""Tests for B1: declarative field-crop config."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from youkai_ocr.capture import calibrate
from youkai_ocr.fields import FieldSpec, PanelSpec, crop_fields, load_panel

NAV_PATH = Path(__file__).parent.parent / "data" / "zzz_1.4" / "navigation.yaml"

# Fields we expect the disc detail panel to expose (flat names after flattening).
DISC_REQUIRED_FIELDS = {
    "set_name_with_slot",
    "slot_badge",
    "equipped_portrait",
    "rarity_badge",
    "level",
    "main_stat_name",
    "main_stat_value",
    "substat_1_name",
    "substat_1_value",
    "substat_2_name",
    "substat_2_value",
    "substat_3_name",
    "substat_3_value",
    "substat_4_name",
    "substat_4_value",
    "lock_icon",
}


# ── load_panel ────────────────────────────────────────────────────────────────


def test_load_disc_panel_returns_required_fields():
    panel = load_panel(NAV_PATH, "disc_inventory", "detail_panel")
    missing = DISC_REQUIRED_FIELDS - panel.fields.keys()
    assert not missing, f"Missing fields: {missing}"


def test_load_engine_panel_returns_fields():
    panel = load_panel(NAV_PATH, "engine_inventory", "detail_panel")
    assert "engine_name" in panel.fields
    assert "level" in panel.fields
    assert "lock_icon" in panel.fields


def test_load_agent_base_stats_panel():
    panel = load_panel(NAV_PATH, "agent_roster", "base_stats_tab")
    assert "agent_name" in panel.fields
    assert "level" in panel.fields
    # Nested stats group should be flattened.
    assert "stats_hp" in panel.fields
    assert "stats_atk" in panel.fields


def test_load_agent_skills_panel():
    panel = load_panel(NAV_PATH, "agent_roster", "skills_tab")
    assert "mindscape_cinema" in panel.fields
    # Skill icons have both icon bbox and level bbox → two entries each.
    assert "skill_icons_basic_attack" in panel.fields
    assert "skill_icons_basic_attack_level" in panel.fields
    # Core nodes flattened from nested dict.
    assert "core_nodes_A" in panel.fields
    assert "core_nodes_F" in panel.fields


def test_load_panel_missing_key_raises():
    with pytest.raises(KeyError):
        load_panel(NAV_PATH, "nonexistent_panel")


def test_field_specs_have_valid_bboxes():
    panel = load_panel(NAV_PATH, "disc_inventory", "detail_panel")
    for name, spec in panel.fields.items():
        x1, y1, x2, y2 = spec.bbox
        assert x2 > x1, f"{name}: x2 ({x2}) must be > x1 ({x1})"
        assert y2 > y1, f"{name}: y2 ({y2}) must be > y1 ({y1})"
        assert 0 <= x1 < 1920, f"{name}: x1 out of reference range"
        assert 0 <= y1 < 1080, f"{name}: y1 out of reference range"


# ── crop_fields — identity (1920×1080) ───────────────────────────────────────


def test_crop_identity_extracts_correct_pixels():
    """At 1920×1080 the crop should hit the exact reference bbox pixels."""
    panel = load_panel(NAV_PATH, "disc_inventory", "detail_panel")
    spec = panel.fields["level"]
    x1, y1, x2, y2 = spec.bbox

    # Fill the frame black, paint the level region red.
    pixels = np.zeros((1080, 1920, 3), dtype=np.uint8)
    pixels[y1:y2, x1:x2] = [255, 0, 0]
    frame = Image.fromarray(pixels, "RGB")

    calib = calibrate(frame)
    crops = crop_fields(frame, calib, panel)

    crop_arr = np.array(crops["level"])
    assert crop_arr.shape == (y2 - y1, x2 - x1, 3), "Crop dimensions wrong at identity"
    assert (crop_arr == [255, 0, 0]).all(), "Crop did not extract the painted region"


def test_crop_identity_non_target_field_is_black():
    """Fields outside the painted region should be all black (not bleed)."""
    panel = load_panel(NAV_PATH, "disc_inventory", "detail_panel")
    spec = panel.fields["level"]
    x1, y1, x2, y2 = spec.bbox

    pixels = np.zeros((1080, 1920, 3), dtype=np.uint8)
    pixels[y1:y2, x1:x2] = [255, 0, 0]
    frame = Image.fromarray(pixels, "RGB")

    calib = calibrate(frame)
    crops = crop_fields(frame, calib, panel)

    lock_arr = np.array(crops["lock_icon"])
    assert (lock_arr == 0).all(), "Unpainted field should be black"


# ── crop_fields — scaled (1600×900) ──────────────────────────────────────────


def _expected_scaled_bbox(
    ref_bbox: tuple[int, int, int, int], w: int, h: int
) -> tuple[int, int, int, int]:
    sx, sy = w / 1920, h / 1080
    x1, y1, x2, y2 = ref_bbox
    return round(x1 * sx), round(y1 * sy), round(x2 * sx), round(y2 * sy)


def test_crop_scaled_extracts_correct_pixels():
    """At 1600×900 bboxes must be scaled before cropping."""
    W, H = 1600, 900
    panel = load_panel(NAV_PATH, "disc_inventory", "detail_panel")
    spec = panel.fields["main_stat_name"]
    ex1, ey1, ex2, ey2 = _expected_scaled_bbox(spec.bbox, W, H)

    pixels = np.zeros((H, W, 3), dtype=np.uint8)
    pixels[ey1:ey2, ex1:ex2] = [0, 200, 100]
    frame = Image.fromarray(pixels, "RGB")

    calib = calibrate(frame)
    crops = crop_fields(frame, calib, panel)

    crop_arr = np.array(crops["main_stat_name"])
    assert crop_arr.shape == (ey2 - ey1, ex2 - ex1, 3)
    assert (crop_arr == [0, 200, 100]).all(), "Scaled crop extracted wrong region"


def test_crop_scaled_dimensions_match_expected():
    """Every crop's pixel dimensions match the scaled bbox at 1600×900."""
    W, H = 1600, 900
    panel = load_panel(NAV_PATH, "disc_inventory", "detail_panel")
    frame = Image.new("RGB", (W, H), (50, 50, 50))
    calib = calibrate(frame)
    crops = crop_fields(frame, calib, panel)

    for name, spec in panel.fields.items():
        ex1, ey1, ex2, ey2 = _expected_scaled_bbox(spec.bbox, W, H)
        crop = crops[name]
        w, h = crop.size
        assert w == ex2 - ex1, f"{name}: crop width {w} != expected {ex2 - ex1}"
        assert h == ey2 - ey1, f"{name}: crop height {h} != expected {ey2 - ey1}"


# ── crop_fields — general contracts ──────────────────────────────────────────


def test_all_crops_non_empty():
    """Every field in the disc panel must produce a non-empty crop."""
    panel = load_panel(NAV_PATH, "disc_inventory", "detail_panel")
    frame = Image.new("RGB", (1920, 1080), (30, 30, 30))
    calib = calibrate(frame)
    crops = crop_fields(frame, calib, panel)

    assert set(crops.keys()) == set(panel.fields.keys()), "crop_fields dropped or added keys"
    for name, crop in crops.items():
        w, h = crop.size
        assert w > 0 and h > 0, f"Field {name!r} returned empty crop ({w}×{h})"


def test_crop_fields_accepts_numpy_frame():
    """crop_fields should work whether frame is PIL or numpy (via calibrate)."""
    panel = load_panel(NAV_PATH, "disc_inventory", "detail_panel")
    arr = np.full((1080, 1920, 3), 77, dtype=np.uint8)
    frame_pil = Image.fromarray(arr, "RGB")
    calib = calibrate(frame_pil)
    crops = crop_fields(frame_pil, calib, panel)
    assert "level" in crops


def test_panel_spec_is_flat():
    """PanelSpec.fields must not contain nested dicts — all values are FieldSpec."""
    panel = load_panel(NAV_PATH, "disc_inventory", "detail_panel")
    for name, spec in panel.fields.items():
        assert isinstance(spec, FieldSpec), f"{name}: expected FieldSpec, got {type(spec)}"
