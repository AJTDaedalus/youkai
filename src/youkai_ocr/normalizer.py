"""B4: Normalizer + validator.

rapidfuzz fuzzy-maps OCR text → canonical ZOD keys from data/zzz_1.4/*.json.
Numeric parsers and range validators live here too.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from rapidfuzz import fuzz, process

_DATA_DIR = Path(__file__).parent.parent.parent / "data" / "zzz_1.4"

_disc_sets: dict[str, str] = {}
_substats: dict[str, str] = {}
_main_stats: dict[str, dict[str, str]] = {}
_agents: dict[str, str] = {}
_engines: dict[str, str] = {}
_loaded = False


def _load() -> None:
    global _disc_sets, _substats, _main_stats, _agents, _engines, _loaded
    if _loaded:
        return

    with open(_DATA_DIR / "disc_sets.json") as f:
        _disc_sets = json.load(f)["disc_sets"]

    with open(_DATA_DIR / "stats.json") as f:
        data = json.load(f)
        _substats = data["substats"]
        _main_stats = data["main_stats_by_slot"]

    with open(_DATA_DIR / "agents.json") as f:
        _agents = json.load(f)["agents"]

    with open(_DATA_DIR / "engines.json") as f:
        _engines = json.load(f)["engines"]

    _loaded = True


# ── Regex patterns ────────────────────────────────────────────────────────────

# Tolerant slot pattern: accepts [N], (N], [N), [N<space>, [N!, etc.
# Primary: bracket/paren + digit + any closing char (optional).
# Fallback: bracket/paren + 1-3 non-digit chars + digit 1-6 (handles OCR
# garbling the slot digit itself as ':', '.', etc.).
_SLOT_RE = re.compile(r"[\[(](\d)[\])\s!,.]?")
_SLOT_RE_FALLBACK = re.compile(r"[\[(][^\d]{1,3}([1-6])")
_LV_RE = re.compile(r"Lv[.\s]*(\d+)")
_UPGRADE_RE = re.compile(r"\s*\+\d+\s*$")
_NUMERIC_STRIP = re.compile(r"[^\d.,]")


# ── Public API ────────────────────────────────────────────────────────────────

def normalize_disc_set(text: str) -> tuple[str, float]:
    """Fuzzy-map display text (may include '[N]' slot suffix) → (ZOD key, 0-100)."""
    _load()
    clean = _SLOT_RE.sub("", text).strip()
    result = process.extractOne(clean, list(_disc_sets.keys()), scorer=fuzz.WRatio)
    if result is None:
        return ("", 0.0)
    display, score, _ = result
    return (_disc_sets[display], float(score))


def parse_slot(text: str) -> Optional[int]:
    """Extract slot number from title text like 'Set Name [3]'. Returns None if absent."""
    m = _SLOT_RE.search(text)
    if m:
        return int(m.group(1))
    m = _SLOT_RE_FALLBACK.search(text)
    return int(m.group(1)) if m else None


def normalize_substat(text: str) -> tuple[str, float]:
    """Map substat OCR text (may have '+N' upgrade suffix) → (ZOD key, 0-100)."""
    _load()
    clean = _UPGRADE_RE.sub("", text).strip()
    if clean in _substats:
        return (_substats[clean], 100.0)
    result = process.extractOne(clean, list(_substats.keys()), scorer=fuzz.WRatio)
    if result is None:
        return ("", 0.0)
    display, score, _ = result
    return (_substats[display], float(score))


def normalize_main_stat(text: str, slot: int) -> tuple[str, float]:
    """Map main stat OCR text for a given slot number → (ZOD key, 0-100)."""
    _load()
    slot_key = str(slot)
    if slot_key not in _main_stats:
        return ("", 0.0)
    candidates = _main_stats[slot_key]
    clean = text.strip()
    if clean in candidates:
        return (candidates[clean], 100.0)
    result = process.extractOne(clean, list(candidates.keys()), scorer=fuzz.WRatio)
    if result is None:
        return ("", 0.0)
    display, score, _ = result
    return (candidates[display], float(score))


def normalize_agent(text: str) -> tuple[str, float]:
    """Fuzzy-map agent display name → (ZOD key, 0-100)."""
    _load()
    result = process.extractOne(text.strip(), list(_agents.keys()), scorer=fuzz.WRatio)
    if result is None:
        return ("", 0.0)
    display, score, _ = result
    return (_agents[display], float(score))


def normalize_engine(text: str) -> tuple[str, float]:
    """Fuzzy-map W-Engine display name → (ZOD key, 0-100)."""
    _load()
    result = process.extractOne(text.strip(), list(_engines.keys()), scorer=fuzz.WRatio)
    if result is None:
        return ("", 0.0)
    display, score, _ = result
    return (_engines[display], float(score))


def parse_level(text: str) -> Optional[int]:
    """Parse 'Lv. 15/15' or 'Lv 60' → first integer."""
    m = _LV_RE.search(text)
    if m:
        return int(m.group(1))
    # Fallback: grab first run of digits.
    m2 = re.search(r"\d+", text)
    return int(m2.group()) if m2 else None


# W-Engine level-cap → ascension table (max level per ascension phase).
_ASCENSION_FROM_MAX: dict[int, int] = {10: 0, 20: 1, 30: 2, 40: 3, 50: 4, 60: 5}


def parse_level_with_ascension(text: str) -> tuple[int, int]:
    """Parse 'Lv. 40/40' → (level=40, ascension=3).

    The max-level suffix (/N) maps to ascension via the W-Engine cap table.
    Falls back to (level, 0) when the max is absent or unrecognized.
    """
    m = re.search(r"(\d+)\s*/\s*(\d+)", text)
    if m:
        level = int(m.group(1))
        ascension = _ASCENSION_FROM_MAX.get(int(m.group(2)), 0)
        return (level, ascension)
    level = parse_level(text) or 0
    return (level, 0)


def parse_numeric(text: str) -> Optional[float]:
    """Parse a stat value like '1,234' or '15.3%' → float."""
    clean = text.replace(",", "").replace("%", "").strip()
    try:
        return float(clean)
    except ValueError:
        m = re.search(r"\d+\.?\d*", clean)
        return float(m.group()) if m else None


# ── Validators ────────────────────────────────────────────────────────────────

def validate_disc_level(level: int) -> bool:
    return 0 <= level <= 15


def validate_disc_rarity(rarity: int) -> bool:
    return rarity in (2, 3, 4)


def validate_disc_slot(slot: int) -> bool:
    return 1 <= slot <= 6
