# DESIGN — Agent Roster Scan + Tandem Full-Scan (Phase H)

**Author:** Opus 4.8 · **Date:** 2026-06-06 · **Branch:** `feature/ocr`
**Supersedes the agent portions of:** `DESIGN_ocr.md` (E1–E4), the G3 task notes.
**Inputs read:** `agent_scanner.py`, `cli.py:_cmd_scan_all`, `navigation.yaml:agent_roster`,
`grid.py` (scroll/stability pattern), live archive `archive/live_20260605/agent_00{0,1,2}/`,
reference frames `reference_{3,4,7,8,9,10}`.

---

## 1. Problem statement

The agent scanner is the only subsystem blocking a clean `scan-all`. Discs (2210, exact) and
engines (222, exact) are solid. Agents stalled at **3 captured of ~8+ visible** on the last live
run, and — newly discovered this session — **the Equipment tab was never actually reached**, so
the location cross-reference (the entire purpose of the tandem scan) has never run on real data.

## 2. Root causes (evidence-backed this session)

Three independent, compounding defects. All were authored from assumption and never verified
against the reference frames that already exist in the repo.

### RC-1 — Roster under-detection: the strip y-band is too low
`_ROSTER_STRIP_BBOX = (0, 32, 1920, 75)`. In `reference_3_agent_page.png` the portrait strip sits
at the **very top** (portraits ≈ y=8–42 ref, packed edge-to-edge in x≈1100–1905). The y=32–75
band catches mostly the dark gutter *below* the portraits, so only the brightest few portraits
push their column-mean over `_PORTRAIT_BRIGHTNESS=80` → **3 of ~8 detected**. The G3 note itself
records the contradiction (Opus "y≈2–28" vs G3 "y=33–70") and it was never pinned down. The
merge-gap collapsing of adjacent packed portraits compounds it.

### RC-2 — Roster never scrolls (architectural)
`AgentNavigator.scan()` captures **one** frame, calls `_find_agent_portraits()` **once**, iterates
those x-centers, stops. Unlike discs/engines there is **no `[N/M]` count header**, so count-driven
traversal does not transfer. The strip is a **horizontal** scrolling list; whatever is in frame 1
is the entire universe the scanner sees. A full owned roster (often 30–40+) is unreachable.

### RC-3 — Equipment tab never reached + slot geometry ~350px off  ← **new, decisive**
The live `equip_slot_*.png` frames are **Skills-tab captures**, not Equipment. Proof: in
`agent_000/equip_slot_0.png` the bottom tab bar still has **Skills** highlighted and the A–F core
nodes are on screen; `equip_slot_6.png` is the Skills-tab **"Core Skill Enhancement"** popup. So
the `_TAB_EQUIPMENT=(1718,996)` click did not activate Equipment, and the subsequent slot-center
clicks landed on the Skills-tab core nodes / skill icons (opening core-skill popups).

Independently, the slot centers are wrong even on a correct Equipment tab. From
`reference_7_agent_equipment.png` the slot hexagon is centered at **ref x≈1410** (engine slot
center ≈ **(1418, 590)**), with six disc slots ringing it. The code uses x≈870–1185 / engine
(1038, 515) — **~350px too far left**. `navigation.yaml` literally carries
`# TODO: refine slot centers from ref_7 during B1`; it was never done. Even a fixed tab click would
mis-click every slot.

