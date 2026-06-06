"""Tests for grid navigation — scrollbar-thumb scroll-to-top detection."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from youkai_ocr.capture import calibrate
from youkai_ocr.grid import (
    DEFAULT_GRID,
    GridNavigator,
    SCROLLBAR_GROOVE_BBOX,
    SCROLLBAR_TOP_Y,
    _scrollbar_thumb_top,
)

# A real capture confirmed (by inspection + user) to be at the top of the
# Drive Disc inventory: the thumb sits just below the up-arrow.
AT_TOP_FIXTURE = Path(__file__).resolve().parents[1] / "archive" / "live_20260605" / "preflight_discs.png"


@pytest.fixture
def at_top_frame() -> Image.Image:
    if not AT_TOP_FIXTURE.exists():
        pytest.skip(f"fixture missing: {AT_TOP_FIXTURE}")
    return Image.open(AT_TOP_FIXTURE)


def test_thumb_top_detected_at_top(at_top_frame):
    """The known at-top frame reports a thumb at/above the top threshold."""
    calib = calibrate(at_top_frame)
    top = _scrollbar_thumb_top(at_top_frame, calib)
    assert top is not None
    assert top <= SCROLLBAR_TOP_Y, f"expected at-top thumb (<= {SCROLLBAR_TOP_Y}), got {top}"


def test_thumb_absent_when_groove_blank(at_top_frame):
    """A frame with the groove blacked out yields None (no false top)."""
    calib = calibrate(at_top_frame)
    arr = np.asarray(at_top_frame.convert("RGB")).copy()
    x0, y0, x1, y1 = calib.scale_bbox(SCROLLBAR_GROOVE_BBOX)
    arr[y0:y1, x0:x1] = 0  # blank the whole groove → no thumb pixels
    blanked = Image.fromarray(arr)
    assert _scrollbar_thumb_top(blanked, calib) is None


def test_thumb_lower_when_scrolled_down(at_top_frame):
    """A synthetic 'scrolled down' frame (thumb painted lower) reports a larger
    Y and is therefore not considered at-top."""
    calib = calibrate(at_top_frame)
    arr = np.asarray(at_top_frame.convert("RGB")).copy()
    x0, y0, x1, y1 = calib.scale_bbox(SCROLLBAR_GROOVE_BBOX)
    arr[y0:y1, x0:x1] = 0                       # clear existing thumb
    mid = (y0 + y1) // 2
    arr[mid:mid + 12, x0:x1] = 200              # paint a thumb mid-track
    scrolled = Image.fromarray(arr)
    top = _scrollbar_thumb_top(scrolled, calib)
    assert top is not None
    assert top > SCROLLBAR_TOP_Y, f"mid-track thumb should not read as top, got {top}"


# ── Traversal simulation ──────────────────────────────────────────────────────
# Models ZZZ's confirmed edge-row scroll behaviour to validate scan() logic
# offline: clicking the top visible row scrolls up (unless it is the first
# inventory row), clicking the bottom visible row scrolls down (unless last),
# middle rows never scroll.  Each disc's panel is a deterministic pattern so the
# tolerant fingerprint comparison distinguishes discs; disc id is encoded at
# pixel (0,0) for the test to decode the yielded frame.

class _SimZZZ:
    def __init__(self, n_discs: int, cols: int = 9, visible: int = 4):
        self.n = n_discs
        self.cols = cols
        self.visible = visible
        self.total_rows = (n_discs + cols - 1) // cols
        self.scroll_top = 0
        self.selected = 0

    def _disc_id(self, inv_row: int, col: int):
        idx = inv_row * self.cols + col
        return idx if 0 <= idx < self.n else None

    def click(self, x: int, y: int) -> None:
        col = round((x - DEFAULT_GRID.cell_0_0_center[0]) / DEFAULT_GRID.col_pitch)
        srow = round((y - DEFAULT_GRID.cell_0_0_center[1]) / DEFAULT_GRID.row_pitch)
        did = self._disc_id(self.scroll_top + srow, col)
        if did is not None:                       # empty cell → selection unchanged
            self.selected = did
        if srow == 0 and self.scroll_top > 0:
            self.scroll_top -= 1
        elif srow == self.visible - 1 and self.scroll_top + self.visible < self.total_rows:
            self.scroll_top += 1

    def frame(self) -> Image.Image:
        a = np.zeros((1080, 1920, 3), dtype=np.uint8)
        # Encode the disc id at pixel (0,0) so the test can decode the read.
        a[0, 0] = (self.selected & 0xFF, (self.selected >> 8) & 0xFF, 0)
        # Draw a scrollbar thumb in the groove whose top edge tracks scroll_top,
        # so _scroll_down can confirm a scroll via _scrollbar_thumb_top.
        from youkai_ocr.grid import SCROLLBAR_TOP_Y
        per_row = 5  # px the thumb drops per scrolled row (well above STALL noise)
        top = int(SCROLLBAR_TOP_Y - 8 + self.scroll_top * per_row)
        a[top:top + 11, 1362:1370] = 200
        return Image.fromarray(a, "RGB")


def _run_sim(n_discs: int, monkeypatch, total=...) -> list[int]:
    import youkai_ocr.grid as grid_mod

    monkeypatch.setattr(grid_mod.time, "sleep", lambda *_a, **_k: None)  # no real settles
    sim = _SimZZZ(n_discs)
    calib = calibrate(sim.frame())
    nav = GridNavigator(sim.frame, calib)
    nav._scroll_to_top = lambda: setattr(sim, "scroll_top", 0)  # scrollbar rewind stubbed
    nav._click = sim.click
    arg = n_discs if total is ... else total
    got = []
    for _idx, _row, frame in nav.scan(arg):
        r, g, _ = frame.getpixel((0, 0))
        got.append(r + (g << 8))
    return got


def test_scan_reads_every_disc_in_order_full_last_row(monkeypatch):
    n = 8 * 9   # 8 full rows
    assert _run_sim(n, monkeypatch) == list(range(n))


def test_scan_reads_every_disc_in_order_partial_last_row(monkeypatch):
    n = 8 * 9 - 4   # last row has 5 discs, 4 trailing empty cells
    assert _run_sim(n, monkeypatch) == list(range(n))


def test_scan_single_screen_no_scroll(monkeypatch):
    n = 3 * 9   # fits in the first three rows, no scroll loop needed
    assert _run_sim(n, monkeypatch) == list(range(n))


def test_scan_exactly_visible_rows(monkeypatch):
    n = 4 * 9   # exactly rows_visible rows; last row is the bottom, no scroll
    assert _run_sim(n, monkeypatch) == list(range(n))


def test_scan_thumb_fallback_no_count(monkeypatch):
    # Without a count, the thumb fallback should still read a tidy full grid.
    n = 6 * 9
    assert _run_sim(n, monkeypatch, total=None) == list(range(n))
