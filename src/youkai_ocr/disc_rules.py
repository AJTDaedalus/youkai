"""B6/B7: Disc Drive invariant validator + conservative repair.

Pure functions only — no OCR/capture imports (see DESIGN_disc_validation.md
Architecture). Expected-value tables live in data/zzz_1.4/disc_values.json,
not here, so a new game patch's stat changes are a data-only update.
"""
from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Optional

from youkai_ocr.zod import ZodDisc, ZodSubstat

# Relative tolerance on value/base = k before a substat is considered
# off-lattice (DESIGN "Expected-value tables" > "Substats").
_LATTICE_REL_TOL = 0.02

# hp/atk/def each have a flat and a percent substat variant that OCR can
# flip (E3). crit_/crit_dmg_/anomProf/pen have no flat<->percent counterpart.
_FLAT_PERCENT_PAIRS = {"hp": "hp_", "hp_": "hp", "atk": "atk_", "atk_": "atk", "def": "def_", "def_": "def"}


def _find_data_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "data" / "zzz_1.4"
    return Path(__file__).parent.parent.parent / "data" / "zzz_1.4"


_DATA_DIR = _find_data_dir()


@dataclass(frozen=True)
class RarityRules:
    label: str
    max_level: int
    growth_per_level: float
    upgrade_cadence: int
    n0_range: tuple[int, int]
    max_rolls_per_line: int


@dataclass(frozen=True)
class DiscValues:
    rarities: dict[int, RarityRules]
    main_stat_base: dict[str, dict[int, float]]
    substat_base: dict[str, dict[int, float]]


_cache: DiscValues | None = None


def load_disc_values() -> DiscValues:
    global _cache
    if _cache is not None:
        return _cache

    with open(_DATA_DIR / "disc_values.json") as f:
        raw = json.load(f)

    rarities = {
        int(rarity): RarityRules(
            label=r["label"],
            max_level=r["max_level"],
            growth_per_level=r["growth_per_level"],
            upgrade_cadence=r["upgrade_cadence"],
            n0_range=tuple(r["n0_range"]),
            max_rolls_per_line=r["max_rolls_per_line"],
        )
        for rarity, r in raw["rarities"].items()
    }
    main_stat_base = {
        key: {int(rarity): base for rarity, base in by_rarity.items()}
        for key, by_rarity in raw["main_stat_base"].items()
    }
    substat_base = {
        key: {int(rarity): base for rarity, base in by_rarity.items()}
        for key, by_rarity in raw["substat_base"].items()
    }

    _cache = DiscValues(rarities=rarities, main_stat_base=main_stat_base, substat_base=substat_base)
    return _cache


_main_stats_by_slot_cache: dict[str, set[str]] | None = None


def _load_main_stats_by_slot() -> dict[str, set[str]]:
    """slot_key -> legal main-stat ZOD keys, from stats.json (source of truth)."""
    global _main_stats_by_slot_cache
    if _main_stats_by_slot_cache is not None:
        return _main_stats_by_slot_cache

    with open(_DATA_DIR / "stats.json") as f:
        raw = json.load(f)

    _main_stats_by_slot_cache = {
        slot: set(names_to_keys.values())
        for slot, names_to_keys in raw["main_stats_by_slot"].items()
    }
    return _main_stats_by_slot_cache


def expected_main_value(rarity: int, key: str, level: int) -> float:
    """value(level) = base * (1 + growth * level); floored for flats, 1dp for percents."""
    dv = load_disc_values()
    rules = dv.rarities[rarity]
    base = dv.main_stat_base[key][rarity]
    raw = base * (1 + rules.growth_per_level * level)
    if key.endswith("_"):
        return round(raw, 1)
    return float(math.floor(raw))


def substat_base(rarity: int, key: str) -> float:
    dv = load_disc_values()
    return dv.substat_base[key][rarity]


def _main_value_matches(observed: float, expected: float, key: str) -> bool:
    if key.endswith("_"):
        return abs(observed - expected) <= 0.05
    return round(observed) == round(expected)


@dataclass(frozen=True)
class SubstatEvidence:
    """Raw OCR observations for one substat line, kept even when discarded downstream."""

    raw_name_text: Optional[str] = None
    raw_value_texts: tuple[str, ...] = ()
    roll_suffix: Optional[int] = None
    pct_seen: Optional[bool] = None


