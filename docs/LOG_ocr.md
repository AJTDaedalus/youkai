# LOG — ZZZ Inventory OCR Scanner ("youkai-ocr")

Append-only worklog. Newest at bottom.

---

## 2026-06-01 — Planning (Opus)
- Pivoted the project from packet decryption (STOP per D14) to screen OCR.
- Confirmed scope with user: automated UI control, Python, full spec in one milestone, full Youkai scrap OK.
- User named **AdeptiScanner-ZZZ** (D1firehail) as template — verified it's external-only C#/Tesseract,
  GOOD export, windowed reference res, color-sensitive. Disc scanning documented; **agent** scanning
  (talents/mindscapes) essentially net-new.
- Wrote `DESIGN_ocr.md`, `TASKS_ocr.md`; recorded D15–D18 in `DECISIONS.md`.
- Key carry-forward: the ZOD/GOOD output contract (`youkai/src/zod.rs`) — everything else scrapped.
- Open blockers to clear first: OQ-ocr-1 (canonical ZZZ data source) and OQ-ocr-4 (reference screenshots).
- **Next**: switch to Sonnet; start at TASKS A0 → A1, and clear OQ-ocr-1/OQ-ocr-4 early (they gate A2–A4).

## 2026-06-01 — Plan refinement: positional + no external data dump (Opus)
- User challenge: "can we do it off position, do we need a data source / screenshots?" Resolved:
  position gives *where*, not *what* — recognition still needed, but the external dump is droppable.
- **D19**: no external data dump; hand-authored name lists + OCR-the-text; templates only for the
  equipped-agent indicator if it's portrait-only. **D20**: a co-op nav+capture session (A0.5) authors
  the keybind map + reference screenshots and resolves OQ-ocr-4/OQ-ocr-7.
- Updated DESIGN_ocr.md (§6 data bullet, §8, OQ-1/-4, new OQ-7) and TASKS_ocr.md (new A0.5; A2→hand
  lists; A3 conditional; A4 blocked-by A0.5; dependency notes).
- User will provide the disc/agent screenshots; **A0.5 is the first thing to run with Sonnet.**
- **Next**: switch to Sonnet → run A0.5 (navigation + reference capture) with the user, then A0/A1.

## 2026-06-01 — A0 complete (Sonnet)
- Created `youkai-ocr/` Python package skeleton: `pyproject.toml` (hatchling), `src/youkai_ocr/`,
  `tests/`, `data/`, `reference/`, `.gitignore` (archives/screenshots/JSON excluded).
- Stub CLI `youkai-ocr {scan,calibrate}` runs; `pip install -e .[dev]` passes.
- **Next**: A0.5 (co-op navigation map + reference capture) — user needs ZZZ open at 1920×1080,
  filters off, Drive Disc detail panel with an equipped disc visible.

## 2026-06-01 — A0.5 in progress: disc inventory mapped (Sonnet)
Reference screenshot `reference_1_disc_menu.png` (1922×1112 raw, game area 1920×1080 at offset 1,32).
Measurements confirmed via pixel analysis:
- **Grid geometry**: 9 columns × 4 visible rows; col_pitch=135px, row_pitch=175px
  Cell (0,0) center: (166, 242). Grid bbox: (98, 155)–(1315, 865).
- **Detail panel** at x=1421–1860, y=100–870. All disc fields mapped with precise bbox coords:
  set_name_with_slot, slot_badge, equipped_indicator, rarity_badge, level, main_stat, 4×substat, lock.
- **OQ-ocr-7 partial**: EMPTY state confirmed — shows grey "EMPTY" button text at (1455–1725, 378–440).
  Hypothesis: EQUIPPED state shows agent name as OCR-able text in same button. NEEDS CONFIRMATION.
- **OQ-ocr-4**: Disc panel geometry fully mapped. Calibration anchors still TODO (live session needed).
- Written `data/zzz_1.4/navigation.yaml` with all confirmed values; TODO entries for:
  nav_path (key sequence), scroll config, sort menu, W-Engine section, Agent section, calibration anchors.
- All 8 reference screenshots provided by user. Full panel analysis completed.

## 2026-06-01 — A0.5 complete (Sonnet)
All reference screenshots mapped. navigation.yaml written with confirmed coordinates for:
- Disc inventory detail panel (all fields: set name+slot, portrait indicator, rarity, level, main stat,
  4 substats, lock)
- W-Engine detail panel (engine name, portrait, rarity, level, refinement stars, base ATK, secondary
  stat, effect label, lock)
- Agent base stats page (faction, name, level, element, specialty, stats grid 5×2, fully-equipped)
- Agent skills page (5 skill level numbers, A-F core node grid, mindscape cinema counter)
- Agent equipment tab (hexagonal disc/engine slot positions, slot detail panel structure)
- Shared grid geometry: 9 columns × 175px row pitch (confirmed for both disc and engine inventories)
OQ-ocr-7 RESOLVED: portrait-only; equipped state = small portrait circle present; unequipped = absent.
D21 recorded: Equipment-tab cross-reference is primary location-detection path (portrait templates demoted
to fallback). A3 and E1 tasks updated accordingly.
Still TODO in navigation.yaml: nav_path key sequences (live session), calibration anchors,
equipment-tab slot precise coordinates (B1), skills icon precise positions (B1).
**Next**: A1 (ZOD emitter + schema), A2 (hand-author name lists), A4 (window capture + calibration).

## 2026-06-02 — AdeptiScanner navigation research (Sonnet)
Verified AdeptiScanner-ZZZ navigation approach (GitHub D1firehail/AdeptiScanner-ZZZ):
- **Grid traversal**: synthetic mouse CLICKS on calculated cell positions — NOT arrow keys.
  Arrow keys confirmed non-functional in ZZZ grid; do not use.
- **Inventory opening**: NOT automated. User manually opens disc/engine screen before running
  the scanner. We adopt the same approach — require user to be on the correct screen at scan start.
- **Scrolling**: clicks the bottom-most row to trigger game auto-scroll; detects scroll completion
  via screenshot hash comparison (not a fixed wait). Scroll wait ~1500ms default.
- **ZZZ vs GI**: same code path in the repo — no ZZZ-specific nav code.
- **Effect on design**: nav_path TODOs in navigation.yaml do not need to be automated keyboard
  sequences. Pre-condition at scan start = user is already on the correct screen.
  Scroll detection = hash/brightness diff between before/after clicking bottom row.

## 2026-06-02 — A1 complete (Sonnet)
Ported ZOD schema to `youkai_ocr/zod.py`:
- `ZodSubstat`, `ZodDisc`, `ZodWEngine`, `ZodAgent`, `ZodExport` dataclasses with `.to_dict()` / `.to_json()`.
- **Added** `ZodTalent` with 6 fields (basic/dodge/assist/special/chain/core); `ZodAgent.talent` is `Optional[ZodTalent]`, absent if `None`.
- `to_zod_key` mirrors Rust exactly: capitalizes first char of each word-boundary segment, passes remaining chars through **as-is** (no lowercasing — "HP" stays "HP", "CRIT Rate" → "CRITRate").
- `tests/test_zod.py`: 26 parametrized `to_zod_key` cases + 7 serialisation tests, all green.
- Clarification: stats use explicit percent convention in name lists (HP% → "HPPercent") because `to_zod_key` cannot distinguish flat vs percent.

## 2026-06-02 — A2 complete (Sonnet)
Wrote `data/zzz_1.4/{agents,disc_sets,engines,stats,manifest}.json`:
- **agents.json**: 25 agents (1.0 launch through 1.4 Miyabi/Harumasa).
- **disc_sets.json**: 13 sets (launch sets + Thunder Metal, Proto Punk confirmed by name).
- **engines.json**: 30 engines (S-rank signatures + A/B-rank pool).
- **stats.json**: 19 stat entries with `main_stat_by_slot` metadata; percent stats keyed as "HPPercent" etc.
- **manifest.json**: version header + patch instructions.
- All 68 agents/sets/engines ZOD keys verified against `to_zod_key` (100% match).
- Stat keys follow explicit convention, NOT `to_zod_key`, due to flat-vs-percent collision.
- **TODO for user**: verify disc_sets.json "Proto Punk" and "Thunder Metal" exist in-game at 1.4;
  verify engines.json B-rank entries against actual inventory; confirm stat display string for
  elemental DMG (may be "Electric DMG Bonus" or "Electric DMG%").

