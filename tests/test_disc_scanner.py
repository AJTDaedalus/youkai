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
from youkai_ocr.disc_scanner import _arbitrate_main_value, _crop, export_discs
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
    from youkai_ocr.disc_scanner import read_disc_count
    from youkai_ocr.recognize import make_recognizer

    fixture = (
        Path(__file__).resolve().parents[1] / "archive" / "live_20260605" / "preflight_discs.png"
    )
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
        _time.sleep(random.uniform(0, 0.01))  # scramble completion order
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
            return {}

    def fake_extract(frame, calib, cx, cy, rec, arch, cell_idx):
        return Stub(cell_idx), {"set": 99.0}

    monkeypatch.setattr(ds, "GridNavigator", FakeNav)
    monkeypatch.setattr(ds, "make_recognizer", lambda *a, **k: object())
    monkeypatch.setattr(ds, "make_kill_listener", lambda: (Event(), FakeListener()))
    monkeypatch.setattr(ds, "read_disc_count", lambda *a, **k: N)
    monkeypatch.setattr(ds, "_extract_disc", fake_extract)

    calls: list[tuple[int, int | None]] = []
    discs, _ = ds.scan_discs(
        lambda: "preflight",
        calib=None,
        grid=DEFAULT_GRID,
        on_item=lambda s, t: calls.append((s, t)),
    )

    assert len(calls) == N
    scanned_values = [s for s, _ in calls]
    # Disc scanner uses a thread pool — completion order is non-deterministic,
    # but every value 1..N must appear exactly once.
    assert sorted(scanned_values) == list(range(1, N + 1)), (
        f"expected {{1..N}}, got: {scanned_values}"
    )
    assert all(t == N for _, t in calls), "total should equal N for all calls"


def test_scan_discs_on_item_omitted_no_error(monkeypatch):
    """on_item=None (default) causes no error."""
    from threading import Event

    import youkai_ocr.disc_scanner as ds
    from youkai_ocr.grid import DEFAULT_GRID

    class FakeNav:
        def __init__(self, *a, **k):
            pass

        def scan(self, total):
            for i in range(3):
                yield i, 0, f"frame{i}"

    class FakeListener:
        def stop(self):
            pass

    class Stub:
        def __init__(self, idx):
            self.idx = idx

        def to_dict(self):
            return {}

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

    def read_digits_word(self, img, profile):
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
        frame,
        _identity_calib(),
        agent_key="Zhu Yuan",
        slot_key=1,
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

    def read_digits_word(self, img, profile):
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
        "Lv.4",  # level
        "",
        "",
        "",  # main stat name — bright + dim + 2x fallback ladder (T12), all empty
        "",
        "",  # main stat value — native + 2x reads (unused here)
        "DEF +2",  # substat 1 name — bright pass, resolves immediately
        "30",
        "30",  # substat 1 value — on-lattice (def base 15 x k=2), so T9's
        # repair_disc wiring leaves it untouched: this test is about
        # roll-suffix evidence capture, not repair behavior.
        "",
        "",
        "",  # substat 2 name — bright, dim, upscale: all empty
        "",
        "",  # substat 2 value — bright + 2x: both empty -> ends the list
    ]
    recognizer = _ScriptedRecognizer("Astral Voice [1]", lines)
    disc, conf = _extract_disc(frame, _identity_calib(), 0, 0, recognizer, None, 0)

    assert disc is not None
    assert disc.substats[0].key == "def"
    assert disc.substats[0].value == 30.0
    assert conf["substat_1_roll_suffix"] == 2.0
    assert "substat_2_roll_suffix" not in conf


def test_equip_parse_stat_block_captures_roll_suffix():
    from youkai_ocr.disc_scanner import _equip_parse_stat_block

    block_text = "Main Stat\nATK% 12.0%\nSub Stats\nDEF +2 44\nCRIT Rate 4.8%\nSet Effect\n"
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
        "Lv.4",  # level
        "",  # main stat name (unused here)
        "7.5%",
        "7.5%",  # main stat value — native + 2x, percent seen
        "DEF +2",  # substat 1 name
        "14.4%",
        "14.4%",  # substat 1 value — percent seen
        "",
        "",
        "",  # substat 2 name — bright, dim, upscale: all empty
        "",
        "",  # substat 2 value — both empty -> ends the list
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

    def read_digits_word(self, img, profile):
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
    block_text = "Main Stat\nATK 316\nSub Stats\nDEF +2 44\nSet Effect\n"
    recognizer = _EquipStubRecognizer("Astral Voice [2]", block_text)
    disc, conf = scan_equipped_disc_frame(
        frame,
        _identity_calib(),
        agent_key="Zhu Yuan",
        slot_key=2,
        engine=recognizer,
    )
    assert disc is not None
    assert conf["main_stat_value"] == 316.0