@dataclass(frozen=True)
class Evidence:
    """Raw OCR observations for a disc, beyond what made it into the ZodDisc."""

    main_value_raw: Optional[float] = None
    substats: tuple[Optional[SubstatEvidence], ...] = field(default_factory=tuple)


def evidence_from_conf(conf: dict, num_substats: int) -> Evidence:
    """Assemble Evidence from the conf dict's raw-observation keys.

    disc_scanner.py's conf dict carries confidence scores alongside the raw
    OCR observations repair_disc needs (T4 roll_suffix, T5 main_stat_value,
    T8 pct_seen) under the same keys — this reconstructs the Evidence object
    from them, so extraction and tests share one assembly path.
    """
    substats = tuple(
        SubstatEvidence(
            roll_suffix=(
                int(conf[f"substat_{i + 1}_roll_suffix"])
                if f"substat_{i + 1}_roll_suffix" in conf else None
            ),
            pct_seen=conf.get(f"substat_{i + 1}_pct_seen"),
        )
        for i in range(num_substats)
    )
    return Evidence(
        main_value_raw=conf.get("main_stat_value"),
        substats=substats,
    )


@dataclass(frozen=True)
class Violation:
    field: str
    code: str
    observed: object
    expected: object
    severity: str = "error"


def _substat_lattice_k(value: float, base: float) -> Optional[int]:
    """Nearest integer roll count for value/base, or None if off-lattice."""
    k = value / base
    nearest = round(k)
    if nearest < 1:
        return None
    if abs(k - nearest) > _LATTICE_REL_TOL:
        return None
    return nearest


def _validate_substats(disc: ZodDisc, rules: RarityRules) -> list[Violation]:
    dv = load_disc_values()
    violations: list[Violation] = []
    u = disc.level // rules.upgrade_cadence

    ks: list[Optional[int]] = []
    for i, sub in enumerate(disc.substats):
        base_by_rarity = dv.substat_base.get(sub.key)
        base = base_by_rarity.get(disc.rarity) if base_by_rarity is not None else None
        if base is None:
            ks.append(None)
            continue

        k = _substat_lattice_k(sub.value, base)
        if k is None:
            violations.append(
                Violation(f"substat[{i}]", "sub_not_on_lattice", sub.value, base, "error")
            )
            ks.append(None)
            continue

        ks.append(k)
        max_allowed = min(1 + u, rules.max_rolls_per_line)
        if k > max_allowed:
            violations.append(
                Violation(f"substat[{i}]", "sub_rolls_exceed_max", k, max_allowed, "error")
            )

    all_on_lattice = len(disc.substats) > 0 and all(k is not None for k in ks)
    if all_on_lattice:
        total = sum(ks) - u
        lo, hi = rules.n0_range
        if not (lo <= total <= hi):
            violations.append(Violation("substats", "roll_budget", total, (lo, hi), "error"))

    lo, hi = rules.n0_range
    expected_count = (min(4, lo + u), min(4, hi + u))
    visible_count = len(disc.substats)
    if not (expected_count[0] <= visible_count <= expected_count[1]):
        violations.append(Violation("substats", "sub_count", visible_count, expected_count, "error"))

    seen_keys: set[str] = set()
    for sub in disc.substats:
        if sub.key in seen_keys:
            violations.append(Violation("substats", "dup_substat", sub.key, "unique keys", "error"))
        seen_keys.add(sub.key)

    for i, sub in enumerate(disc.substats):
        if sub.key == disc.main_stat_key:
            violations.append(
                Violation(f"substat[{i}]", "sub_equals_main", sub.key, "!= main_stat_key", "error")
            )

    return violations