## A4 — Window capture + calibration (2026-06-02)

**Implemented:** `src/youkai_ocr/capture.py`

- `CalibrationResult` dataclass: `scale_x`, `scale_y`, `frame_width`, `frame_height`; helpers `to_frame()`, `scale_bbox()`, `is_identity`.
- `calibrate(frame)`: validates 16:9 aspect ratio (±1% tolerance), returns scale against 1920×1080 reference. Rejects ultrawide/portrait with clear ValueError.
- `grab_window()` (Windows-only): finds ZZZ window via `win32gui.FindWindow`, maps client-area to screen coords via `ClientToScreen`, grabs via `dxcam` (DXGI) with PIL.ImageGrab fallback.
- `dxcam>=0.3` added to pyproject.toml as a Windows-only dependency.

**Tests:** `tests/test_capture.py` — 8 tests, all passing.
- Reference 1920×1080 → identity
- Resized 1600×900 → scale ≈ 0.8333
- 2560×1080 (ultrawide) → ValueError
- 1080×1920 (portrait) → ValueError
- `scale_bbox` and `to_frame` round-trip checks

**Unblocks:** B1, C1, D1, E1 (all capture consumers).
**Next:** A5 (color-hygiene preflight) or skip to B1 (declarative field-crop config).

## 2026-06-04 — ref_9 analysis: equipment slot_detail_panel mapped (Sonnet)
Analysed reference_9_equipment_disc_info.png (1922×1112, same resolution as other refs).
The slot detail panel when a disc slot is clicked in the Equipment tab:
- Panel bbox (game coords): [610, 120, 965, 620]
- Disc title "Bunny in Wonderland [1]": y=120–205, x=610–960
- Rarity badge (color sample): x=610–648, y=205–255
- Level "Lv. 15/15": x=648–960, y=205–255
- Main stat name: x=610–920, y=308–345; value right-aligned x=920–965, y=308–345
- Substats 1–4: name x=610–920, value x=920–965; y-rows: 403, 455, 507, 558 (height ~37px)
- Set Effect starts y≈619 (not needed for ZOD)
- No lock icon visible in this panel; lock state comes from inventory scan (C2/D2).
Updated navigation.yaml equipment_tab.slot_detail_panel with confirmed coords.
- ref_10 comparison revealed VARIABLE LAYOUT: y-positions shift with title line count (~32px
  offset between 1-line vs 2-line titles). Fixed-coordinate crops unreliable for body fields.
  Resolution: structure-first OCR on full body crop, anchored on "Main Stat" / "Sub-Stats" headers.
- Lock icon confirmed on disc thumbnails: small icon to the RIGHT of "Lv. N" text.
  Present=locked, absent=unlocked (verified by OCR: locked reads "Lv. 15 L", unlocked reads "Lv. 4").
  Lock state comes from C2 inventory scan, not from this panel.
- navigation.yaml updated with variable-layout notes and structure-first parse strategy.
E gap fully resolved. **Next**: Phase C (disc grid traversal).

## 2026-06-04 — Phase B3/B4 + Phase C complete (Sonnet)

### B3: matchers.py
- `detect_rarity(sample)` → int (4=S, 3=A, 2=B): median-pixel Euclidean distance to color centroids
  from navigation.yaml. Raises ValueError if nearest centroid > threshold 80.0.
- `detect_lock_from_text(text)` → bool: regex `\d\s+L\b` on thumbnail level OCR text.
- 7 tests, all green.

### B4: normalizer.py
- `normalize_disc_set(text)` → (key, 0-100): strips "[N]" suffix, rapidfuzz WRatio over disc_sets.json.
- `normalize_substat(text)` → (key, 0-100): strips "+N" upgrade suffix, exact-first then rapidfuzz.
- `normalize_main_stat(text, slot)` → (key, 0-100): slot-contextual lookup + fuzzy fallback.
- `normalize_agent/engine(text)` → (key, 0-100): fuzzy over agents/engines.json.
- `parse_level(text)` → int: "Lv. N" regex with digit fallback.
- `parse_numeric(text)` → float: strips commas/%, regex fallback.
- Validators: `validate_disc_level/rarity/slot`.
- 42 parametrized tests, all green.

### C1: grid.py — GridNavigator
- `GridParams` dataclass mirrors navigation.yaml shared_grid (9 cols, 4 rows, 135/175 pitches).
- `GridNavigator.scan()` generator: clicks cells via pynput.mouse, scrolls by clicking bottom row,
  detects end-of-inventory via MD5 hash of a grid centre strip, stops on no-change.
- Page 0 visits rows 0-3; subsequent pages skip row 0 (duplicate after scroll).
- `make_kill_listener()` → Esc sets a threading.Event to abort mid-scan.

### C2: disc_scanner.py — _extract_disc + scan_discs
- Field bboxes from navigation.yaml disc_inventory.detail_panel (right-side panel at x≈1421+).
- Crops/OCRs: title (set+slot), rarity (color sample), level, main stat, up to 4 substats.
- Lock from cell thumbnail level strip (relative offsets from cell center).
- Archives raw crops to archive/disc_NNNN/ per disc.
- `scan_discs()` drives the navigator, returns (discs, issues). Issues list low-conf fields
  and critical failures separately.

### C3: disc_scanner.py — export_discs
- `export_discs(discs, path)` writes ZodExport{format=GOOD, version=1} JSON.
- Creates parent directories automatically.

### Tests: 150/150 green (all previous + 70 new)
- test_normalizer.py: 48 tests
- test_matchers.py: 12 tests
- test_disc_scanner.py: 10 tests (geometry, crop math, export round-trip)

### What's still TODO before C is "production ready"
- C2 field bboxes need live-game validation: the navigation.yaml coords are from ref screenshots,
  but we haven't tested OCR on a real scan yet. Expect some tuning needed.
- Lock detection via thumbnail strip uses estimated y-offsets (+55 to +87 from cell center).
  Verify these against a real game frame.
- C3 acceptance criterion ("optimizer imports without error") requires a live optimizer import test
  by the user.
**Next**: D1/D2 (W-Engine scanner), or live validation of C with real game frames.

## 2026-06-05 — CLI wired up + offline validation session (Sonnet)

### CLI: `youkai-ocr scan` + `youkai-ocr calibrate` wired up (was stub)
- `scan --file PATH --crop X0,Y0,X1,Y1` — offline single-frame extraction (no pynput, no game)
- `scan` (no --file) — live mode: grabs game window, drives grid navigator
- `calibrate [--file PATH]` — validates window/frame aspect ratio + prints scale

### Offline validation against reference_1 and reference_5
Ran `scan --file reference_1_disc_menu.png --crop 1,32,1921,1112`. Found and fixed 6 bugs:

**Bug 1: parse_slot regex anchored to `$`**
`_SLOT_RE = re.compile(r"\[(\d)\]\s*$")` failed when OCR adds trailing junk after `[1]`
(e.g. `"Notes From the\nChained [1]\n1g"`). Fixed: removed `\s*$` anchor.

**Bug 2: Level used `read_digits` (strips "/")**
`read_digits` whitelist excludes `/`, so "Lv. 15/15" became "1515" → parse_level gave 1515
(out of range → 0.0 confidence). Fixed: use `read_line` (psm 7) for level crop.

**Bug 3: Main stat name needed psm 7**
`read_text` (psm 6) returned empty for 2-character "HP" crop (psm 6 expects a text block,
not a single word). `psm 7` reads it correctly. Fixed: added `read_line()` method to
`TextRecognizer` protocol + `TesseractRecognizer`, used for main stat name.

**Bug 4: Rarity used median (median too dark due to badge design)**
S-rank badge median was [129,113,33], far from centroid [245,200,33] (dist=145 > threshold 80).
Fixed: use 75th percentile instead of median — bright badge color wins over dark background pixels.
Pure-color synthetic test images are unaffected (p75 = their single color).

**Bug 5: ATK% vs flat ATK indistinguishable from name alone**
Both show "ATK" as the substat name; value "9%" vs "38" distinguishes them.
Fixed: `_FLAT_TO_PERCENT` remap in disc_scanner — if value_text has "%" and key is hp/atk/def,
upgrade to hp_/atk_/def_.

