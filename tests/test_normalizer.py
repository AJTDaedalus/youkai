"""Tests for B4 normalizer."""

from __future__ import annotations

from pathlib import Path

import pytest

from youkai_ocr.normalizer import (
    normalize_agent,
    normalize_disc_set,
    normalize_engine,
    normalize_main_stat,
    normalize_substat,
    parse_level,
    parse_numeric,
    parse_roll_suffix,
    parse_slot,
    validate_disc_level,
    validate_disc_rarity,
    validate_disc_slot,
)

# ── parse_slot ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Bunny in Wonderland [1]", 1),
        ("Notes From the Chained [3]", 3),
        ("Astral Voice [6]", 6),
        ("No slot here", None),
        ("", None),
    ],
)
def test_parse_slot(text, expected):
    assert parse_slot(text) == expected


@pytest.mark.parametrize(
    "text,garbled_result,strict_result",
    [
        # disc_2070 (T12): OCR misread "[1]" as "[ 4" — the garble-tolerant
        # fallback confidently returns the wrong digit, so the strict tier must
        # return None and let the panel slot-widget read (G5) outrank it.
        ("Fanged Metal [ 4", 4, None),
        ("Dawn's Bloom < [ 6 ] 4", 6, None),
        ("Bunny in Wonderland [1]", 1, 1),  # clean bracket: both tiers agree
    ],
)
def test_parse_slot_strict_rejects_garbled_bracket(text, garbled_result, strict_result):
    assert parse_slot(text) == garbled_result
    assert parse_slot(text, allow_garbled=False) == strict_result


# ── normalize_disc_set ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text,expected_key",
    [
        ("Bunny in Wonderland [1]", "BunnyInWonderland"),
        ("Astral Voice", "AstralVoice"),
        ("Woodpecker Electro [4]", "WoodpeckerElectro"),
        ("Puffer Electro", "PufferElectro"),
        ("Freedom Blues [2]", "FreedomBlues"),
        ("Shockstar Disco", "ShockstarDisco"),
    ],
)
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
    "WoodpeckerElectro",
    "PufferElectro",
    "ShockstarDisco",
    "FreedomBlues",
    "HormonePunk",
    "SoulRock",
    "SwingJazz",
    "ChaosJazz",
    "ProtoPunk",
    "InfernoMetal",
    "ChaoticMetal",
    "ThunderMetal",
    "PolarMetal",
    "FangedMetal",
    "BranchBladeSong",
    "AstralVoice",
    "ShadowHarmony",
    "PhaethonsMelody",
    "YunkuiTales",
    "KingOfTheSummit",
    "DawnsBloom",
    "MoonlightLullaby",
    "WhiteWaterBallad",
    "ShiningAria",
    "BunnyInWonderland",
    "NotesFromTheChained",
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
        "Assassin's Ballad",
        "Doom Grindcore",
        "Ecstatic Punk",
        "Mammoth Electro",
        "Monsoon Funk",
        "Noisy Pop",
        "Twisted Grindcore",
        "Unicorn Electro",
        "Vagabond Folk",
    }
    assert excluded_display_names.isdisjoint(normalizer._disc_sets.keys())


# ── normalize_disc_set unknown-set floor (T3) ─────────────────────────────────


@pytest.mark.parametrize(
    "garbage",
    [
        "Future Set Name [1]",
        "Nonexistent Set 9000",
        "",
    ],
)
def test_normalize_disc_set_floor_rejects_unknown(garbage):
    """Below-floor matches return ('', <floor) so the caller emits unknown_set
    instead of snapping a foreign/unmapped title to the nearest set — the
    Wuthering-Salon-read-as-SwingJazz failure mode (E1), fixed by T2's table
    refresh + this floor as a backstop for the *next* unmapped patch."""
    from youkai_ocr.normalizer import _SET_NAME_SCORE_MIN

    key, score = normalize_disc_set(garbage)
    assert key == "", f"expected empty key for {garbage!r}, got {key!r} (score={score})"
    assert score < _SET_NAME_SCORE_MIN


def test_normalize_disc_set_partial_wonderland_still_resolves():
    # Real archived OCR (docs/diag_title_reocr_20260704.json, disc with a
    # 2-line title where only "Wonderland" survived): scores 68-73, comfortably
    # above the 60 floor, and must still resolve rather than critical-fail.
    key, score = normalize_disc_set("B Z Wonderland [1] »®")
    assert key == "BunnyInWonderland", f"got {key!r} (score={score})"
    assert score >= 60.0


def test_normalize_disc_set_shockstar_dropped_char_still_resolves():
    # Real archived OCR with a dropped trailing char: scores ~78, above floor.
    key, score = normalize_disc_set("Shockstar Disc G] 6 ©")
    assert key == "ShockstarDisco", f"got {key!r} (score={score})"
    assert score >= 60.0


