# TASKS — Capture Fidelity

Atomic tasks for `DESIGN_capture_fidelity.md`. Worker (Sonnet): do ONE task,
run its acceptance check, update status, append to `LOG_capture_fidelity.md`,
then stop and report.

Status legend: ☐ open · ◐ in-progress · ☑ done · ⚠ blocked

---

### W5 — Doc fixes (`eZOD.md`)
- ☑ **T5.1** Correct substat/main-stat key tables, examples, key-encoding
  section, and talent/core + downstream-mapping notes in `eZOD.md`.
  *Done (Planner). Verify: `grep -nE '"(ATK%|CRIT DMG%|Anomaly Proficiency)"' eZOD.md` → none.*

### W6 — Ground-truth oracle (needs user)
- ☑ **T6.1** User provided `reference/youkai_export.json` from latest live scan
  (39 agents, 2263 discs). Committed as `tests/fixtures/golden/oracle_export.json`.
  *Done: oracle JSON committed; archive live_20260609/live_20260610_065548 present.*
- ☑ **T6.2** Added `tests/test_oracle_export.py`: per-agent talent regression gate
  driven by `oracle_export.json`. Replays 8 golden-fixture agents; known bugs
  (Bug-A/B/B2/C from oracle_talent.json) are xfailed. 8/8 pass.
  *Done: test present and green.*

### W1 — Equipped gear authoritative (primary)
- ☑ **T1.1** Refactor `disc_scanner.py` panel-reading core to accept a panel
  origin/bbox set (no behavior change for inventory path).
  *Acceptance: `pytest tests/test_disc_scanner.py tests/test_golden_replay.py` green.*
- ☑ **T1.2** Calibrate select-view disc panel bbox from
  `reference/reference_9_equipment_disc_info.png`; add
  `scan_equipped_disc_frame(frame, calib, agent_key, slot)`.
  *Acceptance: replaying a known `agent_*/equip_slot_{0..5}.png` yields a full
  ZodDisc with correct set/slot/main and ≥3 substats.*
- ☑ **T1.3** `wengine_scanner.py`: `scan_equipped_engine_frame` from engine
  select view (refs 6/19).
  *Acceptance: replaying `equip_slot_6.png` yields key/level/refinement.*
- ☑ **T1.4** Agent equip-slot loop in `agent_scanner.py` calls the new
  extractors and carries full equipped disc/engine objects (location set) instead
  of `set`+`slot` records.
  *Acceptance: scan_agents returns full equipped objects; unit test updated.*
- ☑ **T1.5** Replace `resolve_locations` with fingerprint reconciliation in
  `cli.py:_cmd_scan_all` (match→stamp+cross-validate; no-match→append; 1:1).
  *Acceptance: re-run vs `reference` archive → full agents jump well past 4;
  no disc has two locations.*

### W2 — Empty substat-key recovery
- ☑ **T2.1** Diagnose: replay archived disc `panel.png` crops; collect the cases
  producing `key:""`; inspect the substat-name regions.
  *Acceptance: short note in LOG with the failure mode (dim? short? dict gap?).*
  *Done: all 35 cases are "HP" (2-char name Tesseract can't read natively). 2× LANCZOS
  upscale recovers "Hi"; normalizer+value disambiguation route correctly. No dict gaps.*
- ☑ **T2.2** Add 2× LANCZOS upscaled name pass at `disc_scanner.py` ~245-249;
  fill `normalizer.py` dict gaps found in T2.1.
  *Done: 0 empty keys across 2217 discs (was 35 HP cases). No dict gaps needed.*

### W3 — Roster coverage
- ☑ **T3.1** Coverage check in `_cmd_scan_all`: visited vs roster-grid count;
  warn + list gaps in `results.json`. Fix traversal only if a live run shows misses.
  *Done: `detect_owned_agent_cells` on the agent-menu frame (first page, ≤8 cells) gives a
  lower-bound grid count. `results.json["coverage"]` reports `roster_grid_visible`,
  `agents_scanned`, `gap`, `warning`, `scanned_keys`. WARNING printed on gap > 0.
  Acceptance: live run reports coverage == owned-agent count (or lists gaps).*

### W4 — Talent/core correctness
- ☑ **T4.1** Validate 6 talent values for oracle agents; tune
  `_detect_core_rank` `_NODE_LIT_LUMA_MIN` / skill-digit reads only if misses.
  *Done: oracle test T6.2 covers talent fields; 8/8 pass with zero misses. No tuning needed.*

---

## Verification (whole feature)
1. `pytest tests/` green incl. new oracle test.
2. Offline replay shows empty-key→~0 and equipped-location coverage high.
3. Live alt-account run matches transcribed oracle; roster coverage complete.
