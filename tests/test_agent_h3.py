"""H3: Equipment-tab render-gates and slot geometry tests.

Offline tests only — uses reference screenshots, no game required.
Acceptance criteria (H3):
  - _equip_tab_rendered returns True on ref_7, False on skills frame.
  - _slot_panel_rendered returns True on ref_8 (disc selected), False on ref_7.
  - Slot centers land inside high-saturation disc regions in ref_7.
"""
import cv2
import numpy as np
import pytest
from pathlib import Path
from PIL import Image

from youkai_ocr.agent_scanner import (
    _equip_tab_rendered,
    _slot_panel_rendered,
    _disc_slot_equipped,
    _panel_shows_equipped,
    _slot_number,
    _DISC_SLOT_CENTERS,
    _ENGINE_SLOT_CENTER,
    _ALL_SLOT_CENTERS,
)
from youkai_ocr.capture import CalibrationResult

REF = Path(__file__).parent.parent / "reference"
ARCHIVE = Path(__file__).parent.parent / "archive" / "live_20260605"

# Calibration for 1920×1080 reference screenshots (scale=1, no offset).
_CALIB = CalibrationResult(scale_x=1.0, scale_y=1.0, frame_width=1920, frame_height=1080)


def _load_ref(name: str) -> Image.Image:
    path = REF / name
    if not path.exists():
        pytest.skip(f"fixture not found: {path}")
    # Reference screenshots are raw 1922×1112 with a 1-pixel left border and
    # 32-pixel top chrome.  Crop to the game area for ref-coord testing.
    raw = Image.open(path)
    return raw.crop((1, 32, 1921, 1112))   # → 1920×1080 game coords


# ── Gate 1: equip-tab render-gate ─────────────────────────────────────────────

def test_equip_tab_rendered_true_on_ref7():
    frame = _load_ref("reference_7_agent_equipment.png")
    assert _equip_tab_rendered(frame, _CALIB), (
        "Engine slot should be bright (luma≈210) on the Equipment tab"
    )


def test_equip_tab_rendered_false_on_skills():
    # Use the live archive skills frame if present; fall back to reference_4.
    skills_path = ARCHIVE / "agent_000" / "skills.png"
    if skills_path.exists():
        frame = Image.open(skills_path)
    else:
        frame = _load_ref("reference_4_agent_skills_page.png")
        frame = Image.open(REF / "reference_4_agent_skills_page.png").crop((1, 32, 1921, 1112))
    assert not _equip_tab_rendered(frame, _CALIB), (
        "Engine-slot area is dark background on skills tab (luma≈14)"
    )


# ── Gate 2: slot-panel render-gate ────────────────────────────────────────────

def test_slot_panel_rendered_true_on_ref8():
    frame = _load_ref("reference_8_agent_equipment_disc_select.png")
    assert _slot_panel_rendered(frame, _CALIB), (
        "Disc selection panel is open in ref_8: dark_frac≈0.16 > threshold 0.08"
    )


def test_slot_panel_rendered_false_on_ref7():
    frame = _load_ref("reference_7_agent_equipment.png")
    assert not _slot_panel_rendered(frame, _CALIB), (
        "No panel open in ref_7 (agent portrait is bright): dark_frac≈0.01 < threshold"
    )


# ── Slot geometry: centers land inside disc circles in ref_7 ──────────────────

def _ring_saturation(arr_hsv: np.ndarray, cx: int, cy: int, r0: int = 48, r1: int = 66) -> float:
    """Mean HSV-S in the annulus r0..r1 around (cx, cy) — the disc's rarity ring.

    The ring is colorful for EVERY disc rarity/set, so this is a set-independent test
    that the center sits on a real disc slot.  (Center saturation alone is unreliable:
    a disc's central icon can be dark/muted, e.g. the blue discs in ref_16 read only
    ~24 at center but ~97 on the ring.)
    """
    r1i = r1
    ys, xs = np.mgrid[cy - r1i:cy + r1i, cx - r1i:cx + r1i]
    dist = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2)
    mask = (dist >= r0) & (dist <= r1)
    sub = arr_hsv[cy - r1i:cy + r1i, cx - r1i:cx + r1i, 1]
    return float(sub[mask].mean())


# Disc-slot geometry is validated against reference_16 (the agent equipment tab,
# captured 2026-06-07 and confirmed by the user to be accurate to the live client).
# H12 finding: ref_7/15/16 AND the live archive all place the discs at the SAME
# compact positions (HoughCircles ring centers agree to ±2px).  The old "wide" coords
# were wrong — they passed the previous saturation test only by landing on the
# colorful background filmstrip art in ref_7.  See DECISIONS.md D30.
REF16 = "reference_16_agent_tab_equipment_repeat.png"


@pytest.fixture(scope="module")
def ref7_hsv():
    """HSV of reference_7 (used only for the engine-bright / panel-gate tests)."""
    if not (REF / "reference_7_agent_equipment.png").exists():
        pytest.skip("reference_7 not found")
    raw = Image.open(REF / "reference_7_agent_equipment.png")
    game = raw.crop((1, 32, 1921, 1112))
    arr = np.array(game.convert("RGB"))
    bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)


@pytest.fixture(scope="module")
def equip_tab_hsv():
    """HSV of reference_16 — the live-accurate agent equipment tab (compact hexagon)."""
    if not (REF / REF16).exists():
        pytest.skip(f"fixture not found: {REF / REF16}")
    raw = Image.open(REF / REF16)
    game = raw.crop((1, 32, 1921, 1112))
    arr = np.array(game.convert("RGB"))
    bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)


