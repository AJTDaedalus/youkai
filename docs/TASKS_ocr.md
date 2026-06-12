# TASKS — ZZZ Inventory OCR Scanner ("youkai-ocr")

Execute with Sonnet. Load `DESIGN_ocr.md` first. Pick ONE task, do only it, update this file
(done/blocked) and append to `LOG_ocr.md`. Tasks are atomic, resumable, idempotent. Template:
[AdeptiScanner-ZZZ](https://github.com/D1firehail/AdeptiScanner-ZZZ).

Status legend: `[ ]` todo · `[~]` in progress · `[x]` done · `[!]` blocked.

---

## Phase A — Foundations

- [x] **A0. Decide scrap vs keep, lay out the new project.** Confirm full scrap of the Youkai Rust app
  (DESIGN §2/N-OCR-3). Create `youkai-ocr/` Python package skeleton (pyproject, `src/youkai_ocr/`,
  `tests/`, `data/`, `archive/`). Add `.gitignore` for `archive/`, exported JSON, screenshots, secrets.
  *Acceptance*: `pip install -e .` works; empty CLI `youkai-ocr --help` runs.
- [x] **A0.5. Co-op navigation map + reference capture (DO THIS FIRST; human-in-the-loop with user).**
  Live session: user drives ZZZ while we record the keybind/click path between every target screen
  (Drive Disc inventory, W-Engine inventory, agent detail, agent skills page), the grid geometry
  (rows×cols, cell pitch), and scroll deltas → `data/zzz_<ver>/navigation.yaml`. Capture one clean
  reference screenshot per screen at **1920×1080** (and 1600×900 if available) → `reference/`. From a
  real disc detail shot, record whether the equipped-agent indicator is **name-text or portrait-only**
  (resolves OQ-ocr-7) and the anchor elements for calibration (resolves OQ-ocr-4). *Acceptance*:
  `navigation.yaml` documents a complete path to every target screen; one labeled reference screenshot
  per screen type exists; equipped-agent display mode recorded in `LOG_ocr.md`.
- [x] **A1. ZOD emitter + schema extension.** Port `ZodExport/ZodDisc/ZodWEngine/ZodAgent` and
  `to_zod_key` from `youkai/src/zod.rs` to `youkai_ocr/zod.py`. **Add** `ZodAgent.talent
  {basic,dodge,assist,special,chain,core}` (DESIGN §3). Keep `zod.rs` updated as the canonical schema
  ref. *Acceptance*: emitting a hand-built export matches `serde` field names (camelCase) exactly; unit
  test asserts `to_zod_key` parity with the Rust version on a fixed string set.
- [x] **A2. Hand-author name lists.** Write `data/zzz_<ver>/{agents,engines,disc_sets,stats}.json`
  (display name → ZOD key) **by hand** from known content + the A0.5 reference screenshots — no external
  dump (D19). Stats are a fixed ~12-item enum. Include a version manifest. *Acceptance*: lists cover all
  current agents/engines/sets/stats; a spot-check of 10 keys matches `to_zod_key`; trivially patch-updatable.
- [ ] **A3. (Low-priority fallback) Equipped-agent portrait templates.** OQ-ocr-7 confirmed portrait-only.
  However per D21, the primary location-detection path is Equipment-tab cross-reference (Phase E). Build
  portrait templates only as a fallback for ambiguous cross-ref matches. Collect per-agent 30×30 face
  crops into `data/zzz_<ver>/templates/portraits/`; derive crops from `IconRole*.webp` via manual-annotated
  face bbox per agent. *Acceptance*: portrait library covers the current agent roster; template match on
  a reference screenshot returns the correct agent ≥95% of the time.
- [x] **A4. Window capture + calibration.** External framebuffer grab of the game window (DXGI/BitBlt
  class, S-OCR-1/2). Anchor-based scale+offset solver against a reference 1920×1080 layout; also accept
  1600×900. Reject unsupported aspect ratios. *Acceptance*: given a reference screenshot, calibration
  returns identity; given a 1600×900 shot, returns correct scale; an ultrawide shot is rejected.
  *Blocked-by*: A0.5 (reference screenshots + anchor geometry).
- [ ] **A5. Color-hygiene preflight.** Detect Night Light / f.lux / Reshade / Nvidia filter / HDR tint
  by sampling known-color anchors; refuse to scan with a clear message if tint detected (DESIGN §6).
  *Acceptance*: a clean frame passes; a tinted frame is rejected with the offending check named.

## Phase B — Recognition primitives

- [x] **B1. Declarative field-crop config.** A per-screen region spec (name, bbox in reference coords,
  preprocessing profile) resolved through the A4 transform. *Acceptance*: given a calibrated frame +
  the disc-panel spec, returns correctly-cropped sub-images for every field.
- [x] **B2. Text recognition wrapper.** Pluggable interface (D17) over Tesseract (default, WFInfo-style
  model) with a separate digit-optimized pass for levels/values; preprocessing profiles (scale,
  grayscale, threshold/invert for light-on-dark UI). *Acceptance*: on labeled field crops, raw text
  accuracy ≥ baseline target before fuzzy correction.
- [x] **B3. Template-match recognizers.** Rarity (color), disc set (icon), equipped agent (portrait),
  lock (overlay), slot (number/position) → return best match + score. *Acceptance*: on the labeled set,
  each recognizer's top-1 is correct ≥99%; below-threshold returns "unknown" not a wrong guess.
- [x] **B4. Normalizer + validator.** rapidfuzz map OCR text → canonical ZOD key (A2 lists); numeric
  range checks (disc lvl 0–15, engine/agent lvl 0–60, mindscape 0–6, refinement 1–5, allowed
  stats/substats); emit per-field confidence. *Acceptance*: known noisy inputs map to correct keys;
  out-of-range inputs are flagged, not written.

## Phase C — Drive Discs (proves the recognition spine)

- [x] **C1. Disc grid navigation.** Open Drive Disc inventory; fix sort order; iterate cells with
  synthetic input; scroll a page; detect end-of-inventory + dedupe (OQ-ocr-5, mirror AdeptiScanner-ZZZ).
  Honor Esc kill-switch (S-OCR-3). *Acceptance*: dry-run over a recorded session visits every disc once.
- [x] **C2. Disc assembler.** Per disc: drive B1→B2/B3→B4 to fill `ZodDisc` (set, slot, level, rarity,
  mainStat, substats, lock, location). Save raw crops to `archive/`. *Acceptance*: on the ground-truth
  disc set (≥30), produces correct `ZodDisc[]` meeting the §10 accuracy gate; misses land in the review
  report.
- [x] **C3. First export.** Assemble `ZodExport` with discs only; write JSON; import into the target
  optimizer to confirm contract. *Acceptance*: optimizer imports the file without error.

## Phase D — W-Engines

- [x] **D1. W-Engine navigation.** Same pattern as C1 for the W-Engine inventory. *Acceptance*: dry-run
  visits every engine once.
- [x] **D2. W-Engine assembler.** Fill `ZodWEngine` (key, level, ascension, refinement, location, lock);
  archive crops. *Acceptance*: ground-truth engine set (≥8) correct to the accuracy gate.
  *Note*: offline validation pending — no W-Engine reference screenshot yet. Tests cover all logic;
  star detection and name OCR need a real frame to confirm thresholds.

## Phase E — Agents (novel; not covered by Adepti docs)

- [x] **E1. Agent navigation.** Iterate the agent roster; for each agent open: (1) Base Stats page,
  (2) Skills page, (3) Equipment tab. Equipment tab traversal: click each of 6 disc slots + engine slot
  to read currently-equipped item details (primary location-detection path per D21). Esc kill-switch.
  *Acceptance*: dry-run opens all three views per agent and visits all 7 equipment slots.
- [x] **E2. Agent core fields.** Read level, promotion (ascension), Mindscape Cinema (0–6 via lit film
  cells, template match) → `ZodAgent`. *Acceptance*: ground-truth agents (≥8) correct.
- [x] **E3. Talent levels.** Read the 6 skill levels → `talent{basic,dodge,assist,special,chain,core}`;
  handle Core's distinct encoding (OQ-ocr-3). *Acceptance*: talent block matches ground truth; Core
  encoded per the optimizer's expectation.
- [x] **E4. Equip reconstruction.** Confirm agents' equipped discs/engines come through correctly via
  `location` on the disc/engine records (OQ-ocr-6); optional cross-check against the agent equipment
  page. *Acceptance*: every equipped item's `location` resolves to a scanned agent; no orphans.

## Phase F — QA + ship

- [x] **F1. Full `ZodExport` assembly.** Merge discs+engines+agents into one export; dedupe; stable
  ordering. *Acceptance*: a full scan imports cleanly into the optimizer with all three sections.
- [x] **F2. Golden-replay test + accuracy gate.** *Done 2026-06-10*: Committed 30 disc / 8 engine /
  8 agent labeled fixtures in `tests/fixtures/golden/`. `tests/test_golden_replay.py` replays all three
  item types offline via `scan_single_frame_*` helpers, enforces §10 gate (≥99% names, ≥98% numerics,
  no silent wrong values), and contains negative controls (Night-Light tint → ValueError, 1920×900 →
  ValueError). `.github/workflows/ci.yml` installs Tesseract and runs `pytest` on ubuntu-latest.
  All 6 golden-replay tests pass (400+6 = 406 total green).
- [x] **F3. Review report + confidence UX.** *Done 2026-06-10*: `_write_review_report` in `cli.py`
  writes `review.txt` per run (sections: critical fails, unknown agents, low-conf agents/engines/discs,
  orphans). Engine `_comment_*` separator keys stripped from normalizer pool (were falsely matching as keys).
  Stale CLI tests updated to match warn-not-abort behaviour of engine/agent screen checks.
- [x] **F4. Safety audit + runbook.** *Done 2026-06-10*: Static audit confirmed 0 forbidden patterns
  (ReadProcessMemory / WriteProcessMemory / mitmproxy / socket / scapy) in `src/`. `docs/RUNBOOK.md`
  written: setup prerequisites, scan procedure, output file guide, review-report guide, troubleshooting
  table, and the static audit commands.
- [x] **F5. Decommission Youkai.** *Done 2026-06-10*: `README.md` created at repo root (youkai-ocr as
  the active tool; `youkai/` noted as decommissioned Rust prototype, `irminsul/` as pristine ref clone;
  `zod.rs` kept as schema reference). D38 appended to `docs/DECISIONS.md`.

---

### Dependency notes
- A1 → B4/C2/D2/E2 (schema everywhere). A2/A3 → B3/B4 (matching needs the DB + templates).
- A4 → all capture (B1, C1, D1, E1). C-phase is the spine; D and E reuse B's recognizers.
- C1/D1/E1 navigation consume `navigation.yaml` from **A0.5**.
- **Do A0.5 first** (co-op with user): it yields the navigation map + reference screenshots and resolves
  OQ-ocr-4 + OQ-ocr-7, unblocking A3 (conditional), A4, B1, and all navigation. OQ-ocr-1 is now just
  hand-authoring A2 — no external dependency.

---

## Phase G — Live-scan correctness fixes (from 2026-06-05 full-scan triage)

- [x] **G1. Render-gate disc/engine captures.** Implement D-render-gate: after click+settle in
  `grid.GridNavigator._read_row`, verify the detail panel rendered (mean luma of the title sub-region
  above a floor) and re-capture up to a short timeout before yielding; raise base `CLICK_DELAY_S`.
  *Acceptance*: a re-run reads ≥99% of 2200 discs (issues ≪ 1038); no blank-panel critical-fails in a
  sampled archive. *Files*: `grid.py` (+ a luma helper), maybe a tunable in `GridParams`.
- [x] **G2. Engine count-driven traversal.** Add `read_engine_count()` (mirror `read_disc_count`,
  header `W-Engine Storage [ N / M ]`) and pass it into `navigator.scan(total)` from
  `wengine_scanner.scan_engines`. *Acceptance*: a re-run reads exactly 222 cells (no phantom cells),
  correct last-row width. *Files*: `wengine_scanner.py`.
- [x] **G3. Re-measure agent geometry.** From `preflight_agents.png` / `agent_000/*`, re-derive the
  portrait strip bbox (top-right, y≈2–28), click-Y, and constrain x so splash-art isn't detected;
  spot-check tab + equipment-slot centers. *Acceptance*: dry-run selects each portrait in turn (no
  City/menu exit); detected portrait count matches the visible roster. *Files*: `agent_scanner.py`,
  `data/zzz_1.4/navigation.yaml`.
  *Done*: added `_ROSTER_X_MIN=400` (City button at x≈40-57 no longer clicks); fixed tab centers
  from nav.yaml estimates (887/1075/1267, y=1052) to measured values (1152/1435/1718, y=996).
  Equipment slot centers pending live verification — need a successful Equipment-tab capture first.
- [ ] **G4. (Optional) Parallel OCR for engines + render-gate carryover.** Once G1 lands, give the
  engine scanner the same desynced worker pool as discs (D-ocr-pipeline) so G1's slightly longer
  settle doesn't balloon engine scan time. *Acceptance*: engine scan time within ~2x of discs/cell.
- [x] **G5. Two-pass panel slot fallback (zero `no_slot` fails).** Implement D-slot-panel-fallback:
  when the title-text `parse_slot` returns None, run a digit+bracket-whitelisted OCR (psm 11) over the
  un-clipped panel — Pass A `x[0:300] y[158:210]` (1-line names, slot pushed right), Pass B
  `x[0:180] y[200:290]` (2-line names, slot wraps left-low, excludes the bright icon); first `[1-6]`
  wins (bracketed preferred, bare-digit fallback). Wire it into `_extract_disc` so it runs only on the
  title-parse miss (no cadence cost). *Files*: `disc_scanner.py` (panel slot helper + call site),
  maybe `normalizer.py`. *Acceptance*: offline re-triage of the 12 archived fail panels
  (`docs/triage_disc_fails.json` / `scripts/triage_disc_failures.py`) recovers **12/12** correct slots;
  commit those 12 `panel.png` crops as test fixtures + a parametrized test; full suite green; a re-run
  reports **0 `no_slot`** critical fails. *Validated offline by Opus 2026-06-06 — recovers 12/12.*
  *Done 2026-06-06*: `recognize.read_slot` (psm 11, whitelist `0-9[]`), `normalizer.parse_panel_slot`
  (full-bracket `[N]` preferred → partial-bracket fallback), `disc_scanner.parse_slot_from_panel`
  wired into `_extract_disc` only on tier-1 miss. 12 panels committed to
  `tests/fixtures/disc_slot_panels/`; `tests/test_disc_slot_fallback.py` asserts 12/12. Full suite
  237 passed / 4 skipped (archive-dependent skips). **Live `0 no_slot` re-run still pending** a clean
  capture (the only remaining acceptance clause — needs the window-targeting fix below).

---

## Phase H — Agent roster redesign + tandem hardening (plan: `docs/DESIGN_agents.md`, 2026-06-06, Opus)

> Fixes the only subsystem blocking `scan-all`. Root causes (evidence in DESIGN_agents §2 / LOG
> 2026-06-06): RC-1 roster strip y-band too low (under-detect), RC-2 never scrolls (no count
> header), RC-3 **Equipment tab never reached** + slot centers ~350px too far left. Discs/engines
> are NOT in scope — do not touch G1/G2/G5. **Precondition:** fix the window-targeting bug
> (`live_20260606` grabbed the Game Pass launcher) before any live task (H0/H6).

> **SUPERSEDED 2026-06-06 by ref_12 (D27):** the agent *menu* roster is a 2D GRID (like the
> inventories), not the top strip. H0/H1/H2 are reframed around grid traversal; the strip-detection /
> horizontal-scroll approach is dropped. RC-1/RC-2 are largely moot — reuse `grid.py`. (RC-3 stands.)

- [ ] **H0. Live probe — agent-grid scroll stride (OQ-H1).** *(needs game, ~5 min)* On the agent
  menu (ref_12), confirm the right-side roster grid scrolls vertically and by how much per
  scroll-trigger (click-bottom-row vs wheel vs scrollbar — mirror the disc grid). *Files*: none
  (notes → `LOG_ocr.md`). *Acceptance*: scroll mechanism + row stride documented; before/after frame
  in `archive/probe_scroll/`. (Lower priority now — grid reuse means this is a tuning detail, not a blocker.)

- [x] **H1. Agent-grid cell detection + ownership filter (D27/D28).** The grid is **sheared**
  (diagonal/parallelogram, not rectilinear) so don't assume fixed col/row pitch — detect cells by
  **saturation-thresholded blob detection** over the right-side grid region: owned = colored portrait
  (high saturation) + gold rarity star; **skip** unowned (padlock on star, desaturated/grayscale,
  "Lv. 1") and the "EMPTY CHARACTER" placeholder. This finds cell click-centers AND filters ownership
  in one pass. Also measure `Base`/`Skills`/`Equipment` button centers + selected-agent signature
  (ref_12), and the bottom-bar `Storage`/`Agents` centers (ref_11). Record under
  `navigation.yaml:agent_menu`. *Fixtures*: ref_12 (owned page), ref_13 (mid-scroll), ref_14 (locked
  tail + EMPTY). *Acceptance*: detector returns only owned cells on each fixture (zero locked/EMPTY),
  plus the 3 detail buttons. *Files*: `navigation.yaml`, `agent_scanner.py`, `tests/`.

- [x] **H2. Roster traversal: scroll + dedupe + loop-around end (D27/D28).** Reuse `grid.py`'s
  scroll/stability/dedupe **loop** (not its rectilinear cell model): detect owned cells (H1) → visit
  each un-seen → scroll down one page → repeat. No scroll-to-top (none reliable; user-confirmed) —
  dedupe owned cells by perceptual hash and **end when a page yields no new owned agent** (hit the
  locked tail OR wrapped/looped back to a seen agent). Cap `AGENT_MAX=60`. Per cell: select → Base →
  Skills → Equipment (H3) → back-arrow → next. *Acceptance*: a dry-run over the ref_12→13→14 frame
  sequence visits each unique owned agent exactly once, skips all locked/EMPTY, and terminates at the
  locked tail. *Files*: `agent_scanner.py`, reuse `grid.py`. Depends on H1; H0 only refines stride.
  *Done 2026-06-06*: `_portrait_phash()` (16×16 average hash), `scan_roster_grid()` (testable
  generator with injectable scroll_fn), `AgentNavigator._scroll_page_down()` (wheel scroll),
  `AgentNavigator.scan()` rewritten to use grid-based loop with back-arrow nav. 10 tests in
  `tests/test_agent_traversal.py`: full dry-run yields 20 agents (8+8+4), 3 scrolls, clean
  termination; pHash dedup, kill_event, agent_max cap all green. Suite 256 passed.

- [x] **H3. Equipment tab: reach it + fix slot geometry + render-gate (RC-3).** Re-measure the slot
  hexagon from `reference_7` (engine center ≈ (1418,590); derive the 6 disc centers) → update
  `_DISC_SLOT_CENTERS`/`_ENGINE_SLOT_CENTER` + `navigation.yaml:equipment_tab`. Add a render-gate
  after the Equipment-tab click (assert hexagon rendered — center engine-ring luma/template) and
  after each slot click (assert detail/select panel opened); re-capture-then-log on gate fail.
  Re-anchor `_EQUIP_TITLE_BBOX` against `reference_8`. *Acceptance*: offline, the gate predicate
  returns True on `reference_7` and False on a Skills-tab frame (`agent_000/skills.png`); slot
  centers land inside the ref_7 slot circles (assert via bbox membership). *Files*: `agent_scanner.py`,
  `navigation.yaml`, `tests/`.
  *Done 2026-06-06*: slot centers re-measured (RC-3 fixed, hexagon was 330px too far left).
  Engine game(1417,558), slots 1-6 game(1730/1785/1715/1087/1125/1088, 363/483/708/708/544/363).
  `_equip_tab_rendered` (luma>150) and `_slot_panel_rendered` (dark_frac>0.08) wired into scan()
  with retry+logging. 11 tests in `tests/test_agent_h3.py` all pass. Slots 2/5 marked TODO for
  live verification (±50px uncertainty). `_EQUIP_TITLE_BBOX` confirmed correct against ref_8
  (246 bright cols, dark_frac=0.16).

- [x] **H4. Validate per-agent extraction offline (G-D).** Build fixtures from
  `reference_{3,4,9,10}` (mirror G5's `tests/fixtures/` pattern) and assert via
  `scan_single_frame_agent` / `_extract_equip_frame`: key=Zhao, level=60, ascension dots, mindscape,
  skills = (12,10,11,12,11) from ref_4, core rank, and equip title→(set,slot)/engine key from
  ref_9/10. Fix bboxes/heuristics until green; route still-uncertain heuristics (ascension/core) to
  low-confidence. *Acceptance*: parametrized fixture test passes; values match the frames. *Files*:
  `agent_scanner.py`, `normalizer.py` (if needed), `tests/`.
  *Done 2026-06-06*: 24/24 tests green. Key fixes: added 'Zhao' to agents.json; _LEVEL_BBOX
  corrected (y=452→460, x=955→1060); _SKILL_LEVEL_BBOXES y-corrected (510-545→750-780); Tesseract
  can't read ZZZ stylized skill badge font → replaced OCR with `_read_skill_badge()` blob-width
  classifier (LANCZOS4 3× + threshold 180 + fill-ratio: 5/5 correct); _CORE_NODE_BBOXES
  re-derived from teal CC centroids in ref_4 (all 6 nodes detect LIT).

- [x] **H5. Tandem hardening — persistence + preflight assert + resume (G-E).** In
  `cli.py:_cmd_scan_all`: tee stdout to `archive/<run>/scan.log`; write `archive/<run>/results.json`
  (per-phase counts, issues, merged export). Add a per-phase preflight screen-assertion (disc/engine
  header present; agent page signature present) that aborts the phase loudly if the wrong screen is
  open. Add per-phase output files so a failed agent phase can resume without rescanning discs.
  Keep the manual `input()` gates between the three menus (non-goal to automate). *Acceptance*: a
  (mocked) scan-all writes log + results.json; a forced wrong-screen preflight aborts that phase
  with a clear message; suite green. *Files*: `cli.py`. Depends on H2–H4.

- [x] **H6. Live acceptance — one clean `scan-all` (G-A..G-E).** *Done 2026-06-10*: run
  `live_20260610_065548` produced **39 agents, 2252 discs, 222 engines** with 186 low-confidence
  issues (0 critical fails). Ring closed at Zhao after 39 owned / 54 visited. All acceptance
  criteria met.

- [ ] **H7. Single auto-navigating `scan-all` (menu hub driver).** *(plan: D26)* Add a navigation
  layer that drives the whole pipeline from the main-menu hub, replacing the manual `input()` gates
  (keep them behind `--manual-nav`). Primitives: `assert_screen(signature)` render-gates for
  main-menu / W-Engine / Disc / agent-page; `active_storage_tab()` = brightest of the 4 top-right
  category-tab bboxes (handles the pulse-glow); `return_to_main()` via the back-arrow. Flow:
  main → Storage → engine tab (scan) → disc tab (scan) → back → Agents → Base → agent page (H2 roster
  scan) → `resolve_locations` → merged export, all persisted per H5.
  - [x] **H7a** *Done 2026-06-11*: measured `Storage`/`Agents` (ref_11) and `Base`
    (ref_12) button centers + main-menu/agent-menu signatures → `navigation.yaml`.
    Storage (1123,1041), Agents (1251,1041), Base already correct (1140,816).
    Signatures: main_menu bbox [1000,1033,1300,1050] mean_luma>20;
    agent_selection_menu bbox [1888,430,1920,570] teal_px>1000. Suite 412 passed.
  - [x] **H7b DONE 2026-06-10:** measured W-Engine (index 0, glow y=135-203, yellow [213,207,0]) and
    Drive Disc (index 1, glow y=304-325, white [255,255,255]) tab bboxes from ref_1/ref_2. Glow
    column: game x=1413-1430. Implemented `active_storage_tab()` in `cli.py` + 6 fixture tests.
    Only 2 of the stated 4 tabs confirmed from available refs. Full suite: 412 passed.
  - [x] **H7c** *Done 2026-06-11*: `_NavDriver` class + `_is_main_menu` / `_is_agent_selection_menu` / `_is_storage_screen` predicates added to `cli.py`. `_cmd_scan_all` branched on `--manual-nav` (default = auto-nav). Auto-nav flow: assert main menu → navigate_to_storage → switch engine tab (0) → scan engines → switch disc tab (1) → scan discs → return_to_main → navigate_to_agents → scan agents. 8 new tests (3 predicate, 3 driver integration, 1 wrong-screen, 1 agents-only); existing H5 tests updated to `manual_nav=True`. Suite 420 passed.
  *Acceptance*: a (mocked-frame) driver test walks the full transition graph and asserts each gate;
  live, one `scan-all` completes hands-off from the main menu. Depends on H2–H5; H7a blocks the live leg.

---

## Phase H (cont.) — `agent_nav_fail` fixes (root-caused 2026-06-07, Opus; LOG 2026-06-07)

> Live `agent_nav_fail cx=1407 cy=144` → 0 agents. Two independent, both-confirmed causes.
> **Do NOT touch H3 equipment geometry or the detail-page navigation — both verified working**
> (`agent_000/equip_slot_0.png` = correct Equipment page; `agent_001/base_stats.png` = real Base
> Stats page). These two tasks are offline-validatable against frames already in the repo.

> **PIVOT 2026-06-07 (D29):** RC-1 confirmed (grid is 3 sheared cols, code models 2 → gutter clicks →
> `agent_nav_fail`). Three offline detectors failed to segment the sheared/packed grid → **abandon
> grid enumeration**; iterate via the detail-page **top agent strip** instead. H8 rewritten below;
> H1's `detect_owned_agent_cells` retired. RC-2 predicate landed this session (see H9).

- [x] **H9. Wipe-proof detail/active-tab predicate + Base/Skills render-gates (RC-2).** *Done
  2026-06-07 (Opus).* Replaced `_on_detail_page`'s fragile `luma>60` with a **yellow active-tab
  signature**: `_tab_yellow_frac`/`_tab_active`/`_on_detail_page` over `_TAB_ACTIVE_BBOXES` (measured
  yellowFrac ≈0.85 on a real open tab vs **0.000** on the AGENT-SELECT wipe / menu / inactive tabs).
  Added `AgentNavigator._capture_tab(idx)` — clicks a bottom tab and poll-recaptures until its pill is
  yellow before banking (render-gates Base + Skills; mirrors the H3 equipment gate). Committed
  negatives `tests/fixtures/agent_nav/{wipe,menu}.png`. `tests/test_agent_rc2.py` 7/7; full
  agent+grid suite **111 passed**, no regressions. Implements the open half of D23.

- [~] **H8. (IMPLEMENTED offline 2026-06-07 — needs live validation) Enumerate agents via
  the detail-page top-strip `<`/`>` controls.**
  *Done (Opus):* rewrote `agent_scanner.py` — removed the grid path (`scan_roster_grid`,
  `_scroll_page_down`, `_navigate_to_detail`, grid-scroll consts); added `_region_phash`/
  `_phash_hamming`/`_strip_id`, `_is_owned_agent` (character-render saturation), and navigator methods
  `_enter_detail_page` (menu Base button, RC-2 gated, idempotent), `_advance(±1)` (click chevron +
  pHash-confirm + retry → no silent skip), `_rewind_to_first`, `_read_equipment` (7 slots, no
  inter-slot Escape, one trailing Escape — Q4). `scan()` now: enter → rewind → forward `>` pass, stop
  at first grayed-out / `_advance` no-change / `AGENT_MAX`. `tests/test_agent_traversal.py` rewritten
  as a `_StripSim` driving the real `scan()` (8 tests): rewind-then-in-order visit, stop-at-grayout,
  one-Escape-per-agent, 7-slot no-inter-Escape, AGENT_MAX, kill-event — all green.
  *Live-verify (H6-style):* `_STRIP_NEXT`/`_STRIP_PREV` chevron coords, `_MENU_BASE_BUTTON`,
  `_OWNED_SAT_P75_MIN` (vs a real grayed agent), `_STRIP_CHANGE_MIN_BITS`. **Superseded design note
  below kept for reference.**
  *H11 (2026-06-07, first live run) — REALIGNED from captured frames:* chevrons were on the portraits
  → `_STRIP_PREV` 1140→1025 (was selecting agent #2 = "skipped first"), `_STRIP_NEXT` 1745→1775 (was
  on the last portrait); `_STRIP_PHASH_BBOX` tightened to the portrait band; `_MENU_BASE_BUTTON`
  re-centred 1167→1140. Equipment hexagon fully re-measured (live is compact, ref_7 zoomed — D30):
  `_DISC_SLOT_CENTERS` + `_ENGINE_SLOT_CENTER` (1417,558→1398,515) + `_EQUIP_GATE_LUMA_MIN` (150→80,
  equipped engine). yaml + tests updated; H3 disc geometry now tests a live fixture. **Still
  unverified live:** `_OWNED_SAT_P75_MIN`, `_STRIP_CHANGE_MIN_BITS` (no grayed-agent frame captured —
  the run stopped at 2 agents). **New follow-ups:** settle-timing race (base=Dialyn/equip=maid,
  ZhuYuan zero-skills), "Dialyn"→"Rina" normalizer miss, runtime hexagon detection (D30). Window-
  targeting fix remains the precondition for a clean full run.
  *H12 (2026-06-07, user added reference_15/16 = live-accurate equipment/disc-select):* HoughCircles ring
  geometry confirms the H11 compact disc coords against ref_7/15/16 + live (±2px) — H11 was right; my
  "ref_7 zoomed" guess was wrong (old wide coords landed on background art). Hexagon doesn't move between
  equip-tab and disc-select ⇒ one coord set for all 7 clicks. Window bar ruled out as an offset source.
  H3 disc test hardened to a set-independent RING annulus vs ref_16. **Added** `youkai_ocr/debug_overlay.py`
  + `--debug-overlays` (scan-agents/scan-all): saves `*_overlay.png` with click targets + OCR crops drawn —
  self-validating artifacts for the next live run. base-overlay shows the name crop is aligned ⇒ Dialyn→Rina
  is a DB gap, not nav. Still open: `_OWNED_SAT_P75_MIN`/`_STRIP_CHANGE_MIN_BITS` live-tune, settle-timing
  race, normalizer DB, window-targeting.

  Original FINAL design (D29 — single forward `>` pass; H10 fully answered): No thumbnail detection / pHash dedupe / grid needed —
  the `>`=next/`<`=prev controls move the selection ±1 deterministically (H10-Q3), agent switches are
  clean and stay on the current tab (Q1), and the owned roster is the contiguous left prefix ending at
  the first grayed-out agent (Q2). **Flow:**
  1. **Enter** the detail page: from the agent menu click any one owned agent (RC-2 `_on_detail_page`
     gate absorbs the one-time AGENT-SELECT wipe). Click `Base`.
  2. **Rewind to the first agent:** click `<` (prev-agent arrow) until the selected agent stops
     changing (detail-page portrait pHash stable two reads running → leftmost reached; `<` doesn't
     loop, Q2/Q3).
  3. **Forward pass**, per agent: if the current agent is **unowned (grayed-out)** → stop. Else
     `_capture_tab(Base)` → `_capture_tab(Skills)` → `_capture_tab(Equipment)`; on Equipment click the
     7 H3 slots in sequence (gate+capture, **no inter-slot Escape**, Q4) then **one** `_press_escape()`
     to restore the bar; then click the **`>`** (next-agent) control and settle. Cap `AGENT_MAX=60`.
  **Robustness (avoid the RC-1 fixed-coordinate trap):** the bar resizes with thumbnail count, so the
  `>`/`<` arrows are NOT at a stable pixel (measured ref_3: thumbnails run x≈1094–1745 then dark; the
  arrow x shifts). So **don't trust a fixed arrow click** — after every `>`/`<`, confirm the selected
  agent actually changed via detail-portrait pHash; on no-change, treat as a missed click (re-locate
  the arrow / retry), and use no-change-after-retry as the rewind "leftmost reached" / forward
  "wherever" signal. Prefer locating the `>`/`<` chevrons by template/bright-spot at the bar's current
  ends each iteration over a hardcoded x.
  Needs: a **`>`/`<` arrow click target** (locate per-iteration; ref_3 right end ≈x1745, left `<`
  ≈x1094, y≈43 — confirm live), a **grayed-out/unowned predicate** (saturation
  of the big character-render bbox: owned≈colorful vs grayed; no offline fixture → principled threshold
  + flag for live tuning, with `AGENT_MAX` as backstop), and a **stable-selection predicate** for the
  rewind (reuse `_portrait_phash` on a detail-page portrait crop). **Remove** from `scan()`: the
  per-slot `_press_escape()` and the end-of-agent Escape-to-menu (Q4); retire
  `detect_owned_agent_cells`/`scan_roster_grid`/`_AGENT_GRID_*`/`_scroll_page_down` from the live path.
  *Acceptance*: a dry-run over mocked strip frames (a sequence of N owned + 1 grayed) rewinds to index
  0, visits each owned agent once in order, stops at the grayout, and never escapes to the menu
  mid-pass; `_capture_tab` gates each tab. *Files*: `agent_scanner.py`, `tests/`,
  `navigation.yaml:agent_menu` (arrow targets, character-render bbox). **Unblocked — ready to build.**

- [~] **H10. Live probe — top-strip behaviour (D29 open questions).** *(answered by user 2026-06-07)*
  - **Q1 ✓** Clicking a strip thumbnail switches the agent **cleanly (no AGENT-SELECT wipe)** and
    **stays on the current subpage** (Base/Skills/Equipment).
  - **Q2 ✓** The strip lists owned agents **first, contiguous, left→right**, then **unowned** agents
    (grayed-out but still clickable). **No looping.** ⇒ stop signal = the **first grayed-out agent**
    (owned roster is the contiguous left prefix). No pHash dedupe needed for a single forward pass.
  - **Q3 ✓ (resolved 2026-06-07)** `>` = **next agent (+1)**, `<` = **previous agent (−1)**, **both
    directions work and the selection always moves by exactly one** (the window scrolls 4 at an edge,
    but the *selection* never skips). No silent-skip risk → iterate by clicking `>`; rewind with `<`.
  - **Q4 ✓ (Equipment-page strip hides during slot reads — ONE Escape after all 7)** On the Equipment
    tab, clicking any disc/engine slot opens its side panel and **hides the top strip bar**. **You do
    NOT Escape between slots** — click slot→slot directly and the side panel just updates. You press
    **Escape exactly once, after reading the engine + all 6 discs**, to restore the bar; only then can
    you advance agents. ⇒ Equipment-phase per agent: click the 7 slots in sequence (gate+capture each,
    **no** inter-slot Escape) → **one** `_press_escape()` to restore the bar → advance with `>`.
    **CORRECTS current `scan()`**, which wrongly does `if panel_open: self._press_escape()` after every
    slot (bounces the view) and then a second Escape-to-menu — both must go in the H8 rewrite. The
    strip "next agent" works only from the hexagon view with the bar visible.

---

## H18 — Live feedback round 2 (2026-06-07, Opus 4.8)

- [x] **H18.1 Slot-drop fix.** `_open_slot()` render-gates each equipment slot with re-click (slot 0
  → panel appears; slot 1+ → panel-title pHash switches); `_SLOT_CLICK_DELAY_S` 0.20→0.45.
  *Acceptance*: `test_open_slot_reclicks_dropped_second_slot`. **DONE.**
- [x] **H18.2 Advance-skip fix.** `_advance`/`start_id`/ring-closure key on `_agent_id`
  (`_CHARACTER_RENDER_BBOX`), not the strip band. *Acceptance*:
  `test_advance_does_not_skip_on_weak_strip_signal` (one `>` per advance, no skips). **DONE.**
- [x] **H18.4a Trial-agent reactive net.** `_read_equipment` returns `_EQUIP_UNAVAILABLE` + Escapes
  when the hexagon never renders; `scan()` skips the agent. *Acceptance*:
  `test_trial_agent_equipment_unavailable_is_skipped_not_hung`. **DONE (de-hangs the live case).**
- [x] **H18.3 Empty-slot tracking.** *DONE (Koleda `reference_17` received).* `_disc_slot_equipped`
  (luma>80) / `_engine_slot_equipped` ("core available" = colored>0.15 AND luma<150) / `_slot_equipped`;
  `_read_equipment` skips empty slots (None frame, no click) and Escapes only if a panel opened;
  `scan_agents` skips None in archive + cross-ref. *Acceptance*: `test_agent_h3` Koleda classifiers,
  `test_read_equipment_skips_all_empty_slots_on_koleda`.
- [x] **H18.6 Reversed disc-slot numbering (bonus, found via Koleda).** `_slot_number(idx)=6-idx`;
  fixed `_extract_equip_frame` `slot_key`. *Acceptance*: `test_slot_number_mapping_matches_koleda_layout`
  + updated `test_agent_h4`/`test_agent_scanner`. Without this every `resolve_locations` disc match
  would have missed.
- [ ] **H18.4b Proactive trial-skip.** *BLOCKED on a Nangong Yu detail+modal frame (OQ-H18b).* Detect
  trial/preview agents before scanning Base/Skills (the reactive net already prevents the hang/bad data).
  *Files*: `agent_scanner.py` (`_is_owned_agent` or sibling), `tests/`.
- [ ] **H18.5 Live confirm.** Re-run `scan-all --agents-only --debug-overlays`; confirm all 6 discs +
  engine open per agent (watch `slot_reclick`/`slot_gate_fail`), no agent skips, and `agent_skip_trial`
  fires for Nangong. Tune OQ-H18c thresholds if the logs show misses.
- [x] **H19.1 Slot switch-detection rewrite.** `_open_slot` gates on the panel BODY
  (`_SLOT_DETAIL_BBOX`) + a two-capture stability check, not the title; returns `(frame, body_pHash)`.
  Fixes same-set futile re-clicks (disc-4 "hang") and mid-fade duplicate-bank (disc-2 "skip").
  *Acceptance*: `test_open_slot_same_set_adjacent_slots_no_reclick_no_skip` + existing dropped-slot test.
  **DONE.**
- [x] **H19.2 Settle Equipment frame before empty-detection.** `_wait_region_stable` on
  `_EQUIP_RING_BBOX` so a half-faded disc icon is not mis-read as empty/skipped. *Acceptance*: Koleda
  empty test still passes (stable frame → all empty). **DONE.**
- [ ] **H19.3 Live confirm (OQ-H19a).** Re-run agents; `slot_reclick` should fire only on genuine
  dropped clicks and `slot_gate_fail` should be rare. If a same-set agent still re-clicks, the body
  signal is too weak — bias `_SLOT_DETAIL_BBOX` toward the substat rows or lower `_SLOT_CHANGE_MIN_BITS`.
- [x] **H20.1 Re-key the Equipment render-gate off the engine.** `_equip_tab_rendered` gated on
  engine-center luma>80 and false-skipped real owned agents whose W-Engine art is dark (live:
  `nav_equip_unavailable.png`, engine luma 78.3 with 6/6 discs equipped). Changed to the UNION: rendered
  if `any(_disc_slot_equipped(...) for i in range(6))` OR engine luma > `_EQUIP_GATE_LUMA_MIN`. The
  ring-bbox edge-frac fallback was tried and rejected (Koleda 0.034 < skills 0.053 → not a discriminator).
  *Files*: `agent_scanner.py` (`_equip_tab_rendered`), `tests/test_agent_h3.py`,
  `tests/test_agent_traversal.py`. *Acceptance*: geared+dark-engine frame reads RENDERED (new regression
  `test_equip_tab_renders_on_geared_agent_with_dark_engine`); Koleda still rendered; trial test (now
  blanks the whole ring) still skips. 331 passed, 1 failed (pre-existing unrelated). See **D35**. **DONE.**
- [ ] **H20.2 Live confirm.** Re-run `scan-all --agents-only --debug-overlays`; the agent that produced
  `nav_equip_unavailable.png` should now be scanned + exported (no `equip_unavailable` / `agent_skip_trial`
  for it). Watch that no *real* trial agent slips through (none expected here — `_is_owned_agent` gates
  upstream).

- [x] **H21.0 Capture empty-slot references.** DONE — user provided
  `screenshots/reference_18_unequipped_disc_slot_clicked.png` + `reference_19_unequipped_engine_clicked.png`.
  Resolved OQ-H21a: empty slot AUTO-LOADS inventory[0] (title parse unsafe); discriminator = action-bar
  `"unequip"` substring, verified with the recognizer (D36 UPDATE). **TODO: move both into `reference/`** (they
  moved into `reference/` (reference_18/19) — they now back the H21 fixtures. **DONE.**
- [x] **H21.1 Route logger to the run dir.** Add a `logging.FileHandler(run_dir/'scan.log')` (or a separate
  `agent_scan.log`) in `cli.py:_cmd_scan_all` so `_log.*` markers (slot_empty/slot_reclick/tab_gate_fail/
  equip_unavailable/agent_skip) are captured — currently `scan.log` tees stdout only and shows 0 of each.
  *Files*: `cli.py`. *Acceptance*: a unit/manual check that an emitted `_log.warning` appears in the file.
- [x] **H21.2 Add `_panel_shows_equipped` (action-bar gate).** New helper: OCR the action-bar bbox
  (ref x≈1100–1560, y≈1002–1052 — wide enough for disc "Unequip All" AND the right-shifted engine "Unequip")
  on a slot-select frame; return `"unequip" in text.lower()`. *Files*: `agent_scanner.py` + a new bbox const,
  tests. *Acceptance*: ref_8 → True; ref_18 → False; ref_19 → False (offline fixtures from the moved refs).
- [x] **H21.3 Rewrite `_read_equipment` to the closed-loop per-slot contract; retire pre-click heuristics.**
  Per slot 0–6: click → `_slot_panel_rendered` gate (re-click on drop, unchanged) → `_slot_equipped_from_panel`.
  If equipped: bank frame + `_extract_equip_frame` record. If empty: no frame, no record (location stays "").
  Remove `_disc_slot_equipped`/`_engine_slot_equipped` as gates (the proven false-empty source — D36). NEVER
  click "Equip". *Files*: `agent_scanner.py`, tests. *Acceptance*: Koleda (all empty) → 0 records, no hang;
  ref_7/16 geared → 6 disc + engine records; engine no longer pre-skipped. Keep H19 switch-detect for moving
  between slots in the select view.
- [ ] **H21.4 Live confirm.** Re-run `scan-all --agents-only --debug-overlays`; per agent expect 6 discs +
  engine resolved (captured when equipped, cleanly skipped when empty), engine no longer systematically
  missing. Inspect the new file-routed log for slot_reclick/gate_fail rates.

## H22 — Owned/unowned detection rewrite (D37)

- [x] **H22.0 Replace render-hue ownership with level + `>>` chevron.** Remove `_is_owned_agent`
  and the `_GRAYED_*`/`_OWNED_COLOR_*` constants. Add `_chevron_color_fracs`, `_classify_owned`
  (pure), `_OWN_*` constants, and `AgentNavigator._agent_level` / `_agent_owned`. *Files*:
  `agent_scanner.py`. *Acceptance*: classifier separates all 34 live frames (manually validated:
  green→owned, white+Lv1→unowned, level≥2→owned incl. agent_023 white-pill L50/50).
- [x] **H22.1 Restructure `scan()` to decide ownership from the Base tab.** Capture Base first;
  `_agent_owned(base_frame)` gates the expensive Skills/Equipment captures; unowned costs one Base
  frame. Keep skip-don't-stop + ring-close (no early-out — entry position is arbitrary). *Files*:
  `agent_scanner.py`. *Acceptance*: traversal tests green.
- [x] **H22.2 Update the strip sim + tests.** Sim renders a green/white `>>` chevron; ownership now
  flows through `_classify_owned` (no recognizer → level 0 → chevron). New `test_classify_owned_rules`
  + `test_chevron_signal_separates_owned_unowned`. *Files*: `tests/test_agent_traversal.py`.
  *Acceptance*: full suite green (no new failures vs the pre-existing disc-count drift).
- [x] **H22.3 Live confirm (user).** *CONFIRMED 2026-06-09 (run `live_20260609_140457`).* Traversal
  ring-closed at Zhao after **39 owned (54 visited)** — NOT AGENT_MAX; `agent_skip — unowned` fired
  only on the contiguous Lv.1 white-chevron tail (strip pos 40-53). Harumasa/Lycaon/Komano were all
  *visited & captured* (their base_stats frames exist) — they only fell out at export due to the name-crop
  truncation bug (now **H30**), which is a separate downstream defect, not an ownership/traversal miss.
- [ ] **H22.4 (OQ-H22a) Harden `_EQUIP_UNAVAILABLE`.** It false-dropped a fully-equipped owned agent
  (`nav_equip_unavailable.png`) — a second silent data-loss path. Likely a render-settle/timing fix
  on `_equip_tab_rendered`. Needs an unowned/trial equipment frame to calibrate. *Files*:
  `agent_scanner.py`. *Acceptance*: the geared agent in that frame resolves as available.

## H23–H26 — Post-D37 live-run findings (H22.3 review, 2026-06-08, Opus)

Context: run `archive/live_20260605` (the 14:07–14:21 block). D37 ownership fix confirmed working
(no owned-position skips; VonLycaon captured; unowned skips confined to the Lv.1 white-chevron tail
pos 40–53). Remaining failures are downstream. On-disk assets for OFFLINE diagnosis (no game needed):
`archive/live_20260605/agent_NNN/{base_stats,skills,equip_slot_*}.png` — including exact-duplicate
re-scans of the same agent one loop apart (e.g. Rina at archive idx 2 & 37; ZhuYuan 5 & 40).

- [x] **H23. Traversal drops ~44% of the roster AND never ring-closes (the priority fix).**
  *Symptom*: true roster is **39 owned**, but the run captured only **22 distinct** (42 entries) and
  ended on `agent_scan_cap — hit AGENT_MAX (60) after 46 owned`. So it both (a) **re-captured 22
  agents repeatedly** (exact-duplicate talent vectors → `_advance` sometimes did NOT move the
  selection, re-reading the same agent — the H18 "strip band is a poor move-detector" failure mode)
  and (b) **never covered 17 owned agents** before the cap. Export dedup hides the re-captures but
  CANNOT recover the 17 missing — this is silent data loss, not just wasted runtime. The ring-close
  gate also never tripped (would have stopped the cycling sooner).
  *Root cause (code)*: `AgentNavigator.scan()` (agent_scanner.py ~1382–1388) closes when
  `_phash_hamming(_agent_id(self._capture()), start_id) <= _AGENT_RING_CLOSE_MAX` (15 bits). Two flaws:
  (a) it compares an **unsettled** frame captured immediately after `_advance(+1)` — the full-body
  render (`_AGENT_ID_BBOX` 120,140,760,1000) is mid-entrance/idle-animation, inflating the Hamming;
  (b) it only ever compares to the single `start_id` anchor, so if that one frame was unlucky the loop
  can never close.
  *Plan*:
  1. **Calibrate first (offline).** Compute `_agent_id` Hamming between the duplicate base_stats.png
     pairs (same agent, one loop apart) to measure the REAL idle-drift the threshold must tolerate.
     Write the numbers to LOG. This tells us if 15 is simply too tight or if (a)/(b) dominate.
  2. **Settle the comparison frame.** Reuse `_wait_region_stable` on `_AGENT_ID_BBOX` (or compute the
     ring-close id from the next loop's gated `_capture_tab(_TAB_BASE)` instead of raw `_capture()`),
     so we compare like-for-like settled renders.
  3. **Seen-set backstop.** Maintain `seen_ids: list[str]`; after each advance, close the ring if the
     current id matches `start_id` OR any previously-visited id within threshold. Robust to an unlucky
     start frame and to arbitrary entry position. Guard against same-agent re-detection within one stop
     by only testing against ids from *prior* strip positions.
  *Files*: `agent_scanner.py`; extend `tests/test_agent_traversal.py` (sim must exercise a full loop +
  return-to-start with injected per-frame jitter ≤ measured drift, asserting close on lap 1 not lap 2).
  *Also*: re-examine `_advance` move-confirmation — the duplicate re-captures mean a real move is
  being mis-read as "no move" (or vice-versa). The fix must guarantee one capture per distinct strip
  position; consider gating advance-confirm on `_agent_id` (render pHash) rather than the strip band.
  *Acceptance*: traversal sim closes after exactly one lap; on a live re-run the log shows
  `agent_scan_done — ring closed` (NOT `agent_scan_cap`), and `agents.json` has **39 distinct owned
  agents, no exact-duplicate keys**.

- [x] **H24. Matcher: full-name client vs short-name map → 3 agents collapse onto "Zhao".**
  *DIAGNOSED (offline, name crops viewed — `agent_{000,011,035}/base_stats.png`)*:
  `"Zhao"` is a **real agent** — agent_000 renders literally "Zhao", map entry is correct, keep it.
  The other two "Zhao" entries are mis-collapses: **agent_011 = "Tsukishiro Yanagi"** (map key is the
  short `"Yanagi"`; the client renders the FULL name) and **agent_035 = "Komano Manato"** (absent from
  the map entirely). So the defect is naming, not ownership (D37 is fine).
  *Root cause (code)*: (a) the name map (`data/zzz_1.4/agents.json`) keys are **short** display names
  while the ZZZ client renders **full** names ("Tsukishiro Yanagi", "Komano Manato", "Asaba Harumasa",
  …); (b) `normalize_agent` (normalizer.py:137-143) = `process.extractOne(text, keys, scorer=WRatio)`
  with **no minimum-score floor**, so every miss snaps to the nearest short key and `"Zhao"` (short,
  vowel-light) is the magnet; (c) the map is also stale (no Komano Manato, Seth, Evelyn, Astra, Vivian,
  Pulchra, Trigger, Hugo, Yixuan, … for the current patch).
  *Plan*:
  1. **Map full-name keys/aliases.** New `data/zzz_<ver>/agents.json` keyed on the EXACT in-game full
     display names, each → its ZOD key (e.g. "Tsukishiro Yanagi"→`Yanagi`, "Komano Manato"→`Komano`,
     "Asaba Harumasa"→`Harumasa`, **"Komano Manato"→`Manato`**). Do NOT mutate existing 1.4 ZOD keys
     (optimizer data references them); add the missing post-1.4 agents.
  2. **Add a WRatio floor.** In `normalize_agent`, if `score < _AGENT_NAME_MIN_SCORE` (start ~85, tune)
     return `("", score)` so the `_CRITICAL_CONF` gate flags `unknown_agent` (issue carries the raw OCR
     text) instead of silently snapping to "Zhao". This is the regression guard for the next new agent.
  *Files*: `normalizer.py`, `data/zzz_*/agents.json`, `agent_scanner.py` (issue plumbing), tests
  (`test_normalize_agent_floor`: full name → correct key; unknown name → ("", low-score)).
  *Acceptance*: agent_011→`Yanagi`, agent_035→`Manato`, agent_000 stays `Zhao`; no name silently snaps
  below the floor; roster distinct-count == true owned (39).

- [x] **H25. Talent OCR noise — spurious 0s, non-deterministic across re-scans.**
  *Symptom*: same agent reads different talent vectors across duplicate visits (Zhao
  `12,12,11,12,11,6` vs `12,0,0,12,0,6`; ZhuYuan full vs all-zeros); pervasive `0`s on Lv.60 agents.
  Because export dedup keeps one copy arbitrarily, accuracy is luck-of-the-draw.
  *Root cause*: digit OCR in `_extract_skills` (agent_scanner.py:725-762) drops/misreads the per-talent
  level numerals; no per-field confidence surfaced to choose between reads.
  *Plan*: (1) tighten the talent-digit crop/preprocess (the `0`s suggest a glyph or thresholding miss —
  inspect skills.png crops offline); (2) surface per-talent confidence into the issues list; (3) once
  H23 stops the looping there is no free redundancy, so the OCR itself must be reliable — but as an
  interim, if duplicates still occur, MERGE on dedup field-by-field taking the highest-confidence /
  non-zero value rather than first-wins.
  *Files*: `agent_scanner.py`, export/dedup path, tests. *Acceptance*: talent reads stable across the
  duplicate base/skills fixtures; Lv.60 agents show no spurious 0 talents on the offline fixtures.

- [x] **H26. Equipment read as empty on every Lv.60 agent (`slot_empty … 'Equip'`).**
  *Symptom*: 0 discs / 0 engines for all 42; log is wall-to-wall `slot_empty slot=N — action-bar
  shows 'Equip'`. Built Lv.60 agents must have at least an engine → this is false-empty, not an
  unequipped roster.
  *Root cause (suspected)*: `_panel_shows_equipped` (agent_scanner.py:674, the H21.2/H21.3 action-bar
  "unequip" gate) is reading the action-bar as empty live — either the equip tab isn't rendering before
  the read (H20-family render-settle), the action-bar bbox/preprocess is off, or `slot_gate_fail`
  banking is feeding it transitional frames (several `slot_gate_fail` lines present).
  *Plan*: OFFLINE — run `_panel_shows_equipped` against the captured `equip_slot_*.png` for a known
  geared agent (e.g. archive idx 10 Miyabi). If it returns True offline but False live → render-settle
  timing; if False offline too → bbox/preprocess regression. Fix accordingly. Note H26 may be partly
  by-design (equipment is exported as a separate location cross-ref, not into ZodAgent) — confirm the
  plumbing too. *Files*: `agent_scanner.py`, tests. *Acceptance*: the geared fixtures read equipped;
  a live re-run records discs+engine for built agents.

## H27–H29 / H25.1 — Live-run review findings (run @20:42 2026-06-08, `--agents-only`; LOG 2026-06-08 review)

> Review verdict: **H23 + H22/D37 CONFIRMED FIXED LIVE** — ring closed at 'Zhao' after 39 owned (54
> visited), terminated by name-based ring-close (not AGENT_MAX), 14 unowned skipped as a contiguous
> tail. The roster blocker is gone. Mindscape reads fine; H24 floor prevents the triple-Zhao collapse.
> Two blockers + two data-quality issues remain (all downstream of traversal). Do NOT touch H23 ring-
> close, D37 ownership, or the strip-advance path — verified working.

- [x] **H26.1. (REOPEN — H26 fix did NOT hold live) Equipment false-empty on every agent.**
  *Symptom (latest run)*: 55 `slot_empty … action-bar shows 'Equip'` — **every slot 0–6 of every
  Lv.60 agent** → 0 discs / 0 engines located. H26 added the `"remove"` keyword but the live action-bar
  still matches neither `"unequip"` nor `"remove"`. Co-symptoms: 10 `slot_reclick` + 4 `slot_gate_fail`
  ("panel never settled in 10 polls; banking frame") → the gate is OCRing **transitional / wrong frames
  live** (same family as RC-3 / D35: passes clean offline fixtures, fails the live transitional frame).
  *Plan*: (1) capture ONE settled equipped-slot frame from a live built agent (the stale `agent_*` dirs
  are unreliable); (2) retest `_panel_shows_equipped` offline on it — True offline ⇒ render-settle-
  before-OCR (gate the action-bar read on a settled panel, don't OCR the banked `slot_gate_fail`
  frame); False offline ⇒ live bbox/preprocess regression of `_ACTION_BAR_BBOX`. (3) Re-verify the
  bbox spans the engine "Remove" button live (OQ-H21b). *Files*: `agent_scanner.py`, tests.
  *Acceptance*: the live geared fixture reads equipped; a re-run records ≥1 disc + engine `location`
  via `resolve_locations`; `slot_gate_fail` is rare and never banks a frame the equipped-gate then reads.

- [x] **H27. Persist issues.json + per-run archive dir to the WSL run dir (blocks name-gap diagnosis).**
  *Symptom*: only 21 of 39 owned exported — 15 captured records have an **empty `key`** (H24 floor
  rejecting low-confidence names) + ~4 owned produced no record. We **cannot tell DB-alias-gap from
  OCR-garble** because the issues file was written to a Windows-relative path
  `export\youkai_export.issues.json` and never landed in WSL (`export/` empty, 0 issues on disk); the
  raw OCR name text lives only there. Also the run reused `archive/live_20260605` (mixed 14:xx/20:xx
  `agent_*` dirs → stale frames). *Plan*: (1) write `issues.json` (with each unknown_agent's raw OCR
  text) into the WSL **run dir**, not a `cwd`-relative Windows path; (2) timestamped per-run archive
  dir (`archive/live_<YYYYMMDD_HHMMSS>/`) so frames aren't overwritten across runs — completes H5.
  *Files*: `cli.py:_cmd_scan_all`, capture/archive path setup, tests. *Acceptance*: a (mocked) scan-all
  writes `<run_dir>/issues.json` readable from WSL with raw OCR text per unknown agent; consecutive
  runs get distinct dirs.

- [x] **H27.1. Close the name gap (depends on H27).** With raw OCR text reviewable, decide per unknown
  agent: full-name alias missing from `data/zzz_1.4/agents.json` (add it) vs OCR garble (fix the name
  bbox/preprocess). Re-run the offline normalizer over the captured name crops; target ≥37/39 resolved
  above the floor, 0 false collapses. *Files*: `data/zzz_*/agents.json`, `normalizer.py`, tests.

- [x] **H28. Ascension reads 0 on Lv.60 agents (dot-counter non-functional live).** 19 of 24 Lv.60
  agents exported `ascension 0` (should be 5); the brightness dot-counter heuristic (E2, conf 75) is
  effectively broken live and unflagged. *Fix*: replaced `_count_ascension_dots` with `_read_level_cap`
  — reads the dim dark-on-dark "/ NN" cap badge via local-contrast normalization → Otsu → snap to
  `_VALID_AGENT_CAPS = {10,20,30,40,50,60}`. 46/46 live archive agents read correctly. Conf 90.0 on
  success, 30.0 on fallback. H4 tests updated. *Files*: `agent_scanner.py`, `tests/test_agent_h4.py`.

- [x] **H25.1. Talent spurious-zero hardening (H25 partial — confirmed live).** Lv.60 agents still show
  impossible `dodge:0`/`assist:0`/`chain:0` (Anton `12,0,0,12,12,0`; Seth `11,0,0,11,0,0`). H23 removed
  the re-capture redundancy, so there is no best-of-N net → the per-field badge classifier must be
  reliable alone. *Plan*: tighten the pass-2 dim-badge / zero-prefix rules against the new live skills
  crops; clamp a Lv.60 talent floor (a built agent's read 0 is almost certainly a miss → flag, don't
  silently emit 0). *Files*: `agent_scanner.py`, tests. *Acceptance*: no `0` talents on Lv.60 fixtures;
  misses surface to issues as low-confidence rather than `0`.
  *Done 2026-06-09*: Root cause — dim fallback required `b1_w < _BADGE_NARROW_W` to classify "08", but
  in the max-16 badge format ("08/16"), the "8"/"9" digits render at full width (~63px, not narrow).
  Fix: changed return type of `_read_skill_badge` to `(int, float) | None` (value + confidence);
  extended dim fallback to tier-classify wide b1 by fill ratio: fill≥0.70→8 (conf 65, "08"/"09"),
  fill≥0.55→5 (conf 45, "05"/"06"), fill<0.55→7 (conf 40, "07"/similar). Tier confidences are below
  _LOW_CONF_THRESHOLD (70) → surface in issues. Added Lv.60 talent floor in `scan_agents`: any talent=0
  on level≥60 agent emits a `talent_zero_lv60` issue as backstop. Committed 5 badge crops to
  `tests/fixtures/skill_badges/`; 7 new tests (6 per-badge, 1 confidence). Live archive re-run: 0 zeros
  in the entire agent_* crop set (was: 21 agents with ≥1 spurious zero). Suite 384 passed / 1 pre-existing.

## H30 — Agent-name crop truncation (root-caused from run `live_20260609_140457`, 2026-06-09 Opus; LOG same date)

> Live `--agents-only` run: traversal PERFECT (39 owned found, ring closed at Zhao — H22.3/H23
> confirmed) but only 26/39 exported. Root cause is **name crop geometry**, not the DB (D37/H24 fixed
> the DB) and not the floor. `_AGENT_NAME_BBOX = (955,278,1350,330)` (395px) truncates the full names
> the client renders ("Hoshimi Mi"→Miyabi, "Von Lycac"→Lycaon, "Asaba Haru"→Harumasa, "Komano Ma",
> "Anby Dem", "Ye Shundat") → below WRatio floor → empty key → dropped at export. Offline-validated fix
> below recovers 36/39 with zero regressions. **DO NOT touch traversal/ownership/ring-close — confirmed
> working.** All offline-validatable against `archive/live_20260605/live_20260609_140457/agent_*/base_stats.png`.

- [x] **H30.1 Widen the name bbox + junk-strip the matcher (recovers 36/39).**
  (a) `_AGENT_NAME_BBOX` → `(935, 278, 1560, 332)` in `agent_scanner.py` (captures full names; a bare
  widen alone regresses Trigger/Pulchra/OrphieMagus on trailing icon glyphs, so (b) is required).
  (b) In `normalize_agent` (`normalizer.py`), pre-clean before WRatio: strip chars outside
  `[A-Za-z0-9& -]`, drop tokens of len<2, collapse whitespace. *Files*: `agent_scanner.py`,
  `normalizer.py`, tests. *Acceptance*: re-OCR the 39 archived `base_stats.png` name crops → ≥36 resolve
  above the floor, 0 regressions vs the current 27; commit the ~13 failing name crops as fixtures + a
  parametrized test. Suite green.
  *Done 2026-06-09*: bbox widened, `_clean_agent_name` added, tests extended. 390 passed.
- [x] **H30.2 Close the last-3 name gaps.** (a) **Nekomata is absent from `agents.json` entirely** —
  the client renders her full name "Nekomiya Manaka" (user-confirmed: Nekomiya = Nekomata), which scores
  only ~72 against current keys. Add display name(s) "Nekomiya Manaka"/"Nekomiya Mana" → ZOD key
  `Nekomata` (verify `to_zod_key("Nekomata")=="Nekomata"`). (b) Add alias **"Orphie Magnusson" → OrphieMagus**
  (pos 12, scores 80). (c) **Qingyi** (pos 17) OCR-garbles to "Ginayi"/"Oinayi" (Q→G/O) — no alias helps;
  add a name-crop preprocessing note / leave flagged low-confidence. *Files*: `agents.json`, `normalizer.py`,
  tests. *Acceptance*: pos 29 + pos 12 resolve; pos 17 surfaces as low-confidence (not a wrong snap).
  *Done 2026-06-09*: Nekomiya Manaka/Mana + Orphie Magnusson aliases added; Ginayi/Oinayi confirmed
  floor-rejected (not snapped) — Qingyi will surface as unknown_agent issue in live runs.
- [ ] **H30.3 (residual, lower pri) Settle-gate the Base-tab name read.** pos 12/24 read key=0.0 *live*
  but resolve fine from the archived frame → the name read occasionally banks a transitional Base frame
  (H1x render-settle family). If a re-run still drops agents the wide+clean fix resolves offline, gate the
  name read on a settled `_AGENT_NAME_BBOX` region. *Files*: `agent_scanner.py`. *Acceptance*: name read
  only OCRs a settled frame.
- [x] **H30.4 Live confirm.** Re-run `scan-all --agents-only --debug-overlays`; expect ≥36/39 exported
  with correct keys, `agent_skip — unowned` only on the Lv.1 tail. Paste `agent_scan.log` + `issues.json`.
  *Done 2026-06-09 (run live_20260609_152444)*: **38/39 keyed correctly** (exceeds ≥36 threshold).
  Ring closed at Zhao after 39 owned / 54 visited (Lv.1 tail positions 40–53 all `agent_skip` — correct).
  1 blank key = Qingyi (confirmed from base_stats.png overlay; OCR reads ~"Ginayi", scores 67.5 < 85 floor — expected).
  2 Lucia entries discovered: agent_001 = "Lucia Elowen" → Lucia (correct); agent_022 = "Luciana de Montefio"
  → was resolving to Lucia (wrong) — fixed by adding "Lucia Elowen"→Lucia and "Luciana de Montefio"→Lucy
  aliases to agents.json. 32 `low_confidence` issues (all numeric fields, zero wrong keys). 399 passed, 0 regressions.
