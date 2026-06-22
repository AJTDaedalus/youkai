# TASKS — Run Validation Fixes

See `DESIGN_run_validation_fixes.md`. Source of truth: `/root/fairy`. One task at a
time; stop and report after each.

Legend: [ ] open · [~] blocked · [x] done

---

## T1 — Regenerate engines.json from fairy (CRITICAL) [x]

**Done.** Landed together with T2 (see LOG). Q1 resolved (3 phantoms dropped).

**Files:** new `tools/gen_engines.py`; regenerate `data/zzz_1.4/engines.json`.

**Do:**
1. Write `tools/gen_engines.py`:
   - Read `source_name` + `rarity` from each
     `/root/fairy/backend/app/data/modifiers/w_engines/*.json`.
   - `key = to_zod_key(name)` with override `{"Roaring Fur-nace": "RoaringFurnace"}`.
   - Validate every key ∈ `references/zo-allStat_gen.json["wengine"]` OR in the
     `_NEWER_THAN_REF` allowlist (Frostfall Sickle, Neon Fantasies, Serpentine
     Seeker, Starlight Rider Faceplate, The Simmering Pot). Hard-error otherwise.
   - Emit grouped by rarity (S/A/B) with `_meta` + `_comment_*` sentinels, sorted.
2. Drop phantoms `Cannibal Grin`, `Door of Limitation`, `Final Curtain` (pending Q1).
   `Peacekeeper` is replaced by `Peacekeeper - Specialized`→`PeacekeeperSpecialized`
   automatically (it's in fairy).
3. Run generator; commit the regenerated engines.json.

**Acceptance:**
- engines.json has 89 non-comment entries; every key ∈ (zo-allStat keyset ∪
  5-newest allowlist).
- `RoaringFurnace` present; `RoaringFurNace` absent.
- `PeacekeeperSpecialized` present; bare `Peacekeeper` absent.
- 3 phantoms absent.
- `python -m pytest tests/test_wengine_scanner.py` passes.
- Generator re-run is idempotent (no diff on second run).

---

## T2 — Add unknown-engine confidence floor (hardening) [x]

**Done.** Floor = 80 (`_ENGINE_NAME_SCORE_MIN`). Callers reject empty key. Golden
label engine_0060→StarlightEngineReplica fixed; test_ref10_engine asserts None.
Full suite 495 passed. See LOG.

**Files:** `src/youkai_ocr/normalizer.py`, `src/youkai_ocr/wengine_scanner.py`,
`tests/test_wengine_scanner.py`.

**Do:**
1. Mirror `normalize_agent`: add `_ENGINE_NAME_SCORE_MIN`; in `normalize_engine`,
   return `("", score)` when best score < floor.
2. Confirm scanner's `_CRITICAL_NAME_THRESHOLD` path emits `unknown_engine` on
   empty key (it already gates `name_conf < 30.0`; verify empty-key handling).
3. Set the floor from observed golden scores — must be **below** the lowest
   legit known-engine score (bracket-series siblings score lower). Start ~80,
   tune against golden fixtures.

**Acceptance:**
- All golden engine fixtures still resolve to correct keys.
- A synthetic unknown name (e.g. `"Nonexistent Engine 9000"`) returns `("", <floor)`
  and the scanner records `unknown_engine`, not a wrong key.

---

## T3 — Investigate dim-badge skill misread (MEDIUM, investigation) [x]

**Done.** Labeled fill-ratio table + recommended fix in LOG (2026-06-16). Tool:
`tools/diag_skill_badges.py` → `docs/diag_skill_badges.csv`. Finding: fill-ratio
tiers are exhausted (3⊂5, 6⊂8, two-digit units overlap); basic slot renders digits
~16px narrower (Bug-A). Recommend per-digit template matching, not recalibration.
Escalated to Planner to spec impl (also covers Bug-C A-rank 13/14/15). Impl is a
gated follow-up — not done here.

**Do not change thresholds blind.** (See `gui_layout_fragile` lesson — don't ship
heuristic changes you can't verify.)

**Files:** `src/youkai_ocr/agent_scanner.py` (`_read_skill_badge`), debug crop dump.

**Do:**
1. Re-run affected agents (Billy, Corin, Piper, Manato; asc-0 Harumasa, Lycaon)
   with badge-crop debug dump enabled.
2. Tabulate measured `b1_fill` for ground-truth 1, 5, 8.
3. Investigate the asc-0 basic=8/others=1 split (lit basic-attack badge styling).
4. Decide recalibrate-tiers vs per-digit template match. **Append findings to
   `LOG_run_validation_fixes.md`; escalate to a design decision before implementing.**

**Acceptance:** labeled fill-ratio table + a recommended fix in the LOG. (Impl is a
follow-up task gated on that decision.)

---

## T6 — Robust bottom-nav targeting (OCR-located buttons + retry) [x]

**Why now:** blocks the glyph-sourcing capture (T7) and all live scans. Root cause
proven (Planner, 2026-06-17): `navigate_to_storage`/`navigate_to_agents` click
hard-coded coords (`_NAV_STORAGE_CENTER 1178,1041` / `_NAV_AGENTS_CENTER 1274,1041`).
Against real `archive/diag_nav/*/nav_pre_storage.png` frames, the **Agents** target is
**33px stale** (detected label center 1307 vs hard-coded 1274); Storage is dx=1. The
bottom nav drifts when items are inserted (1.5 added Achievements → already
re-measured twice) and a single missed click hard-fails (no retry, unlike
`switch_storage_tab`).

**Approach (verified against real frames):** OCR the bottom-nav label strip and click
the *detected* "Storage"/"Agents" word center; retry-until-confirmed.
- Locator: crop band `(900,1015,1400,1062)` game-coords → 3× cubic upscale → threshold
  ~90 → `pytesseract.image_to_data --psm 11`; match word == "storage"/"agents"
  (fuzzy, len≥5); return center mapped back to ref coords. (Prototype in this session
  read `"Achievements Inter-Knot Storage Agents"` cleanly and located both.)
- Put band/threshold in `navigation.yaml` under `agent_menu.bottom_nav` (keep the
  existing hard-coded centers as a fallback when OCR finds nothing).
- `navigate_to_storage`/`navigate_to_agents`: locate → click detected center (fallback
  to constant) → `wait_for` signature, **re-locate+re-click every ~3s** until confirmed
  or timeout (mirror `switch_storage_tab`'s retry loop).

**Files:** `src/youkai_ocr/cli.py` (NavDriver), `data/zzz_1.4/navigation.yaml`,
new `tests/test_nav_locate.py`.

**Acceptance:**
- A `locate_bottom_nav_button(frame, calib, "agents")` returns a center within ~8px of
  the OCR-measured label center on both archived `nav_pre_storage.png` frames (offline,
  no live game) — i.e. tracks the real position, not the stale 1274.
- Returns `None`/fallback gracefully on a non-main-menu frame.
- Retry loop re-clicks on a simulated dropped first click.

---

## T7 — Build complete 0–9 badge-glyph reference set [x]

Depends on T6 (need a working capture). Source: oracle blobs for 0–8 + **fresh
capture** of the user's level-9 agent and 13–16 agent for the missing 9 and extra 4/6
(see `DECISIONS.md` D1).
- Reuse blob extraction from `tools/diag_skill_badges.py`: for each labeled
  agent+skill, extract the units-digit blob (b1), crop to its bbox, normalize to a fixed
  box (e.g. 24×36), tag with truth digit.
- Capture the two new agents' `skills.png` (1920×1080), hand-label per-skill levels,
  extract their units blobs → fills 9, 13→3, 14→4, 15→5, 16→6.
- Emit `tests/fixtures/badge_glyphs.json` (or a templates dir): per-digit 0–9, ≥2
  samples each (averaged or kept multi-sample for nearest-correlation).

**Acceptance:** reference set has all 10 digits 0–9 with ≥2 samples each; build is
reproducible from a script (`tools/build_badge_glyphs.py`).

---

## T8 — Rewrite `_read_skill_badge` to template-match the units digit [x]

Depends on T7. Replace ONLY the b1 units-digit classification (the bright-pass
`10/12` fill split AND the entire dim-pass wide/narrow fill-tier block) with
normalized-correlation matching against the T7 reference glyphs. Keep b0/tens logic
(single blob→1; b0 narrow→leading "1"; b0 wide+round→"0"-prefix). Below-floor
correlation → low-confidence (<70) flagged read (never silent-wrong). See `DECISIONS.md`
D1, `DESIGN…md` Issue 2 resolution.

**Acceptance:** Bug-A/B/B2/C all fixed; `_BADGE_HIGH/MID_FILL/THIN_FILL` tier constants
removed; existing badge tests pass.

---

## T9 — Validate badge reader (leave-one-agent-out + regression) [x]

Depends on T8. LOO cross-val harness (build templates from all-but-one oracle agent,
classify held-out) proving generalization, not memorization; fresh-capture agents as a
fully held-out 9/13–16 set. Extend `tools/diag_skill_badges.py` or new
`tools/eval_badge_reader.py`.

**Acceptance:** LOO accuracy reported per digit; the 7 T3-documented MISS badges
(03→5, 06→8, basic-7→1, 13/14/15) now read correctly; no regression on golden agent
tests.

---

## T4 — Document Issue 3 (LOW, no code) [x]

**Done.** Note added to `eZOD.md` after the `ZodSubstat` field table — explains that
low-confidence flags on flat/% substats are expected (genuine numerical ambiguity, not
data corruption). No code change.

---

## T5 — Harden agent path against below-floor empty keys (hardening) [x]

**Done.** Symmetric counterpart to T2. `normalize_agent` already floors a junk name
to `("", <real score>)` (`_AGENT_NAME_SCORE_MIN = 85`), but a sub-floor score in the
30–84 band sailed past the `< _CRITICAL_CONF` (30) gate — so a junk name could build a
`ZodAgent` with `key=""`. Both gate sites now reject the empty key, not just a low score.

**Files:** `src/youkai_ocr/agent_scanner.py` (`scan_agents` ~L1595,
`scan_single_frame_agent` ~L1679), `tests/test_agent_scanner.py`.

**Do:**
1. `scan_agents`: gate `if not key or base_conf["key"] < _CRITICAL_CONF` → critical_fail.
2. `scan_single_frame_agent`: same gate → return `(None, conf)`.
3. Ring-close caller (`_ring_close_key`, ~L1227) needs no change — an empty key already
   declines to close the ring and falls back to AGENT_MAX (safe).
4. Tests: `test_scan_agents_empty_key_below_floor_is_critical_fail`,
   `test_scan_single_frame_agent_empty_key_below_floor_returns_none` (empty key + score 50).

**Acceptance:** both gate sites reject `key=""` even when the score > 30; no agent is
emitted, slot flagged critical_fail. `pytest tests/test_agent_scanner.py` passes (43).
