# Youkai

ZZZ inventory OCR scanner. Reads Drive Discs, W-Engines, and Agent stats directly from the game window and exports them as [ZOD](https://frzyc.github.io/zenless-optimizer/)-format JSON, importable into ZZZ-Optimizer and similar tools.

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

## Requirements (live scan)

- Windows 10/11
- ZenlessZoneZero running in **Windowed** mode (not Borderless/Fullscreen)
- A **16:9** resolution — 1920×1080 recommended (ultrawide/portrait are rejected)
- Windows display scale **100%** (DPI scaling breaks region capture)
- **Night Light / f.lux / HDR / color filters OFF** (color-shifted frames are rejected)
- Game data targets ZZZ **v1.4** (`data/zzz_1.4/`)

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

## Export format (extended ZOD)

Output is the ZOD/GOOD JSON the [Zenless Optimizer](https://frzyc.github.io/zenless-optimizer/) accepts (`format: "GOOD"`, `source: "Youkai"`), with `discs`, `weapons`, and `characters` arrays. Equipped relationships live on each disc/engine's `location` (the agent's key, or `""` if unequipped); characters carry no gear list — it's reconstructed downstream from `location`.

**What youkai adds over baseline ZOD:** every character includes a `talent` object with all six skill ranks — the standard scanner export omits these:

```json
"characters": [{
  "key": "...", "level": 60, "constellation": 0, "ascension": 5,
  "talent": { "basic": 1, "dodge": 1, "assist": 1, "special": 1, "chain": 1, "core": 1 }
}]
```

`basic/dodge/assist/special/chain` are numeric skill levels; `core` is the Core Passive rank. The extension is additive and `format` stays `"GOOD"`, so importers that ignore unknown fields keep working, while those that read `talent` get full skill data.

## Safety

Youkai is passive: it reads the game window framebuffer (BitBlt) and sends synthetic mouse/keyboard input. It never reads process memory, modifies game files, or intercepts network traffic. See [docs/RUNBOOK.md §Safety rules](docs/RUNBOOK.md#safety-rules-required--read-before-first-use) for details.

## License

youkai is licensed under the [MIT License](LICENSE). The source repository is private; the MIT terms apply to the distributed `youkai-portable.zip`.

Bundled third-party components are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md):
- **irminsul** — MIT, © 2025 Erik Gilling (the Rust GUI shell derives from it)
- **Tesseract OCR** — Apache-2.0 (bundled in the portable zip)

## Schema reference

`youkai/src/zod.rs` — the original Rust ZOD schema definitions, kept as a field-name reference. The active Python implementation is in `src/youkai_ocr/zod.py`.

> **Note:** The `youkai/` subdirectory is the **Rust GUI shell** — an egui frontend (`youkai.exe`) that spawns the Python scanner as a subprocess and renders its JSONL event stream. The scanner logic lives entirely in `src/youkai_ocr/` (Python). `youkai/src/zod.rs` is kept as a field-name reference for the ZOD schema. The `irminsul/` subdirectory is an unmodified reference clone of the Genshin Impact sniffer the Rust skeleton was derived from.
