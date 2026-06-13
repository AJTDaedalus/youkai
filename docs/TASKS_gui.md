# TASKS — GUI ↔ scanner integration (feature: gui)

Worker protocol: one task per session step; load DESIGN_gui.md first; mark
done/blocked here; append to LOG_gui.md. Python tasks run/test in WSL. Rust tasks
build with `cargo build` in `youkai/` (WSL build OK for compile checks; release
exe is built on Windows).

Order matters: T1–T5 (Python contract) before T6–T10 (Rust), T11–T12 last.

---

## T1 — `--phases` flag for scan-all  ✓
- **Files:** `src/youkai_ocr/cli.py`, `tests/test_cli_scan_all.py`
- **Do:** Add `--phases engines,discs,agents` (default all). Pure helper
  `select_phases(args) -> frozenset[str]` (validates names, maps deprecated
  `--agents-only` → `{"agents"}`, errors on empty/unknown). Gate both auto-nav and
  manual-nav flows: storage visit iff engines|discs; engine tab iff engines; disc
  tab iff discs; return_to_main + agent nav iff agents; `resolve_locations` iff
  agents AND discs. Skipped phases report `count: 0, skipped: true` in
  `results.json` phases dict.
- **Accept:** unit tests for `select_phases` (all/discs/agents-only-alias/unknown
  name/empty); existing scan-all tests still pass; no live-game test required.

## T2 — `progress.py` emitter + event schema  ✓
- **Files:** new `src/youkai_ocr/progress.py`, new `tests/test_progress.py`
- **Do:** `ProgressEmitter(stream)` with `run_start/phase_start/progress/
  phase_done/warning/done/error` methods per DESIGN §1 (v:1, one flushed JSON line
  per call); `NullEmitter` no-op with same interface.
- **Accept:** each method's output round-trips through `json.loads`, contains
  `event` + required fields; `NullEmitter` writes nothing.

## T3 — `--porcelain` wiring in scan-all  ✓
- **Files:** `src/youkai_ocr/cli.py`, `tests/test_cli_scan_all.py`
- **Do:** Add flag; construct emitter; emit `run_start` after run-dir creation,
  `phase_start`/`phase_done` around each phase (incl. resumed/skipped),
  `done` after results.json, `error` on ScreenAssertError/any exception (then
  re-raise/exit 1). In porcelain mode re-point `_Tee` mirror from stdout to
  stderr so stdout stays pure JSONL.
- **Accept:** test driving `_cmd_scan_all` with mocked scanners (or the existing
  scan-all test harness) captures stdout and asserts: pure JSONL, exactly one
  terminal event, correct phase sequence for `--phases discs`.

## T4 — Non-interactive policy under porcelain  ✓
- **Files:** `src/youkai_ocr/cli.py`, `tests/test_cli_scan_all.py`
- **Do:** Thread an `interactive: bool` (false when porcelain) into
  `_make_first_item_check` and `_preflight_frame`. Non-interactive: every
  `input()` confirmation becomes `emitter.warning(...)` + continue; hard aborts
  (black frame, size change, color hygiene, first-item total OCR failure) remain
  RuntimeError → `error` event.
- **Accept:** test with `builtins.input` monkeypatched to raise AssertionError;
  porcelain path triggers low-conf and dark-frame branches without calling it;
  warning events observed on stdout.

## T5 — `on_item` progress callbacks in the three scanners  ✓
- **Files:** `disc_scanner.py`, `wengine_scanner.py`, `agent_scanner.py`,
  `cli.py`, existing scanner tests
- **Do:** Optional `on_item(scanned, total)` param, called after each processed
  cell/agent; discs/engines pass total from the `[N / M]` header once read
  (None before); agents pass None. cli.py wires to `emitter.progress`.
- **Accept:** golden-replay/offline scanner tests assert callback called once per
  item with monotonically increasing `scanned`; no behavior change when callback
  omitted (default None).

