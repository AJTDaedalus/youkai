"""T2.1 diagnostic: replay archived disc panel.png crops and collect key:"" cases.

Run from the repo root:
    python tools/diag_empty_keys.py [--limit N] [--save-crops]

For each disc with an empty substat key, prints the failure mode and optionally
saves the name-region crop to /tmp/diag_crops/ for visual inspection.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from youkai_ocr.capture import CalibrationResult
from youkai_ocr.disc_scanner import (
    _PANEL_BBOX,
    _PANEL_ORIGIN,
    _SUBSTAT_RELS,
    _abs_bbox,
    _crop,
    _extract_disc,
)
from youkai_ocr.recognize import make_recognizer

ROOT = Path(__file__).parent.parent
DISC_RUN = ROOT / "archive/live_20260605"

CALIB = CalibrationResult(scale_x=1.0, scale_y=1.0, frame_width=1920, frame_height=1080)
DUMMY_CELL = (300, 300)


def panel_to_frame(panel_path: Path) -> Image.Image:
    frame = Image.new("RGB", (1920, 1080), (10, 10, 10))
    panel = Image.open(panel_path).convert("RGB")
    frame.paste(panel, (_PANEL_BBOX[0], _PANEL_BBOX[1]))
    return frame


def diagnose_name_region(
    frame: Image.Image,
    substat_idx: int,
    recognizer,
    save_path: Path | None = None,
) -> dict:
    """Inspect the name region for a specific substat slot and return brightness info."""
    name_rel, _val_rel = _SUBSTAT_RELS[substat_idx]
    name_bbox = _abs_bbox(name_rel, _PANEL_ORIGIN)
    crop = _crop(frame, CALIB, name_bbox)

    bright_text = recognizer.read_line(crop, "white_text_on_dark").strip()
    dim_text = recognizer.read_line(crop, "white_text_on_dark_dim").strip()

    # Brightness stats: median and 90th percentile of grayscale to classify dim vs empty
    import numpy as np

    arr = np.array(crop.convert("L"))
    median_luma = float(np.median(arr))
    p90_luma = float(np.percentile(arr, 90))
    max_luma = float(arr.max())

    if save_path:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        crop.save(save_path)
        # Also save 2× upscale
        up = crop.resize((crop.width * 2, crop.height * 2), Image.LANCZOS)
        up.save(save_path.with_suffix(".2x.png"))

    return {
        "bright_text": bright_text,
        "dim_text": dim_text,
        "median_luma": round(median_luma, 1),
        "p90_luma": round(p90_luma, 1),
        "max_luma": round(max_luma, 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Max discs to scan (0=all)")
    parser.add_argument(
        "--save-crops", action="store_true", help="Save name crops to /tmp/diag_crops/"
    )
    args = parser.parse_args()

    recognizer = make_recognizer("tesseract")
    crop_dir = Path("/tmp/diag_crops") if args.save_crops else None

    disc_dirs = sorted(DISC_RUN.glob("disc_*/"))
    if args.limit:
        disc_dirs = disc_dirs[: args.limit]

    total = 0
    empty_key_cases: list[dict] = []
    failure_modes: Counter = Counter()

    print(f"Scanning {len(disc_dirs)} disc dirs...", flush=True)

    for disc_dir in disc_dirs:
        panel_path = disc_dir / "panel.png"
        if not panel_path.exists():
            continue
        total += 1

        frame = panel_to_frame(panel_path)
        disc, conf = _extract_disc(frame, CALIB, *DUMMY_CELL, recognizer, None, 0)

        if disc is None:
            continue

        for i, sub in enumerate(disc.substats):
            if sub.key == "":
                # Diagnose this slot
                save_path = None
                if crop_dir:
                    save_path = crop_dir / f"{disc_dir.name}_sub{i}.png"

                info = diagnose_name_region(frame, i, recognizer, save_path)

                # Classify failure mode
                if info["max_luma"] < 30:
                    mode = "black/invisible"
                elif info["max_luma"] < 80:
                    mode = "very_dim"
                elif info["p90_luma"] < 50:
                    mode = "dim_with_bright_pixels"
                elif not info["bright_text"] and not info["dim_text"]:
                    mode = "ocr_blank_readable_region"
                elif not info["bright_text"] and info["dim_text"]:
                    mode = "dim_only_readable"
                else:
                    mode = "dict_gap"

                failure_modes[mode] += 1
                empty_key_cases.append(
                    {
                        "disc": disc_dir.name,
                        "substat_idx": i,
                        "value": sub.value,
                        "mode": mode,
                        **info,
                    }
                )
                print(
                    f"  EMPTY_KEY {disc_dir.name} sub{i}: "
                    f"mode={mode!r} bright={info['bright_text']!r} "
                    f"dim={info['dim_text']!r} "
                    f"luma(med={info['median_luma']} p90={info['p90_luma']}"
                    f" max={info['max_luma']}) "
                    f"val={sub.value}"
                )

        if total % 200 == 0:
            print(
                f"  ... {total}/{len(disc_dirs)} scanned, {len(empty_key_cases)} empty keys so far",
                flush=True,
            )

    print("\n=== SUMMARY ===")
    print(f"Total discs scanned: {total}")
    print(f"Total empty-key substats: {len(empty_key_cases)}")
    print(f"Empty-key rate: {len(empty_key_cases) / total * 100:.2f}% of discs have ≥1")

    counted_discs = len({c["disc"] for c in empty_key_cases})
    print(f"Discs with ≥1 empty key: {counted_discs}")

    print("\nFailure modes:")
    for mode, count in failure_modes.most_common():
        print(f"  {mode}: {count}")

    # Print examples per mode
    seen_modes: set[str] = set()
    print("\nFirst example per mode:")
    for case in empty_key_cases:
        if case["mode"] not in seen_modes:
            seen_modes.add(case["mode"])
            print(
                f"  [{case['mode']}] {case['disc']} sub{case['substat_idx']}: "
                f"bright={case['bright_text']!r} dim={case['dim_text']!r} val={case['value']}"
            )

    # Save full report
    report = {
        "total_discs": total,
        "empty_key_count": len(empty_key_cases),
        "discs_with_empty_key": counted_discs,
        "failure_modes": dict(failure_modes),
        "cases": empty_key_cases[:100],  # first 100 for review
    }
    out_path = ROOT / "docs" / "diag_empty_keys.json"
    out_path.write_text(json.dumps(report, indent=2))
    print(f"\nFull report: {out_path}")


if __name__ == "__main__":
    main()
