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
from typing import Callable, Iterable, Optional

import numpy as np
from PIL import Image

REFERENCE_W = 1920
REFERENCE_H = 1080
REFERENCE_ASPECT = REFERENCE_W / REFERENCE_H  # 1.7777…  (16:9)
ASPECT_TOLERANCE = 0.01  # ±1% before rejection

DEFAULT_GAME_TITLES: tuple[str, ...] = ("ZenlessZoneZero", "chiaki-ng")

# Module-level accepted title list; replaced by set_accepted_titles() in main()
# before any capture call.  Starts equal to DEFAULT_GAME_TITLES so the module
# works correctly when imported without going through the CLI entry point.
_accepted_titles: tuple[str, ...] = DEFAULT_GAME_TITLES


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


# A5/F2 color-hygiene preflight: minimum bright-pixel channel-balance ratio.
# Clean ZZZ UI frames measure ≥0.96 (white text/chrome is neutral); a Night
# Light / f.lux warm shift measures ~0.62. 0.85 splits with wide margin.
_COLOR_BALANCE_MIN = 0.85


def check_color_hygiene(frame: Image.Image) -> None:
    """Raise ValueError if the frame looks color-shifted (negative control, F2).

    Night Light / f.lux / Reshade / driver filters suppress the blue channel;
    rarity color-matching and Otsu thresholds silently degrade under them.
    Samples the brightest 1% of pixels — game UI text/chrome is neutral white
    on every scanned screen — and requires near-equal RGB channel means.
    """
    arr = np.asarray(frame.convert("RGB"), dtype=np.float64).reshape(-1, 3)
    lum = arr.mean(axis=1)
    bright = arr[lum >= np.percentile(lum, 99)]
    means = bright.mean(axis=0)
    ratio = float(means.min() / max(means.max(), 1.0))
    if ratio < _COLOR_BALANCE_MIN:
        r, g, b = (int(v) for v in means)
        raise ValueError(
            f"Frame looks color-shifted: bright-pixel RGB means ({r},{g},{b}), "
            f"balance {ratio:.2f} < {_COLOR_BALANCE_MIN}. Disable Night Light / "
            "f.lux / color filters (HDR off, sRGB) and rescan."
        )


# ── Windows-only capture ──────────────────────────────────────────────────────

class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def _normalize_title(s: str) -> str:
    """Lowercase, strip whitespace — so "Zenless Zone Zero" == "ZenlessZoneZero"."""
    return "".join(s.lower().split())


def title_matches(window_title: str, accepted: "Iterable[str]") -> bool:
    """Return True if any accepted title is a normalized substring of window_title.

    Pure function — no module state; unit-testable without a live window.
    Case-insensitive, whitespace-insensitive (reuses _normalize_title).
    """
    norm = _normalize_title(window_title)
    return any(_normalize_title(t) in norm for t in accepted)


def resolve_accepted_titles(
    extra: "Iterable[str] | None" = None,
    env: "str | None" = None,
) -> "tuple[str, ...]":
    """Build the accepted-titles tuple from defaults + env var + extra iterable.

    Merge order (lowest → highest priority, all merged as a union):
      1. DEFAULT_GAME_TITLES
      2. comma-split env string (e.g. YOUKAI_WINDOW_TITLES="A,B")
      3. extra iterable (CLI --window-title values)

    Dedupes preserving first-seen order; drops blank strings.
    """
    seen: set[str] = set()
    result: list[str] = []
    candidates: list[str] = (
        list(DEFAULT_GAME_TITLES)
        + [s.strip() for s in (env or "").split(",")]
        + list(extra or [])
    )
    for t in candidates:
        if t and t not in seen:
            seen.add(t)
            result.append(t)
    return tuple(result)


def set_accepted_titles(titles: "Iterable[str]") -> None:
    """Replace the module-level accepted-titles list (always unions in defaults).

    Call this once in main() after parsing args; all capture functions read
    the module state so no signature changes are needed throughout the call graph.
    """
    global _accepted_titles
    # resolve_accepted_titles always starts with DEFAULT_GAME_TITLES, so the
    # passed iterable is merged on top of the built-in defaults.
    _accepted_titles = resolve_accepted_titles(extra=titles)


def get_accepted_titles() -> "tuple[str, ...]":
    """Return the current module-level accepted-titles tuple."""
    return _accepted_titles


