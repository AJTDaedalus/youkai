# HANDOFF — GUI resize + polish + admin warning

**Created:** 2026-06-12 (end of session). **Tier:** start as Planner (Opus) for Step 0,
then Worker (Sonnet) for the feature tasks. **Feature dir:** `youkai/` (Rust egui GUI).

---

## TL;DR for the next session

We restored the GUI to the proven **reference_18** build, but **that binary cannot be
rebuilt from git** — it was compiled Jun 11 from an *uncommitted* working tree, and HEAD
source rebuilds to a **broken layout** (empty left terminal, missing EXECUTE button,
SCAN PARAMETERS box overflowing the frame). **Do Step 0 first** — re-establish a
rebuildable baseline that renders identically to reference_18 — *before* attempting any
of the feature changes. Everything else depends on it.

**Hard constraint:** this WSL box has **no GPU**; the GUI cannot be rendered/screenshotted
headless (Xvfb + llvmpipe produces blank/1×1 frames — verified). **Every visual change
must be confirmed by the user via screenshot before deploying further.** Do not ship GUI
layout changes blind — four blind builds this session were all broken. See memory
`[[gui_layout_fragile]]`.

---

## Current state (as of this handoff)

- **Deployed everywhere = recovered reference_18 binary**, md5 `0b7efeb6ce5fda1bcb0a93ee4dab8dd0`,
  22,783,223 bytes, built Jun 11 20:44. Locations: repo-root `youkai.exe`,
  `youkai-portable/youkai.exe`, and both Windows copies under
  `C:\Users\laharre\OneDrive\Documents\youkai\` (standalone + `youkai-portable\`).
- **Archived (do not delete):** `archive/known_good_gui/youkai_reference18_jun11.exe`
  — the only surviving copy of the working binary. Recovered from cargo's
  `target/x86_64-pc-windows-gnu/release/deps/youkai-63d5076e2d62d655.exe`. Consider
  copying it somewhere off-machine.
- **HEAD source** (`youkai/src/ui/app.rs`, `main.rs`) = commit `f7ec2ac`, byte-identical
  to `a1a197e` for app.rs+main.rs. Window size `with_inner_size(* 0.5)` = 800×500.

## Why HEAD can't reproduce reference_18 (root cause analysis)

- All repo commits (`ffdf5bb`…`a1a197e`) were made Jun 12 **15:39–15:44** in one batch.
  The working binary is Jun 11 20:44 — it predates every commit. The exact Jun-11 source
  is not in git.
- `strings` diff of recovered binary vs a HEAD build: the **only** UI-text difference is
  the TARGET line. Everything else (dialogue, labels, stat rows) is identical ⇒ the
  **`app.rs` layout code is effectively unchanged**; the broken render is almost certainly
  a **dependency/egui behavior difference**, not lost layout source.
- Binary size differs: 22.7 MB (Jun 11) vs 24.1 MB (HEAD build). egui has been pinned to
  `"0.32"` in `Cargo.toml` since initial import, but `Cargo.lock` was first committed
  (Jun 12) already at **egui 0.32.3** — we do NOT know which 0.32.x the Jun-11 build used.
  egui 0.32 deprecated `allocate_ui_at_rect` and changed sizing/clip behavior across
  patches; a patch bump is the leading suspect for the layout regression.

---

## STEP 0 (BLOCKER) — re-establish a rebuildable baseline = reference_18

Goal: a committed source state that, cross-compiled, renders identically to the recovered
binary (modulo the intentional TARGET-text change, which HEAD already has correct).

1. **Full strings diff** to confirm app.rs source parity:
   ```
   strings -n 6 archive/known_good_gui/youkai_reference18_jun11.exe | sort -u > /tmp/old.txt
   # build HEAD: cargo build --release --target x86_64-pc-windows-gnu
   strings -n 6 youkai/target/x86_64-pc-windows-gnu/release/youkai.exe | sort -u > /tmp/new.txt
   diff /tmp/old.txt /tmp/new.txt
   ```
   Expect: TARGET text + build-hash paths differ; little else. If large source-level diffs
   appear, reconsider the "egui version" hypothesis.
2. **Bisect egui/eframe patch versions.** Try the earliest 0.32.x and walk forward:
   ```
   cargo update -p egui --precise 0.32.0   # also eframe, egui_extras, egui-file-dialog as needed to resolve
   cargo build --release --target x86_64-pc-windows-gnu
   ```
   Signals of a match: binary size approaches **22.7 MB**; and (primary) the **user
   confirms via screenshot** the layout matches reference_18 (full left column, EXECUTE
   button present, params box inside frame). Pin the winning versions with `=` in
   `Cargo.toml` (e.g. `egui = "=0.32.x"`) and commit `Cargo.lock`.
3. If no egui patch fixes it, fall back to **adapting the layout to egui 0.32.3**: replace
   the fragile absolute geometry in `app.rs` (the `allocate_ui_at_rect(window_rect.shrink(8))`
   + `set_clip_rect(intersect max_rect)` + `set_height(available-6)` + `bottom_up` patterns
   at app.rs ~259/377/384/453/622/629) with normal top-down flow in correctly-sized frames.
   This also makes the layout **size-independent**, which is prerequisite for the resize task
   anyway. Verify with user screenshot.
4. **Acceptance:** a `cargo build` from committed HEAD produces a GUI the user confirms is
   visually identical to reference_18 (except TARGET now reads `INTER-KNOT DATABASE`).
   Commit this as the new baseline. Only then proceed to features.

**Built-in canary:** the recovered binary shows `ZZZ CLIENT WINDOW // OPTICAL SIPHON`;
HEAD source shows `INTER-KNOT DATABASE`. So a correct baseline rebuild will visibly switch
that line — instant confirmation the user is running the rebuild, not the recovered binary.

