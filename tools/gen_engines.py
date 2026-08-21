"""Generate data/zzz_1.4/engines.json from the fairy database (source of truth).

Reads every W-engine modifier file under fairy's w_engines/ dir, maps each
display name → ZOD key via to_zod_key (with one override where the algorithm
diverges from fairy's canonical key), and validates every key against fairy's
canonical ZOD keyset (references/zo-allStat_gen.json["wengine"]).

Re-run whenever fairy adds an engine:  python tools/gen_engines.py

Source of truth: /root/fairy. Do not hand-edit data/zzz_1.4/engines.json.

Engines that are live in-game but have no fairy modifier file yet go in
EXTRA_ENGINES, so the scanner can recognise them without waiting on fairy's kit
curation. That path is a stopgap, not a second source of truth: the generator
hard-errors once fairy ships the real file, so the entry has to be removed.
"""

from __future__ import annotations

import glob
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from youkai_ocr.zod import to_zod_key  # noqa: E402

FAIRY = Path("/root/fairy")
W_ENGINES = FAIRY / "backend/app/data/modifiers/w_engines"
ZO_ALLSTAT = FAIRY / "references/zo-allStat_gen.json"
OUT = Path(__file__).parent.parent / "data/zzz_1.4/engines.json"

# to_zod_key diverges from fairy's canonical key only here: the hyphen in the
# "Fur-nace" pun yields "RoaringFurNace", but the canonical ZOD key is "RoaringFurnace".
KEY_OVERRIDES = {"Roaring Fur-nace": "RoaringFurnace"}

# Engines newer than zo-allStat_gen.json's keyset (that reference is slightly stale).
# Their to_zod_key output is trusted; listed so unexpected key drift still hard-errors.
NEWER_THAN_REF = {
    "Frostfall Sickle",
    "Neon Fantasies",
    "Serpentine Seeker",
    "Starlight Rider Faceplate",
    "The Simmering Pot",
    # ZZZ 3.1, verified against fairy's w_engines table 2026-07-27.
    "Boisterous Echoes",
    "Chief Sidekick",
    "Joyau Dore",
    "Ode of Resurrected Wings",
    "Sol Exuvia",
    # Named in fairy's 2026-07-28 refresh; shipped as a modifier file on 2026-08-09.
    "Knight's Extolment",
    # ZZZ 3.2, added by fairy's 2026-08-09 roster refresh; see EXTRA_ENGINES.
    "Bloodmarrow Coffer",
    "Catty Luck",
    "Crimson Thirst",
    "[Lunar] Semiluna",
}

# Modifier files are named from whatever fairy's kit curation captured first, which for
# a signature engine can be the pre-release/datamined name.  The scanner matches what the
# English client prints, so the display name is corrected here, keyed by source_id because
# the id is stable across a rename and the name by definition is not.
#
# 14158 shipped as "Ode of Resurrected Wings"; its modifier file still says "Poem of the
# Empty Feather Return".  Same engine — same id, both S/anomaly.
SOURCE_NAME_OVERRIDES = {"14158": "Ode of Resurrected Wings"}

# Engines live in-game that fairy's w_engines table has but has no modifier file for yet.
# The generator reads modifier files, so these are invisible to the scanner until fairy's
# kit curation catches up.  Absent is usually safe — normalize_engine's floor rejects an
# unknown name — but not always: "Ode of Resurrected Wings" fuzzy-matched "Flight of Fancy"
# at 85.5, over the 80 floor, so it was silently exported as the wrong engine.
#
# hakushin_id 14159 was the "..." placeholder when this list was first written; fairy's
# 2026-07-28 refresh resolved it to "Knight's Extolment" (S/attack, Sigrid's signature).
# It scores 53 against the nearest existing engine, well under normalize_engine's 80 floor,
# so before this entry it was dropped as unknown_engine rather than mismatched.
#
# The 2026-08-09 refresh repeats the pattern with five w_engines rows (all LR
# roster_uncovered in fairy's kit validator, so no modifier file for any of them).  Four
# carry real names and are listed below; the fifth, hakushin_id 14162, is still the "..."
# placeholder and is deliberately NOT listed — "..." is not a name the client ever prints,
# and to_zod_key("...") is the empty string, which would poison the table.  Add it here
# once fairy resolves the name, exactly as 14159 was.
#
# Keyed by hakushin_id (fairy's modifier files call the same number source_id), NOT by
# display name, for the same reason SOURCE_NAME_OVERRIDES is: the id is stable across a
# rename and the name by definition is not.  A name-keyed guard cannot fire on the case
# it exists for — fairy shipping the modifier file under a *different* name, as 14158 did
# ("Poem of the Empty Feather Return" -> "Ode of Resurrected Wings") — and would emit both
# spellings under two different ZOD keys with no error.  That matters here: every entry
# below is an UNRELEASED row in fairy's coverage ledger (beta index only), which is exactly
# the population most likely to be renamed at release.
#
# id -> (display name, rarity).  Remove an entry once fairy ships its modifier file; the
# duplicate check below fails loudly if you forget, rather than letting the two sources
# drift.
EXTRA_ENGINES = {
    "12016": ("[Lunar] Semiluna", "B"),
    "13017": ("Catty Luck", "A"),
    "13021": ("Bloodmarrow Coffer", "A"),
    "14161": ("Crimson Thirst", "S"),
}


