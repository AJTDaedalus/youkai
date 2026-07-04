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
