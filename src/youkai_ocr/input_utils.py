"""Natural mouse input — smooth Bezier movement + timing jitter.

All scanners use natural_click() and jitter() from here instead of
teleporting the cursor or using fixed delays.
"""

from __future__ import annotations

import math
import random
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pynput.mouse import Controller


def jitter(base: float, frac: float = 0.25) -> float:
    """Return base ± frac*base, uniformly distributed."""
    return base * random.uniform(1.0 - frac, 1.0 + frac)


def _bezier_path(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    steps: int = 30,
    curve_mag: float = 0.15,
) -> list[tuple[int, int]]:
    """Quadratic Bezier path from (x0,y0) to (x1,y1) with a slight lateral curve."""
    dx, dy = x1 - x0, y1 - y0
    dist = math.hypot(dx, dy)
    if dist < 1:
        return [(int(x1), int(y1))]

    # Control point: midpoint + random perpendicular offset
    side = random.choice((-1, 1))
    perp_x = (-dy / dist) * dist * curve_mag * side
    perp_y = (dx / dist) * dist * curve_mag * side
    cx = (x0 + x1) / 2 + perp_x
    cy = (y0 + y1) / 2 + perp_y

    path: list[tuple[int, int]] = []
    for i in range(steps + 1):
        t = i / steps
        bx = (1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t**2 * x1
        by = (1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t**2 * y1
        path.append((int(bx), int(by)))
    return path


def natural_click(
    mouse: Controller,
    target_x: int,
    target_y: int,
    jitter_px: int = 3,
) -> None:
    """Move to (target_x, target_y) along a Bezier curve then click.

    Never lands on the exact target pixel — adds ±jitter_px randomness,
    uses smooth path movement (not teleport), and randomizes press/release
    duration so timing is indistinguishable from manual clicking.
    """
    from pynput.mouse import Button

    tx = target_x + random.randint(-jitter_px, jitter_px)
    ty = target_y + random.randint(-jitter_px, jitter_px)

    cur_x, cur_y = mouse.position
    dist = math.hypot(tx - cur_x, ty - cur_y)

    # Movement duration scales with sqrt(distance): ~50ms short, ~150ms long.
    duration = min(0.15, max(0.05, 0.007 * math.sqrt(dist)))
    steps = max(15, int(dist / 8))
    path = _bezier_path(cur_x, cur_y, tx, ty, steps=steps)

    step_sleep = duration / max(len(path), 1)
    for px, py in path:
        mouse.position = (px, py)
        time.sleep(step_sleep)

    # Settle, then press+hold+release
    time.sleep(jitter(0.018, 0.30))
    mouse.press(Button.left)
    time.sleep(jitter(0.045, 0.30))
    mouse.release(Button.left)
