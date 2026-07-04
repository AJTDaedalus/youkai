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
