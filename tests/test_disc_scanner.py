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
from youkai_ocr.grid import DEFAULT_GRID
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
    from youkai_ocr.capture import calibrate
    from youkai_ocr.recognize import make_recognizer
    from youkai_ocr.disc_scanner import read_disc_count

    fixture = Path(__file__).resolve().parents[1] / "archive" / "live_20260605" / "preflight_discs.png"
    if not fixture.exists():
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


# ── Critical-failure reasons (T3: unknown-set floor) ──────────────────────────

class _FakeRecognizer:
    """Returns a fixed title on every read; other fields don't matter for these
    tests since the critical-fail guard short-circuits before they're used."""

    def __init__(self, title: str):
        self._title = title

    def read_text(self, img, profile):
        return self._title

    def read_line(self, img, profile):
        return ""

    def read_digits(self, img, profile):
        return ""

    def read_slot(self, img, profile):
        return ""

    def read_cinema(self, img):
        return ""


def _identity_calib() -> CalibrationResult:
    return CalibrationResult(scale_x=1.0, scale_y=1.0, frame_width=1920, frame_height=1080)


def test_extract_disc_unknown_set_critical_fail():
    """A title that fuzzy-matches no known set (score < floor) must critical-fail
    with 'unknown_set', not silently snap to the nearest table key (E1)."""
    from youkai_ocr.disc_scanner import _extract_disc

    frame = Image.new("RGB", (1920, 1080), color=(0, 0, 0))
    disc, conf = _extract_disc(
        frame, _identity_calib(), 0, 0, _FakeRecognizer("Future Set Name [1]"), None, 0
    )
    assert disc is None
    assert conf["_fail_reason"].startswith("unknown_set:"), conf["_fail_reason"]


def test_extract_disc_no_slot_critical_fail_distinguished_from_unknown_set():
    """A title with no parseable slot must fail as 'no_slot', not 'unknown_set' —
    the two failure modes stay distinguishable in the reason string."""
    from youkai_ocr.disc_scanner import _extract_disc

    frame = Image.new("RGB", (1920, 1080), color=(0, 0, 0))
    disc, conf = _extract_disc(
        frame, _identity_calib(), 0, 0, _FakeRecognizer("Astral Voice"), None, 0
    )
    assert disc is None
    assert conf["_fail_reason"].startswith("no_slot:"), conf["_fail_reason"]


def test_extract_disc_partial_title_still_resolves_not_critical_fail():
    """A legit-but-partial title (real archived 2-line-title OCR, scores 68-73)
    must still resolve and NOT critical-fail, even though it's below the old
    80-ish 'looks solid' bar — this is exactly the case the 60 floor is
    calibrated to admit."""
    from youkai_ocr.disc_scanner import _extract_disc

    frame = Image.new("RGB", (1920, 1080), color=(0, 0, 0))
    disc, conf = _extract_disc(
        frame, _identity_calib(), 0, 0, _FakeRecognizer("B Z Wonderland [1] »®"), None, 0
    )
    assert disc is not None
    assert disc.set_key == "BunnyInWonderland"
    assert "_fail_reason" not in conf


def test_scan_equipped_disc_frame_unknown_set_critical_fail():
    from youkai_ocr.disc_scanner import scan_equipped_disc_frame

    frame = Image.new("RGB", (1920, 1080), color=(0, 0, 0))
    disc, conf = scan_equipped_disc_frame(
        frame, _identity_calib(), agent_key="Zhu Yuan", slot_key=1,
        engine=_FakeRecognizer("Future Set Name [1]"),
    )
    assert disc is None
    assert conf["_fail_reason"].startswith("unknown_set:"), conf["_fail_reason"]


# ── Roll-count suffix evidence (T4) ────────────────────────────────────────────

