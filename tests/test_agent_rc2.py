"""RC-2: wipe-proof detail-page / active-tab predicate.

Offline tests — no game required.  Validates that `_on_detail_page` and
`_tab_active` key on the yellow active-tab pill (not raw luma), so the
"AGENT SELECT" transition wipe and the agent menu are rejected while real
Base/Skills/Equipment pages are accepted.

Positives use committed reference frames (reference/reference_{3,4,7}).
Negatives use committed fixtures copied from the live archive:
  - agent_nav/wipe.png — the "AGENT SELECT" transition wipe (was banked as a
    bogus base_stats.png; byte-identical to skills.png in agent_000).
  - agent_nav/menu.png — the agent menu (reference_12), no tab bar.
"""
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from youkai_ocr.agent_scanner import (
    _on_detail_page,
    _tab_active,
    _tab_content_rendered,
    _tab_yellow_frac,
    _TAB_BASE,
    _TAB_SKILLS_IDX,
    _TAB_EQUIP_IDX,
)
from youkai_ocr.capture import CalibrationResult

REF = Path(__file__).parent.parent / "reference"
FIX = Path(__file__).parent / "fixtures" / "agent_nav"
_CALIB = CalibrationResult(scale_x=1.0, scale_y=1.0, frame_width=1920, frame_height=1080)


def _load_ref(name: str) -> Image.Image:
    p = REF / name
    if not p.exists():
        pytest.skip(f"fixture not found: {p}")
    return Image.open(p).crop((1, 32, 1921, 1112))  # raw 1922×1112 → game coords


def _load_fix(name: str) -> Image.Image:
    p = FIX / name
    if not p.exists():
        pytest.skip(f"fixture not found: {p}")
    return Image.open(p)  # already game-coord (1920×1080)


# ── Positives: the open tab is yellow-active, and we're on the detail page ─────

@pytest.mark.parametrize("ref,tab", [
    ("reference_3_agent_page.png",       _TAB_BASE),
    ("reference_4_agent_skills_page.png", _TAB_SKILLS_IDX),
    ("reference_7_agent_equipment.png",  _TAB_EQUIP_IDX),
])
def test_active_tab_detected(ref, tab):
    frame = _load_ref(ref)
    assert _tab_active(frame, _CALIB, tab), f"{ref}: expected tab {tab} active"
    assert _on_detail_page(frame, _CALIB), f"{ref}: expected on detail page"


def test_only_the_open_tab_is_yellow():
    # On the Base Stats page, only the Base pill is yellow; Skills/Equipment are not.
    frame = _load_ref("reference_3_agent_page.png")
    assert _tab_active(frame, _CALIB, _TAB_BASE)
    assert not _tab_active(frame, _CALIB, _TAB_SKILLS_IDX)
    assert not _tab_active(frame, _CALIB, _TAB_EQUIP_IDX)


# ── Negatives: the wipe and the menu are NOT the detail page ───────────────────

def test_wipe_is_not_detail_page():
    frame = _load_fix("wipe.png")
    assert not _on_detail_page(frame, _CALIB), "AGENT SELECT wipe must be rejected"
    for tab in (_TAB_BASE, _TAB_SKILLS_IDX, _TAB_EQUIP_IDX):
        assert _tab_yellow_frac(frame, _CALIB, tab) < 0.40


def test_menu_is_not_detail_page():
    frame = _load_fix("menu.png")
    assert not _on_detail_page(frame, _CALIB), "agent menu must be rejected"


def test_blank_frame_is_not_detail_page():
    frame = Image.fromarray(np.zeros((1080, 1920, 3), dtype=np.uint8))
    assert not _on_detail_page(frame, _CALIB)


# ── H17: content-render gate (pill-yellow alone banks half-painted frames) ─────

def test_content_gate_accepts_rendered_pages():
    # A fully-rendered Base / Skills page passes the content gate.
    assert _tab_content_rendered(_load_ref("reference_3_agent_page.png"), _CALIB, _TAB_BASE)
    assert _tab_content_rendered(_load_ref("reference_4_agent_skills_page.png"), _CALIB, _TAB_SKILLS_IDX)


def test_content_gate_rejects_unrendered_frame():
    # wipe.png is a mid-transition frame (the live failure mode): the pill may be on but
    # the page content has not painted, so the content gate must reject it for both tabs.
    frame = _load_fix("wipe.png")
    assert not _tab_content_rendered(frame, _CALIB, _TAB_BASE)
    assert not _tab_content_rendered(frame, _CALIB, _TAB_SKILLS_IDX)


def test_content_gate_does_not_gate_equipment():
    # Equipment is intentionally not content-gated (engine hexagon reads dark when no
    # W-Engine is equipped; the equipment-tab frame feeds no OCR).
    assert _tab_content_rendered(_load_fix("wipe.png"), _CALIB, _TAB_EQUIP_IDX)
