"""Tests for D1/D2: W-Engine scanner helpers and export logic."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from youkai_ocr.capture import CalibrationResult
from youkai_ocr.matchers import count_filled_stars
from youkai_ocr.normalizer import parse_level_with_ascension
from youkai_ocr.wengine_scanner import _crop, export_engines
from youkai_ocr.zod import ZodWEngine


# ── parse_level_with_ascension ────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected_level,expected_asc", [
    ("Lv. 10/10",  10, 0),
    ("Lv. 20/20",  20, 1),
    ("Lv. 30/30",  30, 2),
    ("Lv. 40/40",  40, 3),
    ("Lv. 50/50",  50, 4),
    ("Lv. 60/60",  60, 5),
    # Partial ascension: level below the cap
    ("Lv. 15/20",  15, 1),
    ("Lv. 1/10",    1, 0),
    # No slash: level only, ascension falls back to 0
    ("Lv 60",      60, 0),
    ("60",         60, 0),
    # OCR noise
    ("Lv. 40 /40", 40, 3),
])
def test_parse_level_with_ascension(text, expected_level, expected_asc):
    level, asc = parse_level_with_ascension(text)
    assert level == expected_level
    assert asc == expected_asc


def test_parse_level_with_ascension_empty():
    level, asc = parse_level_with_ascension("")
    assert level == 0
    assert asc == 0


# ── count_filled_stars ────────────────────────────────────────────────────────

def _make_star_strip(n_filled: int, width: int = 188, height: int = 34) -> Image.Image:
    """Build a synthetic star strip: first n_filled sections gold, rest grey."""
    arr = np.zeros((height, width, 3), dtype=np.uint8)
    section_w = width // 5
    for i in range(5):
        x0 = i * section_w
        x1 = x0 + section_w
        if i < n_filled:
            # Gold star color: R=245, G=200, B=33
            arr[:, x0:x1] = [245, 200, 33]
        else:
            # Unfilled: grey
            arr[:, x0:x1] = [100, 100, 100]
    return Image.fromarray(arr, "RGB")


@pytest.mark.parametrize("n_filled", [1, 2, 3, 4, 5])
def test_count_filled_stars_gold(n_filled):
    strip = _make_star_strip(n_filled)
    assert count_filled_stars(strip) == n_filled


def test_count_filled_stars_all_grey_returns_1():
    strip = _make_star_strip(0)
    # All grey — no gold detected; fallback to 1
    assert count_filled_stars(strip) == 1


# ── _crop helper ──────────────────────────────────────────────────────────────

def test_crop_identity():
    calib = CalibrationResult(scale_x=1.0, scale_y=1.0, frame_width=1920, frame_height=1080)
    frame = Image.new("RGB", (1920, 1080), color=(0, 128, 255))
    cropped = _crop(frame, calib, (100, 200, 400, 500))
    assert cropped.size == (300, 300)


# ── export_engines round-trip ─────────────────────────────────────────────────

def _make_engine(key: str = "BashfulDemon") -> ZodWEngine:
    return ZodWEngine(
        key=key,
        level=60,
        ascension=5,
        refinement=1,
        location="",
        lock=False,
    )


def test_export_engines_roundtrip():
    engines = [_make_engine("BashfulDemon"), _make_engine("Housekeeper")]
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "export.json"
        export_engines(engines, path)
        data = json.loads(path.read_text())

    assert data["format"] == "GOOD"
    assert data["version"] == 1
    assert data["source"] == "Youkai"
    assert len(data["weapons"]) == 2
    assert data["discs"] == []
    assert data["characters"] == []


def test_export_engine_fields():
    eng = ZodWEngine(key="FusionCompiler", level=40, ascension=3, refinement=2, location="Zhu Yuan", lock=True)
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "export.json"
        export_engines([eng], path)
        data = json.loads(path.read_text())

    w = data["weapons"][0]
    assert w["key"] == "FusionCompiler"
    assert w["level"] == 40
    assert w["ascension"] == 3
    assert w["refinement"] == 2
    assert w["location"] == "Zhu Yuan"
    assert w["lock"] is True


def test_export_creates_parent_dirs():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "nested" / "dir" / "export.json"
        export_engines([_make_engine()], path)
        assert path.exists()


# ── T5: on_item callback ──────────────────────────────────────────────────────

def test_scan_engines_on_item_called_once_per_engine_monotonically(monkeypatch):
    """on_item is called exactly once per engine with monotonically increasing scanned."""
    from threading import Event
    import youkai_ocr.wengine_scanner as ws
    from youkai_ocr.grid import DEFAULT_GRID

    N = 5

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
        return Stub(cell_idx), {"key": 99.0}

    monkeypatch.setattr(ws, "GridNavigator", FakeNav)
    monkeypatch.setattr(ws, "make_recognizer", lambda *a, **k: object())
    monkeypatch.setattr(ws, "make_kill_listener", lambda: (Event(), FakeListener()))
    monkeypatch.setattr(ws, "read_engine_count", lambda *a, **k: N)
    monkeypatch.setattr(ws, "_extract_engine", fake_extract)

    calls: list[tuple[int, int | None]] = []
    ws.scan_engines(
        lambda: "preflight", calib=None, grid=DEFAULT_GRID,
        on_item=lambda s, t: calls.append((s, t)),
    )

    assert len(calls) == N
    scanned_values = [s for s, _ in calls]
    assert scanned_values == list(range(1, N + 1)), f"not monotonically increasing: {scanned_values}"
    assert all(t == N for _, t in calls), "total should equal N for all calls"


def test_scan_engines_on_item_omitted_no_error(monkeypatch):
    """on_item=None (default) causes no error."""
    from threading import Event
    import youkai_ocr.wengine_scanner as ws
    from youkai_ocr.grid import DEFAULT_GRID

    class FakeNav:
        def __init__(self, *a, **k): pass
        def scan(self, total):
            for i in range(2):
                yield i, 0, f"frame{i}"

    class FakeListener:
        def stop(self): pass

    class Stub:
        def __init__(self, idx): self.idx = idx
        def to_dict(self): return {}

    monkeypatch.setattr(ws, "GridNavigator", FakeNav)
    monkeypatch.setattr(ws, "make_recognizer", lambda *a, **k: object())
    monkeypatch.setattr(ws, "make_kill_listener", lambda: (Event(), FakeListener()))
    monkeypatch.setattr(ws, "read_engine_count", lambda *a, **k: 2)
    monkeypatch.setattr(ws, "_extract_engine",
                        lambda f, c, cx, cy, r, a, i: (Stub(i), {"key": 99.0}))

    engines, _ = ws.scan_engines(lambda: "preflight", calib=None, grid=DEFAULT_GRID)
    assert len(engines) == 2