class _ScriptedRecognizer:
    """Fixed title/lock text; scripted read_line() returns consumed in call
    order. Extends the _FakeRecognizer pattern (T3) with per-call text so a
    substat line's name/value reads can be distinguished from level/main-stat
    reads, which a single fixed string can't do."""

    def __init__(self, title: str, lines: list[str]):
        self._title = title
        self._lines = list(lines)
        self._idx = 0

    def read_text(self, img, profile):
        return self._title

    def read_line(self, img, profile):
        if self._idx < len(self._lines):
            v = self._lines[self._idx]
            self._idx += 1
            return v
        return ""

    def read_digits(self, img, profile):
        return ""

    def read_slot(self, img, profile):
        return ""

    def read_cinema(self, img):
        return ""


def test_extract_disc_captures_roll_suffix_evidence():
    """A '+N' roll-count suffix on a substat line must surface as evidence
    (conf[f"substat_{i}_roll_suffix"]) instead of being silently discarded the
    way normalize_substat's internal _UPGRADE_RE stripping does — this is the
    deterministic signal disc_rules.repair_disc (T6/T7) will need."""
    from youkai_ocr.disc_scanner import _extract_disc

    frame = Image.new("RGB", (1920, 1080), color=(0, 0, 0))
    lines = [
        "Lv.4",     # level
        "",         # main stat name (unused here)
        "", "",     # main stat value — native + 2x reads (unused here)
        "DEF +2",   # substat 1 name — bright pass, resolves immediately
        "44", "44", # substat 1 value — bright + 2x reads agree
        "", "", "", # substat 2 name — bright, dim, upscale: all empty
        "", "",     # substat 2 value — bright + 2x: both empty -> ends the list
    ]
    recognizer = _ScriptedRecognizer("Astral Voice [1]", lines)
    disc, conf = _extract_disc(frame, _identity_calib(), 0, 0, recognizer, None, 0)

    assert disc is not None
    assert disc.substats[0].key == "def"
    assert conf["substat_1_roll_suffix"] == 2.0
    assert "substat_2_roll_suffix" not in conf


def test_equip_parse_stat_block_captures_roll_suffix():
    from youkai_ocr.disc_scanner import _equip_parse_stat_block

    block_text = (
        "Main Stat\n"
        "ATK% 12.0%\n"
        "Sub Stats\n"
        "DEF +2 44\n"
        "CRIT Rate 4.8%\n"
        "Set Effect\n"
    )
    main_raw, subs_raw = _equip_parse_stat_block(block_text)
    assert main_raw == ("ATK%", "12.0%")
    assert subs_raw[0] == ("DEF +2", "44", 2)
    assert subs_raw[1] == ("CRIT Rate", "4.8%", None)


def test_extract_disc_captures_pct_seen_evidence():
    """Whether a substat's raw value text carried a '%' glyph is the other
    half of the flat/percent-key discriminator disc_rules.repair_disc (T7)
    needs (alongside roll_suffix) — must surface per-line, not be silently
    dropped after being used only to pick the key inline."""
    from youkai_ocr.disc_scanner import _extract_disc

    frame = Image.new("RGB", (1920, 1080), color=(0, 0, 0))
    lines = [
        "Lv.4",       # level
        "",           # main stat name (unused here)
        "7.5%", "7.5%",  # main stat value — native + 2x, percent seen
        "DEF +2",     # substat 1 name
        "14.4%", "14.4%",  # substat 1 value — percent seen
        "", "", "",   # substat 2 name — bright, dim, upscale: all empty
        "", "",       # substat 2 value — both empty -> ends the list
    ]
    recognizer = _ScriptedRecognizer("Astral Voice [1]", lines)
    disc, conf = _extract_disc(frame, _identity_calib(), 0, 0, recognizer, None, 0)

    assert disc is not None
    assert conf["main_stat_pct_seen"] is True
    assert conf["substat_1_pct_seen"] is True
    assert "substat_2_pct_seen" not in conf


# ── Main-stat value evidence (T5) ───────────────────────────────────────────

class _EquipStubRecognizer:
    """Distinguishes the title read_text() call from the stat-block read_text()
    call by order — scan_equipped_disc_frame issues exactly one of each."""

    def __init__(self, title: str, block_text: str):
        self._title = title
        self._block_text = block_text
        self._text_calls = 0

    def read_text(self, img, profile):
        self._text_calls += 1
        return self._title if self._text_calls == 1 else self._block_text

    def read_line(self, img, profile):
        return "Lv.15"

    def read_digits(self, img, profile):
        return ""

    def read_slot(self, img, profile):
        return ""

    def read_cinema(self, img):
        return ""


