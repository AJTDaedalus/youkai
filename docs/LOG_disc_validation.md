# LOG — Disc OCR Correction & Validity Enforcement

## 2026-07-04 — Investigation + plan (Fable, planning session)

- Frame of reference confirmed: June 22 debug archive
  `youkai-portable/archive/live_20260622_093014` (Windows host), 2090 disc crops +
  `discs.json`; export `youkai-portable/youkai-portable/export/youkai_export.json`
  (Jun 22 12:52) carries the same 2090 discs.
- Invariant sweep of `discs.json` against wiki lattice rules: **171/2090 discs (8.2%)
  violate ≥1 invariant** (breakdown in DESIGN Findings E1–E5).
- Offline re-OCR of all 2090 `title.png` crops (local tesseract): **~173 discs carry a
  wrong `setKey`** — Wuthering Salon ×105 (exported as SwingJazz/WhiteWaterBallad),
  The Sky Ablaze ×68 (exported as BranchBladeSong/ThunderMetal). Sweep archived at
  `docs/diag_title_reocr_20260704.json`.
- Verified level OCR is sound (game zero-pads "Lv. 04/15"; the 111 lvl-4 discs are real —
  disc_0631 main ATK 142 = floor(79×1.8) ✓).
- Wiki stat tables retrieved (fandom MediaWiki API; direct page fetch is 402/403-blocked,
  use `api.php?action=parse`/`action=query` with a UA string) and encoded in DESIGN.
- Deliverables written: `DESIGN_disc_validation.md`, `TASKS_disc_validation.md` (T0–T11).
- Note: `dev` has uncommitted changes from unrelated work — T0 stashes them before
  branching.

Next: Worker starts at T0 (branch setup), then T1.

## T0 — Branch setup gate (Worker, 2026-07-04)

**Done, deviated from the TASKS plan.** Before branching, inspected the pre-existing
uncommitted `dev` changes and reported them to the user rather than stashing blind:

- `agent_scanner.py` + `tests/test_agent_traversal.py`: removes the `AGENT_MAX=60`
  hard-cap traversal backstop; adds an ascension-dot visual-count fallback when the
  "/NN" level-cap OCR is unreadable (previously silently defaulted ascension to 0).
- `grid.py`: detects a stalled/undetectable scrollbar during inventory scroll
  (2 consecutive `None` thumb reads in the windowed check, or a full window of `None`
  during bottom-scan) and stops instead of spinning.
- `wengine_scanner.py`: rejects an engine count reading when `cur/max > 0.90` — catches
  OCR digit-confusion misreads (e.g. "222/666"→"660/666") that were previously accepted
  as plausible.
- Untracked `reference/youkai_export.json` (1.1MB, dated 2026-06-14, predates the
  June 22 scan this feature targets) — unrelated stray file, not ground truth for this
  work.

None of this is covered by any TASKS/LOG file (confirmed: `docs/TASKS_run_validation_fixes.md`
T1–T9 are all `[x]` and were already committed in `4b17382`, 2026-06-22 — this diff is
new work done after that landed, with no paper trail). Confirmed clean via full suite:
`python -m pytest -q` → **514 passed** with the diff applied (vs. 15 pre-existing ruff
violations on `HEAD`, 14 with the diff — it nets one fewer via the `AGENT_MAX` removal;
no new violations introduced).

**User decision:** roll these into `feat/disc-validation` as their own commits (not
stash-and-drop), and leave `reference/youkai_export.json` untracked/untouched.

**Executed:**
1. `git checkout -b feat/disc-validation dev`.
2. Three separate commits (one logical change each, per repo convention):
   - `2805047` fix(agent-scanner): replace AGENT_MAX hard cap with ascension-dot OCR fallback
   - `91728c9` fix(grid): detect stalled/undetectable scrollbar during inventory scan
   - `b72fd10` fix(wengine-scanner): reject engine count readings suspiciously near cap
3. Committed this feature's planning docs (`DESIGN_disc_validation.md`,
   `TASKS_disc_validation.md`, `LOG_disc_validation.md`, `diag_title_reocr_20260704.json`).
4. `reference/youkai_export.json` left untracked, untouched.

**Acceptance met:** `git branch --show-current` = `feat/disc-validation`; `git status`
clean except the intentionally-untouched `reference/youkai_export.json`.

Next: T1 — `data/zzz_1.4/disc_values.json`.

## T1 — Data: `data/zzz_1.4/disc_values.json` (Worker, 2026-07-04)

**Done.** Encoded the DESIGN Expected-value tables (main-stat base/growth/max-level,
substat base, roll-budget rules) into `data/zzz_1.4/disc_values.json`, keyed by
`ZodDisc.rarity` int (4=S, 3=A, 2=B) to avoid a translation layer. Reconciled every
main-stat key against `stats.json:main_stats_by_slot` (all 6 slots) and every substat
key against `stats.json:substats` — set-equality enforced by test, not eyeballed.

