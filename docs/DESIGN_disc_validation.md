# DESIGN — Disc OCR Correction & Validity Enforcement (`disc_validation`)

**Status**: Planned (2026-07-04). Investigation complete; tasks in `docs/TASKS_disc_validation.md`.
**Tier**: Planned by Fable (Brain) at user request; execute with Worker (Sonnet). Escalate per the standard protocol.

## Branch policy

- All work on **`feat/disc-validation`**, branched from `dev`.
- **No direct commits to `dev` or `main`.** Merge back via PR after review.
- ⚠️ `dev` currently has uncommitted modifications (`agent_scanner.py`, `grid.py`, `wengine_scanner.py`, `tests/test_agent_traversal.py`, untracked `reference/youkai_export.json`). **Task 0 must stash or otherwise exclude these** — they belong to other work; do not bundle them into this feature.
- Task 0 of the TASKS file is the branch-setup gate.

## Problem statement

The June 22 scan (`youkai-portable/archive/live_20260622_093014`, 2090 discs, Windows host path
`C:\Users\laharre\OneDrive\Documents\youkai\youkai-portable\archive\live_20260622_093014`)
produced an export with wrong disc values that corrupt downstream consumers (fairy optimizer).
Frame of reference: the archived per-disc crops (`disc_NNNN/{panel,title,rarity,level,main_name}.png`)
plus `discs.json` from the same run, and the export at
`youkai-portable/youkai-portable/export/youkai_export.json` (Jun 22 12:52).

