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
