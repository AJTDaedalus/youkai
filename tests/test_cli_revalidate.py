"""Tests for the `revalidate` CLI subcommand (T10).

`revalidate` replays an archived disc scan (disc_NNNN/panel.png crops +
discs.json) offline through the current validator/repair tables — no game,
no pynput. `scan_single_frame` is mocked throughout so these tests are fast
and deterministic; real-OCR-over-golden-panels coverage of the repair
pipeline itself already lives in test_disc_scanner.py / test_golden_replay.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from youkai_ocr.cli import _cmd_revalidate
from youkai_ocr.disc_rules import Violation
from youkai_ocr.zod import ZodDisc, ZodSubstat


def _raw_disc(location: str = "", lock: bool = False) -> dict:
    return {
        "setKey": "SwingJazz",
        "slotKey": "1",
        "level": 15,
        "rarity": 4,
        "mainStatKey": "hp",
        "location": location,
        "lock": lock,
        "substats": [{"key": "def_", "value": 4.8}],
    }


def _make_archive(tmp_path: Path, raw_discs: list[dict]) -> Path:
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / "discs.json").write_text(json.dumps(raw_discs), encoding="utf-8")
    for i in range(len(raw_discs)):
        cell_dir = archive / f"disc_{i:04d}"
        cell_dir.mkdir()
        Image.new("RGB", (439, 770), color=(50, 50, 50)).save(cell_dir / "panel.png")
    return archive


def _sample_disc(location: str = "", lock: bool = False) -> ZodDisc:
    return ZodDisc(
        set_key="SwingJazz",
        slot_key="1",
        level=15,
        rarity=4,
        main_stat_key="hp",
        location=location,
        lock=lock,
        substats=[ZodSubstat(key="def_", value=4.8)],
    )


def _args(archive: Path, out: Path, report: Path | None = None, limit: int | None = None):
    return SimpleNamespace(
        archive=str(archive),
        out=str(out),
        report=str(report) if report else None,
        engine="tesseract",
        limit=limit,
    )


# ── Location/lock merge ──────────────────────────────────────────────────────


def test_revalidate_merges_location_lock_from_discs_json(tmp_path):
    raw = [_raw_disc(location="BelleTest", lock=True)]
    archive = _make_archive(tmp_path, raw)
    out = tmp_path / "export.json"

    # scan_single_frame doesn't know about location/lock (panel crops don't
    # show them) — returns the disc with defaults, as the real function does.
    # validate_disc patched clean: T13 would otherwise exclude the minimal
    # sample disc (its single substat can't satisfy the real roll budget).
    with (
        patch(
            "youkai_ocr.disc_scanner.scan_single_frame",
            return_value=(_sample_disc(location="", lock=False), {}),
        ),
        patch("youkai_ocr.disc_rules.validate_disc", return_value=[]),
    ):
        _cmd_revalidate(_args(archive, out))

    data = json.loads(out.read_text())
    assert data["discs"][0]["location"] == "BelleTest"
    assert data["discs"][0]["lock"] is True


# ── Summary counts / status classification ───────────────────────────────────


def test_revalidate_counts_clean_disc_when_no_repairs_no_violations(tmp_path, capsys):
    raw = [_raw_disc()]
    archive = _make_archive(tmp_path, raw)
    out = tmp_path / "export.json"

    with (
        patch("youkai_ocr.disc_scanner.scan_single_frame", return_value=(_sample_disc(), {})),
        patch("youkai_ocr.disc_rules.validate_disc", return_value=[]),
    ):
        _cmd_revalidate(_args(archive, out))

    captured = capsys.readouterr()
    assert "clean: 1  repaired: 0  unrepairable: 0" in captured.out


def test_revalidate_counts_repaired_disc_from_conf_repairs(tmp_path, capsys):
    raw = [_raw_disc()]
    archive = _make_archive(tmp_path, raw)
    out = tmp_path / "export.json"
    report = tmp_path / "report.json"

    conf = {
        "_repairs": [{"field": "substat[0]", "before": 44.0, "after": 14.4, "rule": "roll_suffix"}]
    }
    with (
        patch("youkai_ocr.disc_scanner.scan_single_frame", return_value=(_sample_disc(), conf)),
        patch("youkai_ocr.disc_rules.validate_disc", return_value=[]),
    ):
        _cmd_revalidate(_args(archive, out, report=report))

    captured = capsys.readouterr()
    assert "clean: 0  repaired: 1  unrepairable: 0" in captured.out

    data = json.loads(report.read_text())
    assert data["summary"]["repaired"] == 1
    assert data["discs"][0]["repairs"][0]["rule"] == "roll_suffix"
    assert data["discs"][0]["status"] == "repaired"


def test_revalidate_excludes_unrepairable_disc_from_export(tmp_path, capsys):
    """T13: a disc with residual violations is EXCLUDED from the export; its
    values live only in the report (with the excluded_from_export marker) so
    the user can review and re-scan."""
    raw = [_raw_disc()]
    archive = _make_archive(tmp_path, raw)
    out = tmp_path / "export.json"
    report = tmp_path / "report.json"

    violation = Violation("substat[0]", "sub_not_on_lattice", 44.0, 4.8, "error")
    with (
        patch("youkai_ocr.disc_scanner.scan_single_frame", return_value=(_sample_disc(), {})),
        patch("youkai_ocr.disc_rules.validate_disc", return_value=[violation]),
    ):
        _cmd_revalidate(_args(archive, out, report=report))

    captured = capsys.readouterr()
    assert "clean: 0  repaired: 0  unrepairable: 1" in captured.out
    assert "1 disc(s) failed validation and were EXCLUDED" in captured.out

    data = json.loads(out.read_text())
    assert data["discs"] == []  # excluded from export

    rep = json.loads(report.read_text())
    entry = rep["discs"][0]
    assert entry["status"] == "unrepairable"
    assert entry["excluded_from_export"] is True
    assert entry["violations"][0]["code"] == "sub_not_on_lattice"
    assert entry["disc"]["setKey"] == "SwingJazz"  # reviewable payload
    assert rep["summary"]["exported"] == 0
    assert rep["summary"]["excluded"] == 1


def test_revalidate_passes_evidence_so_main_value_mismatch_is_excluded(tmp_path):
    """Regression: revalidate's export gate must run validate_disc WITH the
    conf-captured evidence. The main_value_mismatch check is evidence-only, so
    dropping evidence silently exports a main-key/level/rarity misread — the
    exact leak T13 exists to prevent. Assert validate_disc receives the
    reconstructed Evidence (main_value_raw from conf) and that a violation it
    only raises given that evidence excludes the disc from the export."""
    raw = [_raw_disc()]
    archive = _make_archive(tmp_path, raw)
    out = tmp_path / "export.json"

    # scan_single_frame carries the main-stat value it read as evidence in conf.
    conf = {"main_stat_value": 999.0}

    seen_evidence = []

    def _validate(disc, evidence=None):
        seen_evidence.append(evidence)
        # Mimic the real validator: main_value_mismatch fires ONLY when evidence
        # is supplied. If the fix regresses (evidence dropped), this returns []
        # and the disc leaks into the export → the assertions below fail.
        if evidence is not None and evidence.main_value_raw == 999.0:
            return [Violation("main_stat_value", "main_value_mismatch", 999.0, 2200.0, "error")]
        return []

    with (
        patch("youkai_ocr.disc_scanner.scan_single_frame", return_value=(_sample_disc(), conf)),
        patch("youkai_ocr.disc_rules.validate_disc", side_effect=_validate),
    ):
        _cmd_revalidate(_args(archive, out))

    # Evidence was reconstructed from conf and threaded into the gate.
    assert seen_evidence and seen_evidence[-1] is not None
    assert seen_evidence[-1].main_value_raw == 999.0
    # And the evidence-only violation actually excluded the disc.
    data = json.loads(out.read_text())
    assert data["discs"] == []


def test_revalidate_missing_panel_excluded_from_export_but_reported(tmp_path, capsys):
    raw = [_raw_disc(location="Corin", lock=True)]
    archive = _make_archive(tmp_path, raw)
    # Delete the panel to simulate a gap in the archive.
    (archive / "disc_0000" / "panel.png").unlink()
    out = tmp_path / "export.json"
    report = tmp_path / "report.json"

    _cmd_revalidate(_args(archive, out, report=report))

    captured = capsys.readouterr()
    assert "unrepairable: 1" in captured.out
    data = json.loads(out.read_text())
    assert data["discs"] == []  # T13: unverifiable disc no longer passed through

    rep = json.loads(report.read_text())
    assert rep["discs"][0]["status"] == "missing_panel"
    assert rep["discs"][0]["excluded_from_export"] is True
    assert rep["discs"][0]["disc"]["location"] == "Corin"


def test_revalidate_critical_fail_excluded_from_export_but_reported(tmp_path):
    raw = [_raw_disc(location="Anby", lock=False)]
    archive = _make_archive(tmp_path, raw)
    out = tmp_path / "export.json"
    report = tmp_path / "report.json"

    with patch(
        "youkai_ocr.disc_scanner.scan_single_frame",
        return_value=(None, {"_fail_reason": "unknown_set:10:title='???'"}),
    ):
        _cmd_revalidate(_args(archive, out, report=report))

    data = json.loads(out.read_text())
    assert data["discs"] == []  # T13: raw archived disc no longer passed through

    rep = json.loads(report.read_text())
    assert rep["discs"][0]["status"] == "critical_fail"
    assert rep["discs"][0]["excluded_from_export"] is True
    assert rep["discs"][0]["disc"]["setKey"] == "SwingJazz"
    assert rep["discs"][0]["disc"]["location"] == "Anby"


# ── Report file ───────────────────────────────────────────────────────────────


def test_revalidate_writes_report_with_summary_and_per_disc_entries(tmp_path):
    raw = [_raw_disc(), _raw_disc()]
    archive = _make_archive(tmp_path, raw)
    out = tmp_path / "export.json"
    report = tmp_path / "report.json"

    with patch("youkai_ocr.disc_scanner.scan_single_frame", return_value=(_sample_disc(), {})):
        _cmd_revalidate(_args(archive, out, report=report))

    data = json.loads(report.read_text())
    assert data["summary"]["total"] == 2
    assert len(data["discs"]) == 2
    assert data["discs"][0]["index"] == 0
    assert data["discs"][1]["index"] == 1


def test_revalidate_without_report_arg_writes_default_report(tmp_path):
    """T13: failed discs exist only in the report, so it is always written —
    defaulting to <out stem>.report.json next to the export."""
    raw = [_raw_disc()]
    archive = _make_archive(tmp_path, raw)
    out = tmp_path / "export.json"

    with patch("youkai_ocr.disc_scanner.scan_single_frame", return_value=(_sample_disc(), {})):
        _cmd_revalidate(_args(archive, out, report=None))

    default_report = tmp_path / "export.report.json"
    assert default_report.exists()
    data = json.loads(default_report.read_text())
    assert data["summary"]["total"] == 1


# ── --limit ───────────────────────────────────────────────────────────────────


def test_revalidate_limit_processes_only_first_n_discs(tmp_path, capsys):
    raw = [_raw_disc(), _raw_disc(), _raw_disc()]
    archive = _make_archive(tmp_path, raw)
    out = tmp_path / "export.json"

    with (
        patch(
            "youkai_ocr.disc_scanner.scan_single_frame", return_value=(_sample_disc(), {})
        ) as mock_scan,
        patch("youkai_ocr.disc_rules.validate_disc", return_value=[]),
    ):
        _cmd_revalidate(_args(archive, out, limit=1))

    assert mock_scan.call_count == 1
    data = json.loads(out.read_text())
    assert len(data["discs"]) == 1