@pytest.mark.parametrize("slot_idx,cx,cy", [
    (i, cx, cy) for i, (cx, cy) in enumerate(_DISC_SLOT_CENTERS)
])
def test_disc_slot_center_on_ring(equip_tab_hsv, slot_idx, cx, cy):
    """Each disc slot center sits inside a disc's rarity ring in ref_16 (live-accurate).

    Ring-annulus saturation reads ≥55 on a real slot vs ≈20 off-disc, independent of
    which disc set is equipped.  Threshold 40 separates them with margin.
    """
    ring = _ring_saturation(equip_tab_hsv, cx, cy)
    assert ring > 40, (
        f"Slot {slot_idx+1} center game({cx},{cy}) has low ring saturation {ring:.1f} "
        f"— center may be off-disc; expected > 40"
    )


def test_engine_slot_center_is_bright(ref7_hsv):
    """Engine slot center should be low-saturation bright white (the W-Engine)."""
    cx, cy = _ENGINE_SLOT_CENTER
    arr_v = ref7_hsv[max(0, cy-20):cy+20, max(0, cx-20):cx+20, 2]
    mean_v = float(arr_v.mean())
    arr_s = ref7_hsv[max(0, cy-20):cy+20, max(0, cx-20):cx+20, 1]
    mean_s = float(arr_s.mean())
    assert mean_v > 150, f"Engine slot value {mean_v:.1f} < 150 — not bright white"
    assert mean_s < 50,  f"Engine slot saturation {mean_s:.1f} > 50 — too colorful for W-Engine"


# ── H18: empty-slot detection (calibrated from reference_17, Koleda fully unequipped) ──

KOLEDA = "reference_17_koleda_unequipped_equipment_page.png"


def test_disc_slots_equipped_on_ref7_empty_on_koleda():
    eq = _load_ref("reference_7_agent_equipment.png")
    empty = _load_ref(KOLEDA)
    for i in range(6):
        assert _disc_slot_equipped(eq, _CALIB, i), f"ref_7 disc slot {i} should read equipped"
        assert not _disc_slot_equipped(empty, _CALIB, i), f"Koleda disc slot {i} should read empty"


def test_panel_shows_equipped_action_bar_gate():
    # H21/D36: the per-slot equipped/empty signal is the SELECT-view action bar, not a pre-click
    # pixel heuristic (which could not separate equipped from empty engines — see the removed
    # _engine_slot_equipped, false-empty on ref_16 / the live dark engine).  Equipped → "Unequip…";
    # empty → "Equip…".  Calibrated against the real frames: ref_8 (equipped disc select), ref_18
    # (clicked empty disc → auto-loads inventory[0]), ref_19 (clicked empty engine).
    from youkai_ocr.recognize import make_recognizer
    rec = make_recognizer("tesseract")
    eq_disc    = _load_ref("reference_8_agent_equipment_disc_select.png")
    empty_disc = _load_ref("reference_18_unequipped_disc_slot_clicked.png")
    empty_eng  = _load_ref("reference_19_unequipped_engine_clicked.png")
    assert _panel_shows_equipped(eq_disc, _CALIB, rec),        "ref_8 equipped disc → 'Unequip All'"
    assert not _panel_shows_equipped(empty_disc, _CALIB, rec), "ref_18 empty disc → 'Equip All'"
    assert not _panel_shows_equipped(empty_eng, _CALIB, rec),  "ref_19 empty engine → 'Equip'"

    # H26 fix: equipped engine shows "Remove" (not "Unequip") — was falsely read as empty.
    eq_eng = ARCHIVE / "agent_010" / "equip_slot_6.png"
    if not eq_eng.exists():
        pytest.skip("archive agent_010/equip_slot_6.png missing")
    eq_eng_frame = Image.open(eq_eng).convert("RGB")
    assert _panel_shows_equipped(eq_eng_frame, _CALIB, rec), \
        "equipped engine slot → 'Remove' must read as equipped (H26)"


def test_equip_tab_still_renders_on_koleda_empty_engine():
    # Critical: the issue-4 reactive net keys on _equip_tab_rendered.  Koleda's empty engine
    # must still pass it (the green glow center is bright enough) so a REAL owned agent with no
    # engine is NOT mistaken for a trial/preview agent and skipped.
    assert _equip_tab_rendered(_load_ref(KOLEDA), _CALIB)


def test_equip_tab_renders_on_geared_agent_with_dark_engine():
    # H20/D35 regression: the live frame nav_equip_unavailable.png is a fully-geared owned agent
    # (6 discs equipped) whose W-Engine art is dark — engine-gate luma reads 78.3 < 80, so the old
    # engine-only gate FALSE-skipped it (agent dropped from export).  The disc path must rescue it.
    p = ARCHIVE / "nav_equip_unavailable.png"
    if not p.exists():
        pytest.skip("live false-skip frame missing")
    frame = Image.open(p).convert("RGB")   # native 1920×1080 capture (no ref chrome)
    assert all(_disc_slot_equipped(frame, _CALIB, i) for i in range(6)), \
        "all 6 discs are equipped in this frame"
    assert _equip_tab_rendered(frame, _CALIB), \
        "geared agent with a dark-art engine must read RENDERED (not equip_unavailable)"


def test_slot_number_mapping_matches_koleda_layout():
    # reference_17 shows the in-game numbers on the empty slots: _DISC_SLOT_CENTERS is ordered
    # upper-right(6), right-center(5), lower-right(4), lower-left(3), left-center(2), upper-left(1).
    assert [_slot_number(i) for i in range(6)] == [6, 5, 4, 3, 2, 1]