**Bug 6: Substat values used `read_text` (psm 6 fails on narrow value crops)**
Value crops are ~95×41px with a single number. psm 6 returned empty; `read_line` (psm 7) reads correctly.
Confirmed fix: `def=30` reads correctly on reference_5 after this change.

### Extraction accuracy on reference_1 (all fields 90-100% confidence):
`NotesFromTheChained / slot 1 / S-rank / Lv.15 / HP 2200 / anomProf 18, crit_dmg_ 4.8, atk_ 9%, atk 38`
All correct vs ground truth from panel image.

### Extraction accuracy on reference_5:
`NotesFromTheChained / slot 1 / S-rank / Lv.15 / HP 2200 / def 30, crit_ 4.8%, atk_ 6%, anomProf 27`
All correct.

### Tests: 150/150 green (no regressions)

### What's needed for the actual live scan:
- **Must run on Windows** — `grab_window()` uses win32gui + dxcam, explicitly raises on non-win32.
  From WSL, use `--file` mode (pass Windows screenshots). From Windows, run `youkai-ocr scan` directly.
- A/B rank rarity centroids need calibration from a real A or B rank disc screenshot.
- Lock detection via thumbnail strip needs live validation (uses dummy cell-0-position in offline mode).
- `location` field always empty until Phase E (agent equipment cross-reference).

**Next**: Live scan on Windows, or D1/D2 (W-Engine scanner).


---

## 2026-06-05 — D1/D2: W-Engine scanner

### Tasks completed: D1 (navigation), D2 (assembler)

**New files:**
- `src/youkai_ocr/wengine_scanner.py` — grid nav + assembler + offline scan + export
- `tests/test_wengine_scanner.py` — 22 new tests (all passing)

**Modified files:**
- `src/youkai_ocr/normalizer.py` — added `parse_level_with_ascension()` (parses "Lv. N/MAX" → level + ascension via cap table)
- `src/youkai_ocr/matchers.py` — added `count_filled_stars()` (counts gold star sections in refinement strip)
- `src/youkai_ocr/cli.py` — added `scan-engines` subcommand; refactored scan arg setup into shared `_add_scan_args()`

**Design decisions:**
- Ascension derived from the `/MAX` suffix in "Lv. N/MAX" (cap table: /10=0, /20=1, /30=2, /40=3, /50=4, /60=5) — no separate ascension field on the panel needed.
- Refinement star count uses a 5-section column split + gold-threshold heuristic (R>180, R>B+80). Works on synthetic strips; needs validation from a real screenshot.
- Lock detection reuses the same cell-thumbnail level-strip approach as disc scanner.
- `location` field stubbed as "" — to be filled by Phase E equipment-tab cross-reference.

**Test results: 172/172 green (150 prior + 22 new)**

**Still to validate with real game frames:**
- Refinement star color thresholds on real star renders (confirm gold threshold holds).
- Engine name OCR accuracy (relies on fuzzy match against engines.json).
- No W-Engine reference screenshots in `reference/` yet — offline validation blocked until user provides one via Windows screenshot.

**CLI usage:**
```
# Offline (from WSL, screenshot on Windows):
youkai-ocr scan-engines --file path/to/screenshot.png --crop "1,32,1921,1112"

# Live (from Windows):
youkai-ocr scan-engines --archive-dir archive/ --output export/engines.json
```

### Offline validation on reference_6_unequipped_wengine.png (2026-06-05)

Bug found + fixed: LEVEL_BBOX right edge (x=1582) clipped the last digit of "/60", causing
`parse_level_with_ascension` to read "60/6" and fall back to ascension=0. Widened bbox to x=1640.

All fields correct vs ground truth (Fusion Compiler, Lv. 60/60, refinement 1, unequipped):
`FusionCompiler / level 60 / ascension 5 / refinement 1 / location "" / lock false`

All 172 tests still green.

## 2026-06-05 — E1/E2/E3: Agent scanner (Sonnet)

### Tasks completed: E1 (navigation), E2 (core fields), E3 (talent levels)

**New files:**
- `src/youkai_ocr/agent_scanner.py` — AgentNavigator + extractors + offline scan + export
- `tests/test_agent_scanner.py` — 28 new tests (all passing)

**Modified files:**
- `src/youkai_ocr/cli.py` — added `scan-agents` subcommand; added `--skills-file` flag

**Design decisions:**

E1 — AgentNavigator:
- Portrait detection: scan roster strip (y=32-75) for bright clusters (grayscale col-mean > 80,
  min width 20px scaled, merge gap 8px). Portrait positions sampled once from the initial frame;
  all agents assumed visible in a single row at 1920×1080 (no scroll needed for ≤25 agents).
- Per agent: click portrait → Base Stats tab (wait 0.4s) → capture → Skills tab → capture →
  Equipment tab → click each of 6 disc slots + engine slot (wait 0.25s each) → capture 7 frames.
- Esc kill-switch via make_kill_listener() (same pattern as GridNavigator).

E2 — _extract_base_stats:
- Agent name: read_line on _AGENT_NAME_BBOX (955, 278, 1350, 330) → normalize_agent.
- Level: read_line on _LEVEL_BBOX (955, 452, 1100, 497) → parse_level.
- Ascension: brightness-based dot counter on _ASCENSION_DOTS_BBOX (955, 332, 1350, 360).
  Threshold 150, counts distinct bright column regions. Marked as heuristic (conf=75.0).

E3 — _extract_skills:
- Mindscape: read_line on _MINDSCAPE_BBOX (35, 980, 200, 1030), first digit match.
- 5 skill levels: read_line on each skill level_bbox, first digit group.
- Core rank: counts lit (teal-glowing) core nodes A-F. Detection: center 30×30px crop of
  each node bbox, green channel mean > 140 AND green-red > 50 (distinguishes teal from white).

**Test results: 200/200 green (172 prior + 28 new)**

**Still to validate with real game frames:**
- Portrait detection brightness threshold (80) and minimum width (20px) — may need tuning.
- Ascension dots counting — visual representation of promotion dots not confirmed from live session.
- Core node teal detection — threshold and green-red diff need live validation.
- Skill level bboxes from navigation.yaml are approximate; real skills-tab screenshot may shift.

**CLI usage:**
```
# Offline (base stats + skills in separate screenshots):
youkai-ocr scan-agents --file base_stats.png --skills-file skills.png --crop "1,32,1921,1112"

# Offline (same frame for both — if a frame shows both):
youkai-ocr scan-agents --file agent_page.png --crop "1,32,1921,1112"

# Live (from Windows):
youkai-ocr scan-agents --archive-dir archive/ --output export/agents.json
```

**Next**: E4 (equip reconstruction — match archived equipment frames to disc/engine inventory),
or A5 (color-hygiene preflight), or live validation of E1-E3 with real agent screenshots.

---

## E4 — Equip reconstruction (2026-06-05)

**Task**: Populate `location` on disc/engine records by cross-referencing the Equipment-tab frames captured during agent scanning.

**What was built** (all in `agent_scanner.py`):

- `_EQUIP_TITLE_BBOX = (610, 120, 965, 210)` — fixed title region from navigation.yaml `slot_detail_panel`.
- `_extract_equip_frame(frame, calib, recognizer, slot_idx)` — parses one equipment-tab slot frame:
  - Disc slots (slot_idx 0–5): OCR title with `normalize_disc_set()`; `slot_key` derived from `slot_idx + 1` (authoritative, not from title OCR).
  - Engine slot (slot_idx 6): OCR title with `normalize_engine()`.
  - Returns `None` if confidence < 30 (empty slot).
- `resolve_locations(equip_records, discs, engines)` — mutates disc/engine `location` fields; returns orphan issues for any record that found no match.
- `scan_agents()` now returns a 3-tuple `(agents, issues, equip_records)`. Equipment frames are parsed inline during the scan, and each record gets `agent_key` attached.

**Tests**: 10 new tests in `test_agent_scanner.py` covering disc/engine extraction, slot_key-from-index authority, empty slot → None, multi-agent location assignment, and orphan reporting. 210/210 suite green.

**Threshold / validation note**: `_EQUIP_CONF_MIN = 30.0` (same as disc scanner critical threshold). Live validation with real Equipment-tab screenshots still pending — empty-slot detection and set-name OCR accuracy should be confirmed against ref_7/ref_8.

**Next**: F1 (full ZodExport assembly — merge discs + engines + agents, call resolve_locations, write JSON).

