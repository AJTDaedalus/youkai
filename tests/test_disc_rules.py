"""Tests for disc_rules.py — T1: data-load part only.

See docs/DESIGN_disc_validation.md 'Expected-value tables' and
docs/TASKS_disc_validation.md T1 for the source values and acceptance criteria.
"""
from __future__ import annotations

import json
from pathlib import Path

from youkai_ocr.disc_rules import load_disc_values

_DATA_DIR = Path(__file__).parent.parent / "data" / "zzz_1.4"


def _stats_json() -> dict:
    with open(_DATA_DIR / "stats.json") as f:
        return json.load(f)


# ── Key-set reconciliation against stats.json (the acceptance gate) ──────────

def test_main_stat_keys_match_stats_json_all_slots():
    stats = _stats_json()
    expected_keys = {
        key for slot in stats["main_stats_by_slot"].values() for key in slot.values()
    }
    dv = load_disc_values()
    assert set(dv.main_stat_base.keys()) == expected_keys


def test_substat_keys_match_stats_json():
    stats = _stats_json()
    expected_keys = set(stats["substats"].values())
    dv = load_disc_values()
    assert set(dv.substat_base.keys()) == expected_keys


# ── Shape ──────────────────────────────────────────────────────────────────────

def test_rarities_present_for_s_a_b():
    dv = load_disc_values()
    assert set(dv.rarities.keys()) == {2, 3, 4}


def test_every_main_stat_has_all_three_rarities():
    dv = load_disc_values()
    for key, by_rarity in dv.main_stat_base.items():
        assert set(by_rarity.keys()) == {2, 3, 4}, key


def test_every_substat_has_all_three_rarities():
    dv = load_disc_values()
    for key, by_rarity in dv.substat_base.items():
        assert set(by_rarity.keys()) == {2, 3, 4}, key


# ── Spot values (DESIGN Expected-value tables, cross-checked against archive) ─

def test_s_rank_atk_main_base_and_growth():
    dv = load_disc_values()
    assert dv.main_stat_base["atk"][4] == 79
    assert dv.rarities[4].growth_per_level == 0.20


def test_s_rank_crit_dmg_substat_base():
    dv = load_disc_values()
    assert dv.substat_base["crit_dmg_"][4] == 4.8


def test_a_rank_max_level():
    dv = load_disc_values()
    assert dv.rarities[3].max_level == 12


def test_b_rank_n0_range():
    dv = load_disc_values()
    assert dv.rarities[2].n0_range == (1, 2)


def test_a_rank_hp_atk_substat_base_matches_archive_not_stale_stats_json():
    """A-rank hp/atk substat bases are 75/13 (wiki + archive-verified), NOT the
    79/15 in stats.json's unused substat_step_values block (stale AdeptiScanner
    data) — see disc_values.json _meta note."""
    dv = load_disc_values()
    assert dv.substat_base["hp"][3] == 75
    assert dv.substat_base["atk"][3] == 13
