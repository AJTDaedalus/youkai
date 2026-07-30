"""End-to-end reads against live ZZZ 3.1 frames, not synthetic ones.

The bbox tests elsewhere assert invariants (stay off the pill border, exclude the
artwork).  Those would still pass if ZZZ moved the widget again, which is exactly
how the 2026-07-30 failures went unnoticed: geometry drifted, every unit test stayed
green, and the export quietly filled with ascension 0 and dropped engines.  These
run the real recognizers over committed live frames so a future drift fails here.

Requires Tesseract; skipped when it is unavailable.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from youkai_ocr.capture import calibrate

_REF = Path(__file__).parent.parent / "reference"
_AGENT = _REF / "reference_21_agent_base_stats_3_1.png"  # Qingyi, Lv.60, cap 60
_ENGINE_NAME = _REF / "reference_22_engine_name_two_line.png"  # "[Reverb] Mark II"


def _tesseract_available() -> bool:
    try:
        from youkai_ocr.recognize import resolve_tesseract

        cmd, _ = resolve_tesseract()
    except Exception:
        return False
    if cmd is None:
        import shutil

        return shutil.which("tesseract") is not None
    return True


pytestmark = [
    pytest.mark.skipif(not _AGENT.exists(), reason="live 3.1 reference frames not present"),
    pytest.mark.skipif(not _tesseract_available(), reason="Tesseract not installed"),
]


def _load(path: Path):
    frame = Image.open(path).convert("RGB")
    return frame, calibrate(frame)


# ── Agent base stats ──────────────────────────────────────────────────────────


def test_level_cap_reads_sixty():
    """cap read 0 on 41 of 42 agents before the bbox fix, taking ascension with it."""
    from youkai_ocr.agent_scanner import _read_level_cap

    frame, calib = _load(_AGENT)
    assert _read_level_cap(frame, calib) == 60


def test_base_stats_give_level_sixty_ascension_five():
    """Level 60 is reachable only at cap 60, so ascension 5 is the only valid answer.

    This frame previously produced ascension 0 (and other frames level 90 or 99).
    """
    from youkai_ocr.agent_scanner import _extract_base_stats
    from youkai_ocr.recognize import make_recognizer

    frame, calib = _load(_AGENT)
    key, level, ascension, conf = _extract_base_stats(frame, calib, make_recognizer("tesseract"))
    assert level == 60
    assert ascension == 5
    assert conf["ascension"] == 90.0, "should come from the cap read, not the level floor"


def test_qingyi_name_resolves():
    """Tesseract reads the Q as G; 'Gingyi' scored 83.3 against the 85 floor and the
    agent was dropped from the export entirely."""
    from youkai_ocr.agent_scanner import _AGENT_NAME_BBOX, _crop
    from youkai_ocr.normalizer import normalize_agent
    from youkai_ocr.recognize import make_recognizer

    frame, calib = _load(_AGENT)
    raw = make_recognizer("tesseract").read_line(
        _crop(frame, calib, _AGENT_NAME_BBOX), "white_text_on_dark"
    )
    key, score = normalize_agent(raw)
    assert key == "Qingyi", f"raw OCR {raw!r} scored {score}"


# ── Engine name ───────────────────────────────────────────────────────────────


@pytest.mark.skipif(not _ENGINE_NAME.exists(), reason="engine name fixture not present")
def test_two_line_engine_name_is_not_mismatched():
    """Cropped to the text column this reads '[Reverb] Mark II'.

    With the artwork left in, psm 6 returned a bare 'Mark Il' that fuzzy-matched
    Demara Battery Mark II at 90 — the wrong engine, on 13 copies.
    """
    from youkai_ocr.normalizer import normalize_engine
    from youkai_ocr.recognize import make_recognizer
    from youkai_ocr.wengine_scanner import _NAME_BBOX

    full = Image.open(_ENGINE_NAME).convert("RGB")
    # The fixture is the crop the old bbox produced; trim it to the new one.
    w = _NAME_BBOX[2] - _NAME_BBOX[0]
    h = _NAME_BBOX[3] - _NAME_BBOX[1]
    crop = full.crop((0, 0, min(w, full.width), min(h, full.height)))
    raw = make_recognizer("tesseract").read_text(crop, "white_text_on_dark").replace("\n", " ")
    key, score = normalize_engine(raw.strip())
    assert key == "ReverbMarkII", f"raw OCR {raw!r} scored {score}"