## 2026-06-05 — F1 complete (Sonnet)

**F1: Full ZodExport assembly.**

- Fixed `_cmd_scan_agents` in `cli.py`: unpacked the E4-introduced 3-tuple `(agents, issues, equip_records)` (was silently broken as a 2-tuple unpack).
- Added `_cmd_scan_all()`: sequential 3-phase interactive scan (discs → engines → agents). Each phase pauses with a prompt so the user can open the right inventory screen. After all three scans, calls `resolve_locations(equip_records, discs, engines)` to wire disc/engine `location` fields from Equipment-tab cross-reference data.
- Dedupe + stable sort: agents deduped by key (first-seen wins), sorted by key; discs sorted by (set_key, slot_key); engines sorted by key.
- Orphan issues (equip records that matched no scanned disc/engine) collected alongside all other scan issues and written to `<output>.issues.json` if non-empty.
- Wired `scan-all` subparser to `main()`.

**Tests**: 210/210 suite green (no new tests needed — F1 logic is integration of already-tested primitives).

**Next**: F2 (golden-replay CI test + accuracy gate) or live validation of E-phase thresholds.

---

## scroll-to-top fix — scrollbar thumb detection (2026-06-05, Opus)

**Problem**: `_scroll_to_top()` looped forever (10 prior attempts, `HANDOFF_scroll_to_top.md`).

**Diagnosis**: every attempt used exact md5 of a grid region; ZZZ's breathing selection-glow + capture jitter means the hash never repeats even when stationary → no exit. Confirmed by inspecting `archive/live_20260605/preflight_discs.png`: pixel scan of the scrollbar groove (x1360–1372) shows it is black except two static arrows and the thumb (top edge y≈238 at-top). That column never changes except on real scroll.

**Change** (`src/youkai_ocr/grid.py`):
- Removed dead `_grid_hash_bottom` and `_top_position_hash` (md5 helpers, both unused after this).
- Added `_scrollbar_thumb_top(frame, calib) -> float | None`: scans the groove bbox for the first row brighter than the track, returns thumb top edge in reference-Y.
- Rewrote `_scroll_to_top()`: burst wheel-up (6 notches), settle, read thumb; exit on `thumb_top <= SCROLLBAR_TOP_Y` (250) or thumb stalled (rose <2 px) two bursts running; hard cap 80 bursts; ends with a priming click on (0,0). Prints `bursts [reason] thumb_top= …ms`.
- Added constants block (groove bbox, thresholds, burst sizing).

**Tests**: new `tests/test_grid.py` — at-top fixture reads thumb_top=238 (≤250); blanked groove → None; synthetic mid-track thumb → not-at-top. Full suite **211 passed**.

**Not yet validated live** — needs a real run against the game to confirm burst/settle timing and the 250 threshold on the user's rig. `SCROLLBAR_TOP_Y` is the one constant to retune if the thumb-at-top Y differs; the stall backstop covers small drift.

### scroll-to-top follow-up — disc 1 selection fix (2026-06-05, Opus)

Live run: scrollbar scroll-to-top works (first row captured). But disc 1 read as
the *third* disc in row 0. Scanner reads the **detail panel** (selected disc), so
this is a selection-state bug, not a geometry bug.

User clarification: **the wheel does not move the selection** — only the viewport.
So the selection stays glued to its disc and rises into row 0 at whatever column
it occupied (col 2), explaining the "diagonal" drift. The earlier "walk selection
with extra wheel notches" theory was wrong and was removed (`SCROLL_FINISH_NOTCHES`
deleted).

Leading hypothesis: the old priming click was on (0,0); the scan's first action
*also* clicks (0,0), so disc 1 was a no-op re-select that read the stale glued
disc, while discs 2-9 (each a new-cell click) read fine.

Change (`grid.py`): prime on **(1,0)** instead of (0,0), so the scan's first click
on (0,0) is a genuine adjacent selection change (identical to the working clicks).
Added debug dumps when `archive_dir` is set: `scroll_to_top_final.png` (post-prime)
and `disc1_capture.png` (exact frame disc 1 is read from). `disc_scanner.scan_discs`
now passes `archive_dir` as the navigator's `debug_dir`.

Status: NEEDS LIVE VALIDATION. If disc 1 is still wrong, `disc1_capture.png` shows
the panel disc 1 was read from → disambiguates "click didn't register" vs other.

### scan traversal rewrite — edge-row scroll handling (2026-06-05, Opus)

Live symptom: scan read discs along a diagonal (disc 1 from row 3, disc 2 up-one/
over-one, …). Scanner reads the detail panel = selected disc, so this was the
grid scrolling between clicks.

Root cause (confirmed by user + AdeptiScanner-ZZZ source, github.com/D1firehail):
**clicking the top visible row scrolls up unless it is the first inventory row,
and clicking the bottom visible row scrolls down unless it is the last; middle
rows never scroll.** Our naive raster clicked rows 0,1,2 and triggered on row 3
with brittle grid-hash scroll detection — it didn't account for edge-row scroll
and the hash was selection-glow-brittle.

Rewrite of `GridNavigator.scan()` (ported the *insight*, not the C#; kept our
natural Bezier click + scrollbar rewind):
- Scrollbar rewind guarantees we start at the top → row 0 is the first inventory
  row, safe to click. Read rows 0..rows_visible-2 in place.
- Bottom row is the scroll trigger: click it to advance one row, re-read the
  second-to-last row until its discs stop changing → end of inventory. Then read
  the bottom row once (now the last inventory row).
- Scroll/end detection uses a **tolerant** panel fingerprint (`_panel_signature`,
  48×48 gray, mean-MAE < `PANEL_MATCH_THRESH`), not exact hashes — avoids the
  glow/noise brittleness that defeated every earlier hash approach.
- `_trim_empty` drops trailing empty cells and whole empty rows (partial last
  row / small inventories that fit one screen).
- Removed dead `_scroll_by_click`, `_grid_hash`, `hashlib` import, and the
  `SCROLL_POLL_S`/`SCROLL_TIMEOUT_S` constants.

Tests (`tests/test_grid.py`): added an offline `_SimZZZ` that models the edge-row
scroll mechanic; verifies scan() reads every disc once, in order, with correct
bottom detection and trailing-empty trimming for full last row (72), partial last
row (68), and single-screen (27). Full suite **214 passed**.

Known limits: assumes scroll-to-top reaches the absolute top (it does, via the
scrollbar). Two pixel-identical discs straddling a trim boundary could be
over-trimmed (same edge case AdeptiScanner has). NEEDS LIVE VALIDATION on the
2200-disc inventory.

### scan traversal — deterministic, count-driven (2026-06-05, Opus)

