# DESIGN — GUI ↔ scanner integration (feature: gui)

**Inputs:** BRIEF_gui.md · Existing code: `src/youkai_ocr/cli.py` (scan-all),
`youkai/src/ui/app.rs` (egui console), `youkai/src/main.rs`.

## Architecture

```
┌─────────────────────────────┐        spawn + pipe stdout
│ youkai.exe (Rust egui GUI)  │ ───────────────────────────────┐
│  ui/app.rs   — console UI   │                                ▼
│  scan.rs     — ScanRunner   │   ┌────────────────────────────────────┐
│   • spawn child             │   │ python -m youkai_ocr scan-all      │
│   • read JSONL events       │◀──│   --porcelain --phases …           │
│   • watch::Sender<AppState> │   │ stdout: JSONL events (v1)          │
│   • kill()                  │   │ human log → run_dir/scan.log       │
└─────────────────────────────┘   └────────────────────────────────────┘
```

The GUI never scans, never touches the game window, and never parses scan.log.
All state it displays comes from the JSONL stream plus the files the scanner
writes (`results.json`, export JSON, `review.txt`).

## 1. JSONL progress protocol (v1)

One JSON object per line on **stdout**, only when `--porcelain` is passed.
All other prints in porcelain mode go to the `_Tee` log file and **stderr**
(stderr is advisory; the GUI shows the last stderr line on failure).

| event | fields |
|---|---|
| `run_start` | `v:1, run_dir, output, phases:[…]` |
| `phase_start` | `phase` ("engines"\|"discs"\|"agents"), `total` (int or null) |
| `progress` | `phase, scanned` (int), `total` (int or null) |
| `phase_done` | `phase, count, issues, elapsed, resumed:bool` |
| `warning` | `message` (replaces every interactive `input()` prompt) |
| `done` | `output, run_dir, summary:{agents,discs,engines,issues}, review_path?` |
| `error` | `message` (emitted before nonzero exit) |

Rules: additive-only evolution; unknown fields/events must be ignored by the GUI;
exactly one terminal event (`done` or `error`); every line flushed immediately.

## 2. Python CLI changes (`src/youkai_ocr/`)

### 2a. `--phases` (scan-all)
- `--phases engines,discs,agents` (default: all three). Validates names; order is
  fixed by the nav flow regardless of argument order.
- `--agents-only` becomes a deprecated alias for `--phases agents`.
- Auto-nav flow generalizes: storage visit happens iff engines or discs selected;
  `return_to_main` + agent nav happen iff agents selected; `resolve_locations`
  runs iff agents AND discs both selected. Discs-only therefore: main-menu assert →
  storage → disc tab → scan → done (no agent nav).
- Manual-nav path gets the same gating.

### 2b. `--porcelain` (scan-all)
- New module `src/youkai_ocr/progress.py`: a `ProgressEmitter` with methods
  mirroring the event table; writes JSON lines to the real stdout, flush per line.
  A `NullEmitter` no-ops for non-porcelain runs.
- In porcelain mode, `_Tee` redirects human prints to the log file ONLY (plus
  stderr mirror), keeping stdout pure JSONL. Implementation: construct `_Tee`
  against stderr instead of stdout for the mirror leg.
- Porcelain implies non-interactive: `_make_first_item_check` and
  `_preflight_frame` must not call `input()`. Policy: emit `warning` and continue,
  EXCEPT the existing hard-abort cases (black frame, size change, color hygiene)
  which stay hard errors → `error` event + exit 1.
- `ScreenAssertError` and any uncaught exception in scan-all emit `error` before
  exiting (wrap `_cmd_scan_all` call site).

### 2c. Per-item progress callbacks
- `scan_discs`, `scan_engines`, `scan_agents` accept optional
  `on_item(scanned: int, total: int | None)`; called once per processed
  cell/agent. Total for discs/engines comes from the already-read `[N / M]` count
  header (pass N once known; null before). Agents: total unknown → null.
- cli.py wires `on_item` → `emitter.progress(phase, …)`, throttled to ≥1 per item
  (items are seconds apart; no rate limiting needed).

## 3. Rust GUI changes (`youkai/`)

### 3a. Deletions
- Modules: `monitor.rs`, `capture.rs`, `wish.rs`, `update.rs`, `good.rs`,
  `player_data.rs` (ExportSettings dies with it). Keep `zod.rs` (reference, may
  stay unused — `#[allow(dead_code)]` or leave out of module tree).
- `ui/admin.rs` elevation + the admin warning banner; `--no-admin`,
  `--capture-all-udp` args; update/download `State` variants; tokio runtime if no
  longer needed (ScanRunner uses plain `std::thread` + `std::process`).
- Fake telemetry counter block (app.rs lines ~370–382) and the wish/update flows.
- Cargo.toml: drop pcap/pktmon/protocol/tokio/reqwest-class deps no longer used
  (verify with `cargo build`); keep egui stack, serde, chrono, egui_file_dialog,
  egui_notify, open.

