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
- [ ] **G5. Two-pass panel slot fallback (zero `no_slot` fails).** Implement D-slot-panel-fallback:
  when the title-text `parse_slot` returns None, run a digit+bracket-whitelisted OCR (psm 11) over the
  un-clipped panel — Pass A `x[0:300] y[158:210]` (1-line names, slot pushed right), Pass B
  `x[0:180] y[200:290]` (2-line names, slot wraps left-low, excludes the bright icon); first `[1-6]`
  wins (bracketed preferred, bare-digit fallback). Wire it into `_extract_disc` so it runs only on the
  title-parse miss (no cadence cost). *Files*: `disc_scanner.py` (panel slot helper + call site),
  maybe `normalizer.py`. *Acceptance*: offline re-triage of the 12 archived fail panels
  (`docs/triage_disc_fails.json` / `scripts/triage_disc_failures.py`) recovers **12/12** correct slots;
  commit those 12 `panel.png` crops as test fixtures + a parametrized test; full suite green; a re-run
  reports **0 `no_slot`** critical fails. *Validated offline by Opus 2026-06-06 — recovers 12/12.*