## T6 — Rust: strip the sniffer backend  ✓
- **Files:** `youkai/src/{main.rs, monitor.rs, capture.rs, wish.rs, update.rs,
  good.rs, player_data.rs, ui/app.rs, ui/admin.rs}`, `youkai/Cargo.toml`
- **Do:** Delete modules per DESIGN §3a; remove admin elevation, update/download
  states, `Message` enum, fake counters, wish flow, `--capture-all-udp/--no-admin`
  args, unused deps. Keep `zod.rs` out of the module tree (reference file).
  Replace `AppState` with the DESIGN §3b skeleton, UI compiles showing Idle state
  with existing chrome (buttons may be inert this task).
- **Accept:** `cargo build` clean (warnings OK); app launches to the console
  layout with SCAN STATUS: [IDLE]; `cargo tree` shows pcap/pktmon/reqwest gone.
- *Note: this is the largest task; if it exceeds ~45 min, split at "modules
  deleted + compiles" / "state skeleton in".*

## T7 — Rust: ScanRunner + event parsing  ✓
- **Files:** new `youkai/src/scan.rs`, `youkai/src/main.rs`
- **Do:** Per DESIGN §3c: command resolution (override → sibling exe →
  `python -m youkai_ocr`), spawn with piped stdout/stderr + CREATE_NO_WINDOW,
  reader thread folding serde-tagged events into ScanState via watch channel,
  stderr ring buffer, `kill()`, exit-without-terminal-event → Failed.
- **Accept:** Rust tests: (a) fake-scanner script streaming canned JSONL →
  Idle→Running→Done transitions observed; (b) early-exit script → Failed with
  stderr tail; (c) unknown event + garbage line ignored; (d) kill() leads to
  Failed/Killed state, no hang.

## T8 — Rust: config + persistence (SavedAppState v2)  ✓
- **Files:** `youkai/src/ui/app.rs` (or new `config.rs`)
- **Do:** `ScanConfig { mode: Full|DiscsOnly, output: PathBuf, scanner_override:
  Option<PathBuf>, debug_overlays: bool }`; serde defaults so missing fields
  deserialize; map mode → `--phases` args; default output
  `export/youkai_export.json` resolved beside the exe's working dir.
- **Accept:** unit test: config → arg vector for both modes; round-trip
  serialize/deserialize; old/garbage persisted blob falls back to default.

## T9 — Rust: UI rework (left column + parameters box)  ✓
- **Files:** `youkai/src/ui/app.rs`
- **Do:** Per DESIGN §3d: real stat rows + progress fraction, status line,
  scan-precondition dialogue text, EXECUTE/KILL button driving ScanRunner; right
  column mode radio, output picker, debug-overlays checkbox, Done-state buttons
  (COPY CLIPBOARD reads output file, EXPORT FILE copies it, OPEN RUN DIR,
  REVIEW REPORT (N) when issues>0), Failed-state stderr tail display;
  configuration modal = scanner override picker. Delete dead modals
  (zzz_settings min-levels, capture settings).
- **Accept:** `cargo build` clean; manual smoke vs the T7 fake scanner shows live
  counts, Done buttons function on a fabricated output file.

## T10 — Rust: occlusion guard (minimize on scan)  ✓
- **Files:** `youkai/src/ui/app.rs`
- **Do:** On successful `start()`: `ViewportCommand::Minimized(true)`. On terminal
  event: `Minimized(false)` + `request_user_attention`. Guard against repeated
  sends.
- **Accept:** code path covered by manual check in T11; transition logic unit-
  testable if folded into ScanState observer (assert commands queued exactly once
  per transition).

## T11 — Windows end-to-end validation (manual, live game)  [~]
- **Do:** Build release exe on Windows. Validate: full scan from GUI; discs-only
  scan; KILL mid-scan (subprocess dies, GUI resets cleanly); clipboard + file
  export; review.txt button; GUI minimized during scan (no GUI pixels in archive
  frames); `Child::kill()` actually stops the python process (else switch to
  `taskkill /T /F` and re-test).
