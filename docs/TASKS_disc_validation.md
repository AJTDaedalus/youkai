# TASKS — Disc OCR Correction & Validity Enforcement

See `DESIGN_disc_validation.md` (invariant tables, error taxonomy E1–E5, repair policy).
Source of truth: repo files + June 22 archive at
`/mnt/c/Users/laharre/OneDrive/Documents/youkai/youkai-portable/archive/live_20260622_093014`.
One task at a time; stop and report after each. Append results to `LOG_disc_validation.md`.

Legend: [ ] open · [~] blocked · [x] done

---

## T0 — Branch setup gate [x]

**Done (deviated from plan — see LOG).** User reviewed the pre-existing dirty state on
`dev` and chose to land it as its own commits on `feat/disc-validation` rather than
stashing it. `reference/youkai_export.json` left untracked/untouched per user decision.

**Acceptance:** `git branch --show-current` = `feat/disc-validation` ✓; `git status`
clean apart from the intentionally-untouched `reference/youkai_export.json` ✓.

---

## T1 — Data: `data/zzz_1.4/disc_values.json` [x]

**Files:** new `data/zzz_1.4/disc_values.json`; new `tests/test_disc_rules.py` (data-load part).

**Do:**
1. Encode the DESIGN "Expected-value tables": per-rarity main-stat bases + growth rates +
   max levels; per-rarity substat bases; roll rules (`n0` range per rarity, upgrade cadence 3,
   per-line max rolls). Keys MUST be the ZOD keys already used in `data/zzz_1.4/stats.json`
   (`main_stats_by_slot`, `substats`) — reconcile key-for-key, don't retype from the wiki.
   Include a `_meta` block citing the wiki URL + retrieval date (2026-07-04).
2. TDD: write the loading test first (`load_disc_values()` shape + spot values:
   S `atk` main base 79 growth 0.2; S `crit_dmg_` sub base 4.8; A max level 12; B `n0` {1,2}).

**Acceptance:**
- Every main-stat key in `stats.json:main_stats_by_slot` (all slots) has an entry; every
  substat key in `stats.json:substats` has an entry; test asserts both set-equalities.
- Spot-value tests pass. `ruff check` clean.

---

## T2 — Data: refresh `disc_sets.json` to the live set list [x]

**Files:** `data/zzz_1.4/disc_sets.json`; `tests/test_normalizer.py`.

**Do:**
1. Add the missing sets from the DESIGN set list (Wuthering Salon, Assassin's Ballad,
   Doom Grindcore, Ecstatic Punk, Mammoth Electro, Monsoon Funk, Noisy Pop, The Sky Ablaze,
   Twisted Grindcore, Unicorn Electro, Vagabond Folk, …) — display name → `to_zod_key(name)`.
2. Cross-check each *new* name against the wiki "Removed" (beta) category before adding;
   removed sets stay out. Record which (if any) were excluded in the LOG.
3. Tests: `normalize_disc_set("Wuthering Salon [2]")` → `("WutheringSalon", ≥95)`;
   existing 26 keys unchanged (regression assert on the full old keyset).

**Acceptance:** tests pass; every June-22 title in the re-OCR sweep (see DESIGN Findings)
matches some set at ≥80 once this lands.

---

## T3 — Normalizer: unknown-set score floor [x]

**Files:** `src/youkai_ocr/normalizer.py`, `src/youkai_ocr/disc_scanner.py`,
`tests/test_normalizer.py`, `tests/test_disc_scanner.py`.

**Do:**
1. Add `_SET_NAME_SCORE_MIN = 60` to `normalize_disc_set` mirroring
   `normalize_engine`: below floor → `("", score)`. (60, not 80: legit 2-line
   "Bunny in Wonderland" titles score 68–73; foreign unknown sets ≤ 46 — see DESIGN E1.)
2. In `_extract_disc` / `scan_equipped_disc_frame`, empty set key → critical fail with
   reason `unknown_set:score:title=…` (the existing `low_set_conf` path already handles
   most of this — verify the floor path reaches it and the reason string distinguishes them).
