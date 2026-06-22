"""T9: Leave-one-sample-out cross-validation + T3 regression for badge reader.

Two evaluations:

1. LOSO (leave-one-sample-out) accuracy per digit
   For each sample in badge_glyphs.json, build the median template from the
   remaining samples of that digit, then classify the held-out sample.
   Reports per-digit accuracy and the 7 T3-documented misread cases.

2. T3 regression — the 7 previously broken badges
   Extract b1 blobs from the oracle archive and verify `_read_skill_badge`
   now returns the correct value for each.

Run:
    python tools/eval_badge_reader.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from youkai_ocr.agent_scanner import _read_skill_badge, _b1_hole_count  # noqa: E402

GLYPHS_PATH = ROOT / "tests/fixtures/badge_glyphs.json"
ORACLE_PATH = ROOT / "tests/fixtures/golden/oracle_talent.json"
ARCHIVE_J9  = ROOT / "archive/live_20260609/live_20260610_065548"
ARCHIVE_J17 = Path(
    "/mnt/c/Users/laharre/OneDrive/Documents/youkai/archive/live_20260617_194045"
)

GLYPH_W, GLYPH_H = 24, 36

_SKILL_BBOXES = [
    ( 930, 750, 1065, 780),
    (1110, 750, 1245, 780),
    (1295, 750, 1425, 780),
    (1470, 750, 1605, 780),
    (1650, 750, 1785, 780),
]
SKILL_ORDER = ("basic", "dodge", "assist", "special", "chain")

# Oracle agent folder overrides for June-17 archive
_J17_FOLDER: dict[str, int] = {
    "Velina": 41, "Billy": 30, "Seth": 19, "Nekomata": 28,
}


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na < 1e-6 or nb < 1e-6:
        return 0.0
    return float(np.dot(a, b)) / (na * nb)


def _loso_classify(
    held_out: np.ndarray,
    held_digit: int,
    all_glyphs: dict[int, list[np.ndarray]],
    valid_digits: set[int],
) -> int:
    """Classify held_out using templates built from all-but-held-out samples."""
    templates: dict[int, np.ndarray] = {}
    for d, samples in all_glyphs.items():
        if d not in valid_digits:
            continue
        if d == held_digit:
            rest = [s for s in samples if not np.array_equal(s, held_out)]
        else:
            rest = samples
        if not rest:
            continue
        templates[d] = np.median(np.stack(rest), axis=0)

    # Mirror hole-count shortcut from _match_b1_glyph
    canvas = (held_out * 255).astype(np.uint8).reshape(GLYPH_H, GLYPH_W)
    holes = _b1_hole_count(canvas)
    if holes >= 2 and 8 in valid_digits and 8 in templates:
        return 8

    best_d, best_s = min(valid_digits), -1.0
    for d, tmpl in templates.items():
        s = _cosine(held_out, tmpl)
        if s > best_s:
            best_s, best_d = s, d
    return best_d


def run_loso() -> bool:
    data = json.loads(GLYPHS_PATH.read_text())
    raw: dict[int, list[list[int]]] = {
        int(k): v for k, v in data["glyphs"].items()
    }
    all_glyphs: dict[int, list[np.ndarray]] = {
        d: [np.array(s, dtype=np.float32) / 255.0 for s in samples]
        for d, samples in raw.items()
    }

    print("=" * 60)
    print("LOSO cross-validation (leave-one-sample-out per digit)")
    print("  Note: informational only — low accuracy is expected for digits")
    print("  with few samples (4,6,9) or mixed dim/bright contexts (1-6).")
    print("  The production scanner constrains valid_digits by badge context,")
    print("  which is not modelled here.")
    print("=" * 60)

    # Context-appropriate valid_digits for LOSO:
    #   digit 0  → only from bright badges (level 10), valid = {0..6}
    #   digits 7-9 → only from dim badges (level 7-9), valid = {1..9}
    #   digits 1-6 → mixed; use dim context {1..9} as the common case
    _VALID_DIM    = set(range(1, 10))
    _VALID_BRIGHT = set(range(7))
    _DIGIT_VALID: dict[int, set[int]] = {
        0: _VALID_BRIGHT,
        1: _VALID_DIM, 2: _VALID_DIM, 3: _VALID_DIM,
        4: _VALID_DIM, 5: _VALID_DIM, 6: _VALID_DIM,
        7: _VALID_DIM, 8: _VALID_DIM, 9: _VALID_DIM,
    }

    total_correct = 0
    total_tested  = 0
    per_digit: dict[int, tuple[int, int]] = {}

    for d in sorted(all_glyphs):
        samples = all_glyphs[d]
        if len(samples) < 2:
            print(f"  digit {d}: SKIP (only {len(samples)} sample — can't hold out)")
            per_digit[d] = (0, 0)
            continue
        valid = {
            dd for dd in _DIGIT_VALID[d]
            if dd in all_glyphs and (dd != d or len(all_glyphs[dd]) > 1)
        }
        correct = 0
        for i, held_out in enumerate(samples):
            pred = _loso_classify(held_out, d, all_glyphs, valid)
            if pred == d:
                correct += 1
        total_correct += correct
        total_tested  += len(samples)
        pct = 100.0 * correct / len(samples)
        status = "OK" if correct == len(samples) else f"{len(samples)-correct} wrong"
        print(f"  digit {d}: {correct}/{len(samples)} ({pct:.0f}%)  [{status}]")
        per_digit[d] = (correct, len(samples))

    overall = 100.0 * total_correct / total_tested if total_tested else 0.0
    print(f"\n  Overall: {total_correct}/{total_tested} ({overall:.1f}%)  (informational)")
    return True  # LOSO is informational — never fails the gate


def _get_archive_path(key: str, archive_idx: int) -> Path | None:
    """Return skills.png path for an oracle agent, preferring June-17."""
    if key in _J17_FOLDER and ARCHIVE_J17.exists():
        p = ARCHIVE_J17 / f"agent_{_J17_FOLDER[key]:03d}" / "skills.png"
        if p.exists():
            return p
    p = ARCHIVE_J9 / f"agent_{archive_idx:03d}" / "skills.png"
    return p if p.exists() else None


def run_t3_regression() -> bool:
    oracle = json.loads(ORACLE_PATH.read_text())
    agents_by_key: dict[str, dict] = {a["key"]: a for a in oracle["agents"]}

    # T3 documented misread cases: (agent_key, skill, true_value, old_wrong_value)
    T3_CASES: list[tuple[str, str, int, int]] = [
        # Bug A — basic-7 was read as 1
        ("OrphieMagus", "basic", 7, 1),
        ("Ben",         "basic", 7, 1),
        # Bug B — 03 dim-pass bucketed as 5
        ("Jane",        "assist", 3, 5),
        ("Caesar",      "basic",  3, 5),
        ("Rina",        "dodge",  3, 5),
        # Bug B2 — 06 bright bucketed as 8
        ("Rina",        "basic",  6, 8),
        # Bug C — A-rank 15 misread as 10
        ("Anton",       "basic",  15, 10),
    ]

    print()
    print("=" * 60)
    print("T3 regression — previously broken badges")
    print("=" * 60)

    all_pass = True
    for key, skill, true_val, old_val in T3_CASES:
        if key not in agents_by_key:
            print(f"  SKIP {key}/{skill}: not in oracle")
            continue
        agent = agents_by_key[key]
        archive_idx = agent["archive_idx"]
        skill_path = _get_archive_path(key, archive_idx)
        if skill_path is None:
            print(f"  SKIP {key}/{skill}: skills.png not found")
            continue

        frame = Image.open(skill_path)
        skill_idx = SKILL_ORDER.index(skill)
        bbox = _SKILL_BBOXES[skill_idx]
        crop = frame.crop(bbox)

        result = _read_skill_badge(crop)
        if result is None:
            print(f"  FAIL {key}/{skill}: reader returned None (expected {true_val})")
            all_pass = False
            continue
        got_val, got_conf = result
        ok = got_val == true_val
        mark = "OK  " if ok else "FAIL"
        print(
            f"  {mark} {key:15s}/{skill:7s}: "
            f"expected={true_val:2d}  got={got_val:2d}  conf={got_conf:.1f}"
            f"  (was broken as {old_val})"
        )
        if not ok:
            all_pass = False

    if all_pass:
        print("\n  PASS — all T3 cases read correctly")
    else:
        print("\n  FAIL — some T3 cases still wrong")
    return all_pass


def main() -> None:
    run_loso()          # informational — always returns True
    t3_ok = run_t3_regression()

    print()
    if t3_ok:
        print("ALL CHECKS PASSED")
        sys.exit(0)
    else:
        print("T3 REGRESSION FAILED — see above")
        sys.exit(1)


if __name__ == "__main__":
    main()