### 3b. New state model (`main.rs` or `state.rs`)
```rust
enum ScanPhase { Engines, Discs, Agents }
enum ScanState {
    Idle,
    Running { phase: Option<ScanPhase>, scanned: u32, total: Option<u32>,
              counts: PhaseCounts /* per-phase done counts+issues */ },
    Done    { summary: Summary, output: PathBuf, run_dir: PathBuf,
              review_path: Option<PathBuf> },
    Failed  { message: String, run_dir: Option<PathBuf> },
}
struct ScanConfig { mode: ScanMode /* Full | DiscsOnly */, output: PathBuf,
                    scanner_override: Option<PathBuf>, debug_overlays: bool }
```
`SavedAppState` v2 persists `ScanConfig`. Old persisted blobs fail to deserialize →
`unwrap_or_default()` already handles that (acceptable: settings reset once).

### 3c. `scan.rs` — ScanRunner
- `start(config) -> ScanHandle`: resolves scanner command (override →
  `youkai-ocr.exe` beside current_exe → `["python", "-m", "youkai_ocr"]`), builds
  args (`scan-all --porcelain --output … [--phases discs] [--debug-overlays]`),
  spawns with `Stdio::piped()` for stdout+stderr, `CREATE_NO_WINDOW` on Windows.
- Reader thread: line-buffered read of stdout, `serde_json::from_str` into a
  `#[serde(tag="event")]` enum (unknown events → ignored via fallback variant),
  fold into `ScanState`, publish via `watch::channel` (or
  `std::sync::mpsc` + `ctx.request_repaint`).
- Stderr thread: ring-buffer last ~50 lines for the Failed view.
- `kill()`: `Child::kill()` (direct python.exe child — no shell wrapper, so no
  orphan tree; verify in T11, fall back to `taskkill /T /F` if needed).
  On exit-without-terminal-event → `Failed { "scanner exited unexpectedly …" }`.

### 3d. UI rework (`ui/app.rs`)
Keep layout, palette, typography. Semantic re-skin:
- **Left column:** `TUNNEL STATUS` → `SCAN STATUS : [IDLE|SCANNING|COMPLETE|FAILED]`;
  `TARGET : [ ZZZ CLIENT WINDOW // OPTICAL SIPHON ]`. Stat rows become real:
  `W-Engine Cores`, `Drive Discs`, `Agent Files` with live `scanned/total` from
  events. Progress bar = real fraction when total known, else activity sweep.
  Waveform animates only while `Running`. Button: `EXECUTE EXTRACTION SCRIPT` ↔
  `KILL EXTRACTION SCRIPT` (kill → confirm-free; run dir persists).
  Dialogue text instructs the real precondition: *game windowed, on the Inter-Knot
  main hub, unobscured, no Night-Light*.
- **Right column (parameters box):** radio `FULL SIPHON (agents+discs+engines)` /
  `DISC PARTITIONS ONLY`; output path row (egui_file_dialog); `debug overlays`
  checkbox; after Done: `COPY CLIPBOARD` (reads output file → clipboard),
  `EXPORT FILE` (copy output file to picked path), `OPEN RUN DIR`,
  `REVIEW REPORT (N issues)` (opens review.txt via `open` crate) — only shown when
  issues > 0. Configuration modal: scanner command override path + a "locate"
  file picker. Delete the min-level DragValue grids.
- **Occlusion guard:** on `start()` success send
  `ViewportCommand::Minimized(true)`; on terminal event (`Done`/`Failed`) restore
  + `request_user_attention`. This is required for capture correctness (dxcam
  region capture includes whatever overlaps the game window).

## 4. Testing strategy

**Python (runs in WSL, offline):**
- Unit-test `ProgressEmitter` output shape (parse each line, assert schema).
- `--phases` arg parsing + gating logic: refactor phase-selection into a pure
  helper (`select_phases(args) -> set[str]`) and test combinations incl.
  deprecated `--agents-only`.
- Non-interactive policy: monkeypatch `input` to raise; assert porcelain path
  never calls it (low-conf warning → `warning` event, hard fails → `error`).
- `on_item` callbacks: extend existing scanner tests (golden replay fixtures) to
  count callback invocations.

**Rust (runs anywhere):**
- ScanRunner against a fake scanner: a tiny script (or `cargo` test binary)
  printing a canned JSONL sequence with sleeps → assert state transitions
  Idle→Running(…)→Done; a variant exiting 1 mid-stream → Failed; kill test.
- Event enum deserialization: known events, unknown event ignored, garbage line
  ignored (logged).

**Manual (Windows, live game) — acceptance for the feature:**
- Full scan from GUI end-to-end; discs-only scan; KILL mid-scan then CLI
  `--resume` of the same run dir; clipboard + file export; review.txt opens.

## Open questions
- OQ-G1: exact dxcam behavior when GUI is minimized to taskbar vs moved offscreen —
  minimize is the chosen default; if dxcam needs the game *foreground* anyway
  (focus_game_window already handles), minimize is strictly safe.
- OQ-G2: whether any Cargo deps are shared between deleted modules and the egui
  stack (resolve mechanically at T6 via `cargo build`).
