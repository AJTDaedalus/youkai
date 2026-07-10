"""B4: Normalizer + validator.

rapidfuzz fuzzy-maps OCR text → canonical ZOD keys from data/zzz_1.4/*.json.
Numeric parsers and range validators live here too.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from rapidfuzz import fuzz, process


def _find_data_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "data" / "zzz_1.4"
    return Path(__file__).parent.parent.parent / "data" / "zzz_1.4"


_DATA_DIR = _find_data_dir()

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
        raw_engines = json.load(f)["engines"]
    # Strip _comment_* sentinel keys (their values are separator strings, not valid ZOD keys).
    _engines = {k: v for k, v in raw_engines.items() if not k.startswith("_comment")}

    _loaded = True


# ── Regex patterns ────────────────────────────────────────────────────────────

# Tolerant slot pattern: accepts [N], (N], {N], {N), [N<space>, [N!, etc.
# { is included because Tesseract sometimes misreads [ as { in dim text.
# Primary: bracket/paren/brace + digit + any closing char (optional).
# Fallback: bracket/paren/brace + 1-3 non-digit chars + digit 1-6 (handles OCR
# garbling the slot digit itself as ':', '.', etc.).
_SLOT_RE = re.compile(r"[\[({](\d)[\])\s!,.]?")
_SLOT_RE_FALLBACK = re.compile(r"[\[({][^\d]{1,3}([1-6])")
# Panel-slot fallback (G5): the digit+bracket OCR of the un-clipped panel yields
# strings like "[3]4" (bracketed slot + noise) or "6]"/"16]" (partial bracket).
# Prefer a fully-bracketed [N]; fall back to a digit adjacent to one bracket.
_PANEL_SLOT_FULL = re.compile(r"\[([1-6])\]")
_PANEL_SLOT_PARTIAL = re.compile(r"([1-6])\]|\[([1-6])")
_LV_RE = re.compile(r"Lv[.\s]*(\d+)")
_UPGRADE_RE = re.compile(r"\s*\+\d+\s*$")
_NUMERIC_STRIP = re.compile(r"[^\d.,]")


# ── Public API ────────────────────────────────────────────────────────────────

_SET_NAME_SCORE_MIN = 60  # WRatio floor: below this the match is too uncertain


def normalize_disc_set(text: str) -> tuple[str, float]:
    """Fuzzy-map display text (may include '[N]' slot suffix) → (ZOD key, 0-100).

    Returns ("", score) when the best match scores below _SET_NAME_SCORE_MIN so
    the caller's critical-fail gate emits unknown_set instead of silently snapping
    an unmapped set name to the nearest table entry — the "Wuthering Salon read as
    SwingJazz" failure mode (E1). Mirrors normalize_agent/normalize_engine. Floor
    calibrated from the June 22 title re-OCR sweep: foreign (truly unknown) set
    names top out at 46; legit-but-partial titles (2-line "Bunny in Wonderland"
    OCR'd as just "Wonderland") bottom out at 68.
    """
    _load()
    clean = _SLOT_RE.sub("", text).strip()
    result = process.extractOne(clean, list(_disc_sets.keys()), scorer=fuzz.WRatio)
    if result is None:
        return ("", 0.0)
    display, score, _ = result
    if float(score) < _SET_NAME_SCORE_MIN:
        return ("", float(score))
    return (_disc_sets[display], float(score))


def parse_slot(text: str, *, allow_garbled: bool = True) -> int | None:
    """Extract slot number from title text like 'Set Name [3]'. Returns None if absent.

    allow_garbled=False restricts to the primary clean-bracket pattern. The
    garble-tolerant fallback (`[` + junk chars + digit) can confidently return
    a *misread* digit — disc_2070's "[1]" OCR'd as "[ 4" (T12) — so callers
    with a second slot source (the G5 panel widget read) should try strict
    first, the panel next, and the garbled fallback only as a last resort.
    """
    m = _SLOT_RE.search(text)
    if m:
        return int(m.group(1))
    if not allow_garbled:
        return None
    m = _SLOT_RE_FALLBACK.search(text)
    return int(m.group(1)) if m else None


def parse_panel_slot(*texts: str) -> int | None:
    """Parse a slot 1-6 from one or more digit+bracket OCR passes (G5 fallback).

    A fully-bracketed ``[N]`` in any pass wins (preferred over noise digits like
    the trailing rarity in ``"[3]4"``). Otherwise a digit adjacent to a single
    bracket (``"6]"``, ``"16]"``, ``"[6"``) is accepted. Returns None if no pass
    contains a bracketed slot digit.
    """
    for text in texts:
        m = _PANEL_SLOT_FULL.search(text)
        if m:
            return int(m.group(1))
    for text in texts:
        m = _PANEL_SLOT_PARTIAL.search(text)
        if m:
            return int(m.group(1) or m.group(2))
    return None


_ROLL_SUFFIX_RE = re.compile(r"\+\s*([\dlI|])(?=\s|$)")


def parse_roll_suffix(text: str) -> int | None:
    """Extract the '+N' roll-upgrade count from substat text, or None if absent.

    `normalize_substat` strips this suffix (`_UPGRADE_RE`) before fuzzy-matching
    the stat name and discards the digit; this is the counterpart that keeps it,
    since `base × (N + 1)` is the deterministic evidence the repair policy needs
    (DESIGN Repair policy rule 1). Tolerates single-character OCR noise (l/I/|
    misread for the digit "1") since that's a cheap, common Tesseract confusion.

    The suffix is always a single digit (max +5 upgrades on a line), matched at
    a whitespace/end boundary rather than end-of-string: wide values ("14.4%")
    straddle the name/value bbox split and bleed leading digits into the name
    crop ("DEF +2 1" — T12/Cluster 1, 38 archive discs), which an end anchor
    silently rejects. A digit run merged with bleed ("+21") stays None —
    refuse rather than guess.
    """
    m = _ROLL_SUFFIX_RE.search(text)
    if not m:
        return None
    digit = m.group(1).translate(str.maketrans("lI|", "111"))
    return int(digit)


def normalize_substat(text: str) -> tuple[str, float]:
    """Map substat OCR text (may have '+N' upgrade suffix) → (ZOD key, 0-100).

    An empty query must return ("", 0.0): rapidfuzz scores every candidate 0
    for "" and returns the first arbitrarily, silently turning an OCR
    total-failure into a confident-looking key (T12/Cluster 3).
    """
    _load()
    clean = _UPGRADE_RE.sub("", text).strip()
    if not clean:
        return ("", 0.0)
    if clean in _substats:
        return (_substats[clean], 100.0)
    result = process.extractOne(clean, list(_substats.keys()), scorer=fuzz.WRatio)
    if result is None:
        return ("", 0.0)
    display, score, _ = result
    return (_substats[display], float(score))


def normalize_main_stat(text: str, slot: int) -> tuple[str, float]:
    """Map main stat OCR text for a given slot number → (ZOD key, 0-100).

    An empty query must return ("", 0.0) — same rapidfuzz empty-query trap as
    normalize_substat (disc_0576/0618: an empty main-name read silently became
    "hp_" at confidence 0.0 — T12/Cluster 3).
    """
    _load()
    slot_key = str(slot)
    if slot_key not in _main_stats:
        return ("", 0.0)
    candidates = _main_stats[slot_key]
    clean = text.strip()
    if not clean:
        return ("", 0.0)
    if clean in candidates:
        return (candidates[clean], 100.0)
    result = process.extractOne(clean, list(candidates.keys()), scorer=fuzz.WRatio)
    if result is None:
        return ("", 0.0)
    display, score, _ = result
    return (candidates[display], float(score))


_AGENT_NAME_SCORE_MIN = 85  # WRatio floor: below this the match is too uncertain

_AGENT_NAME_JUNK_RE = re.compile(r"[^A-Za-z0-9& -]")


def _clean_agent_name(text: str) -> str:
    """Strip OCR icon glyphs and junk from a widened name-bbox crop."""
    cleaned = _AGENT_NAME_JUNK_RE.sub(" ", text)
    tokens = [t for t in cleaned.split() if len(t) >= 2]
    return " ".join(tokens)


def normalize_agent(text: str) -> tuple[str, float]:
    """Fuzzy-map agent display name → (ZOD key, 0-100).

    Returns ("", score) when the best match scores below _AGENT_NAME_SCORE_MIN so
    the caller's CRITICAL_CONF gate emits unknown_agent instead of silently snapping
    to the nearest key (which was the "Zhao magnet" failure mode — H24).
    """
    _load()
    cleaned = _clean_agent_name(text)
    result = process.extractOne(cleaned, list(_agents.keys()), scorer=fuzz.WRatio)
    if result is None:
        return ("", 0.0)
    display, score, _ = result
    if float(score) < _AGENT_NAME_SCORE_MIN:
        return ("", float(score))
    return (_agents[display], float(score))


_ENGINE_NAME_SCORE_MIN = 80  # WRatio floor: below this the match is too uncertain

_ENGINE_NAME_JUNK_RE = re.compile(r"[^A-Za-z0-9'\[\] -]")
_ROMAN_CONFUSION_RE = re.compile(r"[Il1]+")


def _clean_engine_name(text: str) -> str:
    """Strip OCR icon junk from an engine-name crop; fix roman-numeral l/I mixups.

    The name bbox overlaps the engine icon, producing trailing junk tokens
    ("ee | &@ ae Sd"); and tesseract reads "III" as "Ill". Both made WRatio
    snap bracket-series siblings to the wrong entry (F2 golden-set finding).
    """
    cleaned = _ENGINE_NAME_JUNK_RE.sub(" ", text)
    out: list[str] = []
    for tok in cleaned.split():
        if _ROMAN_CONFUSION_RE.fullmatch(tok):
            out.append("I" * len(tok))
        elif len(tok) >= 3 or tok.lower() == "of":
            out.append(tok)
    return " ".join(out)


def normalize_engine(text: str) -> tuple[str, float]:
    """Fuzzy-map W-Engine display name → (ZOD key, 0-100).

    Returns ("", score) when the best match scores below _ENGINE_NAME_SCORE_MIN so
    the caller's empty-key gate emits unknown_engine instead of silently snapping a
    foreign name (e.g. a disc-set title bled into the engine slot) to the nearest
    engine — the "Astral Voice → FrostfallSickle @50" failure mode (T2). Mirrors
    normalize_agent. Lowest legit golden/equip engine scores ~83; foreign matches
    sit ~50, so the floor cleanly separates them.
    """
    _load()
    cleaned = _clean_engine_name(text)
    result = process.extractOne(cleaned, list(_engines.keys()), scorer=fuzz.WRatio)
    if result is None:
        return ("", 0.0)
    display, score, _ = result
    if float(score) < _ENGINE_NAME_SCORE_MIN:
        return ("", float(score))
    return (_engines[display], float(score))


def parse_level(text: str) -> int | None:
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


def parse_numeric(text: str) -> float | None:
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