3. Tests: a fake unknown title ("Future Set Name [1]") → critical fail, NOT nearest-key snap;
   "Wonderland" (partial 2-line title) still resolves to `BunnyInWonderland`.
   Re-verify the floor: golden legit titles must all clear it (record min observed in LOG).

**Acceptance:** tests pass; golden replay still passes; no legit set drops below floor.

---

## T4 — Extractor: capture roll-count suffix (+N) as evidence [x]

**Files:** `src/youkai_ocr/normalizer.py`, `src/youkai_ocr/disc_scanner.py`,
`tests/test_normalizer.py`.

**Do:**
1. New `parse_roll_suffix(text) -> Optional[int]` in normalizer (extract `+N` that
   `_UPGRADE_RE` currently throws away; tolerate OCR noise like `+l`→+1 only if cheap).
2. In `_extract_disc` substat loop and `_equip_parse_stat_block`, capture the suffix per
   line into the new `Evidence` structure (T6 defines it; for now return alongside conf —
   keep the diff small, a local dataclass or dict is fine until T6 wires it).

**Acceptance:** unit tests: `"DEF +2"` → 2, `"CRIT Rate"` → None, `"Anomaly Proficiency +1"` → 1;
`_extract_disc` on a golden panel with `+2` line yields that evidence.

---

## T5 — Extractor: read the main-stat value [x]

**Files:** `src/youkai_ocr/disc_scanner.py`, `tests/test_disc_scanner.py`.

**Do:**
1. Read `_MAIN_VAL_REL` (bbox already defined, currently unused) with the same dual-scale
   read used for substat values; `parse_numeric` + `%`-seen flag → evidence.
2. Same for the equip path (block parse already yields the main value text — stop
   discarding it).
3. Archive the crop (`main_val.png`) alongside the existing per-disc crops.

**Acceptance:** golden panels produce main values matching hand-read ground truth
(disc_0001 → 316; disc_0631 → 142); no regression in golden replay.

---

## T6 — `disc_rules.py`: validator (pure, TDD) [x]

**Files:** new `src/youkai_ocr/disc_rules.py`; `tests/test_disc_rules.py`.

**Do:** implement per DESIGN Architecture:
`Evidence`, `Violation`, `expected_main_value`, `substat_base`, `validate_disc`.
Checks (each a named violation code):
- `level_range` (0..max_level[rarity]); `slot_range`; `rarity_range`.
- `main_key_slot` (key legal for slot per stats.json).
- `main_value_mismatch` (evidence main value ≠ expected(rarity, key, level), int-floor for
  flats / 1-dp for percents; skip when no evidence).
- `sub_not_on_lattice` (value/base not integer within 0.02 rel tolerance).
- `sub_rolls_exceed_max` (k > 1 + floor(level/3), and per-line rarity cap).
- `roll_budget` (Σk − u ∉ n0 range for rarity) — only when all lines on-lattice.
- `sub_count` (visible count vs min(4, n0+u) range).
- `dup_substat`; `sub_equals_main` (severity=warning until confirmed, see DESIGN OQ3).
Write the test table FIRST from DESIGN examples (all E1–E5 real cases + clean discs
lvl 0/3/4/15 of each rarity).

**Acceptance:** all table tests pass; module imports nothing from OCR/capture layers;
100% branch coverage on `validate_disc` (it's the product's integrity gate).

---

## T7 — `disc_rules.py`: conservative repair (TDD) [x]

**Files:** `src/youkai_ocr/disc_rules.py`; `tests/test_disc_rules.py`.

