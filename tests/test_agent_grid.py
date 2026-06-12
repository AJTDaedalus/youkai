"""H1 fixture tests: detect_owned_agent_cells() against ref_12/13/14.

Reference screenshots are 1922×1112 (raw, includes window chrome).
Game area is obtained by cropping (left=1, top=32) → 1920×1080.
Identity calibration (scale=1.0) is used so ref coords == frame coords.

Ownership expectations:
  ref_12 — all 8 visible cells owned (8/8 YES)
  ref_13 — scrolled down, different agents, all 8 owned (8/8 YES)
  ref_14 — locked agents at top rows (rows 0-1), owned at bottom rows (rows 2-3) → 4 owned
"""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from youkai_ocr.agent_scanner import (
    _AGENT_GRID_LEFT_COL,
    _AGENT_GRID_RIGHT_COL,
    _AGENT_GRID_ROW_CENTERS,
    _AGENT_SAT_P75_THRESH,
    detect_owned_agent_cells,
)
from youkai_ocr.capture import CalibrationResult

# ── Paths ────────────────────────────────────────────────────────────────────

_SCREENSHOTS = Path(__file__).parent.parent / "screenshots"
_REF12 = _SCREENSHOTS / "reference_12_agent_menu.png"
_REF13 = _SCREENSHOTS / "reference_13_agent_menu_scrolled_down.png"
_REF14 = _SCREENSHOTS / "reference_14_agent_menu_scrolled_up.png"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _identity_calib() -> CalibrationResult:
    return CalibrationResult(scale_x=1.0, scale_y=1.0, frame_width=1920, frame_height=1080)


def _load_game_frame(path: Path) -> Image.Image:
    """Load a raw screenshot (1922×1112) and crop to game area (1920×1080)."""
    raw = Image.open(path)
    assert raw.size == (1922, 1112), f"Unexpected raw size {raw.size} for {path.name}"
    return raw.crop((1, 32, 1921, 1112))


# ── Column/row structure sanity ───────────────────────────────────────────────

def test_grid_constants_structure():
    assert len(_AGENT_GRID_ROW_CENTERS) == 4
    for cy in _AGENT_GRID_ROW_CENTERS:
        assert 0 < cy < 1080
    assert _AGENT_GRID_LEFT_COL[1] == _AGENT_GRID_RIGHT_COL[0], (
        "Left col x1 must equal right col x0 (contiguous)"
    )
    assert _AGENT_SAT_P75_THRESH > 0


# ── ref_12: all 8 cells owned ────────────────────────────────────────────────

@pytest.mark.skipif(not _REF12.exists(), reason="reference_12 not present")
def test_ref12_all_owned():
    frame = _load_game_frame(_REF12)
    calib = _identity_calib()
    cells = detect_owned_agent_cells(frame, calib)
    assert len(cells) == 8, f"Expected 8 owned cells, got {len(cells)}: {cells}"


@pytest.mark.skipif(not _REF12.exists(), reason="reference_12 not present")
def test_ref12_cell_centers_in_range():
    frame = _load_game_frame(_REF12)
    calib = _identity_calib()
    cells = detect_owned_agent_cells(frame, calib)
    col_cx_l = (_AGENT_GRID_LEFT_COL[0] + _AGENT_GRID_LEFT_COL[1]) // 2
    col_cx_r = (_AGENT_GRID_RIGHT_COL[0] + _AGENT_GRID_RIGHT_COL[1]) // 2
    for cx, cy in cells:
        assert cx in (col_cx_l, col_cx_r), f"Unexpected cx={cx}"
        assert cy in _AGENT_GRID_ROW_CENTERS, f"Unexpected cy={cy}"


# ── ref_13: scrolled down, all 8 cells owned ─────────────────────────────────

@pytest.mark.skipif(not _REF13.exists(), reason="reference_13 not present")
def test_ref13_all_owned():
    frame = _load_game_frame(_REF13)
    calib = _identity_calib()
    cells = detect_owned_agent_cells(frame, calib)
    assert len(cells) == 8, f"Expected 8 owned cells, got {len(cells)}: {cells}"


# ── ref_14: locked top rows (0-1), owned bottom rows (2-3) ───────────────────

@pytest.mark.skipif(not _REF14.exists(), reason="reference_14 not present")
def test_ref14_only_owned_bottom():
    frame = _load_game_frame(_REF14)
    calib = _identity_calib()
    cells = detect_owned_agent_cells(frame, calib)
    assert len(cells) == 4, f"Expected 4 owned cells (bottom 2 rows), got {len(cells)}: {cells}"


@pytest.mark.skipif(not _REF14.exists(), reason="reference_14 not present")
def test_ref14_owned_in_correct_rows():
    frame = _load_game_frame(_REF14)
    calib = _identity_calib()
    cells = detect_owned_agent_cells(frame, calib)
    owned_cys = {cy for _, cy in cells}
    locked_rows = set(_AGENT_GRID_ROW_CENTERS[:2])
    owned_rows  = set(_AGENT_GRID_ROW_CENTERS[2:])
    assert owned_cys == owned_rows, (
        f"Expected owned rows {owned_rows}, got {owned_cys}. "
        f"Locked rows {locked_rows} must be skipped."
    )
