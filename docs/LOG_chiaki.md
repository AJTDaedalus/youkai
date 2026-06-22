# LOG — Chiaki window support

## Session 2026-06-13 — Worker (Sonnet)

### Tasks completed: TASK-1, TASK-2, TASK-3, TASK-3b, TASK-4, TASK-5

All implemented as one cohesive change set (per task brief — they form a single
logical diff and share no inter-task blocking dependencies).

---

### TASK-1 + TASK-3b — capture.py: generalize title matching

**Changes (`src/youkai_ocr/capture.py`):**
- Added `Iterable` to `from typing import` line.
- Replaced `GAME_TITLE = "ZenlessZoneZero"` with:
  - `DEFAULT_GAME_TITLES: tuple[str, ...] = ("ZenlessZoneZero", "chiaki-ng")`
    (TASK-3b shipped simultaneously — no reason to separate them)
  - `_accepted_titles: tuple[str, ...] = DEFAULT_GAME_TITLES` module state
- Added four pure functions after `_normalize_title`:
  - `title_matches(window_title, accepted) -> bool` — pure, no module state
  - `resolve_accepted_titles(extra=None, env=None) -> tuple[str,...]`
  - `set_accepted_titles(titles) -> None`
  - `get_accepted_titles() -> tuple[str, ...]`
- Updated `list_game_windows()`: removed `target = _normalize_title(GAME_TITLE)`
  line; replaced `if target not in _normalize_title(title)` with
  `if not title_matches(title, get_accepted_titles())`.
- Updated `_require_window()` error message: now dynamically lists
  `get_accepted_titles()` instead of hardcoding `GAME_TITLE`.

**Deviations from spec:** None.

---

### TASK-2 — capture.py: add list_all_windows()

**Changes (`src/youkai_ocr/capture.py`):**
- Added `list_all_windows()` between the end of `list_game_windows()` and
  `pick_best_window()`. Identical EnumWindows loop, no title filter.
  Returns `[]` on non-win32 (confirmed by import smoke test on Linux).

**Deviations:** None.

---

### TASK-3 — cli.py: wire --window-title and set_accepted_titles

**Changes (`src/youkai_ocr/cli.py`):**
- Added `import os` to top-level imports.
- Added `--window-title` global arg on the top-level parser
  (`action="append"`, `metavar="TITLE"`, `default=None`).
- In `main()`, immediately after `args = parser.parse_args()` /
  `if args.command is None` guard, added:
  ```python
  from youkai_ocr import capture as _capture
  _capture.set_accepted_titles(
      _capture.resolve_accepted_titles(
          extra=args.window_title,
          env=os.environ.get("YOUKAI_WINDOW_TITLES"),
      )
  )
  ```
- Also updated the `_cmd_calibrate` hardcoded `'ZenlessZoneZero'` "no windows
  found" message to use `get_accepted_titles()` dynamically (minor bonus, stays
  correct when titles are extended).

**Deviations:** None.

---

### TASK-4 — cli.py: add `windows` subcommand

**Changes (`src/youkai_ocr/cli.py`):**
- Added `_cmd_windows(args)` function before `_cmd_calibrate`:
  - Calls `list_all_windows()` for the full enumeration.
  - Calls `list_game_windows()` for the title-matched subset.
  - Calls `pick_best_window(matched)` to find the scanner's pick.
  - Prints a table (hwnd, size, aspect ratio, position, title) marking
    `[matched]` and `<-- scanner pick`.
  - On no matches: prints the "run Chiaki, copy its title into --window-title"
    hint.
  - On non-win32: prints a clear "only available on Windows" message and returns.
- Added `subparsers.add_parser("windows", ...)` in `main()`.
- Added `elif args.command == "windows": _cmd_windows(args)` dispatch branch
  (first branch, before calibrate).

**Verification (Linux/WSL):**
```
$ python -m youkai_ocr windows
Window enumeration is only available on Windows.
```
Correct non-win32 fallback.

**Deviations:** None.

---

### TASK-5 — Docs

**Changes:**
- `README.md`: added "Chiaki / alternate client" subsection in the CLI Usage
  section with the 3-step discovery recipe, chiaki-ng built-in note, retail
  unaffected note, and the 16:9/no-black-bars caveat.
- `docs/RUNBOOK.md`: added "Chiaki / alternate client" subsection under
  "Verify window targeting" (§1) with the same 3-step recipe, env var usage,
  and the retail-unaffected note.

**Deviations:** None.

---

### Test results

```
$ python -m pytest tests/test_title_match.py tests/test_window_pick.py -v
============================= test session starts ==============================
...
collected 23 items

tests/test_title_match.py::test_defaults_include_retail PASSED
tests/test_title_match.py::test_defaults_include_chiaki_ng PASSED
tests/test_title_match.py::test_default_accepts_exact_game_title PASSED
tests/test_title_match.py::test_default_accepts_spaced_variant PASSED
tests/test_title_match.py::test_default_accepts_chiaki_ng_built_in PASSED
tests/test_title_match.py::test_default_rejects_unrelated_title PASSED
tests/test_title_match.py::test_default_rejects_blank_title PASSED
tests/test_title_match.py::test_custom_accepts_after_add PASSED
tests/test_title_match.py::test_custom_match_is_case_insensitive PASSED
tests/test_title_match.py::test_custom_match_strips_whitespace PASSED
tests/test_title_match.py::test_retail_still_matches_after_adding_chiaki PASSED
tests/test_title_match.py::test_env_comma_split PASSED
tests/test_title_match.py::test_env_drops_blanks PASSED
tests/test_title_match.py::test_env_strips_whitespace_around_commas PASSED
tests/test_title_match.py::test_defaults_always_present_with_env PASSED
tests/test_title_match.py::test_dedup_preserves_order PASSED
tests/test_title_match.py::test_no_blank_from_empty_env PASSED
tests/test_title_match.py::test_no_blank_from_none_extra PASSED
tests/test_title_match.py::test_returns_tuple PASSED
tests/test_window_pick.py::test_none_when_empty PASSED
tests/test_window_pick.py::test_prefers_16_9_over_larger_non_16_9 PASSED
tests/test_window_pick.py::test_prefers_largest_among_16_9 PASSED
tests/test_window_pick.py::test_falls_back_to_largest_when_none_16_9 PASSED

============================== 23 passed in 0.18s ==============================
```

### Import smoke tests

```
$ python -c "from youkai_ocr import capture; ..."
capture OK
DEFAULT_GAME_TITLES: ('ZenlessZoneZero', 'chiaki-ng')
get_accepted_titles(): ('ZenlessZoneZero', 'chiaki-ng')
list_all_windows (non-win32): []

$ python -c "from youkai_ocr import cli; print('cli OK')"
cli OK

$ python -m youkai_ocr --help
usage: youkai-ocr [-h] [--version] [--window-title TITLE]
                  {windows,calibrate,...}
```

All green. No escalations.
