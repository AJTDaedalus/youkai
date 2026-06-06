"""B3: Color-sample and text-pattern recognizers.

detect_rarity   — rarity badge color → int (4=S, 3=A, 2=B)
detect_lock_from_text — OCR text of thumbnail level strip → bool
"""
from __future__ import annotations

import re

import numpy as np
from PIL import Image

# Color centroids in RGB (from navigation.yaml rarity_badge.colors).
# 4 = S-rank gold, 3 = A-rank purple, 2 = B-rank blue.
_RARITY_CENTROIDS: dict[int, np.ndarray] = {
    4: np.array([245, 200, 33], dtype=float),   # S-rank gold
    3: np.array([160, 80, 220], dtype=float),   # A-rank purple
    2: np.array([80, 140, 200], dtype=float),   # B-rank blue
}

# Maximum Euclidean distance to accept a rarity match.
_RARITY_THRESHOLD = 80.0

# Lock indicator: "L" after digit(s) in thumbnail level text.
_LOCK_RE = re.compile(r"\d\s+L\b", re.IGNORECASE)


def detect_rarity(sample: Image.Image) -> int:
    """Identify rarity from a small color-sample crop of the rarity badge.

    Returns 4 (S-rank), 3 (A-rank), or 2 (B-rank).
    Raises ValueError if no centroid is within the distance threshold.
    """
    arr = np.array(sample.convert("RGB"), dtype=float).reshape(-1, 3)
    # Use 75th percentile to sample the bright badge color while ignoring dark
    # pixels from internal design elements (disc art, shadows).
    sample_color = np.percentile(arr, 75, axis=0)

    best, best_dist = 2, float("inf")
    for rarity, centroid in _RARITY_CENTROIDS.items():
        dist = float(np.linalg.norm(sample_color - centroid))
        if dist < best_dist:
            best_dist = dist
            best = rarity

    if best_dist > _RARITY_THRESHOLD:
        raise ValueError(
            f"Rarity unrecognized: p75 RGB {tuple(sample_color.astype(int))}, "
            f"nearest dist={best_dist:.1f} > threshold {_RARITY_THRESHOLD}"
        )
    return best


def count_filled_stars(crop: Image.Image) -> int:
    """Count filled (gold) refinement stars in a horizontal star-strip crop.

    Divides the crop into 5 equal columns and checks each for gold-coloured pixels.
    Gold stars have high red channel and significantly higher red than blue.
    Returns 1–5 (refinement level). Falls back to 1 if none detected.
    """
    arr = np.array(crop.convert("RGB"), dtype=float)
    w = arr.shape[1]
    section_w = max(1, w // 5)
    count = 0
    for i in range(5):
        section = arr[:, i * section_w : (i + 1) * section_w, :]
        mean_r = float(np.mean(section[:, :, 0]))
        mean_b = float(np.mean(section[:, :, 2]))
        if mean_r > 180 and mean_r > mean_b + 80:
            count += 1
    return max(1, count)


def detect_lock_from_text(level_text: str) -> bool:
    """Return True if the thumbnail OCR text contains the lock indicator.

    Locked discs/engines show 'Lv. 15 L' in the thumbnail; unlocked show 'Lv. 4'.
    """
    return bool(_LOCK_RE.search(level_text))