def test_normalize_disc_set_floor_below_all_legit_sweep_scores():
    """Re-verify the 60 floor against the full June-22 sweep now that T2 has
    landed: every legit title (all but the 6 pre-existing blank-OCR crops)
    must clear the floor. See LOG T3 for the observed minimum (68.42, the
    Wonderland partial title)."""
    import json

    from youkai_ocr.normalizer import _SET_NAME_SCORE_MIN

    diag_path = Path(__file__).resolve().parents[1] / "docs" / "diag_title_reocr_20260704.json"
    if not diag_path.exists():
        pytest.skip("diagnostic sweep file missing")
    rows = json.loads(diag_path.read_text())

    resolved_scores = []
    unresolved = []
    for row in rows:
        key, score = normalize_disc_set(row["ocr"])
        if key:
            resolved_scores.append(score)
        else:
            unresolved.append(row)

    # Only the 6 pre-existing blank-OCR crops (empty ocr text) should fail to
    # resolve; every legit title must clear the floor.
    assert all(r["ocr"] == "" for r in unresolved), (
        f"unexpected below-floor legit titles: {unresolved[:5]}"
    )
    assert len(unresolved) == 6
    assert min(resolved_scores) >= _SET_NAME_SCORE_MIN


# ── normalize_substat ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text,expected_key",
    [
        ("HP", "hp"),
        ("ATK", "atk"),
        ("DEF", "def"),
        ("HP%", "hp_"),
        ("ATK%", "atk_"),
        ("CRIT Rate%", "crit_"),
        ("CRIT DMG%", "crit_dmg_"),
        ("Anomaly Proficiency", "anomProf"),
        ("PEN", "pen"),
    ],
)
def test_normalize_substat_exact(text, expected_key):
    key, conf = normalize_substat(text)
    assert key == expected_key, f"got {key!r} for {text!r}"
    assert conf >= 90.0


def test_normalize_substat_upgrade_stripped():
    key, conf = normalize_substat("CRIT Rate% +3")
    assert key == "crit_"
    assert conf >= 80.0


# ── parse_roll_suffix ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text,expected",
    [
        ("DEF +2", 2),
        ("CRIT Rate", None),
        ("Anomaly Proficiency +1", 1),
        ("CRIT Rate% +3", 3),
        ("", None),
        ("DEF +l", 1),  # OCR noise: 'l' misread for the digit '1'
        # T12/Cluster-1: wide values ("14.4%") straddle the name/value bbox
        # boundary, bleeding their leading digit(s) into the name crop. The
        # suffix must still parse when trailing bleed follows it.
        ("DEF +2 1", 2),  # disc_0001/0091 et al. — the literal 38-disc read
        ("DEF +2 14", 2),
        ("HP +2 336", 2),
        ("DEF +21", None),  # merged bleed: ambiguous, refuse rather than guess
    ],
)
def test_parse_roll_suffix(text, expected):
    assert parse_roll_suffix(text) == expected


# ── normalize_main_stat ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text,slot,expected_key",
    [
        ("HP", 1, "hp"),
        ("ATK", 2, "atk"),
        ("DEF", 3, "def"),
        ("HP", 4, "hp_"),
        ("ATK", 4, "atk_"),
        ("CRIT Rate", 4, "crit_"),
        ("CRIT DMG", 4, "crit_dmg_"),
        ("Electric DMG Bonus", 5, "electric_dmg_"),
        ("Fire DMG Bonus", 5, "fire_dmg_"),
        ("Anomaly Mastery", 6, "anomMas_"),
        ("Impact", 6, "impact_"),
        ("Energy Regen", 6, "enerRegen_"),
    ],
)
def test_normalize_main_stat(text, slot, expected_key):
    key, conf = normalize_main_stat(text, slot)
    assert key == expected_key, f"got {key!r} for slot={slot} text={text!r}"
    assert conf >= 80.0


@pytest.mark.parametrize("text", ["", "   "])
@pytest.mark.parametrize("slot", [1, 4, 5, 6])
def test_normalize_main_stat_empty_query_returns_no_match(text, slot):
    """T12/Cluster-3: rapidfuzz scores every candidate 0 for an empty query and
    returns the first one arbitrarily — an OCR total-failure must yield the
    explicit ("", 0.0) no-match signal, never a confident-looking key
    (disc_0576/0618: empty main-name read silently became "hp_")."""
    assert normalize_main_stat(text, slot) == ("", 0.0)


@pytest.mark.parametrize("text", ["", "   ", "+2"])
def test_normalize_substat_empty_query_returns_no_match(text):
    """Same unguarded-empty-query gap as normalize_main_stat ("+2" strips to
    empty via _UPGRADE_RE). normalize_agent/engine/disc_set are already safe
    behind their score floors."""
    assert normalize_substat(text) == ("", 0.0)


