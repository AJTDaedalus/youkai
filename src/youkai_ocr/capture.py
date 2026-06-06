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
from typing import Callable, Optional

import numpy as np
from PIL import Image

REFERENCE_W = 1920
REFERENCE_H = 1080
REFERENCE_ASPECT = REFERENCE_W / REFERENCE_H  # 1.7777…  (16:9)
ASPECT_TOLERANCE = 0.01  # ±1% before rejection

GAME_TITLE = "ZenlessZoneZero"


@dataclass(frozen=True)
class CalibrationResult:
    """Transform from a captured game frame to 1920×1080 reference coordinates.

    All bboxes in navigation.yaml use reference coordinates. Multiply by scale
    and add the window offset to get absolute screen coordinates for input.
    """

    scale_x: float  # frame_width / 1920
    scale_y: float  # frame_height / 1080
    frame_width: int
    frame_height: int
    window_left: int = 0  # screen x of game client area top-left
    window_top: int = 0   # screen y of game client area top-left

    @property
    def is_identity(self) -> bool:
        return self.frame_width == REFERENCE_W and self.frame_height == REFERENCE_H

    def to_frame(self, ref_x: int, ref_y: int) -> tuple[int, int]:
        """Convert reference coords to frame pixel coords (no window offset)."""
        return (round(ref_x * self.scale_x), round(ref_y * self.scale_y))

    def to_screen(self, ref_x: int, ref_y: int) -> tuple[int, int]:
        """Convert reference coords to absolute screen coords for mouse input."""
        return (
            round(ref_x * self.scale_x) + self.window_left,
            round(ref_y * self.scale_y) + self.window_top,
        )

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

    Does NOT set window_left/window_top — use calibrate_window() when you need
    mouse input coordinates.

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


def _find_game_window() -> Optional[tuple[int, int, int, int, int]]:
    """Return (left, top, right, bottom, hwnd) screen coords + handle, or None."""
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
        return (left, top, right, bottom, hwnd)
    except Exception:
        return None


def focus_game_window() -> bool:
    """Bring the ZZZ window to the foreground so it receives input events.

    Returns True if focus was successfully set, False if the window wasn't found
    or the OS denied the SetForegroundWindow call.
    """
    result = _find_game_window()
    if result is None:
        return False
    *_, hwnd = result
    try:
        import win32gui
        # AllowSetForegroundWindow lets a background process steal foreground.
        ctypes.windll.user32.AllowSetForegroundWindow(ctypes.windll.kernel32.GetCurrentProcessId())
        win32gui.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def _require_window() -> tuple[int, int, int, int]:
    """Return (left, top, right, bottom) client-area screen coords or raise."""
    if sys.platform != "win32":
        raise RuntimeError("Window capture is only supported on Windows.")
    result = _find_game_window()
    if result is None:
        raise RuntimeError(
            f'Game window "{GAME_TITLE}" not found. '
            "Ensure the game is running in Windowed (not Borderless / Fullscreen) mode."
        )
    left, top, right, bottom, _hwnd = result
    w, h = right - left, bottom - top
    aspect = w / h
    if abs(aspect - REFERENCE_ASPECT) > ASPECT_TOLERANCE:
        raise ValueError(
            f"Game window is {w}×{h} ({aspect:.4f}); expected 16:9. "
            "Change the in-game resolution to a 16:9 value (e.g. 1920×1080)."
        )
    return (left, top, right, bottom)


_dxcam_camera = None  # module-level singleton; created once, reused for the session


def _grab_region(region: tuple[int, int, int, int]) -> Image.Image:
    """Capture a screen region. Tries dxcam first, falls back to PIL.ImageGrab."""
    global _dxcam_camera
    left, top, right, bottom = region
    try:
        import dxcam
        if _dxcam_camera is None:
            _dxcam_camera = dxcam.create(output_color="RGB")
        frame_np = _dxcam_camera.grab(region=(left, top, right, bottom))
        if frame_np is not None:
            return Image.fromarray(frame_np, "RGB")
    except Exception:
        pass
    from PIL import ImageGrab
    return ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True).convert("RGB")


def grab_window() -> Image.Image:
    """Capture the ZZZ game window client area as a PIL RGB Image.

    Raises RuntimeError if the game window cannot be found.
    Raises ValueError  if the window's aspect ratio is not 16:9.
    """
    return _grab_region(_require_window())


def calibrate_window() -> tuple[CalibrationResult, Callable[[], Image.Image]]:
    """Locate the game window, build a CalibrationResult with screen offset baked in,
    and return a capture function bound to that window region.

    Use this instead of grab_window() + calibrate() for any scan that issues
    mouse clicks — CalibrationResult.to_screen() needs window_left/window_top.
    """
    region = _require_window()
    left, top, right, bottom = region
    w, h = right - left, bottom - top
    calib = CalibrationResult(
        scale_x=w / REFERENCE_W,
        scale_y=h / REFERENCE_H,
        frame_width=w,
        frame_height=h,
        window_left=left,
        window_top=top,
    )
    capture_fn: Callable[[], Image.Image] = lambda: _grab_region(region)
    return calib, capture_fn
