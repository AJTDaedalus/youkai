"""C1: Inventory grid navigator.

Iterates Drive Disc / W-Engine grid cells using synthetic mouse clicks
(pynput). Downward scroll is triggered by clicking the bottom visible row,
which causes ZZZ to auto-scroll the grid down by one row. Upward rewind
(scroll-to-top) uses the mouse wheel so disc selection is never altered.
Detects end-of-inventory / end-of-rewind by comparing grid hashes.
Supports Esc kill-switch.

Usage::

    kill, listener = make_kill_listener()
    nav = GridNavigator(capture_fn, calib, kill_event=kill)
    try:
        for cell_idx, visual_row, frame in nav.scan():
            process(cell_idx, visual_row, frame)
    finally:
        listener.stop()
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Callable, Generator

import numpy as np
from PIL import Image

from .capture import CalibrationResult
from .input_utils import jitter, natural_click

# ── Grid geometry ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class GridParams:
    columns: int = 9
    rows_visible: int = 4
    col_pitch: int = 135
    row_pitch: int = 175
    cell_0_0_center: tuple[int, int] = (166, 242)
    grid_bbox: tuple[int, int, int, int] = (98, 155, 1315, 865)
    scroll_anchor: tuple[int, int] = (700, 500)

    def cell_center(self, col: int, row: int) -> tuple[int, int]:
        cx = self.cell_0_0_center[0] + col * self.col_pitch
        cy = self.cell_0_0_center[1] + row * self.row_pitch
        return (cx, cy)


DEFAULT_GRID = GridParams()

# ── Timing ────────────────────────────────────────────────────────────────────

CLICK_DELAY_S    = 0.15   # post-click settle before render-gate (was 0.09 — raised so panel has a head start)
SCROLL_WAIT_S    = 0.50   # wait after scroll-trigger click for animation
CAPTURE_MIN_INTERVAL_S = 0.40   # min wall time per disc (human-cadence floor; OCR backpressure may make it longer)

# ── Render-gate: wait for the detail panel to actually appear ─────────────────
# ZZZ fades the detail panel in on each selection change.  At the old 0.09 s
# settle roughly half the captures landed during the fade (mean luma ≈ 0) and
# produced unreadable/blank crops.  The gate samples the title sub-region; once
# mean luma rises above RENDER_GATE_LUMA_FLOOR the panel is considered rendered.
RENDER_GATE_BBOX      = (1421, 270, 1860, 385)  # title area; same for discs and engines
RENDER_GATE_LUMA_FLOOR = 15   # blank/faded panel mean luma ≈ 0–5; rendered > 15
RENDER_GATE_TIMEOUT_S  = 1.0  # give up and return the best frame we have
RENDER_GATE_POLL_S     = 0.08 # re-sample interval

# ── Scroll-to-top via scrollbar thumb (reference 1920×1080 coords) ─────────────
# The grid's scrollbar groove is a near-black vertical channel containing only a
# static up-arrow, the thumb, and a static down-arrow.  Unlike the grid cells it
# is immune to selection-glow / hover / icon animation — it moves ONLY when the
# viewport scrolls — so the thumb's top edge is a clean absolute scroll position.
SCROLLBAR_GROOVE_BBOX  = (1358, 232, 1373, 872)  # x0,y0,x1,y1; excludes both arrows
SCROLLBAR_BRIGHT_THRESH = 18     # row-mean luma above this = thumb pixel (track≈0)
SCROLLBAR_TOP_Y         = 250    # thumb top edge ≤ this ⇒ rewound to first row (≈238)
SCROLLBAR_STALL_PX      = 2      # thumb rose < this between bursts ⇒ no progress
SCROLL_TO_TOP_BURST     = 6      # wheel notches per measurement (overshoot-up is safe)
SCROLL_TO_TOP_MAX_BURSTS = 80    # hard cap (~480 notches) so we can never loop forever
SCROLL_NOTCH_S          = 0.03   # gap between wheel notches within a burst
SCROLL_SETTLE_S         = 0.18   # settle after a burst before measuring the thumb

# Scroll-progress guard: the thumb moves only ~2-3 px per row on a large
# inventory, so progress is checked cumulatively over a window of scrolls rather
# than per scroll.  If the thumb descends ≤ MIN_PX across WINDOW scrolls, scrolling
# has stalled (bottom reached, or the click stopped scrolling) → stop.
SCROLL_PROGRESS_WINDOW   = 5     # scrolls between thumb-progress checks
SCROLL_PROGRESS_MIN_PX   = 4     # min thumb descent over a window to count as progress
SCAN_MAX_ROWS            = 400   # hard cap on count-free scrolling (≈ 3600 discs)
SCAN_DEBUG_FRAMES        = 30    # when debug_dir set, save this many read frames
_PANEL_DBG_BBOX          = (1421, 260, 1860, 790)  # detail-panel region for the log fingerprint

CaptureFunc = Callable[[], Image.Image]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _panel_luma(frame: Image.Image, calib: "CalibrationResult") -> float:
    """Return mean luma of the detail-panel title region (render-gate probe)."""
    x0, y0, x1, y1 = calib.scale_bbox(RENDER_GATE_BBOX)
    strip = np.asarray(frame.convert("L"))[y0:y1, x0:x1]
    return float(strip.mean()) if strip.size > 0 else 0.0


def _scrollbar_thumb_top(
    frame: Image.Image,
    calib: "CalibrationResult",
) -> float | None:
    """Return the scrollbar thumb's top edge in reference-Y, or None if absent.

    Scans the scrollbar groove (a near-black channel, both arrows excluded by
    the bbox) for the first row whose mean luma exceeds the track.  That row is
    the top of the thumb; its position is a clean, selection-independent measure
    of scroll position — smaller Y = higher up, ``SCROLLBAR_TOP_Y`` = first row.

    Unlike the grid cells, this column is untouched by selection-glow, hover, or
    icon animation — it changes ONLY when the viewport actually scrolls, which is
    why every md5-on-grid approach failed and this one does not.

    Returns reference-space Y (resolution-independent) so callers compare it
    against fixed thresholds regardless of capture resolution.
    """
    x0, y0, x1, y1 = calib.scale_bbox(SCROLLBAR_GROOVE_BBOX)
    strip = np.asarray(frame.convert("L"))[y0:y1, x0:x1]
    if strip.size == 0:
        return None
    row_mean = strip.mean(axis=1)
    bright = np.nonzero(row_mean > SCROLLBAR_BRIGHT_THRESH)[0]
    if bright.size == 0:
        return None
    top_frame_y = y0 + int(bright[0])
    return top_frame_y / calib.scale_y


# ── Navigator ─────────────────────────────────────────────────────────────────

class GridNavigator:
    """Click-driven grid iterator. Yields (cell_index, visual_row, frame)."""

    def __init__(
        self,
        capture_fn: CaptureFunc,
        calib: CalibrationResult,
        grid: GridParams = DEFAULT_GRID,
        kill_event: Event | None = None,
        debug_dir: "Path | None" = None,
    ) -> None:
        self._capture = capture_fn
        self._calib = calib
        self._grid = grid
        self._kill = kill_event or Event()
        self._mouse = None
        self._t0: float = 0.0   # scan start time for relative timestamps
        self._debug_dir = debug_dir
        if debug_dir is not None:
            debug_dir.mkdir(parents=True, exist_ok=True)

    def _mouse_ctrl(self):
        if self._mouse is None:
            from pynput.mouse import Button, Controller
            self._mouse = Controller()
        return self._mouse

    def _ref_to_screen(self, ref_x: int, ref_y: int) -> tuple[int, int]:
        return self._calib.to_screen(ref_x, ref_y)

    def _click(self, ref_x: int, ref_y: int) -> None:
        sx, sy = self._ref_to_screen(ref_x, ref_y)
        natural_click(self._mouse_ctrl(), sx, sy)

    def _ms(self) -> int:
        """Milliseconds elapsed since scan start."""
        return int((time.monotonic() - self._t0) * 1000)

    def _wait_panel_render(self, first_frame: Image.Image) -> Image.Image:
        """Spin-wait until the detail panel's title region is bright, or timeout.

        Returns the first frame whose luma exceeds the floor, or the last frame
        captured if the timeout fires (so the caller always gets *something*).
        """
        frame = first_frame
        deadline = time.monotonic() + RENDER_GATE_TIMEOUT_S
        while time.monotonic() < deadline:
            luma = _panel_luma(frame, self._calib)
            if luma >= RENDER_GATE_LUMA_FLOOR:
                return frame
            time.sleep(RENDER_GATE_POLL_S)
            frame = self._capture()
        return frame

    def _scroll_to_top(self) -> None:
        """Rewind to the first disc by watching the scrollbar thumb.

        Each burst: send ``SCROLL_TO_TOP_BURST`` wheel-up notches, settle, then
        read the thumb's top edge (``_scrollbar_thumb_top``).  Stop when the
        thumb reaches the top (``<= SCROLLBAR_TOP_Y``) or stops rising for two
        bursts (a backstop in case the absolute threshold is mis-tuned).

        The thumb is read from the scrollbar groove, which — unlike the grid
        cells — is immune to selection-glow, hover, and icon animation, so this
        does not suffer the false "movement" that defeated the md5-on-grid
        approaches.  Wheel-up overshoot is harmless (ZZZ pins the view at the
        top), and because the thumb gives an *absolute* position, large bursts
        cannot overshoot the detection — only the wall-clock cost.

        The wheel scrolls the *viewport* without moving the selection cursor, so
        when the top is reached the cursor is still glued to whatever disc it was
        on (now risen into row 0 at some column).  The scan's first action is a
        click on (0,0); to make that a genuine adjacent selection change — the
        same operation that reads discs 2-9 correctly — we leave the cursor on a
        *different* cell here (and warm the detail-panel render) by priming on
        (1,0).  Priming on (0,0) instead would make the scan's first click a
        no-op re-selection that leaves disc 1 reading the stale glued disc.
        """
        print("  [nav] scrolling to top…", end=" ", flush=True)
        t0 = time.monotonic()
        mouse = self._mouse_ctrl()
        ax, ay = self._ref_to_screen(*self._grid.scroll_anchor)

        bursts = 0
        stalls = 0
        prev_top: float | None = None
        reason = "max-bursts"

        # ── Bring the viewport to the top (scrollbar thumb) ───────────────────
        for _ in range(SCROLL_TO_TOP_MAX_BURSTS):
            if self._kill.is_set():
                reason = "killed"
                break

            top = _scrollbar_thumb_top(self._capture(), self._calib)

            if top is not None and top <= SCROLLBAR_TOP_Y:
                reason = "at-top"
                break
            if top is not None and prev_top is not None and top >= prev_top - SCROLLBAR_STALL_PX:
                stalls += 1
                if stalls >= 2:
                    reason = "stalled"
                    break
            else:
                stalls = 0
            if top is not None:
                prev_top = top

            # Wheel-up burst (overshoot is safe; thumb position can't be skipped).
            mouse.position = (ax, ay)
            for _ in range(SCROLL_TO_TOP_BURST):
                mouse.scroll(0, 1)
                time.sleep(jitter(SCROLL_NOTCH_S))
            time.sleep(SCROLL_SETTLE_S)
            bursts += 1

        # Prime the panel on (1,0) — NOT (0,0) — so the scan's first click on
        # (0,0) is a real adjacent selection change rather than a stale re-select.
        if not self._kill.is_set():
            self._click(*self._grid.cell_center(1, 0))
            time.sleep(SCROLL_WAIT_S)

        elapsed = int((time.monotonic() - t0) * 1000)
        final = self._capture()
        final_top = _scrollbar_thumb_top(final, self._calib)
        if self._debug_dir is not None:
            path = self._debug_dir / "scroll_to_top_final.png"
            final.save(path)
            print(f"\n  [nav] debug frame → {path}", end="")
        print(f"{bursts} burst(s) [{reason}], thumb_top={final_top}, {elapsed}ms")

    def _read_row(self, row: int, ncols: int | None = None):
        """Yield (col, frame, timing) for each of ``ncols`` cells in a visual row.

        A *generator*, so each click happens only as the consumer pulls the next
        cell — when the OCR pipeline applies backpressure the navigation simply
        pauses between discs, which both bounds memory and keeps the click rate
        no faster than OCR can drain.  A per-disc cadence floor
        (``CAPTURE_MIN_INTERVAL_S``) keeps the motion human even if OCR is quick.

        Uses the natural Bezier click.  ``ncols`` defaults to the full row width;
        pass a smaller value for a partial last inventory row so empty cells are
        never clicked.
        """
        if ncols is None:
            ncols = self._grid.columns
        for col in range(ncols):
            if self._kill.is_set():
                return
            t_start = time.monotonic()
            cx, cy = self._grid.cell_center(col, row)
            self._click(cx, cy)
            t_clicked = time.monotonic()
            time.sleep(jitter(CLICK_DELAY_S))
            t_settled = time.monotonic()
            frame = self._wait_panel_render(self._capture())
            t_captured = time.monotonic()
            # Human-cadence floor: don't let a disc take less than this.
            floor = jitter(CAPTURE_MIN_INTERVAL_S, 0.15)
            extra = floor - (time.monotonic() - t_start)
            if extra > 0:
                time.sleep(extra)
            yield (col, frame, (t_start, t_clicked, t_settled, t_captured))

    def _thumb(self) -> float | None:
        """Current scrollbar thumb top edge in reference-Y (None if not found)."""
        return _scrollbar_thumb_top(self._capture(), self._calib)

    def _scroll_down(self) -> None:
        """Click the bottom row once to scroll the grid down a row, then settle.

        No per-scroll thumb confirmation: for a large inventory the thumb only
        moves ~2-3 px per row, too small to gate on reliably.  The caller bounds
        the number of scrolls by the disc count and uses a *cumulative* thumb
        check (`_scroll_progressing`) to catch the case where scrolling stops
        advancing entirely.
        """
        cx, cy = self._grid.cell_center(0, self._grid.rows_visible - 1)
        self._click(cx, cy)
        time.sleep(jitter(SCROLL_WAIT_S))

    def scan(
        self, total_discs: int | None = None
    ) -> Generator[tuple[int, int, Image.Image], None, None]:
        """Yield (cell_index, visual_row, frame) for every disc, top to bottom.

        Traversal accounts for ZZZ's edge-row scrolling (confirmed live): clicking
        the top visible row scrolls up unless it is the first inventory row, and
        clicking the bottom visible row scrolls down unless it is the last; middle
        rows never scroll.  The scrollbar rewind guarantees we start at the top, so
        row 0 is the first inventory row and is safe to read in place.

        When ``total_discs`` is known (read from the storage header), traversal is
        fully deterministic — exactly ``ceil(total_discs / columns)`` rows, with
        the last row truncated to its real width — so there is no content-based
        scroll/end detection and no way to loop.  ZZZ has many near-identical
        discs (panels can match to within noise), which is precisely why content
        fingerprints can't be trusted to decide "did we scroll" or "is this empty".

        Without a count, falls back to scrolling until the scrollbar thumb stops.
        """
        self._t0 = time.monotonic()
        cols = self._grid.columns
        rows_visible = self._grid.rows_visible
        last_row = rows_visible - 1
        repeat_row = rows_visible - 2   # second-to-last: fresh content after each scroll
        cell_idx = 0

        def emit(row: int, cells: list):
            nonlocal cell_idx
            for col, frame, (t0, t1, t2, t3) in cells:
                if self._debug_dir is not None and cell_idx < SCAN_DEBUG_FRAMES:
                    frame.save(self._debug_dir / f"read_{cell_idx:03d}_r{row}c{col}.png")
                # panel fingerprint: same value on consecutive discs ⇒ selection
                # didn't change (stuck/lagged); changing ⇒ reads are working.
                pcrop = frame.crop(self._calib.scale_bbox(_PANEL_DBG_BBOX))
                psig = hashlib.md5(pcrop.tobytes()).hexdigest()[:6]
                print(
                    f"  [nav] +{self._ms():>6}ms  d{cell_idx+1:<4}  r{row}c{col}"
                    f"  panel={psig}"
                    f"  tot={int((t3-t0)*1000)}ms"
                )
                yield cell_idx, row, frame
                cell_idx += 1

        # ── Rewind viewport to the top (scrollbar-confirmed; primes the panel) ──
        self._scroll_to_top()

        if total_discs is not None and total_discs <= 0:
            return

        if total_discs is None:
            yield from self._scan_by_thumb(emit, repeat_row, last_row)
            return

        # ── Deterministic traversal from the known disc count ──────────────────
        total_rows = (total_discs + cols - 1) // cols
        last_width = total_discs - (total_rows - 1) * cols   # discs in the last row (1..cols)
        print(f"  [nav] {total_discs} discs → {total_rows} rows (last row {last_width})")

        if total_rows <= rows_visible:
            # Whole inventory fits on one screen: every row is safe to read here.
            for row in range(total_rows):
                if self._kill.is_set():
                    return
                width = last_width if row == total_rows - 1 else cols
                yield from emit(row, self._read_row(row, width))
            return

        # Top rows 0 .. repeat_row are safe to read in place.
        for row in range(repeat_row + 1):
            if self._kill.is_set():
                return
            yield from emit(row, self._read_row(row, cols))

        # Scroll down one row at a time; the freshly revealed row sits at
        # repeat_row.  This reads inventory rows repeat_row+1 .. total_rows-2.
        # A cumulative thumb check guards against scrolling that stops advancing
        # (e.g. a wrong count, or the bottom-row click no longer scrolling): over
        # SCROLL_PROGRESS_WINDOW scrolls the thumb should descend clearly, so if
        # it doesn't we bail rather than re-read the same row indefinitely.
        ckpt_thumb = self._thumb()
        none_count = 0  # consecutive None readings; too many → stall
        for i, inv_row in enumerate(range(repeat_row + 1, total_rows - 1)):
            if self._kill.is_set():
                return
            self._scroll_down()
            yield from emit(repeat_row, self._read_row(repeat_row, cols))
            if (i + 1) % SCROLL_PROGRESS_WINDOW == 0:
                now = self._thumb()
                if now is None:
                    none_count += 1
                    if none_count >= 2:
                        # Scrollbar consistently undetectable — treat as stalled.
                        print(f"  [nav] scrollbar undetectable for {none_count} windows "
                              f"at inv row {inv_row}; stopping")
                        return
                else:
                    none_count = 0
                if (ckpt_thumb is not None and now is not None
                        and now <= ckpt_thumb + SCROLL_PROGRESS_MIN_PX):
                    print(f"  [nav] scrolling stalled at inv row {inv_row} "
                          f"(thumb {ckpt_thumb:.0f}→{now:.0f}); stopping")
                    return
                # Re-read ckpt each window so an initial None can't disable the guard.
                if now is not None:
                    ckpt_thumb = now

        # The last inventory row can only sit at the bottom visible row (we can't
        # scroll past it); read just its real width.
        if not self._kill.is_set():
            yield from emit(last_row, self._read_row(last_row, last_width))

    def _scan_by_thumb(self, emit, repeat_row: int, last_row: int):
        """Count-free fallback: scroll until the scrollbar thumb stops descending.

        Less precise than the count-driven path (no exact last-row width). Uses a
        cumulative thumb check so it ends at the bottom and a hard row cap so it
        can never loop forever.
        """
        for row in range(repeat_row + 1):
            if self._kill.is_set():
                return
            yield from emit(row, self._read_row(row))

        scrolled = 0
        none_streak = 0
        while not self._kill.is_set() and scrolled < SCAN_MAX_ROWS:
            before = self._thumb()
            self._scroll_down()
            after = self._thumb()
            if before is None and after is None:
                none_streak += 1
                if none_streak >= SCROLL_PROGRESS_WINDOW:
                    print(f"  [nav] scrollbar undetectable for {none_streak} consecutive "
                          f"scrolls; stopping thumb-scan")
                    break
            else:
                none_streak = 0
            if (before is not None and after is not None
                    and after <= before + 1.0):
                break   # thumb didn't descend → bottom reached (emit nothing)
            yield from emit(repeat_row, self._read_row(repeat_row))
            scrolled += 1
        if not self._kill.is_set():
            yield from emit(last_row, self._read_row(last_row))


# ── Kill switch ───────────────────────────────────────────────────────────────

def make_kill_listener(
    kill_key=None,
    suppress_flag: list | None = None,
) -> tuple[Event, object]:
    """Return (kill_event, listener).

    kill_key: pynput Key to use as the abort key (default: Key.esc).
    suppress_flag: optional list[bool]; when suppress_flag[0] is True the
        listener ignores one key event — used by AgentNavigator to send
        programmatic Escape presses for in-game back-navigation without
        triggering the abort.
    """
    from pynput.keyboard import Key, Listener

    if kill_key is None:
        kill_key = Key.esc

    kill_event = Event()

    def on_press(key):
        if key == kill_key:
            if suppress_flag and suppress_flag[0]:
                suppress_flag[0] = False  # consume one suppression
                return
            kill_event.set()

    listener = Listener(on_press=on_press)
    listener.start()
    return kill_event, listener