ZZZ Drive Disc values are **fully lattice-constrained** (source:
https://zenless-zone-zero.fandom.com/wiki/Drive_Disc): every legal disc satisfies exact
arithmetic invariants (§ Expected-value tables). The OCR pipeline currently checks only
loose per-stat ranges (`_SUBSTAT_RANGE` in `disc_scanner.py`), so single-digit misreads
that stay in range are exported silently. We will (a) correct the systematic OCR errors,
(b) add a validator that proves every exported disc is a *possible* disc, (c) add a
conservative auto-repair layer that snaps unambiguous misreads onto the lattice, and
(d) provide an offline tool to re-derive a corrected June 22 export from the archive.

## Findings from the June 22 run (measured, not hypothesized)

Invariant sweep over `discs.json` (2090 discs): **171 discs (8.2%) violate at least one
invariant.** Breakdown by class:

| # | Class | Count | Example (real, from run) | Root cause |
|---|-------|-------|--------------------------|------------|
| E1 | Stale set table → silent wrong `setKey` | **~173 discs** | disc_0001 panel shows **"Wuthering Salon [2]"**, exported as `SwingJazz` | `data/zzz_1.4/disc_sets.json` has 26 sets; live game has ~37. `normalize_disc_set()` has **no score floor** (unlike agents ≥85 / engines ≥80), so unknown sets snap to the nearest key above the critical threshold (30). |
| E2 | Substat value digit misread | 175 value violations | `crit_dmg_ 4.4` (true 4.8 — "8"→"4"); `crit_dmg_ 9.2` (true 9.6 — "6"→"2"); `def 44.0` (true `def_ 14.4%` — leading "1" + "." + "%" all lost) | Tesseract confuses 8/4 and 6/2 at *both* voting scales, so the dual-scale vote in `_extract_disc` agrees on the same wrong read. |
| E3 | Flat/percent key flip compounding E2 | subset of E2 | `DEF +2 14.4%` → `def 44.0`: OCR read "44%", the percent upgrade was rejected because 44 > `def_` upper bound (38.4), so the *flat* key was kept with the wrong value | `_value_plausible` arbitration assumes the value is right when deciding the key. |
| E4 | Substat duplicates main stat | 7 | slot-1 (main flat HP) disc listing an `hp` substat | No cross-field check exists. Likely OCR key error; verify per-disc against `panel.png` during fixture curation. |
| E5 | Dup substat keys / zero values / roll-budget violations | 4 dup, ~6 rolls>max, 2 roll-budget, 1 count | `pen 0.0` (unreadable row exported as 0.0) | Unreadable rows are exported with `value=0.0` at conf 30 — flagged in issues but still poison the export. |

Levels are **not** a problem: the game zero-pads ("Lv. 04/15") and the 111 level-4 discs
were verified genuine (disc_0631 panel: `Lv. 04/15`, main ATK 142 = floor(79 × 1.8) ✓).

### E1 quantification (offline re-OCR sweep of all 2090 archived `title.png` crops, 2026-07-04)

Full sweep results archived at `docs/diag_title_reocr_20260704.json`. Titles whose best
fuzzy match scored < 80 against the current 26-set table, clustered:

| True set (read from crops) | Discs | Exported as (score) |
|---|---|---|
| **Wuthering Salon** | 105 | `SwingJazz` (45) ×91, `WhiteWaterBallad` (46) ×14 |
| **The Sky Ablaze** | 68 | `BranchBladeSong` (38–43) ×46, `ThunderMetal` (40) ×22 |
| Bunny in Wonderland (2-line title, only "Wonderland" OCR'd) | 44 | ✔ correct match — but at score **68–73** |
| Shockstar Disco (one dropped char) | 2 | ✔ correct at 78 |

So ~8% of `SwingJazz` inventory is really Wuthering Salon (91 of 204), and nearly half the
apparent BranchBladeSong surplus is The Sky Ablaze. **Floor calibration**: foreign
(unknown-set) matches top out at **46**; legitimate-but-partial titles bottom out at
**68**. The unknown-set floor therefore goes at **60** (not 80 as engines use) — task T3.

Two currently-discarded signals make most of this correctable:

1. **Roll-count suffix**: every upgraded substat displays `+N` after its name
   (e.g. `DEF +2  14.4%`). `normalizer._UPGRADE_RE` strips it. `+N` ⇒ value = base × (N+1),
   which *deterministically* resolves E2/E3 when readable.
2. **Main stat value**: displayed on every panel; the crop bbox `_MAIN_VAL_REL` exists in
   `disc_scanner.py` but is **never read**. Main value = f(rarity, main key, level) exactly,
   giving a strong cross-check on level, rarity, and main-key, and an anchor for slot-4/5/6
   key disambiguation.

## Expected-value tables (from the wiki, cross-checked against archive screenshots)

### Main stats — value(level) = base × (1 + growth × level), displayed floored (ints) / 1-dp (percents)

Verified against archive: S-rank ATK lvl4 → floor(79 × 1.8) = 142 ✓ (disc_0631); lvl15 → 316 ✓ (disc_0001).

| Rarity | max level | growth/level | max multiplier |
|--------|-----------|--------------|----------------|
| S (rarity=4) | 15 | 0.20 × base | 4.0× |
| A (rarity=3) | 12 | 0.25 × base | 4.0× |
| B (rarity=2) | 9  | **unverified** (wiki gap; assume 1/3 × base → 4.0×) | ~4.0× |

Base (level-0) values:

| Main stat (ZOD key) | Slots | B base | A base | S base | S max (lv15) |
|---------------------|-------|--------|--------|--------|--------------|
| `hp` (flat) | 1 | 183 | 367 | 550 | 2200 |
| `atk` (flat) | 2 | 26 | 53 | 79 | 316 |
| `def` (flat) | 3 | 15 | 31 | 46 | 184 |
| `hp_` | 4,5,6 | 2.5 | 5 | 7.5 | 30 |
| `atk_` | 4,5,6 | 2.5 | 5 | 7.5 | 30 |
| `def_` | 4,5,6 | 4 | 8 | 12 | 48 |
| `crit_` | 4 | 2 | 4 | 6 | 24 |
| `crit_dmg_` | 4 | 4 | 8 | 12 | 48 |
| `anomProf` | 4 | 8 | 15 | 23 | 92 |
| `pen_` (PEN Ratio) | 5 | 2 | 4 | 6 | 24 |
| element DMG (`fire_dmg_` etc.) | 5 | 2.5 | 5 | 7.5 | 30 |
| `anomMas_` (Anomaly Mastery %) | 6 | 2.5 | 5 | 7.5 | 30 |
| `impact_` | 6 | 1.5 | 3 | 4.5 | 18 |
| `enerRegen_` | 6 | 5 | 10 | 15 | 60 |

(Use the ZOD keys already present in `data/zzz_1.4/stats.json` `main_stats_by_slot`; the
table above must be reconciled key-for-key against that file in Task 1, not retyped blind.)

### Substats — value = base × k, k = 1 + upgrades on that line (integer)

| Substat (ZOD key) | B base | A base | S base | S max (6 rolls) |
|--------------------|--------|--------|--------|-----------------|
| `hp` | 39 | 75 | 112 | 672 |
| `atk` | 7 | 13 | 19 | 114 |
| `def` | 5 | 10 | 15 | 90 |
| `hp_` | 1 | 2 | 3 | 18 |
| `atk_` | 1 | 2 | 3 | 18 |
| `def_` | 1.6 | 3.2 | 4.8 | 28.8 |
| `crit_` | 0.8 | 1.6 | 2.4 | 14.4 |
| `crit_dmg_` | 1.6 | 3.2 | 4.8 | 28.8 |
| `anomProf` | 3 | 6 | 9 | 54 |
| `pen` (flat) | 3 | 6 | 9 | 54 |

### Roll-budget rules

For a disc of rarity r at level L:

- `u = floor(L / 3)` upgrade events (levels 3, 6, 9, 12, 15 as allowed by max level).
- Initial substat count `n0`: S ∈ {3,4}, A ∈ {2,3}, B ∈ {1,2}.
- Each event **adds a new substat if count < 4, else upgrades an existing one** (+1 roll).
- Therefore: `visible_count = min(4, n0 + u)`; `Σ k_i = n0 + u`;
  each `k_i ∈ [1, 1 + u]`; per-line max rolls: S 6, A 4, B 2.
- Corollary used as the primary integrity check: `Σ k_i − u ∈ {3,4}` (S-rank),
  where `k_i = value_i / base_i` must each be a near-exact integer.

### Disc sets

Live set list (wiki category, July 2026, 37 entries — Task 2 filters out removed beta sets
by cross-checking each against the wiki "Removed" category before adding):
Assassin's Ballad, Astral Voice, Branch & Blade Song, Bunny in Wonderland, Chaos Jazz,
Chaotic Metal, Dawn's Bloom, Doom Grindcore, Ecstatic Punk, Fanged Metal, Freedom Blues,
Hormone Punk, Inferno Metal, King of the Summit, Mammoth Electro, Monsoon Funk,
Moonlight Lullaby, Noisy Pop, Notes From the Chained, Phaethon's Melody, Polar Metal,
Proto Punk, Puffer Electro, Shadow Harmony, Shining Aria, Shockstar Disco, Soul Rock,
Swing Jazz, The Sky Ablaze, Thunder Metal, Twisted Grindcore, Unicorn Electro,
Vagabond Folk, White Water Ballad, Woodpecker Electro, **Wuthering Salon**, Yunkui Tales.

## Architecture

New module `src/youkai_ocr/disc_rules.py` — pure functions, no OCR imports, fully unit-testable:

```
load_disc_values() -> DiscValues            # from data/zzz_1.4/disc_values.json
expected_main_value(rarity, key, level) -> float
substat_base(rarity, key) -> float
validate_disc(disc: ZodDisc, evidence: Evidence | None) -> list[Violation]
repair_disc(disc: ZodDisc, evidence: Evidence | None) -> RepairResult
```

`Evidence` is a small dataclass of raw OCR observations the extractor already has but
throws away: per-substat `(raw_name_text, raw_value_texts, roll_suffix, pct_seen)`, plus
`main_value_raw`. `Violation` carries `{field, code, observed, expected, severity}`.
`RepairResult` carries the (possibly) corrected disc, a list of applied repairs, and a
list of residual violations (unrepairable → issues file).

### Repair policy (conservative — never guess)

A substat value is snapped to `base × k` only when at least one of, in precedence order:

1. **Roll suffix agrees**: OCR read `+N` and `base × (N+1)` is within digit-edit distance
   of the observed value (e.g. observed 4.4, `+0` implied k=1 → 4.8 ✓).
2. **Unique lattice neighbor**: exactly one legal `k ∈ [1, 1+u]` whose value matches the
   observed digits up to one digit-substitution / decimal-point loss / dropped leading "1"
   (44 → {45=def×3, 14.4=def_×3} is *two* neighbors → not unique → escalate to rule 3).
3. **Roll-budget forcing**: after rules 1–2, if exactly one assignment of the remaining
   line makes `Σk − u ∈ {3,4}` hold, take it.
4. Otherwise: leave the value, emit a `Violation(severity=error)` into issues. **Never**
   export a silent guess.

Flat/percent key choice is made *jointly* with the lattice snap (E3 fix): candidate set is
`{(flat_key, k), (pct_key, k)}` and the winner must satisfy both the lattice and the
plausibility range; `pct_seen` breaks ties, main-stat-collision (E4) disqualifies a candidate.

### Integration points

1. `_extract_disc` (`disc_scanner.py`): capture roll suffix before `_UPGRADE_RE` strips it;
   read `_MAIN_VAL_REL` (dual-scale, like substats); build `Evidence`; call
   `repair_disc`; merge violations into the existing `conf`/issues flow.
2. `scan_equipped_disc_frame`: same treatment (block-parse already yields `+N` in names).
3. `normalize_disc_set`: add `_SET_NAME_SCORE_MIN = 60` floor (calibrated from the E1
   sweep: foreign names ≤ 46, legit partial titles ≥ 68). Below floor → `("", score)` →
   existing critical-fail path (`unknown_set`), not a snap.
4. Export: unchanged ZOD schema. Repairs logged in `youkai_export.issues.json` with
   before/after and rule used.
5. New CLI subcommand `revalidate`: replays an archive dir (`disc_NNNN/panel.png` →
   `scan_single_frame`) offline with the updated tables + validator + repair, and writes a
   corrected export + repair report. This is how the June 22 export gets fixed without
   rescanning the game.

## Testing strategy

- **TDD throughout** — rules module is pure; write table-driven tests from this doc first.
- Unit: every invariant, every repair rule, every real failure case from Findings
  (disc_0001 `def 44.0`→`def_ 14.4`; `crit_dmg_ 4.4`→4.8; `9.2`→9.6; `pen 0.0`→flag-only;
  Wuthering Salon → unknown-set before Task 2, → `WutheringSalon` after).
- Golden replay: extend `tests/fixtures/golden` with ~30 hand-labeled panels curated from
  the June 22 archive covering every error class + clean discs of each rarity/level tier;
  gate: ≥98% numeric accuracy **after repair**, zero silent-wrong (wrong value ⇒ conf < 70
  or violation emitted).
- Full-archive sweep as an integration smoke: `revalidate` over all 2090 archived panels
  must end with 0 invariant violations surviving un-flagged.

## Downstream robustness

- Tables live in data JSON (versioned like the rest of `data/zzz_1.4/`), not code, so the
  next patch's new sets/stats are data-only updates. Unknown set names **fail loudly**
  (issues) instead of snapping — the Wuthering Salon failure mode cannot recur silently.
- Validator is schema-level (ZOD in, violations out) so fairy can reuse the same rules
  server-side on import if desired.

## Open questions (non-blocking; noted for Planner/user)

1. B-rank main-stat growth is unverified on the wiki (1 B-rank disc in inventory —
   validate loosely, flag rather than fail).
2. Element DMG % substat does not exist (mains only) — confirmed by wiki substat table.
3. Whether a substat can ever equal the main stat: assumed **no** (7 observed cases all
   look like OCR errors); fixture curation (Task 8) must confirm from `panel.png` before
   the check ships as `severity=error`; if a counterexample appears, downgrade to warning.
4. ~~Set-name score floor value~~ **Resolved**: 60, from the E1 sweep (foreign ≤46,
   legit partial ≥68). Re-verify in T3 against golden data after the new sets land.
