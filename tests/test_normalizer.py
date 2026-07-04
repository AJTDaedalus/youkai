"""Tests for B4 normalizer."""
from __future__ import annotations

import pytest

from youkai_ocr.normalizer import (
    normalize_agent,
    normalize_disc_set,
    normalize_engine,
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


# ── T2: live set-list refresh (2026-07-04) ────────────────────────────────────

def test_normalize_disc_set_wuthering_salon():
    key, conf = normalize_disc_set("Wuthering Salon [2]")
    assert key == "WutheringSalon"
    assert conf >= 95.0


def test_normalize_disc_set_the_sky_ablaze():
    key, conf = normalize_disc_set("The Sky Ablaze [5]")
    assert key == "TheSkyAblaze"
    assert conf >= 95.0


_OLD_26_DISC_SET_KEYS = {
    "WoodpeckerElectro", "PufferElectro", "ShockstarDisco", "FreedomBlues",
    "HormonePunk", "SoulRock", "SwingJazz", "ChaosJazz", "ProtoPunk",
    "InfernoMetal", "ChaoticMetal", "ThunderMetal", "PolarMetal", "FangedMetal",
    "BranchBladeSong", "AstralVoice", "ShadowHarmony", "PhaethonsMelody",
    "YunkuiTales", "KingOfTheSummit", "DawnsBloom", "MoonlightLullaby",
    "WhiteWaterBallad", "ShiningAria", "BunnyInWonderland", "NotesFromTheChained",
}


def test_disc_sets_old_26_keys_unchanged():
    from youkai_ocr import normalizer

    normalizer._load()
    assert _OLD_26_DISC_SET_KEYS <= set(normalizer._disc_sets.values())


def test_disc_sets_excludes_removed_beta_stubs():
    # T2: these titles share the wiki's Category:Drive Discs but carry
    # Category:Removed + Category:Drive Disc Missing ID — beta stubs, never
    # released. They must not appear as ZOD keys (see LOG T2).
    from youkai_ocr import normalizer

    normalizer._load()
    excluded_display_names = {
        "Assassin's Ballad", "Doom Grindcore", "Ecstatic Punk", "Mammoth Electro",
        "Monsoon Funk", "Noisy Pop", "Twisted Grindcore", "Unicorn Electro",
        "Vagabond Folk",
    }
    assert excluded_display_names.isdisjoint(normalizer._disc_sets.keys())


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


# ── normalize_agent (H24 / H27.1) ────────────────────────────────────────────

@pytest.mark.parametrize("text,expected_key", [
    # Short names
    ("Zhao",         "Zhao"),
    ("Rina",         "Rina"),
    ("Yanagi",       "Yanagi"),
    ("Miyabi",       "Miyabi"),
    ("Harumasa",     "Harumasa"),
    ("Zhu Yuan",     "ZhuYuan"),
    ("Manato",       "Manato"),
    ("Lycaon",       "Lycaon"),
    ("Anby",         "Anby"),
    ("Billy",        "Billy"),
    ("Jane",         "Jane"),
    ("Ju Fufu",      "JuFufu"),
    ("Hugo",         "Hugo"),
    ("Koleda",       "Koleda"),
    ("Soukaku",      "Soukaku"),
    ("Ye Shunguang", "YeShunguang"),
    ("Pan Yinhu",    "PanYinhu"),
    ("Nangong Yu",   "NangongYu"),
    # Full in-game display names
    ("Tsukishiro Yanagi",  "Yanagi"),
    ("Asaba Harumasa",     "Harumasa"),
    ("Komano Manato",      "Manato"),
    ("Hoshimi Miyabi",     "Miyabi"),
    ("Von Lycaon",         "Lycaon"),
    ("Anby Demara",        "Anby"),
    ("Jane Doe",           "Jane"),
    ("Billy Kid",          "Billy"),
    ("Alexandrina",        "Rina"),
    ("Seth Lowe",          "Seth"),
    ("Orphie & Magus",     "OrphieMagus"),
    # Dialyn is a distinct physical/stun agent (NOT Rina — H27.1 fix)
    ("Dialyn",             "Dialyn"),
    # Post-1.4 agents
    ("Yixuan",   "Yixuan"),
    ("Astra",    "Astra"),
    ("Astra Yao","Astra"),
    ("Seth",     "Seth"),
    ("Trigger",  "Trigger"),
    ("Vivian",   "Vivian"),
    ("Pulchra",  "Pulchra"),
    # OCR-noise variants that still resolve (score ≥ 85)
    ("Dan Yinhu",    "PanYinhu"),
    ("Orphie Magnus","OrphieMagus"),
    # H30.2 — new full-name aliases
    ("Nekomiya Manaka", "Nekomata"),
    ("Nekomiya Mana",   "Nekomata"),
    ("Orphie Magnusson","OrphieMagus"),
    # H30.1 — junk-stripping: widened bbox may append icon glyphs
    ("Trigger ",  "Trigger"),
    ("Pulchra ◆",  "Pulchra"),
    # Qingyi OCR aliases (Q→G/O glyph confusion in bold ZZZ font)
    ("Ginayi",    "Qingyi"),
    ("Oinayi",    "Qingyi"),
])
def test_normalize_agent_full_names(text, expected_key):
    key, score = normalize_agent(text)
    assert key == expected_key, f"got {key!r} (score={score}) for {text!r}"
    assert score >= 85.0


@pytest.mark.parametrize("garbage", [
    "Ye Shundat",
    "",
])
def test_normalize_agent_floor_rejects_garbage(garbage):
    key, score = normalize_agent(garbage)
    assert key == "", f"expected empty key for {garbage!r}, got {key!r} (score={score})"


# ── normalize_engine floor (T2) ───────────────────────────────────────────────

def test_normalize_engine_known_resolves():
    key, score = normalize_engine("Steam Oven")
    assert key == "SteamOven", f"got {key!r} (score={score})"
    assert score >= 80.0


@pytest.mark.parametrize("garbage", [
    "Nonexistent Engine 9000",
    "Astral Voice [1]",   # a disc-set title bled into the engine slot (ref_10, H4)
    "",
])
def test_normalize_engine_floor_rejects_garbage(garbage):
    """Below-floor matches return ('', <floor) so the caller emits unknown_engine
    instead of snapping a foreign name to the nearest engine key."""
    from youkai_ocr.normalizer import _ENGINE_NAME_SCORE_MIN
    key, score = normalize_engine(garbage)
    assert key == "", f"expected empty key for {garbage!r}, got {key!r} (score={score})"
    assert score < _ENGINE_NAME_SCORE_MIN
