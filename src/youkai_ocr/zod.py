"""ZOD/GOOD export schema — mirrors youkai/src/zod.rs exactly.

Field names must match the Rust serde camelCase output. Any schema change
must be applied to both files in lockstep.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional


def to_zod_key(value: str) -> str:
    """Normalize a display string to a PascalCase alphanumeric ZOD key.

    Mirrors the Rust ``to_zod_key`` in zod.rs:
    - Split on space, underscore, or hyphen boundaries.
    - Capitalize the first letter of each word; lowercase the rest.
    - Strip non-alphanumeric characters.

    Examples:
        "Shockstar Disc"  -> "ShockstarDisc"
        "Chaotic Metal"   -> "ChaoticMetal"
        "HP"              -> "HP"   (no lowercasing of non-first chars, mirrors Rust)
        "CRIT Rate"       -> "CRITRate"
    """
    result = []
    capitalize_next = True
    for ch in value:
        if ch.isascii() and ch.isalnum():
            if capitalize_next:
                result.append(ch.upper())
                capitalize_next = False
            else:
                result.append(ch)  # no-op lowercase: mirrors Rust which also pushes as-is
        elif ch in (" ", "_", "-"):
            capitalize_next = True
    return "".join(result)


@dataclass
class ZodSubstat:
    key: str
    value: float

    def to_dict(self) -> dict:
        return {"key": self.key, "value": self.value}

    @classmethod
    def from_dict(cls, d: dict) -> "ZodSubstat":
        return cls(key=d["key"], value=d["value"])


@dataclass
class ZodDisc:
    set_key: str
    slot_key: str          # "1" through "6"
    level: int
    rarity: int            # 4 = S-rank, 3 = A-rank, 2 = B-rank
    main_stat_key: str
    location: str          # agent ZOD key, or "" if unequipped
    lock: bool
    substats: list[ZodSubstat] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "setKey": self.set_key,
            "slotKey": self.slot_key,
            "level": self.level,
            "rarity": self.rarity,
            "mainStatKey": self.main_stat_key,
            "location": self.location,
            "lock": self.lock,
            "substats": [s.to_dict() for s in self.substats],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ZodDisc":
        return cls(
            set_key=d["setKey"],
            slot_key=d["slotKey"],
            level=d["level"],
            rarity=d["rarity"],
            main_stat_key=d["mainStatKey"],
            location=d["location"],
            lock=d["lock"],
            substats=[ZodSubstat.from_dict(s) for s in d.get("substats", [])],
        )


@dataclass
class ZodWEngine:
    key: str
    level: int
    ascension: int
    refinement: int
    location: str          # agent ZOD key, or "" if unequipped
    lock: bool

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "level": self.level,
            "ascension": self.ascension,
            "refinement": self.refinement,
            "location": self.location,
            "lock": self.lock,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ZodWEngine":
        return cls(
            key=d["key"],
            level=d["level"],
            ascension=d["ascension"],
            refinement=d["refinement"],
            location=d["location"],
            lock=d["lock"],
        )


@dataclass
class ZodTalent:
    """Six talent/skill levels for one agent."""
    basic: int
    dodge: int
    assist: int
    special: int
    chain: int
    core: int              # Core Passive rank (0-6 in-game A–F nodes + inactive)

    def to_dict(self) -> dict:
        return {
            "basic": self.basic,
            "dodge": self.dodge,
            "assist": self.assist,
            "special": self.special,
            "chain": self.chain,
            "core": self.core,
        }


@dataclass
class ZodAgent:
    key: str
    level: int
    constellation: int     # Mindscape Cinema level 0-6
    ascension: int
    talent: Optional[ZodTalent] = None

    def to_dict(self) -> dict:
        d: dict = {
            "key": self.key,
            "level": self.level,
            "constellation": self.constellation,
            "ascension": self.ascension,
        }
        if self.talent is not None:
            d["talent"] = self.talent.to_dict()
        return d


@dataclass
class ZodExport:
    format: str = "GOOD"
    version: int = 1
    source: str = "Youkai"
    characters: list[ZodAgent] = field(default_factory=list)
    discs: list[ZodDisc] = field(default_factory=list)
    weapons: list[ZodWEngine] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "format": self.format,
            "version": self.version,
            "source": self.source,
            "characters": [c.to_dict() for c in self.characters],
            "discs": [d.to_dict() for d in self.discs],
            "weapons": [w.to_dict() for w in self.weapons],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)