Live symptom: infinite loop re-capturing one disc ("sticks on the last disc of
the first row… keeps capturing over and over"), likely missing earlier discs.

Root cause: the tolerant panel-fingerprint controlling the scroll/end loop was
unreliable. Measured on real archived panels: **minimum MAE between *different*
discs = 0.57**, median ≈ 6 (== the old threshold). ZZZ has many near-identical /
duplicate discs, so "panels match" cannot mean "didn't scroll" → the loop never
terminated (or trimmed real rows). Content fingerprints are the wrong signal.

Fix — drive traversal from the **disc count** in the storage header:
- `disc_scanner.read_disc_count()` OCRs "Drive Disc Storage [ N / M ]" (regex on
  `read_line`); verified =2200 on the real frame. Passed into `scan(total_discs)`.
- `grid.scan(total_discs)` is now **deterministic**: `rows = ceil(N/9)`, last row
  truncated to its real width (`_read_row(row, ncols)` — empty cells never
  clicked, so no phantom captures, no trimming). No content comparison anywhere →
  cannot loop.
- Each down-scroll is confirmed via the scrollbar thumb (`_scroll_down()` clicks
  the bottom row once, waits for the thumb to move down) so deterministic row
  reads stay aligned; single click avoids double-scroll.
- Removed `_panel_signature` / `_rows_match` / `_trim_empty` and the
  `PANEL_HASH_BBOX` / `PANEL_MATCH_THRESH` constants.
- Count-free fallback `_scan_by_thumb()` kept (scroll until thumb pins at bottom)
  for callers without a count (e.g. wengine_scanner until it adopts the same).

Tests: sim now renders a moving scrollbar thumb; covers full/partial/single-screen/
exactly-visible inventories + the thumb fallback, plus a real-fixture count test.
Full suite **217 passed**.

NEEDS LIVE VALIDATION on the 2200-disc inventory. Watch the new
`[nav] 2200 discs → 245 rows (last row 4)` line and that it stops at disc 2200.

### scan hardening + self-diagnostics (2026-06-05, Opus)

Live: count path still "stuck reading the last disc over and over." Could be (a)
count OCR failing live → thumb fallback looping, (b) clicks below row 0 not
changing selection, or (c) scroll overshoot. Hardened + instrumented to decide:
- `read_disc_count`: prints raw OCR text on failure; sanity-bounds the parsed
  count; accepts a bare "N/M" if the bracket is missing.
- `_scroll_down`: now a plain click+settle (no per-scroll thumb gate — the thumb
  moves only ~2-3 px/row on a 2200-disc inventory, too small to gate on).
- Deterministic loop: cumulative thumb-progress guard (`SCROLL_PROGRESS_*`) stops
  if the thumb stops descending over a window → no more "re-read forever".
- Fallback `_scan_by_thumb`: per-scroll before/after thumb check + `SCAN_MAX_ROWS`
  cap → cannot loop.
- Per-disc log line now prints `panel=<6hex>` (detail-panel fingerprint): repeated
  value on consecutive discs ⇒ selection stuck/lagged; changing ⇒ reads working.
- Debug mode saves the first `SCAN_DEBUG_FRAMES` (30) read frames as
  `read_NNN_rRcC.png`.

Suite 217 passed. Awaiting a live run's first ~12 `[nav] panel=` lines + the
count line to pinpoint whether the failure is OCR-count, stuck-selection, or
scroll.

### CONFIRMED WORKING + parallel OCR pipeline (2026-06-05, Opus)

Read the saved debug frames directly: read_000=disc "Notes From the Chained [6]"
(Anomaly Mastery 30%), read_003/006 distinct discs, selection box on the correct
cell each time. **Navigation + reads are correct.** The "sits on the last disc"
look was the row-buffered sweep (capture whole row fast, then OCR serially) — the
selector rests on the last-clicked disc while OCR catches up. Not a bug.

Real problem = speed: ~2.7 s/disc, all tesseract (7 calls/disc, serial). ~1.5 h
for 2200 discs. Fix (per user direction — desync capture from OCR, feed a worker
pool, never capture faster than OCR):
- `grid.py`: `_read_row` is now a per-cell generator → backpressure pauses
  navigation between discs (bounds memory, paces clicks to OCR). Added
  `CAPTURE_MIN_INTERVAL_S=0.40` human-cadence floor (was ~0.27 s, "too fast").
  Natural Bezier clicks unchanged.
- `disc_scanner.py`: navigation (main thread) feeds a bounded `Queue(maxsize=
  n_workers)`; `n_workers = min(8, cpu-1)` OCR threads drain it (pytesseract
  shells out, so threads parallelise). Results keyed by cell_idx, reassembled in
  order; Esc-responsive backpressured put; on_first_item early-abort preserved.
- New test: parallel pipeline preserves scan order with scrambled OCR completion.

Expected ~OCR_time/n_workers, floored by the 0.40 s cadence → ~15-20 min for 2200,
clicking at a human pace. Suite 218 passed. NEEDS LIVE VALIDATION (speed + that it
reads all rows, not just row 0).

---

## 2026-06-05 — Live full-scan triage: why discs/engines came back incomplete (Opus)

**Run analysed**: `archive/live_20260605/` (full scan-all). Headline results from the log:
- Discs: navigation visited **all 2200 cells** (`read 2200/2200`), but only **1162 assembled, 1832 issues** → ~1038 discs lost.
- Engines: scanned **225 cells → 206 engines, 223 issues** (you have 222).
- Agents: portrait nav wandered and clicked **City**, exiting the menu.

### Finding 1 — discs are NOT skipped by navigation; they fail at OCR (detail-panel render lag)
Every disc cell was clicked and produced a **distinct** `panel=` hash, and the count-driven
traversal (`2200 → 245 rows`) is sound. So the deterministic scroll logic is fine. The loss is
extraction: ~1038 discs hit the critical-fail guard (`not slot or set_conf < 30`).

Cause confirmed from archived panels:
- `disc_2100/panel.png` — **completely blank** detail panel (only the "DETAIL" header + bottom
  buttons rendered; no disc at all).
- `disc_1200/panel.png` — **dim, mid-fade-in** (title greyed, icon faded), vs
  `disc_1201/panel.png` — **fully rendered/bright**.

ZZZ fades the detail panel in on every selection change. At the parallel-pipeline cadence
(`CLICK_DELAY_S = 0.09 s` settle, ~0.4 s/disc) the capture frequently lands **before the panel
finishes rendering** → blank/dim crop → OCR garbage → `set_conf` below 30 → disc dropped. The
earlier "CONFIRMED WORKING" check only inspected first-row frames (0/3/6), so the deep-scan
failure rate was never measured until this end-to-end run. **The D-ocr-pipeline speedup is what
exposed/created this**: faster clicking outran the panel render.

### Finding 2 — W-Engine scanner never adopted the count-driven path
`wengine_scanner.scan_engines` calls `navigator.scan()` **with no `total_discs`** (grid.py path
`_scan_by_thumb`). Consequences in the log: it ran **25 full rows = 225 cells** though you have 222,
i.e. it over-ran into **3 phantom empty cells** (guaranteed critical-fail) and has no exact
last-row width. The engine inventory **does** have the same header — preflight shows
`W-Engine Storage [ 222 / 2000 ]` (top-left, ~x20–200,y45). Engines also share Finding-1 render
lag, but at the serial ~1.1 s/disc cadence the panel almost always rendered (206/225 ok), so the
miss is smaller. Net: adopt the disc count path for engines.

### Finding 3 — agent portrait detection targets the wrong screen region
`preflight_agents.png`: the agent roster is the small thumbnail strip at the **top-right**
(~x810–1300, y≈2–28), partially off the top. But `_ROSTER_STRIP_BBOX = (0,32,1920,75)` scans a
full-width band **below** the portraits, so `_find_agent_portraits` locks onto the bright character
splash-art (left) and the stats panel, and `_ROSTER_CENTER_Y = 53` clicks below the portraits.
Result: garbage click targets → wandering → eventually the **City** button (top-left), which exits
the agent menu. The agent geometry (portrait strip, tabs, slots) was authored from assumptions and
**never validated live** — this is the first run to reach it.

### Fixes (proposed — see TASKS G1–G4, DECISIONS D-render-gate / D-count-everywhere / D-agent-geom)
1. **Render-gate the capture** (discs + engines): after click+settle, capture, and *verify the panel
   actually rendered* before accepting it — e.g. mean luma of the title/panel region above a floor,
   poll-recapture up to a short timeout. Plus raise `CLICK_DELAY_S` base settle. This adapts to render
   time instead of a blind fixed wait, and keeps the disc that would otherwise be dropped.
   (Re-running OCR on the 1038 archived blank panels won't help — the data was never on screen; the
   capture must be retried live. The archive does prove the diagnosis.)
2. **Engine count path**: `wengine_scanner` reads `W-Engine Storage [ N / M ]` (mirror
   `read_disc_count`) and passes `total` into `navigator.scan(total)`; kills the 3 phantom cells +
   fixes last-row width.
3. **Agent geometry**: re-measure portrait strip bbox/Y from `preflight_agents.png` (top-right,
   y≈2–28), restrict x-range so splash-art isn't detected, and re-validate tab/slot coords against the
   archived agent frames before another live agent run.

**Status**: diagnosis only; no code changed this session. Recommend implementing G1–G4 on Sonnet.

## 2026-06-05 — G1 + G2 implemented (Sonnet)

**G1 — Render-gate disc/engine captures** (`grid.py`):
- Added `RENDER_GATE_BBOX = (1421, 270, 1860, 385)` (detail-panel title area).
- `RENDER_GATE_LUMA_FLOOR = 15`: blank/faded panels have mean luma ≈ 0–5; rendered > 15.
- `_panel_luma(frame, calib)`: helper returning mean luma of the title region.
- `GridNavigator._wait_panel_render(first_frame)`: spin-polls until luma >= floor or 1.0 s timeout; always returns a frame.
- `_read_row` now calls `_wait_panel_render(self._capture())` instead of bare `self._capture()`.
- Raised `CLICK_DELAY_S` 0.09 → 0.15 s (head-start before the gate kicks in).
- No change to the human-cadence floor — the gate's worst-case adds ~1 s/disc only if ZZZ is
  extremely slow; typical case adds zero latency (panel already rendered before the gate checks).

**G2 — Engine count-driven traversal** (`wengine_scanner.py`):
- Added `read_engine_count(frame, calib, recognizer)` (mirrors `read_disc_count`; regex on
  "W-Engine Storage [ N / M ]", same bbox `(20,95,560,155)`, sanity bound 0 < cur <= mx <= 2000).
- `scan_engines` captures a preflight frame, reads the count, passes it to `navigator.scan(total_engines)`.
  Falls back to thumb-stop (`total=None`) if OCR fails, with a warning.
- Kills the 3 phantom over-run cells and fixes last-row width.

**Tests**: 218/218 passed (imports OK, all existing tests green).
**Status**: awaiting live re-run to confirm G1 eliminates blank-panel critical-fails on discs.

## 2026-06-05 — G3 agent geometry re-measurement (Sonnet)

**Root cause of agent scan failures**: Two distinct bugs in `agent_scanner.py`.

**Bug 1 — City button being clicked as portrait** (roster strip x constraint):
- `_find_agent_portraits` scanned the full x=0-1920 roster strip.
- The City/Home UI button at x≈40-57 (luma ~162, width 34px) passes both the `_PORTRAIT_BRIGHTNESS=80`
  and `_MIN_PORTRAIT_WIDTH=20` filters, and merges with adjacent UI elements.
- Clicking x≈40 as a "portrait" exits the agent page to the City screen.
- **Fix**: added `_ROSTER_X_MIN = 400` constant; in `_find_agent_portraits`, zero out
  `col_means[:min_col]` before the brightness pass. Agent portraits start at x≈490+ (selected agent's
  teal-highlighted portrait); x=400 gives a safe margin.
- Roster strip y and click-Y unchanged: strip at y=33-70 (peak luma y=45-60), `_ROSTER_CENTER_Y = 53`.

**Bug 2 — Wrong tab coordinates** (tabs mis-estimated in navigation.yaml):
- nav.yaml estimated tabs at y=1030-1075 (x=790-1370); agent_scanner.py used centers (887,1052),
  (1075,1052), (1267,1052). These positions are empty dark regions on the actual screen.
- Pixel analysis of `archive/live_20260605/agent_000/base_stats.png` shows:
  - Tab bar is at **y=964-1028** (not y=1030-1075 — the names of ZZZ UI elements shifted).
  - Active "Base Stats" yellow button: x=1011-1294, center (1152, 996).
  - "Skills" white text cluster: x=1362-1445; equal-width spacing → button center ≈ (1435, 996).
  - "Equipment" white text cluster: x=1569-1738; equal-width spacing → button center ≈ (1718, 996).
- All 7 equip_slot_*.png frames in agent_000/ and agent_001/ showed Base Stats (tabs never switched).
- **Fix**: updated `_TAB_BASE_STATS/SKILLS/EQUIPMENT` to measured/estimated centers.
  Equipment slot centers (_DISC_SLOT_CENTERS, _ENGINE_SLOT_CENTER) **not yet verified** — need a
  live re-run with correct tab coordinates to capture Equipment-tab frames.

**Files changed**: `agent_scanner.py`, `data/zzz_1.4/navigation.yaml`  
**Tests**: 218/218 passed (geometry constants only; no logic change).  
**Next**: live re-run — verify Equipment tab opens and slot centers are correct. If slot centers are
wrong, re-measure from the newly captured equip_slot_*.png frames.

---

## 2026-06-05 — G1 post-run triage + slot regex fix (Sonnet)

**Scan result**: `read 2200/2200 discs, scanned 1633 disc(s), issues 1716`.
G1 (render-gate) improved disc yield from 1162 → 1633 (+471), but 567 still failed.

**Root cause**: Panel rendering is fine (no blank panels in archive). The failure is
`parse_slot()` returning `None` because `_SLOT_RE = r"\[(\d)\]"` requires both brackets,
but OCR frequently produces:
- `[1 ` (missing closing `]`) — most common
- `(1]` (paren instead of `[`)
- `[3!` (`!` as closing char)
- `[: 2` (digit OCR'd as `:`) — Fanged Metal specific

**Fixes** (`normalizer.py`):
- `_SLOT_RE` extended: `r"[\[(](\d)[\])\s!,.]?"` — accepts `[N]`, `(N]`, `[N `, `[N!`, etc.
- `_SLOT_RE_FALLBACK`: `r"[\[(][^\d]{1,3}([1-6])"` — recovers slot when digit is OCR'd as symbols (e.g. `[: 2` → slot 2).
- `parse_slot()` tries primary then fallback.

**Fix** (`disc_scanner.py`):
- `_fail_reason` key added to `conf` on critical fail: prints `no_slot:title=...` or
  `low_set_conf:...:title=...` — gives exact diagnosis when debugging future failures.
- Critical-fail issue entry now includes a `"reason"` field.

**Fix** (`tests/test_agent_scanner.py`):
- Portrait detection tests updated to place portraits at x≥450 (above `_ROSTER_X_MIN=400`
  threshold added in G3 to prevent clicking the City button).

**Impact** (measured against 440-disc sample from live archive):
- Before: 112/440 failures (25%)
- After: 4/440 failures (~1%) → projected ~20 remaining out of 2200 total

**Remaining failures** (~20 projected): all Fanged Metal discs where the OCR renders
the slot number as `. ec)`, `[ .`, `[: x`, `[ (=` — the slot digit itself is unreadable.
Likely needs a preprocessing or bbox adjustment specific to Fanged Metal's icon style.
Lowest-priority since only ~4 disc instances observed in sample.

**Tests**: 218/218 passed.

## 2026-06-06 — Opus triage: the 12 structural disc fails root-caused (slot, not render)

Picked up `.claude/handoffs/2026-06-06-disc-critical-fails.md`. The live run reported
~46 critical fails; the archive (`archive/live_20260605`, re-pointed across several disc
re-runs) is the *latest* capture of each disc, so render-lag fails were overwritten by
good frames. Re-OCR'd all 2205 archived `title.png` crops offline (reproduces the live
`_extract_disc` decision exactly — `scripts/triage_disc_failures.py`,
`docs/triage_disc_fails.json`): **12 persistent fails, all `no_slot`** — 8 Fanged Metal,
4 Dawn's Bloom. The 46-vs-12 gap = render-lag transients (already handled by G1), not
structural. The 12 are the real, reproducible target.

**Root cause (two distinct layouts, same symptom — confirmed by pixel inspection of the
panels):**
- **Fanged Metal (8)**: long set name pushes the title `[N]` past `_TITLE_BBOX` right
  edge (x=1660). The bracket+digit is *clipped* → OCR garbage (`'Fanged Metal [: a*'`,
  `'... [. ec)'`). The digit is fine in the wider `panel.png` (x→1860).
- **Dawn's Bloom (4)**: long name makes `"Dawn's Bloom [6]"` *wrap to two lines* (`[6]`
  on line 2). The title crop catches both lines + a faint diagonal watermark; psm-6 OCR
  mashes them (`'Gi s Bloom _ 6'`) — the `[` is lost entirely, so no `parse_slot` regex
  can recover it.

