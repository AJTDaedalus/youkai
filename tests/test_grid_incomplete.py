"""Regression cover for the 2026-07-30 disc phase, which read 1962 of 2097 discs
(15 rows short) after one flat thumb window, reported status "ok", and left the
only trace in scan.log."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from youkai_ocr.capture import calibrate
from youkai_ocr.grid import PANEL_STUCK_RECLICKS, SCROLL_STALL_WINDOWS, GridNavigator


def _frame():
    return Image.fromarray(np.zeros((1080, 1920, 3), dtype=np.uint8))


def _nav(thumb_values):
    """Navigator whose _thumb() walks thumb_values, then repeats the last one."""
    frame = _frame()
    nav = GridNavigator(lambda: frame, calibrate(frame))
    seq = list(thumb_values)
    calls = {"n": 0}

    def thumb():
        i = min(calls["n"], len(seq) - 1)
        calls["n"] += 1
        return seq[i]

    nav._thumb = thumb
    nav._scroll_down = lambda: None
    nav._scroll_to_top = lambda: None
    nav._read_row = lambda row, width=None: []
    return nav


def test_incomplete_is_none_before_scan():
    nav = _nav([100.0])
    assert nav.incomplete is None


def test_single_flat_window_does_not_end_the_scan():
    """One stale capture or dropped click reads the same thumb twice — not a stall."""
    # Descend, go flat once, then resume descending.
    thumbs = [100.0, 120.0, 120.0, 160.0, 200.0, 240.0, 280.0, 320.0, 360.0, 400.0]
    nav = _nav(thumbs)
    list(nav.scan(9 * 40))
    assert nav.incomplete is None, "bailed on a single flat window"


def test_persistent_stall_is_recorded_with_the_shortfall():
    nav = _nav([100.0])  # never moves
    total = 9 * 40
    list(nav.scan(total))
    assert nav.incomplete is not None, "a genuinely stuck scroll must be reported"
    inc = nav.incomplete
    assert inc["expected_cells"] == total
    assert inc["cells_missed"] > 0
    assert inc["cells_read"] + inc["cells_missed"] == total
    assert "stall" in inc["reason"]


def test_stall_needs_the_full_window_budget():
    """SCROLL_STALL_WINDOWS is the contract the disc-loss fix rests on."""
    assert SCROLL_STALL_WINDOWS >= 2


def test_complete_traversal_leaves_incomplete_none():
    nav = _nav([float(100 + 40 * i) for i in range(60)])
    list(nav.scan(9 * 8))
    assert nav.incomplete is None


@pytest.mark.parametrize("scanner", ["disc", "engine"])
def test_scanners_report_incomplete_traversal_as_an_issue(scanner, monkeypatch):
    """An early stop must reach issues.json, not just scan.log."""
    import youkai_ocr.disc_scanner as ds
    import youkai_ocr.wengine_scanner as ws

    mod = ds if scanner == "disc" else ws
    marker = {"reason": "scrolling stalled", "cells_missed": 135, "expected_cells": 2097}

    class FakeNav:
        incomplete = marker

        def scan(self, total=None):
            return iter(())

    monkeypatch.setattr(mod, "GridNavigator", lambda *a, **k: FakeNav())
    monkeypatch.setattr(
        mod, "make_kill_listener", lambda *a, **k: (_DummyEvent(), _DummyListener())
    )
    fn = ds.scan_discs if scanner == "disc" else ws.scan_engines
    frame = _frame()
    _, issues = fn(lambda: frame, calibrate(frame))
    truncated = [i for i in issues if i.get("status") == "incomplete_traversal"]
    assert len(truncated) == 1
    assert truncated[0]["type"] == scanner
    assert truncated[0]["cells_missed"] == 135


class _DummyEvent:
    def is_set(self):
        return False

    def set(self):
        pass


class _DummyListener:
    def stop(self):
        pass


# ── Dropped-click detection ───────────────────────────────────────────────────
# The 1.0.7 engine phase logged 4 cells whose detail panel came back byte-identical
# to the previous cell's, at r0c2/c3/c4 and r1c1.  The render gate passed them —
# it only checks the panel is lit, and a dropped click leaves the PREVIOUS item's
# panel fully rendered — so each was recorded as a duplicate of its neighbour and
# the real engine at that position was never read.  All four happened to be equipped
# and were recovered by the location reconciliation; an unequipped one would have
# been replaced by a phantom copy with nothing reported.


def _panel_nav(sig_sequence):
    """Navigator whose panel fingerprint follows sig_sequence, one entry per capture."""
    frame = _frame()
    nav = GridNavigator(lambda: frame, calibrate(frame))
    seq = list(sig_sequence)
    state = {"i": 0}

    def sig(_frame):
        i = min(state["i"], len(seq) - 1)
        state["i"] += 1
        return seq[i]

    nav._panel_sig = sig
    nav._click = lambda cx, cy: None
    nav._wait_panel_render = lambda f: f
    return nav


def test_distinct_panels_are_never_flagged():
    nav = _panel_nav(["aaa", "bbb", "ccc"])
    rows = list(nav._read_row(0, 3))
    assert [stuck for *_, stuck in rows] == [False, False, False]
    assert nav.stuck_cells == []


def test_repeated_panel_triggers_reclicks_then_flags():
    """Panel never changes → re-clicked PANEL_STUCK_RECLICKS times, then flagged."""
    nav = _panel_nav(["aaa"] * 20)
    clicks = []
    nav._click = lambda cx, cy: clicks.append((cx, cy))
    rows = list(nav._read_row(0, 2))
    assert rows[0][3] is False, "first cell has no predecessor to match"
    assert rows[1][3] is True, "second cell repeated the panel and must be flagged"
    # cell 1: 1 click.  cell 2: 1 click + PANEL_STUCK_RECLICKS retries.
    assert len(clicks) == 2 + PANEL_STUCK_RECLICKS


def test_reclick_that_succeeds_is_not_flagged():
    """A dropped click that recovers on retry must read normally, not be skipped."""
    nav = _panel_nav(["aaa", "aaa", "bbb", "ccc"])
    rows = list(nav._read_row(0, 3))
    assert [stuck for *_, stuck in rows] == [False, False, False]
    assert nav.stuck_cells == []


def test_stuck_cell_is_skipped_not_yielded_as_a_duplicate():
    frame = _frame()
    nav = GridNavigator(lambda: frame, calibrate(frame))
    nav._scroll_to_top = lambda: None
    nav._thumb = lambda: 100.0
    seq = iter(["aaa", "aaa", "aaa", "aaa", "bbb", "ccc"])
    last = {"v": "zzz"}

    def read_row(row, ncols=None):
        for col in range(ncols or 9):
            v = next(seq, last["v"])
            stuck = v == last["v"]
            last["v"] = v
            yield (col, frame, (0.0, 0.0, 0.0, 0.0), stuck)

    nav._read_row = read_row
    got = list(nav.scan(3))
    # cell 0 reads; cells 1 and 2 repeat the panel and must be dropped, not yielded.
    assert [c for c, _, _ in got] == [0]
    assert nav.stuck_cells == [1, 2]


@pytest.mark.parametrize("scanner", ["disc", "engine"])
def test_scanners_report_stuck_cells(scanner, monkeypatch):
    import youkai_ocr.disc_scanner as ds
    import youkai_ocr.wengine_scanner as ws

    mod = ds if scanner == "disc" else ws

    class FakeNav:
        incomplete = None
        stuck_cells = [2, 4, 10]

        def scan(self, total=None):
            return iter(())

    monkeypatch.setattr(mod, "GridNavigator", lambda *a, **k: FakeNav())
    monkeypatch.setattr(
        mod, "make_kill_listener", lambda *a, **k: (_DummyEvent(), _DummyListener())
    )
    fn = ds.scan_discs if scanner == "disc" else ws.scan_engines
    frame = _frame()
    _, issues = fn(lambda: frame, calibrate(frame))
    stuck = [i for i in issues if i.get("status") == "stuck_panel"]
    assert [i["cell"] for i in stuck] == [2, 4, 10]
    assert {i["type"] for i in stuck} == {scanner}