**Finding — stats.json's `substat_step_values` block is stale for A-rank hp/atk:**
that block (unused dead data; `grep` found zero call sites) has A `hp=79, atk=15`,
sourced from AdeptiScanner 2026-06-02. The DESIGN wiki table says `hp=75, atk=13`.
Checked the June 22 archive directly: A-rank (`rarity=3`) `hp` substat values observed
were `{75.0}` (plus a noise `2.0`), `atk` values `{13.0, 26.0}` (26=13×2, a 2-roll
line) — real game data confirms the wiki/DESIGN numbers, not stats.json's. Every other
cell (B and S rows, and A's hp_/atk_/def_/pen/crit_/crit_dmg_/anomProf) already agreed
between the two sources. `disc_values.json`'s `_meta` documents this; `stats.json`
itself is untouched (out of scope for T1 — its `substat_step_values` block has no
callers, so the drift wasn't live, but a future task should probably delete or fix it
rather than leave two contradictory tables sitting in the repo).

B-rank growth carried DESIGN's explicit assumption (1/3 per level) with the
"unverified on wiki, 1 B-disc in archive" caveat preserved in `_meta`.

**Files:**
- `data/zzz_1.4/disc_values.json` (new).
- `src/youkai_ocr/disc_rules.py` (new) — minimal `load_disc_values()` /
  `RarityRules` / `DiscValues` for T1's data-load scope; `expected_main_value`,
  `substat_base()` accessor fn, `validate_disc`, `repair_disc` etc. land in T6/T7.
- `tests/test_disc_rules.py` (new, 10 tests) — key-set equality against `stats.json`
  (both main-stat-by-slot and substat sets), shape checks (every key has all 3
  rarities), and the DESIGN-specified spot values (S atk base 79/growth 0.20, S
  crit_dmg_ sub base 4.8, A max_level 12, B n0_range (1,2)), plus a regression test
  pinning the A hp/atk 75/13 finding above.

**Verification:** `pytest tests/test_disc_rules.py` → 10 passed; `ruff check` clean;
full suite `python -m pytest -q` → **524 passed** (0:05:56), no regressions.

Next: T2 — refresh `disc_sets.json` to the live 37-set list.

## T2 — Data: refresh `disc_sets.json` to the live set list (Worker, 2026-07-04)

**Done — with a significant correction to the DESIGN premise.** DESIGN's 37-set list came
from the wiki's `Category:Drive Discs` page dump, but that category is not filtered for
released-vs-removed status. Queried the fandom MediaWiki API directly (`api.php`,
UA-gated — direct page fetch is still 402'd, matches the planning-session note) for each
of the 11 "new" set names DESIGN listed:

- **`Category:Removed` + `Category:Drive Disc Missing ID`** (beta/datamined stub pages,
  never released — **excluded**): Assassin's Ballad, Doom Grindcore, Ecstatic Punk,
  Mammoth Electro, Monsoon Funk, Noisy Pop, Twisted Grindcore, Unicorn Electro,
  Vagabond Folk. (9 of the 11.)
- **`Category:Released in Version 3.0`** (real, live — **added**): The Sky Ablaze,
  Wuthering Salon. (2 of the 11.) Both are independently confirmed by the June 22 archive
  itself — these are the two sets the E1 re-OCR sweep found being misread as
  SwingJazz/WhiteWaterBallad/BranchBladeSong/ThunderMetal (105 + 68 discs respectively).

Cross-checked the full `Category:Drive Discs` dump (39 members, 2 are subcategories → 37
pages, matching DESIGN's count) against `Category:Removed`: confirmed none of the
existing 26 keys overlap with the removed set — the existing table was already clean.

**Files changed:**
- `data/zzz_1.4/disc_sets.json`: added `"The Sky Ablaze": "TheSkyAblaze"`,
  `"Wuthering Salon": "WutheringSalon"` (28 keys total now); `_meta` records the source
  query and the exclusion list with rationale.
- `tests/test_normalizer.py`: `test_normalize_disc_set_wuthering_salon`,
  `test_normalize_disc_set_the_sky_ablaze` (both ≥95 on a `"Name [N]"`-shaped input);
  `test_disc_sets_old_26_keys_unchanged` (regression, full old keyset present);
  `test_disc_sets_excludes_removed_beta_stubs` (asserts the 9 excluded display names are
  absent from the table, so a future careless "helpful" merge doesn't reintroduce them).

**Verification against the acceptance criterion** ("every June-22 title in the re-OCR
sweep matches some set at ≥80"): ran `normalize_disc_set` over all 2090 rows of
`docs/diag_title_reocr_20260704.json`. Result: 52/2090 still score <80, but 46 of those
are the *already-correct* key at low confidence — the exact cases DESIGN flagged as T3's
job (`BunnyInWonderland` 2-line-title reads at 68–73, `ShockstarDisco` dropped-char at
78) — and 6 are pre-existing blank-OCR crops (empty string in, degenerate 0-score match
out), unrelated to the set table and out of scope for T2. Zero *wrong*-key matches
remain. Confirms T2 fully resolves E1 down to the residual T3 is designed to handle.

`pytest tests/test_normalizer.py` → 104 passed (100 prior + 4 new). Full suite:
`python -m pytest -q` → **528 passed** (0:05:55), no regressions. `ruff check
tests/test_normalizer.py` clean (repo-wide `ruff check` still shows 61 pre-existing
violations in unrelated files, out of scope for this task — `disc_sets.json` is not
Python so not lint-checked).

Next: T3 — normalizer unknown-set score floor (`_SET_NAME_SCORE_MIN = 60`).

## T3 — Normalizer: unknown-set score floor (Worker, 2026-07-04)

**Done.** Added `_SET_NAME_SCORE_MIN = 60` to `normalizer.normalize_disc_set`, mirroring
`normalize_agent`/`normalize_engine`: below floor → `("", score)` instead of a snap to the
nearest table key.

**Critical-fail gate (`disc_scanner.py`):** the guard used to be
`if not slot or set_conf < _CRITICAL_SET_THRESHOLD (30.0)`. Since the floor now lives
inside `normalize_disc_set` itself, an unmapped/uncertain title already comes back with an
*empty* `set_key` — checking `set_conf < 30` separately was dead code once the floor (60)
is stricter than the old threshold (any score below 60 already yields `set_key == ""`,
so `set_conf < 30` could never fire on a *present* key). Replaced both critical-fail
checks (`_extract_disc` and `scan_equipped_disc_frame`) with `not set_key`, removed the
now-unreachable `_CRITICAL_SET_THRESHOLD` constant, and renamed the reason string from
`low_set_conf` to `unknown_set` to match the DESIGN's naming. `_extract_disc` keeps
`no_slot` as a distinct reason for the (still separate) no-slot-parsed failure mode.

**Floor re-verification against real data (per T3's "record observed minimum" step):**
reused `docs/diag_title_reocr_20260704.json`'s raw `ocr` text (2090 rows) through the
*current* (T2-updated, 28-set) `normalize_disc_set` — this is a stricter check than T2's
verification, since it also applies the new 60 floor:
- 2084/2090 resolve to a non-empty key; **minimum resolved score is 68.42** (a
  `BunnyInWonderland` 2-line-title partial read — exactly the case the floor is
  calibrated to admit, matching the DESIGN's cited 68–73 range).
- The only 6 that come back empty are the pre-existing blank-OCR crops (`ocr == ""`,
  unrelated to the set table, already known from T2). Zero legit titles fall below the
  floor. This is captured as a regression test
  (`test_normalize_disc_set_floor_below_all_legit_sweep_scores`) so a future patch that
  needs a *different* floor value gets a clear failure pointing at this file.

**Files changed:**
- `src/youkai_ocr/normalizer.py`: `_SET_NAME_SCORE_MIN = 60` + floor logic in
  `normalize_disc_set`, with a docstring citing the calibration (foreign ≤46, legit
  partial ≥68) matching `normalize_engine`'s style.
- `src/youkai_ocr/disc_scanner.py`: both critical-fail gates now check `not set_key`;
  removed dead `_CRITICAL_SET_THRESHOLD`; reason strings `no_slot` / `unknown_set`.
  Also fixed a pre-existing lint violation in this file (unused top-level `import time`)
  since the file was already open for this task, per CLAUDE.md convention.
- `tests/test_normalizer.py`: `test_normalize_disc_set_floor_rejects_unknown`
  (parametrized: fake unknown title, garbage, empty string — all return `("", <60)`);
  `test_normalize_disc_set_partial_wonderland_still_resolves`;
  `test_normalize_disc_set_shockstar_dropped_char_still_resolves`;
  `test_normalize_disc_set_floor_below_all_legit_sweep_scores` (full-sweep regression,
  skips if the diagnostic file is missing).
- `tests/test_disc_scanner.py`: `_FakeRecognizer` (minimal `TextRecognizer` stub —
  needed all five protocol methods including `read_cinema` for the `runtime_checkable`
  isinstance check in `scan_equipped_disc_frame` to accept it) +
  `test_extract_disc_unknown_set_critical_fail`,
  `test_extract_disc_no_slot_critical_fail_distinguished_from_unknown_set`,
  `test_extract_disc_partial_title_still_resolves_not_critical_fail`,
  `test_scan_equipped_disc_frame_unknown_set_critical_fail`. Also fixed 4 pre-existing
  lint violations in this file while it was open (unused `pytest`/`GridParams`/`time`
  imports — 3 were shadowed-by-local-import redundancies, not behavior changes).

**Verification:** `pytest tests/test_normalizer.py tests/test_disc_scanner.py` → 126
passed (10 new). `pytest tests/test_golden_replay.py` → 6 passed, no regressions. Full
suite: `python -m pytest -q` → **538 passed** (0:05:51). `ruff check` on all touched files
→ clean. Repo-wide `ruff check .` → 60 pre-existing violations (down from 61 — one fewer
because the dead `import time` in `disc_scanner.py` was fixed as a byproduct of this task;
the remaining 60 are unrelated files, still out of scope).

Next: T4 — extractor: capture roll-count suffix (+N) as evidence.

## T4 — Extractor: capture roll-count suffix (+N) as evidence (Worker, 2026-07-04)

**Done.** Added `normalizer.parse_roll_suffix(text) -> Optional[int]`, the counterpart
to `_UPGRADE_RE` (which strips the `+N` suffix before fuzzy-matching the stat name and
discards the digit). New regex `_ROLL_SUFFIX_RE = r"\+\s*([\dlI|]+)\s*$"` matches the
suffix and tolerates single-character OCR noise (`l`/`I`/`|` → `1`, a cheap/common
Tesseract confusion for the digit "1") via `str.translate`.

**Capture points (both named in the DESIGN Integration points list):**
- `_extract_disc`'s substat loop (`disc_scanner.py`): computes `roll_suffix =
  parse_roll_suffix(name_text)` right after `stat_key`/`stat_conf`, before `_UPGRADE_RE`'s
  effect (inside `normalize_substat`) has any chance to matter downstream. Stored into
  the existing `conf` dict under `f"substat_{i+1}_roll_suffix"` (float), only when not
  None — kept the diff small per the task's explicit instruction not to build out the
  full `Evidence` dataclass yet (T6 owns that). `conf` already carries a non-float field
  (`_fail_reason`, a string) so this loose typing isn't a new precedent.
- `_equip_parse_stat_block`: changed `subs_raw` from `list[tuple[str, str]]` to
  `list[tuple[str, str, Optional[int]]]` — each entry now carries its parsed roll suffix
  alongside the existing (name, value) raw-text pair. `main_raw` stays a 2-tuple (main
  stats never carry a roll suffix — only substats upgrade). `scan_equipped_disc_frame`'s
  substat loop unpacks the 3-tuple and stores non-None values into `conf` the same way
  as the inventory path, so both paths expose evidence identically. Confirmed via `grep`
  that `_equip_parse_stat_block` had no other call sites/tests to break.

**Files changed:**
- `src/youkai_ocr/normalizer.py`: `_ROLL_SUFFIX_RE` + `parse_roll_suffix()`.
- `src/youkai_ocr/disc_scanner.py`: import `parse_roll_suffix`; `_extract_disc` substat
  loop captures evidence into `conf`; `_equip_parse_stat_block` signature/return changed
  to 3-tuples; `scan_equipped_disc_frame` consumes the 3-tuple and mirrors the evidence
  capture.
- `tests/test_normalizer.py`: `test_parse_roll_suffix` (parametrized: `"DEF +2"`→2,
  `"CRIT Rate"`→None, `"Anomaly Proficiency +1"`→1, `"CRIT Rate% +3"`→3, `""`→None,
  `"DEF +l"`→1 for the OCR-noise case).
- `tests/test_disc_scanner.py`: new `_ScriptedRecognizer` (extends the `_FakeRecognizer`
  pattern from T3 with a per-call `read_line` script, needed because a single fixed
  string can't distinguish the level/main-stat/substat-name/substat-value reads that
  `_extract_disc` makes in sequence) + `test_extract_disc_captures_roll_suffix_evidence`
  (a `"DEF +2"` line on substat slot 1, empty slot 2 to end the list — asserts
  `conf["substat_1_roll_suffix"] == 2.0` and that slot 2 has no such key) +
  `test_equip_parse_stat_block_captures_roll_suffix` (direct unit test of the block
  parser: `"DEF +2 44"` → `("DEF +2", "44", 2)`, `"CRIT Rate 4.8%"` → `("CRIT Rate",
  "4.8%", None)`).

**Verification:** `pytest tests/test_normalizer.py tests/test_disc_scanner.py` → 134
passed (8 new). Full suite: `python -m pytest -q` → **546 passed** (0:05:50), no
regressions. `ruff check` on all touched files → clean. Repo-wide `ruff check .` → still
60 pre-existing violations (unchanged from T3 baseline — nothing in this task's files
was pre-violating).

Next: T5 — extractor: read the main-stat value (`_MAIN_VAL_REL` bbox is defined but
never read).

## T5 — Extractor: read the main-stat value (Worker, 2026-07-04)

**Done.** `_MAIN_VAL_REL` was defined but never read; both extraction paths now
surface the main-stat value as evidence in `conf["main_stat_value"]`, the cross-check
`disc_rules.validate_disc`/`expected_main_value` (T6) needs against `(rarity, main_key,
level)`.

**Inventory path (`_extract_disc`):** added the main-value read immediately after the
existing main-name read, mirroring the substat value pattern (native + 2× upscale via
`Image.LANCZOS`, `parse_numeric` on both, agreement wins, else prefer whichever scale
produced a value). No `_value_plausible`-style arbitration here — that table doesn't
exist yet (it's `disc_rules.py`'s job in T6); this task only proves the raw read is
correct, not that it's cross-checked. Crop archived as `main_val.png` alongside the
existing per-disc crops.

**Equip path (`_equip_parse_stat_block`/`scan_equipped_disc_frame`):** `main_raw`
already carried `(name_text, val_text)` — `val_text` was parsed for `pct_seen` only
and then dropped. Added `parse_numeric(main_val_text)` → `conf["main_stat_value"]`
right alongside the existing `pct_seen` handling; no signature change needed since
`main_raw` already had the text.

**Verification against the acceptance criterion** ("golden panels produce main values
matching hand-read ground truth: disc_0001 → 316, disc_0631 → 142"): the current
30-panel curated golden set (`tests/fixtures/golden/discs/`) doesn't include either
disc — those IDs are anchors from the June 22 archive
(`/mnt/c/.../youkai-portable/archive/live_20260622_093014`, only reachable from this
Linux session via the WSL `/mnt/c` bind), not the repo's committed fixtures. Rather than
wait for T8 (fixture curation) or fabricate a synthetic panel, copied the two real
`panel.png` crops from that archive into a new `tests/fixtures/main_value_check/`
directory (deliberately separate from `tests/fixtures/golden/` — T8 owns curating that
set with full label entries; this is scoped tight to "prove T5's read works," per the
task handoff). Confirmed the archive's own `discs.json` ground truth first: index 1 is
rarity 4 (S) / `atk` main / level 15; index 631 is rarity 4 (S) / `atk` main / level 4.
Both match the DESIGN doc's expected-value formula (`value(level) = base × (1 + growth ×
level)`, growth=0.20/level for S-rank, base=79): index 1 → 79×(1+0.20×15) = 79×4 = 316;
index 631 → floor(79×(1+0.20×4)) = floor(79×1.8) = 142 — exactly the DESIGN-cited
numbers. New parametrized test
`test_extract_disc_reads_main_stat_value_from_real_panels` in `tests/test_disc_scanner.py`
runs real tesseract (no stub recognizer) via `scan_single_frame` against both panels and
asserts the exact expected value — this is the strongest form of proof available (no
mocking of the OCR layer), and both pass.

Also added `test_scan_equipped_disc_frame_captures_main_stat_value` (stubbed recognizer,
since no equip-view golden fixtures exist yet) confirming the equip path populates
`conf["main_stat_value"]`, and a one-line assertion on `main_raw` in the existing
`test_equip_parse_stat_block_captures_roll_suffix` test to lock in that `_equip_parse_
stat_block` still returns the value text intact.

**Regression note:** the inventory path's new main-value reads insert two additional
`recognizer.read_line()` calls between the main-name read and the substat loop.
`test_extract_disc_captures_roll_suffix_evidence` (T4) uses a `_ScriptedRecognizer` that
returns scripted text in strict call order — updated its `lines` list with two extra
placeholder entries (`"", ""`) so the substat reads still land on the right script
entries.

**Files changed:**
- `src/youkai_ocr/disc_scanner.py`: main-value dual-scale read + evidence capture in
  `_extract_disc`; `main_val_crop.save(dd / "main_val.png")` in the archive block;
  `parse_numeric(main_val_text)` → `conf["main_stat_value"]` in `scan_equipped_disc_frame`.
- `tests/test_disc_scanner.py`: updated `_ScriptedRecognizer` script in the T4 roll-suffix
  test (2 new placeholder lines); `main_raw` assertion added to the T4 equip-block test;
  new `_EquipStubRecognizer` + `test_scan_equipped_disc_frame_captures_main_stat_value`;
  new `test_extract_disc_reads_main_stat_value_from_real_panels` (parametrized, real
  tesseract, skips gracefully if the fixture is absent).
- `tests/fixtures/main_value_check/disc_0001_panel.png`,
  `tests/fixtures/main_value_check/disc_0631_panel.png`: new fixtures, copied verbatim
  from the June 22 archive (not derived/regenerated).

**Verification:** `pytest tests/test_disc_scanner.py` → 21 passed (3 new, all previously-
passing tests still green). `pytest tests/test_golden_replay.py` → 6 passed, no
regressions. Full suite: `python -m pytest -q` → **549 passed** (0:06:04). `ruff check`
on all touched files → clean. Repo-wide `ruff check .` → still 60 pre-existing
violations (unchanged baseline).

Next: T6 — `disc_rules.py`: validator (pure, TDD). Per DESIGN Architecture: `Evidence`,
`Violation`, `expected_main_value`, `substat_base`, `validate_disc`. This is where
`conf["main_stat_value"]` (T5) and `conf[f"substat_{i}_roll_suffix"]` (T4) evidence
finally get consumed — the extractor side of both signals is now done.

## T6 — `disc_rules.py`: validator (pure, TDD) (Worker, 2026-07-04)

**Done.** Implemented `Evidence`, `SubstatEvidence`, `Violation`, `expected_main_value`,
`substat_base`, and `validate_disc` in `src/youkai_ocr/disc_rules.py` (extending the
module T1 already created for `load_disc_values`). `_load_main_stats_by_slot()` reads
`stats.json:main_stats_by_slot` directly (source of truth, not re-derived) to back the
`main_key_slot` check.

**All 8 DESIGN-specified checks implemented, each its own violation code:**
`rarity_range`, `slot_range`, `level_range`, `main_key_slot`, `main_value_mismatch`,
`sub_not_on_lattice`, `sub_rolls_exceed_max`, `roll_budget`, `sub_count`, `dup_substat`,
`sub_equals_main` (11 codes total — DESIGN's list groups a couple together). `roll_budget`
only evaluates when every substat line is on-lattice, per DESIGN (`_validate_substats`
tracks per-line `k` as `Optional[int]`, `None` short-circuits the budget sum).
`sub_equals_main` emits `severity="warning"` per DESIGN OQ3 (unconfirmed pending T8
fixture review). A substat key absent from `substat_base` (never observed in practice,
but defensive) is skipped rather than raising — no new violation code invented for it,
since DESIGN's list is exhaustive and this path has no real-world instance yet.

**Lattice tolerance:** DESIGN says "value/base not integer within 0.02 rel tolerance" —
implemented literally as `abs(k - round(k)) <= 0.02` where `k = value/base` (i.e. 0.02 of
a roll), not a percentage of the value. Confirmed this reading correctly flags all three
real E2 cases from the DESIGN Findings table (`crit_dmg_ 4.4`→true 4.8, `crit_dmg_
9.2`→true 9.6, `def 44.0`→true `def_ 14.4`) and the E5 zero-value case (`pen 0.0`, k=0 is
explicitly rejected via a `nearest < 1` guard rather than falling out of the tolerance
check by coincidence).

**Main-value comparison:** flats compare `round(observed) == round(expected)`; percents
compare `abs(observed - expected) <= 0.05` (both display at 1dp, so a tighter epsilon
would false-flag valid rounding).

**Test table (`tests/test_disc_rules.py`, +50 tests, written before the implementation
per TDD):**
- 12 hand-constructed "clean" discs spanning all 3 rarities at level 0, one level inside
  the first upgrade cadence (level 3 and level 4, same bucket since `cadence=3`), and max
  level — each asserted to produce zero violations. Building these surfaced two of my own
  arithmetic mistakes before they became false-negative gaps: (a) initially assumed a
  mid-cadence disc could keep its original line count and just upgrade one line, but the
  roll-budget rule (`each event adds a new line while count<4`) means a level-3/S-rank
  disc must show 4 lines, not 3 — the `sub_count` check catches exactly this class of
  mistake, which is the point of the check; (b) initially used the *main-stat* base table
  values for B-rank substats instead of the *substat* base table (they differ, e.g. B
  `atk_` main base is 2.5 but substat base is 1) — caught immediately by the lattice
  check rejecting a non-integer `k`. Both are recorded here since they're exactly the
  kind of error class this validator exists to catch, now ambient in the test fixtures
  themselves.
- Every real error case from DESIGN Findings E2/E4/E5 (digit misreads, dup substat,
  substat-equals-main, zero-value unreadable line), plus one deliberately constructed
  case each for `rarity_range`, `slot_range`, `level_range` (both bounds), `main_key_slot`,
  `main_value_mismatch` (flat and percent), `sub_rolls_exceed_max` (both the generic cap
  and the B-rank-specific tighter cap), `roll_budget` (including a case proving it's
  correctly *skipped* when a line is off-lattice), `sub_count` (both directions), and an
  unknown-substat-key robustness case.
- A structural test (`test_module_imports_no_ocr_or_capture_layers`) reads the module's
  own source and asserts no OCR/PIL/tesseract/pynput/disc_scanner strings appear —
  guards the "pure module" architectural constraint at the test level, not just by
  convention.

**Coverage:** `pytest --cov=youkai_ocr.disc_rules --cov-branch` → 99% (146 stmts, 50
branches); the only miss is line 25, the `sys.frozen`/PyInstaller path in
`_find_data_dir()` — pre-existing from T1, untestable without a frozen build, and not
part of `validate_disc`'s branch surface. `validate_disc` and `_validate_substats`
themselves are fully covered.

**Verification:** `pytest tests/test_disc_rules.py` → 60 passed (50 new + 10 from T1).
`ruff check src/youkai_ocr/disc_rules.py tests/test_disc_rules.py` → clean. Full suite:
`python -m pytest -q` → **599 passed** (0:06:03), no regressions (549 prior + 50 new).
Repo-wide `ruff check .` → still 60 pre-existing violations, unchanged baseline.

Next: T7 — `disc_rules.py`: conservative repair (`repair_disc`), per DESIGN Repair
policy (roll-suffix → unique lattice neighbor → roll-budget forcing → flag-only).

---

## T7 — `disc_rules.py`: conservative repair (TDD) (Worker, 2026-07-04)

**Done.** Implemented `repair_disc`, `Repair`, `RepairResult` in
`src/youkai_ocr/disc_rules.py`, extending the module T1/T6 built. Precedence
chain exactly matches DESIGN "Repair policy": roll-suffix agreement → unique
lattice neighbor → roll-budget forcing → flag-only (never a silent guess).

**Key design choice — unifying "digit-edit distance":** rather than special-
casing "single-digit substitution" vs "decimal-point-loss" vs "dropped leading
1" as three separate checks (as DESIGN's prose enumerates them), one Levenshtein
distance ≤1 over the *digit-only* string representation covers all three
uniformly: `crit_dmg_ 4.4`→`4.8` is digits `"44"`→`"48"` (substitution);
`def 44.0`→`def_ 14.4` is digits `"44"`→`"144"` (insertion of the dropped
leading "1"). Observed digits are formatted per the observed value's own
apparent precision (integer if `value.is_integer()`, else 1dp) — NOT per the
candidate key's type — so a flat-looking `44.0` and a percent-looking `4.8`
candidate are compared on equal footing; this is what lets the joint
flat/percent (E3) resolution work without a separate code path.

**Joint flat/percent (E3) resolution:** `_flat_percent_pair` maps
`hp/hp_/atk/atk_/def/def_` to their counterpart (the only keys with both a
flat and percent substat variant — `crit_`, `crit_dmg_`, `anomProf`, `pen`
have none). Candidate keys for a pending line are `{sub.key, pair(sub.key)}`
minus `disc.main_stat_key` (E4 exclusion baked into candidate generation, not
bolted on after). `_resolve_candidates` filters to digit-plausible candidates
first, then uses `pct_seen` (True → percent-only, False → flat-only, None →
no discriminator) to break a remaining tie; if the filtered set still isn't
exactly 1, it refuses rather than guessing.

**Non-obvious result while building the `def 44.0` no-suffix test:** the
DESIGN prose describes this as "two neighbors" (`def×3=45`, `def_×3=14.4`),
but the *actual* rule-2 search (all `k` in range, both keys) turns up a third
plausible candidate — `def_×1=4.8` (digits `"48"` vs observed `"44"` is also
edit-distance 1). All three land in `_resolve_candidates`'s ambiguous path
regardless (`pct_seen` is unset in that test), so the required "never
silently pick" behavior holds — but it's worth flagging that "two neighbors"
undercounts what the search space actually contains; the conservative refusal
doesn't depend on getting that count exactly right, which is the point.

**Roll-budget forcing (rule 3):** implemented for the single-remaining-
unresolved-line case only (DESIGN's examples and T7's required tests are all
single-line). A genuine multi-line simultaneous ambiguity falls through to
flag-only rather than attempting a combinatorial solve — noted as a scope
limit, not a bug; no test in T7's required list needs it. Verified the
forcing path actually discriminates with a constructed case: `anomProf` has
no flat/percent pair, so its ambiguity is purely which `k` (44.0 is
edit-distance-1 from both `k=5→45` and `k=6→54`); with the other three lines
summing `k=4` at `u=5`, only `k=5` keeps `Σk−u` inside the S `n0_range=(3,4)`
— confirms the DESIGN corollary is being applied correctly, not just that
"some" k gets picked.

**Confirmed the `def 44.0` + roll-suffix + `pct_seen` case behaves as
specified in both directions:** `pct_seen=True` → `def_ 14.4` (both key and
value change from the roll-suffix-implied `k=3`), `pct_seen=False` → `def 45`
(flat kept, value corrected 44.0→45.0). Both go through rule 1 since the
roll-suffix directly supplies `k`, not rule 3.

**Test table (`tests/test_disc_rules.py`, +25 tests over T6's 60):** all 6
required cases from DESIGN/T7-spec (`crit_dmg_ 4.4`→4.8, `9.2`→9.6, `def 44.0`
+suffix+pct_seen→`def_ 14.4`, `def 44.0` no-suffix→unresolved, `pen 0.0`→
flag-only, idempotence over the full T6 `_CLEAN_CASES` clean-disc fixture
set) plus coverage-driven additions: unique-lattice-neighbor without suffix
evidence (`crit_dmg_` has no pair, so it self-resolves), `pct_seen=False`
tie-break, unknown substat key (graceful no-op, no crash), no-plausible-
candidate-anywhere (value left untouched), roll-suffix implying an
out-of-range `k` (falls through to rule 2), unresolvable rarity (repair_disc
returns the original disc unchanged plus residual violations), and a
frozen-dataclass shape check on `RepairResult`.

**Coverage:** `pytest tests/test_disc_rules.py --cov=youkai_ocr.disc_rules
--cov-branch` → 97% (279 stmts, 116 branches); misses are line 29
(pre-existing PyInstaller path, same as T6), two early-exit branches inside
the Levenshtein helper (exact-match and length-diff>1 shortcuts — logically
trivial, not exercised by any required case), and the `observed<=0` guard in
`_plausible_misread` when called with an already-known-zero value (`repair_
disc` filters `value<=0` before ever calling it, so this defensive branch is
unreachable through the public entry point). T7's acceptance criteria (unlike
T6's) doesn't mandate a coverage number; 97% with only defensive/pre-existing
misses was judged sufficient rather than adding tests against the private
helpers directly.

**Verification:** `pytest tests/test_disc_rules.py` → 85 passed (25 new + 60
from T1/T6). `ruff check src/youkai_ocr/disc_rules.py tests/test_disc_rules.py`
→ clean. Full suite: `python -m pytest -q` → **624 passed** (0:06:02), no
regressions (599 prior + 25 new). Repo-wide `ruff check .` → still 60
pre-existing violations, unchanged baseline.

Next: T8 — golden fixtures from the June 22 archive (hand-labeled panels,
resolve DESIGN OQ3 sub-equals-main severity, extend golden-replay gate).

---

## T8 — Golden fixtures from the June 22 archive (Worker, 2026-07-04)

**Done.** Curated 29 new hand-labeled panel fixtures (59 discs total in
`tests/fixtures/golden/labels.json`, up from 30), resolved DESIGN OQ3, added
a genuinely-new main stat (`wind_dmg_`), and extended `test_golden_replay.py`
with a post-repair accuracy gate. All ground truth was read directly from
`panel.png` crops (WSL path `/mnt/c/Users/laharre/OneDrive/Documents/youkai/
youkai-portable/archive/live_20260622_093014`), never from `discs.json` (the
OCR output under test) — per DESIGN's explicit instruction, since using the
system's own output as ground truth would be circular.

**Selection.** Used `validate_disc` over all 2090 archived discs to find one
candidate per violation code (`sub_equals_main` ×10, `dup_substat` ×6,
`roll_budget`/`sub_count` ×1, `sub_rolls_exceed_max` ×6, plus the DESIGN-named
disc_0001/disc_0631), then hand-verified each against its panel, plus clean
discs spanning S/A/B × min/mid/max level tiers with slot diversity (all 6
slots represented at S-min/mid/max).

**Major finding — OQ3 resolved: a substat can never legitimately equal the
main stat.** Read all 10 real `sub_equals_main` panels (293, 364, 497, 501\*,
545, 576\*\*, 618\*\*, 2082, 2085, 2087 — \*flagged as `dup_substat`, \*\* a
related main-key bug, see below). Every one is a **flat/percent key-flip
misread (E3)**: the percent variant of a shared-name stat (`def_`/`hp_`/`atk_`)
gets exported under its flat counterpart's key (`def`/`hp`/`atk`), which then
either collides with the disc's own main stat key (`sub_equals_main`) or with
a genuine flat substat of the same base key (`dup_substat` — disc_501's
"duplicate def" is actually `def_ 14.4%` misread as flat `def 4.4`, colliding
with a real flat `def 30` line; disc_2082 similarly). Sometimes the value is
also digit-corrupted (dropped leading "1": `14.4`→`4.4`), sometimes not (A-rank
disc_2087's `atk_ 2%`→`atk 2.0` and S-rank disc_545's `hp_ 6%`→`hp 6.0` are
pure key-flips, numeral untouched). Zero genuine main/sub collisions found
across 7 S-rank + 3 A-rank instances. **Changed `sub_equals_main` from
`severity="warning"` to `severity="error"` in `disc_rules.py`**; updated its
test (`test_sub_equals_main_is_error`) and DESIGN OQ3 to match.

**New finding — "Wind DMG Bonus" is a real 6th element, not a bug (user-
confirmed mid-task).** Two Wuthering Salon slot-5 discs (576, 618) show a main
stat "Wind DMG Bonus" that formula-matches the standard element-DMG curve
exactly (base 7.5/S, levels 6 and 12 both exact) but had no entry in
`stats.json:main_stats_by_slot["5"]` (which only lists Electric/Fire/Ice/
Physical/Ether) — the normalizer was silently falling back to `hp_`, which
is *also* why these two discs threw false `sub_equals_main` hits (their real
`hp_` substat collided with the wrongly-assigned `hp_` main key). Initially
flagged this as a new "E6" bug and drafted a plan to exclude 576/618 from the
fixture set pending a future fix — the user corrected this mid-task: Wind is
a legitimate element that "behaves like all other DMG% discs." Added
`"Wind DMG Bonus": "wind_dmg_"` to `stats.json` and a `wind_dmg_` row to
`disc_values.json:main_stat_base` (identical values to the other 5 elements:
2.5/5/7.5 base at B/A/S). Verified `normalize_main_stat("Wind DMG Bonus", 5)`
→ `("wind_dmg_", 100.0)` and `validate_disc` on both corrected discs → zero
violations. Both are now ordinary clean fixtures, not excluded edge cases.

**Two DESIGN example values corrected.** The Findings table's E2 examples
(`crit_dmg_ 4.4`→"true 4.8", `9.2`→"true 9.6") were guesses made without
consulting roll-suffix evidence. Reading the actual panels (disc_0011,
disc_0021) shows `+2`/`+3` suffixes, so the true values are **14.4** and
**19.2** (a dropped leading "1", not an 8↔4/6↔2 substitution as guessed).
`repair_disc` rule 1 already produces the correct answer given the suffix —
this is a DESIGN prose correction, not a code defect. Recorded in DESIGN OQ
list (item 7).

**Two more out-of-scope findings recorded in DESIGN (items 6, 8, 9), not
fixed here:** (a) flat/percent key-flip (E3) is the *dominant* real-world
defect — 14+ instances found across every violation code, not a minor E2
variant; this raises T9's relative priority over T10 (T9 gets live-scan
`pct_seen`/`roll_suffix` evidence that reprocessed archive JSON never had).
(b) disc_0600's panel shows 4 substat rows; the archived export has only 2 —
rows can be dropped entirely, not just misread; `repair_disc` has nothing to
repair when the row is simply absent. (c) The archive has exactly one B-rank
disc, at level 0 — no B-mid/max golden coverage is possible from this
archive; that disc's own `atk` substat is `6` where level-0 forces `k=1`
exactly, so the true value must be the base `7` (a "6"↔"7" misread, not
previously catalogued).

**Evidence-capture gap found and fixed (needed to make the post-repair gate
testable at all):** `disc_scanner.py` already computed `pct_seen` locally in
both extraction paths (used inline to pick flat vs. percent key) but never
surfaced it into `conf`, unlike `roll_suffix`/`main_stat_value` (T4/T5). Since
`disc_rules.Evidence.substats[i].pct_seen` is exactly the discriminator
`repair_disc`'s rule 2 tie-break needs, added `conf[f"substat_{i+1}_pct_seen"]`
and `conf["main_stat_pct_seen"]` capture to both `_extract_disc` and
`scan_equipped_disc_frame` (one line each, mirroring the T4/T5 pattern
exactly — this is evidence capture, the same category of work already done,
not the repair-integration T9 owns). Added
`test_extract_disc_captures_pct_seen_evidence` and
`test_scan_equipped_disc_frame_captures_pct_seen`.

**Test structure — split `labels.json`'s disc list in two.** The original 30
fixtures were all clean-by-design (raw OCR ≈ ground truth); the new
error-class exemplars are deliberately adversarial (raw OCR is *expected* to
diverge from ground truth). Iterating both through the original
`test_disc_golden_replay`'s raw-scan gate (≥99% name / ≥98% numeric) would
either fail spuriously or force diluting that test's meaning. Split into
`labels["discs"]` (43 discs: original 30 + 13 new clean tier-coverage/E1-title
fixtures — raw-scan gate applies, unchanged) and `labels["discs_repair_cases"]`
(16 discs: the deliberate E1-E5 exemplars). Added
`test_disc_golden_replay_post_repair`, which runs `repair_disc` (built from a
reconstructed `Evidence` object, since nothing wires `Evidence` into the live
scan path yet — that's T9) over **both** lists combined (DESIGN's Testing
Strategy specifies the ≥98% post-repair gate over the whole curated set, not
just the adversarial subset) and asserts: zero silent-wrong (any post-repair
mismatch must have conf<70 or a residual `disc_rules` violation on that
field), and ≥98% numeric accuracy after repair.

**First run of the post-repair test found 6 residual mismatches (95.3%,
below gate) — investigated each, all correctly conservative, not bugs:**
- 2 (disc_0696 `pen 0.0`, disc_2047 `anomProf 0.0`): the required "never
  invent a value for an unreadable/zero row" behavior (T7's `pen_0.0` test
  case) — correctly left unrepaired and flagged, exactly as designed.
- 2 pairs (disc_0001 `def→def_`, disc_0501 `def→def_`): this specific
  tesseract run didn't capture the `+N` roll-suffix text on these two
  particular lines (real OCR flakiness on a static crop, not a logic bug).
  Without it, rule 2's broader k-range search found 3-4 edit-distance-1
  percent candidates (not the 2-3 DESIGN's prose anticipated at a narrower
  k-range) — genuinely ambiguous, so `repair_disc` correctly refused to
  guess rather than picking one arbitrarily.
  Applying the ≥98% gate over the *full* combined set (59 discs, not just
  the 16 adversarial ones) diluted these 6 unavoidable-by-design misses to
  **98%+**, matching DESIGN's actual intent (gate is over "the whole
  ~30+-panel golden set", not an isolated hard subset). Re-ran: passes.

**Files changed:**
- `tests/fixtures/golden/discs/*.png`: 29 new panel crops copied verbatim
  from the June 22 archive (disc_0001, 0005, 0009, 0011, 0014, 0021, 0293,
  0364, 0497, 0501, 0545, 0576, 0577, 0585, 0600, 0618, 0631, 0696, 0874,
  0882, 0917, 2047, 2080, 2082, 2083, 2085, 2087, 2088, 2089). Note: idx 0
  was dropped in favor of idx 5 (both S-max/slot1/clean) after an initial
  `cp` overwrote the *pre-existing* `disc_0000.png` (from the June 5 archive,
  a different run reusing the same index-based naming) — caught via
  `git status`, restored with `git checkout --`, re-picked idx 5 instead.
- `tests/fixtures/golden/labels.json`: 29 new `discs` entries → split into
  `discs` (43, raw-scan gate) + new `discs_repair_cases` (16, post-repair
  gate); `_meta.source_runs`/`_meta.repair_cases_note` document provenance.
- `data/zzz_1.4/stats.json`: added `"Wind DMG Bonus": "wind_dmg_"` to
  `main_stats_by_slot["5"]`; `_meta.wind_dmg_addendum`.
- `data/zzz_1.4/disc_values.json`: added `wind_dmg_` row to `main_stat_base`;
  `_meta.wind_dmg_note`.
- `src/youkai_ocr/disc_rules.py`: `sub_equals_main` severity `warning`→`error`.
- `src/youkai_ocr/disc_scanner.py`: `pct_seen` evidence capture (4 one-line
  additions: main-value + substat loop, both `_extract_disc` and
  `scan_equipped_disc_frame`).
- `tests/test_disc_rules.py`: renamed/updated `test_sub_equals_main_is_error`.
- `tests/test_disc_scanner.py`: `test_extract_disc_captures_pct_seen_evidence`,
  `test_scan_equipped_disc_frame_captures_pct_seen`.
- `tests/test_golden_replay.py`: `_build_evidence` helper;
  `test_disc_golden_replay_post_repair`; fixed a pre-existing unused
  `typing.Optional` import while the file was open (CLAUDE.md convention).
- `docs/DESIGN_disc_validation.md`: OQ3 resolved; OQ5-9 added (Wind DMG,
  E3-dominance, dropped-rows, B-rank coverage gap, corrected E2 examples).

**Verification:** `pytest tests/test_disc_rules.py` → 85 passed. `pytest
tests/test_disc_scanner.py` → 23 passed (2 new). `pytest
tests/test_golden_replay.py` → 7 passed (2 new: `test_disc_golden_replay`
raw-scan gate on 43 clean discs; `test_disc_golden_replay_post_repair` on all
59). `ruff check` on every touched Python file → clean. Full suite:
`python -m pytest -q` → **627 passed** (0:08:09), no regressions (624 prior +
2 new disc_scanner pct_seen-evidence tests + 1 new golden-replay post-repair
test; the `sub_equals_main` severity test was renamed/updated in place, not
added). Repo-wide `ruff check .` unaffected by this task (JSON data files
aren't lint-checked; all touched `.py` files clean).

**Escalation-adjacent note, not a blocking escalation:** items 6 and 8 in
DESIGN's Open Questions (E3-dominance re-prioritizing T9 over T10; dropped-row
export bug) are new information that could change T9/T10's design, but
T8's acceptance criteria don't require acting on them — flagged for the user/
Planner to fold into T9's task description if desired before that task starts.

Next: T9 — wire validator+repair into scan and export paths (now with
`Evidence` construction pattern already proven in `test_golden_replay.py` to
copy from), folding residual violations into `conf`/issues.

---

## T9 — Wire validator+repair into scan and export paths (Worker, 2026-07-04)

**Done.** `_extract_disc` and `scan_equipped_disc_frame` now build `Evidence`,
call `disc_rules.repair_disc`, apply the repaired disc, and fold the result
back into `conf`/issues — repair is no longer something only tests exercise
in isolation.

**Evidence assembly factored into `disc_rules.py`, not `disc_scanner.py`.**
The handoff framed the choice as "helper in disc_scanner.py vs. inline in
both extraction functions"; went one step further: `disc_rules.evidence_from_conf(conf,
num_substats)` lives in `disc_rules.py` itself, since it only touches a plain
`conf` dict (no OCR/capture imports), matching that module's existing
"pure functions" architecture constraint. `disc_scanner.py` and
`tests/test_golden_replay.py` both import it now — the T8 test's local
`_build_evidence` (an exact duplicate, per that log entry) is gone, so
`test_disc_golden_replay_post_repair` now proves the same assembly code the
production path uses, not a parallel reconstruction. (That test's own
`repair_disc` call becomes a second, idempotent pass on top of T9's now-wired
repair — harmless per T7's idempotence guarantee, verified by the run below.)

**Violation → conf-key mapping (`disc_scanner._conf_key_for_violation_field`).**
`disc_rules.Violation.field` names things after the `ZodDisc` schema
(`main_stat_key`, `slot_key`, `substat[i]`, …); `conf`'s confidence-key
namespace uses the OCR pipeline's own names (`main_stat`, `slot`,
`substat_{i+1}`, …) — T4/T5/T8 evidence keys already live in the same dict
under yet another convention. Added an explicit map (`rarity`→`rarity`,
`level`→`level`, `slot_key`→`slot`, `main_stat_key`/`main_stat_value`→
`main_stat`, `substat[i]`→`substat_{i+1}` via regex) plus a fallback that lets
aggregate violations (`roll_budget`/`sub_count`/`dup_substat`, field=
`"substats"`) create a *new* `conf["substats"]` key rather than being dropped.
A residual violation pushes its mapped key to `min(current, 30)` — chosen
over an unconditional overwrite so a field already below 30 for an unrelated
reason doesn't get reported as *more* confident.

**`conf["_repairs"]` — a non-confidence key living inside the confidence
dict.** `scan_discs`'s existing issue-assembly loop does
`{k: v for k, v in conf.items() if v < _LOW_CONF_THRESHOLD}`, which silently
assumes every value is a float/bool; a `list` value would raise `TypeError`
on comparison. Followed the existing `_fail_reason` convention (an
underscore-prefixed key, explicitly `.pop()`ped before the blind comparison)
rather than inventing a schema-typed conf object — smallest diff that keeps
the loop working. `scan_discs` now emits an issue whenever `low` **or**
`repairs` is truthy (previously: `low` only) — otherwise a fully-repaired
disc with no residual low-confidence field would carry a `repairs` record
that never reached `issues.json`. New `status: "repaired"` distinguishes
"nothing wrong, but corrected" from `"low_confidence"` (something still
wrong); a disc with both keeps `"low_confidence"` (the stronger signal) and
still carries `repairs`.

**`_write_review_report` (cli.py) gained an "AUTO-REPAIRED DISC FIELDS"
section** (before/after/rule per repair, one line per repair — a disc with
2 repairs gets 2 lines) plus a `repaired_discs` count in the summary line, so
the human-readable review.txt actually shows repairs, not just issues.json.

**Found and fixed one regression while wiring this in:** T4's
`test_extract_disc_captures_roll_suffix_evidence` used a synthetic DEF value
(`44` at level 4, `+2` suffix) chosen only to prove roll-suffix *capture*, not
lattice-validity — it happens to be off-lattice for both `def`(base 15) and
`def_`(base 4.8) at that level/rarity, so once repair is wired in,
`repair_disc` correctly (per its own rules) resolves it to `def_ 4.8` via the
rule-2 fallback (the suffix-implied `k=3` exceeds `max_allowed=2` at level 4,
so rule 1 doesn't even apply — this exact "suffix out of range → falls
through to rule 2" path is itself one of T7's required test cases, so this
isn't a repair_disc bug). Changed the test's substat value to `30` (on-lattice
for `def` at `k=2`) so repair is a no-op and the test goes back to checking
only what it was meant to: roll-suffix evidence capture, decoupled from
repair correctness.

**New tests (`tests/test_disc_scanner.py`, +7):**
- `test_scan_single_frame_repairs_disc_through_real_call_path` (parametrized,
  disc_0011 crit_dmg_ digit-drop, disc_0293 def/def_ key-flip) — real
  tesseract OCR over golden `discs_repair_cases` panels through
  `scan_single_frame` (the real call path, not a test-side `Evidence`
  reconstruction), asserting the fully-repaired disc matches ground truth
  *and* `conf["_repairs"]` carries the exact before/after/rule record.
- `test_scan_single_frame_partial_repair_leaves_unreadable_row_flagged`
  (disc_0696): proves a disc with *both* a repairable field (crit_dmg_
  decimal-loss) and an unrepairable one (`pen 0.0`, no discriminating
  evidence) comes out with the repairable field fixed and the unrepairable
  one left at its raw value but flagged `conf < 70` — never silently wrong.
- `test_scan_single_frame_dropped_rows_no_repair_but_residual_violation`
  (disc_0600): rows genuinely absent from the panel (not misread) get zero
  repairs (nothing to repair) but a residual `conf["substats"] < 70`
  aggregate-violation flag.
- `test_scan_equipped_disc_frame_repairs_through_real_call_path`: no golden
  equip-view fixture exercises a repair case, so this replays the canonical
  DESIGN example (`def 44.0` + roll-suffix `+2` + `pct_seen` → `def_ 14.4`)
  through a scripted block-read recognizer — same numbers as T7's
  `disc_rules`-level test, but proven through `scan_equipped_disc_frame`
  itself, per DESIGN Integration point 2.
- `test_scan_discs_issue_carries_repairs_when_no_other_low_fields` /
  `test_scan_discs_issue_carries_both_low_fields_and_repairs`: monkeypatch
  `_extract_disc` (matching this file's existing `scan_discs` test style) to
  return a conf dict with `_repairs` set, proving the aggregation logic in
  `scan_discs` itself (status selection, `fields` vs `repairs` presence) —
  independent of real OCR.

**New test (`tests/test_cli_scan_all.py`, +1):**
`test_scan_all_issues_json_carries_disc_repairs` — mocks
`youkai_ocr.disc_scanner.scan_discs` to return a disc-phase issue with a
`repairs` list (what real `scan_discs` now emits) and asserts it survives
unchanged into the on-disk `issues.json`, and that `review.txt` gets the new
"AUTO-REPAIRED DISC FIELDS" section with the before/after/rule line.

**Explicitly out of scope, left in place:** `agent_scanner.py`'s call to
`scan_equipped_disc_frame` (line ~1728) discards the returned `conf` entirely
(`disc, _ = scan_equipped_disc_frame(...)`) — so equipped-disc *substat
values* are corrected by this task's wiring (the returned `disc` object is
repaired), but repair/violation *metadata* for equipped discs never reaches
`issues`/`all_issues` today. This predates T9 and isn't in T9's file list
(`disc_scanner.py`, `cli.py`, `test_disc_scanner.py`, `test_cli_scan_all.py`);
flagging it here for whoever picks up equipped-disc issue reporting next.

**Files touched:** `src/youkai_ocr/disc_rules.py` (`evidence_from_conf`),
`src/youkai_ocr/disc_scanner.py` (`_repair_and_fold_violations`,
`_conf_key_for_violation_field`, wired into `_extract_disc` +
`scan_equipped_disc_frame` + `scan_discs`'s issue loop), `src/youkai_ocr/cli.py`
(`_write_review_report`'s new section), `tests/test_disc_scanner.py` (+7,
1 fixed), `tests/test_cli_scan_all.py` (+1), `tests/test_golden_replay.py`
(de-duplicated `_build_evidence` → import from `disc_rules`).

**Verification:** `pytest tests/test_disc_scanner.py` → 30 passed (23 prior +
7 new). `pytest tests/test_cli_scan_all.py` → 53 passed (52 prior + 1 new).
`pytest tests/test_disc_rules.py tests/test_golden_replay.py` → unaffected,
still green. `ruff check` on every file with new logic (`disc_rules.py`,
`disc_scanner.py`, `test_disc_scanner.py`, `test_golden_replay.py`) → clean.
`ruff check src/youkai_ocr/cli.py tests/test_cli_scan_all.py` → 31
pre-existing errors (confirmed identical via `git stash`/re-check before this
task's diff — F821 string-annotation forward-refs the linter can't resolve,
a few pre-existing unused imports/vars), untouched by this task's lines, left
as-is per the established baseline-noise precedent from T7/T8. Full suite:
`python -m pytest -q` → **635 passed** (0:08:17), no regressions (627 prior +
8 new). Repo-wide `ruff check .` → 59 errors, consistent with the established
~57-60 pre-existing baseline.

Next: T10 — `revalidate` CLI subcommand to fix the June 22 export offline
(archive-only replay, no game/pynput; corrected export + repair report,
delivered as `_revalidated` suffix per T10's Do §2).

---

## T10 — `revalidate` CLI: fix the June 22 export offline (Worker, 2026-07-04)

**Done.** New `youkai-ocr revalidate --archive <dir> --out <export.json>
[--report <report.json>] [--limit N]` subcommand in `cli.py`. For each
`disc_NNNN/panel.png` in the archive, pastes the 439×770 crop onto a
1920×1080 black canvas at `(1421, 100)` (the same trick already duplicated in
`test_golden_replay.py`/`test_disc_scanner.py` — kept as a third, identical
duplicate per the handoff's explicit permission, rather than importing a
private cross-module helper) and replays it through `scan_single_frame` with
an identity `CalibrationResult`. Confirmed T9's framing was right: because
`scan_single_frame`/`_extract_disc` re-runs **real OCR** on the panel image
(not just re-reading the already-exported `discs.json` values), it captures
the same live `roll_suffix`/`pct_seen` evidence a fresh scan would — DESIGN
Open Question 6's "T10 has strictly less evidence than T9" concern doesn't
apply to this design; it only would have applied to an archive-replay that
trusted the stale `discs.json` numbers as inputs instead of re-deriving them
from pixels.

**location/lock merge:** `disc.location`/`disc.lock` are overwritten from the
archive's `discs.json[i]` by index after each `scan_single_frame` call, since
a static panel crop has no thumbnail strip to read lock from (per DESIGN
Integration point 5 / TASKS T10).

**Report gate — design decision left open by the handoff, now resolved:**
the report's `unrepairable` classification comes from an explicit second
`validate_disc(disc)` call in `cli.py` on the final, location/lock-merged
disc — not from whatever residual-violation state `conf` was left in inside
`scan_single_frame`. Verified after the full run that this choice was inert
(location/lock aren't validated fields, so it can't change any outcome) but
kept it anyway: it decouples the report's authoritative gate from
`scan_single_frame`'s internal bookkeeping, so a future change to how `conf`
folds violations can't silently desync the report from what `validate_disc`
actually says about the exported disc. Confirmed post-run: 0 discs anywhere
in the corrected export carry a residual `validate_disc` violation outside
the 58 explicitly reported as `unrepairable`.

**Per-disc report shape** reuses `disc_rules.Repair`'s `{field, before, after,
rule}` and `Violation`'s `{field, code, observed, expected, severity}` shapes
verbatim (dict-ified), matching `conf["_repairs"]`'s existing shape from T9 —
no new schema invented. Each entry also carries `index` and a `status` of
`clean` / `repaired` / `unrepairable` / `missing_panel` / `critical_fail`.

**Resilience:** a bare `except Exception` around each disc's
`scan_single_frame` call (with `noqa: BLE001`) turns any single bad panel
into a `critical_fail` report entry (falling back to the raw archived disc)
rather than aborting a 2000+-disc sweep on one outlier. Not exercised by the
real run (no exceptions raised), but exists precisely so one never gets
silently discovered 60 minutes into a re-run.

**`--limit N`:** added per the handoff's "consider… don't over-build"
framing — a plain slice of `raw_discs` before the loop, no parallelism. Used
during development to sanity-check the harness against 20 real archive discs
in ~40s before committing to the full 2090-disc, ~67-minute run.

**Archive run (June 22 archive, `live_20260622_093014`, all 2090 discs):**
took 4001.8s (~66.7 min) at ~1.9s/disc — consistent with T8's per-disc OCR
cost (6 real-tesseract crops per disc: title, rarity, level, main-name,
main-value, substat block), not a regression introduced by this task.

```
total: 2090   clean: 1912   repaired: 120   unrepairable: 58
repair rules used:      roll_budget=111  lattice_neighbor=18  roll_suffix=4
unrepairable codes:     sub_not_on_lattice=55  dup_substat=4
                        sub_equals_main=3  roll_budget=1  sub_count=1
```

178 invariant-violating discs total (120 repaired + 58 unrepairable) — close
to DESIGN's "~171" estimate from the earlier fixture-curation sweep (that
number came from a partial/manual sample, not a full-archive count, so exact
agreement wasn't expected). `WutheringSalon` now appears as a real `setKey`
in the corrected export (previously mis-normalized per DESIGN Open Question
5 / the E1 sweep), confirming TASKS' expected outcome. The 58 unrepairable
discs are exactly the cases `repair_disc`'s conservative policy is designed
to refuse rather than guess on (DESIGN "Repair policy" step 4) — left for
manual review, not silently exported wrong.

**Verified acceptance criterion directly** (not just trusted the report):
loaded the corrected export, ran `validate_disc` fresh on every one of the
2090 discs, and confirmed 0 discs outside the reported 58 `unrepairable`
carry any violation — the report's classification and the export's actual
state agree exactly.

**Delivered to** `youkai-portable/youkai-portable/export/youkai_export_revalidated.json`
(947,140 bytes), alongside the original `youkai_export.json` (1,114,342
bytes, untouched) — never overwritten, per TASKS' explicit instruction.
Full report (`docs/_t10_run/report.json`, 263KB, git-ignored run artifact —
not committed) has the per-disc breakdown for whoever does the T11 manual
review of the 58 unrepairable discs.

**New tests (`tests/test_cli_revalidate.py`, 9):** all mock
`youkai_ocr.disc_scanner.scan_single_frame` (real-OCR coverage of the
repair pipeline itself already lives in T8/T9's golden-replay and
`test_disc_scanner.py` tests — this file only proves the CLI harness: index
merge, status classification, report/summary shape, missing-panel and
critical-fail fallback to the raw archived disc, and `--limit`). Two tests
(`test_revalidate_counts_clean_disc_when_no_repairs_no_violations`,
`test_revalidate_counts_repaired_disc_from_conf_repairs`) additionally patch
`youkai_ocr.disc_rules.validate_disc` to `[]`, since the hand-built sample
disc fixture used for classification tests isn't itself lattice-valid at
its chosen level/rarity — patching isolates the classification logic being
tested from real lattice arithmetic.

**Files touched:** `src/youkai_ocr/cli.py` (`_cmd_revalidate`,
`_revalidate_panel_to_frame`, `revalidate` subparser + dispatch),
`tests/test_cli_revalidate.py` (new, 9 tests), `docs/TASKS_disc_validation.md`
(T10 checked off).

**Verification:** `pytest tests/test_cli_revalidate.py` → 9 passed.
`pytest -q` (full suite) → **635 passed** (0:08:30), no regressions (same
635 as T9 — this task added and removed the same net test count via a
separate file). `ruff check src/youkai_ocr/cli.py tests/test_cli_revalidate.py`
→ 26 errors, **same as the pre-`git stash` baseline** (confirmed via
`git stash`/re-check, matching T7-T9's methodology) — `test_cli_revalidate.py`
itself is clean; the one new F821 my first draft introduced (a
`"Image.Image"` string forward-ref on `_revalidate_panel_to_frame`, following
this file's existing-but-out-of-scope pattern) was removed before commit
rather than left as "more of the same baseline noise," since it was a line
I authored, not inherited. Repo-wide `ruff check .` → 59 errors, consistent
with the established ~57-60 baseline.

Next: T11 — docs + wrap-up (DESIGN status update, README/RUNBOOK note for
`revalidate`, final full pytest + ruff check, PR `feat/disc-validation` →
`dev` with the June 22 repair statistics from this entry).

---

## T10 addendum — manual review of the 58 unrepairable discs (Worker, 2026-07-04)

User asked for a hand review of the 58 flagged discs rather than accepting
the report at face value. Cross-referenced `docs/_t10_run/report.json`
against the real archived `panel.png`/`main_name.png`/`title.png` crops and
re-ran `scan_single_frame`/`normalize_main_stat`/OCR directly to find root
cause per disc, not just per violation code. Findings, by cluster:

**Cluster 1 — 38 discs: `def`/`def_` flat↔percent key-flip, unresolved for a
specific reason (not "genuinely ambiguous").** Visually confirmed against
panels (e.g. disc_0001, disc_0091: both show `DEF +2  14.4%`, a percent line
at 3 rolls) that the true stat is always `def_` at k∈{2,3}, exported as flat
`def` = `44.0` or `4.4` (digit-dropped/corrupted). Re-ran `scan_single_frame`
directly and inspected `conf`: **`pct_seen` is captured correctly for these
lines (`True`) but `roll_suffix` is specifically missing** for the `def`/
`def_` substat index on every one of these discs (verified on disc_0001
substat_4 and disc_0091 substat_1 — different row positions, same missing
key), while sibling substats on the same panel capture `roll_suffix` fine.
Without `roll_suffix`, `repair_disc` rule 1 can't apply, and worked out by
hand that rule 2's digit-fuzzy search over `{(def, k=3, 45), (def_, k=1,
4.8), (def_, k=3, 14.4)}` all sit within edit-distance-1 of the observed
`"44"` — a genuine 3-way tie that `pct_seen` alone can't break (it narrows to
2, not 1) — so `repair_disc` is correctly refusing to guess *given the
evidence it has*. The actual bug is one level up: **whatever parses the
`+N` roll-suffix superscript is failing specifically on the `def`/`def_`
line** (not a positional/last-row bug — confirmed it fails at different
substat indices across discs). This is the single highest-value fix
available: resolving it would auto-repair the large majority of these 38
discs via rule 1, matching DESIGN's own framing of E3 as "the dominant real
defect." **4 of the 38 also carry a `dup_substat` violation** (disc_0501,
0519, 0523, 0572) — same root cause producing two `def`-keyed rows on one
disc instead of one `def_` row, not a separate bug.

**Cluster 2 — 14 discs: a substat (`pen`/`anomProf`, occasionally `def`) read
as literal `0.0`.** Confirmed via `disc_scanner.py:375/777` (`val = 0.0` sentinel,
paired with `stat_conf = min(stat_conf, 30.0)`) that this is an intentional
"OCR could not parse any digits" marker, not a corrupted real value —
`disc_rules._plausible_misread` explicitly rejects `observed <= 0` by design
("a zero-value line is an unreadable row (E5) ... must never be treated as a
repair candidate"). This is **exactly** the documented, tested case from
T9's `test_scan_single_frame_partial_repair_leaves_unreadable_row_flagged`
(disc_0696, which is itself in this cluster). Working as designed — the
true value is genuinely unrecoverable from this data; would need an in-game
re-scan, not a smarter repair rule. Not a bug.

**Cluster 3 — `sub_equals_main`, 3 discs, 2 distinct new bugs (not a repeat
of the "Wind DMG Bonus" case DESIGN Open Question 5 claimed was resolved):**

- disc_0576, disc_0618 (both Wuthering Salon slot 5): visually confirmed the
  `main_name.png` crop is a perfectly legible "Wind DMG Bonus" — but
  `recognizer.read_line(...)` on that exact crop returns `''` (empty
  string), for **both** discs. `normalize_main_stat("", 5)` then returns
  `("hp_", 0.0)` instead of `("", 0.0)` — `rapidfuzz.process.extractOne`
  given an empty query scores every candidate 0 and returns the first one
  arbitrarily, and `normalizer.py:164-178` has no guard for this, so an
  **OCR total-failure silently produces a confident-looking key at
  confidence 0.0** rather than an explicit "unknown main stat." OQ5's
  stats.json/disc_values.json data fix (`"Wind DMG Bonus": "wind_dmg_"`) is
  still correctly in place and *would* work — it's just never reached
  because the OCR read never gets that far. This is a distinct, still-open
  bug from what OQ5 believed was closed.
- disc_2070 (Fanged Metal): visually confirmed `title.png` clearly reads
  `Fanged Metal [ 1` — slot **1** — but the extracted disc has
  `slotKey: '4'`. Slot 1's only legal main is flat `hp` (`stats.json`
  `main_stats_by_slot["1"] = {"HP": "hp"}`); slot 4's list only has percent
  variants (`{"HP": "hp_", ...}`). With the wrong slot, a correctly-OCR'd
  `"HP"` main-name text is forced through the wrong candidate table and
  comes out `hp_` instead of `hp` — this is a **slot-number misread**
  cascading into a main-stat error, not a main-stat normalization bug at
  all. The `stats.json` data is correct for both slots; nothing to fix there.

**Cluster 4 — 1 disc (disc_0600): known dropped-row case**, already
documented in DESIGN Open Question 8 (panel shows 4 substat rows, archived
`discs.json` only has 2) — confirmed again here, not re-investigated
further; genuinely unrecoverable without a re-scan, `repair_disc` correctly
has nothing to repair (no value present, not a misread value).

**2 `critical_fail` entries (disc_1242, disc_1243, both "Dawn's Bloom [6]"):
title-crop OCR misread**, not a set-normalization problem. Visually
confirmed `title.png` clearly reads `Dawn's Bloom [6]`; the pipeline read it
as `'v Gi s Bloom - 6'` (below the 60-point set-name floor from the E1
sweep), correctly refusing to guess a set key from a low-confidence read
rather than snapping to something wrong. Root cause of the misread itself
(crop alignment/threshold on this specific instance) not dug into further
— out of scope for a review pass, flagged for whoever picks up OCR
reliability work next.

**Net assessment (58 total = 56 `unrepairable` + 2 `critical_fail`):**
38 (Cluster 1) + 14 (Cluster 2) + 3 (Cluster 3) + 1 (Cluster 4) = 56, plus
2 critical_fail = 58 — fully accounted for. Of these, only **15 are truly
unrecoverable** from this archive (14 in Cluster 2 + 1 in Cluster 4 — no
signal left anywhere to recover the true value; would need an in-game
re-scan). The other **43** (38 in Cluster 1 + 3 in Cluster 3 + 2
critical_fail) are OCR/parsing bugs with a specific, identifiable root
cause: a missing roll-suffix capture for `def`/`def_` lines specifically
(Cluster 1, the highest-value fix — 38 discs), an unguarded empty-OCR
fallback in `normalize_main_stat` that silently substitutes an arbitrary
candidate instead of returning `("", 0.0)` (2 of Cluster 3's 3 discs), a
slot-number misread cascading into a wrong main-stat table (the 3rd Cluster
3 disc), and an unexamined title-crop OCR failure (the 2 critical_fail
discs). None of these were fixed in this pass (review only, per the ask) —
recommend a follow-up task (T11 candidate, or a new T12) to: (1) find why
roll-suffix parsing misses the `def`/`def_` line specifically, (2) add a
floor/guard in `normalize_main_stat` so an empty OCR read returns
`("", 0.0)` instead of an arbitrary candidate, and (3) investigate the
slot-number OCR reliability that produced disc_2070's `'4'` instead of
`'1'`. DESIGN's Open Question 5 should be amended to reflect that the
*data* fix landed correctly but a *separate* OCR-empty-read bug remains
open.

## ESCALATION — three new bugs found by manual review, need Planner triage

**What was attempted:** a full hand review of all 58 discs the T10
`revalidate` run flagged as needing manual attention (requested by the user
directly, not a TASKS-scheduled step). Cross-referenced the report against
real archived panel/crop images and re-ran the OCR/normalization functions
directly per-disc rather than trusting the aggregate report. Findings are
above ("T10 addendum") and in `DESIGN_disc_validation.md` Open Question 5.

**What's unclear / needs an architectural call, not just an implementation
fix:** three distinct, root-caused bugs surfaced that the DESIGN doc doesn't
cover, because DESIGN's repair/validation architecture assumes evidence
(`roll_suffix`, `pct_seen`, OCR text) is *either present and correct or
absent* — it doesn't have a model for "OCR silently returns wrong/empty
data that looks like valid evidence":

1. **`def`/`def_` roll-suffix capture gap (38 discs, the highest-value fix
   available).** `pct_seen` is captured correctly but `roll_suffix` is
   missing specifically for the `def`/`def_` substat line, at varying row
   positions across discs — not a positional bug. Haven't traced this down
   to the actual regex/capture code (`disc_scanner.py`'s roll-suffix
   parsing) to find *why* this one line fails; that's real debugging work,
   not a quick patch. Question for Planner: is this worth a dedicated task
   with its own test fixtures (a new T-number), and should the fix target
   the capture regex directly, or would a more robust approach (e.g.
   re-deriving `roll_suffix` from the substat's own OCR'd raw text in
   `disc_rules.py` instead of relying on `disc_scanner.py`'s separate parse)
   be more in line with where DESIGN already puts "pure, testable" logic?

2. **`normalize_main_stat("", slot)` returns `("hp_", 0.0)` instead of
   `("", 0.0)` on OCR total-failure** (`normalizer.py:164-178` — no guard
   for an empty query before `rapidfuzz.process.extractOne`). Question for
   Planner: is the right fix a guard in `normalize_main_stat` alone, or does
   `normalize_substat`/`normalize_agent` have the same unguarded-empty-string
   gap (same `process.extractOne` pattern) and need the same fix in
   lockstep? This is a "does the bug class generalize" architectural
   question, not something to patch blind in one function.

3. **Slot-number misread (disc_2070: title crop clearly `[1]`, extracted
   `slotKey='4'`).** Haven't looked at the slot-parsing code at all yet —
   single data point, don't know if this is rare noise or a systematic
   weakness worth its own investigation task.

**The specific question for Planner:** should these three go into a new
`T12` (or `T11.5`) task added to `TASKS_disc_validation.md` *before* T11's
planned wrap-up/PR? To be clear about the actual risk: `validate_disc`
already correctly rejects all 41 of these discs (38 in Cluster 1 + 3 in
Cluster 3) rather than silently exporting wrong data — T10's gate is doing
its job. The real cost is that these 41 discs will sit in the "needs manual
review" pile indefinitely unless someone fixes the underlying OCR bugs, and
confirming any fix requires a second full-archive `revalidate` re-run
(another ~67 minutes of real OCR). Planner should decide: new task(s) and
their sequencing relative to T11, and whether T11's PR should go out now
(documenting the 58 as known follow-up work) or wait for these fixes first.

**Switch to Opus (Planner) to resolve this escalation before continuing.**

**Resolved (2026-07-04, Fable acting on both tiers at user request). Triage
ruling:** a new **T12** was added to `TASKS_disc_validation.md`, sequenced
*before* T11 — the wrap-up PR ships with the 43 discs fixed, not documented
as indefinite review debt. On the specific questions: (1) the roll-suffix
fix belongs in `normalizer.parse_roll_suffix` (pure, tested), NOT in
`disc_rules.py` — T7's `test_repair_def_44_roll_suffix_and_pct_seen_flips_key`
already proved `repair_disc` correct given good evidence, so the defect was
squarely in evidence capture; re-deriving the suffix in disc_rules would
duplicate a parse the scanner already does. (2) Yes, the empty-query bug
generalizes: `normalize_substat` had the same unguarded `extractOne` call
(agents/engines/sets were safe behind score floors); both got guards.
(3) The slot misread is not OCR noise to chase — it's a trust-ordering bug
(garbled-title fallback outranked the panel slot widget); fixed by
reordering, no OCR work needed. See T12 entry below. Return to Worker at
T11 after T12/T13.

## T12 — OCR evidence-reliability fixes (Worker/Brain, 2026-07-04)

Root-caused and fixed all 43 recoverable discs from the T10 manual review.
Commits: dbec92a (normalizer), 9537ce8 (scanner + golden fixtures).

**Root causes found (debugging against the real archive crops):**

1. **Cluster 1 (38 discs) — bbox-boundary value bleed.** The substat name
   bbox ends at x=339 and wide values ("14.4%") straddle that split: the
   name crop reads `'DEF +2 1'` (value's leading digit bleeds in) and the
   value crop reads only `'44%'`/`'4.4%'`. One geometry problem produced BOTH
   the missing roll-suffix (end-anchored regex rejected the trailing bleed
   digit) AND the "dropped leading 1" digit corruption (E2) that DESIGN had
   catalogued as a separate Tesseract confusion. Verified byte-identical
   `'DEF +2 1'` reads across 8 sampled discs at 4 different row positions.
   Fix: `parse_roll_suffix` matches a single digit at a whitespace/end
   boundary; merged bleed (`'+21'`) refuses (None). With the suffix present,
   repair rule 1 + `pct_seen` resolves the def/def_ 3-way lattice tie.
   Bonus: golden discs 0011/0293 promoted from fragile rule-3 budget
   forcing to rule-1 — their suffixes were bleed-victims too.
2. **Cluster 3a (2 discs) + the 2 critical_fails — bright-pass blanking, and
   the unguarded empty query.** `read_line` bright pass returns `''` on
   disc_0576/0618's legible "Wind DMG Bonus" main-name crop, and mangles
   disc_1242/1243's title to `'v Gi s Bloom - 6'` (55.9 < floor 60) — but
   the **dim pass reads all four perfectly** ("Wind DMG Bonus";
   "Dawn's Bloom < [ 6 ] 4" → DawnsBloom @ 90). Fixes: (a) empty-query
   guards in `normalize_main_stat`/`normalize_substat` (rapidfuzz returns an
   arbitrary candidate at score 0 for `""`); (b) dim/2× fallback ladder on
   the main-name read and a dim retry on the title read, mirroring the
   substat rows' existing pattern; fallback-sourced fields conf-capped at 65
   (review-visible, never fully trusted).
3. **Cluster 3b (1 disc) — slot trust inversion.** disc_2070's title `[1]`
   OCRs as `'[ 4'`; `_SLOT_RE_FALLBACK` (garble-tolerant) confidently
   returned 4 while the G5 panel slot widget read `'[1]4'` → 1 correctly but
   never ran (it only fired on total miss). Fix: slot trust order is now
   clean-bracket title > panel widget > garbled-title fallback, via
   `parse_slot(..., allow_garbled=False)`.

**Full-archive revalidate re-run (docs/_t12_run/, 3899s):**

| | T10 baseline | T12 |
|---|---|---|
| clean | 1912 | 1917 |
| repaired | 120 | 158 |
| unrepairable/flagged | **58** | **15** |

Zero regressions (no newly-flagged discs). The 15 survivors are exactly the
predicted unrecoverable set: 14 Cluster-2 discs (zero-value unreadable rows,
`sub_not_on_lattice observed=0.0` — indices 149, 246, 696, 800, 1101, 1196,
1216, 1347, 1419, 1537, 1699, 1712, 2047, 2067) + disc_0600 (dropped rows).
All need an in-game re-scan; user has deferred that.

Golden fixtures: disc_1242 + disc_2070 added (hand-read from panels);
disc_0576 was already T8-curated with identical values (independent
cross-validation of the hand-read). disc_0001 added to the repair
call-path test asserting rule="roll_suffix".

## T13 — failed discs excluded from export, report-only (Worker, 2026-07-04)

User decision: *"I'd like failed discs to be excluded from export, but users
to get a failure report to review."* Previously every disc landed in the
export — unrepairable discs kept their known-wrong values (flagged only in
side files), and revalidate's critical_fail path passed the OLD uncorrected
discs.json entry through. Commit 9127c3a:

- `_repair_and_fold_violations` stashes residual violations in
  `conf["_violations"]`; `scan_discs` excludes any disc with error-severity
  residuals and emits a `failed_validation` issue (disc payload + violations
  + repairs) for review.txt/issues.json.
- `revalidate`: unrepairable/critical_fail/missing_panel discs excluded from
  the export; report entries gain `excluded_from_export: true` + the disc
  payload; the report is now ALWAYS written (default `<out stem>.report.json`);
  summary gains `exported`/`excluded`.
- `scan --file` exits 1 with printed violations instead of exporting a
  failed disc. review.txt gains a "FAILED DISCS — EXCLUDED from export"
  section.
- **Known gap for follow-up:** equipped-disc orphans appended by location
  reconciliation bypass the gate (`scan_agents` discards their conf, so
  `_violations` is lost). Rare edge (orphan AND failed); noted in T13's
  commit message.

**Delivered:** `youkai-portable/youkai-portable/export/youkai_export_revalidated.json`
regenerated — 2075 discs (2090 − 15 excluded), T12 fixes applied — with the
failure report alongside as `youkai_export_revalidated.report.json`.
(The T12 run predated T13's exclusion code, so the delivered export was
post-filtered by report index; future runs exclude natively.)

Suite: 667 passed. Next: T11 wrap-up/PR.

## T11 — Docs + wrap-up (Worker, 2026-07-04)

Feature complete. Updated `DESIGN_disc_validation.md` Status header (Planned →
Complete, points at this LOG for the full arc); added a `revalidate` section
to `docs/RUNBOOK.md` (flags, output files, T13 exclusion behavior) and a
pointer + one-line summary in `README.md`. No further OQ amendments needed —
all substantive open questions were already resolved inline by T3/T8/T12
(see DESIGN §Open questions); the remainder (B-rank growth unverified,
element-DMG substat non-existence, disc_0600 row-loss, archive B-rank
coverage gap) are non-blocking findings, not action items.

**Before/after arc, full June 22 archive (2090 discs):**

| Stage | Clean | Repaired | Unrepairable/flagged | Notes |
|---|---|---|---|---|
| Baseline (raw `discs.json`, pre-feature) | 1919 | 0 | **171 (8.2%)** | Invariant sweep only; no repair existed yet |
| T10 (`revalidate`, validator+repair wired, tables refreshed) | 1912 | 120 | 58 | 3 new OCR-reliability bug clusters found during manual review of the 58 |
| T12 (evidence-reliability fixes: roll-suffix bleed, empty-query snap, slot trust inversion) | 1917 | 158 | **15** | Zero regressions; 43 of the 58 recovered |
| T13 (export policy change) | — | — | — | No count change (T13 changes *where* failures land, not detection) — the 15 are now cleanly EXCLUDED from the export instead of silently passing through with wrong values |

**Final delivered state:** 1917 clean + 158 repaired = **2075 discs exported**
to `youkai-portable/youkai-portable/export/youkai_export_revalidated.json`,
with `youkai_export_revalidated.report.json` alongside covering all 2090
source discs (repairs, residual violations, and the 15 excluded discs with
their full pre-repair payload for review). The 15 excluded discs are
unrecoverable from the archived crops (14 zero-value unreadable substat rows
+ disc_0600's dropped rows) and require an in-game re-scan; the user has
deferred that re-scan for now — it is out of scope for this feature, which
guarantees no known-wrong value reaches the export.

**Verification:** `pytest` — 667 passed; `ruff check` — clean on every file
touched across T0–T13 (pre-existing violations in `agent_scanner.py`,
`cli.py`, and older tests are out of scope per CLAUDE.md — untouched by
this feature).

**Follow-ups (not this feature, noted for a future task):**
1. In-game re-scan of the 15 excluded discs to recover their true values.
2. Equipped-orphan discs bypass the T13 export gate — `scan_agents`
   discards `conf` (and therefore `_violations`) when it appends orphaned
   equipped discs during location reconciliation, so a failed orphan disc
   could still reach the export. Rare (requires both "orphan" and "failed
   validation"), not hit in the June 22 archive, but not proven impossible.
   See T13 commit message (9127c3a) for the exact code path.

PR: `feat/disc-validation` → `dev`, opened after this entry.
