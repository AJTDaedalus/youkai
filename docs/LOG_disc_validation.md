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
