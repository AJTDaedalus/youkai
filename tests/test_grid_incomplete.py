"""Regression cover for the 2026-07-30 disc phase, which read 1962 of 2097 discs
(15 rows short) after one flat thumb window, reported status "ok", and left the
only trace in scan.log."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from youkai_ocr.capture import calibrate
from youkai_ocr.grid import SCROLL_STALL_WINDOWS, GridNavigator


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
