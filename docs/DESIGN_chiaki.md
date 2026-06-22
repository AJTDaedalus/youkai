# DESIGN — Chiaki window support

**Status:** ready for implementation
**Author tier:** Planner (Opus)
**Date:** 2026-06-13

## Problem

Youkai should scan when the game is running under `chiaki.exe` (windowed, 1920×1080),
not only the retail `ZenlessZoneZero.exe` client.

## Confirmed facts (from user, 2026-06-13)

1. **Detection is window-*title* based, not exe-based.** `capture.list_game_windows()`
   enumerates top-level windows (EnumWindows / GetWindowText / GetClientRect /
   ClientToScreen) and keeps those whose title contains `GAME_TITLE`
   (`"ZenlessZoneZero"`, normalized). There is **no process or memory access** anywhere —
   this is deliberate (anti-ban rule 2). We keep it that way: no psutil, no
   GetWindowThreadProcessId, no process-image lookups.
2. **Same UI.** Chiaki renders the identical ZZZ inventory / disc / W-engine / agent
   screens at the 1920×1080 reference. ⇒ `navigation.yaml` and every field bbox are
   **unchanged**. Only detection changes.
3. **Either, not replace.** Accept *either* the retail title or chiaki's title with one
   build. No regression for existing ZZZ users.
4. **Chiaki's title bar text = `chiaki-ng`** (confirmed 2026-06-13 via
   `Get-Process chiaki | Select MainWindowTitle`). This is **Chiaki-NG**, the open-source
   PlayStation Remote Play client — ZZZ is streamed from a PS5/PS4 and rendered in the
   chiaki-ng window. Accepted title to ship: `"chiaki-ng"` (substring `"chiaki"` also
   matches). Discovery command (TASK-4) still ships for future / other clients.

### Remote-Play caveats (new, because chiaki-ng is a stream)

- The window client area may not be a pixel-exact 1920×1080 — remote play letterboxes /
  scales the stream, and window chrome is excluded by `GetClientRect`. Existing aspect-ratio
  calibration (`calibrate()` accepts any 16:9 within ±1%, scales to the 1920×1080 reference)
  absorbs uniform scaling, **but letterbox bars would break bbox alignment.** Verify the
  stream fills the client area 16:9 with no black bars during testing.
- Stream compression/latency may soften text → watch OCR confidence on first live run; not a
  code change, a tuning/QA note.

## Approach

Generalize the single hardcoded `GAME_TITLE` into a configurable **accepted-titles list**.
A window matches if *any* accepted title is a normalized substring of its title bar text
(same `_normalize_title` rule already used). Resolution order, lowest → highest priority,
all **merged** (union) so retail always keeps working:

1. Built-in default: `("ZenlessZoneZero",)`
2. Env var `YOUKAI_WINDOW_TITLES` — comma-separated (for portable-exe users who set it in
   a shortcut / .bat).
3. CLI `--window-title TITLE` — repeatable global flag; appends.

Resolution happens once in `main()` before command dispatch, via
`capture.set_accepted_titles(...)`. All existing call sites (`grab_window`,
`calibrate_window`, `focus_game_window`, `list_game_windows`) read module state — **no
signature changes threaded through the call graph.**

### Discovery (the "what is chiaki's title?" problem)

Add `youkai windows` — enumerates **every** visible, non-zero-client top-level window
(title, size, position), not just title-matched ones, and marks which the scanner would
pick. This lets a user run Chiaki, run `youkai windows`, and read off the exact string to
pass to `--window-title`. Same passive EnumWindows path — no new safety surface.

## Module changes

### `capture.py`
- Replace `GAME_TITLE = "ZenlessZoneZero"` with
  `DEFAULT_GAME_TITLES = ("ZenlessZoneZero",)` and module state
  `_accepted_titles: tuple[str, ...] = DEFAULT_GAME_TITLES`.
- `set_accepted_titles(titles: Iterable[str]) -> None` / `get_accepted_titles() -> tuple[str, ...]`.
  `set_` always unions in the defaults, dedupes, drops blanks.
- `title_matches(window_title: str, accepted: Iterable[str]) -> bool` — **pure**, unit-testable.
- `list_game_windows()` uses `title_matches(title, get_accepted_titles())`.
- `list_all_windows()` — new; same enumeration but no title filter (for discovery).
- `_require_window()` error text lists all accepted titles, not just one.

### `cli.py`
- Add global args on the top-level parser (visible to all subcommands):
  `--window-title` (action="append", metavar="TITLE", repeatable).
- In `main()`, before dispatch: merge env `YOUKAI_WINDOW_TITLES` + `args.window_title`,
  call `capture.set_accepted_titles(...)`.
- New subcommand `windows` → `_cmd_windows(args)` printing the `list_all_windows()` table
  with the scanner's pick marked (reuse the `calibrate` listing style at cli.py:478-486).

## Out of scope

- Process/exe detection (would breach the no-process-access posture for no benefit —
  title matching is sufficient and safer).
- Any bbox / navigation / OCR change (same UI confirmed).
- Auto-detecting chiaki's title (user supplies it once via flag/env after discovery).

## Risks

- **Chiaki's render surface is a child window with a different/empty title.** Mitigated by
  `youkai windows` showing *all* windows so the user finds the right one; worst case they
  pass the parent title. If the real render window has an empty title, title matching can't
  target it precisely — `pick_best_window` still selects the 16:9 largest among matches, so
  matching the launcher title may still land the right surface. Flag this if it surfaces in
  testing (escalation candidate).
- **Multiple 16:9 windows open** (retail + chiaki simultaneously): existing
  `pick_best_window` picks largest; acceptable, document it.

## Test strategy

- `title_matches` is pure → direct unit tests (default rejects "Chiaki"; accepts after add;
  case/space-insensitive; substring).
- Title resolution merge (env + flag + default union, dedupe, blanks dropped) → unit test on
  a small `resolve_accepted_titles()` helper extracted into `capture.py`.
- `list_all_windows` / `_cmd_windows` are win32-only; not unit-tested (consistent with
  existing `list_game_windows` coverage — only the pure picker is tested).