def test_scan_equipped_disc_frame_captures_pct_seen():
    from youkai_ocr.disc_scanner import scan_equipped_disc_frame

    frame = Image.new("RGB", (1920, 1080), color=(0, 0, 0))
    block_text = "Main Stat\nATK 7.5%\nSub Stats\nDEF +2 14.4%\nSet Effect\n"
    recognizer = _EquipStubRecognizer("Astral Voice [2]", block_text)
    disc, conf = scan_equipped_disc_frame(
        frame,
        _identity_calib(),
        agent_key="Zhu Yuan",
        slot_key=2,
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


# ── T9: validator+repair wiring end-to-end (real OCR, golden repair cases) ────
#
# These replay the T8 discs_repair_cases panels through the *real* extraction
# functions (scan_single_frame -> _extract_disc, scan_equipped_disc_frame) —
# not a test-side Evidence reconstruction like test_golden_replay.py's T8
# helper — to prove _repair_and_fold_violations is actually wired into the
# production call path, not just exercised in isolation.

_GOLDEN_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "golden"
_GOLDEN_LABELS = _GOLDEN_FIXTURES / "labels.json"
_GOLDEN_PANEL_ORIGIN = (1421, 100)


def _golden_panel_to_frame(panel_path: Path) -> Image.Image:
    panel = Image.open(panel_path).convert("RGB")
    frame = Image.new("RGB", (1920, 1080), color=(0, 0, 0))
    frame.paste(panel, _GOLDEN_PANEL_ORIGIN)
    return frame


def _load_repair_case(disc_id: str) -> dict:
    if not _GOLDEN_LABELS.exists():
        pytest.skip("golden fixture labels.json missing")
    labels = json.loads(_GOLDEN_LABELS.read_text())
    by_id = {item["id"]: item for item in labels["discs_repair_cases"]}
    if disc_id not in by_id:
        pytest.skip(f"{disc_id} not in discs_repair_cases")
    return by_id[disc_id]


@pytest.mark.parametrize(
    "disc_id, repaired_field, before, after, rule",
    [
        # E2 digit-drop. Landed on rule 3 (roll_budget) pre-T12 because the
        # value bleed also ate this line's "+N"; the fixed parse_roll_suffix
        # recovers it, so rule 1 now resolves it directly.
        (
            "disc_0011",
            "substat[1]",
            {"key": "crit_dmg_", "value": 4.4},
            {"key": "crit_dmg_", "value": 14.4},
            "roll_suffix",
        ),
        # E3 flat/percent key-flip masquerading as sub_equals_main — same
        # pre-T12 rule-3 → rule-1 promotion as disc_0011.
        (
            "disc_0293",
            "substat[3]",
            {"key": "def", "value": 44.0},
            {"key": "def_", "value": 14.4},
            "roll_suffix",
        ),
        # T12/Cluster-1: the def_ 14.4% value bleeds its leading "1" into the
        # name crop ("DEF +2 1"); the fixed parse_roll_suffix recovers the +2,
        # so rule 1 (not budget forcing) resolves the 3-way lattice tie that
        # left 38 archive discs unrepairable.
        (
            "disc_0001",
            "substat[3]",
            {"key": "def", "value": 44.0},
            {"key": "def_", "value": 14.4},
            "roll_suffix",
        ),
    ],
)
def test_scan_single_frame_repairs_disc_through_real_call_path(
    disc_id, repaired_field, before, after, rule
):
    """_extract_disc must build Evidence from its own conf capture and call
    disc_rules.repair_disc for real — the corrected disc and a `repairs`
    record must come out of scan_single_frame exactly as they would from the
    live scan_discs() path."""
    from youkai_ocr.disc_scanner import scan_single_frame

    item = _load_repair_case(disc_id)
    panel_path = _GOLDEN_FIXTURES / "discs" / f"{disc_id}.png"
    if not panel_path.exists():
        pytest.skip(f"panel missing: {panel_path}")

    frame = _golden_panel_to_frame(panel_path)
    disc, conf = scan_single_frame(frame, _identity_calib())

    assert disc is not None, conf.get("_fail_reason")
    expect = item["expect"]
    assert disc.main_stat_key == expect["main_stat_key"]
    got_subs = [{"key": s.key, "value": s.value} for s in disc.substats]
    assert got_subs == expect["substats"], f"{disc_id}: {got_subs} != {expect['substats']}"

    repairs = conf.get("_repairs") or []
    matching = [r for r in repairs if r["field"] == repaired_field]
    assert matching, f"{disc_id}: expected a repair record for {repaired_field}, got {repairs}"
    assert matching[0]["before"] == before
    assert matching[0]["after"] == after
    assert matching[0]["rule"] == rule


def _load_golden_disc(disc_id: str) -> dict:
    if not _GOLDEN_LABELS.exists():
        pytest.skip("golden fixture labels.json missing")
    labels = json.loads(_GOLDEN_LABELS.read_text())
    by_id = {item["id"]: item for item in labels["discs"]}
    if disc_id not in by_id:
        pytest.skip(f"{disc_id} not in discs")
    return by_id[disc_id]


@pytest.mark.parametrize(
    "disc_id, review_conf_key",
    [
        # Cluster-3a: bright pass blanks the legible "Wind DMG Bonus" main-name
        # crop; the dim-pass fallback recovers it (review-capped at 65).
        ("disc_0576", "main_stat"),
        # Cluster-3b: title "[1]" misread as "[ 4" — the panel slot widget must
        # outrank the garbled-bracket title fallback. Full-confidence read.
        ("disc_2070", None),
        # Bright pass mangles the title below the set floor ("v Gi s Bloom");
        # the dim-pass title retry recovers DawnsBloom (review-capped at 65).
        ("disc_1242", "set"),
    ],
)
def test_scan_single_frame_t12_ocr_reliability_fixes(disc_id, review_conf_key):
    """T10's manual review found three OCR failure modes where wrong/empty
    reads masqueraded as valid evidence. Each panel must now extract exactly
    its hand-read ground truth through the real call path; fallback-sourced
    fields stay conf<=65 so they surface in issues for review."""
    from youkai_ocr.disc_scanner import scan_single_frame

    item = _load_golden_disc(disc_id)
    panel_path = _GOLDEN_FIXTURES / "discs" / f"{disc_id}.png"
    if not panel_path.exists():
        pytest.skip(f"panel missing: {panel_path}")

    frame = _golden_panel_to_frame(panel_path)
    disc, conf = scan_single_frame(frame, _identity_calib())

    assert disc is not None, conf.get("_fail_reason")
    expect = item["expect"]
    assert disc.set_key == expect["set_key"]
    assert disc.slot_key == expect["slot_key"]
    assert disc.level == expect["level"]
    assert disc.main_stat_key == expect["main_stat_key"]
    got_subs = [{"key": s.key, "value": s.value} for s in disc.substats]
    exp_subs = [{"key": s["key"], "value": s["value"]} for s in expect["substats"]]
    assert got_subs == exp_subs, f"{disc_id}: {got_subs} != {exp_subs}"

    if review_conf_key is not None:
        assert conf[review_conf_key] <= 65.0, (
            f"{disc_id}: fallback-sourced {review_conf_key} must stay "
            f"review-flagged, got conf {conf[review_conf_key]}"
        )


def test_scan_single_frame_repairs_decimal_loss_and_reads_the_lone_digit():
    """disc_0696: crit_dmg_ 48.0->4.8 is a repairable decimal-loss misread, and
    pen is a 0-roll row whose bare "9" psm 7 could not see at all.

    This test used to assert pen came out at 0.0 — the value the repair policy
    correctly refused to guess, since no roll-suffix or lattice evidence pins it.
    The premise was that the pixels were unreadable; they were not, only psm 7's
    line assumption was. The psm 8 fallback reads the glyph directly, so pen now
    lands on the fixture's own ground truth (labels.json records "pen 0.0->true 9")
    without anything being inferred. The crit_dmg_ repair must still fire."""
    from youkai_ocr.disc_scanner import scan_single_frame

    item = _load_repair_case("disc_0696")
    panel_path = _GOLDEN_FIXTURES / "discs" / "disc_0696.png"
    if not panel_path.exists():
        pytest.skip(f"panel missing: {panel_path}")

    frame = _golden_panel_to_frame(panel_path)
    disc, conf = scan_single_frame(frame, _identity_calib())

    assert disc is not None, conf.get("_fail_reason")
    expect = item["expect"]

    repaired = [r for r in conf.get("_repairs", []) if r["field"] == "substat[2]"]
    assert repaired and repaired[0]["after"] == {"key": "crit_dmg_", "value": 4.8}

    pen_sub = disc.substats[1]
    assert pen_sub.key == "pen"
    # Read from the pixels by the psm 8 fallback, not inferred: it equals the
    # fixture's labelled true value.
    assert pen_sub.value == next(s["value"] for s in expect["substats"] if s["key"] == "pen")
    assert pen_sub.value == 9.0
    assert not [r for r in conf.get("_repairs", []) if r["field"] == "substat[1]"]
    # Fallback-sourced, so still capped for review like every other fallback in the
    # file — a psm-8-only read must never look like a clean dual-scale agreement.
    assert conf["substat_2"] <= 65.0


def test_scan_single_frame_recovers_the_row_behind_an_unreadable_name():
    """disc_0600's third row is a real "PEN 9" whose *name* no pass of the name
    ladder can read, and whose value is a lone digit psm 7 cannot see either.

    This test used to assert the disc came out with 2 substats, on the premise
    that rows 3 and 4 were absent from the panel. They are not: labels.json gives
    the true substats as def_ 9.6 / hp 336 / pen 9.0 / atk_ 3.0, and all four rows
    are visible in the fixture. Terminating on row 3 also discarded row 4's
    "ATK 3%", which reads perfectly at both name and value — two ground-truth
    substats lost, one of them fully legible.

    So the empty-value break must consider the psm 8 fallback before deciding a row
    is the end of the list. Row 3's key still comes out "" (the name really is
    unreadable) at conf 0, so it surfaces for review rather than being silently
    dropped or silently mis-keyed."""
    from youkai_ocr.disc_scanner import scan_single_frame

    item = _load_repair_case("disc_0600")
    panel_path = _GOLDEN_FIXTURES / "discs" / "disc_0600.png"
    if not panel_path.exists():
        pytest.skip(f"panel missing: {panel_path}")

    frame = _golden_panel_to_frame(panel_path)
    disc, conf = scan_single_frame(frame, _identity_calib())

    assert disc is not None, conf.get("_fail_reason")
    assert len(disc.substats) == 4  # row 3 recovered, and row 4 no longer cut off
    expect = {s["key"]: s["value"] for s in item["expect"]["substats"]}
    # Every value matches ground truth; only row 3's key is unreadable.
    assert [s.value for s in disc.substats] == [9.6, 336.0, 9.0, 3.0]
    assert [s.key for s in disc.substats] == ["def_", "hp", "", "atk_"]
    assert expect["pen"] == disc.substats[2].value  # the "" row is the true PEN row
    assert conf["substat_3"] == 0.0  # unreadable name — flagged, never silent
    assert conf["substat_4"] > 70.0  # the legible row is not penalised by its neighbour


def test_scan_equipped_disc_frame_repairs_through_real_call_path():
    """Same wiring proof as test_scan_single_frame_repairs_disc_through_real_call_path,
    for the equip-slot select-view path (DESIGN Integration point 2). No golden
    equip-view panel exercises a repair case, so this uses a scripted block
    read — the canonical DESIGN repair example (def 44.0 + roll-suffix +2 +
    pct_seen -> def_ 14.4, joint flat/percent resolution) — same as T7's
    disc_rules-level test, but proven through the real extraction call path."""
    from youkai_ocr.disc_scanner import scan_equipped_disc_frame

    frame = Image.new("RGB", (1920, 1080), color=(0, 0, 0))
    block_text = "Main Stat\nATK 316\nSub Stats\nDEF +2 44%\nSet Effect\n"
    recognizer = _EquipStubRecognizer("Astral Voice [2]", block_text)
    disc, conf = scan_equipped_disc_frame(
        frame,
        _identity_calib(),
        agent_key="Zhu Yuan",
        slot_key=2,
        engine=recognizer,
    )

    assert disc is not None
    assert disc.substats[0].key == "def_"
    assert disc.substats[0].value == 14.4

    repairs = conf.get("_repairs") or []
    assert repairs == [
        {
            "field": "substat[0]",
            "before": {"key": "def", "value": 44.0},
            "after": {"key": "def_", "value": 14.4},
            "rule": "roll_suffix",
        }
    ]


# ── T9: scan_discs issue aggregation (repairs surfaced in the issues list) ────


def test_scan_discs_issue_carries_repairs_when_no_other_low_fields(monkeypatch):
    """A disc that's fully auto-repaired (no residual low-confidence field)
    must still get an issue entry recording the repair — repairs are review-
    worthy even when nothing else about the disc looks untrustworthy."""
    from threading import Event

    import youkai_ocr.disc_scanner as ds
    from youkai_ocr.grid import DEFAULT_GRID

    class FakeNav:
        def __init__(self, *a, **k):
            pass

        def scan(self, total):
            yield 0, 0, "frame0"

    class FakeListener:
        def stop(self):
            pass

    class Stub:
        def to_dict(self):
            return {"setKey": "AstralVoice"}

    repair_record = [
        {
            "field": "substat[0]",
            "before": {"key": "def", "value": 44.0},
            "after": {"key": "def_", "value": 14.4},
            "rule": "roll_suffix",
        }
    ]

    def fake_extract(frame, calib, cx, cy, rec, arch, cell_idx):
        return Stub(), {"set": 99.0, "_repairs": repair_record}

    monkeypatch.setattr(ds, "GridNavigator", FakeNav)
    monkeypatch.setattr(ds, "make_recognizer", lambda *a, **k: object())
    monkeypatch.setattr(ds, "make_kill_listener", lambda: (Event(), FakeListener()))
    monkeypatch.setattr(ds, "read_disc_count", lambda *a, **k: 1)
    monkeypatch.setattr(ds, "_extract_disc", fake_extract)

    discs, issues = ds.scan_discs(lambda: "preflight", calib=None, grid=DEFAULT_GRID)

    assert len(discs) == 1
    assert len(issues) == 1
    assert issues[0]["status"] == "repaired"
    assert issues[0]["repairs"] == repair_record
    assert "fields" not in issues[0]


def test_scan_discs_excludes_failed_validation_disc_from_export(monkeypatch):
    """T13: a disc with residual error-severity violations after repair holds a
    known-wrong value — it must be EXCLUDED from the returned disc list (and
    therefore the export) and surface as a failed_validation issue carrying
    the disc payload + violations for the user's failure report."""
    from threading import Event

    import youkai_ocr.disc_scanner as ds
    from youkai_ocr.grid import DEFAULT_GRID

    class FakeNav:
        def __init__(self, *a, **k):
            pass

        def scan(self, total):
            yield 0, 0, "frame0"

    class FakeListener:
        def stop(self):
            pass

    class Stub:
        def to_dict(self):
            return {"setKey": "AstralVoice"}

    violations = [
        {
            "field": "substat[1]",
            "code": "sub_not_on_lattice",
            "observed": 0.0,
            "expected": None,
            "severity": "error",
        }
    ]

    def fake_extract(frame, calib, cx, cy, rec, arch, cell_idx):
        return Stub(), {"set": 99.0, "substat_2": 30.0, "_violations": list(violations)}

    monkeypatch.setattr(ds, "GridNavigator", FakeNav)
    monkeypatch.setattr(ds, "make_recognizer", lambda *a, **k: object())
    monkeypatch.setattr(ds, "make_kill_listener", lambda: (Event(), FakeListener()))
    monkeypatch.setattr(ds, "read_disc_count", lambda *a, **k: 1)
    monkeypatch.setattr(ds, "_extract_disc", fake_extract)

    discs, issues = ds.scan_discs(lambda: "preflight", calib=None, grid=DEFAULT_GRID)

    assert discs == []  # excluded from export
    assert len(issues) == 1
    assert issues[0]["status"] == "failed_validation"
    assert issues[0]["violations"] == violations
    assert issues[0]["disc"] == {"setKey": "AstralVoice"}


def test_scan_discs_issue_carries_both_low_fields_and_repairs(monkeypatch):
    """A disc with both a residual low-confidence field and an applied repair
    must surface both in the same issue entry — status stays low_confidence
    (the stronger signal) but the repairs list is not dropped."""
    from threading import Event

    import youkai_ocr.disc_scanner as ds
    from youkai_ocr.grid import DEFAULT_GRID

    class FakeNav:
        def __init__(self, *a, **k):
            pass

        def scan(self, total):
            yield 0, 0, "frame0"

    class FakeListener:
        def stop(self):
            pass

    class Stub:
        def to_dict(self):
            return {"setKey": "AstralVoice"}

    repair_record = [
        {
            "field": "substat[0]",
            "before": {"key": "def", "value": 44.0},
            "after": {"key": "def_", "value": 14.4},
            "rule": "roll_suffix",
        }
    ]

    def fake_extract(frame, calib, cx, cy, rec, arch, cell_idx):
        return Stub(), {"set": 99.0, "substat_2": 30.0, "_repairs": repair_record}

    monkeypatch.setattr(ds, "GridNavigator", FakeNav)
    monkeypatch.setattr(ds, "make_recognizer", lambda *a, **k: object())
    monkeypatch.setattr(ds, "make_kill_listener", lambda: (Event(), FakeListener()))
    monkeypatch.setattr(ds, "read_disc_count", lambda *a, **k: 1)
    monkeypatch.setattr(ds, "_extract_disc", fake_extract)

    discs, issues = ds.scan_discs(lambda: "preflight", calib=None, grid=DEFAULT_GRID)

    assert len(issues) == 1
    assert issues[0]["status"] == "low_confidence"
    assert issues[0]["fields"] == {"substat_2": 30.0}
    assert issues[0]["repairs"] == repair_record


def test_scan_discs_evidence_keys_do_not_flag_clean_disc(monkeypatch):
    """Regression: raw OCR evidence (pct_seen bools, roll_suffix, main_stat_value)
    shares the conf dict with 0-100 confidence scores. It must NOT feed the
    low-confidence filter — a bool `False`/`True` is `< 70` and a small float
    like roll_suffix=3.0 is `< 70`, so a clean disc whose every real confidence
    is high was silently labeled low_confidence and its evidence dumped into
    `fields`. A fully clean disc must produce no issue entry at all."""
    from threading import Event

    import youkai_ocr.disc_scanner as ds
    from youkai_ocr.grid import DEFAULT_GRID

    class FakeNav:
        def __init__(self, *a, **k):
            pass

        def scan(self, total):
            yield 0, 0, "frame0"

    class FakeListener:
        def stop(self):
            pass

    class Stub:
        def to_dict(self):
            return {"setKey": "AstralVoice"}

    # Every confidence score is high (clean disc); only evidence keys are "low".
    clean_conf = {
        "set": 99.0,
        "slot": 100.0,
        "rarity": 100.0,
        "level": 100.0,
        "lock": 80.0,
        "main_stat": 100.0,
        "substat_1": 100.0,
        "substat_2": 100.0,
        "substat_3": 100.0,
        "substat_4": 100.0,
        # evidence — must be ignored by the low-confidence filter:
        "main_stat_value": 316.0,
        "main_stat_pct_seen": False,
        "substat_1_roll_suffix": 3.0,
        "substat_1_pct_seen": False,
        "substat_2_pct_seen": True,
        "substat_3_pct_seen": False,
        "substat_4_pct_seen": True,
    }

    def fake_extract(frame, calib, cx, cy, rec, arch, cell_idx):
        return Stub(), dict(clean_conf)

    monkeypatch.setattr(ds, "GridNavigator", FakeNav)
    monkeypatch.setattr(ds, "make_recognizer", lambda *a, **k: object())
    monkeypatch.setattr(ds, "make_kill_listener", lambda: (Event(), FakeListener()))
    monkeypatch.setattr(ds, "read_disc_count", lambda *a, **k: 1)
    monkeypatch.setattr(ds, "_extract_disc", fake_extract)

    discs, issues = ds.scan_discs(lambda: "preflight", calib=None, grid=DEFAULT_GRID)

    assert len(discs) == 1
    assert issues == []  # a clean disc must not be flagged from evidence keys alone


# ── _arbitrate_main_value ─────────────────────────────────────────────────────
# The main-stat value is fully determined by (rarity, main_key, level).  When the
# 1x and 2x OCR passes disagree the old rule always took the 2x read, which threw
# away a correct 1x value: "7.2%" came back as "1.2%" upscaled and 67 discs failed
# validation on 2026-07-30 for exactly that.


@pytest.mark.parametrize(
    ("v1", "v2", "rarity", "key", "level", "expected"),
    [
        (7.2, 1.2, 4, "impact_", 3, 7.2),  # the live failure: 1x right, 2x wrong
        (1.2, 7.2, 4, "impact_", 3, 7.2),  # and the mirror image
        (7.5, 7.9, 4, "atk_", 0, 7.5),
        (71.5, 7.5, 4, "atk_", 0, 7.5),
        (7.5, 71.9, 4, "atk_", 0, 7.5),
    ],
)
def test_arbitrate_picks_the_lattice_consistent_read(v1, v2, rarity, key, level, expected):
    assert _arbitrate_main_value(v1, v2, rarity, key, level) == expected


def test_arbitrate_falls_back_to_2x_when_neither_matches():
    """Both scales wrong → no basis to choose; keep the old behaviour and let the
    validator reject the disc rather than inventing a value."""
    assert _arbitrate_main_value(3.3, 9.9, 4, "atk_", 0) == 9.9


@pytest.mark.parametrize(
    ("rarity", "key", "level"),
    [
        (4, "", 0),  # main-stat key unreadable
        (99, "atk_", 0),  # rarity outside the table
        (4, "not_a_stat", 0),
    ],
)
def test_arbitrate_falls_back_when_the_table_cannot_answer(rarity, key, level):
    assert _arbitrate_main_value(7.2, 1.2, rarity, key, level) == 1.2


def test_scan_discs_writes_the_panel_cell_sidecar(monkeypatch, tmp_path):
    """The archive numbers panel dirs by grid cell while `discs` holds only what
    survived the T13 gate, so position == cell only until the first exclusion.
    disc_cells.json records the real mapping; without it `revalidate` pairs each
    disc with a different disc's panel from that point on.
    """
    import json as _json
    from threading import Event

    import youkai_ocr.disc_scanner as ds
    from youkai_ocr.grid import DEFAULT_GRID

    class FakeNav:
        def __init__(self, *a, **k):
            pass

        def scan(self, total):
            yield 0, 0, "f0"
            yield 1, 1, "f1"
            yield 2, 2, "f2"

    class FakeListener:
        def stop(self):
            pass

    class Stub:
        def to_dict(self):
            return {"setKey": "AstralVoice"}

    def fake_extract(frame, calib, cx, cy, rec, arch, cell_idx):
        # Cell 1 fails validation and is excluded, so cells 0 and 2 are exported.
        if cell_idx == 1:
            return Stub(), {
                "_violations": [{"field": "substat[0]", "code": "x", "severity": "error"}]
            }
        return Stub(), {"set": 99.0}

    monkeypatch.setattr(ds, "GridNavigator", FakeNav)
    monkeypatch.setattr(ds, "make_recognizer", lambda *a, **k: object())
    monkeypatch.setattr(ds, "make_kill_listener", lambda: (Event(), FakeListener()))
    monkeypatch.setattr(ds, "read_disc_count", lambda *a, **k: 3)
    monkeypatch.setattr(ds, "_extract_disc", fake_extract)

    discs, issues = ds.scan_discs(
        lambda: "preflight", calib=None, grid=DEFAULT_GRID, archive_dir=tmp_path
    )

    assert len(discs) == 2
    cells = _json.loads((tmp_path / "disc_cells.json").read_text(encoding="utf-8"))
    assert cells == [0, 2]  # NOT [0, 1] — position 1 is cell 2
    assert len(cells) == len(discs)


def test_scan_discs_writes_no_sidecar_without_an_archive(monkeypatch, tmp_path):
    """No archive dir means no panels to map onto, so nothing is written."""
    from threading import Event

    import youkai_ocr.disc_scanner as ds
    from youkai_ocr.grid import DEFAULT_GRID

    class FakeNav:
        def __init__(self, *a, **k):
            pass

        def scan(self, total):
            yield 0, 0, "f0"

    class FakeListener:
        def stop(self):
            pass

    class Stub:
        def to_dict(self):
            return {"setKey": "AstralVoice"}

    monkeypatch.setattr(ds, "GridNavigator", FakeNav)
    monkeypatch.setattr(ds, "make_recognizer", lambda *a, **k: object())
    monkeypatch.setattr(ds, "make_kill_listener", lambda: (Event(), FakeListener()))
    monkeypatch.setattr(ds, "read_disc_count", lambda *a, **k: 1)
    monkeypatch.setattr(ds, "_extract_disc", lambda *a, **k: (Stub(), {"set": 99.0}))

    ds.scan_discs(lambda: "preflight", calib=None, grid=DEFAULT_GRID)

    assert not (tmp_path / "disc_cells.json").exists()
