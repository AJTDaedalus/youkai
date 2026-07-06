"""F2: Golden-replay accuracy gate.

Replays archived panel crops through the real OCR extractors (no game required)
and enforces the §10 accuracy gate: ≥99% name/key fields correct, ≥98% numeric
fields correct, every miss surfaced as low confidence (no silent wrong values).

Also contains negative-control tests:
  - Night-Light-tinted frame is rejected by check_color_hygiene()
  - Wrong-aspect-ratio frame (1920×900) is rejected by calibrate()
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image

from youkai_ocr.agent_scanner import scan_single_frame_agent
from youkai_ocr.capture import CalibrationResult, calibrate, check_color_hygiene
from youkai_ocr.disc_scanner import scan_single_frame as scan_single_frame_disc
from youkai_ocr.wengine_scanner import scan_single_frame_engine

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "golden"
LABELS = FIXTURES / "labels.json"

# §10 accuracy thresholds
NAME_GATE = 0.99  # ≥99% of name/key fields must be correct
NUMERIC_GATE = 0.98  # ≥98% of numeric fields must be correct
SILENT_WRONG_CONF = 70  # a wrong value must have confidence below this


REFERENCE_W = 1920
REFERENCE_H = 1080
# Both disc and engine panel crops sit at this origin in the reference frame.
_PANEL_ORIGIN = (1421, 100)


def _panel_to_frame(panel_path: Path) -> Image.Image:
    """Paste a 439×770 panel crop onto a 1920×1080 black canvas."""
    panel = Image.open(panel_path).convert("RGB")
    frame = Image.new("RGB", (REFERENCE_W, REFERENCE_H), color=(0, 0, 0))
    frame.paste(panel, _PANEL_ORIGIN)
    return frame


def _identity_calib() -> CalibrationResult:
    return CalibrationResult(
        scale_x=1.0,
        scale_y=1.0,
        frame_width=REFERENCE_W,
        frame_height=REFERENCE_H,
    )


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def labels() -> dict:
    if not LABELS.exists():
        pytest.skip("golden fixture labels.json missing")
    return json.loads(LABELS.read_text())


# ── Disc replay ───────────────────────────────────────────────────────────────


class DiscAccumulator:
    """Collects per-field hits/misses across the full disc set."""

    def __init__(self):
        self.name_total = 0
        self.name_correct = 0
        self.num_total = 0
        self.num_correct = 0
        self.silent_wrongs: list[str] = []

    def record_name(self, got: Any, expected: Any, conf: float, label: str) -> None:
        self.name_total += 1
        if got == expected:
            self.name_correct += 1
        elif conf >= SILENT_WRONG_CONF:
            self.silent_wrongs.append(f"{label}: got={got!r} expected={expected!r} conf={conf:.0f}")

    def record_numeric(self, got: Any, expected: Any, conf: float, label: str) -> None:
        self.num_total += 1
        if got == expected or (
            isinstance(got, float) and isinstance(expected, float) and abs(got - expected) < 0.05
        ):
            self.num_correct += 1
        elif conf >= SILENT_WRONG_CONF:
            self.silent_wrongs.append(f"{label}: got={got!r} expected={expected!r} conf={conf:.0f}")


def test_disc_golden_replay(labels):
    calib = _identity_calib()
    acc = DiscAccumulator()
    failures: list[str] = []

    for item in labels["discs"]:
        disc_id: str = item["id"]
        expect: dict = item["expect"]
        panel_path = FIXTURES / "discs" / f"{disc_id}.png"
        if not panel_path.exists():
            pytest.skip(f"panel missing: {panel_path}")

        frame = _panel_to_frame(panel_path)
        disc, conf = scan_single_frame_disc(frame, calib)

        if disc is None:
            failures.append(f"{disc_id}: extraction returned None (conf={conf})")
            continue

        # Name/key fields
        acc.record_name(disc.set_key, expect["set_key"], conf.get("set", 0.0), f"{disc_id}.set_key")
        acc.record_name(
            disc.slot_key, str(expect["slot_key"]), conf.get("slot", 0.0), f"{disc_id}.slot_key"
        )
        acc.record_name(
            disc.main_stat_key,
            expect["main_stat_key"],
            conf.get("main_stat", 0.0),
            f"{disc_id}.main_stat_key",
        )

        # Numeric fields
        acc.record_numeric(disc.level, expect["level"], conf.get("level", 0.0), f"{disc_id}.level")
        # Rarity is excluded: synthetic frame (black canvas) breaks rarity detection.

        # Substats: match by position; tolerate up to one extra/fewer row
        exp_subs = expect.get("substats", [])
        got_subs = disc.substats or []
        for i, (got_sub, exp_sub) in enumerate(zip(got_subs, exp_subs, strict=False)):
            sub_conf = conf.get(f"substat_{i}_key", 0.0)
            acc.record_name(got_sub.key, exp_sub["key"], sub_conf, f"{disc_id}.sub{i}.key")
            val_conf = conf.get(f"substat_{i}_val", 0.0)
            acc.record_numeric(got_sub.value, exp_sub["value"], val_conf, f"{disc_id}.sub{i}.value")

    # §10 gate assertions
    assert not acc.silent_wrongs, (
        f"Silent wrong values (conf ≥ {SILENT_WRONG_CONF}):\n" + "\n".join(acc.silent_wrongs)
    )
    assert failures == [], "Extraction failures:\n" + "\n".join(failures)

    if acc.name_total:
        name_rate = acc.name_correct / acc.name_total
        assert name_rate >= NAME_GATE, (
            f"Name accuracy {name_rate:.1%} < {NAME_GATE:.0%} ({acc.name_correct}/{acc.name_total})"
        )
    if acc.num_total:
        num_rate = acc.num_correct / acc.num_total
        assert num_rate >= NUMERIC_GATE, (
            f"Numeric accuracy {num_rate:.1%} < {NUMERIC_GATE:.0%} "
            f"({acc.num_correct}/{acc.num_total})"
        )


# ── Engine replay ─────────────────────────────────────────────────────────────


def test_engine_golden_replay(labels):
    calib = _identity_calib()
    name_total, name_correct = 0, 0
    num_total, num_correct = 0, 0
    silent_wrongs: list[str] = []
    failures: list[str] = []

    for item in labels["engines"]:
        eng_id: str = item["id"]
        expect: dict = item["expect"]
        panel_path = FIXTURES / "engines" / f"{eng_id}.png"
        if not panel_path.exists():
            pytest.skip(f"panel missing: {panel_path}")

        frame = _panel_to_frame(panel_path)
        engine, conf = scan_single_frame_engine(frame, calib)

        if engine is None:
            failures.append(f"{eng_id}: extraction returned None (conf={conf})")
            continue

        def rn(got, expected, c, label):
            nonlocal name_total, name_correct
            name_total += 1
            if got == expected:
                name_correct += 1
            elif c >= SILENT_WRONG_CONF:
                silent_wrongs.append(f"{label}: got={got!r} expected={expected!r} conf={c:.0f}")

        def rv(got, expected, c, label):
            nonlocal num_total, num_correct
            num_total += 1
            match = got == expected or (
                isinstance(got, (int, float))
                and isinstance(expected, (int, float))
                and abs(float(got) - float(expected)) < 0.5
            )
            if match:
                num_correct += 1
            elif c >= SILENT_WRONG_CONF:
                silent_wrongs.append(f"{label}: got={got!r} expected={expected!r} conf={c:.0f}")

        rn(engine.key, expect["key"], conf.get("key", 0.0), f"{eng_id}.key")
        rv(engine.level, expect["level"], conf.get("level", 0.0), f"{eng_id}.level")
        rv(engine.ascension, expect["ascension"], conf.get("ascension", 0.0), f"{eng_id}.ascension")
        rv(
            engine.refinement,
            expect["refinement"],
            conf.get("refinement", 0.0),
            f"{eng_id}.refinement",
        )

    assert not silent_wrongs, f"Silent wrong values (conf ≥ {SILENT_WRONG_CONF}):\n" + "\n".join(
        silent_wrongs
    )
    assert failures == [], "Extraction failures:\n" + "\n".join(failures)

    if name_total:
        rate = name_correct / name_total
        assert rate >= NAME_GATE, (
            f"Engine name accuracy {rate:.1%} < {NAME_GATE:.0%} ({name_correct}/{name_total})"
        )
    if num_total:
        rate = num_correct / num_total
        assert rate >= NUMERIC_GATE, (
            f"Engine numeric accuracy {rate:.1%} < {NUMERIC_GATE:.0%} ({num_correct}/{num_total})"
        )


# ── Agent replay ──────────────────────────────────────────────────────────────


def test_agent_golden_replay(labels):
    calib = _identity_calib()
    name_total, name_correct = 0, 0
    num_total, num_correct = 0, 0
    silent_wrongs: list[str] = []
    failures: list[str] = []

    for item in labels["agents"]:
        agent_id: str = item["id"]
        expect: dict = item["expect"]
        n = agent_id.split("_", 1)[1]  # "000"
        base_path = FIXTURES / "agents" / f"agent_{n}_base.png"
        skills_path = FIXTURES / "agents" / f"agent_{n}_skills.png"
        if not base_path.exists() or not skills_path.exists():
            pytest.skip(f"agent frames missing: {agent_id}")

        base_frame = Image.open(base_path).convert("RGB")
        skills_frame = Image.open(skills_path).convert("RGB")
        agent, conf = scan_single_frame_agent(base_frame, skills_frame, calib)

        if agent is None:
            failures.append(f"{agent_id}: extraction returned None (conf={conf})")
            continue

        def rn(got, expected, c, label):
            nonlocal name_total, name_correct
            name_total += 1
            if got == expected:
                name_correct += 1
            elif c >= SILENT_WRONG_CONF:
                silent_wrongs.append(f"{label}: got={got!r} expected={expected!r} conf={c:.0f}")

        def rv(got, expected, c, label):
            nonlocal num_total, num_correct
            num_total += 1
            match = got == expected or (
                isinstance(got, (int, float))
                and isinstance(expected, (int, float))
                and abs(float(got) - float(expected)) < 0.5
            )
            if match:
                num_correct += 1
            elif c >= SILENT_WRONG_CONF:
                silent_wrongs.append(f"{label}: got={got!r} expected={expected!r} conf={c:.0f}")

        rn(agent.key, expect["key"], conf.get("key", 0.0), f"{agent_id}.key")
        rv(agent.level, expect["level"], conf.get("level", 0.0), f"{agent_id}.level")
        rv(
            agent.constellation,
            expect["constellation"],
            conf.get("mindscape", conf.get("constellation", 0.0)),
            f"{agent_id}.constellation",
        )
        rv(
            agent.ascension,
            expect["ascension"],
            conf.get("ascension", 0.0),
            f"{agent_id}.ascension",
        )

        exp_talent: dict = expect.get("talent", {})
        got_talent_dict = agent.talent.to_dict() if agent.talent is not None else {}
        for skill_name, exp_val in exp_talent.items():
            skill_conf = conf.get(f"talent_{skill_name}", conf.get("talent", 0.0))
            rv(
                got_talent_dict.get(skill_name),
                exp_val,
                float(skill_conf),
                f"{agent_id}.talent.{skill_name}",
            )

    assert not silent_wrongs, f"Silent wrong values (conf ≥ {SILENT_WRONG_CONF}):\n" + "\n".join(
        silent_wrongs
    )
    assert failures == [], "Extraction failures:\n" + "\n".join(failures)

    if name_total:
        rate = name_correct / name_total
        assert rate >= NAME_GATE, (
            f"Agent name accuracy {rate:.1%} < {NAME_GATE:.0%} ({name_correct}/{name_total})"
        )
    if num_total:
        rate = num_correct / num_total
        assert rate >= NUMERIC_GATE, (
            f"Agent numeric accuracy {rate:.1%} < {NUMERIC_GATE:.0%} ({num_correct}/{num_total})"
        )


# ── Negative controls ─────────────────────────────────────────────────────────


def test_negative_tinted_frame_rejected():
    """A Night-Light-warm-tinted frame must be refused by check_color_hygiene()."""
    # Simulate a warm Night Light shift: R strong, G moderate, B suppressed.
    # Target bright-pixel means ~ (240, 190, 120) → ratio = 120/240 = 0.50 < 0.85
    arr = np.zeros((REFERENCE_H, REFERENCE_W, 3), dtype=np.uint8)
    # Fill with a warm-white tone — looks like Night Light applied to white UI
    arr[:, :] = [240, 190, 120]
    frame = Image.fromarray(arr, "RGB")

    with pytest.raises(ValueError, match="color-shifted"):
        check_color_hygiene(frame)


def test_negative_wrong_resolution_rejected():
    """A non-16:9 frame (1920×900) must be refused by calibrate()."""
    frame = Image.new("RGB", (1920, 900), color=(255, 255, 255))
    with pytest.raises(ValueError, match="aspect ratio"):
        calibrate(frame)


def test_positive_clean_frame_passes_hygiene():
    """A neutral-white frame (clean game UI tone) must pass check_color_hygiene()."""
    # Near-equal channel means → ratio ≈ 1.0
    arr = np.full((REFERENCE_H, REFERENCE_W, 3), 230, dtype=np.uint8)
    frame = Image.fromarray(arr, "RGB")
    check_color_hygiene(frame)  # should not raise