def list_game_windows() -> list[dict]:
    """All visible, non-minimized, non-zero-client windows matching the game title.

    Passive window-metadata enumeration only (EnumWindows / GetWindowText /
    GetClientRect / ClientToScreen) — no process or memory access.  Each entry:
        {hwnd, title, left, top, right, bottom, w, h, aspect, is_16_9}

    The game spawns several windows sharing the title (incl. hidden 0×0 helpers),
    and the launcher matches too — so callers must pick, not take the first.
    """
    out: list[dict] = []
    if sys.platform != "win32":
        return out
    try:
        import win32gui  # pywin32
    except Exception:
        return out

    def _cb(hwnd, _extra):
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return
            if win32gui.IsIconic(hwnd):           # minimized → 0×0 client rect
                return
            title = win32gui.GetWindowText(hwnd)
            if not title_matches(title, get_accepted_titles()):
                return
            _, _, cw, ch = win32gui.GetClientRect(hwnd)   # (0, 0, w, h)
            if cw <= 0 or ch <= 0:                # hidden/message-only helper window
                return
            pt = _POINT(0, 0)
            ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(pt))
            out.append({
                "hwnd": hwnd, "title": title,
                "left": pt.x, "top": pt.y, "right": pt.x + cw, "bottom": pt.y + ch,
                "w": cw, "h": ch, "aspect": cw / ch,
                "is_16_9": abs(cw / ch - REFERENCE_ASPECT) <= ASPECT_TOLERANCE,
            })
        except Exception:
            return  # skip any window that errors; keep enumerating

    try:
        win32gui.EnumWindows(_cb, None)
    except Exception:
        pass
    return out


def list_all_windows() -> list[dict]:
    """All visible, non-minimized, non-zero-client top-level windows — no title filter.

    Same passive enumeration as list_game_windows() but returns every window,
    not just those matching the accepted-titles list.  Used by the ``windows``
    discovery subcommand so users can find the exact title of a non-default client
    (e.g. a custom chiaki-ng build with a different window title).

    Returns [] on non-win32 platforms (mirrors list_game_windows behaviour).
    """
    out: list[dict] = []
    if sys.platform != "win32":
        return out
    try:
        import win32gui  # pywin32
    except Exception:
        return out

    def _cb(hwnd, _extra):
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return
            if win32gui.IsIconic(hwnd):
                return
            title = win32gui.GetWindowText(hwnd)
            _, _, cw, ch = win32gui.GetClientRect(hwnd)
            if cw <= 0 or ch <= 0:
                return
            pt = _POINT(0, 0)
            ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(pt))
            out.append({
                "hwnd": hwnd, "title": title,
                "left": pt.x, "top": pt.y, "right": pt.x + cw, "bottom": pt.y + ch,
                "w": cw, "h": ch, "aspect": cw / ch,
                "is_16_9": abs(cw / ch - REFERENCE_ASPECT) <= ASPECT_TOLERANCE,
            })
        except Exception:
            return

    try:
        win32gui.EnumWindows(_cb, None)
    except Exception:
        pass
    return out


def pick_best_window(cands: list[dict]) -> Optional[dict]:
    """Choose the real render surface from same-title candidates: 16:9 first, then
    largest area.  Skips the hidden 0×0 helpers and the non-16:9 launcher window."""
    if not cands:
        return None
    return sorted(cands, key=lambda c: (0 if c["is_16_9"] else 1, -(c["w"] * c["h"])))[0]


def _find_game_window() -> Optional[tuple[int, int, int, int, int]]:
    """Return (left, top, right, bottom, hwnd) for the best game window, or None."""
    best = pick_best_window(list_game_windows())
    if best is None:
        return None
    return (best["left"], best["top"], best["right"], best["bottom"], best["hwnd"])


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
        titles_str = ", ".join(f'"{t}"' for t in get_accepted_titles())
        raise RuntimeError(
            f"Game window not found (accepted titles: {titles_str}; "
            "no visible, non-minimized window with a renderable client area). "
            "Ensure the game is running in Windowed (not Borderless / Fullscreen) "
            "mode and is not minimized."
        )
    left, top, right, bottom, _hwnd = result
    w, h = right - left, bottom - top
    if w <= 0 or h <= 0:    # defensive; list_game_windows already filters these out
        raise RuntimeError(
            f"Game window has a zero-size client area ({w}×{h}) — it is minimized or "
            "still loading. Restore the window and retry."
        )
    aspect = w / h
    if abs(aspect - REFERENCE_ASPECT) > ASPECT_TOLERANCE:
        others = [c for c in list_game_windows() if c["is_16_9"]]
        hint = (f" A 16:9 candidate does exist ({others[0]['w']}×{others[0]['h']}) — "
                "another same-title window was picked; close the launcher." if others else
                " Change the in-game resolution to a 16:9 value (e.g. 1920×1080).")
        raise ValueError(f"Game window is {w}×{h} ({aspect:.4f}); expected 16:9.{hint}")
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
    try:
        return ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True).convert("RGB")
    except OSError as e:
        raise RuntimeError(
            f"Screen capture failed (PIL.ImageGrab region=({left},{top},{right},{bottom}) "
            f"size={right-left}x{bottom-top}): {e}. "
            "If DPI scaling is not 100%, try setting Display Scale to 100% in Windows Settings, "
            "or run the CLI directly from a terminal."
        ) from e


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
