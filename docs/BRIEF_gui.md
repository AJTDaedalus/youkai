# BRIEF — GUI integration for youkai-ocr scan-all (v0.1 frontend)

**Tier:** Brain (Fable) · 2026-06-11
**Downstream:** DESIGN_gui.md, TASKS_gui.md

## Problem statement

`youkai-ocr scan-all` (Python, CLI) is validated and produces a ZodExport JSON plus a
run-dir with phase caches, issues.json, and review.txt. The only frontend is the
terminal. A draft GUI exists — the egui "hacker console" in `youkai/` — but it is
wired entirely to the dead packet-sniffer backend (pktmon monitor, fake packet
counters, irminsul update checker, admin elevation, GameData download flow). None of
that drives anything real anymore.

Goal: the GUI becomes a thin, honest frontend over the Python scanner. User picks a
scan mode (discs-only vs full), presses one button, watches real progress, and gets
the export JSON to clipboard or file.

## Goals

1. GUI launches `youkai-ocr scan-all` as a child process and reflects its real
   progress (phase, item counts, issues) live.
2. Configurable scan mode persisted across sessions: **Full** (engines + discs +
   agents) or **Discs only**. Implemented generically (phase list) so per-phase
   toggles are free later.
3. Kill button terminates the scan cleanly; run dir remains resumable.
4. Export results to clipboard or file from the GUI.
5. Keep the existing hacker-console aesthetic (designs.md); re-skin the dead
   sniffer semantics to OCR-scan semantics. The theater (fake counters) becomes real.

## Non-goals (v0.1)

- No min-level/rarity export filters (the scanner doesn't filter; the old
  `ExportSettings` thresholds are sniffer-era leftovers — delete them).
- No in-GUI review/fix workflow for low-confidence items; surface counts and an
  "open review.txt / run dir" button only.
- ~~No PyInstaller single-exe distribution (stretch task only; dev-mode `python -m
  youkai_ocr` is acceptable for v0.1).~~ **AMENDED 2026-06-11 (D40):** portability is now
  a hard requirement — the tool must run from a portable folder on a machine with no dev
  Python env. Resolved as a PyInstaller **onedir** distribution with `tesseract` bundled
  as a sibling binary (not a single literal exe — tesseract is an external native binary
  PyInstaller can't absorb). See D40; tasks T13a–T13c. Dev-mode `python -m youkai_ocr`
  stays valid for WSL/dev.
- No resume-from-GUI UI beyond "the run dir is preserved" (CLI `--resume` still
  covers it).
- No GOOD-format export toggle, no localization.

## Approach selected

**Keep the Rust egui shell; drive the Python scanner as a subprocess speaking a
JSONL progress protocol over stdout.**

This amends **D38** (Rust app decommissioned): the `youkai/` crate returns to the
active build path **as a GUI shell only**. All packet-capture machinery
(`monitor.rs`, `capture.rs`, `wish.rs`, `update.rs`, `good.rs`, pcap/pktmon deps,
admin elevation) is deleted, not bypassed — dead code wired to a UI invites
confusion and bloats the build. `zod.rs` stays (schema reference per D38).

### Alternatives rejected

- **Rewrite the GUI in Python** (tkinter/DearPyGui/etc.): throws away a finished,
  polished console design (designs.md, working exe) to save one process boundary.
  The subprocess boundary is a *feature*: a scanner crash or hang cannot take the
  GUI down, and KILL is just process termination.
- **Embed Python via PyO3**: packaging pain (CPython + tesseract inside the exe),
  GIL vs egui thread model, no crash isolation, and pynput synthetic input from
  inside the GUI process complicates focus handling. All cost, no benefit.
- **Port the scanner to Rust**: months of re-validating OCR heuristics that took
  weeks to tune in Python. Not serious for v0.1.

### Key design decisions handed to Planner

1. **Process contract** — add to the Python CLI: `--porcelain` (JSONL events on
   stdout, human text diverted to the run-dir log; implies non-interactive: every
   `input()` prompt becomes a `warning` event + auto-continue) and `--phases
   engines,discs,agents` (subsumes `--agents-only`). The protocol is versioned
   (`"v": 1`). The CLI remains the single source of scan logic; the GUI never
   reimplements navigation or scanning.
2. **Real progress** — the three scanners get an optional `on_item(scanned, total)`
   callback (generalizing the existing `on_first_item`) so the GUI shows live
   counts, not animation theater.
3. **Occlusion hazard (critical)** — capture is screen-region based (dxcam): if the
   GUI window overlaps the game window, scanned frames contain GUI pixels. The GUI
   **must minimize itself when the scan starts** and restore when the child exits.
   This is a correctness requirement, not polish.
4. **Scanner discovery** — lookup order: configured override path → `youkai-ocr.exe`
   beside the GUI exe → `python -m youkai_ocr` from PATH. Persisted in app state.
5. **Admin elevation removed** — passive OCR + synthetic input needs no admin
   (the game client is not elevated). `ensure_admin()` and the "INTRUSION FAILURE"
   admin banner go away.

## Downstream robustness considerations

- The JSONL protocol decouples GUI and scanner release cadence; future frontends
  (web, tray app) reuse it unchanged. Keep events coarse and additive-only.
- `--phases` is the config surface for discs-only mode; the GUI radio maps onto it,
  so adding "engines only" or per-phase checkboxes later is zero protocol work.
- Discs-only nav path must end gracefully (no agent-phase navigation, no
  `resolve_locations` cross-ref — locations are only resolvable in full mode; the
  export simply has no disc `location` data in discs-only mode. Verify ZOD
  consumers accept that, they do today for `scan` output).
- Esc-to-abort (pynput global listener) keeps working independently of the GUI;
  KILL in the GUI is the second, harder stop (process kill). Both leave a
  resumable run dir.
- Anti-ban posture unchanged: same synthetic-input + screen-capture approach as the
  CLI; the GUI adds no new game-facing surface.

## Open questions for Planner

- Whether `phase_total` for discs/engines is knowable up front (count header gives
  N/M) — if yes, emit it in `phase_start` for a real progress fraction; agents
  phase may be count-unknown until ring-close (emit `total: null`).
- Child process kill on Windows: confirm `Child::kill()` suffices when launching
  `python.exe -m youkai_ocr` directly (no shell, no py launcher) — if a console
  host intermediates, kill the process tree.
- Stdout buffering through PyInstaller onefile (stretch task only).

**Resolved direction. Switch to Opus (Planner) was skipped at user request — DESIGN
and TASKS are drafted alongside this brief; Worker (Sonnet) executes from
TASKS_gui.md.**
