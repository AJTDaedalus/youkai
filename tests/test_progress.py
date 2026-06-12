"""Tests for ProgressEmitter and NullEmitter."""

import io
import json
import pytest

from youkai_ocr.progress import NullEmitter, ProgressEmitter


def _lines(buf: io.StringIO) -> list[dict]:
    buf.seek(0)
    return [json.loads(line) for line in buf if line.strip()]


def test_run_start():
    buf = io.StringIO()
    e = ProgressEmitter(buf)
    e.run_start(run_dir="/tmp/r", output="/tmp/out.json", phases=["discs", "agents"])
    rows = _lines(buf)
    assert len(rows) == 1
    r = rows[0]
    assert r["event"] == "run_start"
    assert r["v"] == 1
    assert r["run_dir"] == "/tmp/r"
    assert r["output"] == "/tmp/out.json"
    assert r["phases"] == ["discs", "agents"]


def test_phase_start_with_total():
    buf = io.StringIO()
    e = ProgressEmitter(buf)
    e.phase_start(phase="discs", total=12)
    r = _lines(buf)[0]
    assert r["event"] == "phase_start"
    assert r["phase"] == "discs"
    assert r["total"] == 12


def test_phase_start_null_total():
    buf = io.StringIO()
    e = ProgressEmitter(buf)
    e.phase_start(phase="agents")
    r = _lines(buf)[0]
    assert r["total"] is None


def test_progress():
    buf = io.StringIO()
    e = ProgressEmitter(buf)
    e.progress(phase="engines", scanned=3, total=10)
    r = _lines(buf)[0]
    assert r["event"] == "progress"
    assert r["phase"] == "engines"
    assert r["scanned"] == 3
    assert r["total"] == 10


def test_phase_done():
    buf = io.StringIO()
    e = ProgressEmitter(buf)
    e.phase_done(phase="discs", count=5, issues=1, elapsed=2.5)
    r = _lines(buf)[0]
    assert r["event"] == "phase_done"
    assert r["phase"] == "discs"
    assert r["count"] == 5
    assert r["issues"] == 1
    assert r["elapsed"] == pytest.approx(2.5)
    assert r["resumed"] is False


def test_phase_done_resumed():
    buf = io.StringIO()
    e = ProgressEmitter(buf)
    e.phase_done(phase="agents", count=3, issues=0, elapsed=1.0, resumed=True)
    r = _lines(buf)[0]
    assert r["resumed"] is True


def test_warning():
    buf = io.StringIO()
    e = ProgressEmitter(buf)
    e.warning(message="low confidence match")
    r = _lines(buf)[0]
    assert r["event"] == "warning"
    assert r["message"] == "low confidence match"


def test_done_without_review_path():
    buf = io.StringIO()
    e = ProgressEmitter(buf)
    summary = {"agents": 5, "discs": 30, "engines": 5, "issues": 2}
    e.done(output="/tmp/out.json", run_dir="/tmp/r", summary=summary)
    r = _lines(buf)[0]
    assert r["event"] == "done"
    assert r["output"] == "/tmp/out.json"
    assert r["run_dir"] == "/tmp/r"
    assert r["summary"] == summary
    assert "review_path" not in r


def test_done_with_review_path():
    buf = io.StringIO()
    e = ProgressEmitter(buf)
    e.done(output="/tmp/out.json", run_dir="/tmp/r", summary={}, review_path="/tmp/review.txt")
    r = _lines(buf)[0]
    assert r["review_path"] == "/tmp/review.txt"


def test_error():
    buf = io.StringIO()
    e = ProgressEmitter(buf)
    e.error(message="something went wrong")
    r = _lines(buf)[0]
    assert r["event"] == "error"
    assert r["message"] == "something went wrong"


def test_each_call_is_one_line():
    buf = io.StringIO()
    e = ProgressEmitter(buf)
    e.run_start(run_dir="/r", output="/o", phases=["discs"])
    e.phase_start(phase="discs", total=2)
    e.progress(phase="discs", scanned=1, total=2)
    e.phase_done(phase="discs", count=2, issues=0, elapsed=0.5)
    e.done(output="/o", run_dir="/r", summary={"agents": 0, "discs": 2, "engines": 0, "issues": 0})
    rows = _lines(buf)
    assert len(rows) == 5
    events = [r["event"] for r in rows]
    assert events == ["run_start", "phase_start", "progress", "phase_done", "done"]


def test_null_emitter_writes_nothing():
    buf = io.StringIO()
    # NullEmitter ignores its stream — but it must not raise
    e = NullEmitter()
    e.run_start(run_dir="/r", output="/o", phases=["discs"])
    e.phase_start(phase="discs", total=5)
    e.progress(phase="discs", scanned=1, total=5)
    e.phase_done(phase="discs", count=5, issues=0, elapsed=1.0)
    e.warning(message="heads up")
    e.done(output="/o", run_dir="/r", summary={})
    e.error(message="oops")
    assert buf.tell() == 0  # nothing written to our buf


def test_roundtrip_all_events():
    """Every emitted line must be valid JSON with an 'event' key."""
    buf = io.StringIO()
    e = ProgressEmitter(buf)
    e.run_start(run_dir="/r", output="/o", phases=["engines", "discs"])
    e.phase_start(phase="engines", total=None)
    e.progress(phase="engines", scanned=2, total=None)
    e.phase_done(phase="engines", count=2, issues=0, elapsed=0.1)
    e.warning(message="w")
    e.done(output="/o", run_dir="/r", summary={"agents": 0, "discs": 0, "engines": 2, "issues": 0})
    for line in buf.getvalue().splitlines():
        obj = json.loads(line)
        assert "event" in obj