- **Accept:** all checks pass; findings + any threshold fixes logged in
  LOG_gui.md; RUNBOOK.md gains a "GUI quickstart" section.
- *Confirmed (2026-06-12)*: full scan from GUI ✓; clipboard export ✓.
- *Still open — 2 runs:*
  - **Run 1**: discs-only scan; file export; review.txt button; GUI-minimized
    archive-frame check (minimize immediately after starting scan).
  - **Run 2**: KILL mid-scan → confirm subprocess dies + GUI resets cleanly.
- *Deferred (not a v0.1 gate)*: CLI `--resume <run_dir>` — GUI is the
  entrypoint; resume-from-partial is a power-user escape hatch, not exposed in
  GUI. Re-evaluate if GUI gains a resume flow. `Child::kill()` subprocess-death
  check is covered during Run 2.

## T12 — Docs + DECISIONS sync  ✓
- **Files:** `README.md`, `docs/RUNBOOK.md`, `docs/DECISIONS.md`
- **Do:** README: GUI usage, dev-mode requirement (Python env + tesseract on
  PATH), amend the "Rust app decommissioned" wording to "Rust GUI shell, scanner
  in Python". Confirm D39 entry reflects final shape.
- **Accept:** docs match behavior; no references to packet capture remain in
  user-facing docs.

## T13 — Portable distribution (REQUIRED per D40; was stretch)

Portability is now a hard requirement (D40): the tool must run from a portable
folder on a machine with no dev Python env. Shape = PyInstaller **onedir** with
`tesseract` bundled as a sibling binary. Split into T13a–T13c. T13a is Python and
testable in WSL; T13b/T13c are Windows-only (PyInstaller does not cross-compile).

### T13a — Bundled-tesseract resolver (Python, WSL-testable)  ✓
- **Files:** `src/youkai_ocr/recognize.py`, new `tests/test_tesseract_resolve.py`
- **Do:** Refactor the tesseract-path resolution in `TesseractRecognizer.__init__`
  into a pure helper `resolve_tesseract() -> (cmd: str | None, tessdata: Path | None)`.
  Lookup order: (1) `tesseract/tesseract.exe` resolved relative to the app root —
  `Path(sys._MEIPASS)` when `getattr(sys, "frozen", False)`, else the dir of
  `sys.argv[0]` / cwd; (2) existing hardcoded `C:\Program Files\Tesseract-OCR\
  tesseract.exe`; (3) PATH (`"tesseract"`). When a bundled `tessdata/` sits beside the
  resolved binary, set `os.environ["TESSDATA_PREFIX"]` to it. `__init__` calls the
  helper, sets `tesseract_cmd`, then keeps the existing `get_tesseract_version()`
  probe + RuntimeError. No behavior change in dev (slots 2/3 still resolve as today).
- **Accept:** unit tests with a fake frozen layout (monkeypatch `sys.frozen`,
  `sys._MEIPASS`, and a tmp dir holding `tesseract/tesseract.exe` + `tessdata/`):
  assert resolver returns the bundled path and sets `TESSDATA_PREFIX`; assert
  fallthrough to PATH when no bundle present; existing recognize tests still pass.

### T13b — PyInstaller onedir spec for youkai-ocr.exe (Windows)  ✓
- **Files:** new `packaging/youkai-ocr.spec`, `docs/RUNBOOK.md`
- **Do:** PyInstaller `--onedir` spec building `youkai-ocr.exe` from
  `youkai_ocr.cli:main`. Add hidden-imports / `collect_all` as needed for `dxcam`,
  `cv2` (opencv-python-headless), `pynput`, `win32*` (pywin32) — verify by running
  the frozen exe, not by guessing. Console subsystem (the GUI spawns it with
  CREATE_NO_WINDOW). Document the exact build command + how to source `tesseract.exe`
  + `tessdata/eng.traineddata` (UB-Mannheim build, Apache-2.0) in RUNBOOK.
