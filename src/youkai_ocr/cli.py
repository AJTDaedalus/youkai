"""Entry point: youkai-ocr --help"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def _countdown(seconds: int) -> None:
    """Count down, then bring the game window to the foreground."""
    from .capture import focus_game_window
    for i in range(seconds, 0, -1):
        print(f"  Starting in {i}s...", end="\r", flush=True)
        time.sleep(1)
    focused = focus_game_window()
    time.sleep(0.3)  # let the OS process the foreground change
    status = "game window focused" if focused else "WARNING: could not focus game window"
    print(f"  Scanning... ({status})", flush=True)


def _make_first_item_check(phase: str):
    """Return a callback that warns if the first scanned item has uniformly low confidence."""
    def _check(item, conf: dict) -> None:
        if not conf:
            return
        mean_conf = sum(conf.values()) / len(conf)
        low_fields = {k: v for k, v in conf.items() if v < 30}
        if item is None or mean_conf < 25:
            raise RuntimeError(
                f"First {phase} completely failed OCR (mean confidence {mean_conf:.0f}%). "
                "Check that the game is on the correct screen and the window is unobscured.\n"
                "Inspect the preflight PNG in your archive dir to see what the scanner captured."
            )
        if len(low_fields) >= len(conf) // 2:
            print(f"\n  WARNING: first {phase} has low confidence on {len(low_fields)}/{len(conf)} fields:")
            for field, score in sorted(low_fields.items(), key=lambda x: x[1]):
                print(f"    {field}: {score:.0f}%")
            print("  Inspect the preflight PNG in your archive dir.")
            ans = input("  Continue scan anyway? [y/N] ").strip().lower()
            if ans != "y":
                raise RuntimeError(f"Scan aborted by user after low-confidence {phase} warning.")
    return _check


def _preflight_frame(
    capture_fn,
    calib,
    archive_dir: "Path | None",
    phase: str,
) -> None:
    """Capture one frame, run basic sanity checks, and save it for inspection.

    Raises RuntimeError if the frame looks unusable (black, wrong size).
    Prints a warning and asks the user to confirm if brightness is marginal.
    """
    import numpy as np

    frame = capture_fn()

    if archive_dir:
        from .grid import DEFAULT_GRID
        from PIL import ImageDraw
        annotated = frame.copy()
        draw = ImageDraw.Draw(annotated)
        for col in range(DEFAULT_GRID.columns):
            for row in range(DEFAULT_GRID.rows_visible):
                rx, ry = DEFAULT_GRID.cell_center(col, row)
                fx = round(rx * calib.scale_x)
                fy = round(ry * calib.scale_y)
                r = 8
                draw.ellipse((fx - r, fy - r, fx + r, fy + r), outline="red", width=2)
        path = archive_dir / f"preflight_{phase}.png"
        annotated.save(path)
        print(f"  Preflight frame saved → {path}  (grid cells marked in red)")

    # Wrong size means the window moved or was resized after calibration.
    if frame.width != calib.frame_width or frame.height != calib.frame_height:
        raise RuntimeError(
            f"Frame size changed after calibration: got {frame.width}×{frame.height}, "
            f"expected {calib.frame_width}×{calib.frame_height}. "
            "Did the game window resize?"
        )

    import numpy as np
    arr = np.array(frame)
    brightness = float(arr.mean())
    print(f"  Frame brightness: {brightness:.1f}/255", end="")

    if brightness < 5:
        print()
        raise RuntimeError(
            f"Captured frame is nearly black (mean brightness {brightness:.1f}). "
            "The game may be minimized, covered, or in fullscreen mode."
        )
    # Dark UI (e.g. disc inventory) typically sits around 30–60; only warn below 15.
    if brightness < 15:
        print(f"  — frame looks very dark, game may be obscured.")
        ans = input("  Continue anyway? [y/N] ").strip().lower()
        if ans != "y":
            raise RuntimeError("Scan aborted by user after dark-frame warning.")
    else:
        print("  — OK")


def _cmd_calibrate(args: argparse.Namespace) -> None:
    from PIL import Image
    from .capture import calibrate, grab_window

    if args.file:
        frame = Image.open(args.file).convert("RGB")
    else:
        frame = grab_window()

    result = calibrate(frame)
    print(f"Frame:  {result.frame_width}×{result.frame_height}")
    print(f"Scale:  x={result.scale_x:.4f}  y={result.scale_y:.4f}")
    print(f"Identity: {result.is_identity}")


def _cmd_scan_engines(args: argparse.Namespace) -> None:
    import time
    from PIL import Image
    from .capture import calibrate, grab_window
    from .wengine_scanner import export_engines, scan_engines, scan_single_frame_engine

    output = Path(args.output)
    archive_dir = Path(args.archive_dir) if args.archive_dir else None

    if args.file:
        frame = Image.open(args.file).convert("RGB")
        if args.crop:
            x0, y0, x1, y1 = (int(v) for v in args.crop.split(","))
            frame = frame.crop((x0, y0, x1, y1))
        calib = calibrate(frame)
        print(f"Offline mode — frame: {frame.width}×{frame.height}, scale: {calib.scale_x:.3f}×{calib.scale_y:.3f}")

        if archive_dir:
            archive_dir.mkdir(parents=True, exist_ok=True)
            print(f"Archiving crops to: {archive_dir}")

        t0 = time.perf_counter()
        eng, conf = scan_single_frame_engine(frame, calib, archive_dir=archive_dir, engine=args.engine)
        elapsed = time.perf_counter() - t0

        print(f"\nExtraction complete ({elapsed:.1f}s)")
        print(f"Confidence: {json.dumps(conf, indent=2)}")

        if eng is None:
            print("\nCRITICAL FAIL — could not extract engine. Check bboxes and OCR output in archive.")
            sys.exit(1)

        print(f"\nEngine: {json.dumps(eng.to_dict(), indent=2)}")
        export_engines([eng], output)
        print(f"\nExported to: {output}")

    else:
        frame = grab_window()
        calib = calibrate(frame)
        print(f"Game window found: {frame.width}×{frame.height}, scale: {calib.scale_x:.3f}×{calib.scale_y:.3f}")
        capture_fn = grab_window

        print("Starting W-Engine scan. Make sure the W-Engine inventory is open.")
        print("Press Esc at any time to stop.")

        if archive_dir:
            archive_dir.mkdir(parents=True, exist_ok=True)
            print(f"Archiving crops to: {archive_dir}")

        t0 = time.perf_counter()
        engines, issues = scan_engines(
            capture_fn=capture_fn,
            calib=calib,
            archive_dir=archive_dir,
            engine=args.engine,
        )
        elapsed = time.perf_counter() - t0

        print(f"\nScanned {len(engines)} engine(s) in {elapsed:.1f}s. Issues: {len(issues)}")

        if issues:
            print("\n--- Issues ---")
            for issue in issues:
                print(json.dumps(issue, indent=2))

        if not engines:
            print("No engines scanned — check that the W-Engine inventory screen is open.")
            sys.exit(1)

        export_engines(engines, output)
        print(f"\nExported to: {output}")


def _cmd_scan_agents(args: argparse.Namespace) -> None:
    import time
    from PIL import Image
    from .capture import calibrate, grab_window
    from .agent_scanner import export_agents, scan_agents, scan_single_frame_agent

    output = Path(args.output)
    archive_dir = Path(args.archive_dir) if args.archive_dir else None

    if args.file:
        # Offline mode: extract from two static frames (base stats + skills tab).
        # Pass --file for base stats and --skills-file for the skills tab.
        base_frame = Image.open(args.file).convert("RGB")
        if args.crop:
            x0, y0, x1, y1 = (int(v) for v in args.crop.split(","))
            base_frame = base_frame.crop((x0, y0, x1, y1))

        skills_path = args.skills_file or args.file
        skills_frame = Image.open(skills_path).convert("RGB")
        if args.crop:
            x0, y0, x1, y1 = (int(v) for v in args.crop.split(","))
            skills_frame = skills_frame.crop((x0, y0, x1, y1))

        calib = calibrate(base_frame)
        print(f"Offline mode — frame: {base_frame.width}×{base_frame.height}, scale: {calib.scale_x:.3f}×{calib.scale_y:.3f}")

        if archive_dir:
            archive_dir.mkdir(parents=True, exist_ok=True)

        t0 = time.perf_counter()
        agent, conf = scan_single_frame_agent(base_frame, skills_frame, calib, ocr_engine=args.engine)
        elapsed = time.perf_counter() - t0

        print(f"\nExtraction complete ({elapsed:.1f}s)")
        print(f"Confidence: {json.dumps(conf, indent=2)}")

        if agent is None:
            print("\nCRITICAL FAIL — could not extract agent. Check bboxes and OCR output.")
            sys.exit(1)

        print(f"\nAgent: {json.dumps(agent.to_dict(), indent=2)}")
        export_agents([agent], output)
        print(f"\nExported to: {output}")

    else:
        frame = grab_window()
        calib = calibrate(frame)
        print(f"Game window found: {frame.width}×{frame.height}, scale: {calib.scale_x:.3f}×{calib.scale_y:.3f}")
        capture_fn = grab_window

        print("Starting agent scan. Make sure an agent detail page is open.")
        print("Press Esc at any time to stop.")

        if archive_dir:
            archive_dir.mkdir(parents=True, exist_ok=True)
            print(f"Archiving crops to: {archive_dir}")

        t0 = time.perf_counter()
        agents, issues, _equip_records = scan_agents(
            capture_fn=capture_fn,
            calib=calib,
            archive_dir=archive_dir,
            ocr_engine=args.engine,
        )
        elapsed = time.perf_counter() - t0

        print(f"\nScanned {len(agents)} agent(s) in {elapsed:.1f}s. Issues: {len(issues)}")

        if issues:
            print("\n--- Issues ---")
            for issue in issues:
                print(json.dumps(issue, indent=2))

        if not agents:
            print("No agents scanned — check that an agent detail page is open.")
            sys.exit(1)

        export_agents(agents, output)
        print(f"\nExported to: {output}")


def _cmd_scan(args: argparse.Namespace) -> None:
    import time
    from PIL import Image
    from .capture import calibrate, grab_window
    from .disc_scanner import export_discs, scan_discs, scan_single_frame

    output = Path(args.output)
    archive_dir = Path(args.archive_dir) if args.archive_dir else None

    if args.file:
        # Offline mode — extracts from a single static frame, no pynput needed.
        frame = Image.open(args.file).convert("RGB")
        if args.crop:
            x0, y0, x1, y1 = (int(v) for v in args.crop.split(","))
            frame = frame.crop((x0, y0, x1, y1))
        calib = calibrate(frame)
        print(f"Offline mode — frame: {frame.width}×{frame.height}, scale: {calib.scale_x:.3f}×{calib.scale_y:.3f}")

        if archive_dir:
            archive_dir.mkdir(parents=True, exist_ok=True)
            print(f"Archiving crops to: {archive_dir}")

        t0 = time.perf_counter()
        disc, conf = scan_single_frame(frame, calib, archive_dir=archive_dir, engine=args.engine)
        elapsed = time.perf_counter() - t0

        print(f"\nExtraction complete ({elapsed:.1f}s)")
        print(f"Confidence: {json.dumps(conf, indent=2)}")

        if disc is None:
            print("\nCRITICAL FAIL — could not extract disc. Check bboxes and OCR output in archive.")
            sys.exit(1)

        print(f"\nDisc: {json.dumps(disc.to_dict(), indent=2)}")
        export_discs([disc], output)
        print(f"\nExported to: {output}")

    else:
        # Live mode — drives the grid navigator with synthetic mouse input.
        # Requires Windows (win32gui / dxcam) and the game window to be open.
        frame = grab_window()
        calib = calibrate(frame)
        print(f"Game window found: {frame.width}×{frame.height}, scale: {calib.scale_x:.3f}×{calib.scale_y:.3f}")
        capture_fn = grab_window

        print("Starting disc scan. Make sure the Drive Disc inventory is open.")
        print("Press Esc at any time to stop.")

        if archive_dir:
            archive_dir.mkdir(parents=True, exist_ok=True)
            print(f"Archiving crops to: {archive_dir}")

        t0 = time.perf_counter()
        discs, issues = scan_discs(
            capture_fn=capture_fn,
            calib=calib,
            archive_dir=archive_dir,
            engine=args.engine,
        )
        elapsed = time.perf_counter() - t0

        print(f"\nScanned {len(discs)} disc(s) in {elapsed:.1f}s. Issues: {len(issues)}")

        if issues:
            print("\n--- Issues ---")
            for issue in issues:
                print(json.dumps(issue, indent=2))

        if not discs:
            print("No discs scanned — check that the inventory screen is open.")
            sys.exit(1)

        export_discs(discs, output)
        print(f"\nExported to: {output}")


def _cmd_scan_all(args: argparse.Namespace) -> None:
    """F1: Full ZodExport — discs + engines + agents with location wiring."""
    import time
    from .capture import calibrate_window
    from .disc_scanner import scan_discs
    from .wengine_scanner import scan_engines
    from .agent_scanner import scan_agents, resolve_locations
    from .zod import ZodExport

    output = Path(args.output)
    archive_dir = Path(args.archive_dir) if args.archive_dir else None

    calib, capture_fn = calibrate_window()
    print(f"Game window found: {calib.frame_width}×{calib.frame_height}, "
          f"offset: ({calib.window_left},{calib.window_top}), "
          f"scale: {calib.scale_x:.3f}×{calib.scale_y:.3f}")

    if archive_dir:
        archive_dir.mkdir(parents=True, exist_ok=True)
        print(f"Archiving crops to: {archive_dir}")

    all_issues: list[dict] = []

    # ── Step 1: Disc inventory ────────────────────────────────────────────────
    print("\n[1/3] Drive Disc inventory — navigate there, then press Enter.")
    input()
    _countdown(5)
    _preflight_frame(capture_fn, calib, archive_dir, "discs")
    # Show where click #1 will land so the user can sanity-check before the scan.
    from .grid import DEFAULT_GRID
    cell0 = DEFAULT_GRID.cell_0_0_center
    sx, sy = calib.to_screen(*cell0)
    print(f"  First cell ref=({cell0[0]},{cell0[1]}) → screen=({sx},{sy})  "
          f"window origin=({calib.window_left},{calib.window_top})")
    t0 = time.perf_counter()
    discs, disc_issues = scan_discs(
        capture_fn=capture_fn, calib=calib, archive_dir=archive_dir, engine=args.engine,
        on_first_item=_make_first_item_check("disc"),
    )
    all_issues.extend(disc_issues)
    print(f"  Scanned {len(discs)} disc(s) in {time.perf_counter()-t0:.1f}s. Issues: {len(disc_issues)}")

    # ── Step 2: W-Engine inventory ────────────────────────────────────────────
    print("\n[2/3] W-Engine inventory — navigate there, then press Enter.")
    input()
    _countdown(5)
    _preflight_frame(capture_fn, calib, archive_dir, "engines")
    t0 = time.perf_counter()
    engines, engine_issues = scan_engines(
        capture_fn=capture_fn, calib=calib, archive_dir=archive_dir, engine=args.engine,
    )
    all_issues.extend(engine_issues)
    print(f"  Scanned {len(engines)} engine(s) in {time.perf_counter()-t0:.1f}s. Issues: {len(engine_issues)}")

    # ── Step 3: Agent roster ──────────────────────────────────────────────────
    print("\n[3/3] Agent roster — open an agent detail page, then press Enter.")
    input()
    _countdown(5)
    _preflight_frame(capture_fn, calib, archive_dir, "agents")
    t0 = time.perf_counter()
    agents, agent_issues, equip_records = scan_agents(
        capture_fn=capture_fn, calib=calib, archive_dir=archive_dir, ocr_engine=args.engine,
    )
    all_issues.extend(agent_issues)
    print(f"  Scanned {len(agents)} agent(s) in {time.perf_counter()-t0:.1f}s. Issues: {len(agent_issues)}")

    # ── Resolve equipment locations ───────────────────────────────────────────
    orphans = resolve_locations(equip_records, discs, engines)
    if orphans:
        print(f"\n  Location orphans (equipment cross-ref mismatches): {len(orphans)}")
        all_issues.extend(orphans)

    # ── Dedupe + stable sort ──────────────────────────────────────────────────
    # Agents: keep first occurrence per key (roster nav should never produce dupes,
    # but guard anyway).
    seen_agents: set[str] = set()
    unique_agents = []
    for a in agents:
        if a.key not in seen_agents:
            seen_agents.add(a.key)
            unique_agents.append(a)
    unique_agents.sort(key=lambda a: a.key)

    # Discs: no natural unique key; preserve scan order (stable, grid-traverse).
    # Sort by set_key then slot_key for deterministic output.
    discs.sort(key=lambda d: (d.set_key, d.slot_key))

    # Engines: sort by key.
    engines.sort(key=lambda e: e.key)

    # ── Assemble and write ────────────────────────────────────────────────────
    export = ZodExport(characters=unique_agents, discs=discs, weapons=engines)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(export.to_json(), encoding="utf-8")

    print(f"\nExport written to: {output}")
    print(f"  {len(unique_agents)} agent(s), {len(discs)} disc(s), {len(engines)} engine(s)")

    if all_issues:
        issues_path = output.with_suffix(".issues.json")
        import json as _json
        issues_path.write_text(_json.dumps(all_issues, indent=2), encoding="utf-8")
        print(f"  {len(all_issues)} issue(s) written to: {issues_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="youkai-ocr",
        description="ZZZ inventory OCR scanner — exports ZodExport/GOOD JSON.",
    )
    parser.add_argument("--version", action="version", version="youkai-ocr 0.1.0")
    subparsers = parser.add_subparsers(dest="command")

    # -- calibrate ----------------------------------------------------------------
    cal = subparsers.add_parser("calibrate", help="Verify window detection and scale.")
    cal.add_argument("--file", metavar="PATH", help="Use a screenshot file instead of the live window.")

    # -- scan-engines -------------------------------------------------------------
    def _add_scan_args(p: argparse.ArgumentParser, default_output: str, subject: str) -> None:
        p.add_argument("--output", "-o", default=default_output, metavar="PATH",
                       help=f"Output JSON path (default: {default_output}).")
        p.add_argument("--archive-dir", "-a", default=None, metavar="DIR",
                       help="Save raw field crops here for debugging.")
        p.add_argument("--file", "-f", default=None, metavar="PATH",
                       help="Offline mode: use a static screenshot instead of the live window.")
        p.add_argument("--crop", default=None, metavar="X0,Y0,X1,Y1",
                       help="Crop screenshot to game area before calibrating.")
        p.add_argument("--engine", default="tesseract", choices=["tesseract"],
                       help="OCR engine (default: tesseract).")

    scan_eng = subparsers.add_parser("scan-engines", help="Scan the W-Engine inventory and export JSON.")
    _add_scan_args(scan_eng, "export/engines.json", "W-Engine")

    # -- scan-agents --------------------------------------------------------------
    scan_agt = subparsers.add_parser("scan-agents", help="Scan agent roster (stats, skills, equipment) and export JSON.")
    _add_scan_args(scan_agt, "export/agents.json", "agent")
    scan_agt.add_argument("--skills-file", default=None, metavar="PATH",
                          help="Offline mode: skills-tab screenshot (defaults to --file if omitted).")

    # -- scan ---------------------------------------------------------------------
    scan = subparsers.add_parser("scan", help="Scan the Drive Disc inventory and export JSON.")
    _add_scan_args(scan, "export/discs.json", "disc")

    # -- scan-all -----------------------------------------------------------------
    scan_all = subparsers.add_parser(
        "scan-all",
        help="Full scan: discs + engines + agents merged into one ZodExport JSON.",
    )
    scan_all.add_argument("--output", "-o", default="export/youkai_export.json", metavar="PATH",
                          help="Output JSON path (default: export/youkai_export.json).")
    scan_all.add_argument("--archive-dir", "-a", default=None, metavar="DIR",
                          help="Save raw field crops here for debugging.")
    scan_all.add_argument("--engine", default="tesseract", choices=["tesseract"],
                          help="OCR engine (default: tesseract).")

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "calibrate":
        _cmd_calibrate(args)
    elif args.command == "scan":
        _cmd_scan(args)
    elif args.command == "scan-engines":
        _cmd_scan_engines(args)
    elif args.command == "scan-agents":
        _cmd_scan_agents(args)
    elif args.command == "scan-all":
        _cmd_scan_all(args)


if __name__ == "__main__":
    main()