**Do:** `repair_disc` per DESIGN Repair policy (precedence: roll-suffix → unique lattice
neighbor → roll-budget forcing → flag-only). Joint flat/percent + lattice resolution (E3).
Required test cases (real June 22 data):
- `crit_dmg_ 4.4` (+0 suffix) → 4.8, rule 1.
- `crit_dmg_ 9.2` (+1) → 9.6, rule 1.
- `def 44.0` with `+2` suffix and `pct_seen` → `def_ 14.4`, rules 1+joint-key.
- `def 44.0`, no suffix evidence → two lattice neighbors (def 45 k3 / def_ 14.4 k3) →
  budget-forcing or flag; assert NEVER silently picks without a discriminator.
- `pen 0.0` → flag-only (`value_unreadable`), never invented.
- Already-valid disc → zero repairs (idempotence over the whole golden clean set).

**Acceptance:** table tests pass; every repair emits a record {field, before, after, rule};
no repair path can fire on ambiguous input (asserted).

---

## T8 — Golden fixtures from the June 22 archive [x]

**Files:** `tests/fixtures/golden/` (new panels + labels.json entries), maybe
`tools/curate_golden.py` helper.

**Do:**
1. Copy ~30 `panel.png`s from the archive into fixtures: every error-class exemplar
   named in DESIGN Findings (disc_0001, disc_0631, a `Wuthering Salon` title, a `pen 0.0`,
   a dup-substat, a sub-equals-main case, …) + clean discs covering rarity×level tiers.
2. Hand-label ground truth by READING THE PANEL IMAGE (not the old discs.json!). Record
   each label's provenance. While labeling, resolve DESIGN OQ3 (sub-equals-main) from the
   7 flagged discs' panels and update DESIGN + T6 severity accordingly.
3. Extend `test_golden_replay.py`: post-repair numeric gate ≥98%, zero silent-wrong
   (wrong exported value ⇒ conf < 70 or violation present).

**Acceptance:** golden replay green with the new gate; labels.json review-clean.

---

## T9 — Wire validator+repair into scan and export paths [x]

**Files:** `src/youkai_ocr/disc_scanner.py`, `src/youkai_ocr/cli.py`,
`tests/test_disc_scanner.py`, `tests/test_cli_scan_all.py`.

**Do:**
1. `_extract_disc` + `scan_equipped_disc_frame`: build `Evidence`, run `repair_disc`,
   fold residual violations into `conf`/issues (violation ⇒ conf ≤ 30 on that field);
   applied repairs annotate the issues entry (`repairs: [...]`).
2. Ensure `youkai_export.issues.json` (or the existing issues emission path in cli.py)
   carries violations + repairs for every affected disc.
3. Tests: end-to-end `scan_single_frame` on golden bad panels yields repaired discs +
   issue records.

**Acceptance:** full test suite green; issues output shows before/after for repairs.

---

## T10 — `revalidate` CLI: fix the June 22 export offline [x]

**Files:** `src/youkai_ocr/cli.py` (new subcommand), `tests/test_cli_revalidate.py`.

**Do:**
1. `youkai-ocr revalidate --archive <dir> --out <export.json> [--report <report.json>]`:
   for each `disc_NNNN/panel.png` run `scan_single_frame` (identity calibration — panels
   are 439×770 reference-scale crops; reuse `_panel_to_frame` trick from golden replay),
   with updated tables + validator + repair. Preserve `location`/`lock` by merging from the
   run's `discs.json` on matching index (panel crops don't show lock; lock came from the
   thumbnail strip).
2. Report: per-disc violations, repairs, unrepairable list, summary counts.
3. Run it on the June 22 archive. Expected outcome: ~171 invariant-violating discs → the
   large majority auto-repaired (rules 1–2); Wuthering Salon discs get their true set key;
   remainder listed for manual review. Deliver corrected export to
   `youkai-portable/youkai-portable/export/` (alongside, NOT overwriting — suffix
   `_revalidated`) and paste summary counts into the LOG.

**Acceptance:** command runs archive-only (no game, no pynput); corrected export passes
`validate_disc` for every disc except explicitly-reported unrepairables; summary in LOG.

---

## T12 — OCR evidence-reliability fixes from T10's manual review [x]