**Meta-cause:** no navigation step verified it landed. A render-gate on the Equipment tab (mirror
of G1's disc render-gate) would have turned this silent wrong-screen capture into a loud failure.

## 3. Goals / Non-goals

**Goals**
- G-A: Detect **all** visible roster portraits per frame (fix RC-1).
- G-B: Traverse the **whole owned roster** — scroll-until-stable + dedupe, no count header (fix RC-2).
- G-C: Actually reach the Equipment tab and click the **correct** slot centers; verify both with a
  render-gate (fix RC-3).
- G-D: **Validate** per-agent field extraction (name/level/ascension/mindscape/skills/core/equip)
  offline against `reference_{3,4,9,10}` before any live run; commit fixtures.
- G-E: Harden the tandem run: persist log + per-phase counts + results to the archive; per-phase
  preflight screen-assertion; resume semantics.
- Acceptance: one clean `scan-all` end-to-end producing a single merged `ZodExport` with disc/engine
  `location` fields populated from a correct agent pass.

**Non-goals**
- Re-touching discs/engines (G1/G2/G5 are solid — do not re-litigate).
- ~~Auto-navigation between the three top-level menus.~~ **Reopened 2026-06-06 (D26):** with
  `reference_11` (main-menu hub: `Storage`/`Agents` buttons) + `reference_12` (agent menu: `Base`),
  and the universal back-arrow, full menu auto-nav is now in scope as task **H7**. Storage is a
  single screen — engine↔disc is one category-tab click (ref_1/ref_2), and the active tab's
  yellow→green pulse-glow doubles as a render-gate. Manual `input()` gates downgrade to a fallback.
- Stat-grid extraction beyond ZOD requirements (the 5×2 stats grid is captured but ZOD only needs
  key/level/ascension/mindscape/talents — leave richer stats out of scope).

## 4. Approach

### 4.1 Roster traversal (RC-1 + RC-2)
Replace "detect once" with **detect-page → act → scroll → repeat until stable**:

1. **Re-measure the strip** from `reference_3`: raise the band to ≈ `(_x_min, 6, 1920, 44)`,
   set `click_y≈25`. Re-tune `_PORTRAIT_BRIGHTNESS` / `_MIN_PORTRAIT_WIDTH` / `_PORTRAIT_MERGE_GAP`
   so all packed portraits separate (validate count against the visible strip in `reference_3`).
2. **Per-page detect** all portrait x-centers in the current strip frame.
3. **Dedupe** by a perceptual hash (pHash/aHash) of each portrait thumbnail crop, kept in a
   `seen` set — so re-scrolled/overlapping portraits are not re-visited. Agent-key repetition
   (read from Base Stats) is a **secondary** end-of-roster signal.
4. **Scroll** the strip horizontally by a fixed stride (mechanism TBD by the live probe in H0 —
   candidate: drag on the strip, or click the rightmost partially-visible portrait to advance, or
   wheel-over-strip). After scroll+settle, recapture.
5. **End-of-roster** when the strip frame-hash is stable across the scroll (reuse the
   `grid.py` `_scrollbar_thumb_top` / cumulative-stability idea, adapted to a strip-region hash),
   **or** no new (un-seen) portraits appear for one scroll, **or** an agent key repeats. Hard cap
   `AGENT_MAX = 60` mirrors `SCAN_MAX_ROWS`.

The scroll mechanism is the one genuinely unknown; **H0 is a tiny live probe** to settle it before
building the loop (do not guess — it bit us on slot geometry already).

### 4.2 Per-agent capture with render-gates (RC-3)
For each new portrait: click → **Base Stats** (gate: assert active) → capture; **Skills** (gate) →
capture; **Equipment** (gate: assert the hexagon rendered, e.g. mean-luma / template of the center
engine ring) → for each of the 7 **re-measured** slot centers: click → gate (assert the
detail/select panel opened) → capture. A gate failure re-captures up to a short timeout, then logs
a per-step issue instead of silently banking the wrong frame.

Slot geometry re-measured from `reference_7` (engine center ≈ (1418,590); six disc centers ring it
— derive exact centers in H3). Equipment slot click opens the **disc-select** view
(`reference_8`) with the equipped disc's `SetName [N]` title in the panel — parse that (already the
intended `_EQUIP_TITLE_BBOX` path; re-anchor against ref_8/9/10).

### 4.3 Extraction validation (G-D)
Build offline fixtures from `reference_{3,4,9,10}` (mirror the G5 disc-slot fixture pattern) and
assert: agent key (Zhao), level (60), ascension dots, mindscape, the five skill levels
(ref_4 shows 12/10/11/12/11), core rank, and equip title→set/slot + engine key. Fix bboxes/heuristics
to pass. `scan_single_frame_agent()` already exists as the offline entry point.