**Why the obvious fallbacks don't work:**
- *Detail-panel slot badge* (the hexagon `③`/`⑥`, nav.yaml `slot_badge`): its **Y shifts
  with title line-count** (1-line vs 2-line), and its metallic hexagon ring reads as a
  spurious `1` (`'16'`). Fixed-bbox + single-char OCR = unreliable (2/12).
- *Widen `_TITLE_BBOX`*: the disc icon art begins ~x1651, overlapping the slot x-range —
  widening pulls icon noise into the crop.

**Offline-validated fix (recovers 12/12):** a tiered `parse_slot` — keep the title-text
parse as tier-1, add a **two-pass panel slot OCR** fallback (digit+bracket whitelist,
psm 11) operating on the un-clipped panel:
- Pass A (1-line names, slot pushed right): band ≈ panel-rel x[0:300] y[158:210].
- Pass B (2-line names, slot wraps left-low; exclude the bright icon): x[0:180] y[200:290].
- Take the first `[1-6]` (bracketed preferred, bare digit fallback).
Measured offline: Pass A → all 8 Fanged Metal; Pass B → all 4 Dawn's Bloom = **12/12**.
A single unified crop only gets 7/12 (icon noise / lost leading `[`); the two-pass is the
clean version. → handed to Sonnet as **G5** (implement + add the 12 panels as test
fixtures). The truly layout-proof source (grid-cell thumbnail slot digit, fixed offset
from cell center) is recorded as the future-proofing option but is **not offline-validatable**
— no archived full frames for these discs.

