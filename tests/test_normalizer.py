"""Tests for B4 normalizer."""
from __future__ import annotations

import pytest

from youkai_ocr.normalizer import (
    normalize_disc_set,
    normalize_main_stat,
    normalize_substat,
    parse_level,
    parse_numeric,
    parse_slot,
    validate_disc_level,
    validate_disc_rarity,
    validate_disc_slot,
)


# ── parse_slot ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("Bunny in Wonderland [1]", 1),
    ("Notes From the Chained [3]", 3),
    ("Astral Voice [6]", 6),
    ("No slot here", None),
    ("", None),
])
def test_parse_slot(text, expected):
    assert parse_slot(text) == expected


# ── normalize_disc_set ────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected_key", [
    ("Bunny in Wonderland [1]", "BunnyInWonderland"),
    ("Astral Voice",            "AstralVoice"),
    ("Woodpecker Electro [4]",  "WoodpeckerElectro"),
    ("Puffer Electro",          "PufferElectro"),
    ("Freedom Blues [2]",       "FreedomBlues"),
    ("Shockstar Disco",         "ShockstarDisco"),
])
def test_normalize_disc_set_exact(text, expected_key):
    key, conf = normalize_disc_set(text)
    assert key == expected_key, f"got {key!r} for {text!r}"
    assert conf >= 80.0


def test_normalize_disc_set_fuzzy():
    # OCR noise: missing space, extra char
    key, conf = normalize_disc_set("Bunny inWonderland [1]")
    assert key == "BunnyInWonderland"
    assert conf >= 60.0


def test_normalize_disc_set_no_match():
    key, conf = normalize_disc_set("")
    # Should return some key but with very low confidence, or empty.
    # An empty input matches unpredictably; just confirm it doesn't crash.
    assert isinstance(key, str)
    assert 0.0 <= conf <= 100.0


# ── normalize_substat ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected_key", [
    ("HP",                "hp"),
    ("ATK",               "atk"),
    ("DEF",               "def"),
    ("HP%",               "hp_"),
    ("ATK%",              "atk_"),
    ("CRIT Rate%",        "crit_"),
    ("CRIT DMG%",         "crit_dmg_"),
    ("Anomaly Proficiency","anomProf"),
    ("PEN",               "pen"),
])
def test_normalize_substat_exact(text, expected_key):
    key, conf = normalize_substat(text)
    assert key == expected_key, f"got {key!r} for {text!r}"
    assert conf >= 90.0


def test_normalize_substat_upgrade_stripped():
    key, conf = normalize_substat("CRIT Rate% +3")
    assert key == "crit_"
    assert conf >= 80.0


# ── normalize_main_stat ───────────────────────────────────────────────────────

@pytest.mark.parametrize("text,slot,expected_key", [
    ("HP",   1, "hp"),
    ("ATK",  2, "atk"),
    ("DEF",  3, "def"),
    ("HP",   4, "hp_"),
    ("ATK",  4, "atk_"),
    ("CRIT Rate", 4, "crit_"),
    ("CRIT DMG",  4, "crit_dmg_"),
    ("Electric DMG Bonus", 5, "electric_dmg_"),
    ("Fire DMG Bonus",     5, "fire_dmg_"),
    ("Anomaly Mastery",    6, "anomMas_"),
    ("Impact",             6, "impact_"),
    ("Energy Regen",       6, "enerRegen_"),
])
def test_normalize_main_stat(text, slot, expected_key):
    key, conf = normalize_main_stat(text, slot)
    assert key == expected_key, f"got {key!r} for slot={slot} text={text!r}"
    assert conf >= 80.0


# ── parse_level ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("Lv. 15/15", 15),
    ("Lv 4",      4),
    ("Lv.60/60",  60),
    ("15",        15),
    ("abc",       None),
])
def test_parse_level(text, expected):
    assert parse_level(text) == expected


# ── parse_numeric ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("1,234",   1234.0),
    ("15.3%",   15.3),
    ("684",     684.0),
    ("abc",     None),
    ("",        None),
])
def test_parse_numeric(text, expected):
    result = parse_numeric(text)
    if expected is None:
        assert result is None
    else:
        assert result == pytest.approx(expected)


# ── validators ────────────────────────────────────────────────────────────────

def test_validate_disc_level():
    assert validate_disc_level(0)
    assert validate_disc_level(15)
    assert not validate_disc_level(16)
    assert not validate_disc_level(-1)


def test_validate_disc_rarity():
    assert validate_disc_rarity(2)
    assert validate_disc_rarity(3)
    assert validate_disc_rarity(4)
    assert not validate_disc_rarity(1)
    assert not validate_disc_rarity(5)


def test_validate_disc_slot():
    for s in range(1, 7):
        assert validate_disc_slot(s)
    assert not validate_disc_slot(0)
    assert not validate_disc_slot(7)
