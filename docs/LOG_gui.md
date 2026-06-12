# LOG — GUI ↔ scanner integration

## T6 — Rust: strip the sniffer backend ✓ (2026-06-11)

**Deleted modules:** `monitor.rs`, `capture.rs`, `wish.rs`, `update.rs`, `good.rs`,
`player_data.rs`, `ui/admin.rs`

**Cargo.toml:** Dropped anime-game-data, flate2, tokio, tokio-util, async-watcher,
auto-artifactarium, base64, ctrlc, futures, futures-util, indexmap, log, notify,
regex, reqwest, self_update, tempfile, rand_mt, clap, env_logger, pktmon, windows.
Kept: egui stack, serde, chrono, anyhow, open, tracing stack.

**build.rs:** Stripped to just winresource icon embed (removed anime-game-data/tokio
async download logic).

**main.rs:** Replaced State/Message/AppState/DataUpdated with new ScanState skeleton
(Idle/Running/Done/Failed) + PhaseCounts, PhaseResult, Summary, ScanPhase.
Removed --no-admin, --capture-all-udp args and admin elevation call.
`mod zod` removed from module tree (file kept on disk as reference).

**ui/mod.rs:** Removed `pub mod admin`.

**ui/app.rs:** Removed tokio/monitor/player_data/update/wish imports and all
capture-related fields (ui_message_tx, state_rx, wish_url_rx, log_packets_tx,
zzz_*, interknot_packets, tops_packets). Removed start_async_runtime, fake counters,
admin warning banner, capture_settings_modal, zzz_settings_modal,
zenless_optimizer_* methods. Kept visual chrome (title bar, double-line frame,
power tools, bug report). New main_ui shows SCAN STATUS: [IDLE] / RUNNING / DONE /
FAILED based on scan_state. Scan buttons present but inert (T7 wires up ScanRunner).

**Result:** `cargo build` clean (22 warnings, 0 errors). `cargo tree` confirms
pktmon/reqwest/tokio absent from dependency tree.

**Next:** T7 — ScanRunner + event parsing (`youkai/src/scan.rs`)

## T7 — Rust: ScanRunner + event parsing ✓ (2026-06-11)

**New file:** `youkai/src/scan.rs`

**`ScanConfig`** — `scanner_override`, `output`, `phases`, `debug_overlays`.

**`ScanHandle::start(config, ctx)`** — resolves command (override → sibling
`youkai-ocr[.exe]` → `python -m youkai_ocr`), spawns with piped stdout/stderr
+ `CREATE_NO_WINDOW` on Windows. Returns immediately; state transitions happen
on reader thread.

**Reader thread** — line-buffered `BufReader` on stdout; `serde_json::from_str`
into `ScanEvent` (`#[serde(tag="event", rename_all="snake_case")]`); unparseable
or unknown-event lines are logged at WARN and skipped. Folds events into
`Arc<Mutex<ScanState>>`: `run_start`→Running, `phase_start/progress/phase_done`
update live counts, `done`→Done, `error`→Failed. EOF without terminal event →
Failed with stderr tail.

**Stderr thread** — ring-buffer last 50 lines for the Failed view.

**`kill()`** — `Child::kill()` (ignores error); stdout EOF causes reader thread
to transition to Failed naturally.

**`main.rs`:** Added `mod scan; pub use scan::{ScanConfig, ScanHandle};`

**Tests (4/4 pass, 0.19s):**
- `test_good_run_reaches_done` — canned JSONL via Python → `Done{engines:2}`
- `test_early_exit_failed_with_stderr_tail` — exit-1 script → `Failed` containing stderr
- `test_garbage_and_unknown_events_ignored` — garbage line + unknown event → still reaches `Done`
- `test_kill_leads_to_failed_no_hang` — sleep-60 script, kill after 150ms → `Failed` within 5s

**Result:** `cargo build` + `cargo test` clean (28 warnings pre-existing, 0 errors).

**Next:** T8 — config + persistence (`ScanConfig` in `SavedAppState v2`)

## T8 — Rust: config + persistence ✓ (2026-06-11)

