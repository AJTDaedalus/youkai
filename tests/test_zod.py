"""Tests for the ZOD emitter (A1).

Verifies:
- to_zod_key parity with the Rust implementation on a fixed string set.
- Hand-built ZodExport serialises to the exact camelCase field names the
  Rust serde output would produce.
"""

import json

import pytest

from youkai_ocr.zod import (
    ZodAgent,
    ZodDisc,
    ZodExport,
    ZodSubstat,
    ZodTalent,
    ZodWEngine,
    to_zod_key,
)


# ---------------------------------------------------------------------------
# to_zod_key parity (mirrors Rust test vectors)
# ---------------------------------------------------------------------------

ZOD_KEY_CASES = [
    ("Shockstar Disco", "ShockstarDisco"),
    ("Chaotic Metal", "ChaoticMetal"),
    ("Polar Metal", "PolarMetal"),
    ("Fanged Metal", "FangedMetal"),
    ("Puffer Electro", "PufferElectro"),
    ("Woodpecker Electro", "WoodpeckerElectro"),
    ("Hormone Punk", "HormonePunk"),
    ("Inferno Metal", "InfernoMetal"),
    ("Swing Jazz", "SwingJazz"),
    ("Chaotic Metal", "ChaoticMetal"),
    # stats — Rust pushes non-first chars as-is (no lowercasing), so all-caps abbrevs stay caps
    ("HP", "HP"),
    ("ATK", "ATK"),
    ("DEF", "DEF"),
    ("CRIT Rate", "CRITRate"),
    ("CRIT DMG", "CRITDMG"),
    ("Anomaly Proficiency", "AnomalyProficiency"),
    ("Anomaly Mastery", "AnomalyMastery"),
    ("PEN Ratio", "PENRatio"),
    ("Energy Regen", "EnergyRegen"),
    ("Impact", "Impact"),
    # separators
    ("some-hyphen_word", "SomeHyphenWord"),
    ("already_pascal", "AlreadyPascal"),
    ("  leading spaces", "LeadingSpaces"),
    ("trailing ", "Trailing"),
    ("123number", "123number"),
    ("", ""),
]


@pytest.mark.parametrize("display,expected", ZOD_KEY_CASES)
def test_to_zod_key(display: str, expected: str) -> None:
    assert to_zod_key(display) == expected


# ---------------------------------------------------------------------------
# Serialisation: field names must be camelCase, matching serde output
# ---------------------------------------------------------------------------

def _make_export() -> ZodExport:
    return ZodExport(
        characters=[
            ZodAgent(
                key="ZhuYuan",
                level=60,
                constellation=3,
                ascension=6,
                talent=ZodTalent(basic=12, dodge=12, assist=12, special=12, chain=12, core=6),
            )
        ],
        discs=[
            ZodDisc(
                set_key="ShockstarDisco",
                slot_key="1",
                level=15,
                rarity=4,
                main_stat_key="HP",
                location="ZhuYuan",
                lock=True,
                substats=[
                    ZodSubstat(key="ATK", value=19.0),
                    ZodSubstat(key="CRITRate", value=8.0),
                ],
            )
        ],
        weapons=[
            ZodWEngine(
                key="TheVault",
                level=60,
                ascension=5,
                refinement=1,
                location="ZhuYuan",
                lock=False,
            )
        ],
    )


def test_export_top_level_keys() -> None:
    d = _make_export().to_dict()
    assert set(d.keys()) == {"format", "version", "source", "characters", "discs", "weapons"}
    assert d["format"] == "GOOD"
    assert d["source"] == "Youkai"
    assert d["version"] == 1


def test_disc_field_names() -> None:
    disc = _make_export().to_dict()["discs"][0]
    expected_keys = {"setKey", "slotKey", "level", "rarity", "mainStatKey", "location", "lock", "substats"}
    assert set(disc.keys()) == expected_keys


def test_disc_substat_field_names() -> None:
    sub = _make_export().to_dict()["discs"][0]["substats"][0]
    assert set(sub.keys()) == {"key", "value"}


def test_weapon_field_names() -> None:
    w = _make_export().to_dict()["weapons"][0]
    assert set(w.keys()) == {"key", "level", "ascension", "refinement", "location", "lock"}


def test_agent_field_names_with_talent() -> None:
    char = _make_export().to_dict()["characters"][0]
    assert set(char.keys()) == {"key", "level", "constellation", "ascension", "talent"}
    talent = char["talent"]
    assert set(talent.keys()) == {"basic", "dodge", "assist", "special", "chain", "core"}


def test_agent_without_talent_omits_field() -> None:
    agent = ZodAgent(key="Nicole", level=50, constellation=0, ascension=4)
    d = agent.to_dict()
    assert "talent" not in d


def test_json_roundtrip() -> None:
    export = _make_export()
    raw = export.to_json()
    parsed = json.loads(raw)
    assert parsed["format"] == "GOOD"
    assert parsed["discs"][0]["setKey"] == "ShockstarDisco"
    assert parsed["characters"][0]["talent"]["core"] == 6
