"""B6/B7: Disc Drive invariant validator + conservative repair.

Pure functions only — no OCR/capture imports (see DESIGN_disc_validation.md
Architecture). Expected-value tables live in data/zzz_1.4/disc_values.json,
not here, so a new game patch's stat changes are a data-only update.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path


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
