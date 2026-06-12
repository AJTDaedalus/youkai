"""JSONL progress emitter for --porcelain mode."""

import json
import time
from typing import Optional


class ProgressEmitter:
    def __init__(self, stream):
        self._stream = stream

    def _emit(self, payload: dict):
        self._stream.write(json.dumps(payload) + "\n")
        self._stream.flush()

    def run_start(self, *, run_dir: str, output: str, phases: list):
        self._emit({"event": "run_start", "v": 1, "run_dir": run_dir, "output": output, "phases": phases})

    def phase_start(self, *, phase: str, total=None):
        self._emit({"event": "phase_start", "phase": phase, "total": total})

    def progress(self, *, phase: str, scanned: int, total=None):
        self._emit({"event": "progress", "phase": phase, "scanned": scanned, "total": total})

    def phase_done(self, *, phase: str, count: int, issues: int, elapsed: float, resumed: bool = False):
        self._emit({"event": "phase_done", "phase": phase, "count": count, "issues": issues, "elapsed": elapsed, "resumed": resumed})

    def warning(self, *, message: str):
        self._emit({"event": "warning", "message": message})

    def done(self, *, output: str, run_dir: str, summary: dict, review_path: Optional[str] = None):
        payload = {"event": "done", "output": output, "run_dir": run_dir, "summary": summary}
        if review_path is not None:
            payload["review_path"] = review_path
        self._emit(payload)

    def error(self, *, message: str):
        self._emit({"event": "error", "message": message})


class NullEmitter:
    def run_start(self, **_): pass
    def phase_start(self, **_): pass
    def progress(self, **_): pass
    def phase_done(self, **_): pass
    def warning(self, **_): pass
    def done(self, **_): pass
    def error(self, **_): pass