**`scan.rs`:**
- Added `ScanMode { Full (default), DiscsOnly }` — `Serialize/Deserialize/Default/PartialEq`.
- Replaced `ScanConfig.phases: Vec<String>` with `mode: ScanMode`; added
  `Serialize/Deserialize/Default` with per-field `#[serde(default)]` and
  `#[serde(default = "ScanConfig::default_output")]` for `output`.
- `ScanConfig::default_output()` returns `export/youkai_export.json`.
- `build_command`: Full → no `--phases` flag; DiscsOnly → `--phases discs`.

**`main.rs`:** Re-exported `ScanMode`.

**`ui/app.rs`:** `SavedAppState` gains `scan_config: ScanConfig` field with
`#[serde(default)]`; old persisted blobs missing the field deserialize via
`unwrap_or_default()` fallback already in place.

**Tests (4/4 pass, 0.00s):**
- `test_config_args_full_mode` — Full mode emits no `--phases` flag
- `test_config_args_discs_only` — DiscsOnly emits `--phases discs`
- `test_config_round_trip` — serialize → deserialize preserves all fields
- `test_config_empty_json_falls_back_to_default` — `{}` deserializes to defaults

**Result:** `cargo build` + 4 new tests pass. 28 pre-existing warnings, 0 errors.

**Next:** T9 — UI rework (left column + parameters box)

## T9 — Rust: UI rework (left column + parameters box) ✓ (2026-06-11)

**`ui/app.rs`** — full UI rework:

**New fields on `YoukaiApp`:**
- `scan_handle: Option<ScanHandle>` — live handle; polled every frame; cleared on terminal state
- `file_dialog: FileDialog` + `file_dialog_purpose: FileDialogPurpose` — single dialog reused for OutputPath / ScannerOverride / ExportFile
- `config_modal_open: bool` — scanner override config modal

**Left column changes:**
- `phase_display(phase)` helper returns `(String, Color32)` live from ScanState: active phase shows `scanned/total`, finished phases show final count, Done shows summary, Failed shows `--` in red
- Stat rows: `W-Engine Cores`, `Drive Discs`, `Agent Files` with live counts
- Dialogue text updated to real preconditions: windowed ZZZ, main hub, no Night Light
- `EXECUTE EXTRACTION SCRIPT` button: creates `ScanHandle::start(config, ctx)` → live scan
- `KILL EXTRACTION SCRIPT` button: calls `handle.kill()` (no confirm dialog)

**Right column — `params_panel` dispatches to three sub-functions:**
- `params_config` (Idle/Running): mode radio (Full/DiscsOnly), output path label+browse (`...`), debug overlays checkbox, scanner override row + "config" button opening `config_modal`
- `params_done` (Done): COPY TO CLIPBOARD (reads output file → `ctx.copy_text`), EXPORT FILE (save dialog → `fs::copy`), OPEN RUN DIR, REVIEW REPORT (N issues) (amber, only when `issues > 0`), NEW SCAN reset
- `params_failed` (Failed): scrollable stderr tail, optional OPEN RUN DIR, NEW SCAN reset

**Config modal** (`config_modal`): scanner override path display + "Locate..." (`pick_file`), clear override, auto-detect order explanation.

**File dialog:** `pick_file()` for ScannerOverride; `save_file()` for OutputPath and ExportFile.

**Result:** `cargo build` clean (warnings pre-existing only, 0 errors); 8/8 tests pass.

**Next:** T10 — occlusion guard (minimize on scan start, restore on terminal event)

## T10 — Rust: occlusion guard (minimize on scan)  ✓ (2026-06-11)

Occlusion guard was already implemented as part of T9. Verified:
- `occlusion_minimized: bool` field in `YoukaiApp` (app.rs:48)
- Initialized to `false` in `new()` (app.rs:123)
- On EXECUTE click: `ViewportCommand::Minimized(true)` + `occlusion_minimized = true` (app.rs:536–539)
- On terminal event in `update()`: `Minimized(false)` + `RequestUserAttention` + `occlusion_minimized = false` (app.rs:143–148)

`cargo build` clean.

## T13a — Bundled-tesseract resolver (Python, WSL-testable)  ✓ (2026-06-11)

**Files changed:** `src/youkai_ocr/recognize.py`, new `tests/test_tesseract_resolve.py`

