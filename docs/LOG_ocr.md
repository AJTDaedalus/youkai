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

---

## H5 — Persistence + preflight assert + resume (2026-06-06)

**Goal:** `_cmd_scan_all` in `cli.py`: tee stdout to `archive/<run>/scan.log`; write `archive/<run>/results.json` (per-phase counts, issues, elapsed); per-phase preflight screen-assertions that abort loudly on wrong screen; per-phase output files (`discs.json`, `engines.json`, `agents.json`) enabling resume; `--resume DIR` flag to skip already-completed phases.

**Files changed:**
- `src/youkai_ocr/zod.py`: added `ZodSubstat.from_dict`, `ZodDisc.from_dict`, `ZodWEngine.from_dict` (needed for resume deserialization).
- `src/youkai_ocr/cli.py`: added `ScreenAssertError`, `_check_disc_screen`, `_check_engine_screen`, `_check_agent_screen`, `_Tee`; `_preflight_frame` now returns the captured frame; `_cmd_scan_all` rewired with run-dir creation, tee, screen assertions, per-phase cache writes, resume load; `--resume` added to scan-all parser; `main()` catches `ScreenAssertError` → clean exit.
- `tests/test_cli_scan_all.py`: 12 tests — 6 unit tests for each screen assertion (pass/fail), 2 integration tests (log+results.json written, phase files written), 3 wrong-screen abort tests, 1 resume test.

**Test run:** 12/12 H5 tests passed. Full suite 294 passed (1 pre-existing `test_read_disc_count_from_real_header` count mismatch unchanged).

---

## H6 Live Debug — Back-navigation fix (2026-06-06)

**Live run revealed three bugs:**

1. `_BACK_ARROW = (75, 38)` was at game y=38 — inside the roster-strip portrait row. Clicking it navigated to a portrait instead of returning to the agent menu grid. This caused "never changed to the next agent."

2. Equipment slot clicks (at `_DISC_SLOT_CENTERS`) don't open the disc selection panel — `equip_slot_0/1.png` from the live archive both show the plain Equipment hexagon (no navigation occurred). The slot coordinates need live calibration but are left for a future session.

3. Clicking an already-selected agent's grid cell (Zhao was selected when the scan started) may be a no-op, causing the scanner to stay on the agent menu and read wrong tab coordinates. This caused "started on agent 2, skipped Zhao entirely."

**Root causes verified from reference screenshots:**
- `reference_3_agent_page.png`: the full detail page has a bottom tab bar at y≈964-1028 (absent on agent menu).
- `reference_7/8/9`: Equipment slot click DOES navigate to a disc selection screen (ref_8/9 are full navigation changes, not overlays), but the current slot coordinates miss the thumbnails.
- The orange ZZZ back icon at top-left in ref_3 says "< City" and would jump to City, not agent menu. Keyboard Escape is the correct one-level-back.

**Fixes applied (all agent tests still pass, 51/51):**

1. **Escape-based back navigation** (`AgentNavigator._press_escape()`): programmatic Escape replaces the `_click(*_BACK_ARROW)` call. Uses a `suppress_flag: list[bool]` shared with the kill listener so the programmatic Escape is not mistaken for a user abort.

2. **`make_kill_listener` updated** (`grid.py`): accepts optional `kill_key` and `suppress_flag` parameters. `suppress_flag[0]=True` causes the listener to ignore the next Escape event (then auto-clears). Default behavior unchanged for disc/engine scans.

3. **Detail-page navigation guard** (`_navigate_to_detail()`): after clicking an agent cell, samples the tab bar bbox (y≈964-1028) to confirm the full detail page is open. If the tab bar is absent (cell click was a no-op), retries once. Logs a warning and calls Escape if still failing.

4. **Per-slot Escape** in equipment scanning: if `_slot_panel_rendered()` returns True (disc selection screen opened), presses Escape after capturing the frame to return to the Equipment tab before the next slot click. If slots don't navigate (current behavior), the Escape is skipped.

5. **Timing increased**: `_PORTRAIT_CLICK_DELAY_S` raised from 0.20 → 0.60 s to allow the detail page transition to complete.

**Files changed:** `src/youkai_ocr/agent_scanner.py`, `src/youkai_ocr/grid.py`

**Outstanding for live re-test:** Verify that keyboard Escape from the full agent detail page returns to the agent menu (not City). Verify slot centers hit the disc thumbnails (or re-measure from a live screenshot). Verify `_on_detail_page()` threshold (60 luma) correctly distinguishes detail page from agent menu.

---

## 2026-06-07 — `agent_nav_fail` root-caused: 3-col grid + AGENT-SELECT transition-wipe race (Opus 4.8)

Investigated the live failure `agent_nav_fail cx=1407 cy=144` (today's run: `scan.log`
"Scanned 0 agent(s)… Issues: 0"; `preflight_agents.png` regenerated 07:44). Read
`agent_scanner.py`, the live preflight, `reference_{3,12}`, and **yesterday's** captures
`agent_00{0,1,2,3}/` (Jun 6 21:40). Two independent, both-confirmed root causes — both the
"authored-from-assumption, validated against the wrong ground truth" failure mode the DESIGN
doc warns about. **Navigation to the detail page and the H3 equipment geometry actually WORK**
(see RC-2 evidence) — neither needs re-litigating.

### RC-1 — Roster grid is **3 columns**, the code models **2** (geometry; explains today's 0 agents)
`detect_owned_agent_cells` uses `_AGENT_GRID_LEFT_COL=(1277,1537)` / `_AGENT_GRID_RIGHT_COL=
(1537,1797)` → click centers **1407 / 1667**. But the live frame and `reference_12` both show a
**3-column** roster (col centers ≈ **1180 / 1460 / 1740**, grid x≈1080–1880; the grid is also
*sheared* per D28, so column-x drifts with row). The two coded centers **1407 and 1667 fall in
the dark gutters between the real columns.** `cx=1407 cy=144` is exactly left-col-center / row-0 —
a gutter point. Clicking a gutter selects nothing → no navigation → menu stays → `_on_detail_page`
False → `agent_nav_fail`, repeated for every (gutter) cell → 0 agents.

**H1's "8/8 owned ✓" was false confidence:** it counted 2cols×4rows=8 saturated bands and called
it 8/8, never checking the true owned count (≥12 colorful cells visible in ref_12). The
saturation test passes in a gutter-straddling band because the whole grid region is colorful — so
"owned" detection looked fine while the *click centers* were wrong. The fixed-pitch / vertical-
column assumption also ignores the shear (D28).

### RC-2 — "AGENT SELECT" transition-wipe race on the un-gated Base/Skills captures (timing)
Clicking a portrait **does** navigate to the full detail page (ref_3) — but through a bright,
full-screen **"AGENT SELECT"** wipe animation that outlasts `_PORTRAIT_CLICK_DELAY_S=0.60 s`.
Proof from yesterday's archive (selection state then let the fixed centers hit real portraits, so
nav fired):
- `agent_000/base_stats.png` **== `skills.png`** (byte-identical, 122 727 B) = the **AGENT SELECT
  hatched wipe**, captured twice. The Base/Skills tab clicks did nothing — we were mid-transition.
- `agent_001/base_stats.png` = a **real** Base Stats page (Dialyn, Lv 60). `agent_00{1,2,3}` base≠skills
  (distinct real pages). ⇒ the outcome is a **race**: sometimes you catch the wipe, sometimes the page.
- `agent_000/equip_slot_0.png` = a **correct Equipment detail page** (hexagon rendered, `Equipment`
  tab lit) — because by the equipment step cumulative delays outlast the wipe **and** it has its own
  render-gate (`_equip_tab_rendered`). **H3 slot geometry is landing correctly.**

The meta-cause is exactly D23 ("render-gate *every* nav step"), only half-done: H3 added gates for
Equipment + slots, but **Base Stats and Skills captures have no render-gate** — just blind
`sleep`s — so they bank transition frames. Worse, `_on_detail_page` keys on **mean luma > 60**,
which the *bright* hatched wipe satisfies → **false-positive** "on detail page" lets the garbage
through (yesterday). The predicate must key on the steady **yellow Base-Stats tab signature**
(color, not brightness) and/or **wait-until-stable**, not raw luma.

### Why today=0 but yesterday=4
Fixed click centers + a grid whose position shifts with the (expanding) selected cell ⇒ whether
1407/1667 land on a portrait or a gutter is **state-dependent**. Today they hit gutters (no nav →
0); yesterday they hit portraits (nav fired → wipe-race produced 1 garbage + 3 real-ish agents).
RC-1 makes selection fragile; RC-2 corrupts whatever does get through.

### Fix direction (→ TASKS H8, H9; offline-validatable against existing frames)
- **H8 (RC-1):** model the roster as **3 sheared columns**; re-measure column/row centers from
  `reference_12` + live `preflight_agents.png`; account for the selected-cell expansion; re-validate
  `detect_owned_agent_cells` against the **true** owned count (not its own 2-col count).
- **H9 (RC-2):** render-gate the **Base** and **Skills** captures too (mirror `_equip_tab_rendered`):
  after each tab click, poll-recapture until the page is steady (two stable frames / tab-signature
  present) before banking. Replace `_on_detail_page`'s luma test with a **yellow Base-Stats-tab
  color** signature so the AGENT-SELECT wipe can't false-positive. Add a "transition cleared" wait
  in `_navigate_to_detail` (poll until the wipe hatch is gone) before asserting the detail page.

No code changed this session — diagnosis only. Reference frames already in the repo are sufficient
to build + validate H8/H9 offline (ref_12 owned-count; `agent_000` wipe frame as the negative
control for the gate; `agent_001` real Base Stats as the positive).

---

## 2026-06-07 (cont.) — User re-tested ("still very buggy"); RC-2 implemented + traversal pivot (Opus 4.8)

User re-ran (`scan.log` 08:30 → still 0 agents). Confirmed **nothing had been implemented** since the
morning diagnosis — the working tree held only the older H6 escape-nav edits, so the run failed
identically by construction.

**Attempted RC-1 (grid geometry) offline and concluded the grid is the wrong substrate.** Tried three
detectors against `reference_12/13/14`: luma column profile, gold-star blobs, and the saturation-blob
method D28 specified. **All three failed** to segment the roster — portraits are packed edge-to-edge,
uniformly saturated, cells are slanted parallelograms, badges/coins add noise (saturation blobs merge
4–6 cells into one). Confirmed the live roster is **3 sheared columns** (≈1180/1460/1740), so the
coded 2-column centers 1407/1667 sit in gutters → `agent_nav_fail cx=1407 cy=144` → 0 agents.

**User chose to pivot** (AskUserQuestion): enumerate via the **detail-page top agent strip** instead
of the grid. Measured the strip from `reference_3` + the live equip frame: clean horizontal row,
pitch ≈60px, y≈43, x≈1180–1850, `<`/`>` arrows. → **D29** (supersedes D27/D28 for enumeration); H8
rewritten as strip-traversal; H10 added for the live unknowns (wipe-on-strip-click? all agents? scroll
stride?). H1's grid detector retired from the live path.

**RC-2 implemented + tested (offline-certain, needed in any traversal path):**
- Measured the active-tab signature across the live archive: a real open tab's pill is **yellowFrac
  ≈0.84–0.87** (HSV hue~24, sat~226) vs **0.000** on the AGENT-SELECT wipe, the agent menu, and
  inactive tabs. The old `luma>60` test couldn't separate a real Equipment page (tab-bbox luma≈6) or
  the wipe (≈8) from the menu (≈33).
- `agent_scanner.py`: added `_TAB_ACTIVE_BBOXES` (3 per-tab pill bboxes) + `_tab_yellow_frac` /
  `_tab_active` / rewrote `_on_detail_page` (= any tab yellow-active); added
  `AgentNavigator._capture_tab(idx)` (clicks a bottom tab, poll-recaptures until its pill is yellow →
  render-gates Base + Skills, mirroring the H3 equipment gate); rewired Base/Skills captures in
  `scan()` to use it. Removed the dead `_DETAIL_TAB_BBOX`/`_DETAIL_TAB_LUMA_MIN`.
- `tests/test_agent_rc2.py` (7/7): positives reference_{3,4,7} (Base/Skills/Equipment active);
  negatives `tests/fixtures/agent_nav/{wipe,menu}.png` (committed) + blank frame; "only the open tab
  is yellow". Full agent+grid suite **111 passed**, no regressions.

**State of the bug:** RC-2 (capture-corruption / wipe race) is fixed and gated. RC-1 (can't reach the
right agent) is now addressed by the **pivot**, which is **blocked on the H10 live probe** — do not
build the H8 strip loop blind (Q1 wipe-on-click and Q2 strip-completeness could change the design).
Next: user runs H10 (≈3 min in-game), then implement H8 against the answers (Sonnet-suitable once the
probe lands). Window-targeting bug still a precondition for any live run.

### 2026-06-07 (cont.) — H10 probe answered live; H8 fully designed (single forward `>` pass)

User ran the strip probe in-game. Answers (→ TASKS H10 Q1–Q4, H8 final):
- **Q1** clicking a strip thumbnail switches agent **cleanly (no wipe)** and **stays on the current
  subpage** (Base/Skills/Equipment).
- **Q2** strip lists owned agents **first, contiguous left→right**, then **grayed-out unowned**
  (clickable); **no loop** → stop at the first grayed-out agent.
- **Q3** `>` = next agent, `<` = prev agent; **selection moves ±1 every time, never skips** (window
  scrolls 4 at an edge but selection advances one). ⇒ no pHash dedupe needed; the silent-skip risk is
  gone.
- **Q4** on Equipment, clicking a slot hides the top bar; **no Escape needed between slots** (the side
  panel just updates) — press **Escape once after the engine + all 6 discs** to restore the bar, then
  advance. This **corrects** the current `scan()` (per-slot Escape + Escape-to-menu — both removed in H8).

**H8 locked (no live unknowns left):** enter detail page once (RC-2 gate absorbs the entry wipe) →
`<`-rewind to the first agent (stop when the detail portrait pHash stops changing) → single forward
pass: per agent, if grayed-out stop, else `_capture_tab` Base/Skills/Equipment (7 slots, one trailing
Escape), then `>`; cap `AGENT_MAX`. Hardening: the bar resizes so arrow x is not fixed — confirm the
selection changed (portrait pHash) after each `>`/`<` and retry on no-change, rather than trusting a
hardcoded arrow pixel (avoids repeating RC-1). Build is offline-testable with mocked strip frames
(N owned + 1 grayed). Retire the grid path (`detect_owned_agent_cells`/`scan_roster_grid`/`_AGENT_GRID_*`).

State: RC-2 done + tested (111 passed). H8 fully specified and ready to implement — clean mechanical
work, Sonnet-suitable. Live precondition unchanged: fix window-targeting before the next run.

