"""Tests for the main-menu / agent-selection screen signatures — offline.

Regression cover for the 2026-07-29 scan-all failure: the agent-menu detector keyed on
the SELECT band's *hue*, but that band is tinted by whichever agent is selected, so it
false-negatived on every non-teal agent.  reference_14 (Astra Yao) is the fixture that
reproduces it; every earlier calibration frame happened to have Zhao (Ice) selected.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from youkai_ocr.capture import calibrate
from youkai_ocr.cli import (
    _AGENT_MENU_BAND_MIN_FRAC,
    _is_agent_selection_menu,
    _is_main_menu,
    agent_menu_band_fraction,
)

_REF = Path(__file__).parent.parent / "reference"

_MAIN_MENU = "reference_11_main_menu.png"
_AGENT_MENUS = [
    "reference_12_agent_menu.png",
    "reference_13_agent_menu_scrolled_down.png",
    # Astra Yao selected → band is grey (157,164,167), not teal.  The retired hue test
    # scored 0 teal pixels here and rejected a genuine agent-selection menu.
    "reference_14_agent_menu_scrolled_up.png",
]
_OTHER_SCREENS = [
    "reference_1_disc_menu.png",
    "reference_2_wengine_inventory.png",
    "reference_3_agent_page.png",  # agent detail, SELECT panel collapsed
    "reference_4_agent_skills_page.png",
    "reference_7_agent_equipment.png",
]

pytestmark = pytest.mark.skipif(
    not (_REF / _MAIN_MENU).exists(),
    reason="reference frames not present",
)


def _load(name: str):
    """Load a reference frame, trimming Windows chrome off windowed-mode captures."""
    frame = Image.open(_REF / name).convert("RGB")
    if frame.size == (1922, 1112):  # 1px border + 31px title bar
        frame = frame.crop((1, 31, 1921, 1111))
    return frame, calibrate(frame)


# ── Agent-selection menu ──────────────────────────────────────────────────────


@pytest.mark.parametrize("name", _AGENT_MENUS)
def test_agent_menu_detected_regardless_of_band_tint(name):
    frame, calib = _load(name)
    assert _is_agent_selection_menu(frame, calib), (
        f"{name} is an agent-selection menu but was not detected "
        f"(band fraction {agent_menu_band_fraction(frame, calib):.2f})"
    )


@pytest.mark.parametrize("name", _AGENT_MENUS)
def test_agent_menu_band_is_fully_lit(name):
    frame, calib = _load(name)
    assert agent_menu_band_fraction(frame, calib) >= _AGENT_MENU_BAND_MIN_FRAC


@pytest.mark.parametrize("name", _OTHER_SCREENS)
def test_non_agent_screens_rejected(name):
    frame, calib = _load(name)
    assert not _is_agent_selection_menu(frame, calib)
    assert agent_menu_band_fraction(frame, calib) == 0.0


def test_main_menu_is_not_mistaken_for_agent_menu():
    """The hub's background art lights the right edge too — main_menu must veto."""
    frame, calib = _load(_MAIN_MENU)
    assert _is_main_menu(frame, calib)
    assert not _is_agent_selection_menu(frame, calib)
    # It is bright enough to pass the band test on its own; the veto is what saves us.
    assert agent_menu_band_fraction(frame, calib) > 0.5


# ── Main menu ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", _AGENT_MENUS)
def test_main_menu_does_not_veto_agent_menus(name):
    """_is_main_menu gates _is_agent_selection_menu, so it must never fire here."""
    frame, calib = _load(name)
    assert not _is_main_menu(frame, calib)


@pytest.mark.parametrize(
    "name",
    [
        "reference_4_agent_skills_page.png",
        "reference_7_agent_equipment.png",
    ],
)
def test_main_menu_known_false_positives_stay_harmless(name):
    """_is_main_menu is loose: its luma bbox also lights up on agent sub-pages.

    Pre-existing and out of scope here, but pinned because _is_main_menu now vetoes
    the agent-menu check.  It stays harmless only because these screens have no SELECT
    band at all — if that ever changes, the veto needs a stricter hub test.
    """
    frame, calib = _load(name)
    assert _is_main_menu(frame, calib)
    assert agent_menu_band_fraction(frame, calib) == 0.0
    assert not _is_agent_selection_menu(frame, calib)
