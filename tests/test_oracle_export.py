"""T6.2 — Oracle-export talent regression gate.

Replays agent golden fixtures through scan_single_frame_agent and validates
talent values against oracle_export.json (the reference eZOD export).

Agents without golden-fixture images are skipped. Known scanner bugs (Bug-A,
Bug-B, Bug-B2, Bug-C from oracle_talent.json) are xfailed per-agent so that
the gate flags regressions without blocking on pre-existing issues.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from youkai_ocr.capture import CalibrationResult
from youkai_ocr.agent_scanner import scan_single_frame_agent

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "golden"
ORACLE_EXPORT = FIXTURES / "oracle_export.json"
ORACLE_TALENT = FIXTURES / "oracle_talent.json"

REFERENCE_W = 1920
REFERENCE_H = 1080


def _identity_calib() -> CalibrationResult:
    return CalibrationResult(
        scale_x=1.0, scale_y=1.0,
        frame_width=REFERENCE_W, frame_height=REFERENCE_H,
    )


def _load_oracles():
    """Return (export_by_key, archive_idx_to_key, known_bugs_by_key)."""
    if not ORACLE_EXPORT.exists() or not ORACLE_TALENT.exists():
        return None, None, None

    export = json.loads(ORACLE_EXPORT.read_text())
    talent_oracle = json.loads(ORACLE_TALENT.read_text())

    export_by_key = {c["key"]: c for c in export.get("characters", [])}

    # archive_idx -> (key, has_mismatch)
    archive_map = {}
    known_bugs = {}
    for a in talent_oracle["agents"]:
        key = a["key"]
        archive_map[a["archive_idx"]] = key
        if a.get("mismatches"):
            known_bugs[key] = a.get("bug", "known mismatch")

    return export_by_key, archive_map, known_bugs


def _collect_cases():
    """Return list of (idx_str, agent_key, expected_talent, bug_reason_or_None)."""
    export_by_key, archive_map, known_bugs = _load_oracles()
    if export_by_key is None:
        return []

    cases = []
    for idx, key in sorted(archive_map.items()):
        idx_str = f"{idx:03d}"
        base_path = FIXTURES / "agents" / f"agent_{idx_str}_base.png"
        skills_path = FIXTURES / "agents" / f"agent_{idx_str}_skills.png"
        if not base_path.exists() or not skills_path.exists():
            continue  # no fixture for this agent — skip
        if key not in export_by_key:
            continue  # agent not in oracle export — skip
        expected_talent = export_by_key[key].get("talent", {})
        bug_reason = known_bugs.get(key)
        cases.append((idx_str, key, expected_talent, bug_reason))
    return cases


_CASES = _collect_cases()
_IDS = [f"{idx}_{key}" for idx, key, _, _ in _CASES]


@pytest.mark.parametrize("idx_str,key,expected_talent,bug_reason", _CASES, ids=_IDS)
def test_oracle_talent(idx_str, key, expected_talent, bug_reason):
    """For each agent with a golden fixture, scanner talent matches oracle export."""
    if not _CASES:
        pytest.skip("oracle files missing")

    base_path = FIXTURES / "agents" / f"agent_{idx_str}_base.png"
    skills_path = FIXTURES / "agents" / f"agent_{idx_str}_skills.png"

    base_frame = Image.open(base_path).convert("RGB")
    skills_frame = Image.open(skills_path).convert("RGB")
    calib = _identity_calib()

    agent, conf = scan_single_frame_agent(base_frame, skills_frame, calib)

    if bug_reason:
        pytest.xfail(reason=bug_reason)

    assert agent is not None, f"{key}: scan returned None"
    got = agent.talent.to_dict() if agent.talent is not None else {}
    mismatches = {
        skill: (got.get(skill), exp)
        for skill, exp in expected_talent.items()
        if got.get(skill) != exp
    }
    assert not mismatches, (
        f"{key}: talent mismatches vs oracle_export.json: {mismatches}"
    )