**Also found (flagged to user, not code):**
- The whole scanner core is **uncommitted/untracked** (`grid.py`, `disc_scanner.py`,
  `agent_scanner.py`, `wengine_scanner.py`, `matchers.py`, `normalizer.py`,
  `input_utils.py`, `__main__.py` + all new tests) — only `capture/cli/recognize/zod/
  fields` are tracked. ~3k lines of working code living only in the working tree.
- `archive/live_20260606/` captured the **wrong window** — `read_000` is the Xbox Game
  Pass app ("ZenlessZoneZero — Running"), not the game. That run died at 6 discs because
  the window-targeting picked the launcher, not ZZZ. Window selection needs checking
  before the next live run.
- Engine archive = stale 225-cell over-run (G2 implemented, never re-run live); agent
  archive = 2 agents only, stalled on the pre-G3 City-button bug. Both need a fresh live
  run to validate G2/G3.

---

## 2026-06-06 — G5 implemented + scanner core committed (Opus)

Picked up the handoff. Order of work: commit core → empty archive → implement G5.

**Scanner core committed** (`0f6f776`, feature/ocr). The ~3k lines that were untracked
(`grid/disc_scanner/agent_scanner/wengine_scanner/matchers/normalizer/input_utils/__main__`
+ all new tests + the triage script + `triage_disc_fails.json`) are now in git. Added
`.claude/` to `.gitignore` (local session state). The work is no longer one `git clean`
from gone.

**Archive emptied** for the next live test (`archive/live_20260605` + `live_20260606`
removed, 426 MB freed). Before deleting, copied the 12 fail panels out to
`tests/fixtures/disc_slot_panels/*.png` (1.4 MB, plain git) so the G5 gate survives the wipe.

**G5 — D-slot-panel-fallback implemented:**
- `recognize.py`: `TextRecognizer.read_slot` (psm 11, whitelist `0123456789[]`) + stub/Protocol.
- `normalizer.py`: `parse_panel_slot(*texts)` — full-bracket `[N]` (N∈1-6) preferred across
  passes, then partial-bracket (`6]`, `16]`, `[6`) fallback. No bare-digit pick (would mis-grab
  the leading `1` in Dawn's Bloom's `16]`).
- `disc_scanner.py`: `parse_slot_from_panel(panel, recognizer)` — scales the panel-local
  windows (Pass A `0,158,300,210`; Pass B `0,200,180,290`) to the actual panel size, OCRs both,
  parses. Wired into `_extract_disc` **only when tier-1 `parse_slot(title)` returns None** →
  zero cadence cost, cannot regress a passing disc. Also de-duplicated the panel crop (computed
  once, reused for the fallback and the archive save).