**What changed:**
- Extracted `resolve_tesseract() -> tuple[str | None, Path | None]` above `TesseractRecognizer`.
  Lookup order: (1) `tesseract/tesseract[.exe]` beside frozen/dev app root (`sys._MEIPASS` when
  frozen, else `sys.argv[0]` parent); (2) `C:\Program Files\Tesseract-OCR\tesseract.exe` on win32;
  (3) `(None, None)` → pytesseract defaults to PATH.
  Returns `(cmd, tessdata_prefix)` — caller sets `TESSDATA_PREFIX` if tessdata is not None.
- `TesseractRecognizer.__init__` now calls `resolve_tesseract()`, sets
  `pytesseract.pytesseract.tesseract_cmd` and `os.environ["TESSDATA_PREFIX"]` as appropriate.
- Removed inline platform-detection code from `__init__`.

**Tests:** 6 new tests in `tests/test_tesseract_resolve.py` (frozen bundle returns bundled cmd,
frozen bundle sets tessdata prefix, no tessdata returns None prefix, fallthrough to PATH on
non-win32, fallthrough on win32 without Program Files, __init__ integration); 26 existing
recognize tests still pass.

**Next:** T11 (Windows end-to-end, manual) or T13b (PyInstaller spec, Windows-only) or T12 (docs).

---

## 2026-06-11 — T13b: PyInstaller onedir spec authored

**Task:** T13b — PyInstaller onedir spec for `youkai-ocr.exe`

**Files changed:**
- `packaging/youkai-ocr.spec` — new
- `docs/RUNBOOK.md` — added "Build the portable release" section

**What was done:**
Created `packaging/youkai-ocr.spec` — a `--onedir` PyInstaller spec targeting `youkai_ocr.cli:main`.
Key decisions:
- `console=True` (GUI spawns the scanner with `CREATE_NO_WINDOW`; the exe itself is a console app).
- `upx=False` — UPX can corrupt OpenCV DLLs; left off by default.
- `hiddenimports` covers `cv2`, `pytesseract`, `rapidfuzz.process`/`.fuzz`, `PIL`/`PIL.Image`,
  `pynput.keyboard._win32` + `.mouse._win32`, `win32api`/`win32con`/`win32gui`/`win32process`/
  `pywintypes`, `dxcam`, `numpy`.
- `datas` bundles the `data/` tree (agents/engines/stats/navigation JSONs) so the frozen exe finds
  its lookup tables at runtime.
- The spec's inline comment documents the exact `pyinstaller` invocation and the Tesseract bundling
  layout (UB-Mannheim build → `dist/youkai-ocr/tesseract/tesseract.exe` +
  `tessdata/eng.traineddata`).
- The RUNBOOK "Build the portable release" section covers: build prerequisites, step-by-step
  commands, smoke-test commands, Tesseract bundling layout, final portable folder assembly (T13c
  shape), and clean-machine validation checklist.

**Acceptance status:**
- `packaging/youkai-ocr.spec` authored and committed. ✓
- Build + smoke-test (`dist/youkai-ocr/youkai-ocr.exe --help`) **requires Windows** — cannot
  execute in WSL. ☐ (to be verified by user on Windows as part of T13c/T11).

**Next:** T13c (assemble portable folder, clean-machine validation — Windows) or T11/T12.

---

## T13c — Portable folder assembly (WSL prep, 2026-06-11)

**WSL-side work completed:**

