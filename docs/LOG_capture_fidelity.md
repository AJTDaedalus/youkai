
## T2.1 — Diagnose empty substat-key cases
**Done.** Replayed all 2,217 disc `panel.png` crops from `archive/live_20260605`
via `tools/diag_empty_keys.py`; full report at `docs/diag_empty_keys.json`.

**Findings:**
- **35 empty-key substats** across 35 discs (1.58% of inventory).
- **One root cause**: every single case is the stat **"HP"** (2 characters). Tesseract
  cannot read a 2-character name in a 339×41px crop — both bright and dim native passes
  return empty string regardless of text brightness.
  - 33/35: white "HP" text (luma max=255, p90=22 — tiny text on dark canvas).
  - 2/35: dim/gray "HP" text (luma max≈75 — probable low-level disc rendering).
- **No dict gaps**: the normalizer already handles "Hi" (Tesseract's 2× misread of "HP")
  → `hp_` at conf=60 via fuzzy match. The existing flat/percent value disambiguation
  (`pct_seen` + `_value_plausible` + `_PERCENT_TO_FLAT` fallback) correctly resolves:
  - val=3% → `hp_` (HP%) ✓
  - val=112 (flat, no %) → `hp` (flat HP) via `_PERCENT_TO_FLAT['hp_']` fallback ✓

**Fix plan for T2.2**: add a 2× LANCZOS name-upscale pass in `disc_scanner.py:_extract_disc`
when both bright+dim native passes return empty (around line 266-268). No normalizer changes
needed; value disambiguation already handles the rest.

## T3.1 — Roster coverage check in _cmd_scan_all
**Done.** Added a roster coverage check to `_cmd_scan_all` (both auto-nav and manual-nav paths):

- On entering the agents phase, capture the agent-menu frame (auto-nav: the return value of `driver.navigate_to_agents()`; manual-nav: the preflight frame) and count owned cells with `detect_owned_agent_cells`.
- `grid_count` is printed and stored. After scan, if `grid_count > 0` and `len(unique_agents) < grid_count`, a `WARNING: roster coverage` message is printed.
- `results.json` gains a `coverage` key with: `roster_grid_visible`, `agents_scanned`, `gap`, `warning` (bool), `scanned_keys`, and optionally `critical_fail_count`.
- The grid count reflects the first visible page only (max 8 cells); it is a lower bound, not the full roster count. The check is conservative: it warns only when scanned < visible.
- 3 new unit tests cover: match (no warning), gap (warning + results.json populated), phase-skipped (no coverage key).

495 tests green.

## T1.5 — fingerprint reconciliation in cli.py:_cmd_scan_all
**Done.** Replaced the placeholder comment with `_reconcile_locations` + `_backfill_disc_substats` implemented in `cli.py`.

Key decisions:
- **Primary filter**: set_key + slot_key + main_stat_key (most discriminating trio).
- **Widened fallback**: if no primary match, retry with set_key + slot_key only (covers main_stat OCR drift, e.g. "ATK" vs "ATK%").
- **Rank**: among multiple candidates, rank by (substat key overlap, -|level diff|) — substat keys are more stable than values between two OCR reads.
- **1:1 guarantee**: `matched_disc_idx` / `matched_eng_idx` sets prevent double-assignment.
- **no-match → append**: inventory misses are appended as new entries so no equipped disc is ever dropped. Reported as `status: "orphan"` informational issues.
- **Backfill**: `_backfill_disc_substats` fills `key:""` substats from the equipped read when values match within 0.01 (self-heals empty-key issues from W2).
- **Engine fallback**: if key doesn't match (OCR drift between inventory/equip reads), appended to the list.
- Tests: 8 new unit tests in `test_cli_scan_all.py`; all `resolve_locations` mock patches removed (function no longer called from cli.py).

All 500 tests green.

## T1.4 — scan_agents equip-slot loop
**Done.** scan_agents calls scan_equipped_disc_frame and scan_equipped_engine_frame in the equip loop and returns (agents, issues, equipped_discs, equipped_engines) with full ZodDisc/ZodWEngine objects with location already set. 485 tests green.

## T1.3 — scan_equipped_engine_frame
**Done.** Added `scan_equipped_engine_frame` to `wengine_scanner.py`.

Key decisions:
- **Panel layout**: In the engine equip-select view the detail panel sits at x=537–1060
  (past the left thumbnail), with the engine name at y=118–165 (1-line) or y=118–210 (2-line).
- **Name + level**: Read via `read_text` on a block covering y=118–310. Level extracted with
  `re.search(r"Lv\.\s*(\d+)\s*/\s*(\d+)", ...)`. The 2-line name case ("Tremor Trigram Vessel")
  shifts everything down ~40px but the combined block OCR handles both without probing.
- **Refinement**: `count_filled_stars` on star band (600, 210, 1060, 305). Stars display as white
  OUTLINE at refinement=1 (no gold fill); gold fill appears only at refinement>1. All equipped
  engines in the current archive are refinement=1, so the function correctly returns 1 via fallback.
- **Normalizer gap**: "Tremor Trigram Vessel" (agent_006) is not in engines.json (post-v1.4 engine);
  normalizer returns conf=47 (too low for reliable key). Add entry to data/zzz_1.4/engines.json
  when the full normalizer update is done.

Test added: `tests/test_wengine_scanner.py::test_scan_equipped_engine_frame_starlight`.
Validated: agent_018 Starlight Engine Lv.60 → key='StarlightEngine', level=60, ascension=5, ref=1.
43 tests green: `pytest tests/test_wengine_scanner.py tests/test_disc_scanner.py tests/test_golden_replay.py`.

## T1.1 — disc_scanner.py panel origin refactor
**Done.** Replaced all hardcoded absolute bboxes with panel-local `_*_REL` constants
and an `_abs_bbox(rel, origin)` helper. `_extract_disc` and `scan_single_frame` now
accept `panel_origin: tuple[int,int] = _PANEL_ORIGIN`. All 18 tests green.

## T1.2 — scan_equipped_disc_frame
**Done.** Added constants `_EQUIP_X0/X1`, `_EQUIP_TITLE_*`, `_EQUIP_RARITY_*`,
`_EQUIP_BLOCK_DY*`. Key decisions:

- **PSM-6 block OCR** over the full stat region avoids per-row Y calibration (sub-row
  pitch varies with "+N" roll indicators). Reads main+substats correctly.
- **`_equip_detect_rarity`**: Two-probe approach (ry=165 then ry=215) with a tight
  32×28px icon crop `(614, ry+12, 646, ry+40)`. The original 38×48px crop caused p75
  to hit dark background; tight crop hits the icon. Probe at ry=165 fails for 2-line
  titles (white title text gives p75=(240,240,240)); ry=215 succeeds for those cases.
- `engine` param accepts `str | TextRecognizer` to allow sharing a warm recognizer.
- `slot_key` is the in-game disc slot (1-6), passed by caller from `6-slot_idx`.

Validated against `archive/live_20260605/agent_018`: ChaoticMetal (1-line) and
WoodpeckerElectro (2-line) both read correctly. `lv=15` for Woodpecker confirmed fixed.
All 18 tests green: `pytest tests/test_disc_scanner.py tests/test_golden_replay.py`.

---

## T6.1 Oracle — Vision Read (2026-06-15)

**Method:** Read `skills.png` + `skills_overlay.png` for all 39 agents in `archive/live_20260609/live_20260610_065548/`. Compared against `agents.json` scanner output. Oracle written to `tests/fixtures/golden/oracle_talent.json`.

**Coverage:** 26 agents checked with high/medium confidence. Agents 030–038 (low-level, minimal investment) not included — scanner reads their trivial values (8/1/1/1/1) correctly per baseline images.

### Confirmed Scanner Bugs

| Bug | Trigger | True→Scanner | Affected |
|-----|---------|-------------|---------|
| **A** | Basic badge `07` reads as `1` | 7→1 | OrphieMagus basic, Ben basic |
| **B** | `03` dim-pass falls in 5-bucket | 3→5 | Jane assist, Caesar basic, Rina dodge |
| **B2** | `06` S-rank falls in 8-bucket (fill ≥ 0.70) | 6→8 | Rina basic |
| **C** | A-rank `13`/`14`/`15` (out of 16) misread as `10`–`12` | 13→12, 15→10 or 12 | Anby basic/special, Pulchra assist/special/chain, Lucy special, Anton basic/special/chain |

**Total:** 15 field mismatches across 9 agents. 15 agents fully correct.

### Root causes
- **Bug A:** `_read_skill_badge` crops to `left_w = 52%` of badge width. For the basic-attack badge specifically, the `0` prefix of `07` lands outside the crop at the observed calibration, leaving a single narrow `7` blob → pass-1 single-narrow-blob → 1.
- **Bug B/B2:** `_read_skill_badge` dim-pass buckets: `3` and `5` land in same fill range (≥0.55); `6` and `8` land in same fill range (≥0.70). No shape distinction within bucket.
- **Bug C:** Bright-pass (`>180`) classifies `1X` values using second-digit fill to split 10/11/12. For A-rank (max 16), true values `13`/`14`/`15` have second digits `3`/`4`/`5` whose fills match the 12/10/12 buckets respectively — indistinguishable from actual 10–12.

### Next steps
- **T6.2:** Add `test_oracle_talent.py` that replays `agents.json` against `oracle_talent.json` and asserts per-field.
- **T4.1:** Fix Bug A (crop width), Bug B (add 3-bucket), Bug B2 (use blob-count to distinguish 6 from 8), Bug C (detect A-rank denominator = 16, shift bucket by +3).

