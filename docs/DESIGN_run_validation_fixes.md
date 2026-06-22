# DESIGN — Run Validation Fixes

Source: full-inventory run validation (39 agents, discs + engines). Three issues
found. This doc specs the fixes; tasks in `TASKS_run_validation_fixes.md`.

Source of truth for all engine naming/keys: the **`/root/fairy`** database.

---

## Issue 1 — CRITICAL: engine normalizer data gap + key bug (priority)

### Root causes (two, not one)

1. **Coverage gap.** `data/zzz_1.4/engines.json` has 46 real entries; fairy has
   **89**. **47 engines are missing.** The run only *encountered* ~22 of them, but
   the gap is 47 — every un-listed engine fuzzy-snaps to the nearest wrong key
   (`fuzz.WRatio` always returns a best match; there is no floor — see cause 3).

2. **Stale/phantom youkai-only entries.** 4 youkai keys are absent from *both*
   fairy sources (`w_engines/*.json` modifier files **and** the canonical ZOD
   keyset in `references/zo-allStat_gen.json["wengine"]`, 84 keys):
   - `Peacekeeper` → real engine, but fairy's canonical name/key is
     **`Peacekeeper - Specialized` / `PeacekeeperSpecialized`**. This is a
     **reconcile** (rename), not a drop.
   - `Cannibal Grin`, `Door of Limitation`, `Final Curtain` → in **neither** fairy
     source. Treated as **phantom** (not importable downstream — fairy would reject
     the keys). **Drop them.** (Confirm with user; see Open Questions.)

3. **No confidence floor on `normalize_engine`.** Unlike `normalize_agent` (which
   has `_AGENT_NAME_SCORE_MIN = 85`, the H24 "Zhao magnet" fix), `normalize_engine`
   returns the nearest key at any score. Even after the data fix, the *next* patch's
   engines (1.6+) will silently mis-snap. Defense-in-depth: add a floor so unknowns
   emit `unknown_engine` instead of a wrong key.

### Key-spelling bug (found during validation, NOT in the report)

`to_zod_key("Roaring Fur-nace")` → `"RoaringFurNace"`, but fairy's canonical key is
`"RoaringFurnace"` (the hyphen is a stylistic pun; ZOD drops the post-hyphen caps).
**This is the only name where `to_zod_key` diverges from the canonical keyset** — all
other 88 round-trip cleanly (verified against `zo-allStat_gen.json["wengine"]`). A
hand-edited engines.json would silently emit a key fairy rejects on import.

→ **Conclusion: do not hand-edit. Generate engines.json from fairy.**

### Approach: generator script (robust to future patches)

`tools/gen_engines.py`:
- Read `source_name` from every `/root/fairy/.../w_engines/*.json` (89 names).
- `key = to_zod_key(name)`, with an explicit override table `{"Roaring Fur-nace":
  "RoaringFurnace"}`.
- **Validate** each key against `references/zo-allStat_gen.json["wengine"]` (84).
  - In keyset → OK.
  - Not in keyset → must be one of the 5 newest S-engines (Frostfall Sickle, Neon
    Fantasies, Serpentine Seeker, Starlight Rider Faceplate, The Simmering Pot) for
    which zo-allStat is stale. Allow via an explicit `_NEWER_THAN_REF` allowlist;
    anything else not in the keyset is a hard error (catches future key drift).
- Emit `data/zzz_1.4/engines.json` grouped by rarity (S/A/B), preserving the
  `_meta` block and `_comment_*` sentinels the normalizer already strips.
- Re-runnable: when fairy adds an engine, rerun → done. This is the patch workflow.

Two fairy sources, reconciled: **modifier dir = coverage (89, most complete);
zo-allStat keyset = canonical key spelling (84, authoritative on conflict).** Where
they disagree on a key (only `RoaringFurnace`), zo-allStat wins.

---

## Issue 2 — MEDIUM: dim-badge skill levels misread (investigation, don't fix blind)

