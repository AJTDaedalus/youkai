# Youkai

ZZZ inventory OCR scanner. Reads Drive Discs, W-Engines, and Agent stats directly from the game window and exports them as [ZOD](https://frzyc.github.io/zenless-optimizer/)-format JSON, importable into ZZZ-Optimizer and similar tools.

## Quick start

### Portable release (no install required)

Download the `youkai-portable.zip` release, extract it, and launch `youkai.exe`. The GUI drives the scanner directly — no Python or Tesseract installation needed.

### Developer install

Requires Python 3.12+ and Tesseract 5.x on `PATH`.

```bash
pip install -e .
python -m youkai_ocr --help
```

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

`scan-all` navigates automatically from the main menu — no manual prompts. Add `--manual-nav` if the automatic screen transitions fail on your setup.

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

### Chiaki / alternate client (PlayStation Remote Play)

Youkai supports scanning ZZZ streamed via **chiaki-ng** (or another Remote Play client)
with no extra flags — chiaki-ng's window title is a built-in default.

If your client has a different title, use the three-step discovery recipe:

1. Launch your streaming client and start the ZZZ stream.
2. Run `youkai-ocr windows` — this lists every visible window with its title:
   ```
   youkai-ocr windows
   ```
3. Copy the exact title from the `title=` column and pass it on the command line:
   ```
   youkai-ocr --window-title "My Remote Play" scan-all ...
   ```
   Or set it persistently via the environment variable:
   ```
   YOUKAI_WINDOW_TITLES="My Remote Play" youkai-ocr scan-all ...
   ```

**Retail ZZZ is unaffected** — `ZenlessZoneZero` is always in the accepted-title list
regardless of any `--window-title` or environment flags.

**Chiaki-ng works out of the box** — `chiaki-ng` is a built-in default title; no flag needed.

> Note: the chiaki-ng window renders the ZZZ stream at whatever resolution you set in
> chiaki. Set it to a 16:9 resolution (1920×1080 recommended) so the scanner's aspect-ratio
> check passes. Ensure the stream fills the client area with no black bars.

## Output

`export/youkai_export.json` — ZOD-format export with `discs`, `weapons`, and `characters` arrays. A disc that fails invariant validation is excluded from the export (never a known-wrong value) and instead reported in `issues.json`/`review.txt` for manual re-scan.

Have an older archived run with wrong disc values? `youkai-ocr revalidate --archive <dir> --out <export.json>` replays its `disc_NNNN/panel.png` crops through the current validator/repair tables offline (no game, no live scan) and writes a corrected export plus a repair report.

Each run also writes a timestamped directory under `--archive-dir` containing:
- `review.txt` — human-readable summary of low-confidence items needing manual verification
- `issues.json` — machine-readable issue records
- `scan.log` / `agent_scan.log` — full run logs
- `results.json` — counts and timing per phase

## Export format (extended ZOD)

Output is extended ZOD JSON for the [Zenless Optimizer](https://frzyc.github.io/zenless-optimizer/) (`format: "eZOD"`, `source: "Youkai"`), with `discs`, `weapons`, and `characters` arrays. Equipped relationships live on each disc/engine's `location` (the agent's key, or `""` if unequipped); characters carry no gear list — it's reconstructed downstream from `location`.

**What youkai adds over baseline ZOD:** every character includes a `talent` object with all six skill ranks — the standard scanner export omits these:

```json
"characters": [{
  "key": "...", "level": 60, "constellation": 0, "ascension": 5,
  "talent": { "basic": 1, "dodge": 1, "assist": 1, "special": 1, "chain": 1, "core": 1 }
}]
```

`basic/dodge/assist/special/chain` are numeric skill levels; `core` is the Core Passive rank. The extension is additive over baseline ZOD, so importers that ignore unknown fields keep working, while those that read `talent` get full skill data.

## Safety

**Youkai is passive.** It reads the game-window framebuffer (BitBlt) and sends synthetic mouse and keyboard input through the OS, exactly as a physical device would. It never reads or writes process memory, never modifies game files, and never intercepts or injects network traffic — there is nothing for a kernel anti-cheat to observe at the process or network level.

Our reading of HoYoverse's Terms of Service is that a passive, read-only screen scanner like this does not grant an unfair competitive advantage and should be permissible, and to our knowledge no one has been penalized for using this or a similar screen-OCR scanner. That is our interpretation, not a guarantee — if you have any concern, skip the automated mode and enter data by hand, and **always test on a secondary/alt account first.**

### Automated ("auto") scanning mode

- **Run as administrator.** Auto mode must run elevated to deliver input to the game window; unelevated, the synthetic mouse/keyboard events are silently dropped.
- **It takes over your mouse and keyboard.** During a scan it clicks, scrolls, and presses keys on its own — do not move the mouse or type while it runs.
- **Press `Esc` to abort.** The scanner watches for a physical `Esc` and stops immediately. (Its own in-game "back" navigation presses `Esc` programmatically without tripping the abort.)

### Keep on-screen colors unmodified

Youkai identifies content by OCR and by sampling rendered colors (rarity, badge digits, disc fill tiers), so anything that shifts the game's on-screen colors corrupts a read. Youkai **rejects** color-shifted frames rather than emitting wrong values, so an interfering overlay makes scans *fail* instead of silently mis-reading. Turn these off before scanning:

- Windows **Night Light**, **f.lux**, and **HDR**
- **ReShade** and **NVIDIA Freestyle / game filters**
- **Colorblind** compensation filters
- Image sharpening such as **Radeon Image Sharpening** or **NVIDIA Image Sharpening**

(See also the display requirements above: windowed, 16:9, 100% scale.)

## License

youkai is licensed under the [MIT License](LICENSE). The source repository is private; the MIT terms apply to the distributed `youkai-portable.zip`.

Bundled third-party components are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md):
- **irminsul** — MIT, © 2025 Erik Gilling (the Rust GUI shell derives from it)
- **Tesseract OCR** — Apache-2.0 (bundled in the portable zip)

## Schema reference

`youkai/src/zod.rs` — the original Rust ZOD schema definitions, kept as a field-name reference. The active Python implementation is in `src/youkai_ocr/zod.py`.

> **Note:** The `youkai/` subdirectory is the **Rust GUI shell** — an egui frontend (`youkai.exe`) that spawns the Python scanner as a subprocess and renders its JSONL event stream. The scanner logic lives entirely in `src/youkai_ocr/` (Python). `youkai/src/zod.rs` is kept as a field-name reference for the ZOD schema. The `irminsul/` subdirectory is an unmodified reference clone of the Genshin Impact sniffer the Rust skeleton was derived from.
