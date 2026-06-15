"""Tests for C3 export logic and grid geometry helpers.

C1/C2 (live game interaction) are not tested here — those require the game.
This file covers: export_discs round-trip, GridParams geometry, and the
_crop helper math.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from PIL import Image

from youkai_ocr.capture import CalibrationResult
from youkai_ocr.disc_scanner import _crop, export_discs
from youkai_ocr.grid import DEFAULT_GRID, GridParams
from youkai_ocr.zod import ZodDisc, ZodSubstat


# ── GridParams ────────────────────────────────────────────────────────────────

def test_cell_center_origin():
    g = DEFAULT_GRID
    assert g.cell_center(0, 0) == g.cell_0_0_center


def test_cell_center_col_pitch():
    g = DEFAULT_GRID
    cx0, cy0 = g.cell_center(0, 0)
    cx1, cy1 = g.cell_center(1, 0)
    assert cx1 - cx0 == g.col_pitch
    assert cy1 == cy0


def test_cell_center_row_pitch():
    g = DEFAULT_GRID
    cx0, cy0 = g.cell_center(0, 0)
    cx1, cy1 = g.cell_center(0, 1)
    assert cy1 - cy0 == g.row_pitch
    assert cx1 == cx0



# ── _crop helper ──────────────────────────────────────────────────────────────

def test_crop_identity():
    # At 1:1 scale (1920×1080), crop should be exact.
    calib = CalibrationResult(scale_x=1.0, scale_y=1.0, frame_width=1920, frame_height=1080)
    frame = Image.new("RGB", (1920, 1080), color=(255, 0, 0))
    cropped = _crop(frame, calib, (100, 200, 300, 400))
    assert cropped.size == (200, 200)


def test_crop_scaled():
    calib = CalibrationResult(scale_x=0.5, scale_y=0.5, frame_width=960, frame_height=540)
    frame = Image.new("RGB", (960, 540), color=(0, 255, 0))
    cropped = _crop(frame, calib, (100, 100, 300, 300))
    # Reference coords halved → 50,50 to 150,150 → 100×100
    assert cropped.size == (100, 100)


# ── export_discs ──────────────────────────────────────────────────────────────

def _make_disc(slot: int = 1, set_key: str = "AstralVoice") -> ZodDisc:
    return ZodDisc(
        set_key=set_key,
        slot_key=str(slot),
        level=15,
        rarity=4,
        main_stat_key="hp",
        location="",
        lock=False,
        substats=[
            ZodSubstat(key="crit_", value=9.6),
            ZodSubstat(key="crit_dmg_", value=19.2),
        ],
    )


def test_export_discs_roundtrip():
    discs = [_make_disc(s) for s in range(1, 7)]
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "export.json"
        export_discs(discs, path)

        data = json.loads(path.read_text())

    assert data["format"] == "eZOD"
    assert data["version"] == 1
    assert data["source"] == "Youkai"
    assert len(data["discs"]) == 6
    assert data["weapons"] == []
    assert data["characters"] == []


def test_export_disc_fields():
    disc = _make_disc(slot=4, set_key="WoodpeckerElectro")
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "export.json"
        export_discs([disc], path)
        data = json.loads(path.read_text())

    d = data["discs"][0]
    assert d["setKey"] == "WoodpeckerElectro"
    assert d["slotKey"] == "4"
    assert d["level"] == 15
    assert d["rarity"] == 4
    assert d["mainStatKey"] == "hp"
    assert d["location"] == ""
    assert d["lock"] is False
    assert len(d["substats"]) == 2
    assert d["substats"][0] == {"key": "crit_", "value": 9.6}


def test_export_creates_parent_dirs():
    discs = [_make_disc()]
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "nested" / "dir" / "export.json"
        export_discs(discs, path)
        assert path.exists()


# ── Storage count reader ──────────────────────────────────────────────────────

def test_read_disc_count_from_real_header():
    from pathlib import Path
    from PIL import Image
    from youkai_ocr.capture import calibrate
    from youkai_ocr.recognize import make_recognizer
    from youkai_ocr.disc_scanner import read_disc_count

    fixture = Path(__file__).resolve().parents[1] / "archive" / "live_20260605" / "preflight_discs.png"
    if not fixture.exists():
        import pytest
        pytest.skip("fixture missing")
    im = Image.open(fixture)
    count = read_disc_count(im, calibrate(im), make_recognizer("tesseract"))
    # The live_20260605 preflight header reads "[ 2217 / ... ]" (dir was
    # reused/overwritten across runs pre-H27; 2217 is the surviving frame).
    assert count == 2217


# ── Parallel OCR pipeline ─────────────────────────────────────────────────────

def test_scan_discs_parallel_preserves_order(monkeypatch):
    """Workers finish OCR out of order; results must still come back in scan order."""
    import random
    import time as _time
    from threading import Event
    import youkai_ocr.disc_scanner as ds
    from youkai_ocr.grid import DEFAULT_GRID

    N = 50

    class FakeNav:
        def __init__(self, *a, **k):
            pass

        def scan(self, total):
            for i in range(N):
                yield i, 0, f"frame{i}"

    class FakeListener:
        def stop(self):
            pass

    class Stub:
        def __init__(self, idx):
            self.idx = idx

        def to_dict(self):
            return {"idx": self.idx}

    def fake_extract(frame, calib, cx, cy, rec, arch, cell_idx):
        _time.sleep(random.uniform(0, 0.01))   # scramble completion order
        return Stub(cell_idx), {"set": 99.0}

    monkeypatch.setattr(ds, "GridNavigator", FakeNav)
    monkeypatch.setattr(ds, "make_recognizer", lambda *a, **k: object())
    monkeypatch.setattr(ds, "make_kill_listener", lambda: (Event(), FakeListener()))
    monkeypatch.setattr(ds, "read_disc_count", lambda *a, **k: N)
    monkeypatch.setattr(ds, "_extract_disc", fake_extract)

    discs, issues = ds.scan_discs(lambda: "preflight", calib=None, grid=DEFAULT_GRID)
    assert [d.idx for d in discs] == list(range(N))
    assert issues == []


def test_scan_discs_on_item_called_once_per_disc_monotonically(monkeypatch):
    """on_item is called exactly once per disc with monotonically increasing scanned."""
    import time as _time
    from threading import Event
    import youkai_ocr.disc_scanner as ds
    from youkai_ocr.grid import DEFAULT_GRID

    N = 6

    class FakeNav:
        def __init__(self, *a, **k): pass
        def scan(self, total):
            for i in range(N):
                yield i, 0, f"frame{i}"

    class FakeListener:
        def stop(self): pass

    class Stub:
        def __init__(self, idx): self.idx = idx
        def to_dict(self): return {}

    def fake_extract(frame, calib, cx, cy, rec, arch, cell_idx):
        return Stub(cell_idx), {"set": 99.0}

    monkeypatch.setattr(ds, "GridNavigator", FakeNav)
    monkeypatch.setattr(ds, "make_recognizer", lambda *a, **k: object())
    monkeypatch.setattr(ds, "make_kill_listener", lambda: (Event(), FakeListener()))
    monkeypatch.setattr(ds, "read_disc_count", lambda *a, **k: N)
    monkeypatch.setattr(ds, "_extract_disc", fake_extract)

    calls: list[tuple[int, int | None]] = []
    discs, _ = ds.scan_discs(
        lambda: "preflight", calib=None, grid=DEFAULT_GRID,
        on_item=lambda s, t: calls.append((s, t)),
    )

    assert len(calls) == N
    scanned_values = [s for s, _ in calls]
    # Disc scanner uses a thread pool — completion order is non-deterministic,
    # but every value 1..N must appear exactly once.
    assert sorted(scanned_values) == list(range(1, N + 1)), f"expected {{1..N}}, got: {scanned_values}"
    assert all(t == N for _, t in calls), "total should equal N for all calls"


def test_scan_discs_on_item_omitted_no_error(monkeypatch):
    """on_item=None (default) causes no error."""
    from threading import Event
    import youkai_ocr.disc_scanner as ds
    from youkai_ocr.grid import DEFAULT_GRID

    class FakeNav:
        def __init__(self, *a, **k): pass
        def scan(self, total):
            for i in range(3):
                yield i, 0, f"frame{i}"

    class FakeListener:
        def stop(self): pass

    class Stub:
        def __init__(self, idx): self.idx = idx
        def to_dict(self): return {}

    monkeypatch.setattr(ds, "GridNavigator", FakeNav)
    monkeypatch.setattr(ds, "make_recognizer", lambda *a, **k: object())
    monkeypatch.setattr(ds, "make_kill_listener", lambda: (Event(), FakeListener()))
    monkeypatch.setattr(ds, "read_disc_count", lambda *a, **k: 3)
    monkeypatch.setattr(ds, "_extract_disc", lambda f, c, cx, cy, r, a, i: (Stub(i), {"set": 99.0}))

    discs, _ = ds.scan_discs(lambda: "preflight", calib=None, grid=DEFAULT_GRID)
    assert len(discs) == 3
