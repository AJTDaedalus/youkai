"""Tests for disc_rules.py.

T1: data-load part. T6: validator (`validate_disc` + supporting pure functions).

See docs/DESIGN_disc_validation.md 'Expected-value tables' / 'Architecture' and
docs/TASKS_disc_validation.md T1/T6 for the source values and acceptance criteria.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from youkai_ocr.disc_rules import (
    Evidence,
    RepairResult,
    SubstatEvidence,
    Violation,
    expected_main_value,
    load_disc_values,
    repair_disc,
    substat_base,
    validate_disc,
)
from youkai_ocr.zod import ZodDisc, ZodSubstat

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


# ── expected_main_value / substat_base ────────────────────────────────────────

@pytest.mark.parametrize(
    ("rarity", "level", "expected"),
    [
        (4, 0, 79), (4, 3, 126), (4, 4, 142), (4, 15, 316),   # S atk (verified vs archive, DESIGN)
        (3, 0, 53), (3, 3, 92), (3, 4, 106), (3, 12, 212),    # A atk
        (2, 0, 26), (2, 3, 52), (2, 4, 60), (2, 9, 104),      # B atk
    ],
)
def test_expected_main_value_flat_atk(rarity, level, expected):
    assert expected_main_value(rarity, "atk", level) == expected


def test_expected_main_value_percent_is_one_decimal():
    # S def_ base 12, growth 0.20: level 3 -> 12*1.6 = 19.2
    assert expected_main_value(4, "def_", 3) == 19.2


def test_substat_base_accessor():
    assert substat_base(4, "crit_dmg_") == 4.8
    assert substat_base(3, "hp") == 75


# ── validate_disc: clean discs (zero violations) across rarity/level tiers ───

def _disc(rarity, slot, level, main_key, subs):
    return ZodDisc(
        set_key="ChaosJazz",
        slot_key=slot,
        level=level,
        rarity=rarity,
        main_stat_key=main_key,
        location="",
        lock=False,
        substats=[ZodSubstat(key=k, value=v) for k, v in subs],
    )


_CLEAN_CASES = [
    # S-rank (rarity=4, max_level=15, n0=(3,4), cadence 3, cap 6). Substat bases:
    # hp_=3, atk_=3, def_=4.8, crit_=2.4.
    (4, 0, [("hp_", 3), ("atk_", 3), ("def_", 4.8)]),  # n0=3, u=0: all k=1
    (4, 3, [("hp_", 3), ("atk_", 3), ("def_", 4.8), ("crit_", 2.4)]),  # n0=3,u=1: new 4th line (count<4)
    (4, 4, [("hp_", 3), ("atk_", 3), ("def_", 4.8), ("crit_", 2.4)]),  # same cadence bucket as level 3
    (4, 15, [("hp_", 9), ("atk_", 6), ("def_", 9.6), ("crit_", 4.8)]),  # n0=4,u=5: k=[3,2,2,2], sum=9
    # A-rank (rarity=3, max_level=12, n0=(2,3), cadence 3, cap 4). Substat bases:
    # hp_=2, atk_=2, def_=3.2, crit_dmg_=3.2.
    (3, 0, [("hp_", 2), ("atk_", 2)]),  # n0=2,u=0
    (3, 3, [("hp_", 2), ("atk_", 2), ("def_", 3.2)]),  # n0=2,u=1: new 3rd line
    (3, 4, [("hp_", 2), ("atk_", 2), ("def_", 3.2)]),
    (3, 12, [("hp_", 8), ("atk_", 2), ("def_", 3.2), ("crit_dmg_", 3.2)]),  # n0=3,u=4: k=[4,1,1,1], sum=7
    # B-rank (rarity=2, max_level=9, n0=(1,2), cadence 3, cap 2). Substat bases:
    # hp_=1, atk_=1, def_=1.6, crit_=0.8.
    (2, 0, [("hp_", 1)]),  # n0=1, u=0
    (2, 3, [("hp_", 1), ("atk_", 1)]),  # n0=1,u=1: new 2nd line
    (2, 4, [("hp_", 1), ("atk_", 1)]),
    (2, 9, [("hp_", 1), ("atk_", 1), ("def_", 1.6), ("crit_", 0.8)]),  # n0=1,u=3: capped at 4 lines
]


@pytest.mark.parametrize(("rarity", "level", "subs"), _CLEAN_CASES)
def test_validate_disc_clean_discs_have_no_violations(rarity, level, subs):
    # main key "anomProf" never collides with any substat key used above.
    disc = _disc(rarity, slot="4", level=level, main_key="anomProf", subs=subs)
    evidence = Evidence(main_value_raw=expected_main_value(rarity, "anomProf", level))
    assert validate_disc(disc, evidence) == []


def test_validate_disc_clean_disc_with_no_evidence_still_clean():
    disc = _disc(4, slot="4", level=0, main_key="crit_", subs=[("hp_", 3), ("atk_", 3), ("def_", 4.8)])
    assert validate_disc(disc) == []


# ── validate_disc: real error cases from DESIGN Findings (E1-E5) ────────────

def test_rarity_range_violation():
    disc = _disc(5, slot="4", level=0, main_key="crit_", subs=[])
    violations = validate_disc(disc)
    codes = [v.code for v in violations]
    assert "rarity_range" in codes


def test_slot_range_violation():
    disc = _disc(4, slot="9", level=0, main_key="crit_", subs=[("hp_", 3)] * 3)
    violations = validate_disc(disc)
    assert any(v.code == "slot_range" for v in violations)


def test_level_range_violation_above_max():
    disc = _disc(4, slot="4", level=99, main_key="crit_", subs=[])
    violations = validate_disc(disc)
    assert any(v.code == "level_range" and v.observed == 99 for v in violations)


def test_level_range_violation_negative():
    disc = _disc(2, slot="4", level=-1, main_key="crit_", subs=[])
    violations = validate_disc(disc)
    assert any(v.code == "level_range" for v in violations)


def test_main_key_slot_violation():
    # slot 1 only legally carries "hp" (flat) as main stat.
    disc = _disc(4, slot="1", level=0, main_key="atk", subs=[])
    violations = validate_disc(disc)
    assert any(v.code == "main_key_slot" for v in violations)


def test_main_value_mismatch_flat():
    disc = _disc(4, slot="2", level=4, main_key="atk", subs=[("hp_", 3), ("atk_", 3), ("def_", 4.8)])
    evidence = Evidence(main_value_raw=999)  # true value is 142
    violations = validate_disc(disc, evidence)
    mismatches = [v for v in violations if v.code == "main_value_mismatch"]
    assert len(mismatches) == 1
    assert mismatches[0].expected == 142


def test_main_value_mismatch_percent():
    disc = _disc(4, slot="4", level=3, main_key="def_", subs=[("hp_", 3), ("atk_", 3), ("crit_", 2.4)])
    evidence = Evidence(main_value_raw=999.9)  # true value is 19.2
    violations = validate_disc(disc, evidence)
    mismatches = [v for v in violations if v.code == "main_value_mismatch"]
    assert len(mismatches) == 1
    assert mismatches[0].expected == 19.2


def test_main_value_no_evidence_skips_check():
    disc = _disc(4, slot="2", level=4, main_key="atk", subs=[("hp_", 3), ("atk_", 3), ("def_", 4.8)])
    violations = validate_disc(disc, evidence=None)
    assert not any(v.code == "main_value_mismatch" for v in violations)


def test_sub_not_on_lattice_crit_dmg_4_4_true_4_8():
    """E2: tesseract read 4.4 for a true 4.8 CRIT DMG% line (8->4 digit confusion)."""
    disc = _disc(4, slot="4", level=0, main_key="hp_", subs=[("crit_dmg_", 4.4)])
    violations = validate_disc(disc)
    hit = [v for v in violations if v.code == "sub_not_on_lattice"]
    assert len(hit) == 1
    assert hit[0].observed == 4.4
    assert hit[0].expected == 4.8


def test_sub_not_on_lattice_crit_dmg_9_2_true_9_6():
    """E2: tesseract read 9.2 for a true 9.6 (two-roll CRIT DMG%, 6->2 confusion)."""
    disc = _disc(4, slot="4", level=6, main_key="hp_", subs=[("crit_dmg_", 9.2)])
    violations = validate_disc(disc)
    assert any(v.code == "sub_not_on_lattice" and v.observed == 9.2 for v in violations)


def test_sub_not_on_lattice_def_44_true_def_pct_14_4():
    """E2/E3: flat `def 44.0` should have been percent `def_ 14.4` (3 rolls); as a flat
    substat 44/15=2.933 is a near-miss to k=3 but outside the 0.02 lattice tolerance."""
    disc = _disc(4, slot="4", level=9, main_key="hp_", subs=[("def", 44.0)])
    violations = validate_disc(disc)
    assert any(v.code == "sub_not_on_lattice" and v.observed == 44.0 for v in violations)


def test_sub_value_zero_unreadable_line_flagged():
    """E5: an unreadable row exported as value=0.0 must never pass silently."""
    disc = _disc(4, slot="4", level=0, main_key="hp_", subs=[("pen", 0.0)])
    violations = validate_disc(disc)
    assert any(v.code == "sub_not_on_lattice" and v.observed == 0.0 for v in violations)


def test_dup_substat_violation():
    """E5: duplicate substat key."""
    disc = _disc(
        4, slot="4", level=0, main_key="hp_",
        subs=[("pen", 9), ("pen", 9), ("crit_", 2.4)],
    )
    violations = validate_disc(disc)
    assert any(v.code == "dup_substat" and v.observed == "pen" for v in violations)


def test_sub_equals_main_is_warning_not_error():
    """E4: substat duplicates main stat (slot-1 flat HP main, hp substat)."""
    disc = _disc(4, slot="1", level=0, main_key="hp", subs=[("hp", 112)])
    violations = validate_disc(disc)
    hit = [v for v in violations if v.code == "sub_equals_main"]
    assert len(hit) == 1
    assert hit[0].severity == "warning"


def test_sub_rolls_exceed_max_for_level():
    """A 2-roll substat at level 0 (u=0) can have at most k=1 -> exceeds max."""
    disc = _disc(4, slot="4", level=0, main_key="hp_", subs=[("crit_", 4.8)])  # k=2, cap 1
    violations = validate_disc(disc)
    assert any(v.code == "sub_rolls_exceed_max" and v.observed == 2 for v in violations)


def test_sub_rolls_exceed_max_per_rarity_cap():
    """B-rank per-line cap is 2 rolls even at max level (u=3 would otherwise allow 4)."""
    disc = _disc(2, slot="4", level=9, main_key="hp_", subs=[("crit_", 2.4)])  # k=3, cap min(4,2)=2
    violations = validate_disc(disc)
    assert any(v.code == "sub_rolls_exceed_max" and v.observed == 3 and v.expected == 2 for v in violations)


def test_roll_budget_violation_when_all_on_lattice():
    """4 lines each at k=1, level 15 (u=5): sum-u = 4-5 = -1, outside S n0_range (3,4)."""
    disc = _disc(
        4, slot="4", level=15, main_key="hp_",
        subs=[("atk_", 3), ("def_", 4.8), ("crit_", 2.4), ("crit_dmg_", 4.8)],
    )
    violations = validate_disc(disc)
    assert any(v.code == "roll_budget" for v in violations)


def test_roll_budget_skipped_when_a_line_is_off_lattice():
    """roll_budget must not fire alongside an unresolved sub_not_on_lattice line."""
    disc = _disc(
        4, slot="4", level=15, main_key="hp_",
        subs=[("atk_", 3), ("def_", 4.8), ("crit_", 2.4), ("crit_dmg_", 4.4)],  # last line off-lattice
    )
    violations = validate_disc(disc)
    codes = [v.code for v in violations]
    assert "sub_not_on_lattice" in codes
    assert "roll_budget" not in codes


def test_sub_count_too_few_visible_lines():
    """S-rank at level 4 (u=1) must show >= min(4,3+1)=4 lines; only 2 given."""
    disc = _disc(4, slot="4", level=4, main_key="hp_", subs=[("atk_", 3), ("def_", 4.8)])
    violations = validate_disc(disc)
    assert any(v.code == "sub_count" and v.observed == 2 for v in violations)


def test_sub_count_too_many_visible_lines():
    disc = _disc(
        2, slot="4", level=0, main_key="hp_",
        subs=[("atk_", 1), ("def_", 1.6), ("crit_", 0.8)],  # B n0=(1,2), u=0 -> expected (1,2)
    )
    violations = validate_disc(disc)
    assert any(v.code == "sub_count" and v.observed == 3 for v in violations)


def test_substat_unknown_key_skipped_gracefully():
    """A substat key absent from the substat_base table (e.g. OCR garbage that fuzzy-
    matched to something outside the table) must not crash the lattice check, and
    must not be reported as sub_not_on_lattice (there's no base to compare against)."""
    disc = _disc(4, slot="4", level=0, main_key="hp_", subs=[("not_a_real_key", 123.0)])
    violations = validate_disc(disc)
    assert not any(v.code == "sub_not_on_lattice" for v in violations)


def test_module_imports_no_ocr_or_capture_layers():
    """Architectural constraint: disc_rules is pure, no OCR/capture imports."""
    import youkai_ocr.disc_rules as m

    src = Path(m.__file__).read_text()
    for banned in ("import disc_scanner", "from youkai_ocr.disc_scanner", "PIL", "tesseract", "pynput"):
        assert banned not in src


def test_violation_is_frozen_dataclass_with_expected_fields():
    v = Violation(field="x", code="y", observed=1, expected=2)
    assert v.severity == "error"
    with pytest.raises(Exception):
        v.field = "z"  # type: ignore[misc]


# ── repair_disc: conservative repair (T7) ────────────────────────────────────


def _evidence(*, main_value_raw=None, roll_suffix=None, pct_seen=None, n=1) -> Evidence:
    subs = tuple(
        SubstatEvidence(roll_suffix=roll_suffix, pct_seen=pct_seen) if i == 0 else None
        for i in range(n)
    )
    return Evidence(main_value_raw=main_value_raw, substats=subs)


def test_repair_crit_dmg_4_4_roll_suffix_agreement():
    """E2: `+0` roll suffix agrees with 4.8 (single digit misread 8->4) -> rule 1."""
    disc = _disc(4, slot="4", level=0, main_key="hp_", subs=[("crit_dmg_", 4.4)])
    result = repair_disc(disc, _evidence(roll_suffix=0))
    assert len(result.repairs) == 1
    assert result.repairs[0].rule == "roll_suffix"
    assert result.disc.substats[0].key == "crit_dmg_"
    assert result.disc.substats[0].value == 4.8


def test_repair_crit_dmg_9_2_roll_suffix_agreement():
    """E2: `+1` roll suffix agrees with 9.6 (two-roll, 6->2 misread) -> rule 1."""
    disc = _disc(4, slot="4", level=6, main_key="hp_", subs=[("crit_dmg_", 9.2)])
    result = repair_disc(disc, _evidence(roll_suffix=1))
    assert len(result.repairs) == 1
    assert result.repairs[0].rule == "roll_suffix"
    assert result.disc.substats[0].key == "crit_dmg_"
    assert result.disc.substats[0].value == 9.6


def test_repair_def_44_roll_suffix_and_pct_seen_flips_key():
    """E2+E3: `+2` roll suffix gives k=3 for both def(45) and def_(14.4); `pct_seen`
    breaks the flat/percent tie -> repaired to def_ 14.4, key AND value both change."""
    disc = _disc(4, slot="4", level=9, main_key="hp_", subs=[("def", 44.0)])
    result = repair_disc(disc, _evidence(roll_suffix=2, pct_seen=True))
    assert len(result.repairs) == 1
    assert result.repairs[0].rule == "roll_suffix"
    assert result.disc.substats[0].key == "def_"
    assert result.disc.substats[0].value == 14.4


def test_repair_def_44_no_suffix_evidence_is_ambiguous_never_guesses():
    """E2/E3 without a discriminator: def(k=3)=45 and def_(k=3)=14.4 are both
    plausible lattice neighbors with identical k, so roll-budget forcing can't
    disambiguate either -> must never silently pick one."""
    disc = _disc(4, slot="4", level=9, main_key="hp_", subs=[("def", 44.0)])
    result = repair_disc(disc, evidence=None)
    assert result.repairs == []
    assert result.disc.substats[0].key == "def"
    assert result.disc.substats[0].value == 44.0
    assert any(v.code == "sub_not_on_lattice" for v in result.violations)


def test_repair_pen_zero_is_flag_only_never_invented():
    """E5: an unreadable row exported as 0.0 must never be repaired to a guessed value."""
    disc = _disc(4, slot="4", level=0, main_key="hp_", subs=[("pen", 0.0)])
    result = repair_disc(disc, evidence=None)
    assert result.repairs == []
    assert result.disc.substats[0].key == "pen"
    assert result.disc.substats[0].value == 0.0
    assert any(v.code == "sub_not_on_lattice" and v.observed == 0.0 for v in result.violations)


@pytest.mark.parametrize(("rarity", "level", "subs"), _CLEAN_CASES)
def test_repair_disc_is_idempotent_on_clean_discs(rarity, level, subs):
    disc = _disc(rarity, slot="4", level=level, main_key="anomProf", subs=subs)
    evidence = Evidence(main_value_raw=expected_main_value(rarity, "anomProf", level))
    result = repair_disc(disc, evidence)
    assert result.repairs == []
    assert [(s.key, s.value) for s in result.disc.substats] == subs
    assert result.violations == []


def test_repair_crit_dmg_via_unique_lattice_neighbor_without_suffix_evidence():
    """crit_dmg_ has no flat/percent counterpart, so even without roll-suffix
    evidence a single-digit misread has exactly one legal neighbor -> rule 2."""
    disc = _disc(4, slot="4", level=0, main_key="hp_", subs=[("crit_dmg_", 4.4)])
    result = repair_disc(disc, evidence=None)
    assert len(result.repairs) == 1
    assert result.repairs[0].rule == "lattice_neighbor"
    assert result.disc.substats[0].value == 4.8


def test_repair_pct_seen_false_prefers_flat_candidate():
    """Same ambiguous def/def_ pair as the pct_seen=True case, but pct_seen=False
    should force the flat candidate instead."""
    disc = _disc(4, slot="4", level=9, main_key="hp_", subs=[("def", 44.0)])
    result = repair_disc(disc, _evidence(roll_suffix=2, pct_seen=False))
    assert len(result.repairs) == 1
    assert result.disc.substats[0].key == "def"
    assert result.disc.substats[0].value == 45.0


def test_repair_unknown_substat_key_skipped_gracefully():
    """A substat key absent from substat_base (no lattice to repair against)
    must not crash and must be left untouched."""
    disc = _disc(4, slot="4", level=0, main_key="hp_", subs=[("not_a_real_key", 123.0)])
    result = repair_disc(disc, evidence=None)
    assert result.repairs == []
    assert result.disc.substats[0].key == "not_a_real_key"
    assert result.disc.substats[0].value == 123.0


def test_repair_no_plausible_candidate_leaves_value_untouched():
    """A value with no digit-edit-distance-1 neighbor anywhere on the lattice
    must be left alone rather than snapped to the nearest (implausible) k."""
    disc = _disc(4, slot="4", level=0, main_key="hp_", subs=[("crit_dmg_", 500.0)])
    result = repair_disc(disc, evidence=None)
    assert result.repairs == []
    assert result.disc.substats[0].value == 500.0


def test_repair_roll_budget_forcing_resolves_unique_assignment():
    """anomProf has no flat/percent pair, so its ambiguity is purely which `k`
    (44 is edit-distance-1 from both k=5->45 and k=6->54); only k=5 keeps the
    roll budget (other lines sum k=4, u=5) in the S n0_range (3,4)."""
    disc = _disc(
        4, slot="4", level=15, main_key="crit_dmg_",
        subs=[("hp_", 3.0), ("atk_", 3.0), ("def_", 9.6), ("anomProf", 44.0)],
    )
    result = repair_disc(disc, evidence=None)
    assert len(result.repairs) == 1
    assert result.repairs[0].rule == "roll_budget"
    assert result.disc.substats[3].key == "anomProf"
    assert result.disc.substats[3].value == 45.0


def test_repair_unknown_rarity_returns_untouched_with_violations():
    """No rarity rules to repair against -> leave disc untouched, still validate."""
    disc = _disc(5, slot="4", level=0, main_key="hp_", subs=[])
    result = repair_disc(disc, evidence=None)
    assert result.repairs == []
    assert result.disc is disc
    assert any(v.code == "rarity_range" for v in result.violations)


def test_repair_roll_suffix_out_of_range_falls_through_to_lattice_neighbor():
    """A roll-suffix implying a k beyond the rarity's cap can't be used for rule 1,
    but the value still resolves via rule 2 (crit_dmg_ has no pair, unique k=1)."""
    disc = _disc(4, slot="4", level=0, main_key="hp_", subs=[("crit_dmg_", 4.4)])
    result = repair_disc(disc, _evidence(roll_suffix=10))
    assert len(result.repairs) == 1
    assert result.repairs[0].rule == "lattice_neighbor"
    assert result.disc.substats[0].value == 4.8


def test_repair_result_is_frozen_dataclass_with_expected_shape():
    disc = _disc(4, slot="4", level=0, main_key="anomProf", subs=[("hp_", 3), ("atk_", 3), ("def_", 4.8)])
    result = repair_disc(disc, evidence=None)
    assert isinstance(result, RepairResult)
    assert result.repairs == []
    assert result.violations == []
