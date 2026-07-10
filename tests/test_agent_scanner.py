"""Tests for E1-E3: Agent scanner helpers, extractors, and export logic.

Live game interaction (AgentNavigator) is not tested here — that requires the
game window.  This file covers: portrait detection, core-node detection,
ascension-dot counting, field extractors, offline assembly, and export.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from youkai_ocr.agent_scanner import (
    _ALL_SLOT_CENTERS,
    _ASCENSION_DOTS_BBOX,
    _CORE_NODE_BBOXES,
    _DISC_SLOT_CENTERS,
    _ROSTER_STRIP_BBOX,
    _count_ascension_dots,
    _crop,
    _detect_core_rank,
    _extract_base_stats,
    _extract_equip_frame,
    _extract_skills,
    _find_agent_portraits,
    export_agents,
    resolve_locations,
)
from youkai_ocr.capture import CalibrationResult
from youkai_ocr.zod import ZodAgent, ZodDisc, ZodTalent, ZodWEngine

# ── Fixtures & helpers ────────────────────────────────────────────────────────


def _identity_calib() -> CalibrationResult:
    return CalibrationResult(scale_x=1.0, scale_y=1.0, frame_width=1920, frame_height=1080)


def _dark_frame(w: int = 1920, h: int = 1080) -> Image.Image:
    """Solid dark frame (background colour)."""
    return Image.new("RGB", (w, h), (10, 10, 10))


class _MockRecognizer:
    """Returns preset values in sequence for read_line; falls back to ''."""

    def __init__(self, *lines: str) -> None:
        self._lines = list(lines)

    def read_text(self, img: Image.Image, profile: str) -> str:
        return self._lines.pop(0) if self._lines else ""

    def read_line(self, img: Image.Image, profile: str) -> str:
        return self._lines.pop(0) if self._lines else ""

    def read_digits(self, img: Image.Image, profile: str) -> str:
        return self._lines.pop(0) if self._lines else ""

    def read_slot(self, img: Image.Image, profile: str) -> str:
        return self._lines.pop(0) if self._lines else ""

    def read_cinema(self, img: Image.Image) -> str:
        return self._lines.pop(0) if self._lines else ""


# ── _crop (mirrors disc/engine tests) ─────────────────────────────────────────


def test_crop_identity():
    calib = _identity_calib()
    frame = Image.new("RGB", (1920, 1080), (255, 0, 0))
    cropped = _crop(frame, calib, (100, 200, 400, 500))
    assert cropped.size == (300, 300)


def test_crop_scaled():
    calib = CalibrationResult(0.5, 0.5, 960, 540)
    frame = Image.new("RGB", (960, 540), (0, 255, 0))
    cropped = _crop(frame, calib, (100, 100, 300, 300))
    assert cropped.size == (100, 100)


# ── _find_agent_portraits ─────────────────────────────────────────────────────


def _make_roster_frame(portrait_x_refs: list[int], portrait_width: int = 40) -> Image.Image:
    """Build a 1920×1080 dark frame with bright portrait blobs at given ref x positions."""
    frame = _dark_frame()
    arr = np.array(frame)
    _, y0, _, y1 = _ROSTER_STRIP_BBOX
    cy = (y0 + y1) // 2
    half_h = (y1 - y0) // 2 - 2
    half_w = portrait_width // 2
    for px in portrait_x_refs:
        x0 = max(0, px - half_w)
        x1 = min(1920, px + half_w)
        arr[cy - half_h : cy + half_h, x0:x1] = [200, 200, 200]
    return Image.fromarray(arr.astype(np.uint8), "RGB")


def test_find_portraits_detects_two():
    calib = _identity_calib()
    # Both portraits must be at x >= _ROSTER_X_MIN (400) — the City/Home button
    # at x≈40-57 is filtered out by design to prevent clicking out of the agent menu.
    expected = [450, 600]
    frame = _make_roster_frame(expected)
    found = _find_agent_portraits(frame, calib)
    assert len(found) == 2
    for ex, got in zip(expected, found, strict=False):
        assert abs(ex - got) <= 5, f"Expected ≈{ex}, got {got}"


def test_find_portraits_detects_many():
    calib = _identity_calib()
    # Portraits start at x=450 (>= _ROSTER_X_MIN=400) and spaced 100px apart.
    xs = [450 + i * 100 for i in range(6)]
    frame = _make_roster_frame(xs)
    found = _find_agent_portraits(frame, calib)
    assert len(found) == 6


def test_find_portraits_empty_strip():
    calib = _identity_calib()
    frame = _dark_frame()
    found = _find_agent_portraits(frame, calib)
    assert found == []


def test_find_portraits_scaled_calib():
    calib = CalibrationResult(scale_x=0.8333, scale_y=0.8333, frame_width=1600, frame_height=900)
    # Build a scaled-down frame at 1600×900
    frame = Image.new("RGB", (1600, 900), (10, 10, 10))
    arr = np.array(frame)
    # Place portrait at ref x=500 (>= _ROSTER_X_MIN=400) → scaled x≈416
    ref_x = 500
    sx = int(ref_x * calib.scale_x)
    _, y0, _, y1 = _ROSTER_STRIP_BBOX
    sy0, sy1 = int(y0 * calib.scale_y), int(y1 * calib.scale_y)
    cy = (sy0 + sy1) // 2
    half_h = (sy1 - sy0) // 2 - 1
    arr[cy - half_h : cy + half_h, sx - 15 : sx + 15] = [200, 200, 200]
    frame = Image.fromarray(arr.astype(np.uint8), "RGB")
    found = _find_agent_portraits(frame, calib)
    assert len(found) == 1
    assert abs(found[0] - ref_x) <= 10


# ── _detect_core_rank ─────────────────────────────────────────────────────────


def _make_skills_frame(lit_nodes: list[int]) -> Image.Image:
    """Frame where nodes at given indices (0-5) have teal centers."""
    frame = _dark_frame()
    arr = np.array(frame)
    for i, bbox in enumerate(_CORE_NODE_BBOXES):
        x0, y0, x1, y1 = bbox
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        color = [0, 180, 180] if i in lit_nodes else [30, 30, 30]
        arr[cy - 15 : cy + 15, cx - 15 : cx + 15] = color
    return Image.fromarray(arr.astype(np.uint8), "RGB")


def test_detect_core_rank_none():
    calib = _identity_calib()
    frame = _make_skills_frame([])
    assert _detect_core_rank(frame, calib) == 0


def test_detect_core_rank_three():
    calib = _identity_calib()
    frame = _make_skills_frame([0, 1, 2])
    assert _detect_core_rank(frame, calib) == 3


def test_detect_core_rank_all():
    calib = _identity_calib()
    frame = _make_skills_frame(list(range(6)))
    assert _detect_core_rank(frame, calib) == 6


def test_detect_core_rank_golden_node_is_lit():
    """A golden/orange node (character accent colour) must count as lit."""
    frame = _dark_frame()
    arr = np.array(frame)
    bbox = _CORE_NODE_BBOXES[0]
    cx, cy = (bbox[0] + bbox[2]) // 2, (bbox[1] + bbox[3]) // 2
    arr[cy - 15 : cy + 15, cx - 15 : cx + 15] = [215, 150, 12]  # YeShunguang gold
    frame = Image.fromarray(arr.astype(np.uint8), "RGB")
    calib = _identity_calib()
    assert _detect_core_rank(frame, calib) == 1


def test_detect_core_rank_dark_not_lit():
    """Dark-gray locked nodes (luma≈42) must not count as lit."""
    frame = _dark_frame()
    arr = np.array(frame)
    for bbox in _CORE_NODE_BBOXES:
        cx, cy = (bbox[0] + bbox[2]) // 2, (bbox[1] + bbox[3]) // 2
        arr[cy - 15 : cy + 15, cx - 15 : cx + 15] = [42, 42, 42]
    frame = Image.fromarray(arr.astype(np.uint8), "RGB")
    calib = _identity_calib()
    assert _detect_core_rank(frame, calib) == 0


# ── _count_ascension_dots ─────────────────────────────────────────────────────


def _make_dots_frame(n_dots: int, dot_width: int = 15, dot_gap: int = 20) -> Image.Image:
    """Frame with n_dots bright regions in the ascension dots bbox."""
    frame = _dark_frame()
    arr = np.array(frame)
    x0, y0, x1, y1 = _ASCENSION_DOTS_BBOX
    cy = (y0 + y1) // 2
    half_h = max(1, (y1 - y0) // 2 - 2)
    for i in range(n_dots):
        dx = x0 + i * (dot_width + dot_gap) + dot_width // 2
        arr[cy - half_h : cy + half_h, dx : dx + dot_width] = [200, 200, 200]
    return Image.fromarray(arr.astype(np.uint8), "RGB")


def test_count_dots_zero():
    calib = _identity_calib()
    frame = _dark_frame()
    assert _count_ascension_dots(frame, calib) == 0


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 6])
def test_count_dots_n(n):
    calib = _identity_calib()
    frame = _make_dots_frame(n)
    assert _count_ascension_dots(frame, calib) == n


# ── _extract_base_stats ───────────────────────────────────────────────────────


def test_extract_base_stats_normal():
    """Agent name + level are read from the mock recognizer and normalised."""
    calib = _identity_calib()
    frame = _dark_frame()
    rec = _MockRecognizer("Zhu Yuan", "Lv. 45")
    key, level, ascension, conf = _extract_base_stats(frame, calib, rec)
    assert key == "ZhuYuan"
    assert level == 45
    assert 0 <= ascension <= 6
    assert conf["key"] > 0
    assert conf["level"] == 90.0


def test_extract_base_stats_out_of_range_level():
    calib = _identity_calib()
    frame = _dark_frame()
    rec = _MockRecognizer("Ellen", "Lv. 99")  # 99 out of range → low confidence
    _, level, _, conf = _extract_base_stats(frame, calib, rec)
    assert level == 99
    assert conf["level"] == 30.0


def test_extract_base_stats_unrecognised_agent():
    calib = _identity_calib()
    frame = _dark_frame()
    rec = _MockRecognizer("XxX_NotAnAgent_XxX", "Lv. 30")
    key, _, _, conf = _extract_base_stats(frame, calib, rec)
    # key may be a partial match; what matters is conf["key"] is populated
    assert "key" in conf


# ── _extract_skills ───────────────────────────────────────────────────────────


def test_extract_skills_normal():
    """Mindscape from recogniser; skill levels from blob classifier (0 on dark frame); core=0."""
    calib = _identity_calib()
    frame = _dark_frame()
    # Skill levels now use _read_skill_badge() (pixel-based), not the recogniser.
    # A dark frame has no badge blobs → all skills fall back to 0.
    rec = _MockRecognizer("CINEMA 3/6")
    mindscape, talent, conf = _extract_skills(frame, calib, rec)
    assert mindscape == 3
    assert conf["mindscape"] == 90.0
    assert talent.basic == 0  # dark frame — no badge blobs detectable
    assert talent.dodge == 0
    assert talent.core == 0  # dark frame → no teal nodes


def test_extract_skills_lit_nodes():
    """Core rank counted from teal-lit node bboxes."""
    calib = _identity_calib()
    frame = _make_skills_frame([0, 1, 2, 3])  # 4 lit nodes
    rec = _MockRecognizer("CINEMA 0/6", "1", "1", "1", "1", "1")
    _, talent, _ = _extract_skills(frame, calib, rec)
    assert talent.core == 4


def test_extract_skills_missing_mindscape():
    """If OCR returns empty, mindscape defaults to 0 with low confidence."""
    calib = _identity_calib()
    frame = _dark_frame()
    rec = _MockRecognizer("", "1", "1", "1", "1", "1")
    mindscape, _, conf = _extract_skills(frame, calib, rec)
    assert mindscape == 0
    assert conf["mindscape"] == 30.0


# ── export_agents ─────────────────────────────────────────────────────────────


def _make_agent(key: str = "ZhuYuan") -> ZodAgent:
    return ZodAgent(
        key=key,
        level=60,
        constellation=3,
        ascension=5,
        talent=ZodTalent(basic=12, dodge=12, assist=12, special=12, chain=12, core=4),
    )


def test_export_agents_roundtrip():
    agents = [_make_agent("ZhuYuan"), _make_agent("Ellen")]
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "export.json"
        export_agents(agents, path)
        data = json.loads(path.read_text())

    assert data["format"] == "eZOD"
    assert data["version"] == 1
    assert data["source"] == "Youkai"
    assert len(data["characters"]) == 2
    assert data["discs"] == []
    assert data["weapons"] == []


def test_export_agent_fields():
    agent = _make_agent("ZhuYuan")
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "export.json"
        export_agents([agent], path)
        data = json.loads(path.read_text())

    c = data["characters"][0]
    assert c["key"] == "ZhuYuan"
    assert c["level"] == 60
    assert c["constellation"] == 3
    assert c["ascension"] == 5
    assert c["talent"]["basic"] == 12
    assert c["talent"]["core"] == 4


def test_export_agent_no_talent():
    agent = ZodAgent(key="Ellen", level=40, constellation=0, ascension=2)
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "export.json"
        export_agents([agent], path)
        data = json.loads(path.read_text())

    c = data["characters"][0]
    assert "talent" not in c


def test_export_creates_parent_dirs():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "nested" / "dir" / "agents.json"
        export_agents([_make_agent()], path)
        assert path.exists()


# ── _ALL_SLOT_CENTERS structure ───────────────────────────────────────────────


def test_slot_centers_count():
    assert len(_DISC_SLOT_CENTERS) == 6
    assert len(_ALL_SLOT_CENTERS) == 7  # 6 disc + 1 engine


# ── E4: _extract_equip_frame ──────────────────────────────────────────────────


def test_extract_equip_frame_disc_slot():
    """Recogniser returns a disc set name → record with disc_set and slot_key."""
    calib = _identity_calib()
    frame = _dark_frame()
    rec = _MockRecognizer("Shockstar Disco [2]")
    result = _extract_equip_frame(frame, calib, rec, slot_idx=1)  # H18: idx 1 → slot# 6-1 = 5
    assert result is not None
    assert result["slot_idx"] == 1
    assert result["slot_key"] == "5"
    assert result["disc_set"] == "ShockstarDisco"
    assert result["engine_key"] is None
    assert result["confidence"] > 0


def test_extract_equip_frame_slot_key_from_index():
    """slot_key is derived from slot POSITION (slot# = 6 - idx, H18), not from the OCR title."""
    calib = _identity_calib()
    frame = _dark_frame()
    # OCR title says [1] but slot_idx 3 is the lower-LEFT hexagon position → in-game slot 3.
    rec = _MockRecognizer("Chaotic Metal [1]")
    result = _extract_equip_frame(frame, calib, rec, slot_idx=3)
    assert result is not None
    assert result["slot_key"] == "3"


def test_extract_equip_frame_engine_slot():
    """Slot index 6 → engine key extracted, disc fields None."""
    calib = _identity_calib()
    frame = _dark_frame()
    rec = _MockRecognizer("Starlight Engine")
    result = _extract_equip_frame(frame, calib, rec, slot_idx=6)
    assert result is not None
    assert result["slot_idx"] == 6
    assert result["engine_key"] == "StarlightEngine"
    assert result["disc_set"] is None
    assert result["slot_key"] is None


def test_extract_equip_frame_empty_slot_returns_none():
    """Unrecognised / empty title (low confidence) → None (empty slot)."""
    calib = _identity_calib()
    frame = _dark_frame()
    rec = _MockRecognizer("")  # OCR returns blank — low confidence
    result = _extract_equip_frame(frame, calib, rec, slot_idx=0)
    assert result is None


# ── E4: resolve_locations ─────────────────────────────────────────────────────


def _make_disc(set_key: str, slot_key: str, location: str = "") -> ZodDisc:
    return ZodDisc(
        set_key=set_key,
        slot_key=slot_key,
        level=10,
        rarity=4,
        main_stat_key="atk",
        location=location,
        lock=False,
        substats=[],
    )


def _make_engine(key: str, location: str = "") -> ZodWEngine:
    return ZodWEngine(key=key, level=60, ascension=5, refinement=1, location=location, lock=False)


def test_resolve_locations_sets_disc_location():
    discs = [_make_disc("ShockstarDisco", "2")]
    engines: list[ZodWEngine] = []
    records = [
        {
            "agent_key": "ZhuYuan",
            "slot_idx": 1,
            "disc_set": "ShockstarDisco",
            "slot_key": "2",
            "engine_key": None,
            "confidence": 90.0,
        },
    ]
    orphans = resolve_locations(records, discs, engines)
    assert orphans == []
    assert discs[0].location == "ZhuYuan"


def test_resolve_locations_sets_engine_location():
    discs: list[ZodDisc] = []
    engines = [_make_engine("StarlightEngine")]
    records = [
        {
            "agent_key": "ZhuYuan",
            "slot_idx": 6,
            "disc_set": None,
            "slot_key": None,
            "engine_key": "StarlightEngine",
            "confidence": 88.0,
        },
    ]
    orphans = resolve_locations(records, discs, engines)
    assert orphans == []
    assert engines[0].location == "ZhuYuan"


def test_resolve_locations_multiple_agents():
    discs = [_make_disc("ChaoticMetal", "1"), _make_disc("ShockstarDisco", "2")]
    engines = [_make_engine("StarlightEngine"), _make_engine("BigCylinder")]
    records = [
        {
            "agent_key": "ZhuYuan",
            "slot_idx": 0,
            "disc_set": "ChaoticMetal",
            "slot_key": "1",
            "engine_key": None,
            "confidence": 90.0,
        },
        {
            "agent_key": "ZhuYuan",
            "slot_idx": 6,
            "disc_set": None,
            "slot_key": None,
            "engine_key": "StarlightEngine",
            "confidence": 90.0,
        },
        {
            "agent_key": "Ellen",
            "slot_idx": 1,
            "disc_set": "ShockstarDisco",
            "slot_key": "2",
            "engine_key": None,
            "confidence": 90.0,
        },
        {
            "agent_key": "Ellen",
            "slot_idx": 6,
            "disc_set": None,
            "slot_key": None,
            "engine_key": "BigCylinder",
            "confidence": 90.0,
        },
    ]
    orphans = resolve_locations(records, discs, engines)
    assert orphans == []
    assert discs[0].location == "ZhuYuan"
    assert discs[1].location == "Ellen"
    assert engines[0].location == "ZhuYuan"
    assert engines[1].location == "Ellen"


def test_resolve_locations_orphan_disc():
    """No matching disc in the scanned list → orphan issue reported."""
    discs: list[ZodDisc] = []
    engines: list[ZodWEngine] = []
    records = [
        {
            "agent_key": "ZhuYuan",
            "slot_idx": 0,
            "disc_set": "MissingSet",
            "slot_key": "1",
            "engine_key": None,
            "confidence": 90.0,
        },
    ]
    orphans = resolve_locations(records, discs, engines)
    assert len(orphans) == 1
    assert orphans[0]["type"] == "disc"
    assert orphans[0]["agent"] == "ZhuYuan"
    assert orphans[0]["status"] == "no_match"


def test_resolve_locations_orphan_engine():
    """No matching engine → orphan issue reported."""
    discs: list[ZodDisc] = []
    engines: list[ZodWEngine] = []
    records = [
        {
            "agent_key": "ZhuYuan",
            "slot_idx": 6,
            "disc_set": None,
            "slot_key": None,
            "engine_key": "GhostEngine",
            "confidence": 85.0,
        },
    ]
    orphans = resolve_locations(records, discs, engines)
    assert len(orphans) == 1
    assert orphans[0]["type"] == "engine"
    assert orphans[0]["status"] == "no_match"


def test_resolve_locations_unequipped_slots_ignored():
    """Records list contains only equipped slots — unequipped slots produce no records."""
    discs = [_make_disc("ChaoticMetal", "1")]
    engines: list[ZodWEngine] = []
    records = [
        {
            "agent_key": "ZhuYuan",
            "slot_idx": 0,
            "disc_set": "ChaoticMetal",
            "slot_key": "1",
            "engine_key": None,
            "confidence": 90.0,
        },
        # slots 1-5 and engine absent → those slots unequipped, no records for them
    ]
    orphans = resolve_locations(records, discs, engines)
    assert orphans == []
    assert discs[0].location == "ZhuYuan"


# ── T5: on_item callback ──────────────────────────────────────────────────────


def test_scan_agents_on_item_called_once_per_agent_monotonically(monkeypatch):
    """on_item is called exactly once per agent iteration with monotonically increasing scanned."""
    import youkai_ocr.agent_scanner as ag

    N = 4

    class FakeListener:
        def stop(self):
            pass

    class FakeNavigator:
        def __init__(self, *a, **k):
            pass

        def scan(self):
            dummy_frame = Image.new("RGB", (1920, 1080), (80, 80, 80))
            for i in range(N):
                yield i, dummy_frame, dummy_frame, []

    calib = _identity_calib()

    def fake_extract_base(frame, c, rec):
        return "Zhao", 60, 5, {"key": 90.0, "level": 90.0, "ascension": 90.0}

    def fake_extract_skills(frame, c, rec):
        return 0, ZodTalent(basic=10, dodge=10, assist=10, special=10, chain=10, core=6), {}

    _E = type("E", (), {"is_set": lambda s: False, "set": lambda s: None})()
    monkeypatch.setattr(ag, "AgentNavigator", FakeNavigator)
    monkeypatch.setattr(ag, "make_recognizer", lambda *a, **k: object())
    monkeypatch.setattr(ag, "make_kill_listener", lambda suppress_flag=None: (_E, FakeListener()))
    monkeypatch.setattr(ag, "_extract_base_stats", fake_extract_base)
    monkeypatch.setattr(ag, "_extract_skills", fake_extract_skills)

    calls: list[tuple[int, int | None]] = []
    agents, _, _, _ = ag.scan_agents(
        lambda: Image.new("RGB", (1920, 1080)),
        calib=calib,
        on_item=lambda s, t: calls.append((s, t)),
    )

    assert len(calls) == N
    scanned_values = [s for s, _ in calls]
    assert scanned_values == list(range(1, N + 1)), (
        f"not monotonically increasing: {scanned_values}"
    )
    assert all(t is None for _, t in calls), "total should always be None for agents"


def test_scan_agents_on_item_omitted_no_error(monkeypatch):
    """on_item=None (default) causes no error."""
    import youkai_ocr.agent_scanner as ag

    class FakeListener:
        def stop(self):
            pass

    class FakeNavigator:
        def __init__(self, *a, **k):
            pass

        def scan(self):
            dummy = Image.new("RGB", (1920, 1080), (80, 80, 80))
            for i in range(2):
                yield i, dummy, dummy, []

    calib = _identity_calib()

    def fake_extract_base(frame, c, rec):
        return "Zhao", 60, 5, {"key": 90.0, "level": 90.0, "ascension": 90.0}

    def fake_extract_skills(frame, c, rec):
        return 0, ZodTalent(basic=10, dodge=10, assist=10, special=10, chain=10, core=6), {}

    _E = type("E", (), {"is_set": lambda s: False, "set": lambda s: None})()
    monkeypatch.setattr(ag, "AgentNavigator", FakeNavigator)
    monkeypatch.setattr(ag, "make_recognizer", lambda *a, **k: object())
    monkeypatch.setattr(ag, "make_kill_listener", lambda suppress_flag=None: (_E, FakeListener()))
    monkeypatch.setattr(ag, "_extract_base_stats", fake_extract_base)
    monkeypatch.setattr(ag, "_extract_skills", fake_extract_skills)

    agents, _, _, _ = ag.scan_agents(
        lambda: Image.new("RGB", (1920, 1080)),
        calib=calib,
    )
    assert len(agents) == 2


def test_scan_agents_empty_key_below_floor_is_critical_fail(monkeypatch):
    """T5: normalize_agent floors a junk name to ('', <real score>). A score in the
    30–84 band sails past the < _CRITICAL_CONF gate, so the empty key itself must be
    rejected — otherwise we'd build an agent with key="". Assert no agent is emitted
    and the slot is flagged critical_fail."""
    import youkai_ocr.agent_scanner as ag

    class FakeListener:
        def stop(self):
            pass

    class FakeNavigator:
        def __init__(self, *a, **k):
            pass

        def scan(self):
            dummy = Image.new("RGB", (1920, 1080), (80, 80, 80))
            yield 0, dummy, dummy, []

    calib = _identity_calib()

    def fake_extract_base(frame, c, rec):
        # empty key, but score 50 > _CRITICAL_CONF (30): the exact T5 gap
        return "", 60, 5, {"key": 50.0, "level": 90.0, "ascension": 90.0}

    def fake_extract_skills(frame, c, rec):
        return 0, ZodTalent(basic=10, dodge=10, assist=10, special=10, chain=10, core=6), {}

    _E = type("E", (), {"is_set": lambda s: False, "set": lambda s: None})()
    monkeypatch.setattr(ag, "AgentNavigator", FakeNavigator)
    monkeypatch.setattr(ag, "make_recognizer", lambda *a, **k: object())
    monkeypatch.setattr(ag, "make_kill_listener", lambda suppress_flag=None: (_E, FakeListener()))
    monkeypatch.setattr(ag, "_extract_base_stats", fake_extract_base)
    monkeypatch.setattr(ag, "_extract_skills", fake_extract_skills)

    agents, issues, _, _ = ag.scan_agents(
        lambda: Image.new("RGB", (1920, 1080)),
        calib=calib,
    )
    assert agents == []
    assert any(i["status"] == "critical_fail" for i in issues)


def test_scan_single_frame_agent_empty_key_below_floor_returns_none(monkeypatch):
    """T5: same gap on the offline single-frame path."""
    import youkai_ocr.agent_scanner as ag

    calib = _identity_calib()
    frame = _dark_frame()

    def fake_extract_base(f, c, rec):
        return "", 60, 5, {"key": 50.0, "level": 90.0, "ascension": 90.0}

    def fake_extract_skills(f, c, rec):
        return 0, ZodTalent(basic=10, dodge=10, assist=10, special=10, chain=10, core=6), {}

    monkeypatch.setattr(ag, "make_recognizer", lambda *a, **k: object())
    monkeypatch.setattr(ag, "_extract_base_stats", fake_extract_base)
    monkeypatch.setattr(ag, "_extract_skills", fake_extract_skills)

    agent, conf = ag.scan_single_frame_agent(frame, frame, calib)
    assert agent is None