def validate_disc(disc: ZodDisc, evidence: Evidence | None = None) -> list[Violation]:
    """Prove `disc` is a *possible* disc under the ZZZ lattice invariants.

    Returns a list of Violation; empty means the disc is internally consistent.
    `evidence` (raw OCR observations, see Evidence) enables the main-value
    cross-check when present; without it that check is skipped, not failed.
    """
    dv = load_disc_values()
    violations: list[Violation] = []

    rules = dv.rarities.get(disc.rarity)
    if rules is None:
        violations.append(
            Violation("rarity", "rarity_range", disc.rarity, sorted(dv.rarities), "error")
        )

    legal_main_keys = _load_main_stats_by_slot().get(disc.slot_key)
    if legal_main_keys is None:
        violations.append(
            Violation("slot_key", "slot_range", disc.slot_key, sorted(_load_main_stats_by_slot()), "error")
        )

    if rules is not None and not (0 <= disc.level <= rules.max_level):
        violations.append(
            Violation("level", "level_range", disc.level, (0, rules.max_level), "error")
        )

    if legal_main_keys is not None and disc.main_stat_key not in legal_main_keys:
        violations.append(
            Violation("main_stat_key", "main_key_slot", disc.main_stat_key, sorted(legal_main_keys), "error")
        )

    if (
        rules is not None
        and evidence is not None
        and evidence.main_value_raw is not None
        and disc.main_stat_key in dv.main_stat_base
    ):
        expected = expected_main_value(disc.rarity, disc.main_stat_key, disc.level)
        if not _main_value_matches(evidence.main_value_raw, expected, disc.main_stat_key):
            violations.append(
                Violation("main_stat_value", "main_value_mismatch", evidence.main_value_raw, expected, "error")
            )

    if rules is not None:
        violations.extend(_validate_substats(disc, rules))

    return violations


@dataclass(frozen=True)
class Repair:
    field: str
    before: object
    after: object
    rule: str


@dataclass(frozen=True)
class RepairResult:
    disc: ZodDisc
    repairs: list[Repair]
    violations: list[Violation]


def _flat_percent_pair(key: str) -> Optional[str]:
    return _FLAT_PERCENT_PAIRS.get(key)


def _round_substat_value(value: float, key: str) -> float:
    """Match in-game display rounding: 1dp for percent lines, integer for flat."""
    return round(value, 1) if key.endswith("_") else float(round(value))


def _observed_digits(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.1f}".replace(".", "")


def _expected_digits(value: float, key: str) -> str:
    if key.endswith("_"):
        return f"{value:.1f}".replace(".", "")
    return str(int(round(value)))


def _edit_distance_le1(a: str, b: str) -> bool:
    """True if `a` and `b` differ by at most one substitution/insertion/deletion."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    la, lb = len(a), len(b)
    dp = [[0] * (lb + 1) for _ in range(la + 1)]
    for i in range(la + 1):
        dp[i][0] = i
    for j in range(lb + 1):
        dp[0][j] = j
    for i in range(1, la + 1):
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost)
    return dp[la][lb] <= 1


def _plausible_misread(observed: float, expected: float, key: str) -> bool:
    """Is `observed` a digit-edit-distance-1 corruption of `expected` (rendered as `key`)?

    Rejects observed<=0 outright: a zero-value line is an unreadable row (E5),
    not a corrupted real value, and must never be treated as a repair candidate.
    """
    if observed <= 0:
        return False
    return _edit_distance_le1(_observed_digits(observed), _expected_digits(expected, key))


def _resolve_candidates(
    candidates: list[tuple[str, int, float]], pct_seen: Optional[bool], observed: float
) -> Optional[tuple[str, int, float]]:
    """Pick the single plausible (key, k, expected) candidate, or None if ambiguous.

    Joint flat/percent + lattice resolution (E3): when both the flat and
    percent variant of a key are plausible, `pct_seen` breaks the tie. With no
    discriminator, an ambiguous candidate set is left unresolved — never a
    silent guess (DESIGN "Repair policy").
    """
    plausible = [c for c in candidates if _plausible_misread(observed, c[2], c[0])]
    if len(plausible) == 1:
        return plausible[0]
    if len(plausible) < 1:
        return None
    if pct_seen is True:
        percent_only = [c for c in plausible if c[0].endswith("_")]
        if len(percent_only) == 1:
            return percent_only[0]
    elif pct_seen is False:
        flat_only = [c for c in plausible if not c[0].endswith("_")]
        if len(flat_only) == 1:
            return flat_only[0]
    return None


def _try_roll_budget_forcing(
    candidates: list[tuple[str, int, float]], other_ks: list[int], u: int, n0_range: tuple[int, int]
) -> Optional[tuple[str, int, float]]:
    """If exactly one candidate's k makes the roll budget balance, force it."""
    lo, hi = n0_range
    valid = [c for c in candidates if lo <= sum(other_ks) + c[1] - u <= hi]
    if len(valid) == 1:
        return valid[0]
    return None