# ── parse_level ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Lv. 15/15", 15),
        ("Lv 4", 4),
        ("Lv.60/60", 60),
        ("15", 15),
        ("abc", None),
    ],
)
def test_parse_level(text, expected):
    assert parse_level(text) == expected


# ── parse_numeric ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text,expected",
    [
        ("1,234", 1234.0),
        ("15.3%", 15.3),
        ("684", 684.0),
        ("abc", None),
        ("", None),
    ],
)
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


@pytest.mark.parametrize(
    "text,expected_key",
    [
        # Short names
        ("Zhao", "Zhao"),
        ("Rina", "Rina"),
        ("Yanagi", "Yanagi"),
        ("Miyabi", "Miyabi"),
        ("Harumasa", "Harumasa"),
        ("Zhu Yuan", "ZhuYuan"),
        ("Manato", "Manato"),
        ("Lycaon", "Lycaon"),
        ("Anby", "Anby"),
        ("Billy", "Billy"),
        ("Jane", "Jane"),
        ("Ju Fufu", "JuFufu"),
        ("Hugo", "Hugo"),
        ("Koleda", "Koleda"),
        ("Soukaku", "Soukaku"),
        ("Ye Shunguang", "YeShunguang"),
        ("Pan Yinhu", "PanYinhu"),
        ("Nangong Yu", "NangongYu"),
        # Full in-game display names
        ("Tsukishiro Yanagi", "Yanagi"),
        ("Asaba Harumasa", "Harumasa"),
        ("Komano Manato", "Manato"),
        ("Hoshimi Miyabi", "Miyabi"),
        ("Von Lycaon", "Lycaon"),
        ("Anby Demara", "Anby"),
        ("Jane Doe", "Jane"),
        ("Billy Kid", "Billy"),
        ("Alexandrina", "Rina"),
        ("Seth Lowe", "Seth"),
        ("Orphie & Magus", "OrphieMagus"),
        # Dialyn is a distinct physical/stun agent (NOT Rina — H27.1 fix)
        ("Dialyn", "Dialyn"),
        # Post-1.4 agents
        ("Yixuan", "Yixuan"),
        ("Astra", "Astra"),
        ("Astra Yao", "Astra"),
        ("Seth", "Seth"),
        ("Trigger", "Trigger"),
        ("Vivian", "Vivian"),
        ("Pulchra", "Pulchra"),
        # OCR-noise variants that still resolve (score ≥ 85)
        ("Dan Yinhu", "PanYinhu"),
        ("Orphie Magnus", "OrphieMagus"),
        # H30.2 — new full-name aliases
        ("Nekomiya Manaka", "Nekomata"),
        ("Nekomiya Mana", "Nekomata"),
        ("Orphie Magnusson", "OrphieMagus"),
        # H30.1 — junk-stripping: widened bbox may append icon glyphs
        ("Trigger ", "Trigger"),
        ("Pulchra ◆", "Pulchra"),
        # Qingyi OCR aliases (Q→G/O glyph confusion in bold ZZZ font)
        ("Ginayi", "Qingyi"),
        ("Oinayi", "Qingyi"),
    ],
)
def test_normalize_agent_full_names(text, expected_key):
    key, score = normalize_agent(text)
    assert key == expected_key, f"got {key!r} (score={score}) for {text!r}"
    assert score >= 85.0


@pytest.mark.parametrize(
    "garbage",
    [
        "Ye Shundat",
        "",
    ],
)
def test_normalize_agent_floor_rejects_garbage(garbage):
    key, score = normalize_agent(garbage)
    assert key == "", f"expected empty key for {garbage!r}, got {key!r} (score={score})"


# ── normalize_engine floor (T2) ───────────────────────────────────────────────


def test_normalize_engine_known_resolves():
    key, score = normalize_engine("Steam Oven")
    assert key == "SteamOven", f"got {key!r} (score={score})"
    assert score >= 80.0


@pytest.mark.parametrize(
    "garbage",
    [
        "Nonexistent Engine 9000",
        "Astral Voice [1]",  # a disc-set title bled into the engine slot (ref_10, H4)
        "",
    ],
)
def test_normalize_engine_floor_rejects_garbage(garbage):
    """Below-floor matches return ('', <floor) so the caller emits unknown_engine
    instead of snapping a foreign name to the nearest engine key."""
    from youkai_ocr.normalizer import _ENGINE_NAME_SCORE_MIN

    key, score = normalize_engine(garbage)
    assert key == "", f"expected empty key for {garbage!r}, got {key!r} (score={score})"
    assert score < _ENGINE_NAME_SCORE_MIN