### 4.4 Tandem hardening (G-E)
- **Persistence:** write `archive/<run>/scan.log` (tee of stdout) + `archive/<run>/results.json`
  (per-phase counts, issues, and the merged export) so runs are auditable from disk. This run's data
  loss (no stdout saved) must not recur.
- **Preflight assert:** each phase verifies the expected screen is open (disc header / engine header /
  agent page signature) before scanning; abort that phase loudly if not.
- **Resume:** per-phase outputs let a failed agent phase re-run without re-scanning 2210 discs
  (load discs/engines from their phase JSON, run agents, then `resolve_locations`).

## 5. Testing strategy
- Offline unit/fixture tests (no synthetic input): portrait detection count on `reference_3`;
  field extraction on `reference_{3,4,9,10}`; `resolve_locations` matching with synthetic discs.
- Dry-run harness: feed archived frames through the navigator's *detection* path (not clicking) to
  assert dedupe + end-detection logic.
- Live acceptance: one `scan-all` reading the full roster, Equipment tab confirmed reached
  (hexagon-rendered gate passes), ≥1 disc and ≥1 engine receive a `location`.

## 6. Open questions
- **OQ-H1 (live):** strip scroll mechanism + stride (H0 probe).
- **OQ-H2 (live):** does clicking an equipped slot open the swap/select screen (ref_8) directly, and
  is the equipped disc's title always present there? (re-anchor titles in H3.)
- **OQ-H3:** ascension-dots and core-rank remain heuristics; ref frames may not cover all states —
  flag low-confidence and route to the F3 review report rather than trusting them.

## 7. Risks
- Window-targeting bug (LOG: `live_20260606` grabbed the Game Pass launcher) must be fixed before any
  live H run, else H0/H6 capture garbage. Treat as a precondition.
- Anti-ban invariants unchanged (`CLAUDE.md`): external-only, synthetic mouse input, no memory/asset
  access, Esc kill-switch.

---

## H18 — Live feedback round 2 (slot-drop, advance-skip, empty slots, trial agents)

**Status:** issues #1 (slot drop) and #2 (advance skip) FIXED + tested this session; the reactive net
for #4 (no live hang) shipped. Issues #3 (empty-slot tracking) and proactive #4 (trial-skip) are
DESIGNED below but DEFERRED pending live reference frames — calibrating their thresholds blind would
repeat the RC-3 slot-geometry mistake. See LOG H18 and DECISIONS D32 for the shipped fixes.

### Deferred design — #3 empty-slot detection (needs a Koleda equipment frame)

Goal: classify each of the 7 hexagon slots as equipped vs empty **on the Equipment-tab frame, BEFORE
clicking**, so empty slots are neither clicked (no wasted re-click budget) nor cross-referenced (clicking
an empty slot surfaces the first *inventory* disc → today that disc is falsely assigned this agent's
location — the actual data-corruption bug).

Approach (to calibrate against Koleda):
- Per disc slot: crop a tight window at each `_DISC_SLOT_CENTERS[i]`. An EQUIPPED disc is a colourful
  gem icon with a "Lv. N/N" label; an EMPTY slot is a plain slot number on a near-uniform background.
  Candidate signal: saturation/edge-density inside the slot ring (equipped = high; empty = low), or
  presence of the "Lv." label strip below the slot. Pick whichever separates cleanly on Koleda vs ref_7.
- Engine slot: EMPTY shows the animated colour-shifting "core available" icon (high saturation, but a
  distinct shape) vs an equipped engine render. The "reads dark" H3 note refers to the gate window, not
  the whole slot — re-measure on Koleda.
- Wire-up: `_read_equipment` computes an `equipped[7]` mask from `equip_frame`; `_open_slot` is called
  only for equipped slots; `scan_agents` skips `_extract_equip_frame` for empty slots. ZOD needs no
  "empty" record (a disc/engine simply keeps `location=""`).
- Tests: a Koleda fixture asserting the mask is all-empty (or the real partial mask); a fully-equipped
  fixture (ref_7) asserting all-equipped; a `_read_equipment` test asserting empty slots are not clicked
  and produce no equip records.

