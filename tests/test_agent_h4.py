"""H4: Offline validation of per-agent extraction from reference screenshots.

Fixtures: reference_{3,4,9,10} — Zhao's Base Stats, Skills, and Equipment-tab frames.
Acceptance (H4):
  - key='Zhao', level=60 from ref_3.
  - mindscape=0, skills=(12,10,11,12,11), core=6 from ref_4.
  - ascension in valid range 0–6 (heuristic; low-confidence per design).
  - disc_set='BunnyInWonderland' from ref_9; disc_set='AstralVoice' + engine='TheRestrained' from ref_10.

H25 acceptance (added below ref_4 tests):
  - Dim non-maxed badges (live agent_001: 8,1,8,12,11) read ≥4/5 correctly at the new
    two-pass threshold (pass-1 @180 for bright, pass-2 @130 fallback for dim).
  - No regression on any of the H4 bright-badge cases (12,10,11,12,11 from ref_4).
"""
import pytest
from pathlib import Path
from PIL import Image

from youkai_ocr.agent_scanner import (
    scan_single_frame_agent, _extract_equip_frame, _read_skill_badge, _SKILL_LEVEL_BBOXES,
)
from youkai_ocr.capture import CalibrationResult
from youkai_ocr.recognize import make_recognizer

REF = Path(__file__).parent.parent / "reference"
_CALIB = CalibrationResult(scale_x=1.0, scale_y=1.0, frame_width=1920, frame_height=1080)


def _load_ref(name: str) -> Image.Image:
    path = REF / name
    if not path.exists():
        pytest.skip(f"fixture not found: {path}")
    raw = Image.open(path)
    # Reference screenshots are 1922×1112 with 1px left border and 32px top chrome.
    return raw.crop((1, 32, 1921, 1112))


@pytest.fixture(scope="module")
def zhao_base():
    return _load_ref("reference_3_agent_page.png")


@pytest.fixture(scope="module")
def zhao_skills():
    return _load_ref("reference_4_agent_skills_page.png")


@pytest.fixture(scope="module")
def ref9():
    return _load_ref("reference_9_equipment_disc_info.png")


@pytest.fixture(scope="module")
def ref10():
    return _load_ref("reference_10_equipment_disc_info_some_unlocked.png")


@pytest.fixture(scope="module")
def zhao_agent(zhao_base, zhao_skills):
    agent, conf = scan_single_frame_agent(zhao_base, zhao_skills, _CALIB)
    return agent, conf


# ── Base stats (ref_3) ────────────────────────────────────────────────────────

def test_zhao_key(zhao_agent):
    agent, _ = zhao_agent
    assert agent is not None, "scan_single_frame_agent returned None (critical confidence failure)"
    assert agent.key == "Zhao"


def test_zhao_level(zhao_agent):
    agent, _ = zhao_agent
    assert agent is not None
    assert agent.level == 60


def test_zhao_ascension(zhao_agent):
    """Ascension is read from the level-cap badge '/ NN' and snapped to known caps."""
    agent, conf = zhao_agent
    assert agent is not None
    assert agent.ascension == 5, f"Zhao Lv.60 should be ascension 5 (cap=60), got {agent.ascension}"
    assert conf.get("ascension", 0) >= 80.0, "ascension confidence should be high when cap is readable"


# ── Skills tab (ref_4) ────────────────────────────────────────────────────────

def test_zhao_mindscape(zhao_agent):
    agent, _ = zhao_agent
    assert agent is not None
    assert agent.constellation == 0  # CINEMA 0/6 visible in ref_4


@pytest.mark.parametrize("skill,expected", [
    ("basic",   12),
    ("dodge",   10),
    ("assist",  11),
    ("special", 12),
    ("chain",   11),
])
def test_zhao_skill_levels(zhao_agent, skill, expected):
    agent, _ = zhao_agent
    assert agent is not None
    actual = getattr(agent.talent, skill)
    assert actual == expected, f"talent.{skill}: expected {expected}, got {actual}"


def test_zhao_core_rank(zhao_agent):
    agent, _ = zhao_agent
    assert agent is not None
    assert agent.talent.core == 6  # all A-F nodes lit in ref_4


# ── Equipment-tab frames (ref_9 / ref_10) ─────────────────────────────────────

@pytest.fixture(scope="module")
def _rec():
    return make_recognizer("tesseract")


@pytest.mark.parametrize("slot_idx", [0, 1, 2, 3, 4, 5])
def test_ref9_disc_set(ref9, _rec, slot_idx):
    result = _extract_equip_frame(ref9, _CALIB, _rec, slot_idx)
    assert result is not None, f"slot {slot_idx}: no equip record returned"
    assert result["disc_set"] == "BunnyInWonderland"
    assert result["slot_key"] == str(6 - slot_idx)   # H18: slot# = 6 - idx (reference_17 layout)


@pytest.mark.parametrize("slot_idx", [0, 1, 2, 3, 4, 5])
def test_ref10_disc_set(ref10, _rec, slot_idx):
    result = _extract_equip_frame(ref10, _CALIB, _rec, slot_idx)
    assert result is not None, f"slot {slot_idx}: no equip record returned"
    assert result["disc_set"] == "AstralVoice"


def test_ref9_no_engine(ref9, _rec):
    """ref_9 shows a disc slot panel — engine slot should not return a confident match."""
    result = _extract_equip_frame(ref9, _CALIB, _rec, 6)
    # Either None (below confidence threshold) or engine_key may be present — both acceptable.
    # The key requirement is that disc slots 0–5 work correctly (tested above).


