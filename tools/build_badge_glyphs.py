"""T7: Build per-digit badge-glyph reference set for template matching.

Extracts the units-digit (b1) blob from each labeled skill badge, normalises
to GLYPH_W×GLYPH_H pixels (letterboxed binary), and emits
tests/fixtures/badge_glyphs.json.

Ground-truth sources (in priority order):
  1. tests/fixtures/golden/oracle_talent.json  — 26 hand-verified agents
  2. EXTRA_TRUTH dict below                    — manually confirmed agents not
     in oracle (currently: Velina, dodge=9 confirmed from June-17 skills.png)

Archive used: live_20260617_194045 on the Windows host (46 agent folders,
all with skills.png).  Oracle agents are matched by key to their folder in
this run; extra-truth agents by fixed folder index.

Run:
    python tools/build_badge_glyphs.py

Acceptance: all digits 0–9 have ≥ 2 samples.
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = Path("/mnt/c/Users/laharre/OneDrive/Documents/youkai/archive/live_20260617_194045")
ARCHIVE_J9 = ROOT / "archive/live_20260609/live_20260610_065548"
ORACLE = ROOT / "tests/fixtures/golden/oracle_talent.json"
OUT = ROOT / "tests/fixtures/badge_glyphs.json"

GLYPH_W, GLYPH_H = 24, 36

# Badge crop bboxes (1920×1080 ref coords) — mirrors agent_scanner._SKILL_LEVEL_BBOXES
_SKILL_BBOXES: list[tuple[int, int, int, int]] = [
    (930, 750, 1065, 780),  # basic
    (1110, 750, 1245, 780),  # dodge
    (1295, 750, 1425, 780),  # assist
    (1470, 750, 1605, 780),  # special
    (1650, 750, 1785, 780),  # chain
]
SKILL_ORDER = ("basic", "dodge", "assist", "special", "chain")

_BADGE_THRESHOLD_HI = 180  # bright badges (values 10+)
_BADGE_THRESHOLD_LO = 130  # dim badges (values 1–9)
_MIN_BLOB_AREA = 200  # ignore tiny noise components (at 3× scale)

# Manually confirmed truth for agents not in oracle_talent.json.
# Key → {skill: level}.  Folder index must be set in EXTRA_FOLDER below.
# Values confirmed by visual inspection of skills.png.
EXTRA_TRUTH: dict[str, dict[str, int]] = {
    "Velina": {"basic": 11, "dodge": 9, "assist": 11, "special": 12, "chain": 11},
    # Confirmed from agent_030/skills.png (07/16, 07/16, 08/16, 12/16, 07/16)
    "Billy": {"basic": 7, "dodge": 7, "assist": 8, "special": 12, "chain": 7},
    # Confirmed from agent_019/skills.png (12/12, 05/12, 08/12, 10/12, 08/12)
    "Seth": {"basic": 12, "dodge": 5, "assist": 8, "special": 10, "chain": 8},
    # Confirmed from agent_028/skills.png (13/16, 11/16, 11/16, 13/16, 11/16)
    "Nekomata": {"basic": 13, "dodge": 11, "assist": 11, "special": 13, "chain": 11},
}
# Fixed folder indices for EXTRA_TRUTH agents in ARCHIVE (June-17).
EXTRA_FOLDER: dict[str, int] = {
    "Velina": 41,
    "Billy": 30,
    "Seth": 19,
    "Nekomata": 28,
}


def _extract_b1(badge_crop: Image.Image, truth_value: int) -> np.ndarray | None:
    """Extract and normalise the units-digit (b1) blob from one badge crop.

    Mirrors the preprocessing in agent_scanner._read_skill_badge:
      3× Lanczos upscale → threshold → connected components in left 52%.
    The second-leftmost significant blob (b1) is the units digit for both
    the "0X" dim format and the "1X" bright format.

    Threshold selection mirrors runtime: try HI first; fall back to LO if fewer
    than 2 blobs survive (some near-max badges render below the HI cutoff).

    Returns a GLYPH_H×GLYPH_W uint8 binary array, or None if b1 can't be found.
    """
    arr = np.array(badge_crop.convert("RGB"))
    h, w = arr.shape[:2]
    arr_up = cv2.resize(arr, (w * 3, h * 3), interpolation=cv2.INTER_LANCZOS4)
    gray = cv2.cvtColor(arr_up, cv2.COLOR_RGB2GRAY)

    def _blobs(thr: int) -> tuple[np.ndarray, list]:
        _, binary = cv2.threshold(gray, thr, 255, cv2.THRESH_BINARY)
        left_w = int(binary.shape[1] * 0.52)
        n, _, stats, centroids = cv2.connectedComponentsWithStats(binary[:, :left_w])
        blobs = sorted(
            [
                (stats[i], centroids[i])
                for i in range(1, n)
                if stats[i, cv2.CC_STAT_AREA] > _MIN_BLOB_AREA
            ],
            key=lambda x: x[1][0],
        )
        return binary, blobs

    binary, blobs = _blobs(_BADGE_THRESHOLD_HI)
    if len(blobs) < 2:
        binary, blobs = _blobs(_BADGE_THRESHOLD_LO)
    if len(blobs) < 2:
        return None

    b1_s = blobs[1][0]
    x = int(b1_s[cv2.CC_STAT_LEFT])
    y = int(b1_s[cv2.CC_STAT_TOP])
    bw = int(b1_s[cv2.CC_STAT_WIDTH])
    bh = int(b1_s[cv2.CC_STAT_HEIGHT])
    if bw == 0 or bh == 0:
        return None

    b1_crop = binary[y : y + bh, x : x + bw]

    # Letterbox-scale to GLYPH_W×GLYPH_H, then re-threshold to keep binary.
    scale = min(GLYPH_W / bw, GLYPH_H / bh)
    new_w = max(1, int(bw * scale))
    new_h = max(1, int(bh * scale))
    scaled = cv2.resize(b1_crop, (new_w, new_h), interpolation=cv2.INTER_AREA)
    _, scaled = cv2.threshold(scaled, 127, 255, cv2.THRESH_BINARY)

    canvas = np.zeros((GLYPH_H, GLYPH_W), dtype=np.uint8)
    y_off = (GLYPH_H - new_h) // 2
    x_off = (GLYPH_W - new_w) // 2
    canvas[y_off : y_off + new_h, x_off : x_off + new_w] = scaled
    return canvas


def main() -> None:
    oracle = json.loads(ORACLE.read_text())

    # truth_map: key → {skill: truth_level}
    truth_map: dict[str, dict[str, int]] = {a["key"]: a["talent_truth"] for a in oracle["agents"]}
    truth_map.update(EXTRA_TRUTH)

    # folder_map: key → folder index in June-17 archive
    agents_raw = json.loads((ARCHIVE / "agents.json").read_text())
    agents_list = agents_raw if isinstance(agents_raw, list) else agents_raw.get("agents", [])
    folder_map: dict[str, int] = {}
    for i, a in enumerate(agents_list):
        key = a.get("key", "")
        if key and key not in folder_map:
            folder_map[key] = i
    folder_map.update(EXTRA_FOLDER)

    # J9 fallback: oracle agents absent from June-17 use the June-9 archive
    j9_idx: dict[str, int] = {
        a["key"]: a["archive_idx"] for a in oracle["agents"] if a["key"] not in folder_map
    }

    glyphs: dict[int, list[list[int]]] = {d: [] for d in range(10)}
    skipped: list[str] = []

    for key, truth in sorted(truth_map.items()):
        if key in folder_map:
            skills_path = ARCHIVE / f"agent_{folder_map[key]:03d}" / "skills.png"
        elif key in j9_idx:
            skills_path = ARCHIVE_J9 / f"agent_{j9_idx[key]:03d}" / "skills.png"
        else:
            print(f"  SKIP {key}: not in either archive")
            continue
        if not skills_path.exists():
            print(f"  SKIP {key}: skills.png missing ({skills_path})")
            continue
        frame = Image.open(skills_path)
        for skill_idx, skill in enumerate(SKILL_ORDER):
            tv = truth.get(skill)
            if tv is None:
                continue
            units = tv % 10
            bbox = _SKILL_BBOXES[skill_idx]
            crop = frame.crop(bbox)
            glyph = _extract_b1(crop, tv)
            if glyph is None:
                tag = f"{key}/{skill}=={tv}"
                print(f"  b1 not found: {tag}")
                skipped.append(tag)
                continue
            glyphs[units].append(glyph.flatten().tolist())

    # ── Report ──────────────────────────────────────────────────────────────────
    print("\nGlyph counts per digit:")
    all_ok = True
    for d in range(10):
        count = len(glyphs[d])
        status = "OK" if count >= 2 else ("WARN – only 1" if count == 1 else "MISSING")
        print(f"  digit {d}: {count:3d} samples  [{status}]")
        if count < 2:
            all_ok = False

    if skipped:
        print(f"\nSkipped {len(skipped)} badges (b1 not found): {skipped}")

    # ── Emit ────────────────────────────────────────────────────────────────────
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": {
            "glyph_w": GLYPH_W,
            "glyph_h": GLYPH_H,
            "archive": str(ARCHIVE),
            "digits": 10,
        },
        "glyphs": {str(d): glyphs[d] for d in range(10)},
    }
    OUT.write_text(json.dumps(payload, separators=(",", ":")))
    print(f"\nWrote {OUT}")
    if not all_ok:
        print("WARNING: some digits have <2 samples — see above.")


if __name__ == "__main__":
    main()
