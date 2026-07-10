"""Verify that the three product version strings are consistent.

Usage:
    python scripts/check_versions.py               # assert all three agree
    python scripts/check_versions.py --expect 0.2.0 # also assert they equal the tag
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read_pyproject_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return data["project"]["version"]


def _read_init_version() -> str:
    text = (ROOT / "src" / "youkai_ocr" / "__init__.py").read_text(encoding="utf-8")
    m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    if not m:
        raise ValueError("Could not find __version__ in src/youkai_ocr/__init__.py")
    raw = m.group(1)
    # Strip build metadata (e.g. "0.2.0+dev" → "0.2.0")
    return raw.split("+")[0]


def _read_cargo_version() -> str:
    text = (ROOT / "youkai" / "Cargo.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    if not m:
        raise ValueError("Could not find version in youkai/Cargo.toml")
    return m.group(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--expect",
        metavar="X.Y.Z",
        default=None,
        help="Also assert that all versions equal this value (e.g. the git tag).",
    )
    args = parser.parse_args()

    pyproject = _read_pyproject_version()
    init = _read_init_version()
    cargo = _read_cargo_version()

    errors: list[str] = []

    if not (pyproject == init == cargo):
        errors.append(
            f"Version mismatch:\n"
            f"  pyproject.toml           : {pyproject}\n"
            f"  src/youkai_ocr/__init__.py: {init}\n"
            f"  youkai/Cargo.toml        : {cargo}"
        )

    if args.expect and pyproject != args.expect:
        errors.append(f"Version {pyproject!r} does not match expected tag {args.expect!r}")

    if errors:
        for msg in errors:
            print(f"ERROR: {msg}", file=sys.stderr)
        sys.exit(1)

    print(f"OK: all versions agree on {pyproject}")


if __name__ == "__main__":
    main()
