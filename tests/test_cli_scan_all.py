"""H5/H7c tests: run-dir persistence, screen-assertion preflights, resume, and auto-nav driver.

All tests mock external calls (calibrate_window, scan_*, _preflight_frame,
_countdown, input) so no game window or OCR engine is needed.
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import numpy as np
import pytest
from PIL import Image, ImageDraw

from youkai_ocr.capture import CalibrationResult
from youkai_ocr.cli import (
    ScreenAssertError,
    _AGENT_MENU_SIG_BBOX,
    _MAIN_MENU_SIG_BBOX,
    _check_agent_screen,
    _check_disc_screen,
    _check_engine_screen,
    _cmd_scan_all,
    _is_agent_selection_menu,
    _is_main_menu,
    _make_first_item_check,
    _preflight_frame,
    _reconcile_locations,
    select_phases,
)
from youkai_ocr.zod import ZodAgent, ZodDisc, ZodSubstat, ZodWEngine


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _identity_calib() -> CalibrationResult:
    return CalibrationResult(
        scale_x=1.0, scale_y=1.0,
        frame_width=1920, frame_height=1080,
        window_left=0, window_top=0,
    )


def _fake_frame() -> Image.Image:
    return Image.new("RGB", (1920, 1080), color=(80, 80, 80))


def _sample_disc() -> ZodDisc:
    return ZodDisc(
        set_key="ShockstarDisc", slot_key="1", level=10, rarity=4,
        main_stat_key="HP", location="", lock=False,
    )


def _sample_engine() -> ZodWEngine:
    return ZodWEngine(
        key="TheSharpshooting", level=60, ascension=6,
        refinement=1, location="", lock=False,
    )


def _sample_agent() -> ZodAgent:
    return ZodAgent(key="Zhao", level=60, constellation=0, ascension=5)


def _make_args(tmp_path: Path, resume: str | None = None) -> SimpleNamespace:
    """Manual-nav args — existing tests stay on the input()-gated path."""
    return SimpleNamespace(
        output=str(tmp_path / "export" / "out.json"),
        archive_dir=str(tmp_path / "base"),  # base dir; timestamped subdir is created inside
        engine="tesseract",
        resume=resume,
        manual_nav=True,
    )


def _make_auto_nav_args(tmp_path: Path) -> SimpleNamespace:
    """Auto-nav args for H7c driver tests."""
    return SimpleNamespace(
        output=str(tmp_path / "export" / "out.json"),
        archive_dir=str(tmp_path / "base"),
        engine="tesseract",
        resume=None,
        manual_nav=False,
        agents_only=False,
        debug_overlays=False,
    )


# ── Frame builders for screen-predicate tests ─────────────────────────────────

def _make_main_menu_frame() -> Image.Image:
    """1920×1080 frame with bright pixels in the main-menu signature bbox."""
    img  = Image.new("RGB", (1920, 1080), color=(0, 0, 0))
    x1, y1, x2, y2 = _MAIN_MENU_SIG_BBOX
    ImageDraw.Draw(img).rectangle([x1, y1, x2 - 1, y2 - 1], fill=(200, 200, 200))
    return img


def _make_agent_menu_frame() -> Image.Image:
    """1920×1080 frame with teal pixels in the agent-menu signature bbox."""
    img  = Image.new("RGB", (1920, 1080), color=(0, 0, 0))
    x1, y1, x2, y2 = _AGENT_MENU_SIG_BBOX
    # teal: G-R>30 AND G>100 → (20, 150, 150)
    ImageDraw.Draw(img).rectangle([x1, y1, x2 - 1, y2 - 1], fill=(20, 150, 150))
    return img


def _find_run_dir(base_dir: str) -> Path:
    """Return the single timestamped subdir created inside base_dir by _cmd_scan_all."""
    subdirs = [p for p in Path(base_dir).iterdir() if p.is_dir()]
    assert len(subdirs) == 1, f"Expected 1 run subdir, found {len(subdirs)}: {subdirs}"
    return subdirs[0]


# ── Screen assertion unit tests ───────────────────────────────────────────────

def test_check_disc_screen_raises_when_count_none():
    frame = _fake_frame()
    calib = _identity_calib()
    with patch("youkai_ocr.disc_scanner.read_disc_count", return_value=None), \
         patch("youkai_ocr.recognize.make_recognizer", return_value=MagicMock()):
        with pytest.raises(ScreenAssertError, match="Drive Disc inventory not detected"):
            _check_disc_screen(frame, calib)


def test_check_disc_screen_passes_when_count_returned():
    frame = _fake_frame()
    calib = _identity_calib()
    with patch("youkai_ocr.disc_scanner.read_disc_count", return_value=42), \
         patch("youkai_ocr.recognize.make_recognizer", return_value=MagicMock()):
        _check_disc_screen(frame, calib)  # no exception


def test_check_engine_screen_warns_when_count_none(capsys):
    # _check_engine_screen is warn-not-abort (thumb-stop handles missing count).
    frame = _fake_frame()
    calib = _identity_calib()
    with patch("youkai_ocr.wengine_scanner.read_engine_count", return_value=None), \
         patch("youkai_ocr.recognize.make_recognizer", return_value=MagicMock()):
        _check_engine_screen(frame, calib)  # must NOT raise
    captured = capsys.readouterr()
    assert "WARNING" in captured.out


def test_check_engine_screen_passes_when_count_returned(capsys):
    frame = _fake_frame()
    calib = _identity_calib()
    with patch("youkai_ocr.wengine_scanner.read_engine_count", return_value=5), \
         patch("youkai_ocr.recognize.make_recognizer", return_value=MagicMock()):
        _check_engine_screen(frame, calib)  # no exception
    assert "WARNING" not in capsys.readouterr().out


def test_check_agent_screen_warns_on_black_frame(capsys):
    # _check_agent_screen warns on a nearly-black frame (game not visible).
    black_frame = Image.new("RGB", (1920, 1080), color=(0, 0, 0))
    calib = _identity_calib()
    _check_agent_screen(black_frame, calib)
    assert "WARNING" in capsys.readouterr().out


def test_check_agent_screen_passes_on_normal_frame(capsys):
    frame = _fake_frame()  # mean brightness ~80
    calib = _identity_calib()
    _check_agent_screen(frame, calib)  # no exception, no warning
    assert "WARNING" not in capsys.readouterr().out


# ── Full scan-all integration mocks ──────────────────────────────────────────

def _patched_scan_all(tmp_path: Path, args, disc_check=None, engine_check=None, agent_check=None):
    """Run _cmd_scan_all with all live calls mocked out."""
    calib = _identity_calib()
    disc = _sample_disc()
    engine = _sample_engine()
    agent = _sample_agent()

    with patch("youkai_ocr.capture.calibrate_window", return_value=(calib, MagicMock())), \
         patch("youkai_ocr.disc_scanner.scan_discs", return_value=([disc], [])), \
         patch("youkai_ocr.wengine_scanner.scan_engines", return_value=([engine], [])), \
         patch("youkai_ocr.agent_scanner.scan_agents", return_value=([agent], [], [], [])), \
         patch("youkai_ocr.cli._preflight_frame", return_value=_fake_frame()), \
         patch("youkai_ocr.cli._countdown"), \
         patch("youkai_ocr.cli._check_disc_screen",
               side_effect=disc_check if disc_check else lambda *a, **k: None), \
         patch("youkai_ocr.cli._check_engine_screen",
               side_effect=engine_check if engine_check else lambda *a, **k: None), \
         patch("youkai_ocr.cli._check_agent_screen",
               side_effect=agent_check if agent_check else lambda *a, **k: None), \
         patch("builtins.input", return_value=""):
        _cmd_scan_all(args)


def test_scan_all_writes_log_and_results_json(tmp_path):
    """scan-all creates a timestamped subdir with scan.log and results.json."""
    args = _make_args(tmp_path)

    _patched_scan_all(tmp_path, args)

    run_dir = _find_run_dir(args.archive_dir)
    assert run_dir.name.startswith("live_"), f"run dir should start with 'live_', got {run_dir.name}"
    assert (run_dir / "scan.log").exists(), "scan.log not written"
    results_path = run_dir / "results.json"
    assert results_path.exists(), "results.json not written"

    results = json.loads(results_path.read_text())
    assert results["summary"]["discs"] == 1
    assert results["summary"]["engines"] == 1
    assert results["summary"]["agents"] == 1
    assert results["summary"]["issues"] == 0
    assert "discs" in results["phases"]
    assert "engines" in results["phases"]
    assert "agents" in results["phases"]


def test_scan_all_writes_phase_output_files(tmp_path):
    """scan-all writes per-phase JSON files in the timestamped run dir."""
    args = _make_args(tmp_path)

    _patched_scan_all(tmp_path, args)

    run_dir = _find_run_dir(args.archive_dir)
    assert (run_dir / "discs.json").exists()
    assert (run_dir / "engines.json").exists()
    assert (run_dir / "agents.json").exists()

    discs_raw = json.loads((run_dir / "discs.json").read_text())
    assert len(discs_raw) == 1
    assert discs_raw[0]["setKey"] == "ShockstarDisc"


def test_scan_all_wrong_disc_screen_raises(tmp_path):
    """Wrong disc screen triggers ScreenAssertError, which main() turns into SystemExit(1)."""
    args = _make_args(tmp_path)

    def _bad_disc(*a, **k):
        raise ScreenAssertError("Drive Disc inventory not detected — test")

    with pytest.raises(ScreenAssertError):
        _patched_scan_all(tmp_path, args, disc_check=_bad_disc)


def test_scan_all_wrong_engine_screen_raises(tmp_path):
    args = _make_args(tmp_path)

    def _bad_engine(*a, **k):
        raise ScreenAssertError("W-Engine inventory not detected — test")

    with pytest.raises(ScreenAssertError):
        _patched_scan_all(tmp_path, args, engine_check=_bad_engine)


def test_scan_all_wrong_agent_screen_raises(tmp_path):
    args = _make_args(tmp_path)

    def _bad_agent(*a, **k):
        raise ScreenAssertError("Agent roster not detected — test")

    with pytest.raises(ScreenAssertError):
        _patched_scan_all(tmp_path, args, agent_check=_bad_agent)


def test_scan_all_resume_skips_disc_and_engine_phases(tmp_path):
    """With --resume pointing to a dir with discs.json + engines.json, those phases are skipped."""
    resume_dir = tmp_path / "previous_run"
    resume_dir.mkdir()

    disc = _sample_disc()
    engine = _sample_engine()
    (resume_dir / "discs.json").write_text(
        json.dumps([disc.to_dict()]), encoding="utf-8"
    )
    (resume_dir / "engines.json").write_text(
        json.dumps([engine.to_dict()]), encoding="utf-8"
    )

    args = _make_args(tmp_path, resume=str(resume_dir))

    # scan_discs and scan_engines should NOT be called during resume.
    calib = _identity_calib()
    agent = _sample_agent()

    with patch("youkai_ocr.capture.calibrate_window", return_value=(calib, MagicMock())), \
         patch("youkai_ocr.disc_scanner.scan_discs") as mock_discs, \
         patch("youkai_ocr.wengine_scanner.scan_engines") as mock_engines, \
         patch("youkai_ocr.agent_scanner.scan_agents", return_value=([agent], [], [], [])), \
         patch("youkai_ocr.cli._preflight_frame", return_value=_fake_frame()), \
         patch("youkai_ocr.cli._countdown"), \
         patch("youkai_ocr.cli._check_agent_screen"), \
         patch("builtins.input", return_value=""):
        _cmd_scan_all(args)

    mock_discs.assert_not_called()
    mock_engines.assert_not_called()

    run_dir = _find_run_dir(args.archive_dir)
    results = json.loads((run_dir / "results.json").read_text())
    assert results["phases"]["discs"]["resumed"] is True
    assert results["phases"]["engines"]["resumed"] is True
    assert results["summary"]["discs"] == 1
    assert results["summary"]["engines"] == 1


def test_scan_all_issues_written_to_run_dir(tmp_path):
    """issues.json is written inside the run dir, not beside the export file."""
    args = _make_args(tmp_path)
    calib = _identity_calib()
    agent = _sample_agent()
    issue = {"type": "unknown_agent", "raw": "???Dialyn???", "agent_idx": 0}

    with patch("youkai_ocr.capture.calibrate_window", return_value=(calib, MagicMock())), \
         patch("youkai_ocr.disc_scanner.scan_discs", return_value=([], [])), \
         patch("youkai_ocr.wengine_scanner.scan_engines", return_value=([], [])), \
         patch("youkai_ocr.agent_scanner.scan_agents", return_value=([agent], [issue], [], [])), \
         patch("youkai_ocr.cli._preflight_frame", return_value=_fake_frame()), \
         patch("youkai_ocr.cli._countdown"), \
         patch("youkai_ocr.cli._check_disc_screen"), \
         patch("youkai_ocr.cli._check_engine_screen"), \
         patch("youkai_ocr.cli._check_agent_screen"), \
         patch("builtins.input", return_value=""):
        _cmd_scan_all(args)

    run_dir = _find_run_dir(args.archive_dir)
    issues_path = run_dir / "issues.json"
    assert issues_path.exists(), "issues.json not written to run_dir"
    issues = json.loads(issues_path.read_text())
    assert len(issues) == 1
    assert issues[0]["raw"] == "???Dialyn???"

    # Must NOT be written beside the export file
    export_issues = Path(args.output).with_suffix(".issues.json")
    assert not export_issues.exists(), "issues.json must not be written beside the export file"


def test_scan_all_issues_json_carries_disc_repairs(tmp_path):
    """T9: a disc-phase issue entry with a `repairs` list (as scan_discs now
    emits once disc_rules.repair_disc is wired into _extract_disc) must reach
    the on-disk issues.json unchanged — not just live in the in-memory list."""
    args = _make_args(tmp_path)
    calib = _identity_calib()
    disc = _sample_disc()
    repair_record = [{
        "field": "substat[0]", "before": {"key": "def", "value": 44.0},
        "after": {"key": "def_", "value": 14.4}, "rule": "roll_suffix",
    }]
    disc_issue = {
        "cell": 0, "disc": disc.to_dict(), "status": "repaired",
        "repairs": repair_record,
    }

    with patch("youkai_ocr.capture.calibrate_window", return_value=(calib, MagicMock())), \
         patch("youkai_ocr.disc_scanner.scan_discs", return_value=([disc], [disc_issue])), \
         patch("youkai_ocr.wengine_scanner.scan_engines", return_value=([], [])), \
         patch("youkai_ocr.agent_scanner.scan_agents", return_value=([], [], [], [])), \
         patch("youkai_ocr.cli._preflight_frame", return_value=_fake_frame()), \
         patch("youkai_ocr.cli._countdown"), \
         patch("youkai_ocr.cli._check_disc_screen"), \
         patch("youkai_ocr.cli._check_engine_screen"), \
         patch("youkai_ocr.cli._check_agent_screen"), \
         patch("builtins.input", return_value=""):
        _cmd_scan_all(args)

    run_dir = _find_run_dir(args.archive_dir)
    issues = json.loads((run_dir / "issues.json").read_text())
    assert len(issues) == 1
    assert issues[0]["status"] == "repaired"
    assert issues[0]["repairs"] == repair_record

    review_text = (run_dir / "review.txt").read_text()
    assert "AUTO-REPAIRED DISC FIELDS" in review_text
    assert "substat[0]: {'key': 'def', 'value': 44.0} -> {'key': 'def_', 'value': 14.4}" in review_text


def test_scan_all_consecutive_runs_get_distinct_dirs(tmp_path):
    """Two consecutive runs (same --archive-dir) produce distinct subdirs."""
    args = _make_args(tmp_path)
    _patched_scan_all(tmp_path, args)
    _patched_scan_all(tmp_path, args)

    subdirs = [p for p in Path(args.archive_dir).iterdir() if p.is_dir()]
    # Two runs may land in the same second; allow 1 or 2 dirs (both are non-overwriting in practice)
    assert len(subdirs) >= 1
    for d in subdirs:
        assert d.name.startswith("live_")


# ── H7c: screen predicates ────────────────────────────────────────────────────

def test_is_main_menu_true_on_bright_sig_bbox():
    calib = _identity_calib()
    assert _is_main_menu(_make_main_menu_frame(), calib) is True


def test_is_main_menu_false_on_dark_frame():
    calib = _identity_calib()
    assert _is_main_menu(Image.new("RGB", (1920, 1080), (0, 0, 0)), calib) is False


def test_is_agent_selection_menu_true_on_teal_sig_bbox():
    calib = _identity_calib()
    assert _is_agent_selection_menu(_make_agent_menu_frame(), calib) is True


def test_is_agent_selection_menu_false_on_dark_frame():
    calib = _identity_calib()
    assert _is_agent_selection_menu(Image.new("RGB", (1920, 1080), (0, 0, 0)), calib) is False


def test_is_main_menu_false_on_agent_menu_frame():
    """Agent-menu frame should NOT trigger main-menu predicate."""
    calib = _identity_calib()
    assert _is_main_menu(_make_agent_menu_frame(), calib) is False


# ── H7c: auto-nav driver integration ─────────────────────────────────────────

def test_auto_nav_driver_walks_full_transition_graph(tmp_path):
    """H7c: auto-nav calls the driver in the correct sequence; input() never called."""
    args  = _make_auto_nav_args(tmp_path)
    calib = _identity_calib()
    disc  = _sample_disc()
    engine = _sample_engine()
    agent  = _sample_agent()

    driver_calls: list[str] = []

    class _FakeDriver:
        def __init__(self, _calib, _capture_fn, *, archive_dir=None):
            pass
        def navigate_to_storage(self):
            driver_calls.append("navigate_to_storage")
            return _fake_frame()
        def switch_storage_tab(self, idx: int, **kwargs):
            driver_calls.append(f"switch_storage_tab({idx})")
            return _fake_frame()
        def return_to_main(self):
            driver_calls.append("return_to_main")
            return _fake_frame()
        def navigate_to_agents(self):
            driver_calls.append("navigate_to_agents")
            return _fake_frame()

    with patch("youkai_ocr.capture.calibrate_window", return_value=(calib, MagicMock())), \
         patch("youkai_ocr.disc_scanner.scan_discs",    return_value=([disc],   [])), \
         patch("youkai_ocr.wengine_scanner.scan_engines", return_value=([engine], [])), \
         patch("youkai_ocr.agent_scanner.scan_agents",  return_value=([agent],  [], [], [])), \
         patch("youkai_ocr.cli._is_main_menu",          return_value=True), \
         patch("youkai_ocr.cli._NavDriver",              _FakeDriver), \
         patch("builtins.input") as mock_input:
        _cmd_scan_all(args)

    # Full transition sequence: Storage → engine tab → disc tab → main → Agents
    assert driver_calls == [
        "navigate_to_storage",
        "switch_storage_tab(0)",
        "switch_storage_tab(1)",
        "return_to_main",
        "navigate_to_agents",
    ], f"unexpected driver call sequence: {driver_calls}"

    # No manual gates
    mock_input.assert_not_called()

    # All three phases completed and written
    run_dir = _find_run_dir(args.archive_dir)
    results = json.loads((run_dir / "results.json").read_text())
    assert results["summary"]["discs"]   == 1
    assert results["summary"]["engines"] == 1
    assert results["summary"]["agents"]  == 1


def test_auto_nav_raises_if_not_on_main_menu(tmp_path):
    """auto-nav aborts if the initial capture is not the main-menu hub."""
    args  = _make_auto_nav_args(tmp_path)
    calib = _identity_calib()
    dark  = Image.new("RGB", (1920, 1080), (0, 0, 0))

    with patch("youkai_ocr.capture.calibrate_window", return_value=(calib, lambda: dark)), \
         pytest.raises(ScreenAssertError, match="not on the Inter-Knot main-menu hub"):
        _cmd_scan_all(args)


def test_auto_nav_agents_only_skips_storage(tmp_path):
    """--agents-only in auto-nav goes straight from main menu to Agents, no storage visit."""
    args = _make_auto_nav_args(tmp_path)
    args.agents_only = True
    calib  = _identity_calib()
    agent  = _sample_agent()

    driver_calls: list[str] = []

    class _FakeDriver:
        def __init__(self, _calib, _capture_fn, *, archive_dir=None):
            pass
        def navigate_to_storage(self):
            driver_calls.append("navigate_to_storage")
            return _fake_frame()
        def switch_storage_tab(self, idx: int, **kwargs):
            driver_calls.append(f"switch_storage_tab({idx})")
            return _fake_frame()
        def return_to_main(self):
            driver_calls.append("return_to_main")
            return _fake_frame()
        def navigate_to_agents(self):
            driver_calls.append("navigate_to_agents")
            return _fake_frame()

    with patch("youkai_ocr.capture.calibrate_window", return_value=(calib, MagicMock())), \
         patch("youkai_ocr.agent_scanner.scan_agents",  return_value=([agent], [], [], [])), \
         patch("youkai_ocr.cli._is_main_menu",          return_value=True), \
         patch("youkai_ocr.cli._NavDriver",              _FakeDriver), \
         patch("builtins.input"):
        _cmd_scan_all(args)

    assert "navigate_to_storage" not in driver_calls
    assert "switch_storage_tab(0)" not in driver_calls
    assert "switch_storage_tab(1)" not in driver_calls
    assert "return_to_main" not in driver_calls
    assert "navigate_to_agents" in driver_calls


# ── T1: select_phases unit tests ─────────────────────────────────────────────

def _pa(**kwargs) -> SimpleNamespace:
    return SimpleNamespace(**kwargs)


def test_select_phases_default_all():
    assert select_phases(_pa()) == frozenset({"engines", "discs", "agents"})


def test_select_phases_discs_only():
    assert select_phases(_pa(phases="discs")) == frozenset({"discs"})


def test_select_phases_multiple():
    assert select_phases(_pa(phases="engines,agents")) == frozenset({"engines", "agents"})


def test_select_phases_agents_only_alias():
    assert select_phases(_pa(agents_only=True)) == frozenset({"agents"})


def test_select_phases_agents_only_overrides_phases():
    assert select_phases(_pa(agents_only=True, phases="discs")) == frozenset({"agents"})


def test_select_phases_unknown_name():
    with pytest.raises(ValueError, match="Unknown phase"):
        select_phases(_pa(phases="discs,weapons"))


def test_select_phases_empty():
    with pytest.raises(ValueError, match="must not be empty"):
        select_phases(_pa(phases="  ,  "))


def test_scan_all_phases_discs_only_skips_engine_and_agent(tmp_path):
    """--phases discs runs only the disc phase; engines and agents report skipped."""
    args = SimpleNamespace(
        output=str(tmp_path / "out.json"),
        archive_dir=str(tmp_path / "base"),
        engine="tesseract",
        resume=None,
        manual_nav=True,
        phases="discs",
    )
    calib = _identity_calib()
    disc = _sample_disc()

    with patch("youkai_ocr.capture.calibrate_window", return_value=(calib, MagicMock())), \
         patch("youkai_ocr.disc_scanner.scan_discs", return_value=([disc], [])), \
         patch("youkai_ocr.wengine_scanner.scan_engines") as mock_engines, \
         patch("youkai_ocr.agent_scanner.scan_agents") as mock_agents, \
         patch("youkai_ocr.cli._preflight_frame", return_value=_fake_frame()), \
         patch("youkai_ocr.cli._countdown"), \
         patch("youkai_ocr.cli._check_disc_screen"), \
         patch("builtins.input", return_value=""):
        _cmd_scan_all(args)

    mock_engines.assert_not_called()
    mock_agents.assert_not_called()

    run_dir = _find_run_dir(args.archive_dir)
    results = json.loads((run_dir / "results.json").read_text())
    assert results["phases"]["discs"]["count"] == 1
    assert results["phases"]["engines"].get("skipped") is True
    assert results["phases"]["agents"].get("skipped") is True
    assert results["phases"]["engines"]["count"] == 0
    assert results["phases"]["agents"]["count"] == 0


# ── T3.1: Roster coverage check ──────────────────────────────────────────────

def _make_owned_cells(n: int) -> list[tuple[int, int]]:
    """Return n dummy (x, y) owned-cell tuples for mocking detect_owned_agent_cells."""
    return [(100 + i * 10, 200) for i in range(n)]


def test_coverage_no_warning_when_counts_match(tmp_path, capsys):
    """No coverage warning when scanned agents == grid visible count."""
    args = _make_args(tmp_path)
    calib = _identity_calib()
    agent = _sample_agent()

    with patch("youkai_ocr.capture.calibrate_window", return_value=(calib, MagicMock())), \
         patch("youkai_ocr.disc_scanner.scan_discs",       return_value=([], [])), \
         patch("youkai_ocr.wengine_scanner.scan_engines",  return_value=([], [])), \
         patch("youkai_ocr.agent_scanner.scan_agents",     return_value=([agent], [], [], [])), \
         patch("youkai_ocr.agent_scanner.detect_owned_agent_cells", return_value=_make_owned_cells(1)), \
         patch("youkai_ocr.cli._preflight_frame",          return_value=_fake_frame()), \
         patch("youkai_ocr.cli._countdown"), \
         patch("youkai_ocr.cli._check_disc_screen"), \
         patch("youkai_ocr.cli._check_engine_screen"), \
         patch("youkai_ocr.cli._check_agent_screen"), \
         patch("builtins.input", return_value=""):
        _cmd_scan_all(args)

    out = capsys.readouterr().out
    assert "WARNING: roster coverage" not in out

    run_dir = _find_run_dir(args.archive_dir)
    results = json.loads((run_dir / "results.json").read_text())
    assert "coverage" in results
    assert results["coverage"]["warning"] is False
    assert results["coverage"]["agents_scanned"] == 1
    assert results["coverage"]["roster_grid_visible"] == 1
    assert results["coverage"]["gap"] == 0


def test_coverage_warning_when_fewer_agents_scanned(tmp_path, capsys):
    """Warning emitted and gap recorded when scanned count < grid visible count."""
    args = _make_args(tmp_path)
    calib = _identity_calib()
    agent = _sample_agent()

    with patch("youkai_ocr.capture.calibrate_window", return_value=(calib, MagicMock())), \
         patch("youkai_ocr.disc_scanner.scan_discs",       return_value=([], [])), \
         patch("youkai_ocr.wengine_scanner.scan_engines",  return_value=([], [])), \
         patch("youkai_ocr.agent_scanner.scan_agents",     return_value=([agent], [], [], [])), \
         patch("youkai_ocr.agent_scanner.detect_owned_agent_cells", return_value=_make_owned_cells(3)), \
         patch("youkai_ocr.cli._preflight_frame",          return_value=_fake_frame()), \
         patch("youkai_ocr.cli._countdown"), \
         patch("youkai_ocr.cli._check_disc_screen"), \
         patch("youkai_ocr.cli._check_engine_screen"), \
         patch("youkai_ocr.cli._check_agent_screen"), \
         patch("builtins.input", return_value=""):
        _cmd_scan_all(args)

    out = capsys.readouterr().out
    assert "WARNING: roster coverage" in out
    assert "3 owned" in out

    run_dir = _find_run_dir(args.archive_dir)
    results = json.loads((run_dir / "results.json").read_text())
    assert results["coverage"]["warning"] is True
    assert results["coverage"]["gap"] == 2
    assert results["coverage"]["roster_grid_visible"] == 3
    assert results["coverage"]["agents_scanned"] == 1
    assert "Zhao" in results["coverage"]["scanned_keys"]


def test_coverage_skipped_when_agents_phase_skipped(tmp_path):
    """No coverage key in results.json when --phases discs (agents skipped)."""
    args = SimpleNamespace(
        output=str(tmp_path / "out.json"),
        archive_dir=str(tmp_path / "base"),
        engine="tesseract",
        resume=None,
        manual_nav=True,
        phases="discs",
    )
    calib = _identity_calib()
    disc = _sample_disc()

    with patch("youkai_ocr.capture.calibrate_window", return_value=(calib, MagicMock())), \
         patch("youkai_ocr.disc_scanner.scan_discs",    return_value=([disc], [])), \
         patch("youkai_ocr.wengine_scanner.scan_engines") as mock_eng, \
         patch("youkai_ocr.agent_scanner.scan_agents")  as mock_agt, \
         patch("youkai_ocr.cli._preflight_frame",       return_value=_fake_frame()), \
         patch("youkai_ocr.cli._countdown"), \
         patch("youkai_ocr.cli._check_disc_screen"), \
         patch("builtins.input", return_value=""):
        _cmd_scan_all(args)

    run_dir = _find_run_dir(args.archive_dir)
    results = json.loads((run_dir / "results.json").read_text())
    assert "coverage" not in results
    mock_agt.assert_not_called()


# ── Porcelain mode tests ──────────────────────────────────────────────────────

def _make_porcelain_args(tmp_path: Path, phases: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        output=str(tmp_path / "export" / "out.json"),
        archive_dir=str(tmp_path / "base"),
        engine="tesseract",
        resume=None,
        manual_nav=True,
        phases=phases,
        agents_only=False,
        debug_overlays=False,
        porcelain=True,
    )


def _run_porcelain(tmp_path: Path, args) -> list[dict]:
    """Run _cmd_scan_all in porcelain mode; return parsed JSONL lines from stdout."""
    calib = _identity_calib()
    buf = io.StringIO()

    with patch("youkai_ocr.capture.calibrate_window", return_value=(calib, MagicMock())), \
         patch("youkai_ocr.disc_scanner.scan_discs", return_value=([_sample_disc()], [])), \
         patch("youkai_ocr.wengine_scanner.scan_engines", return_value=([_sample_engine()], [])), \
         patch("youkai_ocr.agent_scanner.scan_agents", return_value=([_sample_agent()], [], [], [])), \
         patch("youkai_ocr.cli._preflight_frame", return_value=_fake_frame()), \
         patch("youkai_ocr.cli._countdown"), \
         patch("youkai_ocr.cli._check_disc_screen"), \
         patch("youkai_ocr.cli._check_engine_screen"), \
         patch("youkai_ocr.cli._check_agent_screen"), \
         patch("builtins.input", return_value=""), \
         patch("sys.stdout", buf):
        _cmd_scan_all(args)

    buf.seek(0)
    return [json.loads(line) for line in buf if line.strip()]


def test_porcelain_stdout_is_pure_jsonl(tmp_path):
    """In --porcelain mode every stdout line must be valid JSON with an 'event' key."""
    args = _make_porcelain_args(tmp_path)
    rows = _run_porcelain(tmp_path, args)
    assert len(rows) > 0
    for row in rows:
        assert "event" in row, f"line missing 'event': {row}"
    terminal = [r for r in rows if r["event"] in ("done", "error")]
    assert len(terminal) == 1, f"expected exactly one terminal event, got: {[r['event'] for r in rows]}"
    assert terminal[0]["event"] == "done"


def test_porcelain_phase_sequence_discs_only(tmp_path):
    """--phases discs emits run_start → phase_start×3 → phase_done×3 → done."""
    args = _make_porcelain_args(tmp_path, phases="discs")
    rows = _run_porcelain(tmp_path, args)

    events = [r["event"] for r in rows]
    assert events[0] == "run_start"
    assert events[-1] == "done"

    # run_start lists only the active phase
    assert rows[0]["phases"] == ["discs"]

    phase_starts = [r for r in rows if r["event"] == "phase_start"]
    phase_dones  = [r for r in rows if r["event"] == "phase_done"]
    assert len(phase_starts) == 3
    assert len(phase_dones)  == 3
    assert {r["phase"] for r in phase_starts} == {"engines", "discs", "agents"}

    # discs phase_done has count=1 (one sample disc); engines and agents are skipped (count=0)
    by_phase = {r["phase"]: r for r in phase_dones}
    assert by_phase["discs"]["count"] == 1
    assert by_phase["engines"]["count"] == 0
    assert by_phase["agents"]["count"] == 0

    # done event carries the summary
    done = rows[-1]
    assert done["summary"]["discs"] == 1
    assert done["summary"]["engines"] == 0
    assert done["summary"]["agents"] == 0


def test_porcelain_error_event_on_screen_assert_error(tmp_path):
    """ScreenAssertError inside _cmd_scan_all emits an error event then re-raises."""
    args = _make_porcelain_args(tmp_path)
    buf = io.StringIO()

    def _raise(*a, **k):
        from youkai_ocr.cli import ScreenAssertError
        raise ScreenAssertError("wrong screen")

    with patch("youkai_ocr.capture.calibrate_window", side_effect=_raise), \
         patch("sys.stdout", buf):
        with pytest.raises(Exception, match="wrong screen"):
            _cmd_scan_all(args)

    buf.seek(0)
    rows = [json.loads(line) for line in buf if line.strip()]
    error_events = [r for r in rows if r["event"] == "error"]
    assert len(error_events) == 1
    assert "wrong screen" in error_events[0]["message"]


# ── T4: non-interactive policy under porcelain ───────────────────────────────

class _FakeEmitter:
    """Minimal emitter that records warning events."""
    def __init__(self):
        self.warnings: list[str] = []

    def warning(self, message: str) -> None:
        self.warnings.append(message)


def _dark_frame(brightness: int = 8) -> Image.Image:
    """1920×1080 frame with mean brightness ~brightness (dark but not black)."""
    return Image.new("RGB", (1920, 1080), color=(brightness, brightness, brightness))


def test_preflight_frame_dark_noninteractive_emits_warning_and_continues(tmp_path):
    """In non-interactive mode a dark (but non-black) frame emits a warning and returns."""
    emitter = _FakeEmitter()
    calib   = _identity_calib()
    frame   = _dark_frame(brightness=10)  # mean ≈ 10; 5 < 10 < 15 → dark branch

    def _capture():
        return frame

    with patch("youkai_ocr.capture.check_color_hygiene"):
        result = _preflight_frame(
            _capture, calib, archive_dir=None, phase="discs",
            interactive=False, emitter=emitter,
        )

    assert result is frame
    assert len(emitter.warnings) == 1
    assert "dark" in emitter.warnings[0].lower() or "obscured" in emitter.warnings[0].lower()


def test_preflight_frame_dark_interactive_calls_input():
    """In interactive mode a dark frame calls input(); monkeypatching it to raise proves the call."""
    calib = _identity_calib()
    frame = _dark_frame(brightness=10)

    def _capture():
        return frame

    with patch("youkai_ocr.capture.check_color_hygiene"), \
         patch("builtins.input", side_effect=AssertionError("input must not be called in porcelain")):
        with pytest.raises(AssertionError, match="input must not be called"):
            _preflight_frame(_capture, calib, archive_dir=None, phase="discs",
                             interactive=True, emitter=None)


def test_preflight_frame_dark_noninteractive_does_not_call_input():
    """In non-interactive mode, builtins.input must never be called even in the dark-frame branch."""
    calib = _identity_calib()
    frame = _dark_frame(brightness=10)
    emitter = _FakeEmitter()

    def _capture():
        return frame

    with patch("youkai_ocr.capture.check_color_hygiene"), \
         patch("builtins.input", side_effect=AssertionError("input called in porcelain mode")):
        result = _preflight_frame(
            _capture, calib, archive_dir=None, phase="discs",
            interactive=False, emitter=emitter,
        )

    assert result is frame  # continued without exception


def test_preflight_frame_black_raises_regardless_of_interactive():
    """A nearly-black frame (brightness < 5) is a hard abort regardless of interactive flag."""
    calib   = _identity_calib()
    black   = Image.new("RGB", (1920, 1080), color=(0, 0, 0))
    emitter = _FakeEmitter()

    def _capture():
        return black

    with patch("youkai_ocr.capture.check_color_hygiene"):
        with pytest.raises(RuntimeError, match="nearly black"):
            _preflight_frame(_capture, calib, archive_dir=None, phase="discs",
                             interactive=False, emitter=emitter)

    assert len(emitter.warnings) == 0  # hard abort, no warning emitted


def test_make_first_item_check_low_conf_noninteractive_emits_warning():
    """Low-confidence first item in non-interactive mode emits a warning and continues.

    Use conf where mean ≥ 25 (avoids total-fail branch) but ≥ half fields < 30.
    """
    emitter = _FakeEmitter()
    check   = _make_first_item_check("disc", interactive=False, emitter=emitter)

    # mean = (26+27+26+27)/4 = 26.5 ≥ 25; all 4 fields < 30 → len(low_fields)==4 ≥ 4//2==2
    item = object()
    conf = {"set": 26.0, "slot": 27.0, "level": 26.0, "main_stat": 27.0}

    with patch("builtins.input", side_effect=AssertionError("input called in porcelain")):
        check(item, conf)  # must not raise

    assert len(emitter.warnings) == 1
    assert "low confidence" in emitter.warnings[0].lower() or "disc" in emitter.warnings[0].lower()


def test_make_first_item_check_low_conf_interactive_calls_input():
    """Low-confidence first item in interactive mode calls input(); raise proves the call."""
    check = _make_first_item_check("disc", interactive=True, emitter=None)
    item  = object()
    # same conf as above: mean 26.5 ≥ 25, all fields < 30
    conf  = {"set": 26.0, "slot": 27.0, "level": 26.0, "main_stat": 27.0}

    with patch("builtins.input", side_effect=AssertionError("input called")):
        with pytest.raises(AssertionError, match="input called"):
            check(item, conf)


def test_make_first_item_check_total_fail_raises_regardless_of_interactive():
    """A total OCR failure (mean conf < 25) is a hard abort regardless of interactive."""
    emitter = _FakeEmitter()
    check   = _make_first_item_check("disc", interactive=False, emitter=emitter)
    item    = object()
    conf    = {"set": 10.0, "slot": 8.0}  # mean 9, < 25

    with pytest.raises(RuntimeError, match="completely failed OCR"):
        check(item, conf)


def _make_porcelain_scan_all_args(tmp_path: Path, manual_nav: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        output=str(tmp_path / "out.json"),
        archive_dir=str(tmp_path / "base"),
        engine="tesseract",
        resume=None,
        manual_nav=manual_nav,
        phases=None,
        agents_only=False,
        debug_overlays=False,
        porcelain=True,
    )


def test_scan_all_porcelain_manual_nav_no_input_calls(tmp_path):
    """With --porcelain + --manual-nav, the navigation input() gates are skipped."""
    args   = _make_porcelain_scan_all_args(tmp_path, manual_nav=True)
    calib  = _identity_calib()
    buf    = io.StringIO()

    with patch("youkai_ocr.capture.calibrate_window", return_value=(calib, MagicMock())), \
         patch("youkai_ocr.disc_scanner.scan_discs", return_value=([_sample_disc()], [])), \
         patch("youkai_ocr.wengine_scanner.scan_engines", return_value=([_sample_engine()], [])), \
         patch("youkai_ocr.agent_scanner.scan_agents", return_value=([_sample_agent()], [], [], [])), \
         patch("youkai_ocr.cli._preflight_frame", return_value=_fake_frame()), \
         patch("youkai_ocr.cli._countdown"), \
         patch("youkai_ocr.cli._check_disc_screen"), \
         patch("youkai_ocr.cli._check_engine_screen"), \
         patch("youkai_ocr.cli._check_agent_screen"), \
         patch("builtins.input", side_effect=AssertionError("input called in porcelain")), \
         patch("sys.stdout", buf):
        _cmd_scan_all(args)  # must not raise AssertionError

    buf.seek(0)
    rows = [json.loads(line) for line in buf if line.strip()]
    terminal = [r for r in rows if r["event"] in ("done", "error")]
    assert len(terminal) == 1
    assert terminal[0]["event"] == "done"


# ── --version flag ────────────────────────────────────────────────────────────

def test_version_flag_prints_package_version(capsys):
    import youkai_ocr
    import argparse
    from youkai_ocr.cli import main as cli_main

    with pytest.raises(SystemExit) as exc_info:
        with patch("sys.argv", ["youkai-ocr", "--version"]):
            cli_main()

    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert youkai_ocr.__version__ in out


# ── T1.5: _reconcile_locations unit tests ────────────────────────────────────

def _disc(set_key, slot_key, main, level=15, rarity=4, location="", substats=None) -> ZodDisc:
    return ZodDisc(
        set_key=set_key, slot_key=slot_key, level=level, rarity=rarity,
        main_stat_key=main, location=location, lock=False,
        substats=substats or [],
    )


def _engine(key, level=60, location="") -> ZodWEngine:
    return ZodWEngine(key=key, level=level, ascension=5, refinement=1, location=location, lock=False)


def test_reconcile_exact_match_stamps_location():
    inv = [_disc("ChaoticMetal", "4", "ATK")]
    eq  = [_disc("ChaoticMetal", "4", "ATK", location="Zhu Yuan")]
    orphans = _reconcile_locations(eq, [], inv, [])
    assert inv[0].location == "Zhu Yuan"
    assert len(orphans) == 0
    assert len(inv) == 1  # no append


def test_reconcile_no_match_appends_disc():
    inv = [_disc("ShockstarDisc", "1", "HP")]
    eq  = [_disc("ChaoticMetal", "4", "ATK", location="Zhu Yuan")]
    orphans = _reconcile_locations(eq, [], inv, [])
    assert len(inv) == 2
    assert inv[1].location == "Zhu Yuan"
    assert orphans[0]["status"] == "orphan"
    assert orphans[0]["type"] == "disc"


def test_reconcile_one_to_one_no_double_assign():
    """Two equipped discs from different agents must not both match the same inventory disc."""
    inv = [_disc("ChaoticMetal", "4", "ATK")]
    eq1 = _disc("ChaoticMetal", "4", "ATK", location="Agent1")
    eq2 = _disc("ChaoticMetal", "4", "ATK", location="Agent2")
    orphans = _reconcile_locations([eq1, eq2], [], inv, [])
    # First match stamps; second must append (not overwrite)
    assert inv[0].location in ("Agent1", "Agent2")
    assert len(inv) == 2
    assert len(orphans) == 1


def test_reconcile_engine_match_stamps_location():
    inv_e = [_engine("StarlightEngine", level=60)]
    eq_e  = [_engine("StarlightEngine", level=60, location="Nicole")]
    orphans = _reconcile_locations([], [eq_e[0]], [], inv_e)
    assert inv_e[0].location == "Nicole"
    assert len(orphans) == 0
    assert len(inv_e) == 1


def test_reconcile_engine_no_match_appends():
    inv_e = [_engine("StarlightEngine")]
    eq_e  = [_engine("MissingEngine", location="Nicole")]
    orphans = _reconcile_locations([], [eq_e[0]], [], inv_e)
    assert len(inv_e) == 2
    assert inv_e[1].location == "Nicole"
    assert orphans[0]["type"] == "engine"


def test_reconcile_backfills_empty_substat_key():
    inv = [_disc("ChaoticMetal", "4", "ATK", substats=[ZodSubstat(key="", value=10.0)])]
    eq  = [_disc("ChaoticMetal", "4", "ATK", location="Agent1",
                 substats=[ZodSubstat(key="CRIT Rate", value=10.0)])]
    _reconcile_locations(eq, [], inv, [])
    assert inv[0].substats[0].key == "CRIT Rate"


def test_reconcile_widens_to_set_slot_on_main_mismatch():
    """If main_stat_key mismatches, fall back to set+slot match."""
    inv = [_disc("ChaoticMetal", "4", "ATK%")]
    eq  = [_disc("ChaoticMetal", "4", "ATK", location="Agent1")]  # "ATK" vs "ATK%"
    orphans = _reconcile_locations(eq, [], inv, [])
    assert inv[0].location == "Agent1"
    assert len(orphans) == 0
