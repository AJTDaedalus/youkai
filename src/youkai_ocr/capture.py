"""Window capture and calibration for ZZZ OCR scanner.

Responsibilities:
- Locate the ZZZ game window by title (Windows only, via win32gui)
- Grab a single frame of the game client area via dxcam (DXGI) or PIL.ImageGrab fallback
- Given any 16:9 game frame, compute scale against the 1920×1080 reference layout
- Reject unsupported aspect ratios with a clear error message
"""
from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass
from typing import Optional

import numpy as np
from PIL import Image

REFERENCE_W = 1920
REFERENCE_H = 1080
REFERENCE_ASPECT = REFERENCE_W / REFERENCE_H  # 1.7777…  (16:9)
ASPECT_TOLERANCE = 0.01  # ±1% before rejection

GAME_TITLE = "Zenless Zone Zero"


@dataclass(frozen=True)
class CalibrationResult:
    """Transform from a captured game frame to 1920×1080 reference coordinates.

    All bboxes in navigation.yaml use reference coordinates. Multiply by scale
    to get the corresponding pixel coordinates in the captured frame.
    """

    scale_x: float  # frame_width / 1920
    scale_y: float  # frame_height / 1080
    frame_width: int
    frame_height: int

    @property
    def is_identity(self) -> bool:
        return self.frame_width == REFERENCE_W and self.frame_height == REFERENCE_H

    def to_frame(self, ref_x: int, ref_y: int) -> tuple[int, int]:
        """Convert reference 1920×1080 coords to this frame's pixel coords."""
        return (round(ref_x * self.scale_x), round(ref_y * self.scale_y))

    def scale_bbox(self, bbox: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        """Scale a reference bbox (x1, y1, x2, y2) to frame pixel coords."""
        x1, y1, x2, y2 = bbox
        return (
            round(x1 * self.scale_x),
            round(y1 * self.scale_y),
            round(x2 * self.scale_x),
            round(y2 * self.scale_y),
        )


def calibrate(frame: "Image.Image | np.ndarray") -> CalibrationResult:
    """Compute scale from a game client-area frame against the 1920×1080 reference.

    The frame must contain only the game client area — OS window chrome must be
    stripped before calling this. grab_window() handles that automatically.

    Raises ValueError if the aspect ratio is not 16:9 (e.g. ultrawide, portrait).
    """
    if isinstance(frame, np.ndarray):
        h, w = frame.shape[:2]
    else:
        w, h = frame.size

    aspect = w / h
    if abs(aspect - REFERENCE_ASPECT) > ASPECT_TOLERANCE:
        raise ValueError(
            f"Unsupported aspect ratio {w}×{h} ({aspect:.4f}); "
            f"expected 16:9 ({REFERENCE_ASPECT:.4f}). "
            "Set the game to a 16:9 windowed resolution (e.g. 1920×1080 or 1600×900)."
        )

    return CalibrationResult(
        scale_x=w / REFERENCE_W,
        scale_y=h / REFERENCE_H,
        frame_width=w,
        frame_height=h,
    )


# ── Windows-only capture ──────────────────────────────────────────────────────

class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def _find_game_window() -> Optional[tuple[int, int, int, int]]:
    """Return (left, top, right, bottom) screen coords of the ZZZ client area, or None."""
    try:
        import win32gui  # pywin32

        hwnd = win32gui.FindWindow(None, GAME_TITLE)
        if not hwnd:
            return None

        # GetClientRect → (0, 0, w, h) relative to client origin.
        client_rect = win32gui.GetClientRect(hwnd)
        pt = _POINT(0, 0)
        ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(pt))

        left = pt.x
        top = pt.y
        right = left + client_rect[2]
        bottom = top + client_rect[3]
        return (left, top, right, bottom)
    except Exception:
        return None


def grab_window() -> Image.Image:
    """Capture the ZZZ game window client area as a PIL RGB Image.

    Uses dxcam (DXGI Desktop Duplication) on first attempt; falls back to
    PIL.ImageGrab if dxcam is unavailable or returns no frame.

    Raises RuntimeError if the game window cannot be found.
    Raises ValueError  if the window's aspect ratio is not 16:9.
    """
    if sys.platform != "win32":
        raise RuntimeError("Window capture is only supported on Windows.")

    region = _find_game_window()
    if region is None:
        raise RuntimeError(
            f'Game window "{GAME_TITLE}" not found. '
            "Ensure the game is running in Windowed (not Borderless / Fullscreen) mode."
        )

    left, top, right, bottom = region
    w, h = right - left, bottom - top

    # Pre-validate aspect ratio so the error message is clear before any capture attempt.
    aspect = w / h
    if abs(aspect - REFERENCE_ASPECT) > ASPECT_TOLERANCE:
        raise ValueError(
            f"Game window is {w}×{h} ({aspect:.4f}); expected 16:9. "
            "Change the in-game resolution to a 16:9 value (e.g. 1920×1080)."
        )

    # Try dxcam (DXGI — handles hardware-accelerated / Flip-Model surfaces).
    try:
        import dxcam

        camera = dxcam.create(output_color="RGB")
        frame_np = camera.grab(region=(left, top, right, bottom))
        camera.release()
        if frame_np is not None:
            return Image.fromarray(frame_np, "RGB")
    except Exception:
        pass

    # Fallback: GDI-based grab via PIL.
    from PIL import ImageGrab

    img = ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)
    return img.convert("RGB")