---

## FEATURE TASKS (after Step 0 baseline is committed & verified)

### T-A — Enlarge the app + scale the map to fill its box
- **Why earlier attempts failed:** changing `main.rs` `inner_size` (0.5→0.6) broke the
  fragile layout; `set_zoom_factor(1.2)` didn't visibly fix it either. If Step 0 ended at
  option 3 (size-independent layout), resize becomes safe. If Step 0 stayed on the
  absolute layout, prefer **uniform zoom**: keep the 800×500-point geometry and bump
  `inner_size` AND zoom together so panel points stay 800×500 (e.g. `inner_size *0.6` +
  `set_zoom_factor(1.2)` ⇒ 960/1.2 = 800 pts). This was attempted but unverifiable; revisit
  with user screenshots now that Step 0 gives a known-good baseline to diff against.
- **Map** (`app.rs` ~567–609): currently `Image::max_height(180).max_width(right_width)` —
  aspect-ratio fit leaves dark space on the right of its frame. Make it fill the box width
  ("extend to the right, maintain quality"). Options: (a) raise `map_height` so width fills
  the column; (b) fit-to-width and let height grow; (c) if the source `assets/map.webp` is
  too narrow, source/crop a wider map (do NOT upscale — "maintaining quality"). Pick per
  what looks right; **user screenshot to confirm**.
- **Accept:** app visibly larger; map fills its frame with no dark gutter; quality intact.

### T-B — Make the bottom-right SCAN PARAMETERS box fit inside the pink frame
- This is the *original* request. At 800×500 the params content (`params_config`, app.rs
  ~644–754) is a few px taller than its box, so the last rows
  (`SCANNER OVERRIDE / (auto-detect)`) clip against the window's double-line frame.
- **Do NOT** use a ScrollArea (tried — reflowed the left column and dropped the EXECUTE
  button) or shrink the map alone (looked wrong). Prefer: give the box more vertical budget
  via the T-A resize, and/or trim internal spacing in `params_config`. Keep the EXECUTE
  button and left column intact.
- **Accept:** entire params box (through the SCANNER OVERRIDE line) sits inside the pink
  outline with a clear gutter; left column + EXECUTE unchanged. User screenshot.

### T-C — TARGET text → `INTER-KNOT DATABASE`
- **Already done in HEAD source** (`app.rs:430`). The recovered binary still shows the old
  text; the Step 0 rebuild fixes this automatically. Just **verify** post-baseline.

### T-D — Warning if not running as administrator (NEW feature)
- There was **no** admin warning in the recovered build (removed during the GUI rework;
  `strings` confirms). This is new work, not a restore.
- **Reference implementation** to adapt: `git show 67c4b4e:youkai/src/ui/admin.rs` — has
  `is_admin()` (check) and `ensure_admin()` (auto-elevate via ShellExecute `runas`). User
  wants a **non-blocking warning**, so use `is_admin()` + a banner/toast, NOT auto-elevation.
  The old app.rs banner lived at `67c4b4e:youkai/src/ui/app.rs` ~384–400 (re-theme its
  message; the old one was packet-sniffing flavored).
- **Dependency:** `windows` crate (with `Win32_UI_Shell` feature for `IsUserAnAdmin`) was
  **dropped from `Cargo.toml` in T6** — re-add it (Windows-only target). Gate with
  `#[cfg(windows)]`; non-Windows builds (the Linux dev build) must still compile.
- **Open question OQ-D1:** confirm *why* admin is needed for the OCR scanner (likely: the
  game runs elevated under anti-cheat, so screen capture / input automation against it
  needs elevation too). Word the warning to match the real reason. Keep it advisory and
  consistent with the project's anti-ban guidelines (no memory access; passive only).
- **Accept:** launching un-elevated shows a clear, dismissible warning; launching elevated
  shows nothing. Both Windows (real check) and Linux (compiles, no-op) build.

---

## Logistics / where things live

- **Cross-compile from WSL** (no cargo on Windows; GUI is cross-built):
  `cargo build --release --target x86_64-pc-windows-gnu` (in `youkai/`). Output:
  `youkai/target/x86_64-pc-windows-gnu/release/youkai.exe`.
- **Deploy targets** (keep all in sync): repo-root `youkai.exe`,
  `youkai-portable/youkai.exe`, `C:\Users\laharre\OneDrive\Documents\youkai\youkai.exe`,
  and `…\youkai-portable\youkai.exe`. Windows copies are OneDrive-synced; overwrites fail
  with an I/O error if the app is running — have the user close it first.
- **Portable rebuild** (scanner unchanged ⇒ usually just swap the GUI exe):
  `packaging/build_local.ps1` (Windows; needs Python+PyInstaller; reads GUI exe from
  repo-root `youkai.exe`). For GUI-only changes, copying the new exe into the portable
  folder is enough.
- **The deliverable is `youkai-portable/`** (per the user, 2026-06-12).

## Process rules for this work (learned the hard way)

1. **Never overwrite the last-known-good binary before the replacement is user-verified.**
   Keep `archive/known_good_gui/` intact.
2. **One change at a time → user screenshot → then deploy.** No batching blind changes.
3. Reference screenshots: working baseline = `screenshots/reference_18_cut_off_gui.png`;
   broken states this session = `reference_19_missing_execute.png` (and the design mock
   `4jun26_design_screenshot.png`).
