# youkai-ocr

ZZZ inventory OCR scanner. Reads Drive Discs, W-Engines, and Agent stats directly from the game window and exports them as [ZOD](https://discord.gg/ZZZ-Optimizer)-format JSON, importable into ZZZ-Optimizer and similar tools.

## Quick start

### Portable release (no install required)

Download the `youkai-portable.zip` release, extract it, and launch `youkai.exe`. The GUI drives the scanner directly — no Python or Tesseract installation needed.

See the **[Portable release quickstart](docs/RUNBOOK.md#build-the-portable-release-t13bt13c)** section in the runbook for build instructions (if you are packaging it yourself).

### Developer install

Requires Python 3.12+ and Tesseract 5.x on `PATH`.

```bash
pip install -e .
python -m youkai_ocr --help
```

See [docs/RUNBOOK.md](docs/RUNBOOK.md) for the full scan procedure, safety notes, and troubleshooting guide.

## Usage

### GUI

Launch `youkai.exe` (portable release), choose a scan mode (Full or Discs Only), navigate to the ZZZ main menu, then click **EXECUTE**. The GUI minimizes during the scan and restores with results when done.

### CLI (developer / headless)

`scan-all` navigates automatically from the main menu — no manual prompts. Add `--manual-nav` if the automatic screen transitions fail on your setup (see [RUNBOOK §scan-all](docs/RUNBOOK.md#2-full-scan-scan-all)).

```bash
# Full scan — all three phases in one command
python -m youkai_ocr scan-all --archive-dir archive\my_session --debug-overlays

# Specific phases only
python -m youkai_ocr scan-all --phases discs,engines --archive-dir archive\my_session

# Individual phase commands
python -m youkai_ocr scan          # Drive Discs only
python -m youkai_ocr scan-engines  # W-Engines only
python -m youkai_ocr scan-agents   # Agent roster only

# Verify window detection
python -m youkai_ocr calibrate
```

## Output

`export/youkai_export.json` — ZOD-format export with `discs`, `weapons`, and `characters` arrays.

Each run also writes a timestamped directory under `--archive-dir` containing:
- `review.txt` — human-readable summary of low-confidence items needing manual verification
- `issues.json` — machine-readable issue records
- `scan.log` / `agent_scan.log` — full run logs
- `results.json` — counts and timing per phase

## Safety

youkai-ocr is passive: it reads the game window framebuffer (BitBlt) and sends synthetic mouse/keyboard input. It never reads process memory, modifies game files, or intercepts network traffic. See [docs/RUNBOOK.md §Safety rules](docs/RUNBOOK.md#safety-rules-required--read-before-first-use) for details.

## Schema reference

`youkai/src/zod.rs` — the original Rust ZOD schema definitions, kept as a field-name reference. The active Python implementation is in `src/youkai_ocr/zod.py`.

> **Note:** The `youkai/` subdirectory is the **Rust GUI shell** — an egui frontend (`youkai.exe`) that spawns `youkai-ocr` as a subprocess and renders its JSONL event stream. The scanner logic lives entirely in `src/youkai_ocr/` (Python). `youkai/src/zod.rs` is kept as a field-name reference for the ZOD schema. See [D39 in docs/DECISIONS.md](docs/DECISIONS.md) for the architecture decision. The `irminsul/` subdirectory is an unmodified reference clone of the Genshin Impact sniffer the Rust skeleton was derived from.
