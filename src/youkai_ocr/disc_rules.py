"""B6/B7: Disc Drive invariant validator + conservative repair.

Pure functions only — no OCR/capture imports (see DESIGN_disc_validation.md
Architecture). Expected-value tables live in data/zzz_1.4/disc_values.json,
not here, so a new game patch's stat changes are a data-only update.
"""
from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from youkai_ocr.zod import ZodDisc

# Relative tolerance on value/base = k before a substat is considered
# off-lattice (DESIGN "Expected-value tables" > "Substats").
_LATTICE_REL_TOL = 0.02


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
                Violation(f"substat[{i}]", "sub_equals_main", sub.key, "!= main_stat_key", "warning")
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
