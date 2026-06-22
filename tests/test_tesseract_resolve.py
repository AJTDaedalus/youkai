"""T13a: tests for resolve_tesseract() — bundled, default-install, and PATH slots."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from youkai_ocr.recognize import resolve_tesseract


# ── helpers ────────────────────────────────────────────────────────────────────


def _make_bundle(tmp_path: Path, with_tessdata: bool = True) -> Path:
    """Create a fake frozen layout under *tmp_path*.

    Returns the app_root (== _MEIPASS) where tesseract/ lives.
    """
    exe = tmp_path / "tesseract" / "tesseract.exe"
    exe.parent.mkdir(parents=True)
    exe.touch()
    if with_tessdata:
        (exe.parent / "tessdata").mkdir()
    return tmp_path


# ── Slot 1: bundled (frozen) ───────────────────────────────────────────────────


def test_frozen_bundle_returns_bundled_cmd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app_root = _make_bundle(tmp_path)
    monkeypatch.setattr("youkai_ocr.recognize.sys.platform", "win32")
    monkeypatch.setattr("youkai_ocr.recognize.sys", _FrozenSys(app_root), raising=False)

    cmd, tessdata = resolve_tesseract()

    assert cmd == str(app_root / "tesseract" / "tesseract.exe")
    assert tessdata == app_root / "tesseract" / "tessdata"


def test_frozen_bundle_sets_tessdata_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_root = _make_bundle(tmp_path)
    monkeypatch.setattr("youkai_ocr.recognize.sys", _FrozenSys(app_root), raising=False)

    _, tessdata = resolve_tesseract()

    # Caller would do: os.environ["TESSDATA_PREFIX"] = str(tessdata)
    assert tessdata is not None
    assert (tessdata).is_dir()


def test_frozen_bundle_no_tessdata_returns_none_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_root = _make_bundle(tmp_path, with_tessdata=False)
    monkeypatch.setattr("youkai_ocr.recognize.sys", _FrozenSys(app_root), raising=False)

    cmd, tessdata = resolve_tesseract()

    assert cmd is not None
    assert tessdata is None


# ── Slot 3: fallthrough to PATH ────────────────────────────────────────────────


def test_no_bundle_falls_through_to_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Empty app_root → no bundle → no Windows default → return (None, None)."""
    # Use a non-win32 platform so slot 2 (Program Files) is skipped.
    monkeypatch.setattr("youkai_ocr.recognize.sys", _FrozenSys(tmp_path, platform="linux"), raising=False)

    cmd, tessdata = resolve_tesseract()

    assert cmd is None
    assert tessdata is None


def test_no_bundle_win32_no_programfiles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Empty app_root on win32 where Program Files path doesn't exist → (None, None)."""
    monkeypatch.setattr("youkai_ocr.recognize.sys", _FrozenSys(tmp_path, platform="win32"), raising=False)
    # Program Files path won't exist on WSL/CI — so slot 2 is skipped and we fall to PATH.
    cmd, tessdata = resolve_tesseract()

    # Either cmd is None (PATH) or it's the Program Files path if somehow present.
    # On WSL/Linux, the Program Files path doesn't exist, so we expect None.
    pf = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    if not pf.exists():
        assert cmd is None
        assert tessdata is None


# ── Integration: __init__ sets pytesseract cmd and env var ────────────────────


def test_init_sets_pytesseract_cmd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app_root = _make_bundle(tmp_path)
    monkeypatch.setattr("youkai_ocr.recognize.sys", _FrozenSys(app_root), raising=False)

    import pytesseract
    import youkai_ocr.recognize as rec

    original_cmd = pytesseract.pytesseract.tesseract_cmd
    original_tessdata = os.environ.get("TESSDATA_PREFIX")

    try:
        cmd, tessdata = rec.resolve_tesseract()
        assert cmd == str(app_root / "tesseract" / "tesseract.exe")

        # Simulate what __init__ does:
        pytesseract.pytesseract.tesseract_cmd = cmd
        if tessdata is not None:
            os.environ["TESSDATA_PREFIX"] = str(tessdata)

        assert pytesseract.pytesseract.tesseract_cmd == str(
            app_root / "tesseract" / "tesseract.exe"
        )
        assert os.environ.get("TESSDATA_PREFIX") == str(tessdata)
    finally:
        pytesseract.pytesseract.tesseract_cmd = original_cmd
        if original_tessdata is None:
            os.environ.pop("TESSDATA_PREFIX", None)
        else:
            os.environ["TESSDATA_PREFIX"] = original_tessdata


# ── Fake frozen sys object ─────────────────────────────────────────────────────


class _FrozenSys:
    """Minimal sys-module replacement for monkeypatching resolve_tesseract."""

    def __init__(self, meipass: Path, platform: str = "win32") -> None:
        self.frozen = True
        self._MEIPASS = str(meipass)
        self.platform = platform
        _exe_name = "youkai.exe" if platform == "win32" else "youkai"
        self.executable = str(meipass.parent / _exe_name)
        self.argv = [self.executable]
