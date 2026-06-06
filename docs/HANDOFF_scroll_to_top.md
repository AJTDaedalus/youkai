# Handoff — `_scroll_to_top()` attempts & outcomes

**Status: RESOLVED 2026-06-05.** See `docs/DECISIONS.md` § D-scroll-top and
`docs/LOG_ocr.md`. Root cause was exact-md5 brittleness against ZZZ's breathing
selection-glow; fixed by reading the scrollbar thumb instead. This file is
retained as the failure history.

## Context

`youkai_ocr` is a ZZZ disc inventory scanner. `GridNavigator._scroll_to_top()`
must rewind the inventory to disc #1 before scanning begins. The scanner uses
pynput on Windows/WSL2. The game is ZZZ running on the same machine. The user's
inventory holds ~2200 discs (~245 rows at 9 columns).

## What we know about ZZZ inventory scrolling

- Clicking row 3 (bottom visible row) triggers a 1-row downward auto-scroll.
  Confirmed working; used for `_scroll_by_click()`.
- Clicking row 0 (top visible row) appears to trigger some upward movement when
  the inventory is scrolled down, but produces persistent visual hash changes
  even when already at the true top.
- Mouse wheel (positive dy = up) scrolls the viewport, but ZZZ also moves the
  selection highlight on wheel events.

## Attempts (all FAILED except where noted)

- **v1** — Click row 0, before-vs-after bottom-30% md5. Infinite loop: clicking
  row 0 de-selects rows 2-3, changing the bottom hash with no scroll.
- **v2** — Click row 0, post-settle (60 ms) vs post-wait md5. "Works beautifully"
  then "sticks on first disc and scrolls around it" — settle too short.
- **v3** — Wheel scroll, top-30% md5. "Keeps scrolling against the top" — wheel
  moves the selection highlight, changing the hash.
- **v4** — Click row 0, 150 ms settle, bottom-30% md5. Same as v2.
- **v5** — Click row 0, cross-iteration bottom-30% md5. Loop never exits;
  "something in the bottom 30% persistently changes."
- **v6** — Fixed 50 wheel-up events, no detection. Worked but insufficient: user
  has >50 rows.
- **v7** — Wheel, cross-iteration, inner cell (0,0) thumbnail md5. "Keeps bumping
  against the top"; detail panel never updates on wheel-only.
- **v8** — v7 + detail-panel md5. Panel never populated by wheel alone → constant.
- **v9** — v7 + level/lock badge md5. Superseded mid-edit.
- **v10** — Wheel + click (0,0) per iteration, thumbnail+badge+panel md5. FAILED.

## Resolution (Opus, 2026-06-05)

Every attempt detected "stopped moving" with **exact md5** of a grid region.
md5 flips on one pixel; ZZZ's breathing selection-glow + capture jitter means
the hash never repeats even when stationary → no exit. The "persistent change
at the top" (open question #1) was the glow pulse.

Fix: stop hashing the grid. Read the **scrollbar thumb** — the groove
(reference x≈1360–1372) is black except two static arrows and the thumb, which
moves only on real scroll. `_scrollbar_thumb_top()` returns the thumb top edge
(y≈238 at the top); `_scroll_to_top()` wheel-ups in bursts until the thumb
reaches the top. Absolute position ⇒ overshoot-safe ⇒ fast and bounded.