`_read_skill_badge` Pass-2 (dim fallback, `agent_scanner.py:543`) classifies single
digits 1–9 by **fill-ratio tiers** (`_BADGE_HIGH_FILL`/`_MID_FILL`). The tiers are
miscalibrated: 05/15-badge agents (Billy, Corin, Piper…) read **8**; the `5` fill
lands in the `≥0.70 → 8/9` bucket. Separately, ascension-0 agents read basic=8 /
others=1, suggesting the **basic-attack badge is lit/styled differently** and splits
the read.

This is fragile glyph-shape heuristics — recalibrating thresholds blind risks
regressing the values that currently work (10/12). **Requires labeled badge crops**
from the affected agents before touching thresholds. Scope as investigation:
1. Re-run affected agents with debug badge-crop dump.
2. Measure actual fill ratios for known 5 vs 8 vs 1.
3. Decide: recalibrate tiers, or replace the fill heuristic with per-digit template
   matching. Escalate to a design decision once data is in hand.

(Lower priority than Issue 1: affects skill levels of *unbuilt/low-asc* agents the
user is unlikely to optimize. Confirm priority.)

### Issue 2 — RESOLUTION (Planner, 2026-06-17): template-match rewrite

T3 investigation closed the "recalibrate vs replace" question: **replace** with per-digit
template matching. Full rationale + rejected alternatives in `DECISIONS.md` D1. Summary:

- **Approach:** template-match the **units-digit blob (b1)** by normalized correlation
  against per-digit reference glyphs 0–9. Keep the existing tens-place logic unchanged
  (single blob → 1; b0 narrow → leading "1"; b0 wide+round → "0"-prefix). Only b1
  classification (both the bright-pass `10/12` fill split and the entire dim-pass
  wide/narrow fill-tier block) is replaced.
- **Glyph source:** oracle-labeled blobs (not font — won't pixel-match the pipeline).
- **Binding constraint:** oracle set has **0 nines**, single 4/6. User chose *close the
  gap first* → source 9 + extra 4/6 + high A-rank 13–16 from a **fresh capture** of two
  purpose-built agents, hand-labeled into a `badge_glyphs` reference (T6).
- **Blast radius:** `capture.py` is unchanged; this is a parse-layer change to
  `_read_skill_badge` only. Reuse the blob extraction already in `tools/diag_skill_badges.py`.
- **Fixes:** Bug-A (basic-slot narrow 7→1), Bug-B (03→5), Bug-B2 (06→8), Bug-C
  (A-rank 13/14/15 units collapse) — all four, uniformly, because they are all units-digit
  shape confusions.
- **Defense:** below-floor correlation → low-confidence flagged read (never silent-wrong).
- **Test:** leave-one-agent-out cross-val on oracle + fresh-capture agents as held-out
  set. Tasks T6→T7→T8 in `TASKS_run_validation_fixes.md`.

---

## Issue 3 — LOW: disc low-confidence flags (won't-fix, document)

979 disc substats flagged low-conf, but spot-checks show **values are correct** — the
flags reflect genuine OCR uncertainty on flat-vs-% substats (DEF 10 vs DEF 3.2%),
not wrong data. No data corruption. **No code change.** Optionally document the
flat/% confidence behavior so the flags aren't mistaken for errors. Defer.

---

## Open Questions (for user)

- **Q1 (blocking T1):** Confirm dropping the 3 phantom engines (`Cannibal Grin`,
  `Door of Limitation`, `Final Curtain`) absent from both fairy sources. Recommended:
  drop — they're un-importable. (Peacekeeper is a reconcile, not a question.)
- **Q2:** Issue 1 vs Issue 2 priority/ordering. Recommended: ship Issue 1 first
  (resolves all 42 wrong keys), then investigate Issue 2.

## Testing strategy

- T1: assert generated engines.json has 89 entries (86 after dropping 3 phantoms +
  Peacekeeper reconcile → recount in task); every non-comment key ∈ (zo-allStat ∪
  5-newest allowlist); golden fixtures in `tests/fixtures/golden/` still pass;
  existing `tests/test_wengine_scanner.py` passes.
- T2: golden engine fixtures unchanged (floor must not break known matches — set
  threshold from observed golden scores); a synthetic unknown name returns
  `("", score<floor)` and the scanner emits `unknown_engine`.