- **Accept:** on Windows, `dist/youkai-ocr/youkai-ocr.exe --help` runs with no dev
  Python on PATH; `youkai-ocr.exe scan-all --porcelain --phases discs` reaches the
  preflight frame check and emits valid JSONL (a live scan is exercised in T13c).

### T13c — Assemble portable folder + clean-machine validation (Windows)  ✓
- **Files:** `docs/RUNBOOK.md` ("Build the portable release" section), `README.md`
- **Do:** Assemble the D40 layout: GUI `youkai.exe` + the onedir `youkai-ocr.exe` +
  `_internal/` co-located in the folder root (so `resolve_command` slot 2 finds the
  scanner), plus `tesseract/tesseract.exe` + `tesseract/tessdata/eng.traineddata`,
  plus an empty `export/`. Validate on a machine (or clean VM/user) with **no** dev
  Python and **no** installed Tesseract: launch `youkai.exe`, run a discs-only scan
  end-to-end, confirm export JSON written. Note any extra DLLs PyInstaller missed.
- **Accept:** clean-machine discs-only scan from the GUI produces a valid export
  with no external installs; RUNBOOK documents the build+assemble steps; README
  "portable release" usage matches. Findings logged in LOG_gui.md.
- **Depends on:** T13a (resolver), T13b (scanner exe), and T9/T10 (GUI Done-state +
  occlusion guard) so the GUI path is real, plus T11 (live-game validation) ideally
  done first so a packaging failure isn't confused with a scan-logic failure.
- **Depends on:** T13d ✓

### T13d — Local-path, version-stamped build (resolves D41 escalation)  ✓
- **Root cause (D41):** the crashing exe was stale, built from pre-fix source; current
  spec/source are already correct. Fix is build hygiene + a freshness gate, not code.
- **Files:** `src/youkai_ocr/__init__.py` (add `__version__`), `src/youkai_ocr/cli.py`
  (argparse `--version`), new `packaging/build_local.ps1`, `docs/RUNBOOK.md` (replace the
  UNC build steps with the local-build flow).
- **Do (WSL-autonomous — run these yourself, no check-in needed between them):**
  1. Add `__version__ = "0.1.0+<short-git-sha>"` to `youkai_ocr/__init__.py`; have
     `build_local.ps1` overwrite the sha at build time (or read it from git) so every
     build is uniquely identifiable.
  2. Wire `parser.add_argument("--version", action="version", version=…)` reading
     `youkai_ocr.__version__`. Add/extend a test asserting `--version` prints it.
  3. Run the full WSL test suite (`pytest -q`) + `python -m youkai_ocr --version` and
     confirm both pass. This is the autonomous acceptance for the code half.
  4. Write `packaging/build_local.ps1`: robocopy `/MIR` repo → `C:\Temp\youkai-build\`;
     `python -m PyInstaller packaging\youkai-ocr.spec --clean -y` there;
     **assert** `dist\youkai-ocr\youkai-ocr.exe --version` == expected id (abort if not);
     run `assemble.ps1`; copy `youkai-portable\` back to the repo root. Lint the script
     by eye for path/quoting correctness (cannot execute PowerShell in WSL).
- **Windows boundary (the ONE human check-in for this task):** user runs
  `powershell -ExecutionPolicy Bypass -File packaging\build_local.ps1`, then
  `youkai-portable\youkai-ocr\youkai-ocr.exe --version` (proves fresh) and
  `youkai-portable\youkai-ocr\youkai-ocr.exe scan-all` far enough to trigger the
  `_cmd_scan_all` deferred imports (proves the ImportError is gone). Paste output here.
- **Accept:** WSL `--version` + tests pass (autonomous); on Windows the assembled exe
  reports the expected build id and clears the `_cmd_scan_all` import without ImportError.
  Then T13c clean-machine validation can proceed against this exe.