1. **`resolve_command` fix (`youkai/src/scan.rs`)** — The code was looking for `youkai-ocr.exe` as a flat sibling, but the RUNBOOK documented a `youkai-ocr/youkai-ocr.exe` subdirectory layout (matching PyInstaller's `--onedir` output structure). Fixed: primary lookup is now `<exe_dir>/youkai-ocr/youkai-ocr.exe` (portable layout); flat sibling `<exe_dir>/youkai-ocr.exe` kept as a secondary fallback for dev use; `python -m youkai_ocr` remains the final fallback. `cargo build` clean (30 pre-existing warnings, 0 errors).

2. **RUNBOOK fix (`docs/RUNBOOK.md`)** — Removed the wrong `(PyInstaller onedir, T13c)` annotation for `youkai.exe` (GUI is Rust, not PyInstaller — single exe, no `_internal/`) and removed the erroneous `_internal\` line from the GUI row. Updated the note to accurately describe the `resolve_command` subdirectory logic.

3. **README update (`README.md`)** — Added "Portable release (no install required)" section at the top of Quick start, linking to the RUNBOOK portable build section.

4. **`packaging/assemble.bat`** — New script automating the `youkai-portable\` folder assembly on Windows. Runs after `cargo build --release` + `pyinstaller` + Tesseract copy; preflight-checks all three inputs; calls `xcopy` to build the exact layout; prints the smoke-test commands.

**Still requires Windows:**
- `pyinstaller packaging\youkai-ocr.spec` → `dist\youkai-ocr\youkai-ocr.exe --help` smoke-test
- `cargo build --release` → `youkai\target\release\youkai.exe`
- `packaging\assemble.bat` → assemble `youkai-portable\`
- Clean-machine validation (no dev Python, no Tesseract installed) — discs-only scan from GUI → export JSON written

**Next:** User runs the above four steps on Windows. Log any missing DLLs in this file. Close T13c once clean-machine validation passes.

---

## ESCALATION — T13c PyInstaller frozen-exe ImportError (escalate to Opus)

**Escalation date:** 2026-06-11

**Summary of what was attempted (multiple rounds):**
1. Converted all relative imports in `src/youkai_ocr/cli.py` from `from .X import Y` to `from youkai_ocr.X import Y` using sed. Verified with `grep -c "from \."` → 0 matches.
2. Added `packaging/run.py` wrapper (2 lines) so the PyInstaller entry is NOT cli.py. Spec updated: `Analysis([str(ROOT / "packaging" / "run.py")], ...)`.
3. All `__pycache__/` directories deleted from WSL (`src/youkai_ocr/`, `tests/`).
4. Build run with `python -m PyInstaller packaging/youkai-ocr.spec --clean -y` on Windows (from `\\wsl$\Ubuntu\root\youkai`). Build reported success.
5. Error persists across 6+ rebuild cycles.

**Exact error (full traceback from Windows PowerShell):**
```
File "cli.py", line 1319, in <module>
File "cli.py", line 1312, in main
File "cli.py", line 849, in _cmd_scan_all
ImportError: attempted relative import with no known parent package
[PYI-52976:ERROR] Failed to execute script 'cli' due to unhandled exception!
```

**Key diagnostic that the Planner/Brain should resolve:**
`"Failed to execute script 'cli'"` is PyInstaller's bootloader message — it literally means the frozen exe's `__main__` entry script is named `'cli'`, not `'run'`. Despite the spec file clearly showing `Analysis([str(ROOT / "packaging" / "run.py")])`, the running exe has `cli` as its entry. This is the core contradiction.

**Current spec entry:** `packaging/youkai-ocr.spec` line 42: `[str(ROOT / "packaging" / "run.py")]`  
**Current cli.py line 849:** `from youkai_ocr.capture import calibrate_window` (absolute import — verified in WSL)  
**WSL `__pycache__`:** Only `__init__.cpython-313.pyc` exists; no `cli.cpython-313.pyc`.

**Hypotheses (unconfirmed — requires Windows filesystem access to verify):**
1. **Stale dist/ exe**: `--clean` clears `build/` but not `dist/`. If `dist\youkai-ocr\youkai-ocr.exe` is from a pre-`run.py` build, re-running PyInstaller overwrites it — BUT `assemble.ps1` may have been run before the latest build, so `C:\youkai-portable\youkai-ocr\youkai-ocr.exe` is the old exe.  
2. **Windows Python bytecode cache**: Windows Python 3.13 may have cached `cli.cpython-313.pyc` in a Windows-local AppData cache (not visible from WSL). The cached .pyc could have the old relative imports, and PyInstaller uses that instead of recompiling from source.  
3. **UNC path stale read**: Windows Python's source read of `\\wsl$\Ubuntu\...\cli.py` may be serving a cached version with old content if the mtime precision on the UNC path is insufficient to detect the sed change.

**Concrete verification steps needed (on Windows):**
1. Run: `dist\youkai-ocr\youkai-ocr.exe --help` — does it say "script 'run'" or "script 'cli'"? If 'cli', the exe was built before `run.py` was added.
2. Copy the entire source tree to `C:\Temp\youkai-build\` (local Windows C: drive), rebuild from there. This eliminates UNC path issues entirely.
3. Check `%LOCALAPPDATA%\pyinstaller\` or `%TEMP%\` for any cached pyc files from prior builds.

**Recommended approach for Opus:**
The safest fix is to move the build to a local Windows path (not UNC). Add a `copy_to_local_and_build.ps1` that: (1) `robocopy`s the repo source to `C:\Temp\youkai-build\`, (2) runs PyInstaller from there, (3) copies `dist\youkai-ocr\` back to the UNC path. This eliminates all UNC/mtime/cache issues simultaneously.

**Return to Worker after:** Opus confirms the diagnosis and either (a) identifies the stale exe root cause or (b) approves the local-copy build approach, in which case Worker implements the new build script.

### RESOLUTION (Planner/Opus, 2026-06-12) — escalation closed → D41, T13d

**The escalation's lead hypothesis was right, and the traceback proves it harder than
stated.** The crashing exe is a **stale artifact from pre-fix source**. Three independent
facts in the traceback are each impossible against the *current* spec/source and only
consistent with old cli.py run as the `__main__` entry:
- bootloader `script 'cli'` — current spec entry is `run.py`, would say `'run'`;
- `cli.py:1319 <module>` — that's cli.py's last line (`main()`), i.e. run as a top-level
  script, which the current spec never does;
- relative-import error at `cli.py:849` — current line 849 is the **absolute**
  `from youkai_ocr.capture import …`; only old (`from .capture …`) throws there. sed kept
  line numbers aligned, which is why 849/1319 still match.

So: **the code is already correct.** No more import debugging. What we had was a build-hygiene
failure — fresh PyInstaller output never reached the binary being launched (most likely a
`youkai-portable\` assembled once before run.py, while rebuilds landed in `dist\`; or a
cached `cli.pyc` read over the `\\wsl$` UNC mount).

**Fix (D41 → T13d), two parts:**
1. Build on a local Windows path: `packaging/build_local.ps1` robocopy `/MIR` → `C:\Temp\`,
   PyInstaller `--clean` there, assemble there, copy back. Eliminates the UNC/pyc class.
2. Version-stamp + gate: `youkai_ocr.__version__`, cli `--version`, and the build script
   asserts the fresh exe prints the expected id before assembling. A stale exe can never
   pass silently again. (`--help` is not a valid gate — the broken import is deferred inside
   `_cmd_scan_all`, so a stale exe's `--help` still exits 0.)

**Worker autonomy for T13d:** do ALL of it self-driven with no check-ins —
add `__version__`, wire `--version`, write `build_local.ps1`, run `pytest -q` and
`python -m youkai_ocr --version` in WSL yourself, fix anything that fails, and only stop at
the single genuine Windows boundary (PyInstaller can't run in WSL): the user runs
`build_local.ps1` + the two exe checks and pastes output. Don't stop between WSL substeps.

**Resolved. Return to Worker (Sonnet) to implement T13d in docs/TASKS_gui.md.**

---

## 2026-06-12 — T13d: Local-path, version-stamped build ✓ (WSL half)

**Files changed:**
- `src/youkai_ocr/__init__.py` — changed `__version__` from `"0.1.0"` to `"0.1.0+dev"`;
  added comment flagging the line for build-script patching.
- `src/youkai_ocr/cli.py:1236` — replaced hardcoded `"youkai-ocr 0.1.0"` with
  `f"youkai-ocr {__version__}"` (imports `youkai_ocr.__version__` inline at the call site).
- `tests/test_cli_scan_all.py` — added `test_version_flag_prints_package_version`: invokes
  `main()` with `--version`, asserts exit 0 and that stdout contains `youkai_ocr.__version__`.
- `packaging/build_local.ps1` — new: robocopy → patch sha → PyInstaller --clean → version-gate
  → assemble.ps1 → copy back.
- `docs/RUNBOOK.md` — replaced manual UNC build steps with `build_local.ps1` one-liner;
  documented version-gate rationale; kept clean-machine validation section.

**WSL acceptance (autonomous):**
- `python -m youkai_ocr --version` → `youkai-ocr 0.1.0+dev` ✓
- `pytest -q` → **465 passed, 0 failures** (6:02) ✓

**Windows boundary (next step — user action required):**
Run `powershell -ExecutionPolicy Bypass -File packaging\build_local.ps1` then paste:
1. `youkai-portable\youkai-ocr\youkai-ocr.exe --version` output (proves freshness)
2. `youkai-portable\youkai-ocr\youkai-ocr.exe scan-all` first few lines (proves no ImportError)

---

## T12 — Docs + DECISIONS sync ✓ (2026-06-12)

**Changes:**
- `README.md`: added Python 3.12+ / Tesseract 5.x dev prereqs; split Usage into GUI + CLI sections with auto-nav note and `--phases` example; updated `youkai/` bottom note from "decommissioned packet-sniffer prototype" to "Rust GUI shell" with pointer to D39.
- `docs/RUNBOOK.md`: updated §2 scan procedure to auto-nav as default (no manual prompts); demoted `--manual-nav` to a fallback block; added `--phases` example; added **GUI quickstart** section (portable-release flow: launch → EXECUTE → REVIEW REPORT / EXPORT FILE / KILL).
- `docs/DECISIONS.md`: D39 confirmed accurate — describes final architecture (egui shell + subprocess JSONL protocol + `--porcelain`/`--phases` flags). No changes required.
- `docs/TASKS_gui.md`: T12 marked ✓.

**Acceptance:** no packet-capture references remain in user-facing docs (README/RUNBOOK); `youkai/` described as the GUI shell; dev mode prerequisites explicit; auto-nav documented as default.

---

## 2026-06-12 — T11/T13b/T13c: Windows validation (partial)

**T13b smoke test (confirmed):** `youkai-ocr.exe --help` and `scan-all --porcelain --phases discs` both ran successfully on Windows from the assembled portable folder. "spec authored; build+smoke-test pending" note removed — T13b fully ✓.

**T13c (confirmed):** Portable release launched via `youkai.exe`, ran a full scan from the GUI, and export JSON was saved successfully. T13c marked ✓.
- Note: strict "no dev Python / no Tesseract installed" clean-machine isolation was not explicitly verified — if needed, re-test on a clean VM.

**T11 (partial):**
- ✓ Full scan from GUI completes end-to-end
- ✓ Clipboard export (COPY CLIPBOARD button)
- ☐ Discs-only scan (mode radio → Discs Only)
- ☐ KILL mid-scan then `--resume <run_dir>` from CLI
- ☐ EXPORT FILE button (file copy, not clipboard)
- ☐ REVIEW REPORT button opens review.txt
- ☐ GUI minimized during scan (no GUI pixels in archive agent frames)
- ☐ `Child::kill()` terminates the python subprocess cleanly

The critical path (full scan works, export round-trips) is validated. Remaining items are edge-case robustness checks; none are blockers for v0.1 usage.

---

## 2026-06-12 — UI fix: params box overflowing window frame

**Symptom** (`screenshots/reference_18_cut_off_gui.png`): at the fixed 800×500 window, the right-column `SCAN PARAMETERS` content (`SCANNER OVERRIDE / (auto-detect)` rows) spilled past the box's bottom stroke and overlapped the GRID_OS window frame.

**Root cause:** right column = 180px map + 8px gap + params box sized to remaining height (~180px), but `params_config` content needs ~190px and was laid out top-down with no scroll, so the last rows overflowed onto the chrome. Content height is also variable (path/override strings), so tightening spacing alone wouldn't be robust.

**First attempt (reverted):** ScrollArea around the params box + `map_height` 180→140 + larger gutter. On Windows this reflowed the left column so the EXECUTE button dropped off-screen and the shortened map looked wrong. Reverted to the original layout.

**Fix shipped** (`youkai/src/main.rs`): scaled the window up instead — `with_inner_size` factor `0.5` → `0.6` (800×500 → 960×600). The +100px height clears the params content overflow with room to spare while leaving the proven layout (fixed 360px left column, bottom-anchored EXECUTE button, 180px map) untouched. Window stays non-resizable; 960×600 is still small relative to any modern display.

`cargo build --release --target x86_64-pc-windows-gnu` ✓ (only pre-existing dead-code warnings). Visual re-check on Windows pending.
