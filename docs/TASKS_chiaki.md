# TASKS — Chiaki window support

Atomic tasks. Do one, run its tests, report, stop. See `DESIGN_chiaki.md`.

---

## TASK-1 — Generalize title matching in `capture.py` (pure core)  ✅ DONE 2026-06-13
**Files:** `src/youkai_ocr/capture.py`
**Do:**
- Replace `GAME_TITLE` const with `DEFAULT_GAME_TITLES = ("ZenlessZoneZero",)` and module
  state `_accepted_titles`.
- Add pure `title_matches(window_title, accepted) -> bool` (reuses `_normalize_title`).
- Add `resolve_accepted_titles(extra=None, env=None) -> tuple[str,...]` — merges defaults +
  comma-split env string + extra iterable; dedupe (preserve order), drop blanks.
- Add `set_accepted_titles(titles)` / `get_accepted_titles()`.
- Point `list_game_windows()` at `title_matches(title, get_accepted_titles())`.
- Update `_require_window()` error string to list `get_accepted_titles()`.
**Acceptance / tests (new `tests/test_title_match.py`):**
- default accepts "ZenlessZoneZero" / "Zenless Zone Zero"; rejects "Chiaki".
- after `resolve_accepted_titles(extra=["Chiaki"])`, "chiaki" (any case/space) matches; retail still matches.
- `resolve_accepted_titles(env="A, ,B")` → defaults + A + B, no blanks, deduped.
- `pytest tests/test_window_pick.py tests/test_title_match.py` green.

## TASK-2 — Add `list_all_windows()` for discovery  ✅ DONE 2026-06-13
**Files:** `src/youkai_ocr/capture.py`
**Do:** Clone `list_game_windows()` enumeration without the title filter; include all
visible, non-iconic, non-zero-client top-level windows. Return same dict shape (+ keep title).
**Acceptance:** importable; on non-win32 returns `[]` (mirrors `list_game_windows`). No unit
test (win32-only path); manual check noted in LOG.

## TASK-3 — Wire CLI config (env + `--window-title`)  ✅ DONE 2026-06-13
**Files:** `src/youkai_ocr/cli.py`
**Do:** Add global `--window-title` (append). In `main()` before dispatch call
`capture.set_accepted_titles(capture.resolve_accepted_titles(extra=args.window_title, env=os.environ.get("YOUKAI_WINDOW_TITLES")))`.
**Acceptance:** `youkai --window-title Chiaki calibrate --file <png>` runs;
`YOUKAI_WINDOW_TITLES=Chiaki youkai windows` honored (verify after TASK-4). Existing
commands unchanged when flag/env absent.

## TASK-4 — Add `youkai windows` discovery subcommand  ✅ DONE 2026-06-13
**Files:** `src/youkai_ocr/cli.py`
**Do:** New subparser `windows`; `_cmd_windows` prints a table of `list_all_windows()`
(hwnd, w×h, 16:9 flag, position, title) and marks the one `pick_best_window` over the
*title-matched* subset would choose. Reuse listing style at cli.py:478-486.
**Acceptance:** `youkai windows` lists windows on Windows; prints a clear "run Chiaki, then
copy its title into --window-title" hint when no match. Documented in RUNBOOK.

## TASK-3b — ship `chiaki-ng` as a built-in default title  ✅ DECIDED + DONE 2026-06-13
**Files:** `src/youkai_ocr/capture.py`
**Do:** Set `DEFAULT_GAME_TITLES = ("ZenlessZoneZero", "chiaki-ng")` so it works with no
flag/env. (Decision 2026-06-13: accepted the low false-match risk — `pick_best_window` +
16:9 check + screen-assert gates protect against a non-ZZZ stream.)
**Acceptance:** default `resolve_accepted_titles()` accepts both "ZenlessZoneZero" and
"chiaki-ng"; covered by TASK-1 tests.

## TASK-5 — Docs  ✅ DONE 2026-06-13
**Files:** `README.md`, `docs/RUNBOOK.md`
**Do:** Document chiaki support: the `youkai windows` discovery recipe, `--window-title`
flag, `YOUKAI_WINDOW_TITLES` env var, and that retail still works unchanged.
**Acceptance:** README has a "Chiaki / alternate client" subsection with the 3-step recipe
(run Chiaki → `youkai windows` → `--window-title "<title>"`).