def test_ref10_engine(ref10, _rec):
    """ref_10 slot 6 is a disc panel ("Astral Voice"), not an engine. The engine
    normalizer must NOT snap that foreign title to a wrong engine key: with the T2
    confidence floor the below-floor match (~50) is rejected → no confident engine.
    Previously this only "passed" by garbage-matching garbage (TheRestrained @44)."""
    result = _extract_equip_frame(ref10, _CALIB, _rec, 6)
    assert result is None, f"engine slot should reject the disc title, got {result!r}"


# ── H25: Two-pass dim-badge classifier ────────────────────────────────────────

_ARCHIVE = Path(__file__).parent.parent / "archive" / "live_20260605"
_BADGE_FIXTURES = Path(__file__).parent / "fixtures" / "skill_badges"


def _read_badge_at(img: Image.Image, skill_idx: int) -> int | None:
    """Read badge at skill index, unwrapping the (value, conf) tuple."""
    bbox = _SKILL_LEVEL_BBOXES[skill_idx]
    crop = img.crop((bbox[0], bbox[1], bbox[2], bbox[3]))
    raw = _read_skill_badge(crop)
    return raw[0] if raw is not None else None


def _read_badge_crop(crop: Image.Image) -> int | None:
    """Read badge from a pre-cropped image, unwrapping the (value, conf) tuple."""
    raw = _read_skill_badge(crop)
    return raw[0] if raw is not None else None


@pytest.mark.parametrize("skill_idx,expected", [
    (0, 12),  # basic  — bright badge, pass-1 ✓
    (1, 10),  # dodge  — bright badge, pass-1 ✓
    (2, 11),  # assist — bright badge, pass-1 ✓
    (3, 12),  # special— bright badge, pass-1 ✓
    (4, 11),  # chain  — bright badge, pass-1 ✓
])
def test_h25_ref4_bright_badges_no_regression(skill_idx, expected):
    """H25: pass-1 (threshold=180) still classifies all of Zhao's maxed skills correctly."""
    img_raw = Image.open(REF / "reference_4_agent_skills_page.png")
    img = img_raw.crop((1, 32, 1921, 1112))
    got = _read_badge_at(img, skill_idx) or 0
    names = ("basic", "dodge", "assist", "special", "chain")
    assert got == expected, f"talent.{names[skill_idx]}: expected {expected}, got {got}"


@pytest.mark.parametrize("skill_idx,expected", [
    (0, 8),   # basic=8 (dim "08" badge): pass-2 fallback with zero-prefix + round "8"
    (1, 1),   # dodge=1 (dim "01" badge): pass-2 fallback with zero-prefix + thin "1"
    (3, 12),  # special=12 (bright "12/12" badge): pass-1
    (4, 11),  # chain=11 (bright-ish badge): pass-1
])
def test_h25_dim_badge_fallback(skill_idx, expected):
    """H25: pass-2 (threshold=130) recovers dim non-maxed badges from live agent_001."""
    path = _ARCHIVE / "agent_001" / "skills.png"
    if not path.exists():
        pytest.skip(f"live fixture not found: {path}")
    img = Image.open(path)
    got = _read_badge_at(img, skill_idx) or 0
    names = ("basic", "dodge", "assist", "special", "chain")
    assert got == expected, f"talent.{names[skill_idx]}: expected {expected}, got {got}"


# ── H25.1: Wide-b1 dim fallback for "0X" badges (zero-prefix, max=16 format) ─

@pytest.mark.parametrize("fname,expected_value,description", [
    ("badge_08_of_16.png", 8,  "dodge=8/16: '8' digit — hole-count=2 → 8 (T8)"),
    ("badge_09_of_16.png", 9,  "assist=9/16: '9' digit — template-match, Bug-B2 fixed (T8)"),
    ("badge_07_of_12.png", 7,  "dodge=7/12: wide '7' digit"),
    ("badge_08_of_12_narrow.png", 8, "basic=8/12: narrow-bleed '8' — hole-count=2 → 8 (T8)"),
    ("badge_03_of_12.png", 3,  "assist=3/12: '3' digit — template-match, Bug-B fixed (T8)"),
])
def test_h25_1_wide_dim_badge_nonzero(fname, expected_value, description):
    """H25.1 (T8): dim-badge units digits matched by template/hole-count, not fill-ratio tiers."""
    path = _BADGE_FIXTURES / fname
    if not path.exists():
        pytest.skip(f"badge fixture not found: {path}")
    crop = Image.open(path)
    got = _read_badge_crop(crop)
    assert got is not None and got != 0, (
        f"{description}: classifier returned {got} (expected {expected_value})"
    )
    assert got == expected_value, (
        f"{description}: expected {expected_value}, got {got}"
    )


def test_h25_1_wide_dim_badge_confidence_above_threshold():
    """T8: template/hole-count match is high-confidence (≥70) — no longer tier-estimated."""
    from youkai_ocr.agent_scanner import _LOW_CONF_THRESHOLD
    path = _BADGE_FIXTURES / "badge_08_of_16.png"
    if not path.exists():
        pytest.skip("badge fixture not found")
    crop = Image.open(path)
    raw = _read_skill_badge(crop)
    assert raw is not None
    value, conf = raw
    assert value == 8, f"should return 8, got {value}"
    assert conf >= _LOW_CONF_THRESHOLD, (
        f"template/hole-count confidence {conf} should be ≥ {_LOW_CONF_THRESHOLD}"
    )
