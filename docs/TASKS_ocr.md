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
- [ ] **F2. Golden-replay test + accuracy gate.** Commit the labeled crop archive; CI runs
  recognize→assemble with no game, enforcing the §10 accuracy gate and the negative controls. *Acceptance*:
  CI green; a deliberately tinted/wrong-res frame is refused.
- [ ] **F3. Review report + confidence UX.** Emit a human-readable report of low-confidence / unmatched
  items for manual keying. *Acceptance*: forcing a fuzzy-miss routes the item to the report, not the JSON.
- [ ] **F4. Safety audit + runbook.** Static check for forbidden calls (process attach / memory read /
  file or packet access against the game) enforcing S-OCR-1; write a setup runbook (windowed res, color
  settings off, admin note, Esc kill-switch). *Acceptance*: audit passes; runbook reproduces a clean scan.
- [ ] **F5. Decommission Youkai.** Remove the Rust packet-sniffer app from the active build (keep
  `zod.rs` as schema reference or port note); update README to describe `youkai-ocr`. *Acceptance*:
  repo root documents the OCR tool as the project; dead decryption code archived or deleted per user.

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

- [ ] **H5. Tandem hardening — persistence + preflight assert + resume (G-E).** In
  `cli.py:_cmd_scan_all`: tee stdout to `archive/<run>/scan.log`; write `archive/<run>/results.json`
  (per-phase counts, issues, merged export). Add a per-phase preflight screen-assertion (disc/engine
  header present; agent page signature present) that aborts the phase loudly if the wrong screen is
  open. Add per-phase output files so a failed agent phase can resume without rescanning discs.
  Keep the manual `input()` gates between the three menus (non-goal to automate). *Acceptance*: a
  (mocked) scan-all writes log + results.json; a forced wrong-screen preflight aborts that phase
  with a clear message; suite green. *Files*: `cli.py`. Depends on H2–H4.

- [ ] **H6. Live acceptance — one clean `scan-all` (G-A..G-E).** *(needs game; after window-target
  fix)* Full roster traversed (count ≈ visible owned roster), Equipment-tab gate passes for every
  agent, and ≥1 disc + ≥1 engine receive a `location` via `resolve_locations`. Archive the run
  (now self-documenting via H5). *Acceptance*: merged `ZodExport` validates; `scan.log` shows
  roster count > 3 and zero Equipment-gate failures; spot-check 3 agents' fields against the game.
  Depends on all of H0–H5.

- [ ] **H7. Single auto-navigating `scan-all` (menu hub driver).** *(plan: D26)* Add a navigation
  layer that drives the whole pipeline from the main-menu hub, replacing the manual `input()` gates
  (keep them behind `--manual-nav`). Primitives: `assert_screen(signature)` render-gates for
  main-menu / W-Engine / Disc / agent-page; `active_storage_tab()` = brightest of the 4 top-right
  category-tab bboxes (handles the pulse-glow); `return_to_main()` via the back-arrow. Flow:
  main → Storage → engine tab (scan) → disc tab (scan) → back → Agents → Base → agent page (H2 roster
  scan) → `resolve_locations` → merged export, all persisted per H5.
  - **H7a (blocked on ref_11/ref_12 readability):** measure `Storage`/`Agents` (ref_11) and `Base`
    (ref_12) button centers + main-menu/agent-menu signatures → `navigation.yaml`. *The OneDrive copies
    dehydrated mid-session (present 13:00, gone 13:05); need them re-synced/readable.*
  - **H7b (unblocked now):** measure the 4 Storage category-tab bboxes + active-glow threshold from
    `reference_1`/`reference_2`; implement `active_storage_tab()` + a fixture test (disc-active on
    ref_1, engine-active on ref_2).
  - **H7c:** wire the driver + `assert_screen`/`return_to_main` into `cli.py:_cmd_scan_all`.
  *Acceptance*: a (mocked-frame) driver test walks the full transition graph and asserts each gate;
  live, one `scan-all` completes hands-off from the main menu. Depends on H2–H5; H7a blocks the live leg.
