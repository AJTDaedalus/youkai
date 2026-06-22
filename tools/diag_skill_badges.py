"""T3 diagnostic: measure skill-badge blob metrics vs ground truth.

Reads tests/fixtures/golden/oracle_talent.json (per-agent talent truth +
archive_idx) and, for every skill badge, reproduces the exact preprocessing
and connected-component analysis used by agent_scanner._read_skill_badge,
dumping the measured features (threshold pass, b0_w, b0_fill, b1_w, b1_fill)
alongside the truth digit and the value the live classifier returns.

Output: a labeled fill-ratio table grouped by truth value, written to
docs/diag_skill_badges.csv and summarized to stdout. No thresholds are
changed — this is the evidence-gathering step for T3.

Run: python tools/diag_skill_badges.py
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from youkai_ocr.agent_scanner import (
    _SKILL_LEVEL_BBOXES,
    _read_skill_badge,
    _BADGE_THRESHOLD_HI,
    _BADGE_THRESHOLD_LO,
    _BADGE_NARROW_W,
)

ROOT = Path(__file__).resolve().parent.parent
RUN = ROOT / "archive/live_20260609/live_20260610_065548"
ORACLE = ROOT / "tests/fixtures/golden/oracle_talent.json"
OUT_CSV = ROOT / "docs/diag_skill_badges.csv"

SKILL_ORDER = ("basic", "dodge", "assist", "special", "chain")


def measure(badge_crop: Image.Image) -> list[dict]:
    """Return per-pass blob metrics for a badge crop (mirrors _read_skill_badge)."""
    arr = np.array(badge_crop.convert("RGB"))
    h, w = arr.shape[:2]
    arr_up = cv2.resize(arr, (w * 3, h * 3), interpolation=cv2.INTER_LANCZOS4)
    gray = cv2.cvtColor(arr_up, cv2.COLOR_RGB2GRAY)

    rows = []
    for label, thr in (("hi", _BADGE_THRESHOLD_HI), ("lo", _BADGE_THRESHOLD_LO)):
        _, binary = cv2.threshold(gray, thr, 255, cv2.THRESH_BINARY)
        left_w = int(binary.shape[1] * 0.52)
        n, _, stats, centroids = cv2.connectedComponentsWithStats(binary[:, :left_w])
        blobs = [
            (stats[i], centroids[i])
            for i in range(1, n)
            if stats[i, cv2.CC_STAT_AREA] > 200
        ]
        blobs.sort(key=lambda x: x[1][0])
        rec: dict = {"pass": label, "nblobs": len(blobs)}
        for j, (s, _c) in enumerate(blobs[:2]):
            bw = int(s[cv2.CC_STAT_WIDTH])
            bh = int(s[cv2.CC_STAT_HEIGHT])
            ba = int(s[cv2.CC_STAT_AREA])
            fill = ba / (bw * bh) if bw * bh else 0.0
            rec[f"b{j}_w"] = bw
            rec[f"b{j}_h"] = bh
            rec[f"b{j}_fill"] = round(fill, 3)
        rows.append(rec)
    return rows


def main() -> None:
    oracle = json.loads(ORACLE.read_text())
    fieldnames = [
        "key", "idx", "skill", "truth", "classified", "match",
        "pass", "nblobs", "narrow_w",
        "b0_w", "b0_h", "b0_fill", "b1_w", "b1_h", "b1_fill",
    ]
    out_rows: list[dict] = []

    for a in oracle["agents"]:
        idx = a["archive_idx"]
        frame_path = RUN / f"agent_{idx:03d}" / "skills.png"
        if not frame_path.exists():
            print(f"!! missing {frame_path}")
            continue
        frame = Image.open(frame_path)
        for skill, bbox in zip(SKILL_ORDER, _SKILL_LEVEL_BBOXES):
            crop = frame.crop(bbox)  # identity calib (frames are 1920x1080)
            truth = a["talent_truth"][skill]
            raw = _read_skill_badge(crop)
            classified = raw[0] if raw else None
            metrics = measure(crop)
            # Which pass would the classifier actually land on? hi first; if it
            # returns a value, lo is never reached. Report both for evidence.
            for m in metrics:
                out_rows.append({
                    "key": a["key"], "idx": idx, "skill": skill,
                    "truth": truth, "classified": classified,
                    "match": "OK" if classified == truth else "MISS",
                    "narrow_w": _BADGE_NARROW_W,
                    **m,
                })

    OUT_CSV.parent.mkdir(exist_ok=True)
    with OUT_CSV.open("w", newline="") as f:
        wri = csv.DictWriter(f, fieldnames=fieldnames)
        wri.writeheader()
        for r in out_rows:
            wri.writerow({k: r.get(k, "") for k in fieldnames})
    print(f"wrote {OUT_CSV} ({len(out_rows)} rows)")

    # ── Summary: fill-ratio table grouped by truth value ──────────────────────
    # For each badge we report the LO-pass b1 metrics (the dim-fallback path),
    # since that's the path T3 targets. We dedup to one row per (key,idx,skill).
    print("\n== Dim-pass (lo) b1 metrics, grouped by truth value ==")
    print(f"{'truth':>5} {'key':<14} {'skill':<8} {'cls':>4} {'res':<4} "
          f"{'b0_w':>5} {'b0_fill':>7} {'b1_w':>5} {'b1_fill':>7}")
    per_badge: dict[tuple, dict] = {}
    for r in out_rows:
        if r["pass"] != "lo":
            continue
        per_badge[(r["idx"], r["skill"])] = r
    for r in sorted(per_badge.values(), key=lambda x: (x["truth"], x["key"])):
        print(f"{r['truth']:>5} {r['key']:<14} {r['skill']:<8} "
              f"{str(r['classified']):>4} {r['match']:<4} "
              f"{r.get('b0_w',''):>5} {str(r.get('b0_fill','')):>7} "
              f"{r.get('b1_w',''):>5} {str(r.get('b1_fill','')):>7}")


if __name__ == "__main__":
    main()