**Added 2026-07-04 by escalation triage (see LOG "ESCALATION — three new bugs").
Sequenced before T11: the wrap-up PR should ship with these 43 discs fixed, not
documented as indefinite manual-review debt.**

**Files:** `src/youkai_ocr/normalizer.py`, `src/youkai_ocr/disc_scanner.py`,
`tests/test_normalizer.py`, `tests/test_disc_scanner.py`,
`tests/fixtures/golden/` (disc_1242, disc_2070 panels + labels).

**Do:**
1. `parse_roll_suffix`: single-digit `+N` at a whitespace/end boundary instead of
   end-of-string — wide values ("14.4%") straddle the substat name/value bbox split
   and bleed their leading digit into the name crop (`"DEF +2 1"`), which the end
   anchor silently rejected (Cluster 1, 38 discs). Merged bleed (`"+21"`) → None.
2. `normalize_main_stat` / `normalize_substat`: empty-query guard → `("", 0.0)` —
   rapidfuzz scores every candidate 0 for `""` and returns the first arbitrarily
   (Cluster 3a; agents/engines/sets are already safe behind score floors).
3. `_extract_disc` main-name read: dim-pass + 2× fallback ladder (mirrors substat
   rows); fallback-sourced keys conf-capped at 65 (disc_0576/0618 "Wind DMG Bonus").
4. `_extract_disc` slot trust order: clean-bracket title > panel slot widget (G5) >
   garble-tolerant title fallback (disc_2070 "[1]" misread as "[ 4" → slot 4 →
   wrong main-stat table). New `parse_slot(..., allow_garbled=False)` tier.
5. `_extract_disc` title read: dim-pass retry when the bright read scores below the
   set floor (disc_1242/1243 "Dawn's Bloom" → `'v Gi s Bloom'` critical_fail);
   adopted dim reads conf-capped at 65.
6. Re-run `revalidate` over the full June 22 archive; record before/after counts.

**Acceptance:** suite green incl. new golden fixtures; disc_0001/0011/0293 repair
via rule 1 (roll_suffix) through the real call path; full-archive revalidate shows
Cluster 1 + Cluster 3 discs leaving the unrepairable/critical_fail buckets (results
in LOG T12 entry).

---

## T13 — Failed discs excluded from export, report-only [x]

**Added 2026-07-04 by user decision:** *"failed discs excluded from export,
users get a failure report to review."* Previously failed discs shipped in the
export with known-wrong values (revalidate's critical_fail path even passed the
old uncorrected discs.json entry through).

**Files:** `src/youkai_ocr/disc_scanner.py`, `src/youkai_ocr/cli.py`,
`tests/test_disc_scanner.py`, `tests/test_cli_revalidate.py`.

**Do:**
1. `_repair_and_fold_violations` stashes residual violations in
   `conf["_violations"]`; `scan_discs` excludes discs with error-severity
   residuals and emits `failed_validation` issues (disc + violations + repairs).
2. `revalidate`: unrepairable/critical_fail/missing_panel excluded from export;
   report entries carry `excluded_from_export` + disc payload; report always
   written (default `<out stem>.report.json`); summary gains exported/excluded.
3. `scan --file`: exit 1 with violations printed instead of exporting.
4. review.txt: "FAILED DISCS — EXCLUDED from export" section.

**Acceptance:** suite green (667); delivered June 22 export regenerated at 2075
discs with failure report alongside. **Follow-up noted:** equipped-orphan discs
appended by reconciliation bypass the gate (conf discarded in `scan_agents`).

---

## T11 — Docs + wrap-up [ ]

**Do:** update `DESIGN_disc_validation.md` status + resolved OQs; final LOG entry with the
before/after error counts; `README.md`/`RUNBOOK.md` note for `revalidate`; run full
`pytest` + `ruff check`; prepare PR `feat/disc-validation` → `dev` with the summary.

**Acceptance:** suite green, lint clean, PR body includes the June 22 repair statistics.