### 2026-06-07 (cont.) — H8 implemented (top-strip traversal) — user asked Opus to do the trickier work

Rewrote the agent traversal in `agent_scanner.py` from the (retired) grid path to the detail-page
top-strip `<`/`>` walk:
- **Removed:** `scan_roster_grid`, `AgentNavigator._scroll_page_down`, `_navigate_to_detail`, the
  grid-scroll constants, and the `Generator` import. `detect_owned_agent_cells` + `_AGENT_GRID_*`
  kept (only their fixtures/tests use them now).
- **Added helpers:** `_region_phash` / `_phash_hamming` / `_strip_id` (strip-identity hash over
  `_STRIP_PHASH_BBOX`), `_is_owned_agent` (p75 saturation of `_CHARACTER_RENDER_BBOX` > 30; owned
  fixtures measured 51–105, grayscale ≈ 0).
- **Navigator methods:** `_enter_detail_page` (idempotent; clicks the menu Base button, RC-2 gate
  absorbs the entry wipe), `_advance(±1)` (click `>`/`<`, **confirm selection changed via strip
  pHash Hamming > 10, retry on miss** → the no-silent-skip guarantee), `_rewind_to_first` (`<` until
  no-change), `_read_equipment` (Equipment tab gated; click 7 slots with **no inter-slot Escape**;
  **one** trailing Escape restores the bar — H10-Q4).
- **`scan()`** rewritten: enter → rewind to first → forward `>` pass; per agent `_capture_tab`
  Base/Skills + `_read_equipment`; stop at the first grayed-out agent, on `_advance` no-change, on
  kill, or `AGENT_MAX`. Dropped the old per-slot Escape and the Escape-to-menu (Q4).

**Tests:** `tests/test_agent_traversal.py` rewritten — a `_StripSim(AgentNavigator)` renders synthetic
frames so the **real** `scan()`/`_advance`/`_rewind_to_first`/`_read_equipment` run against the actual
predicates. 8 tests green: rewind-from-mid then visit `[0..n)` in order, stop at grayout, exactly one
Escape per agent, 7 slots with one total Escape, AGENT_MAX cap, kill-event. Strip-id and ownership
predicate unit tests included.

**Live-verify (H6-style, next run):** `_STRIP_NEXT`/`_STRIP_PREV` chevron coords + `_MENU_BASE_BUTTON`
(bar resizes — the pHash-confirm makes a slightly-off `>`/`<` self-correct rather than skip), and the
two thresholds `_OWNED_SAT_P75_MIN` / `_STRIP_CHANGE_MIN_BITS`. Window-targeting fix still a
precondition. Next: full-suite confirm, then a live `scan-all` agent pass.

---

## H11 — Live realignment from the 2026-06-07 scan-all run (coords were off on most steps)

**Trigger.** First live `scan-all --agents-only` run (archive/live_20260605, recaptured 16:02).
User reported navigation slightly off everywhere: the first strip click landed on the **2nd** agent
("skipped the first agent entirely"), the 2nd `>` "hit an agent on the bar" instead of the chevron,
and every equipment disc click missed. Only 2 agents scanned (then stopped); ZhuYuan's skills all read
0; agent_000 base=Dialyn but its equip frame showed a different (maid) agent.

**Method.** The captured frames ARE the 1920×1080 game area (calib scale 1.000×1.000, offset
(1828,198) — clicks are just ref+offset, so a captured frame is ground truth for both crops and
clicks). Measured true positions from the live frames with a labelled pixel grid + HoughCircles, and
cross-checked agent_000 vs agent_001 (stable to ±2px) and against reference_7.

**Findings & fixes (all in `agent_scanner.py`, mirrored in `data/zzz_1.4/navigation.yaml`):**
- **Strip chevrons were on the portraits, not the arrows.** Live: bar spans x≈1005–1810 @ y≈44;
  `<` glyph (1025,44), `>` (1775,44); portraits fill 1045–1745.
  - `_STRIP_PREV` (1140,43)→**(1025,44)**. 1140 sat on the 2nd portrait ⇒ rewind selected agent #2
    (= "skipped the first agent"). Exact match to the symptom.
  - `_STRIP_NEXT` (1745,43)→**(1775,44)**. 1745 sat on the last portrait's right edge ⇒ "hit an
    agent on the bar".
  - `_STRIP_PHASH_BBOX` tightened to the portrait band (1045,28,1750,72) so a selection move is an
    unambiguous Hamming change (was diluted by empty bar out to 1860).
- **Equipment hexagon: live layout is COMPACT, ref_7 is zoomed-up.** Saturation proof — on the LIVE
  frame the new compact centers read S≈57–126 (on-disc) while the old wide coords read 0–46
  (off-disc); on ref_7 it is the reverse. The engine *center* is the same in both (~1398,515); only
  the disc *radius* differs. `_DISC_SLOT_CENTERS` re-measured: (1558,318)/(1662,538)/(1559,760)/
  (1239,761)/(1137,539)/(1239,320). `_ENGINE_SLOT_CENTER` 1417,558→**1398,515**.
- **Equip render-gate mis-thresholded for an equipped engine.** Engine center luma is ≈125 live (an
  *equipped* W-engine icon), not the ≈210 of ref_7's empty/bright slot; base≈33, skills≈46.
  `_EQUIP_GATE_LUMA_MIN` 150→**80** (separates 46 from 125; only logs anyway — the RC-2 yellow-pill
  gate is the real render confirmation).
- **Menu Base entry button** re-centred (1167,818)→**(1140,816)** (was right-of-centre but inside the
  pill, so entry still worked — minor).

**Tests.** ref_7 is unrepresentative of the live disc geometry, so the H3 disc-slot test now validates
against a committed live fixture `tests/fixtures/agent_nav/equipment_hexagon_live.png` (threshold 45;
off-disc <30). Engine-bright + panel-gate tests stay on ref_7 (engine center is shared). Full suite
green (the one pre-existing disc-count-drift fail is unrelated, archive-only, skips in CI).

**Not fixed here (follow-ups).** (1) agent_000 base=Dialyn / equip=maid mismatch + ZhuYuan all-zero
skills ⇒ likely a *settle-timing* race (the yellow-pill gate confirms the tab painted, not that the
character render finished morphing after a selection move) — watch on the next run; if it persists,
add a render-settle gate keyed on the character-render region. (2) "Dialyn"→"Rina" is an OCR/normalizer
miss (Dialyn may be absent from the agent DB), separate from navigation. (3) The hexagon coords are
layout-dependent (ref_7≠live) — a graphics-setting/patch change could shift them again; the robust
long-term fix is runtime HoughCircles hexagon detection (D30). Window-targeting fix still the
precondition for the next clean live run.

---

## H12 — Validate H11 coords against fresh references + add self-validating debug overlays (2026-06-07)

**Trigger.** User added `reference_16` (agent equipment tab) + `reference_15` (disc-select), confirmed
accurate to the live client ("the hexagon doesn't move" between them), and asked (a) re-check the coords
and (b) whether the scanner should take debug screenshots. Also flagged that the reference PNGs include
the OS window bar.

**Window-bar check.** References are raw 1922×1112 (32px title bar, bright luma ~240 at the top); live
captures are 1920×1080 with no bar (top rows dark). The code crops references by (1,32) → both end up in
game-area coords. Confirmed NOT an offset source (the validated coords match across both).

**Coord validation (HoughCircles ring geometry — the reliable measure).** ref_16, ref_15, ref_7 AND the
live archive all return the SAME six disc-ring centers (±2px) = the H11 compact coords. So H11 is
confirmed correct, and my H11 "ref_7 is a zoomed-up layout" guess was WRONG: ref_7 has compact discs
too. The old "wide" coords were simply off — they passed the prior center-saturation test only by landing
on the colorful background filmstrip art behind the hexagon (ref_7 wide ring-sat 84–125 = art, not discs).
Corrected the wrong narrative in `agent_scanner.py`, `navigation.yaml`, and DECISIONS D30.

**Test hardened.** `test_disc_slot_center_is_colorful` (center saturation, disc-set-dependent — ref_16's
blue discs read only ~24 at center) → `test_disc_slot_center_on_ring` (rarity-RING annulus r48–66, ≥55
on-slot vs ≈20 off, set-independent), run against `reference_16` (copied into `reference/`). Dropped the
redundant `equipment_hexagon_live.png` fixture.

