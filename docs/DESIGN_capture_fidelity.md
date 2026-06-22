# DESIGN — Capture Fidelity (true game-state extraction)

Source plan: `/root/.claude/plans/elegant-wobbling-river.md` (approved).
Goal: Youkai's eZOD export faithfully reflects each agent's true in-game state.
Some agents are *genuinely* partial — success is **fidelity to ground truth**,
not a fixed 6-disc count.

## Root causes (confirmed against `reference/youkai_export.json` + source)

1. **Partial builds = lossy linking.** Inventory scan reads all 2263 discs
   (`location:""`). `resolve_locations()` (`src/youkai_ocr/agent_scanner.py:919`)
   joins equipped→inventory by `set_key`+`slot_key`, **first-match-wins**
   (lines 939-943). Fails on set mis-read, non-unique set+slot (arbitrary disc /
   cross-agent collision), and inventory misses. Only 101/2263 discs +
   26/222 engines get a location → 4/39 full builds.
   The per-slot frames `equip_slot_N.png` are **full 1920×1080 disc-detail
   frames** already captured, but only `set`+`slot` is read from them.

2. **Empty substat key** (`disc_scanner.py:263`): name OCR fails both bright +
   dim native passes while value is present → `key:""`+value. Value reads vote
   over native + 2× upscale (255-258); name reads have **no upscale pass**.

3-4. Doc + talent semantics — fixed in `eZOD.md` (W5, done).

## Architecture decision: agent page is authoritative for equipped gear

Read the **full equipped disc/engine directly from the per-slot select-view
frame** (location correct by construction), then **reconcile** against the
inventory list by fingerprint. Rejected alternative: keep inventory-as-truth and
improve the join — still depends on two OCR passes agreeing and can't cleanly
resolve duplicate set+slot collisions. Direction chosen uses frames we already
capture (no extra navigation → no added anti-ban surface).

### Data flow (new)
```
inventory scan ─┐
                ├─► reconcile(by fingerprint) ─► discs[] (location stamped,
agent equip   ─┘     cross-validate fields,         fields cross-validated,
 per-slot read       append unmatched)              missed-equips appended)
```

Fingerprint = set + slot + main_stat + level + rarity + sorted top substats.
- match → keep inventory entry, `location = agent_key`, backfill empty/low-conf
  fields from the higher-confidence read (self-heals many `key:""`).
- no match → append the agent-page disc (inventory missed it). Never drop.
- one disc ↔ at most one agent.

## Components
- `disc_scanner.py`: extract panel-reading core to accept a panel origin/bbox set;
  add `scan_equipped_disc_frame(frame, calib, agent_key, slot)`. Calibrate
  select-view bbox from `reference/reference_9_equipment_disc_info.png`.
- `wengine_scanner.py`: `scan_equipped_engine_frame` (refs 6/19).
- `agent_scanner.py`: equip-slot loop emits full discs/engines; replace
  `resolve_locations` with fingerprint reconciliation (or relocate to cli).
- `cli.py:_cmd_scan_all` (~1210): wire reconciliation; roster-coverage check;
  surface orphans/coverage in `results.json` + summary.
- `disc_scanner.py` (~245-249) + `normalizer.py`: upscaled name pass + dict gaps.

## Testing strategy
- `tests/test_golden_replay.py` gate (≥99% name / ≥98% numeric) stays green.
- New per-agent-build oracle test from transcribed ground truth (~5-10 agents)
  under `tests/fixtures/golden/`; reuse `tools/make_golden_draft.py`.
- Offline replay of `archive/live_*` disc `panel.png` crops to measure empty-key
  count before/after W2.
- Live confirming run on alt account vs. oracle + roster coverage.

## Open questions (resolved with user)
- Live re-scans: available on demand (alt account).
- Ground truth: user transcribes ~5-10 agents.
- Partial agents are sometimes truthful → don't force 6 discs.