def main() -> None:
    ref_keys = set(json.loads(ZO_ALLSTAT.read_text())["wengine"].keys())

    # name -> (key, rarity)
    engines: dict[str, tuple[str, str]] = {}
    modifier_ids: dict[str, str] = {}  # source_id -> name, for the EXTRA_ENGINES guard
    for f in sorted(glob.glob(str(W_ENGINES / "*.json"))):
        d = json.loads(Path(f).read_text())
        source_id = str(d.get("source_id"))
        name = SOURCE_NAME_OVERRIDES.get(source_id, d["source_name"])
        rarity = d["rarity"]
        key = KEY_OVERRIDES.get(name, to_zod_key(name))
        if key not in ref_keys and name not in NEWER_THAN_REF:
            raise SystemExit(
                f"ERROR: key {key!r} for {name!r} not in fairy canonical keyset "
                f"and not in NEWER_THAN_REF allowlist. Resolve before generating."
            )
        modifier_ids[source_id] = name
        engines[name] = (key, rarity)

    for source_id, (name, rarity) in EXTRA_ENGINES.items():
        if source_id in modifier_ids:
            shipped = modifier_ids[source_id]
            renamed = "" if shipped == name else f" — it shipped as {shipped!r}, not {name!r}"
            raise SystemExit(
                f"ERROR: hakushin_id {source_id} ({name!r}) is in EXTRA_ENGINES but fairy "
                f"now has a modifier file for it{renamed}. Drop it from EXTRA_ENGINES so "
                f"fairy stays the single source."
            )
        if name in engines:
            raise SystemExit(
                f"ERROR: EXTRA_ENGINES name {name!r} (id {source_id}) collides with a "
                f"modifier-file engine carrying a different id. Resolve before generating."
            )
        key = KEY_OVERRIDES.get(name, to_zod_key(name))
        if key not in ref_keys and name not in NEWER_THAN_REF:
            raise SystemExit(
                f"ERROR: key {key!r} for {name!r} not in fairy canonical keyset "
                f"and not in NEWER_THAN_REF allowlist. Resolve before generating."
            )
        engines[name] = (key, rarity)

    # Group: S, A, B (non-bracket), B (bracket series). Alpha within group.
    groups: dict[str, list[str]] = {"S": [], "A": [], "B": [], "Bb": []}
    for name in sorted(engines, key=str.lower):
        _, rarity = engines[name]
        if rarity == "B":
            groups["Bb" if name.startswith("[") else "B"].append(name)
        else:
            groups[rarity].append(name)

    blocks = [
        ("_comment_s_rank", "--- S-rank (signature / limited / standard gacha) ---", groups["S"]),
        ("_comment_a_rank", "--- A-rank ---", groups["A"]),
        ("_comment_b_rank", "--- B-rank ---", groups["B"]),
        ("_comment_b_rank_series", "--- B-rank bracket series (standard pool) ---", groups["Bb"]),
    ]

    # Hand-format to preserve _comment sentinels + blank-line group separators.
    lines = ["{", '  "_meta": {', '    "game_version": "1.4",']
    lines.append(
        '    "description": "ZZZ W-Engine display names (English PC client) → ZOD key. '
        "GENERATED by tools/gen_engines.py from /root/fairy (source of truth) — do not hand-edit. "
        'Grouped by rarity for readability; grouping has no semantic effect.",'
    )
    lines.append(f'    "last_updated": "{date.today().isoformat()}"')
    lines.append("  },")
    lines.append('  "engines": {')

    body: list[str] = []
    for comment_key, comment_val, names in blocks:
        seg = [f'    "{comment_key}": "{comment_val}",']
        for name in names:
            key = engines[name][0]
            seg.append(f"    {json.dumps(name)}: {json.dumps(key)},")
        body.append("\n".join(seg))
    joined = "\n\n".join(body)
    joined = joined.rstrip(",")  # last entry must not have a trailing comma
    lines.append(joined)
    lines.append("  }")
    lines.append("}")

    OUT.write_text("\n".join(lines) + "\n")

    total = sum(len(g) for g in groups.values())
    print(
        f"Wrote {OUT} — {total} engines "
        f"(S={len(groups['S'])}, A={len(groups['A'])}, "
        f"B={len(groups['B'])}, B-series={len(groups['Bb'])})"
    )


if __name__ == "__main__":
    main()