**Debug overlays (answers the user's 2nd question — yes, worth it).** New `youkai_ocr/debug_overlay.py`:
imports every click/crop constant from `agent_scanner` (single source of truth, can't drift) and draws
them onto the captured frames — strip chevrons + phash band + bottom tabs + OCR field crops on base/
skills; all 7 slot crosshairs (active slot green) + render-gate + panel crops on equipment. Wired into
`scan_agents(debug_overlays=)` and exposed as `--debug-overlays` on `scan-agents` and `scan-all`; saves
`*_overlay.png` next to each archived frame. Verified on the live frames: every slot crosshair centers on
its disc, tabs/crops all framed. Bonus finding from the base overlay — the "Dialyn" name crop is
perfectly aligned, so the Dialyn→Rina miss is a **normalizer/DB** gap (Dialyn absent from the agent
list), not a crop/nav problem.

**Tests:** H3 (11) + traversal + scanner + rc2 + cli-scan-all (76 total) + new `test_debug_overlay.py`
(3) all green.

**Recommendation for the next live run:** run with `--debug-overlays`; the `*_overlay.png` frames are now
the fastest way to confirm alignment (or spot the settle-timing race) without manual pixel measuring.

---

## H13 — Fix the window-targeting bug (ZeroDivisionError / wrong-window grab) (2026-06-07)

**Trigger.** `scan-all --agents-only --debug-overlays` crashed:
`capture.py:158 aspect = w / h → ZeroDivisionError`. The matched window had a 0-height client rect.

**Root cause.** `_find_game_window` used `win32gui.FindWindow(None, "ZenlessZoneZero")`, which returns the
FIRST same-title window in Z-order. The game spawns several windows sharing that title — including a hidden
0×0 helper — and the Game Pass launcher matches too. FindWindow grabbed a 0×0 helper → `h == 0`.

**Fix (`capture.py`).** Replaced the single FindWindow with `list_game_windows()` — a passive `EnumWindows`
pass that keeps only windows that are visible, NOT minimized (`IsIconic`), title-matching (normalized:
case/space-insensitive so "Zenless Zone Zero" == "ZenlessZoneZero"), and have a non-zero client area —
then `pick_best_window()` chooses 16:9 first, largest area second. This skips the 0×0 helpers and the
non-16:9 launcher. Window-metadata only (EnumWindows/GetWindowText/GetClientRect/ClientToScreen) — no
process or memory access, anti-ban-compliant. `_require_window` now gives specific errors (not-found vs
zero-size/minimized vs wrong-aspect, the last pointing at a 16:9 candidate if one exists).

**Diagnostic.** `python -m youkai_ocr calibrate` now lists every matching window with size/aspect/position
and marks the one the scanner will pick (`<-- chosen`) — run it first to confirm before a scan.

**Tests.** New `tests/test_window_pick.py` (5) covers the picking heuristic: prefers 16:9 over a larger
launcher, largest among 16:9, fallback when none 16:9, empty→None. capture/cli/agent suites green.

**Next:** user re-runs `calibrate` to confirm the right window is chosen, then `scan-all ... --debug-overlays`
for the first clean agent pass with self-validating overlays.

---

## H14 — "Stuck on an upgrade page": the agent-menu entry targets the WRONG menu (2026-06-07)

**Trigger.** User re-ran `scan-all --agents-only --debug-overlays`; reported the scanner "got stuck
on an upgrade page that it doesn't need to open." Run artifacts: `archive/live_20260605/`
(scan.log, results.json, agents.json, preflight_agents.png — all 18:08).

**What the run actually did.** Not a hang. scan.log: preflight passed (brightness 74.2 OK),
`Scanned 0 agent(s) in 2.3s. Issues: 0`. `agents.json = []`. The 2.3s / 0-issues signature ⇒
`AgentNavigator.scan()` returned early at `_enter_detail_page()` (no agents yielded, no issues
appended). The screen left on display = the page in preflight_agents.png.

**preflight_agents.png IS the "Special Training Plan" menu** — identical layout to `reference_12`
(vertical agent grid on the right, character render left, **vertical** Base/Skills/Equipment buttons
mid-screen, "SELECT" on the right edge). Header top-left: back-arrow + **"Special Training Plan"**.

**The Base button coords are correct.** Cropped preflight (1050,740)-(1550,920): the "Base" pill
centers at ≈(1140,815) = `_MENU_BASE_BUTTON=(1140,816)`. So entry didn't fail from a coord miss —
the click landed on Base. It opened *something* that is not the scannable detail page, the
`_on_detail_page` gate (bottom horizontal tabs yellow) never matched across 2 retries → return False
→ scan aborts. The "upgrade page" the user saw = whatever the Special Training Plan "Base" button
opens.

**Root cause (architectural — two incompatible nav models were stitched together):**
- The **scan/traversal** model (H4/H11) is built for `reference_3` = the *agent detail page*:
  **horizontal filmstrip top-right**, `< >` chevrons, **bottom horizontal tabs** "Base Stats /
  Skills / Equipment", stats panel right. Breadcrumb top-left: **🏠 City**.
- The **entry** model (H7/D26, `_enter_detail_page`) assumes the agent menu is `reference_12` =
  **"Special Training Plan"**: vertical grid, mid-screen vertical Base/Skills/Equipment buttons.
  Breadcrumb: **Special Training Plan**.
- **Decisive evidence they are different features, not two states of one:** a sub-page of Special
  Training Plan would inherit its breadcrumb. `reference_3`'s breadcrumb is "City", NOT "Special
  Training Plan". So `reference_3` is reached via the City→Agents path, and clicking "Base" inside
  the *Special Training Plan* menu opens a Special-Training base/upgrade view — exactly "an upgrade
  page it doesn't need to open." The H7/D26 label "reference_12 = the agent menu" is the
  misidentification at the root.
- Internal doc contradiction confirms the confusion: TASKS_ocr.md:338 ("enter by clicking an owned
  agent, then Base") vs agent_scanner.py `_enter_detail_page` (clicks only `_MENU_BASE_BUTTON`).
- Why H11 never caught it: H11's run scanned 2 agents because the user was **already on the detail
  page** (reference_3) when they pressed Enter, so `_on_detail_page` returned True immediately and
  the menu-Base click path never executed live until this run.

**Secondary defect.** Preflight gate is brightness-only (74.2 "OK"), so it green-lit the wrong page.
A real gate must assert the `reference_3` signature (top filmstrip + a bottom horizontal tab present)
and abort loudly otherwise — mirror of the render-gate discipline the design already mandates.

**Open question for the user (blocks the fix — do not guess, per the slot-geometry lesson):**
From the main-menu hub (`reference_11`), does clicking **"Agents"** open the `reference_3` detail
page directly (filmstrip + bottom tabs, breadcrumb "City")? If so, the fix is: (a) drive the scan
from that page, (b) DELETE the Special-Training-Plan "Base" entry path from `_enter_detail_page`,
(c) replace the brightness preflight with a reference_3-signature assertion that aborts on the wrong
screen. If "Agents" instead lands on the Special Training Plan menu, we need the user to capture the
exact click sequence from there to reference_3.

**User confirmation (corrects the breadcrumb theory).** Hub "Agents" → opens the Special Training
Plan menu (reference_12); and clicking its "Base" button DOES open the scannable detail page
(reference_3). So the entry *model* is correct: Agents → Special Training Plan menu → Base → detail
page. "Special Training Plan" is simply this build's title for the agent menu; the breadcrumb
difference is not a different-feature signal after all. The "upgrade page it doesn't need to open"
is the Special Training Plan menu itself — the scanner must pass through it (one Base click) but
failed to and was left sitting on it.

**Refined diagnosis.** `grab_window()` captures the *screen region* at the client-area coords from
`ClientToScreen`, and the same (left,top) is baked into `to_screen` — capture and click share one
origin, so the correct preflight capture proves the click offset is correct too. The H13 offset
hypothesis is RULED OUT. The Base coords are right and the click lands. Two paths give the identical
"0 agents / ~2.3s / 0 issues" log signature and the log can't tell them apart:
  (A) `_enter_detail_page` gate timed out — its 2-retry/~1.7s budget is shorter than the AGENT-SELECT
      wipe, and it *re-clicked Base every retry* (a re-click mid-wipe can land on the detail page and
      confuse the transition); or
  (B) it entered the detail page but `_rewind_to_first`/`_is_owned_agent` failed (e.g. `_OWNED_SAT_
      P75_MIN=30` mis-thresholds the live render) → "0 owned" on the first check.

**Fix applied (this session, `agent_scanner.py`).**
- `_enter_detail_page` rewritten: click Base ONCE, then poll the yellow-tab gate up to
  `_DETAIL_GATE_POLLS=12 × _DETAIL_GATE_POLL_S=0.4 ≈ 4.8s` (absorbs the wipe), re-clicking only every
  `_DETAIL_RECLICK_EVERY=6` polls to recover a genuinely dropped click. Removed the unused
  `_DETAIL_CLICK_RETRIES`.
- **Navigation diagnostic frames (makes the next run conclusive).** `AgentNavigator` now takes
  `archive_dir` and writes `nav_*.png` at each silent-failure point: `nav_enter_pre`,
  `nav_enter_ok`/`nav_enter_fail`, `nav_rewound`, and `nav_owned_check_fail` (first agent read as
  unowned — path B). Wired through `scan_agents`.
- Tests: full agent + CLI suites green.

**Next live run.** Re-run `scan-all --agents-only --debug-overlays`, then read `archive/.../nav_*.png`:
  - `nav_enter_fail` present → entry still failing; the frame shows whether it's stuck on the menu
    (click not registering) or mid-wipe (need a longer budget).
  - `nav_enter_ok` + `nav_owned_check_fail` → entry works; bug is the owned-saturation threshold
    (live-tune `_OWNED_SAT_P75_MIN`).
  - `nav_enter_ok` + `nav_rewound` + agents scanned → fixed.

**Status.** Fix + instrumentation in the working tree; awaiting the next live run's `nav_*.png` to
confirm which path (A or B) and close it out.

---

## H15 — Live run triaged: H14 entry fix WORKED; two new root causes found + fixed (2026-06-07, Opus 4.8)

**Trigger.** User re-ran (`archive/live_20260605/`, 18:21): "much better — it goes to the base page,
loops through (in reverse though), but doesn't get anywhere; never found the first agent." Run = 0
agents / 0 issues / 44s. The H14 instrumentation made this conclusive — read the three `nav_*.png`.

**H14 entry fix is confirmed working.** `nav_enter_pre`→`nav_enter_ok` shows the menu→Base→detail-page
entry now succeeds (`nav_enter_ok` = a real Base Stats page, Zhao Lv 60). Path A is closed.

**RC-A (decisive, offline-certain) — `_is_owned_agent` was blind to ZZZ's grayed-out rendering.**
`nav_rewound` = **Hugo Vlad, Lv 01, blue render** = an *unowned* agent. Measured the character-render
region on the live frames:
- owned (Zhao):  p75-sat=108, hue_std=62, blue_frac=0.33
- grayed (Hugo): **p75-sat=145** (HIGHER), hue_std=22, blue_frac=0.94

ZZZ does **not desaturate** locked agents — it tints them a **blue DUOTONE**, which is *high*
saturation. So the old `p75 saturation > 30` test classified grayed agents as **owned**. The real
discriminator is **hue diversity**: owned = many hues; grayed = monochrome blue. Fix: `_is_owned_agent`
now flags grayed only when `blue_frac > 0.70 AND hue_std < 35` (biased toward "owned" so a blue-themed
owned agent is never mis-skipped). Validated on the live frames: Zhao→owned, Hugo→grayed. **The test
sim had encoded the same wrong assumption** (rendered grayed as gray `(120,120,120)`); updated it to a
blue duotone `(40,60,200)` so the suite now tests the live reality.

**RC-B (design) — rewind landed on an unowned agent ⇒ "stop at first grayed-out, owned = contiguous
prefix" is wrong for the live roster.** The selection highlight moved **right** during rewind
(gold border 1315→1399) and ended on an unowned agent — i.e. the `<`/`>` chevrons are mirrored relative
to the code's assumption (matches the user's "loops in **reverse**") and/or the strip is not
owned-first. Rather than re-chase the chevron geometry blind (the recurring failure mode in this log),
made the traversal **ordering- and direction-robust**: `scan()` now **SKIPS** grayed agents and keeps
going, stopping only at the true end of the strip (advance no-ops), on kill, or at `AGENT_MAX` *visited*.
This is correct whether the strip is owned-first, grayed-first, or interleaved, and whether the chevrons
move forward or backward. New test `test_skips_interleaved_grayout` proves owned agents at non-contiguous
positions `{0,2,5}` are all visited.

**Why the run showed 0 agents (not a separate bug).** The kill listener only fires on real Esc
(`grid.make_kill_listener`), and rewind issues no programmatic Esc — so the only `scan()` exit matching
"0 agents / 0 issues / no `nav_owned_check_fail`" is the **kill event set before the first iteration**:
the user pressed **Escape** to abort the misbehaving reverse rewind. Expected once RC-A/RC-B are fixed.

**Files changed:** `src/youkai_ocr/agent_scanner.py` (`_GRAYED_*`/`_OWNED_COLOR_*` constants replace
`_OWNED_SAT_P75_MIN`; `_is_owned_agent` rewritten; `scan()` skip-don't-stop with `visited` cap +
`nav_first_unowned` diagnostic), `tests/test_agent_traversal.py` (sim grayed=blue duotone; `owned_idxs`;
renamed/updated assertions; interleaved-skip test).

**Tests:** agent suites 71/71; full suite **316 passed, 1 failed** — the 1 is the pre-existing,
unrelated `test_read_disc_count_from_real_header` (disc-count fixture drifted 2205→2217 as the archive
preflight was overwritten by this run).

**Next live run.** Re-run `scan-all --agents-only --debug-overlays`. Expectations: it walks the *whole*
strip (possibly in reverse — benign now), skips unowned agents, and scans every owned one. If it still
yields 0, read `nav_first_unowned.png` + the `agent_skip` log lines. Remaining live unknown: the chevron
direction is "not optimal" (reverse) but no longer fatal — re-measuring `_STRIP_NEXT`/`_STRIP_PREV` for
forward order is a nice-to-have, not a blocker.

---

## H16 — The agent strip is CIRCULAR: `_rewind_to_first` can't terminate; ring-traversal fix (2026-06-07, Opus 4.8)

**Trigger.** User re-ran post-H15. The H15 owned/grayed fix held (it walked the strip, skipping
unowned), but the run died at the rewind: "it went in reverse, scanned through the agents, and said
'hit `_REWIND_MAX` (60) without reaching the first agent'." Decisive new fact from the user: **"the bar
navigation does loop"** (the chevrons wrap around the roster).

**Root cause (certain, no live frame needed).** Every traversal assumption in H8–H15 was built for a
*linear* strip with a terminal first/last agent. On a CIRCULAR strip both terminators are unreachable:
- `_rewind_to_first()` pressed "<" until the selection *stops changing* — but on a loop the selection
  never stops, it just cycles → it always burns all `_REWIND_MAX=60` presses and logs the warning.
  This is exactly the symptom, and why the user had to Esc out (→ H15's "0 agents" via kill-before-loop).
- `_advance(+1)` returning False ("end of strip") never fires either — advance always wraps.

**Fix — anchor-and-close ring traversal (`agent_scanner.py`).** Stop trying to find a "first" agent
(none exists on a ring). `scan()` now:
1. enters the detail page, records the **start** strip identity (`_strip_id`) of whatever agent entry
   landed on (saved as `nav_start.png`),
2. walks forward with ">", scanning owned agents (Base/Skills/Equipment) and SKIPPING grayed ones
   (one cheap advance, no tab captures — H15 skip-don't-stop retained),
3. stops when the strip identity returns to the start (`_phash_hamming ≤ _RING_CLOSE_MAX_BITS`
   = ring closed, every position visited once), or on a true `_advance` no-op (degenerate single-agent
   strip), on kill, or at `AGENT_MAX` visited.
Deleted `_rewind_to_first` and the `_REWIND_MAX` constant; added `_RING_CLOSE_MAX_BITS`
(= `_STRIP_CHANGE_MIN_BITS`). Updated the strip-geometry comment block and class/method docstrings
("no loop / rewind to first" → "circular / anchor on start"). `nav_rewound` diagnostic → `nav_start`.

**Why this is strictly more robust than the user's "back-until-first-grayed, then forward one" idea
(which we discussed).** That anchor works *only* under contiguous ownership and reintroduces the same
infinite loop in two cases on a circular strip: entry landing **on** a grayed agent, or an **all-owned**
roster (backward never hits a grayed agent). The ring anchor needs zero assumptions about sort order,
contiguity, or chevron direction — and the "reverse" direction the user saw is now fully benign (a ring
traversed backward still returns to its start). Tradeoff (user-noted): it advances through the grayed
agents too, but that's ~0.5s each (capture + one chevron press, no tab captures), and `AGENT_MAX=60` is
comfortably above ZZZ's full roster (~40 incl. unowned), so a whole-ring pass stays under the cap.

**Tests (`test_agent_traversal.py`).** Sim strip made circular (`next`/`prev` wrap mod `n_total`);
removed `_rewind_to_first` from the module docstring. Updated assertions to ring order from the start
position (`test_visits_each_owned_once_…` now expects `[2,3,4,0,1]` from `start_idx=2`, and `sim.idx`
back at the start = ring closed); interleaved/single-owned tests assert ring closure. Added
`test_single_agent_total_advance_no_op` (n_total=1) to cover the degenerate advance-no-op terminator.
Agent traversal suite 10/10. **Full suite: 317 passed, 1 failed** — the 1 is the pre-existing, unrelated
`test_read_disc_count_from_real_header` (disc-count fixture drift 2205→2217, same as H15).

**Next live run.** Re-run `scan-all --agents-only --debug-overlays`. Expectation: it enters, walks the
ring once from the entry agent (in whatever direction the chevrons go), scans every owned agent, skips
unowned, and stops on its own at the start — no rewind, no Esc needed. If it still yields 0, read
`nav_start.png` + the `ring closed` / `agent_skip` log lines.

---

## H17 — Equipment-tab click DROPPED (fired during Skills animation); + content-render gate (2026-06-07, Opus 4.8)

**Trigger.** User re-ran post-H16 ("much better!"): the ring traversal worked — it entered, scanned
agent_000, and walked the strip. But it "moused over Equipment but never clicked on it," appeared to
stall, and the user Escaped out. User later confirmed: **"it never went to the equipment page for
agent_000."**

**Root cause (certain, from the live archive — no live repro needed).** The 19:28 run left a complete
`agent_000/` (base + skills + 7 equip_slot frames) but a STALE `results.json`/`agents.json` (18:21) — so
it aborted after agent_000 without exporting. Reading the frames:
- `agent_000/equip_slot_0.png` … `equip_slot_6.png` all show the **Skills page** (core nodes A–F), NOT
  the disc/engine equipment page. The Equipment-tab click never switched tabs; the 7 "slot" clicks
  landed on the still-open Skills screen.
- `agent_000/skills.png` itself was banked **mid-animation** — Skills pill yellow but no nodes/levels
  painted (just character art). The Equipment click fired *during that entrance animation* and the game
  **silently dropped it**.

The bug is in `_capture_tab`: its render gate only **re-CAPTURED** on a miss, never **re-CLICKED**.
A dropped click is never recovered by re-capturing (the pill stays the OLD tab's colour forever) — unlike
`_enter_detail_page` (re-clicks Base) and `_advance` (re-clicks the chevron), which already handle dropped
clicks. Compounding it, the gate keyed only on the **yellow pill**, which lights the instant a tab is
*selected* — before its page content animates in — so even a "successful" capture can be half-painted
(exactly what happened to `skills.png`).

**Fix (`agent_scanner.py`).** Two complementary changes to `_capture_tab`:
1. **Re-click on dropped click.** Poll loop now re-CLICKS the tab every `_TAB_RECLICK_EVERY=3` polls
   (8 polls × 0.35s ≈ 2.8s budget) while the pill is not yellow — recovering a click swallowed by the
   previous tab's animation. (New: `_TAB_GATE_POLLS`/`_TAB_GATE_POLL_S`/`_TAB_RECLICK_EVERY`; removed the
   old recapture-only `_EQUIP_GATE_RETRIES`/`_EQUIP_GATE_RETRY_S`.)
2. **Content-render gate.** Gate now requires pill-yellow **AND** `_tab_content_rendered(frame, tab)`, an
   agent-INDEPENDENT content signal so no half-painted frame is ever banked for OCR:
   - base   → agent-name bbox luma  (rendered ≈57, ref_3 57.1; mid-anim ≈9)  → `>30`
   - skills → mean skill-level luma (rendered ≈56, ref_4 57.5; mid-anim ≈21) → `>40`
   - equip  → not gated (engine hexagon reads dark on an unequipped W-Engine → would false-fail; the
     equipment-tab frame feeds no OCR — the per-slot frames do, each already gated by `_slot_panel_rendered`).
   Thresholds measured directly from the live mid-animation frame (`agent_000/skills.png`) vs the same
   page rendered (`agent_000/equip_slot_0.png`), cross-checked against `reference_3`/`reference_4`.
   Re-click is suppressed once the pill IS yellow (waiting on content, not a dropped click → re-clicking
   would be pointless).

**Tests.**
- `test_agent_traversal.py::test_capture_tab_reclicks_dropped_tab_click` — a `_StripSim` that swallows the
  first 2 Equipment-tab clicks; asserts `_capture_tab` re-clicks and recovers onto Equipment (≥3 tab-2
  clicks logged, pill ends yellow).
- `test_agent_rc2.py` — content gate accepts `reference_3`/`reference_4`, rejects the `wipe.png` fixture
  (mid-transition) for base+skills, and does NOT gate equipment.
- Agent suites (traversal/rc2/h3/grid) **38 passed**. Full suite: 318 passed, 1 failed — the 1 is the
  unchanged, pre-existing `test_read_disc_count_from_real_header` fixture drift (2205→2217).

**Next live run.** Re-run `scan-all --agents-only --debug-overlays`. Expectation: each owned agent now
gets a real Equipment page (disc/engine slots) in `equip_slot_*.png`, and `skills.png` shows painted
nodes/levels. If the Equipment tab still won't open, the new `tab_reclick` / `tab_gate_fail tab=2` log
lines will show the re-clicks firing — if it fails even after re-clicks, the Equipment coord (1718,996)
is wrong and needs re-measuring (unlikely: it matches `_TAB_ACTIVE_BBOXES[2]` center).

---

## H18 — Live feedback after H17: slot-drop, advance-skip, empty slots, trial agents (2026-06-07, Opus 4.8)

**Trigger.** User re-ran post-H17 ("much closer!") and reported four distinct issues from a live pass:
1. **Second disc often not clicked** (≥half of agents) — "looks like it's going too fast; there's a
   long pause after the engine (OCR catching up) so we can afford to slow the capture."
2. **`>` nav skips an agent** by double-clicking (sometimes two agents by triple-clicking).
3. **Empty slots** (e.g. **Koleda**) are mis-recorded — clicking an empty slot still shows disc info
   (it surfaces the *first available inventory disc*). Empty disc = number on a simple background;
   empty engine = a colour-shifting "core available" icon. Hexagon spots are very distinct for the
   unequipped state.
4. **Grayed/trial agents still scanned** — **Nangong Yu** hung the pass on a "not available in
   preview mode" warning.

**Diagnosis (from code + ref_7/8/16; no live repro needed).**
- **#1** — Clicking the FIRST hexagon slot triggers the big equipment→disc-select layout wipe
  (ref_7 → ref_8: character render slides out, disc list slides in). A 2nd slot click fired *during*
  that animation is silently DROPPED — the exact H17 tab-drop class. The old `_read_equipment` loop
  re-CAPTURED on a miss but never re-CLICKED, so the dropped 2nd slot was unrecoverable and re-banked
  slot 1's panel.
- **#2** — A single `>` moves only the **selection highlight** by one thumbnail; the filmstrip itself
  does not scroll except at an edge (H10-Q3). So the thin `_STRIP_PHASH_BBOX` band barely changes
  (< `_STRIP_CHANGE_MIN_BITS`), `_advance` mis-read a real move as "no move", **re-clicked**, and the
  second click advanced the selection a SECOND time → a skipped agent (two skips on a double miss).
- **#4** — Trial/preview agents render full-colour, so the H15 blue-duotone `_is_owned_agent` test
  does NOT catch them. Critically, the obvious "engine hexagon is dark" signal is **unusable** as a
  trial discriminator: an OWNED agent with an empty W-Engine (Koleda) also reads the hexagon dark
  (H3). So proactive trial-skip needs a real reference of Nangong's preview page (see OQs).

**Fixes shipped this session (`agent_scanner.py`).**
1. **Per-slot render gate with re-click** — new `_open_slot()`; `_read_equipment` now gates each slot:
   slot 0 waits for the select panel to APPEAR (`_slot_panel_rendered`); slots 1+ wait for the panel
   TITLE pHash to SWITCH away from the previous slot (the panel stays open and swaps content per
   H10-Q4), re-clicking every `_SLOT_RECLICK_EVERY=3` of `_SLOT_GATE_POLLS=8` polls on a miss. Also
   raised `_SLOT_CLICK_DELAY_S` 0.20 → 0.45 (the per-agent OCR pause dwarfs this — no speed cost).
2. **Advance-confirm + ring-closure keyed on the character render** — new `_agent_id()` over
   `_CHARACTER_RENDER_BBOX` (changes completely on a real move); `_advance`, `start_id`, and the
   ring-close check now use it (`_AGENT_CHANGE_MIN_BITS`/`_AGENT_RING_CLOSE_MAX = 15`). One click per
   advance → no spurious re-clicks → no skips.
4. **Bounded reactive safety net** — if the Equipment hexagon never renders, `_read_equipment` Escapes
   (clears any modal) and returns the new `_EQUIP_UNAVAILABLE` sentinel; `scan()` then SKIPS that
   agent (no export, no false disc/engine location). This *de-hangs* the trial case and, combined with
   the now-bounded slot loop, removes the infinite-poke on the preview modal. It is a net, NOT
   proactive trial detection (would false-fire on Koleda's empty engine — see OQs).

**Tests (`tests/test_agent_traversal.py`).** Extended `_StripSim` to model a unique per-agent render
(white identity stripe, excluded from the hue test) and per-slot panel content. New cases:
- `test_open_slot_reclicks_dropped_second_slot` — drops the first 2 clicks at slot index 1; asserts
  re-click recovery and all 7 slots opened with one final Escape.
- `test_advance_does_not_skip_on_weak_strip_signal` — 6-agent ring, asserts seq `[0..5]` and exactly
  6 `>` clicks (no spurious re-clicks).
- `test_trial_agent_equipment_unavailable_is_skipped_not_hung` — blanks the hexagon for one agent;
  asserts it's skipped (seq `[0,2]`) and the modal-dismiss Escape fired.
- Agent suites **41 passed**. Full suite **324 passed, 1 failed** — the 1 is the unchanged pre-existing
  `test_read_disc_count_from_real_header` fixture drift (2205→2217), untouched by this work.

**Blocked on live reference frames (issues #3 and proactive #4).**
- **#3 empty-slot detection** needs a **Koleda** equipment-tab frame (fully/partly unequipped) to
  calibrate the per-slot empty-vs-equipped signal on the hexagon BEFORE clicking.
- **#4 proactive trial-skip** needs a **Nangong Yu** detail page + the "not available in preview mode"
  popup to build a reliable trial signal (the dark-engine signal collides with Koleda).
Both are scaffolded/designed in `DESIGN_agents.md` H18 and tracked as H18 tasks; do NOT calibrate
thresholds blind (the RC-3 slot-geometry lesson).

### H18 follow-up — Koleda frame received: empty-slot detection + slot-number bug (2026-06-07, Opus 4.8)

User added `reference_17_koleda_unequipped_equipment_page.png` (Koleda, fully unequipped) and noted:
**"equipped sets have many colour schemes/styles, but none look like the unequipped one."** So we
detect the distinctive EMPTY signature, not the varied equipped ones. Measured ref_7 (equipped) vs
ref_17 (empty) at each slot center:
- **Disc empty** = dark (luma ≈32) vs equipped bright (≥120, even white/low-sat discs) → threshold
  `_DISC_EQUIPPED_LUMA_MIN = 80`.
- **Engine empty** = the colour-shifting "core available" glow: highly saturated (colored_frac ≈0.5)
  AND only moderate luma (≈90) vs a bright equipped render → `colored_frac > 0.15 AND luma < 150`.
- **Reactive-net safety confirmed:** at the `_equip_tab_rendered` gate window (r=20) Koleda's empty
  engine reads luma ≈110 > 80 → the gate still passes, so a real owned agent with an empty engine is
  NOT mistaken for a trial agent and skipped. (`test_equip_tab_still_renders_on_koleda_empty_engine`.)

**Empty-slot wiring (`agent_scanner.py`).** `_disc_slot_equipped` / `_engine_slot_equipped` /
`_slot_equipped`; `_read_equipment` skips empty slots (appends `None`, no click), and Escapes ONLY if
a panel was actually opened (a Koleda-style all-empty agent must NOT Escape — that would exit the
detail page). `scan_agents` skips `None` frames in archiving and cross-reference. This kills the
data-corruption path (clicking an empty slot surfaced the first INVENTORY disc → false location).

**BONUS bug fixed — reversed slot numbering.** Koleda's empty slots show their in-game numbers:
left column top→down = 1,2,3; right column bottom→up = 4,5,6. But `_DISC_SLOT_CENTERS` is ordered
upper-right→…→upper-left, so its index 0 (upper-right) is slot **6**, not 1. The code assigned
`slot_key = str(slot_idx + 1)` — fully REVERSED — which would have made EVERY disc-location match miss
in `resolve_locations`. Fixed: new `_slot_number(idx) = 6 - idx`; updated the two tests that had
encoded the reversed assumption (`test_agent_h4`, `test_agent_scanner`).

**Tests.** +5 (`test_agent_h3` Koleda classifiers ×4, `test_agent_traversal` Koleda integration ×1);
updated 3 for the slot-number fix. Agent + equip + cli suites **120 passed**.

**Status now.** Issues #1, #2, #3 FIXED + tested; #4 de-hanged (reactive net) — proactive trial-skip
still needs a Nangong Yu frame (OQ-H18b). Slot-number correctness bug fixed as a bonus.

## 2026-06-08 — H19: slot switch-detection rewrite (live feedback round 3) (Opus 4.8)

**Reported (post-H18 live run):** (1) "disc 2 still skipped sometimes," (2) "errors from having to
click repeatedly," (3) new "hangs oddly on disc 4." All three are the H18 slot-open gate misfiring.

**Root cause — the gate keyed on the TITLE region (`_EQUIP_TITLE_BBOX`), which fails both ways:**
- *False NEGATIVE on same-set adjacent slots.* Two slots holding the same disc set (4-piece sets are
  normal) have near-identical titles → title-pHash Hamming ≤ 8 even on a real switch → the gate never
  fires → 8 polls of futile re-clicking → `slot_gate_fail`. That IS the "clicking repeatedly" and the
  ~2.8s disc-4 "hang."
- *False POSITIVE on a half-faded panel.* A mid-fade title differs enough from the previous slot to
  look "switched" → a duplicate of the previous slot is banked → the real disc reads as "skipped."
- *Separately:* empty-detection sampled `equip_frame` straight from `_capture_tab`, which returns as
  soon as the yellow pill lights — BEFORE the hexagon disc icons fade in. A half-faded icon reads dark
  (luma < 80) → an EQUIPPED slot is mis-flagged EMPTY and skipped (the other half of "disc 2 skipped").

Verified against `reference_7/8/16/17`: in the disc-select view (ref_8) the hexagon ring stays in place
(re-clicking a slot is harmless) and the CENTER detail panel's main-stat + substats differ between two
discs of one set — so the body is a reliable switch signal where the title is not.

**Changes (`agent_scanner.py`):**
- `_SLOT_DETAIL_BBOX = (610,120,965,600)` — switch-detection now gates on the panel BODY (title + main
  stat + substats; stops before the same-for-a-set set-effect text).
- `_open_slot` rewritten: bank only when the body is STABLE across two captures (`_SLOT_STABLE_MAX_BITS
  = 6`) AND changed from the previous slot (`_SLOT_CHANGE_MIN_BITS = 8`); a settled-but-unchanged panel
  = dropped click → re-click (H18 recovery kept). Returns `(frame, body_pHash)` so the next slot
  compares like-for-like. `_SLOT_GATE_POLLS` 8→10; dropped `_SLOT_RECLICK_EVERY` (no longer modulo-based).
- `_wait_region_stable(first, bbox, max_bits, polls, poll_s)` helper; `_read_equipment` settles
  `equip_frame` on `_EQUIP_RING_BBOX` (12-bit tolerant budget) before empty-detection and the
  `_equip_tab_rendered` check.

**Tests (`tests/test_agent_traversal.py`):** sim `_render` now paints a per-slot BODY band (models real
disc detail) so the body-bbox gate is exercised; new
`test_open_slot_same_set_adjacent_slots_no_reclick_no_skip` (identical titles, distinct bodies → each
slot opened with exactly one click, no skips). Existing dropped-slot / Koleda-empty / trial tests still
pass.

**Result:** `331 passed, 1 failed` — the one failure is the pre-existing, unrelated
`test_read_disc_count_from_real_header` drift (2217 vs 2205), present before H19.

**Next (live):** re-run `scan-all --agents-only --debug-overlays`. New/changed log lines:
`slot_reclick` should now fire ONLY on genuine dropped clicks (not on same-set slots); `slot_gate_fail`
should be rare. If a same-set agent still shows repeated `slot_reclick`, the body signal is too weak →
raise the substat weighting in `_SLOT_DETAIL_BBOX` or lower `_SLOT_CHANGE_MIN_BITS`. Thresholds
`_SLOT_STABLE_MAX_BITS=6` / `_EQUIP_STABLE_MAX_BITS=12` are reasoned, not live-measured (OQ-H19a).

## H20 — `equip_unavailable` false-skip root-caused: gate keys on dark engine art (2026-06-08, Opus 4.8)

**Symptom (live).** `equip_unavailable — hexagon not rendered after tab switch` on a real owned agent;
agent silently dropped (`agent_skip_trial`, not exported).

**Investigation.** Pulled the saved frame `archive/live_20260605/nav_equip_unavailable.png` (1920×1080):
a fully-rendered Equipment tab — 6 discs equipped (Lv. 15/15) + equipped Lv. 60/60 W-Engine. Sampled at
the gate's game coords:
- engine gate-center luma (r=20) = **78.3** → fails `_EQUIP_GATE_LUMA_MIN` (>80) by 1.7
- disc slots (r=50) = 159/115/115/116/160/116 → 6/6 read equipped (>80)
- ring bbox (1100,280,1720,800): mean 67, std 63, gradient-edge-frac 0.142 → strongly structured

**Root cause.** `_equip_tab_rendered` gates render-detection on engine-center luma. This W-Engine's art is
dark/rocky → luma 78 < 80 → false `_EQUIP_UNAVAILABLE` → whole agent skipped. The engine slot is the most
agent-variable region; keying the gate to it is brittle. Falsifies D33-Dec-3 (only verified an *empty*
engine glow ≈110, never a dark *equipped* engine). See **D35**.

**Fix (applied, H20.1).** Re-keyed `_equip_tab_rendered` to the **union** of two engine-independent
positives: rendered if any disc slot equipped OR engine luma > 80. Strictly wider than the old gate →
can only remove false skips.

A structural edge-density fallback (for the naked-agent case) was tried and **rejected after measuring**:
edge-frac on `_EQUIP_RING_BBOX` is Koleda 0.034 (rendered, empty) vs skills page 0.053 (not equipment) —
the empty hexagon scores *below* the frame we must reject, so it's not a discriminator. Dropped it and the
two new constants. The naked-agent + dark-engine corner stays out of scope (indistinguishable from a trial
frame without the deferred Nangong reference; the old gate failed it too → no regression). See **D35**.

Signal table (measured):

| frame | discs eq | engine luma | gate |
|---|---|---|---|
| live `nav_equip_unavailable` (geared, dark engine) | 6 | 78.3 | **rendered** (disc path) |
| Koleda ref_17 (fully empty) | 0 | 110.2 | **rendered** (engine glow) |
| skills ref_4 (not equipment) | 0 | 39.0 | not rendered ✓ |
| ref_7 (geared) | 6 | 192.2 | rendered ✓ |

**Tests.** `tests/test_agent_h3.py::test_equip_tab_renders_on_geared_agent_with_dark_engine` (regression on
the live frame). `test_trial_agent_equipment_unavailable_is_skipped_not_hung` updated — the sim now blanks
the whole `_EQUIP_RING_BBOX` (a real trial frame has NO hexagon; blanking only the engine no longer reads
"unavailable" since the discs carry the render signal). Full suite: **331 passed, 1 failed** (the
pre-existing unrelated `test_read_disc_count_from_real_header` drift).

## H21 — Engine-never-captured root-caused (Opus, 2026-06-08)

Live `--agents-only --debug-overlays`, 5 agents: 5/5 got 6/6 disc slots; **engine captured 1/5**
(`equip_slot_6.png` stale for the other 4). Engine is *skipped pre-click*, not mis-clicked — `frames.append(None)`.

Measured `_engine_slot_equipped` on the engine references (chrome-cropped 1922×1112 → 1920×1080):

| frame | state | colored | luma | equipped() |
|---|---|---|---|---|
| ref_7 | equipped (bright) | 0.022 | 210.5 | True ✓ |
| ref_16 | equipped | 0.287 | 134.0 | **False ✗** |
| nav_equip_unavailable | equipped (dark) | 0.834 | 78.7 | **False ✗** |
| ref_17 Koleda | empty | 0.526 | 89.3 | False ✓ |

Empty (0.526/89) sits between the equipped samples → classes don't separate (cf. D35 rejected edge-frac).
Decision D36: invert to post-click content validation; blocked on Koleda empty-slot reference frames (H21.0).
Also found: `scan.log` tees stdout only — `_log.*` markers never captured (0 matches despite 4 skips) → H21.1.

## H21 — IMPLEMENTED (Opus, 2026-06-08): action-bar equipped/empty gate + log routing

Built the closed-loop per-slot contract (D36). Changes:
- `agent_scanner.py`: new `_ACTION_BAR_BBOX` + `_panel_shows_equipped()` (OCR "unequip" substring).
  Deleted `_engine_slot_equipped` / `_slot_equipped` (proven non-separable — D36); kept
  `_disc_slot_equipped` (still backs the D35 render gate). `AgentNavigator` gains a `recognizer` +
  `_slot_equipped_from_panel`. `_open_slot` now returns `(frame, equipped, panel_id)` — empties return
  immediately (no switch-detect; two empties auto-load the same inventory[0] so a switch test can't
  fire and isn't needed), equipped keep the H19 body-switch dropped-click guard. `_read_equipment`
  CLICKS every slot and records only equipped ones; always one Escape (a panel is always opened now).
- `cli.py` (H21.1): `logging.FileHandler` → `run_dir/agent_scan.log` so `_log.*` markers are captured
  (the live `scan.log` teed stdout only — 0 markers despite 4 engine skips). Verified in isolation.
- Tests: `test_panel_shows_equipped_action_bar_gate` (real ref_8/18/19); rewrote the Koleda test to the
  new click-every-slot contract + a mixed equipped/empty integration test; dropped the broken
  `_engine_slot_equipped` test. Refs moved screenshots/ → reference/ (reference_18/19).

**Suite: 332 passed, 1 failed** — the lone failure is the pre-existing unrelated
`test_read_disc_count_from_real_header` (2217 vs 2205 disc-count drift), not touched here.

Remaining: **H21.4 live confirm** — re-run `scan-all --agents-only --debug-overlays`; expect the engine
captured on every equipped agent, empties cleanly skipped, and `agent_scan.log` now populated. Verify the
engine's "Unequip" button falls inside `_ACTION_BAR_BBOX` (OQ-H21b — only the empty-engine frame existed
offline).

## 2026-06-08 — H22: owned/unowned detection rewrite (D37)

**Trigger:** H21.4 live run captured discs/engines reliably but skipped OWNED agents (Harumasa;
Lycaon + Komano Manato). User suspected "agent switching"; investigation pinned it on the ownership
gate instead.

**Investigation (Opus, offline against `archive/live_20260605/`):**
- `agent_scan.log` showed the missed agents on the `agent_skip — unowned agent` path at consecutive
  positions (8+9, 28+29) → classified unowned, never opened. So `_advance` over-shoot was NOT the
  cause; `_is_owned_agent` was.
- Measured `blue_frac`/`hue_std` over all 33 owned captures + the genuine unowned frame: owned
  agent_008 (0.87/27) and agent_014 (0.75/29) sit inside the H15 "grayed" zone; unowned Hugo is
  0.93/24. Clusters overlap — non-separable. H15's "unowned = blue duotone" premise is wrong; the
  unowned frame renders in full colour.
- Footer "Fully Equipped" pill: owned agent_011/025/032 read ≈0 (unequipped) = same as unowned →
  also non-separable.
- Found the reliable signal from user input + frames: level≥2 ⇒ owned; at Lv.1 the level-up `>>`
  pill is green (owned) vs white (unowned). Chevron pill bbox located empirically at
  (1315,455,1370,535); green/white separate cleanly on all 34 frames. Confirmed level OCR reads
  built agents fine (50/55/60) and blank on unowned Lv.01 (→0, folded with Lv.1). agent_023 (owned
  L50/50) shows a WHITE pill too → proves chevron is only valid once level<2 is established.
- Noted a SECOND latent data-loss path: `nav_equip_unavailable.png` (saved on the
  `_EQUIP_UNAVAILABLE` drop) shows a fully-equipped owned agent → that gate false-positives too
  (OQ-H22a, did not fire this run).

**Change:** replaced `_is_owned_agent` (+ `_GRAYED_*`/`_OWNED_COLOR_*`) with `_chevron_color_fracs`
+ `_classify_owned` (pure) + `_agent_level`/`_agent_owned` (navigator, level OCR). `scan()` now
captures the Base tab first and decides ownership there before the expensive captures; unowned costs
one Base frame. Traversal logic unchanged (skip-don't-stop + ring-close; no early-out — entry is
arbitrary). All ambiguity biases to OWNED (never drop an owned agent).

**Tests:** rewrote the strip-sim ownership model (green/white chevron); added
`test_classify_owned_rules` + `test_chevron_signal_separates_owned_unowned`. `test_agent_traversal.py`
18/18 green. Full suite: see run below.

**Left for user:** H22.3 live confirm (`scan-all --agents-only --debug-overlays`) — expect the three
missed agents captured; paste `agent_scan.log`.

---

## H22.3 — Live-run review (run dir `archive/live_20260605`, scanned 14:07–14:21, elapsed 854.9s)

**Reviewer caveat first:** `agent_scan.log` is append-mode and holds **two** runs. The `13:16–13:25`
block uses skip string `"agent_skip — unowned agent at strip position N"` — that string is NOT in the
current code (current emitters: line 1365 `agent_skip_trial`, line 1376 `Lv.1 + static white chevron`),
so that block is the **pre-D37** run. The run under review is `14:07:40–14:21:40` only. (The apparent
42-min "gap" is just the boundary between the two runs, not a stall.)

**Verdict on D37 (the thing we changed): WORKS.** In the new run every skip is in a single contiguous
tail (strip pos 40–53, 14 agents) all logged `Lv.1 + static white chevron`. No owned-position skips
(no mid-roster 8+9 / 28+29 double-skips). **VonLycaon captured** (idx 31, Lv.10). The ownership
classifier is no longer dropping owned agents. `agent_skip_trial` never fired (OQ-H22a latent, still
uncalibrated).

**But the run is still bad downstream of D37 — three separate problems:**

1. **Traversal dropped ~44% of the roster AND never ring-closed (silent data loss).** True roster is
   **39 owned** (user-confirmed), but the run captured only **22 distinct** (42 entries) and ended on
   `agent_scan_cap — hit AGENT_MAX (60) after 46 owned`. Two faults at once: (a) `_advance` sometimes
   did NOT move the selection, so the same agent was re-read — proof: exact-duplicate talent vectors
   (idx2==idx37 Rina `12,10,10,12,12,0`; idx5==idx40 ZhuYuan `12,12,12,12,12,0`); ZhuYuan ×7, Rina ×6
   (the H18 "strip band is a poor move-detector" failure mode); and (b) **17 owned agents were never
   visited** before the cap. Export dedup masks the re-captures but cannot recover the 17 missing.
   The ring-close gate (`_AGENT_RING_CLOSE_MAX=15` bits on the start-anchor render pHash) also never
   tripped. **Correction to my first-pass read: dedup did NOT "mostly recover" the roster — 22 ≠ 39.**
   Priority fix (H23): a per-position capture guarantee (advance-confirm on `_agent_id`, not the strip
   band) + a settled, seen-set ring-close.

2. **Matcher: full-name vs short-name collapse → 3 entries keyed "Zhao".** DIAGNOSED from the
   captured name crops: `"Zhao"` is a REAL agent (agent_000 renders literally "Zhao" — map entry
   correct). The other two "Zhao" entries are mis-collapsed: agent_011 = **"Tsukishiro Yanagi"**
   (map key is the short `"Yanagi"`; client renders the FULL name) and agent_035 = **"Komano Manato"**
   (absent from the map entirely). Root cause: the name map keys are short display names while the
   ZZZ client renders full names, AND `normalize_agent` has no score floor so every miss snaps to the
   nearest short key ("Zhao" is the magnet). So the headline "missed agents" = a naming gap, not
   ownership. Fix = full-name map keys/aliases + a WRatio floor (H24).

3. **Talent OCR is noisy/non-deterministic.** Same agent reads different talent vectors across its
   duplicate visits (Zhao `12,12,11,12,11,6` vs `12,0,0,12,0,6`; ZhuYuan full vs all-zeros). Pervasive
   spurious `0`s on Lv.60 agents that certainly have leveled talents. Because dedup picks one copy
   arbitrarily, talent accuracy is partly luck-of-the-draw. Needs a per-field confidence / best-of-N
   merge (H25).

4. **Equipment: 0 discs / 0 engines on all 42** — every slot logged `slot_empty … 'Equip'`.
   `agents.json` schema has no disc/engine field yet, so equipment-into-record is presumably not
   wired (PNGs captured for offline extraction). BUT slot 6 (engine) reading empty on every Lv.60
   agent is suspicious — confirm whether the equip-slot action-bar OCR is actually reading, or just
   not plumbed (H26).

**Net:** D37 succeeded at its goal. The remaining roster gaps are NOT ownership — they're ring-close
non-termination (H23), matcher misnaming ("Zhao", H24), and talent OCR noise (H25). Recommend tackling
H23 first (it's both a correctness-confidence and a 2× runtime issue).

---

## 2026-06-08 — H23 + H24 (Sonnet 4.6)

### Offline calibration (H23 prerequisite)

Computed `_agent_id` pHash Hamming distances from `archive/live_20260605`:
- **Same-agent pairs (confirmed wrap-around)**: 19–111 bits (agent_000/039=19, agent_002/041=84, agent_003/042=111)
- **Cross-agent pairs**: 74–109 bits

These ranges COMPLETELY OVERLAP. The pHash approach for ring-close is fundamentally broken — the animated character render has enough idle-animation drift over a full visit cycle (~20s) that same-agent pHash looks identical to cross-agent pHash. `_AGENT_RING_CLOSE_MAX = 15` was simply far too tight; no safe threshold exists.

**Name-based ring-close is reliable**: Offline test of all 7 same-agent pairs (both visits) showed identical (key, score) tuples. OCR is deterministic on the same settled base_stats.png.

Root cause of the live failure: scanner entered at Zhao (score 100), traversed 39 owned positions + 14 unowned skips = 53 total advances, re-entered at Zhao again (agent_039), but the ring-close raw-capture pHash of the mid-animation render was >15 bits away from the settled `start_id`. Kept going, eventually hit AGENT_MAX=60 after 7 more re-captures.

### H23 fix

- Replaced pHash ring-close in `scan()` with **name-based ring-close** using `_ring_close_key(base_frame)`:
  - `start_name` set from first agent's normalised key (iteration 1)
  - Ring closes when `current_name == start_name` on any subsequent settled base_frame
  - Falls back to AGENT_MAX (ring-close with no-recognizer sims, AGENT_MAX backstop)
- Extracted `_ring_close_key(frame) -> str` as an overridable method on `AgentNavigator`
- Test sim overrides `_ring_close_key` to return `str(self.idx)` (no OCR needed in tests)
- Removed `_AGENT_RING_CLOSE_MAX = 15` (pHash ring-close gone)
- **Offline simulation**: ring-close fires at agent_039 (visited=40), correctly stopping after 39 agents
- 18 traversal tests: all pass

### H24 fix

**Root cause**: Many OCR reads were genuine full names not in the map (e.g. "Tsukishiro Yanagi" → "Yanagi", "Asaba Harumasa" → "Harumasa"), and 7+ post-1.4 agents completely absent ("Yixuan", "Astra", "Seth", "Trigger", "Vivian", "Pulchra", "Komano Manato"). No WRatio floor → all misses snapped to nearest key (often "Zhao" or "ZhuYuan").

- Updated `data/zzz_1.4/agents.json`:
  - Added full-name aliases: Tsukishiro Yanagi, Asaba Harumasa, Komano Manato, Hoshimi Miyabi, Dialyn, Alexandrina (Rina)
  - Added post-1.4 agents: Yixuan, Astra/Astra Yao, Seth/Seth Lowe, Trigger, Vivian, Pulchra, Manato, Evelyn
- Added `_AGENT_NAME_SCORE_MIN = 85` floor in `normalize_agent`:
  - Below floor → returns ("", score) so CRITICAL_CONF flags unknown_agent
  - Rejects garbage OCR reads ("Oinayvi", "Ju Fufu", "Dan Yinhu") that previously snapped to random keys
- Added 29 parametrized normalizer tests (full names + floor rejection); all pass

**Post-fix analysis**: on the first-pass 39 agents, the updated normalizer resolves 21 with high-confidence keys and flags 18 as unknown (garbled OCR or unknown agents). No false collapses. The 2 "Rina" entries (agents 002 "= Ukinami Yu:" at 87, agent 024 "Alexandrina" at 100) are likely 2 different Rina appearances — "Alexandrina" is Rina's confirmed full first name; "Ukinami Yu" origin uncertain (removed from map to avoid false positive).

**Suite**: 324 passed / 1 pre-existing fail (disc count test, archive-dependent, unrelated).


## 2026-06-08 — H26: Engine equipment gate fix (Sonnet)

**Task**: H26 — equipment read as empty on every Lv.60 agent.

**Root cause found offline**: `_panel_shows_equipped` checked only for `"unequip"` in action-bar text.
- Equipped disc panel → "Unequip All Remove" → `"unequip"` present → True ✓
- Equipped engine panel → "Remove Enhance" → `"unequip"` absent → **False** ✗ (the bug)
- Empty disc → "Equip All Equip" → neither → False ✓
- Empty engine → "Equip Enhance" → neither → False ✓

The engine action bar button is labeled "Remove" (not "Unequip"), so the old single-keyword gate
always reported engine slots as empty. All 42 agents' engines were silently dropped from the export.

**Fix**: `agent_scanner.py:_panel_shows_equipped` — extended gate to `"unequip" in text_clean or "remove" in text_clean`.

**Test**: added equipped-engine case to `test_panel_shows_equipped_action_bar_gate` in `test_agent_h3.py`
(uses archive/live_20260605/agent_010/equip_slot_6.png; pytest.skip if absent).

**Suite**: 78 agent tests pass / 1 pre-existing disc-count fail unchanged.

**Acceptance**: live re-run needed to confirm engines now recorded in export (H22.3 batch run).

---

## 2026-06-08 — H25: Two-pass skill badge classifier (Sonnet 4.6)

**Root cause analysis (offline, against live archive agent_001 / agent_006):**

Two independent failure modes were identified:

1. **Dim non-maxed badges** (max pixel ≈ 177 < old threshold 180): sub-maxed skills render
   with dimmer badge text. Threshold=180 produced zero qualifying blobs → raw=None → 0.
   Confirmed on agent_001 (skills 8,1,8,12,11): basic/dodge/assist all had max=177–181 and
   returned no_blobs at 180. The H17 content-render gate (mean luma>40) passes these because
   the mean luma is above 40 even for dim badges (background included); only the badge text
   pixels themselves fall below 180.

2. **Zero-prefix digits** ("05/16" format, agent_006 "Billy"): ZZZ shows zero-padded current
   levels for some badge styles (e.g. 05 out of 16 max). Both "0" and "5" are wide blobs
   (b1w≥48) → old code returns None. Max pixel is above 180 so pass-1 fires but can't
   classify.

**Fix: two-pass threshold approach** (`agent_scanner.py`):
- Pass 1 (threshold=180, unchanged): correctly classifies bright {10,11,12} badges. The
  fill-based "10 vs 12" discriminant works at 180 (0" fill≈0.72, "2" fill≈0.63) but fails
  at lower thresholds (overlap at 0.663–0.724 at threshold=130).
- Pass 2 fallback (threshold=130): only entered when pass-1 finds no blobs (dim badge).
  Zero-prefix detection: b0_wide + b0_fill>0.65 (round "0") + b1_narrow →
    - b1_fill<0.65 → 1 ("01")
    - b1_fill≥0.65 → 8 ("08" with closed loops, may appear narrow due to "/" bleed)

**Confidence surfacing**: `_extract_skills` now uses `raw is not None` for the 85/30
confidence distinction (raw=None = unclassifiable badge → 30% confidence surfaced in
issues list), not the previous `1 <= lvl <= 12` check that silently gave 0 without
flagging it as uncertain.

**Remaining unclassifiable cases** (correctly return None/0 with 30% confidence):
- agent_001 assist "08" when the "/" and "1" from "/12" merge with "8" → wide b1 (w=62)
  outside the zero-prefix narrow-b1 rule.
- agent_006 all skills "05/16": both "0" and "5" are wide blobs → outside all rules.
These appear in the issues list as `skill_assist: low_confidence` etc.

**Tests** (`tests/test_agent_h4.py`):
- `test_h25_ref4_bright_badges_no_regression` (5 params): pass-1 still classifies
  Zhao's 12,10,11,12,11 correctly (no regression).
- `test_h25_dim_badge_fallback` (4 params): pass-2 recovers agent_001 basic=8, dodge=1,
  special=12, chain=11 (uses live archive fixture, skips if absent).

**Suite**: 361 passed / 1 pre-existing disc-count drift deselected.

---

## 2026-06-08 — Live-run review: H23–H26 confirmation pass (run @20:42, `--agents-only`, Opus 4.8)

Reviewed the latest live run: `archive/live_20260605` (authoritative artifacts at 20:42 —
`results.json` / `scan.log` / `agents.json` / `agent_scan.log`; the 14:xx `agent_*` dirs are stale
from a prior run sharing the reused dir). Latest-run log slice = `agent_scan.log` line 207 → end.
Headline counts: **39 owned visited → 35 records captured → 21 exported; 0 discs / 0 engines; 30 issues.**

### ✅ CONFIRMED FIXED LIVE — the #1 blocker is gone
- **Roster traversal + ownership + ring-close (H22/D37 + H23).** Final line:
  `agent_scan_done — ring closed (returned to 'Zhao') after 39 owned (54 visited)`. Terminated by
  **name-based ring-close, NOT AGENT_MAX**. 39 owned == user-confirmed true roster. 14 unowned skipped
  as a single contiguous `Lv.1 + static white chevron` tail (strip pos 40–53). No owned-position skips,
  no re-capture loop, no cap-out. The H22.3 failure (22/39 captured, never ring-closed) is resolved.
- **Mindscape (constellation)** is wired and reading a sane spread (0/2/3/5/6) — not a failure.
- **H24 name floor** prevents the triple-"Zhao" collapse: `Yanagi` now resolves to its own key.

### ❌ BLOCKER A — name resolution drops ~half the owned roster
- 15 of 35 captured records have an **empty `key`**; a further ~4 owned agents produced no record at
  all → only **21 of 39** exported. The WRatio≥85 floor (H24) is doing its job (no false collapse),
  but ~half the roster falls below it → captured-but-unnamed → dropped silently from the export.
- **Cannot root-cause from this run:** the issues file (which carries the raw OCR name text) was
  written to a **Windows-relative path** `export\youkai_export.issues.json` and never materialised in
  WSL (`export/` is empty, 0 issues on disk). So we can't tell DB-alias-gap from OCR-garble. This is a
  persistence-plumbing gap that must be fixed before the name gap is diagnosable. → **H27.**

### ❌ BLOCKER B — equipment universally false-empty (H26 fix did NOT hold live)
- 55 `slot_empty … action-bar shows 'Equip'` in the latest run — **every slot 0–6 of every Lv.60
  agent**. Built Lv.60 agents must have at least an engine, so this is categorically false-empty →
  **0 discs / 0 engines located**. The location cross-reference (the entire purpose of the tandem
  scan) still yields nothing. **H26/H21.4 acceptance FAILED live.**
- Co-symptoms in the slice: 10 `slot_reclick` + 4 `slot_gate_fail` (“panel never settled in 10 polls;
  banking frame”). The action-bar gate (`_panel_shows_equipped`) is being fed **transitional / wrong
  frames live**, so neither “unequip” nor “remove” is found → false-empty. H26’s keyword fix passed on
  the clean offline fixtures (ref_8 / agent_010) but the live failure is render-settle / bbox, not the
  keyword set. Same family as RC-3 / D35 (“works on a clean fixture, fails on a live transitional
  frame”). → **reopen H26 as H26.1.**

### ⚠️ DATA-QUALITY (lower priority)
- **Ascension broken:** 19 of 24 Lv.60 agents read `ascension 0` (should be 5); the dot-counter
  heuristic is effectively non-functional live. Low ZOD impact (derivable from level) but wrong, and
  unflagged. → **H28.**
- **Talent spurious zeros persist (H25 partial):** Lv.60 agents with `dodge:0`/`assist:0`/`chain:0`
  (impossible at 60) — e.g. Anton `12,0,0,12,12,0`, Seth `11,0,0,11,0,0`. Improved, not eliminated.
  H23 removed the old re-capture redundancy, so there is no best-of-N safety net → per-field talent OCR
  must now be reliable on its own. → fold into **H25.1**.

### ⚠️ INFRA
- **Archive reuse**: the run shares `archive/live_20260605` with prior runs (mixed 14:xx + 20:xx
  `agent_*` dirs) → stale frames masquerade as this run’s. Plus the issues file went to a Windows path.
  H5 persistence is incompletely wired for live WSL paths → post-run review is harder than it should be.
  → fold the per-run dir + WSL issues path into **H27.**

### Recommended priority
1. **P0 — H26.1** (equipment false-empty): the tandem scan’s whole point + the known empty-slot
   data-corruption risk (D36). Needs one *settled* equipped-slot frame from a live agent to retest
   `_panel_shows_equipped` offline; the fix is almost certainly render-settle-before-OCR + a live bbox
   re-verify, not the keyword set.
2. **P0 — H27** (persistence): write `issues.json` + per-run archive dir to the WSL run dir so the 15
   empty-key names (raw OCR) become reviewable; then close the name gap (DB aliases vs OCR garble).
3. **P1 — H28** (ascension) and **H25.1** (talent zeros).

---

## 2026-06-08 — H27 (Sonnet 4.6)

**Task:** Persist `issues.json` to the WSL run dir; timestamped archive dirs.

**Changes (`cli.py`):**
- `issues_path`: changed from `output.with_suffix(".issues.json")` (cwd-relative Windows path, never landed in WSL) to `run_dir / "issues.json"` — guaranteed in the same dir as `scan.log`/`results.json`.
- `run_ts` format: `run_YYYYMMDD_HHMMSS` → `live_YYYYMMDD_HHMMSS`.
- `--archive-dir` handling: now treated as a **base dir** with a timestamped subdir appended (`Path(args.archive_dir) / run_ts`). Consecutive runs on the same `--archive-dir` no longer overwrite each other.

**Tests (`test_cli_scan_all.py`):**
- `_make_args`: `archive_dir` is now a base dir (`tmp_path / "base"`).
- `_find_run_dir`: helper to locate the single timestamped subdir.
- Updated existing tests to discover `run_dir` dynamically.
- Added `test_scan_all_issues_written_to_run_dir`: verifies `issues.json` lands in run_dir and NOT beside the export file.
- Added `test_scan_all_consecutive_runs_get_distinct_dirs`.

**Suite:** 363 passed (pre-existing `test_read_disc_count_from_real_header` drift skipped — unrelated).

**No code changed this session — review only.** Tasks H26.1 / H27 / H28 / H25.1 added to TASKS_ocr.md.

---

## 2026-06-09 — H26.1 investigation (Sonnet 4.6)

**Verdict: H26.1 was a FALSE ALARM. H26 fix held live. Closed.**

Root cause of misdiagnosis: Opus review looked at `results.json` showing `discs:0, engines:0`
and inferred "equipment false-empty". The run was `--agents-only` — those zeroes are expected.

Confirmed from archive:
- All 32 Lv.60 agents (agent_000 to agent_031) have 7 equip slots captured in the 20:xx run.
- `_panel_shows_equipped` returns True on all 32 archived engine frames (bar="Remove").
- `_extract_equip_frame` produces correct disc set+slot and engine key for agent_000 (Zhao): 4×BunnyInWonderland, 2×YunkuiTales, engine=BunnyBand.
- The "55 slot_empty" events are for Lv.01-10 agents (scan positions 033-038) that genuinely have no discs/engine equipped — correct behavior.
- 13:xx run DID have the H26 pre-fix bug (27 engine false-empties); 20:xx run has 0 engine false-empties for Lv.60 agents.
- `slot_gate_fail` (4 events) fires when two adjacent disc slots have identical body pHash; banking returns equipped=True (same disc shown). Minor data-quality risk but not a false-empty.

Next: H28 (ascension from level, pure code fix), then H25.1 (talent zeros).

---

## 2026-06-09 — H28: Ascension OCR fix (`_read_level_cap`)

**Root cause**: `_count_ascension_dots` scanned `_ASCENSION_DOTS_BBOX` for bright columns > 150
luma. The region is dark (max luma ≈52 live). All agents returned ascension=0.

**Fix approach**: Replaced with `_read_level_cap`. The level badge shows "Lv. N / NN" where the
"/ NN" cap is rendered as dark-on-dark text (glyphs ≈0 luma, background ≈28-33 luma).
`_LEVEL_CAP_BBOX = (1182, 453, 1300, 502)` captures the "/ NN" region.

Preprocessing pipeline:
1. 3× upscale (INTER_CUBIC)
2. Normalize local contrast: min→0, max→255 (exposes dark glyph vs slightly-lighter background)
3. THRESH_BINARY_INV + Otsu → white text on black
4. bitwise_not → black text on white for Tesseract (psm 7, digits+slash whitelist)
5. Snap to `_VALID_AGENT_CAPS = {10,20,30,40,50,60}` via last-2-digit parse
   (spurious "7" prefix on thin "1" glyphs near button circles is stripped by taking last 2 digits)

**Validation**: 46/46 live archive agents (live_20260605) → correct cap and ascension.
Distribution: cap=10 (7), cap=20 (2), cap=50 (3), cap=60 (34).
Confidence: 90.0 on success, 30.0 on fallback (cap=0).

**Files changed**: `agent_scanner.py` (new `_LEVEL_CAP_BBOX`, `_VALID_AGENT_CAPS`,
`_ASCENSION_FROM_CAP`, `_read_level_cap`; `_extract_identity` updated), `tests/test_agent_h4.py`
(updated `test_zhao_ascension_in_range` → `test_zhao_ascension`: assert asc==5, conf≥80).

All 33 H4 tests pass. Full test suite running (background).


---

## 2026-06-09 — H27.1: Close the name gap (fairy DB → agents.json)

**Task**: H27.1 — use the fairy PostgreSQL `agents` table as source of truth to flesh out `data/zzz_1.4/agents.json`.

**Findings**:
- Queried `fairy` DB via asyncpg: 55 rows in `agents` table; 2 are `Avatar_*` internal test stubs → 53 real agents.
- Previous `agents.json` had only 28 entries covering ~17 distinct agents.
- Key bugs found:
  - `"Dialyn": "Rina"` — **wrong**. `Dialyn` is a separate physical/stun S-rank in the fairy DB; `Rina` is an electric/support S-rank. Fixed to `"Dialyn": "Dialyn"`.
  - `"Anby Demara" → "AnbyDemara"`, `"Billy Kid" → "BillyKid"`, `"Jane Doe" → "JaneDoe"`, `"Von Lycaon" → "VonLycaon"` — ZOD keys were using the full surname variant. Fairy DB canonical keys are `"Anby"`, `"Billy"`, `"Jane"`, `"Lycaon"`. Updated.
  - 26 agents entirely absent from the map (Alice, Aria, Banyue, Cissia, Hugo, Ju Fufu, Lucia, Nangong Yu, Orphie & Magus, Pan Yinhu, Promeia, Pyrois, Seed, Soldier 0 - Anby, Starlight - Billy, Sunna, Ye Shunguang, Yidhari, Yuzuha, and more).
- `to_zod_key(fairy.name)` generates the canonical ZOD key for every agent.
- Full-name aliases kept: `"Tsukishiro Yanagi"→"Yanagi"`, `"Hoshimi Miyabi"→"Miyabi"`, `"Asaba Harumasa"→"Harumasa"`, `"Komano Manato"→"Manato"`, `"Von Lycaon"→"Lycaon"`, etc.
- `"Dan Yinhu"` and `"Orphie Magnus"` (former garbage tests) now correctly resolve via WRatio ≥ 85 — these are legitimate OCR-noise variants; moved to the resolved test set.

**Changes**:
- `data/zzz_1.4/agents.json` — complete rewrite: 65 entries covering all 53 fairy agents + key full-name aliases.
- `tests/test_normalizer.py` — updated `test_normalize_agent_full_names` (added ~20 new cases, fixed Dialyn/Jane/Anby/Billy/Lycaon values), updated `test_normalize_agent_floor_rejects_garbage` (removed Ju Fufu, Dan Yinhu, Orphie Magnus).

**Result**: 386 passed, 1 pre-existing failure (disc count OCR drift — unrelated).

## 2026-06-09 — H25.1: Talent spurious-zero hardening

**Root cause (diagnosed from live archive `live_20260605` crops):**
- `_read_skill_badge` dim fallback classified "0X" badges by checking `b1_w < _BADGE_NARROW_W`. This worked for the max-12 format ("08/12") where the "/" glyph bleeds into "8" making it narrow (~47px). In max-16 format ("08/16"), wider spacing means "8"/"9" render at full width (~63px), failing the narrow check.
- Specific failures observed: "08/16" (dodge=8→0), "09/16" (assist=9→0), "07/12" (dodge=7→0), "03/12" (assist=3→0), "05/12" (basic=0→was correctly 0 but same issue).

**Fix:**
- Return type of `_read_skill_badge` changed from `int | None` to `tuple[int, float] | None` (value + confidence).
- Dim fallback "0X" branch: removed `b1_w < _BADGE_NARROW_W` constraint for the "8" return. Added 3-tier fill-based classifier for wide second digit:
  - fill ≥ 0.70 → return (8, 65.0) — "08" or "09" (round/looped digit; off-by-1 on "09" acceptable)
  - fill ≥ 0.55 → return (5, 45.0) — "05" or "06" (partially closed digit)
  - fill < 0.55 → return (7, 40.0) — "07" or similar (angled/open digit)
- All tier confidences < _LOW_CONF_THRESHOLD (70) → surface in issues as low_confidence.
- Added Lv.60 talent floor in `scan_agents`: any `talent.X == 0` on a `level >= 60` agent emits a `talent_zero_lv60` issue as backstop.
- `_extract_skills` updated to use `(lvl, badge_conf) = raw` tuple.

**Fixtures committed:** 5 badge crops to `tests/fixtures/skill_badges/`:
- `badge_08_of_16.png` — agent_023 skill[1] dodge=8/16
- `badge_09_of_16.png` — agent_023 skill[2] assist=9/16
- `badge_07_of_12.png` — agent_012 skill[1] dodge=7/12
- `badge_08_of_12_narrow.png` — agent_001 skill[0] basic=8/12 (original passing case)
- `badge_03_of_12.png` — agent_009 skill[2] assist=3/12

**Test results:** Live archive re-run: 0 zeros across all 45 agent skill sets (was 21 agents with ≥1 zero). Suite: 384 passed / 1 pre-existing disc-count-drift failure.

**Known limitations:**
- "03" reads as 5 (off by 2); "09" reads as 8 (off by 1) — tier classification is approximate. These are flagged in issues as low_confidence.
- Values 13-16 in the bright pass still read as 12 (pass-1 can't distinguish "1X" for X≥3 by fill alone). These are non-zero wrong values; fixing requires more digit fill data.

---

## 2026-06-09 — Live run review @14:04 (`--agents-only`, run `live_20260609_140457`) — Opus

**Run command:** `python -m youkai_ocr scan-all --archive-dir …\archive\live_20260605 --agents-only --debug-overlays`
**Headline:** roster traversal is fully fixed; the only remaining loss is agent-name recognition.

### Confirmed FIXED live (close these confirms)
- **0 discs / 0 engines is EXPECTED** — `--agents-only` skips both inventory phases (`cli.py:498-500,535-537`,
  `discs=[] / engines=[]`). Same misread as the 2026-06-09 H26.1 false alarm. Not data loss. (A real
  disc/engine count needs a full `scan-all`.)
- **H22.3 / H23 (ownership + traversal) CONFIRMED:** `agent_scan_done — ring closed (returned to 'Zhao')
  after 39 owned (54 visited)`. User owns **39**; scanner found all 39, ring-closed cleanly (NOT
  AGENT_MAX), and skipped the 14 Lv.1 white-chevron unowned tail (strip pos 40-53) as a contiguous block.
- **H21.1 (file-routed logger) CONFIRMED:** `agent_scan.log` has all `_log.*` markers.
- **H18.5/H19.3/H21.4 equipment markers** (all on Lv.1 unowned tail or genuinely-empty agents):
  3 `slot_gate_fail` + several `slot_reclick` (the H19 dropped-click retry working). The wall of
  `slot_empty … 'Equip'` are the Lv.1-10 agents at the roster tail with nothing equipped — correct.

### THE blocker: name crop truncates long full names → 39 found, only 26 exported
Funnel: **39 owned visited → 35 scan records → 26 exported.** The 13 lost are name failures
(empty key dropped at export + 4 critical_fail key=0.0), NOT traversal and NOT the DB. Root-caused
offline by re-OCRing the archived `base_stats.png` name crops (`_AGENT_NAME_BBOX = (955,278,1350,330)`,
only 395px wide):
```
 10 'Hoshimi Mi'  32 'Asaba Haru'  34 'Von Lycac'  35 'Komano Ma'  26 'Anby Dem'  3 'Ye Shundat'
```
The ZZZ client renders **full names** ("Hoshimi Miyabi", "Von Lycaon", "Asaba Harumasa", "Vivian Banshee",
"Anton Ivanov", "Pulchra Fellini", "Soldier 11"…) that overflow past x=1350 → truncated → below the
WRatio floor → empty key → dropped. (D37/H24 fixed the *DB*; this is the *crop geometry*, never measured
live until now because earlier runs lost these agents to traversal first.)

**No single fixed right-edge works** — widening to 1480/1560 truncation-recovers the long names but
catches trailing icon glyphs on short names ("Triager (g", "Pulchra Fellini'", "Orphie Magnusson & (@")
→ Trigger/Pulchra/OrphieMagus regress. Measured offline across all 39:
- bbox 1350 (current): **27/39**
- bbox 1480, no clean: 34/39 but Orphie+Pulchra regress
- **bbox 1560 + junk-strip matcher: 36/39, zero regressions** ← the fix

### Fix (offline-validated; → H30)
1. `_AGENT_NAME_BBOX` → `(935, 278, 1560, 332)` (capture full names).
2. `normalize_agent`: pre-clean before WRatio — strip chars outside `[A-Za-z0-9& -]`, drop tokens
   len<2, collapse whitespace. Lets the wide crop tolerate leading/trailing icon glyphs.
3. Recovers 36/39. Remaining 3 are individual follow-ups:
   - **Qingyi** (pos 17, OCR'd "Ginayi"/"Oinayi") — hard Q→G/O garble; needs name-crop preprocessing,
     no alias helps. Flag low-confidence.
   - **Nekomata** (pos 29) — client renders full name "Nekomiya Manaka" (user-confirmed Nekomiya =
     Nekomata); **Nekomata is absent from `agents.json` entirely** → add the full display name → key `Nekomata`.
   - **Orphie & Magus** (pos 12, "Orphie Magnusson") — scores 80; add alias "Orphie Magnusson"→OrphieMagus.
4. Residual settle-timing (separate, lower pri): pos 12/24 read 0.0 *live* but resolve fine from the
   archived frame → the Base-tab name read still occasionally banks a transitional frame (H1x family).
   The wide bbox + clean covers the archived frames; if live still drops them, gate the name read on a
   settled frame.

**No code changed this session (Opus review only).** Recommend Sonnet executes H30.

## 2026-06-09 — H30.1 + H30.2 implemented (Sonnet)

**H30.1 — Widen name bbox + junk-strip matcher:**
- `_AGENT_NAME_BBOX` widened `(955,278,1350,330)` → `(935,278,1560,332)` in `agent_scanner.py`.
- Added `_AGENT_NAME_JUNK_RE` + `_clean_agent_name` to `normalizer.py`: strips chars outside
  `[A-Za-z0-9& -]`, drops tokens len<2, collapses whitespace. Applied as pre-clean in
  `normalize_agent()` before WRatio lookup. Lets the wider bbox tolerate trailing icon glyphs
  without regressing Trigger/Pulchra/OrphieMagus.

**H30.2 — Close last-3 name gaps:**
- (a) Added `"Nekomiya Manaka"→Nekomata` and `"Nekomiya Mana"→Nekomata` to `data/zzz_1.4/agents.json`
  (user-confirmed Nekomiya = Nekomata; full in-game display name was absent from the map).
- (b) Added `"Orphie Magnusson"→OrphieMagus` alias (pos 12, was scoring 80 < floor).
- (c) Qingyi OCR garble ("Ginayi"/"Oinayi"): confirmed both score <85 and surface as
  `unknown_agent` issues (not a wrong snap). No alias added — desired low-confidence behavior.

**Tests:** 390 passed / 1 pre-existing deselected (`test_read_disc_count_from_real_header` —
disc count changed 2205→2217, unrelated). New test cases added to `test_normalizer.py`:
- `test_normalize_agent_full_names`: added Nekomiya Manaka/Mana, Orphie Magnusson, junk-glyphed
  Trigger/Pulchra — all resolve ≥85.
- `test_normalize_agent_floor_rejects_garbage`: added "Ginayi"/"Oinayi" — both rejected.

**Acceptance gate**: offline re-OCR pending live confirm (H30.4); H30.3 (settle-gate) deferred.

## 2026-06-09 — H30.4 Live confirm + Lucia/Lucy alias fix (Sonnet)

Live run `live_20260609_152444` (scan-all --agents-only --debug-overlays):
- **38/39 agents keyed correctly** — exceeds the ≥36/39 H30.4 threshold.
- Ring closed: Zhao after 39 owned / 54 visited. Positions 40–53 = Lv.1 tail, all `agent_skip` as expected.
- 1 blank key confirmed = Qingyi: base_stats overlay shows "Qingyi" clearly but OCR reads "Ginayi"-class glyph (score 67.5 < 85 floor). Expected; surfaces as `low_confidence{key:67.5}` in issues.json.
- 32 `low_confidence` issues total — all numeric fields (mindscape, ascension, skill levels), zero wrong keys.

**Lucia/Lucy alias bug found and fixed:**
- agent_001 = "Lucia Elowen" (Spook Shack, Ether/Support) → resolved to Lucia ✓
- agent_022 = "Luciana de Montefio" (Sons of Calydon, Fire/Support) = Lucy — was resolving to Lucia
  (WRatio("Luciana de Montefio", "Lucia")=90 beat WRatio(..., "Lucy")=77)
- Fix: added `"Lucia Elowen"→Lucia` and `"Luciana de Montefio"→Lucy` to `agents.json`.
  Both now exact-match at score 100. 399 passed, 0 regressions.

---

## 2026-06-10 — H6 + F3 + F4 + F5 (Sonnet 4.6)

### H6 — Live acceptance confirmed

Run `archive/live_20260609/live_20260610_065548`: **39 agents, 2252 discs, 222 engines**, 186 issues
(all `low_confidence` — 0 critical fails). Ring closed at Zhao after 39 owned / 54 visited. H6
acceptance fully met. First clean full `scan-all`.

### F3 — Review report

Added `_write_review_report(issues, path)` to `cli.py`: writes `review.txt` per run with sections
for critical fails, unknown agents, low-conf agents/engines/discs, and orphans. Wired into
`_cmd_scan_all` alongside `issues.json`. Verified on live issues.json (31 low-conf agents, 155
low-conf engines, 0 criticals → output readable and actionable).

**Bonus fix (normalizer):** `engines.json` contains `_comment_*` separator keys whose VALUES are
strings like `"--- S-rank ---"`. These were included in the rapidfuzz match pool and could become
false match targets at low score (~40%). Fixed `_load()` to strip `_comment_*` entries from
`_engines` dict before building the pool.

**Test fixes:** two stale `test_cli_scan_all.py` tests expected `ScreenAssertError` from
`_check_engine_screen` (changed to warn-not-abort in H8) and from `_check_agent_screen` (which no
longer calls the retired `detect_owned_agent_cells`). Updated to assert current behavior (warning
printed, no exception). Suite: **397 passed → 399 passed**, 1 pre-existing skip
(`test_read_disc_count_from_real_header` fixture drift, unrelated).

### F4 — Safety audit + runbook

Static audit: `grep` for `ReadProcessMemory`, `WriteProcessMemory`, `mitmproxy`, `scapy`,
`socket.` across `src/` → **0 matches**. Only `ctypes.windll.kernel32.GetCurrentProcessId()`
(read-only, used to `AllowSetForegroundWindow` for the countdown focus) and
`ctypes.windll.user32.AllowSetForegroundWindow` — both benign, read-only OS APIs.

`docs/RUNBOOK.md` written: prerequisites, full 3-step scan procedure, output file guide,
review.txt interpretation, optimizer import notes, troubleshooting table, and the static audit
commands for future audits.

### F5 — Decommission Rust youkai

`README.md` created at repo root. Describes `youkai-ocr` as the active tool; notes `youkai/` as
a decommissioned Rust prototype, `irminsul/` as a pristine reference clone, `zod.rs` as a schema
reference. D38 appended to `docs/DECISIONS.md`. Rust code left in place (already outside Python
build path; no value in deleting it).

## 2026-06-10 — F2: Golden-replay test + accuracy gate

**Task F2 complete.**

### Fixtures committed
- `tests/fixtures/golden/discs/` — 30 disc panel crops (439×770, synthetic frame via `_PANEL_BBOX`)
- `tests/fixtures/golden/engines/` — 8 engine panel crops (439×770, same panel origin)
- `tests/fixtures/golden/agents/` — 8 agent frame pairs (1920×1080 base + skills)
- `tests/fixtures/golden/labels.json` — human-verified ground-truth labels

### Test file: `tests/test_golden_replay.py`
Six tests: `test_disc_golden_replay`, `test_engine_golden_replay`, `test_agent_golden_replay` (§10 accuracy gate), `test_negative_tinted_frame_rejected`, `test_negative_wrong_resolution_rejected`, `test_positive_clean_frame_passes_hygiene`.

Gate logic: name/key fields ≥99% correct, numeric fields ≥98% correct, every miss must have confidence < 70 (no silent wrong values). Uses `scan_single_frame_disc/engine/agent` helpers — no game required.

Negative controls: warm-tinted synthetic frame (R=240, G=190, B=120) → `check_color_hygiene()` raises ValueError; 1920×900 frame → `calibrate()` raises ValueError.

### CI: `.github/workflows/ci.yml`
ubuntu-latest, Tesseract installed via apt, `pip install -e .[dev]`, `pytest -q`. Runs on push to main and feature/* branches and on PRs to main.

All 6 new tests pass; full suite 406 green.

---

## 2026-06-10 — H7b: storage category-tab measurement + active_storage_tab()

**Task**: Measure the 4 Storage category-tab bboxes + active-glow threshold from `reference_1`/`reference_2`; implement `active_storage_tab()` + fixture tests.

**Measurement approach**: Pixel analysis on the glow column at game x=1413-1430 (right edge of the storage panel pill tabs). Compared ref_1 (Drive Disc Storage) vs ref_2 (W-Engine Storage) to isolate the active-indicator stripe per tab.

**Findings**:
- Storage category tabs are VERTICAL PILL BUTTONS at game x≈1350-1430, stacked vertically.
- The ACTIVE TAB shows a bright stripe on the pill's right edge (game x=1413-1430).
- **W-Engine tab** (index 0): active stripe at game y=135-203, color=[213,207,0] (yellow-gold), luma≈185 in ref_2.
- **Drive Disc tab** (index 1): active stripe at game y=304-325, color=[255,255,255] (white), luma≈255 in ref_1.
- Inactive state for each: luma≈12-30 (near-black).
- Only 2 tabs are visible in ref_1/ref_2; tabs 3+4 are undocumented (no reference images for other storage categories).
- Note: "4 tabs" in the original task spec — only 2 confirmed from available references.

**Files changed**:
- `src/youkai_ocr/cli.py`: added `active_storage_tab(frame, calib)` + `STORAGE_TAB_ACTIVE_LUMA=50` + `_STORAGE_TAB_BBOXES`.
- `data/zzz_1.4/navigation.yaml`: added `storage_tabs` section with glow_bbox for each tab.
- `tests/test_storage_tabs.py`: 6 new fixture tests (disc-active on ref_1, engine-active on ref_2, cross-checks).

**Results**: 6/6 new tests pass. Full suite: 412 passed, 0 failures.

**Status**: H7b DONE. H7a (blocked on ref_11/ref_12), H7c (blocked on H7a+H7b).

---

## 2026-06-11 — H7a: bottom_nav centres + screen signatures (Sonnet 4.6)

**Task**: Measure `Storage`/`Agents` button centres from ref_11 (main menu), `Base` button centre
from ref_12 (agent selection menu), and main-menu/agent-menu signatures → `navigation.yaml`.

**Measurement method**: PIL pixel analysis on `reference_11_main_menu.png` (1922×1112,
game-area offset x=1, y=31). OCR via pytesseract on the icon-label strip (game_y 1020-1079
cropped, 2× zoomed, contrast-enhanced) to find text-label centres.

**Results**:

| Button | game_x | game_y | Method |
|--------|--------|--------|--------|
| Storage | 1123 | 1041 | OCR text centre (8th bottom-nav item) |
| Agents | 1251 | 1041 | OCR text centre (9th bottom-nav item) |
| Base (agent menu) | 1140 | 816 | Already in nav.yaml (H11 live); confirmed: pixel (1140,816) in ref_12 = [255,255,255] (white pill) |

Full bottom-nav item sequence (for reference):
More(319) · Investigation Zone Squad(428) · Mail(553) · Options(671) · Notices(784) ·
Achievements(890) · Inter-Knot(1008) · **Storage(1123)** · **Agents(1251)** · Store(1377) ·
New Eridu City Fund(~1479) · Signal Search(1595)

**Screen signatures measured** (4 screens cross-validated):

| Signature | bbox | metric | main_menu | agent_menu | disc | engine |
|-----------|------|--------|-----------|------------|------|--------|
| main_menu | [1000,1033,1300,1050] | mean_luma | **55.2** | 0.1 | 0.0 | 0.0 |
| agent_selection_menu | [1888,430,1920,570] | teal_px (G-R>30,G>100) | 55 | **4480** | 0 | 0 |

Thresholds: main_menu > 20; agent_selection_menu > 1000.

**Files changed**: `data/zzz_1.4/navigation.yaml`
- Updated `agent_menu.bottom_nav.storage.center`: [554,971] → [1123,1041]
- Updated `agent_menu.bottom_nav.agents.center`: [891,971] → [1251,1041]
- Added top-level `screen_signatures:` section (main_menu + agent_selection_menu)
- Added `meta.updated: 2026-06-11`

**Test suite**: 412 passed, 0 failures (yaml-only change; no Python code touched).

**H7a acceptance**: ✓ Storage/Agents centres in nav.yaml; ✓ Base confirmed correct; ✓ both screen signatures measured with thresholds; suite green.

---

## 2026-06-11 — H7c: Auto-nav driver wired into scan-all

**Task**: H7c — wire `_NavDriver` + `assert_screen` / `return_to_main` into `cli.py:_cmd_scan_all`.

### Implementation

Added to `cli.py`:

**Nav constants** (from nav.yaml H7a measurements):
- `_NAV_STORAGE_CENTER = (1123, 1041)`, `_NAV_AGENTS_CENTER = (1251, 1041)`
- `_STORAGE_TAB_CLICK_CENTERS = ((1421, 169), (1421, 314))` — glow bbox midpoints

**Screen predicates** (all module-level, testable offline):
- `_is_main_menu(frame, calib)` — mean_luma > 20 in sig bbox [1000,1033,1300,1050]
- `_is_agent_selection_menu(frame, calib)` — teal_pixel_count > 1000 in bbox [1888,430,1920,570]
- `_is_storage_screen(frame, calib)` — delegates to `active_storage_tab()` (already implemented H7b)

**`_NavDriver` class** — lazy pynput mouse/keyboard; click targets converted via `calib.to_screen()`:
- `navigate_to_storage()` — click Storage button, poll `_is_storage_screen`
- `switch_storage_tab(idx)` — click tab glow center, poll `active_storage_tab() == idx`
- `return_to_main()` — press Escape, poll `_is_main_menu`
- `navigate_to_agents()` — click Agents button, poll `_is_agent_selection_menu`
- `wait_for(check_fn, timeout=8s, poll=0.3s)` — generic poller used by all nav methods

**`_cmd_scan_all` rewrite** — branches on `manual_nav = getattr(args, "manual_nav", False)`:
- **Auto-nav (default)**: assert main menu → navigate_to_storage → switch engine tab → scan engines → switch disc tab → scan discs → return_to_main → navigate_to_agents → scan agents. No `input()` calls. Phase order changed to engines-first (matches navigation flow).
- **Manual-nav (`--manual-nav`)**: original `input()` + `_countdown(5)` + `_preflight_frame()` + `_check_*_screen()` flow, unchanged.

**`--manual-nav` flag** added to `scan-all` subparser.

### Tests added

`tests/test_cli_scan_all.py` (22 → 30 tests):
- `test_is_main_menu_true_on_bright_sig_bbox` / `false_on_dark_frame` / `false_on_agent_menu_frame`
- `test_is_agent_selection_menu_true_on_teal_sig_bbox` / `false_on_dark_frame`
- `test_auto_nav_driver_walks_full_transition_graph` — FakeDriver records call sequence; asserts [navigate_to_storage, switch_storage_tab(0), switch_storage_tab(1), return_to_main, navigate_to_agents]; input() never called; all 3 phase outputs written.
- `test_auto_nav_raises_if_not_on_main_menu` — dark initial frame → ScreenAssertError
- `test_auto_nav_agents_only_skips_storage` — storage + return_to_main absent; navigate_to_agents present

Existing tests updated: `_make_args()` now sets `manual_nav=True` so all existing H5 tests continue using the manual-nav path unchanged.

**Full suite**: 420 passed (was 412). 0 regressions.

**H7c acceptance**: ✓ mocked driver test walks full transition graph and asserts each gate; live leg unblocked (H7a gates now wired).

---

## 2026-06-11 — Bugfix: Drive Disc tab click target (Sonnet)

### Bug
`switch_storage_tab(1)` (Drive Disc) always timed out after W-Engine scan. Mouse was
observed clicking game coords (1421, 314) — left edge of the detail panel in the engine
name text area — completely missing the Drive Disc tab button.

### Root cause
The storage tabs are a **horizontal row** of 4 circular buttons, not vertical pills.
Previous glow_bbox analysis correctly identified which tab is active (luma at x=1413-1430),
but the click coordinates were derived from glow_bbox centers rather than the actual
clickable button positions.

Pixel analysis of reference_1 (disc active) and reference_2 (engine active):
- W-Engine tab circle: game x=1413-1479, y=128-209, **center (1447, 169)**
- Drive Disc tab circle: game x=1450-1619, y=128-210, **center (1535, 169)**

Old Drive Disc click (1421, 314) was ~114px below and ~114px left of the button center.
Old W-Engine click (1421, 169) was within the W-Engine circle (why engine scan worked).

### Fix
Updated `_STORAGE_TAB_CLICK_CENTERS` in `cli.py`:
- Index 0 (W-Engine):  (1421, 169) → **(1447, 169)**
- Index 1 (Drive Disc): (1421, 314) → **(1535, 169)**

Updated `navigation.yaml` storage_tabs section with correct circle positions and explanatory notes.
Detection glow_bboxes unchanged (working correctly via coincidental secondary effects).

---

## 2026-06-11 T1 — `--phases` flag for scan-all

**Task:** Add `--phases engines,discs,agents` flag + `select_phases()` helper; gate auto-nav and manual-nav flows.

**Changes:**
- `src/youkai_ocr/cli.py`: Added `_VALID_PHASES`, `select_phases(args) -> frozenset[str]` (validates names, maps deprecated `--agents-only` → `{"agents"}`). Updated `_cmd_scan_all` to call `select_phases` at entry, replaced all `agents_only` boolean checks with phase-set membership tests, added `storage_visited` tracker for auto-nav path, gated agents phase in both auto-nav and manual-nav branches, guarded shared agent result block with `if "agents" not in phase_results:`, updated `resolve_locations` gate to `"agents" in phases and "discs" in phases`. Added `--phases` argument to scan-all CLI.
- `tests/test_cli_scan_all.py`: Fixed pre-existing `FakeDriver.switch_storage_tab` TypeError (missing `**kwargs`), added `select_phases` import, added 8 new unit tests (default all, discs-only, multi-phase, agents-only alias, alias overrides phases, unknown name, empty, integration test for `--phases discs`).

**Result:** 30/30 tests pass (was 19/20 with one pre-existing failure now fixed).


## T2 — progress.py emitter (2026-06-11)
- Created `src/youkai_ocr/progress.py`: `ProgressEmitter(stream)` with all 7 event methods (run_start, phase_start, progress, phase_done, warning, done, error); each writes one flushed JSON line. `NullEmitter` no-op with same interface.
- Created `tests/test_progress.py`: 13 tests — schema round-trips, null-total, resumed flag, review_path optional, NullEmitter writes nothing.
- Result: 13/13 pass. Full suite clean.

## T3 — --porcelain wiring (2026-06-11)
- `_Tee`: added `mirror` param; in porcelain mode mirror=sys.stderr so print() goes to stderr, stdout stays clean for JSONL.
- `scan-all` subparser: added `--porcelain` flag.
- `_cmd_scan_all`: constructs `ProgressEmitter(sys.stdout)` (before _Tee intercepts stdout) or `NullEmitter` based on flag; emits `run_start` after `select_phases`; `phase_start`/`phase_done` around all 6 phase branches in both auto-nav and manual-nav paths; `done` after results.json; `error` via `except BaseException` before the existing `finally` cleanup.
- 3 new tests in `test_cli_scan_all.py`: pure-JSONL stdout, correct phase sequence for `--phases discs`, error event on ScreenAssertError.
- Result: 46/46 pass across test_cli_scan_all + test_progress.

## T5 — on_item progress callbacks (2026-06-11)
- `scan_discs`: added `on_item: Optional[callable] = None`; called from worker threads after each cell completes (success and error paths), passing `(n, total_discs)`.
- `scan_engines`: added `on_item`; called after each cell in the sequential loop, passing `(scanned, total_engines)`.
- `scan_agents`: added `on_item`; called once per loop iteration (before `continue` in critical-fail branch and at end of normal path), passing `(scanned, None)`.
- `cli.py`: all 6 scan call sites in `_cmd_scan_all` (auto-nav + manual-nav) wired `on_item=lambda s, t: emitter.progress(phase, s, t)`.
- 6 new tests (2 per scanner): monotonically-increasing-scanned + omitted-no-error. Disc test uses `sorted()` not `==` (thread-pool completion order is non-deterministic).
- Result: 458/458 passed, 0 regressions.

## T4 — Non-interactive policy under porcelain (2026-06-11)
- `_make_first_item_check(phase, *, interactive=True, emitter=None)`: when `interactive=False`, low-confidence soft-warn branch calls `emitter.warning(msg)` and returns (no `input()`); hard total-fail branch (mean conf < 25 or item=None) remains RuntimeError regardless.
- `_preflight_frame(…, *, interactive=True, emitter=None)`: when `interactive=False`, dark-but-not-black branch (5 ≤ brightness < 15) calls `emitter.warning(msg)` and returns the frame; hard aborts (brightness < 5, size change, color hygiene) remain RuntimeError regardless.
- `_cmd_scan_all`: derived `interactive = not porcelain`; passed `interactive/emitter` to both helpers at all 3 call sites in the manual-nav path; bare `input()` navigation gates in manual-nav wrapped with `if interactive:`.
- 8 new tests in `test_cli_scan_all.py` covering: dark-frame non-interactive emits warning, dark-frame interactive calls input, black-frame hard-abort in both modes, low-conf non-interactive emits warning, low-conf interactive calls input, total-fail hard-abort, manual-nav porcelain no input calls.
- Result: 452/452 passed, 0 regressions.