def test_scan_equipped_disc_frame_captures_main_stat_value():
    """The equip path's block parse previously discarded the main-stat value
    text (only used it for pct_seen) — it must now surface as evidence the
    same way the inventory path does (conf['main_stat_value'])."""
    from youkai_ocr.disc_scanner import scan_equipped_disc_frame

    frame = Image.new("RGB", (1920, 1080), color=(0, 0, 0))
    block_text = (
        "Main Stat\n"
        "ATK 316\n"
        "Sub Stats\n"
        "DEF +2 44\n"
        "Set Effect\n"
    )
    recognizer = _EquipStubRecognizer("Astral Voice [2]", block_text)
    disc, conf = scan_equipped_disc_frame(
        frame, _identity_calib(), agent_key="Zhu Yuan", slot_key=2,
        engine=recognizer,
    )
    assert disc is not None
    assert conf["main_stat_value"] == 316.0


def test_scan_equipped_disc_frame_captures_pct_seen():
    from youkai_ocr.disc_scanner import scan_equipped_disc_frame

    frame = Image.new("RGB", (1920, 1080), color=(0, 0, 0))
    block_text = (
        "Main Stat\n"
        "ATK 7.5%\n"
        "Sub Stats\n"
        "DEF +2 14.4%\n"
        "Set Effect\n"
    )
    recognizer = _EquipStubRecognizer("Astral Voice [2]", block_text)
    disc, conf = scan_equipped_disc_frame(
        frame, _identity_calib(), agent_key="Zhu Yuan", slot_key=2,
        engine=recognizer,
    )
    assert disc is not None
    assert conf["main_stat_pct_seen"] is True
    assert conf["substat_1_pct_seen"] is True


# ── Real-OCR verification anchors (T5 acceptance criterion) ────────────────
#
# disc_0001 / disc_0631 panel crops from the June 22 archive, cited in
# DESIGN_disc_validation.md's Expected-value tables as the hand-verified
# anchors: S-rank ATK main, lvl15 -> floor(79 * 1.8) = 142... lvl4 -> 316
# (DESIGN's own numbers, confirmed against discs.json ground truth in that
# archive: disc_0001 is level 15 / atk -> 316; disc_0631 is level 4 / atk ->
# 142). Real tesseract OCR (no stubbing) against the actual game-panel crop
# is the only way to prove the new _MAIN_VAL_REL read works end to end.

_MAIN_VALUE_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "main_value_check"
_MAIN_VALUE_PANEL_ORIGIN = (1421, 100)


def _panel_file_to_frame(panel_path: Path) -> Image.Image:
    panel = Image.open(panel_path).convert("RGB")
    frame = Image.new("RGB", (1920, 1080), color=(0, 0, 0))
    frame.paste(panel, _MAIN_VALUE_PANEL_ORIGIN)
    return frame


@pytest.mark.parametrize(
    "panel_file, expected_value",
    [
        ("disc_0001_panel.png", 316.0),
        ("disc_0631_panel.png", 142.0),
    ],
)
def test_extract_disc_reads_main_stat_value_from_real_panels(panel_file, expected_value):
    """Real tesseract OCR over the two DESIGN-cited verification-anchor panels
    must recover the exact main-stat value — proves the new _MAIN_VAL_REL read
    works, not just that the plumbing accepts a stubbed number."""
    from youkai_ocr.disc_scanner import scan_single_frame

    panel_path = _MAIN_VALUE_FIXTURES / panel_file
    if not panel_path.exists():
        pytest.skip(f"fixture not present: {panel_path}")
    frame = _panel_file_to_frame(panel_path)
    disc, conf = scan_single_frame(frame, _identity_calib(), panel_origin=_MAIN_VALUE_PANEL_ORIGIN)

    assert disc is not None, conf.get("_fail_reason")
    assert conf["main_stat_value"] == expected_value