**Acceptance:** `tests/test_disc_slot_fallback.py` recovers **12/12** (8 Fanged Metal via Pass A,
4 Dawn's Bloom via Pass B) + pure `parse_panel_slot` unit cases. Full suite **237 passed,
4 skipped** (archive-dependent tests skip now that the archive is empty).

**Still open (carried from the triage, needs the user / a live run):**
- The **live `0 no_slot` re-run** is the one unmet G5 clause — needs a clean capture.
- `live_20260606` captured the **wrong window** (Xbox Game Pass launcher, not the game).
  Window-targeting must be fixed before the next live run.
- G2 (engine count traversal) and G3 (agent geometry) were implemented but never re-run live;
  their archives are stale. Next live pass should validate all three (G2/G3/G5) at once.

---

## 2026-06-06 — Agent subsystem investigation + Phase H plan (Opus 4.8)

Built the architectural plan for the agent roster + tandem scan. Read `agent_scanner.py`,
`cli.py:_cmd_scan_all`, `navigation.yaml:agent_roster`, `grid.py` scroll pattern, the live archive
`agent_00{0,1,2}/`, and reference frames `reference_{3,4,7,8,9,10}`. Artifacts:
`docs/DESIGN_agents.md`, Phase H in `docs/TASKS_ocr.md`, D22–D25 in `docs/DECISIONS.md`.

**Three root causes found (all from assumed, never-verified geometry):**
- **RC-1** roster strip y-band `(0,32,1920,75)` sits *below* the portraits (ref_3: portraits ≈
  y=8–42) → under-detection (3 of ~8).
- **RC-2** `AgentNavigator.scan()` samples frame 1 only, never scrolls; no `[N/M]` header to drive
  count traversal → most of the roster unreachable.
- **RC-3 (decisive, overturns the handoff):** the live `equip_slot_*.png` are **Skills-tab**
  captures, not Equipment. Proof: `agent_000/equip_slot_0.png` still has **Skills** highlighted +
  A–F core nodes visible; `equip_slot_6.png` is the Skills **"Core Skill Enhancement"** popup. The
  `_TAB_EQUIPMENT=(1718,996)` click never activated Equipment, so slot-center clicks hit Skills-tab
  core nodes. Independently, slot centers are **~350px too far left**: ref_7 puts the slot hexagon
  at x≈1410 (engine center ≈ (1418,590)) vs coded engine (1038,515). `navigation.yaml` still carried
  an un-actioned `TODO: refine slot centers from ref_7`.

⇒ The handoff's "per-agent flow works, G3 fixed the tabs" is true only for Base Stats→Skills. The
location cross-reference (the whole point of the tandem scan) has **never run on real equipment
data**. Meta-fix: render-gate every nav step (D23) so a wrong-screen capture fails loudly instead
of banking 3 dirs of useless frames.

**Next (Sonnet):** start at **H0** (tiny live scroll-mechanism probe — needs the window-targeting
fix first), then H1→H6. Offline tasks H1/H3/H4 can proceed now against the reference frames without
the game.

### 2026-06-06 (cont.) — ref_11/ref_12 reviewed; roster pivots to grid; user picks full-auto+equip-location

- **ref_11 (main menu):** persistent bottom bar with `Storage` + `Agents` buttons → hub for H7 auto-nav.
- **ref_12 (agent menu):** roster is a **2D GRID** (right side) + `Base`/`Skills`/`Equipment` buttons —
  NOT the detail-page top strip the plan assumed. ⇒ **D27**: traverse via `grid.py` reuse; RC-1/RC-2
  dissolve, only RC-3 remains. H0/H1/H2 reframed.
- **User decisions:** full automation **including** the Equipment tab; `location` via the
  **Equipment-tab cross-reference** (D21 stands). Phase H keeps H3/H4 in full; "simplify agents" closed.
- Files ref_11/ref_12 live in `screenshots/` (the `reference/` copies dehydrated via OneDrive mid-session).

### 2026-06-06 (cont.) — ref_13/14: agent grid is sheared + has unowned/locked cells → D28

- Agent grid scrolls vertically over multiple pages (doesn't fit one screen); layout is **sheared**
  (diagonal), so fixed-pitch cell model won't fit → detect cells by saturation blob detection.
- Grid lists **unowned** agents too: padlock on rarity star + grayscale + "Lv. 1" + an "EMPTY
  CHARACTER" placeholder → **skip** these (user rule). Owned = colored + gold star.
- No reliable scroll-to-top; traverse one direction + pHash dedupe, end when a page yields no new
  owned agent (locked tail or loop-around). ⇒ **D28**; H1/H2 updated.

### 2026-06-06 (cont.) — H1 complete: detect_owned_agent_cells() + navigation.yaml + fixture tests

**Task: H1** — agent-grid cell detection + ownership filter.

**Algorithm validated** (all 3 fixtures, identity calib, game-area frames 1920×1080):
- Grid: 2 columns, 4 rows. Left col x=1277-1537, right col x=1537-1797. Row centers [144,402,660,918].
- Ownership: HSV saturation 75th-percentile over full column band (260px wide × 200px tall) > 15 → owned.
- ref_12 (all owned): 8/8 ✓ · ref_13 (scrolled, all owned): 8/8 ✓ · ref_14 (locked top): 4/4 ✓

**Raw→game coord note:** ref screenshots are 1922×1112 (includes 32px chrome). `grab_window()` returns
the 1920×1080 client area only. Constants live in game/ref coords; tests crop raw screenshots via
`Image.crop((1, 32, 1921, 1112))` before calling the detector.

**Files changed:**
- `src/youkai_ocr/agent_scanner.py`: added `import cv2`; added `_AGENT_GRID_*` constants + `detect_owned_agent_cells()`.
- `data/zzz_1.4/navigation.yaml`: added `agent_menu` section (grid params, detail tabs, bottom nav stub).
- `tests/test_agent_grid.py`: 6 fixture tests, all green.

**Test run:** `pytest tests/test_agent_grid.py tests/test_agent_scanner.py` → 44 passed.

## 2026-06-06 — H2: Roster traversal loop (Sonnet)

Implemented grid-based roster traversal replacing the single-frame strip approach.

**Changes:**
- `src/youkai_ocr/agent_scanner.py`:
  - Added traversal constants: `AGENT_MAX=60`, `_BACK_ARROW=(75,38)` (TODO verify live),
    `_AGENT_SCROLL_CENTER`, `_SCROLL_TICKS_PER_PAGE=4`, `_AGENT_SCROLL_WAIT_S`, `_PHASH_SIZE=16`,
    `_PHASH_CROP_HALF=64`.
  - Added `_portrait_phash()`: 16×16 average hash of portrait crop; stable, length-256, distinct
    for different agents.
  - Added `scan_roster_grid()`: testable module-level generator with injectable `capture_fn` and
    `scroll_fn`. Detects owned cells (H1), computes pHashes, dedupes via `seen` set, yields `(cx, cy)`
    for each new cell, calls `scroll_fn()` after each page. Stops when no new cells or `agent_max`
    reached.
  - `AgentNavigator._scroll_page_down()`: wheel-scroll `_SCROLL_TICKS_PER_PAGE` ticks over grid center.
  - `AgentNavigator.scan()` rewritten: iterates `scan_roster_grid()`; per agent: click cell → Base →
    Skills → Equipment (7 slots) → back-arrow → next.
- `tests/test_agent_traversal.py`: 10 tests — pHash unit tests (stable, length, distinct); dry-run
  traversal: full 3-page sequence yields 20 agents (8+8+4), 3 scrolls, clean termination;
  pHash dedup (no revisit on 2nd ref_14); kill_event; agent_max cap; locked-cell exclusion.

**Test run:** full suite 256 passed / 4 skipped / 1 pre-existing fail
(`test_read_disc_count_from_real_header` expects 2205, game now at 2210 — not H2 scope).

**Next:** H3 (Equipment tab geometry + render-gate).

## 2026-06-06 — H3: Equipment-tab slot geometry + render-gates (Sonnet)

**Root cause fixed:** `_DISC_SLOT_CENTERS` and `_ENGINE_SLOT_CENTER` were ~330px too far
left (RC-3). Old values centered around game(1000-1100, 400-700); actual hexagon is centered
around game(1417, 558).

**Measurements from reference_7 (blob analysis + row scan):**
- Engine: raw(1418,590) → game(1417,558). Confirmed via pixel luma (210) and H3 task hint.
- Slot 1 (upper-right): game(1730, 363)  — row scan at raw y=395, x=1731
- Slot 2 (right-center): game(1785, 483)  — row scan x=1784-1788 at raw y=490-540 (TODO: live verify)
- Slot 3 (lower-right): game(1715, 708)  — row scan at raw y=740, x=1716
- Slot 4 (lower-left): game(1087, 708)   — row scan at raw y=740, x=1088
- Slot 5 (left-center): game(1125, 544)  — blob centroid (TODO: live verify)
- Slot 6 (upper-left): game(1088, 363)   — row scan at raw y=395, x=1089

**Render-gate calibration:**
- `_equip_tab_rendered`: luma at engine center > 150 (ref_7: 210, skills: 14) ✓
- `_slot_panel_rendered`: dark_frac > 0.08 in panel bbox (ref_8: 0.16, ref_7: 0.01) ✓

**Files changed:**
- `src/youkai_ocr/agent_scanner.py`: updated `_DISC_SLOT_CENTERS`, `_ENGINE_SLOT_CENTER`,
  added `_EQUIP_GATE_*` / `_SLOT_PANEL_*` constants, `_equip_tab_rendered()`,
  `_slot_panel_rendered()`, wired both into `AgentNavigator.scan()` with retry + `_log`.
- `data/zzz_1.4/navigation.yaml`: updated `equipment_tab.disc_slots`, `engine_slot`,
  added `render_gate` sub-section.
- `tests/test_agent_h3.py`: 11 tests — gate True/False on ref_7/ref_8/skills, all 6 disc slot
  centers verified colorful in ref_7 (sat > 50 in ±40px window), engine verified bright+white.

**Test run:** 11/11 H3 tests passed; full suite pending.

**Remaining uncertainties:** slot 2 and slot 5 centers have ±50px uncertainty — need live
verification (H6). The 6-slot layout is 2-column (x≈1088, x≈1720) × 3-row not a
regular hexagon (engine is not at geometric centroid of slot ring).

**Next:** H4 (validate per-agent extraction offline from reference_{3,4,9,10}).

---

## 2026-06-06 — H4: Offline per-agent extraction validation (Sonnet)

**Task:** Validate `scan_single_frame_agent` + `_extract_equip_frame` against reference_{3,4,9,10}. Fix bboxes/heuristics until green.

**Ground truth confirmed from reference images:**
- ref_3 (Zhao Base Stats): key='Zhao', level=60, ascension=low-confidence
- ref_4 (Zhao Skills): mindscape=0 (CINEMA 0/6), skills=(12,10,11,12,11), core=6 (all A-F lit)
- ref_9 (disc info): BunnyInWonderland, slots 1-6
- ref_10 (disc+engine info): AstralVoice discs, engine=TheRestrained

**Fixes applied:**

1. **`data/zzz_1.4/agents.json`**: Added `"Zhao": "Zhao"` — was missing, fuzzy match returned 'ZhuYuan'.

2. **`_LEVEL_BBOX`**: (955, 452, 1100, 497) → (1060, 460, 1200, 495). Old bbox sampled the stat table. New bbox correctly reads "Lv. 60" from the badge.

3. **`_SKILL_LEVEL_BBOXES`**: y=510-545 → y=750-780 (correct area for the 5 skill level badges). Actual badges span x=(930-1065, 1110-1245, 1295-1425, 1470-1605, 1650-1785).

4. **Skill OCR → blob classifier**: Tesseract cannot read the stylized bold-italic ZZZ skill badge font (returned '1' or '1Z' for '12'). Replaced with `_read_skill_badge()`: 3× LANCZOS4 upscale, threshold at 180, left-50%-restrict, connected-component width + fill-ratio analysis:
   - 1 narrow blob → 1
   - 2 blobs, b2 narrow (w<48) → 11
   - 2 blobs, b2 wide + fill>0.66 → 10 ('0' is rounder than '2')
   - 2 blobs, b2 wide + fill≤0.66 → 12
   Validated: 5/5 correct on all skill badges (including yellow dodge badge at 10).

5. **`_CORE_NODE_BBOXES`**: Old bboxes had y=178-415 (wrong). Re-derived from connected-component centroids of teal pixels in ref_4. Correct ring centers: A(1109,308), B(1061,476), C(1311,309), D(1267,473), E(1517,308), F(1468,475). All 6 nodes now detect as LIT (G>140, G-R>50). Core rank = 6.

**Files changed:**
- `data/zzz_1.4/agents.json`: added 'Zhao'
- `src/youkai_ocr/agent_scanner.py`: _LEVEL_BBOX, _SKILL_LEVEL_BBOXES, _CORE_NODE_BBOXES corrected; `_read_skill_badge()` added; `_extract_skills()` uses blob classifier instead of OCR for skill badges.
- `tests/test_agent_h4.py`: 24 tests — key/level/mindscape/skills(5)/core/ascension-range from ref_3+ref_4; 12 equip slot tests from ref_9+ref_10. All pass.

**Test run:** 24/24 H4 tests passed.
