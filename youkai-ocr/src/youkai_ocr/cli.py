"""Entry point: youkai-ocr --help"""

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="youkai-ocr",
        description="ZZZ inventory OCR scanner — exports ZodExport/GOOD JSON.",
    )
    parser.add_argument(
        "--version", action="version", version="youkai-ocr 0.1.0"
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("scan", help="Run a full inventory scan (not yet implemented).")
    subparsers.add_parser("calibrate", help="Calibrate window position and scale (not yet implemented).")

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(0)

    print(f"Command '{args.command}' is not yet implemented.", file=sys.stderr)
    sys.exit(1)