### Deferred design — proactive #4 trial/preview-agent skip (needs a Nangong Yu frame)

The shipped reactive net (`_EQUIP_UNAVAILABLE`) removes the hang but still scans the trial agent's
Base/Skills (preset, not the user's) before discovering it at the Equipment step. A proactive skip in
`_is_owned_agent` (or a sibling predicate) would avoid that, but the discriminator is unknown:
trial agents are full-colour (the H15 blue-duotone test misses them) and the dark-engine signal
collides with Koleda's empty engine. Need a Nangong Yu detail-page + the preview-modal capture to find
a reliable signal (likely a "Trial"/"Preview" badge region, or the modal's fixed text bbox).

### Open questions
- **OQ-H18a — ANSWERED (reference_17 Koleda).** Empty disc = dark center (luma≈32 vs ≥120 equipped) →
  threshold 80. Empty engine = "core available" glow = colored_frac>0.15 AND luma<150. Also exposed the
  reversed slot numbering (slot# = 6 - idx). Implemented in H18.3 / H18.6.
- **OQ-H18b (live frame):** Nangong Yu detail page + "not available in preview mode" modal — is there a
  stable on-page trial/preview marker to skip proactively? (calibrate #4)
- **OQ-H18c:** thresholds `_AGENT_CHANGE_MIN_BITS`/`_AGENT_RING_CLOSE_MAX = 15` and
  `_SLOT_CHANGE_MIN_BITS = 8` are reasoned, not live-measured — confirm on the next live pass via the
  `nav_*`/`slot_reclick`/`agent_skip_trial` log lines and tune if needed.

## H19 — Live feedback round 3 (slot switch-detection misfires)

**Status:** FIXED + tested this session. See LOG H19 and DECISIONS D34.

**Reported (post-H18):** "disc 2 still skipped sometimes," "errors from having to click repeatedly,"
new "hangs oddly on disc 4." All three are the H18 slot-open gate, which keyed on the disc TITLE region.

**Root cause.** The TITLE is a bad switch signal: two adjacent slots holding the SAME disc set (4-piece
sets are the norm) have near-identical titles → the switch is never detected → futile re-clicking
(`slot_gate_fail` ≈ the disc-4 "hang" + the "clicking repeatedly" noise); and a half-faded title
false-positives → a duplicate of the previous slot is banked → the real disc reads "skipped." Separately,
empty-detection sampled the Equipment frame before the hexagon icons faded in → an equipped slot read
dark → mis-skipped.

**Fix.** Gate the switch on the panel BODY (`_SLOT_DETAIL_BBOX` — main stat + substats DIFFER between two
discs of one set, ref_8) AND require it STABLE across two captures before banking; settle the Equipment
frame (`_wait_region_stable` on `_EQUIP_RING_BBOX`) before empty-detection. `_open_slot` returns
`(frame, body_pHash)`. Verified against ref_7/8/16/17 (the hexagon ring stays clickable in the
disc-select view; the center body is the discriminating region).

### Open questions
- **OQ-H19a (live):** `_SLOT_STABLE_MAX_BITS=6` / `_SLOT_CHANGE_MIN_BITS=8` (body) and
  `_EQUIP_STABLE_MAX_BITS=12` (ring) are reasoned, not live-measured. Confirm on the next pass:
  `slot_reclick` should fire ONLY on genuine dropped clicks, `slot_gate_fail` should be rare. If a
  same-set agent still re-clicks, the body signal is too weak → bias `_SLOT_DETAIL_BBOX` toward the
  substat rows or lower `_SLOT_CHANGE_MIN_BITS`.

## H21 — Closed-loop per-slot validation (engine never captured; occasional disc skips)

**Status:** ROOT-CAUSED + planned this session (Opus). Engine cause PROVEN by measurement (see D36 table).
Disc cause not reproduced in the 5-agent live run (all 6/6 captured). Fix DESIGNED below; the robust version
is BLOCKED on two "clicked-an-empty-slot" reference frames.

### Symptoms (live 2026-06-08, `--agents-only --debug-overlays`, 5 agents)
- **Engine never captured** (1/5): deterministic-ish. `equip_slot_6.png` stale for 4/5 agents.
- **Discs occasionally skipped**: not seen this run (5/5 agents got 6/6), so timing/animation residue or the
  H19 switch-detect banking a duplicate — kept in scope but lower priority than the engine.

### Why this is NOT "missing clicks" (answers the user's question)
The navigator already runs a click→confirm→re-click loop on every navigation step: `_capture_tab` (pill +
content gate, re-click every N polls), `_open_slot` (panel-rendered + body-switch + 2-capture-stable, re-click
on dropped), `_advance` (character-render pHash, retry), `_enter_detail_page` (yellow-tab gate, re-click).
The engine is **not** a dropped click — it is a **deliberate skip**: `_engine_slot_equipped` returns False
(false-empty) before any click fires, and the loop writes `frames.append(None)`. The gate the user is asking
for exists; what's wrong is the *signal one gate trusts* (pre-click overview pixels) and the *place* the
equipped/empty decision is made (before the click, where the signal is weakest).

### Approach — invert the equipped/empty decision to POST-CLICK content (D36)
Per slot, in order, advance only when the slot is *resolved*:
1. Click the slot center.
2. Gate: `_slot_panel_rendered` (panel opened) — re-click on drop (unchanged from H19).
3. **Resolve by content**, not by overview pixels: read the center detail pane (`_EQUIP_TITLE_BBOX` +
   `_EQUIP_LEVEL_BBOX`). Equipped ⇒ title + `Lv. N/N` parse ≥ `_EQUIP_CONF_MIN` (ref_8/9/10). Empty ⇒ no
   parse → no record, `location=""`. This is the per-item "task complete" gate.
4. Bank frame + emit record iff equipped. Then advance to the next slot.

Retire `_engine_slot_equipped` / `_disc_slot_equipped` as *gates* (keep at most as a cheap hint). The
Equipment-tab render-gate (`_equip_tab_rendered`, D35) stays — it guards the trial/preview hang and is a
different concern from per-slot empty.

### BLOCKER — the missing reference (do not guess; this is the RC-3 / D35 lesson)
We have the *equipped* selection screen (ref_8/9/10) but **no frame of clicking a genuinely EMPTY slot**.
ref_6 is the W-Engine Storage inventory, not an agent empty-slot click. Open risk (H18 corruption bug):
clicking an empty slot might auto-select the first inventory item and render its title center → false
location. **Required input:** on Koleda (fully unequipped, ref_17) capture (a) click an empty disc slot, and
(b) click the empty engine; save both. Then the post-click empty signal (blank center vs auto-populated) is
calibratable offline against ref_8 (equipped) vs the new frames (empty), and the gate is safe.

### Diagnostics gap (must fix to debug live at all)
`scan.log` tees stdout only; `_log.*` markers (slot_empty/slot_reclick/tab_gate_fail) never land there — the
live run shows 0 of each despite 4 engine skips. Add a `logging.FileHandler` into the run dir so the next
live pass is self-diagnosing.

### Open questions
- **OQ-H21a — ANSWERED (ref_18/19).** Clicking an empty slot AUTO-SELECTS inventory[0] and renders its full
  detail center (ref_18 "Shockstar Disco [1]", ref_19 "Hellfire Gears") — so title/level parse is NOT a valid
  equipped signal (H18 corruption confirmed). Discriminator is the bottom ACTION-BAR: `"unequip"` present →
  equipped, else empty. Verified with the recognizer (see D36 UPDATE). Per-slot loop step 3 changes from
  "parse center" to "OCR action-bar → equipped?"; only if equipped do we parse the center for the record.
- **OQ-H21b (live, low risk):** we have an EMPTY-engine select frame (ref_19) but not an EQUIPPED-engine one —
  confirm the engine "Unequip" button position live so the action-bar bbox spans it (it already covers the
  disc "Unequip All" x≈1140–1310; widen right to ~x1520 for the engine).