def repair_disc(disc: ZodDisc, evidence: Evidence | None = None) -> RepairResult:
    """Conservatively snap substat misreads onto the lattice.

    Precedence (DESIGN "Repair policy"): roll-suffix agreement, then unique
    lattice neighbor, then roll-budget forcing, then leave untouched (the
    residual `sub_not_on_lattice`/etc. violation stands). Never invents a
    value without one of these discriminators.
    """
    dv = load_disc_values()
    rules = dv.rarities.get(disc.rarity)
    if rules is None:
        return RepairResult(disc=disc, repairs=[], violations=validate_disc(disc, evidence))

    u = disc.level // rules.upgrade_cadence
    max_allowed = min(1 + u, rules.max_rolls_per_line)

    resolved: dict[int, int] = {}  # substat index -> k, for lines already on-lattice
    pending: list[int] = []
    for i, sub in enumerate(disc.substats):
        base = dv.substat_base.get(sub.key, {}).get(disc.rarity)
        k = _substat_lattice_k(sub.value, base) if base is not None else None
        if k is not None and k <= max_allowed:
            resolved[i] = k
        else:
            pending.append(i)

    new_substats: list[ZodSubstat] = list(disc.substats)
    repairs: list[Repair] = []
    rule2_candidates_by_index: dict[int, list[tuple[str, int, float]]] = {}

    for i in pending:
        sub = disc.substats[i]
        if sub.value <= 0:
            continue  # unreadable row (E5) — flag-only, never a repair candidate

        candidate_keys = [
            key for key in [sub.key, _flat_percent_pair(sub.key)]
            if key is not None and key != disc.main_stat_key
        ]

        ev_sub = evidence.substats[i] if evidence and i < len(evidence.substats) else None
        roll_suffix = ev_sub.roll_suffix if ev_sub else None
        pct_seen = ev_sub.pct_seen if ev_sub else None

        chosen: Optional[tuple[str, int, float]] = None
        rule_name = ""

        # Rule 1: roll-suffix agreement.
        if roll_suffix is not None:
            k_suffix = roll_suffix + 1
            rule1_candidates = []
            for key in candidate_keys:
                base = dv.substat_base.get(key, {}).get(disc.rarity)
                if base is None or not (1 <= k_suffix <= max_allowed):
                    continue
                rule1_candidates.append((key, k_suffix, _round_substat_value(base * k_suffix, key)))
            chosen = _resolve_candidates(rule1_candidates, pct_seen, sub.value)
            if chosen is not None:
                rule_name = "roll_suffix"

        # Rule 2: unique lattice neighbor.
        rule2_candidates: list[tuple[str, int, float]] = []
        if chosen is None:
            for key in candidate_keys:
                base = dv.substat_base.get(key, {}).get(disc.rarity)
                if base is None:
                    continue
                for k in range(1, max_allowed + 1):
                    rule2_candidates.append((key, k, _round_substat_value(base * k, key)))
            chosen = _resolve_candidates(rule2_candidates, pct_seen, sub.value)
            if chosen is not None:
                rule_name = "lattice_neighbor"
            else:
                rule2_candidates_by_index[i] = [
                    c for c in rule2_candidates if _plausible_misread(sub.value, c[2], c[0])
                ]

        if chosen is not None:
            key, k, expected = chosen
            repairs.append(
                Repair(
                    field=f"substat[{i}]",
                    before={"key": sub.key, "value": sub.value},
                    after={"key": key, "value": expected},
                    rule=rule_name,
                )
            )
            new_substats[i] = ZodSubstat(key=key, value=expected)
            resolved[i] = k

    # Rule 3: roll-budget forcing — only when exactly one line remains unresolved
    # (a multi-line simultaneous ambiguity is out of scope; it falls through to flag-only).
    unresolved = [
        i for i in pending
        if disc.substats[i].value > 0 and i not in resolved and rule2_candidates_by_index.get(i)
    ]
    if len(unresolved) == 1:
        i = unresolved[0]
        other_ks = [k for j, k in resolved.items() if j != i]
        forced = _try_roll_budget_forcing(rule2_candidates_by_index[i], other_ks, u, rules.n0_range)
        if forced is not None:
            key, k, expected = forced
            sub = disc.substats[i]
            repairs.append(
                Repair(
                    field=f"substat[{i}]",
                    before={"key": sub.key, "value": sub.value},
                    after={"key": key, "value": expected},
                    rule="roll_budget",
                )
            )
            new_substats[i] = ZodSubstat(key=key, value=expected)

    repaired_disc = replace(disc, substats=new_substats)
    return RepairResult(disc=repaired_disc, repairs=repairs, violations=validate_disc(repaired_disc, evidence))
