"""Unit tests for scripts/check_versions.py."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_versions.py"


def _run(*args: str, pyproject: str, init: str, cargo: str, tmp_path: Path):
    """Write three temporary version files and run check_versions.py against them."""
    # pyproject.toml (minimal)
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(f"""\
        [project]
        name = "youkai"
        version = "{pyproject}"
        """),
        encoding="utf-8",
    )
    # src/youkai_ocr/__init__.py
    src = tmp_path / "src" / "youkai_ocr"
    src.mkdir(parents=True, exist_ok=True)
    (src / "__init__.py").write_text(f'__version__ = "{init}"\n', encoding="utf-8")
    # youkai/Cargo.toml (minimal)
    youkai_dir = tmp_path / "youkai"
    youkai_dir.mkdir(exist_ok=True)
    (youkai_dir / "Cargo.toml").write_text(
        textwrap.dedent(f"""\
        [package]
        name = "youkai"
        version = "{cargo}"
        """),
        encoding="utf-8",
    )

    # Patch ROOT inside the script by running it with a modified sys.path approach:
    # We monkeypatch ROOT by writing a small wrapper that overrides ROOT.
    wrapper = tmp_path / "_run_check.py"
    wrapper.write_text(
        textwrap.dedent(f"""\
        import sys
        from pathlib import Path
        import importlib.util

        spec = importlib.util.spec_from_file_location("check_versions", {str(SCRIPT)!r})
        mod = importlib.util.module_from_spec(spec)
        # Override ROOT before executing
        mod.__dict__["__file__"] = str(Path({str(tmp_path)!r}) / "scripts" / "check_versions.py")
        spec.loader.exec_module(mod)
        """),
        encoding="utf-8",
    )

    # Simpler approach: call the script directly but override ROOT via env
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env={
            **__import__("os").environ,
            "_CHECK_VERSIONS_ROOT": str(tmp_path),
        },
    )
    return result


@pytest.fixture(autouse=True)
def _patch_root(monkeypatch):
    """Make ROOT in check_versions read from env var _CHECK_VERSIONS_ROOT if set."""
    # We patch the script dynamically via an env var the script reads
    pass  # actual patching done via env var approach below


def _run_patched(
    *args: str, pyproject: str, init: str, cargo: str, tmp_path: Path
) -> subprocess.CompletedProcess:
    """Write temporary files and run the script with ROOT overridden via env."""
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(f"""\
        [project]
        name = "youkai"
        version = "{pyproject}"
        """),
        encoding="utf-8",
    )
    src = tmp_path / "src" / "youkai_ocr"
    src.mkdir(parents=True, exist_ok=True)
    (src / "__init__.py").write_text(f'__version__ = "{init}"\n', encoding="utf-8")
    youkai_dir = tmp_path / "youkai"
    youkai_dir.mkdir(exist_ok=True)
    (youkai_dir / "Cargo.toml").write_text(
        textwrap.dedent(f"""\
        [package]
        name = "youkai"
        version = "{cargo}"
        """),
        encoding="utf-8",
    )

    # Write a thin wrapper that overrides ROOT before importing main logic
    wrapper = tmp_path / "_wrapper.py"
    wrapper.write_text(
        textwrap.dedent(f"""\
        import sys
        from pathlib import Path
        # Inject ROOT override before the script runs
        import importlib.util, types
        source = Path({str(SCRIPT)!r}).read_text()
        source = source.replace(
            "ROOT = Path(__file__).resolve().parents[1]",
            "ROOT = Path({str(tmp_path)!r})",
        )
        code = compile(source, {str(SCRIPT)!r}, "exec")
        ns = {{"__name__": "__main__", "__file__": {str(SCRIPT)!r}}}
        exec(code, ns)
        """),
        encoding="utf-8",
    )

    return subprocess.run(
        [sys.executable, str(wrapper), *args],
        capture_output=True,
        text=True,
    )


def test_all_match(tmp_path):
    r = _run_patched(pyproject="1.2.3", init="1.2.3", cargo="1.2.3", tmp_path=tmp_path)
    assert r.returncode == 0
    assert "1.2.3" in r.stdout


def test_all_match_with_build_metadata(tmp_path):
    """__version__ = "1.2.3+dev" should compare as "1.2.3"."""
    r = _run_patched(pyproject="1.2.3", init="1.2.3+dev", cargo="1.2.3", tmp_path=tmp_path)
    assert r.returncode == 0


def test_mismatch_cargo(tmp_path):
    r = _run_patched(pyproject="1.2.3", init="1.2.3", cargo="1.0.0", tmp_path=tmp_path)
    assert r.returncode != 0
    assert "mismatch" in r.stderr.lower()


def test_mismatch_init(tmp_path):
    r = _run_patched(pyproject="1.2.3", init="1.9.9", cargo="1.2.3", tmp_path=tmp_path)
    assert r.returncode != 0


def test_expect_match(tmp_path):
    r = _run_patched(
        "--expect", "1.2.3", pyproject="1.2.3", init="1.2.3", cargo="1.2.3", tmp_path=tmp_path
    )
    assert r.returncode == 0


def test_expect_mismatch(tmp_path):
    r = _run_patched(
        "--expect", "9.9.9", pyproject="1.2.3", init="1.2.3", cargo="1.2.3", tmp_path=tmp_path
    )
    assert r.returncode != 0
    assert "9.9.9" in r.stderr
