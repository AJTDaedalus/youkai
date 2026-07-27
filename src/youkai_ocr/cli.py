"""Entry point: youkai-ocr --help"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image

    from .capture import CalibrationResult
    from .zod import ZodDisc, ZodWEngine


# ── Screen assertion error ────────────────────────────────────────────────────


class ScreenAssertError(RuntimeError):
    """Raised when the expected game screen is not visible at phase start."""


# ── Auto-nav constants ────────────────────────────────────────────────────────

# Main-hub bottom-nav click targets (game-area coords, 1920×1080).
# Updated 2026-06-15: ZZZ 1.5 added "Achievements" between Notices and Inter-Knot,
# shifting Storage (was 1123→1178) and Agents (was 1251→1274) one slot right.
_NAV_STORAGE_CENTER = (1178, 1041)
_NAV_AGENTS_CENTER = (1274, 1041)

# Click center of each storage tab circle button (horizontal row, measured from
# ref_1/ref_2 active-circle centroids; game-area coords at 1920×1080).
# Both tabs sit at game y≈169; W-Engine is leftmost (x≈1447), Drive Disc is to its right (x≈1535).
# Previous Drive Disc value (1421, 314) was wrong — it clicked the detail panel, not the tab.
_STORAGE_TAB_CLICK_CENTERS: tuple[tuple[int, int], ...] = (
    (1447, 169),  # W-Engine
    (1535, 169),  # Drive Disc
)

# Screen-signature parameters (from navigation.yaml screen_signatures, H7a).
_MAIN_MENU_SIG_BBOX = (1000, 1033, 1300, 1050)
_MAIN_MENU_SIG_THRESH = 20  # mean_luma > this → main menu

_AGENT_MENU_SIG_BBOX = (1888, 430, 1920, 570)
_AGENT_MENU_SIG_THRESH = 1000  # teal_pixel_count > this → agent selection menu
# teal: G−R>30 AND G>100

_SCREEN_TIMEOUT_S = 8.0  # max seconds to wait for a screen transition
_SCREEN_POLL_S = 0.3  # poll interval inside wait_for
_NAV_SETTLE_S = 0.5  # post-click settle before polling begins

# Bottom-nav OCR-locate parameters (game-area coords, 1920×1080).
# Crop band covers the text-label row of all bottom-nav icons.
_NAV_OCR_BAND = (900, 1015, 1400, 1062)
_NAV_OCR_UPSCALE = 3
_NAV_OCR_THRESH = 90


# ── Screen predicates ─────────────────────────────────────────────────────────


def _is_main_menu(frame: Image.Image, calib) -> bool:
    """True when the bottom navigation strip (main-hub signature) is visible."""
    import numpy as np

    arr = np.array(frame)
    x1, y1, x2, y2 = calib.scale_bbox(_MAIN_MENU_SIG_BBOX)
    region = arr[y1:y2, x1:x2]
    if region.size == 0:
        return False
    luma = (
        0.299 * region[..., 0].mean()
        + 0.587 * region[..., 1].mean()
        + 0.114 * region[..., 2].mean()
    )
    return float(luma) > _MAIN_MENU_SIG_THRESH


def _is_agent_selection_menu(frame: Image.Image, calib) -> bool:
    """True when the teal SELECT pill at the right edge of the agent grid is visible."""
    import numpy as np

    arr = np.array(frame)
    x1, y1, x2, y2 = calib.scale_bbox(_AGENT_MENU_SIG_BBOX)
    region = arr[y1:y2, x1:x2]
    if region.size == 0:
        return False
    g = region[..., 1].astype(int)
    rc = region[..., 0].astype(int)
    teal_count = int(((g - rc > 30) & (g > 100)).sum())
    return teal_count > _AGENT_MENU_SIG_THRESH


def _is_storage_screen(frame: Image.Image, calib) -> bool:
    """True when the Storage inventory is open (any tab has a visible glow)."""
    try:
        active_storage_tab(frame, calib)
        return True
    except ScreenAssertError:
        return False


def locate_bottom_nav_button(
    frame: Image.Image,
    calib,
    label: str,
) -> tuple[int, int] | None:
    """OCR the bottom-nav strip and return the ref-coord center of the named button.

    label must be "storage" or "agents" (case-insensitive).
    Returns None if the word is not found (non-main-menu frame or OCR miss) so
    callers can fall back to hard-coded constants.
    """
    import cv2
    import numpy as np
    import pytesseract

    from youkai_ocr.recognize import resolve_tesseract

    cmd, tessdata = resolve_tesseract()
    if cmd is not None:
        pytesseract.pytesseract.tesseract_cmd = cmd
    if tessdata is not None:
        import os as _os

        _os.environ["TESSDATA_PREFIX"] = str(tessdata)

    x0, y0, x1, y1 = calib.scale_bbox(_NAV_OCR_BAND)
    arr = np.array(frame)
    crop = arr[y0:y1, x0:x1]
    if crop.size == 0:
        return None

    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY) if crop.ndim == 3 else crop
    h_b, w_b = gray.shape
    up = cv2.resize(
        gray,
        (w_b * _NAV_OCR_UPSCALE, h_b * _NAV_OCR_UPSCALE),
        interpolation=cv2.INTER_CUBIC,
    )
    _, thresh = cv2.threshold(up, _NAV_OCR_THRESH, 255, cv2.THRESH_BINARY)

    from PIL import Image as _PIL

    data = pytesseract.image_to_data(
        _PIL.fromarray(thresh),
        config="--psm 11",
        output_type=pytesseract.Output.DICT,
    )

    target = label.lower()
    for i, word in enumerate(data["text"]):
        if word.lower() == target:
            w_box = data["width"][i]
            h_box = data["height"][i]
            if w_box == 0 or h_box == 0:
                continue
            cx_up = data["left"][i] + w_box / 2
            cy_up = data["top"][i] + h_box / 2
            cx_frame = x0 + cx_up / _NAV_OCR_UPSCALE
            cy_frame = y0 + cy_up / _NAV_OCR_UPSCALE
            ref_x = round(cx_frame / calib.scale_x)
            ref_y = round(cy_frame / calib.scale_y)
            return ref_x, ref_y

    return None


# ── Auto-nav driver ───────────────────────────────────────────────────────────


class _NavDriver:
    """Drives menu-hub navigation for hands-off scan-all (H7c).

    All click coords are in reference game-area pixels; to_screen() converts
    them to absolute screen coords for mouse input.
    """

    def __init__(self, calib, capture_fn, *, archive_dir=None) -> None:
        self._calib = calib
        self._capture_fn = capture_fn
        self._archive_dir = archive_dir
        self._mouse = None
        self._kbd = None

    def _mouse_ctrl(self):
        if self._mouse is None:
            from pynput.mouse import Controller

            self._mouse = Controller()
        return self._mouse

    def _kbd_ctrl(self):
        if self._kbd is None:
            from pynput.keyboard import Controller as KbdController

            self._kbd = KbdController()
        return self._kbd

    def _focus(self) -> None:
        from youkai_ocr.capture import focus_game_window

        focus_game_window()
        time.sleep(0.15)

    def _click(self, ref_x: int, ref_y: int, *, label: str = "") -> None:
        from youkai_ocr.input_utils import natural_click

        sx, sy = self._calib.to_screen(ref_x, ref_y)
        if label:
            print(f"  [auto-nav] → screen ({sx}, {sy})  ref ({ref_x}, {ref_y})", flush=True)
        natural_click(self._mouse_ctrl(), sx, sy)

    def _capture_pre_click(self, name: str) -> Image.Image:
        """Capture the frame before a nav click, optionally archiving it."""
        frame = self._capture_fn()
        if self._archive_dir is not None:
            import pathlib

            p = pathlib.Path(self._archive_dir) / f"nav_pre_{name}.png"
            frame.save(p)
            print(f"  [auto-nav] pre-click frame → {p}", flush=True)
        return frame

    def _press_escape(self) -> None:
        from pynput.keyboard import Key

        kbd = self._kbd_ctrl()
        kbd.press(Key.esc)
        time.sleep(0.05)
        kbd.release(Key.esc)

    def wait_for(
        self,
        check_fn,
        timeout: float = _SCREEN_TIMEOUT_S,
        poll: float = _SCREEN_POLL_S,
    ) -> Image.Image:
        """Poll capture_fn until check_fn(frame, calib) is True; return the frame."""
        deadline = time.time() + timeout
        while True:
            frame = self._capture_fn()
            if check_fn(frame, self._calib):
                return frame
            if time.time() >= deadline:
                raise ScreenAssertError(
                    f"Screen transition did not complete within {timeout:.0f}s."
                )
            time.sleep(poll)

    def navigate_to_storage(self) -> Image.Image:
        from youkai_ocr.input_utils import jitter as _jitter

        self._focus()
        pre = self._capture_pre_click("storage")
        center = locate_bottom_nav_button(pre, self._calib, "storage") or _NAV_STORAGE_CENTER
        print(f"  [auto-nav] clicking Storage at ref {center}…", flush=True)
        self._click(*center, label="Storage")
        time.sleep(_jitter(_NAV_SETTLE_S, 0.2))
        deadline = time.time() + _SCREEN_TIMEOUT_S
        poll = 0
        while True:
            frame = self._capture_fn()
            if _is_storage_screen(frame, self._calib):
                return frame
            if time.time() >= deadline:
                raise ScreenAssertError(
                    f"Storage screen did not appear within {_SCREEN_TIMEOUT_S:.0f}s."
                )
            poll += 1
            if poll % 10 == 0:
                self._focus()
                print("  [auto-nav] re-clicking Storage…", flush=True)
                center = (
                    locate_bottom_nav_button(frame, self._calib, "storage") or _NAV_STORAGE_CENTER
                )
                self._click(*center, label="Storage")
            time.sleep(_SCREEN_POLL_S)

    def switch_storage_tab(self, tab_idx: int, archive_dir=None) -> Image.Image:
        from youkai_ocr.input_utils import jitter as _jitter

        label = ("W-Engine", "Drive Disc")[tab_idx]
        self._focus()
        print(f"  [auto-nav] switching to {label} tab…", flush=True)
        self._click(*_STORAGE_TAB_CLICK_CENTERS[tab_idx])
        time.sleep(_jitter(_NAV_SETTLE_S * 0.6, 0.2))
        deadline = time.time() + _SCREEN_TIMEOUT_S
        poll = 0
        last_frame = None
        while True:
            last_frame = self._capture_fn()
            try:
                if active_storage_tab(last_frame, self._calib) == tab_idx:
                    return last_frame
            except ScreenAssertError:
                pass
            if time.time() >= deadline:
                if last_frame is not None and archive_dir is not None:
                    import pathlib

                    p = pathlib.Path(archive_dir) / f"debug_tab{tab_idx}_timeout.png"
                    last_frame.save(p)
                    print(f"  [auto-nav] debug frame saved → {p}", flush=True)
                raise ScreenAssertError(
                    f"Storage tab {tab_idx} ({label}) did not activate within "
                    f"{_SCREEN_TIMEOUT_S:.0f}s."
                )
            # Re-click every ~3s in case the first click was dropped
            poll += 1
            if poll % 10 == 0:
                self._focus()
                print(f"  [auto-nav] re-clicking {label} tab…", flush=True)
                self._click(*_STORAGE_TAB_CLICK_CENTERS[tab_idx])
            time.sleep(_SCREEN_POLL_S)

    def return_to_main(self) -> Image.Image:
        from youkai_ocr.input_utils import jitter as _jitter

        self._focus()
        self._capture_pre_click("escape")
        print("  [auto-nav] pressing Escape → main menu…", flush=True)
        self._press_escape()
        time.sleep(_jitter(_NAV_SETTLE_S, 0.2))
        return self.wait_for(_is_main_menu)

    def navigate_to_agents(self) -> Image.Image:
        from youkai_ocr.input_utils import jitter as _jitter

        self._focus()
        pre = self._capture_pre_click("agents")
        center = locate_bottom_nav_button(pre, self._calib, "agents") or _NAV_AGENTS_CENTER
        print(f"  [auto-nav] clicking Agents at ref {center}…", flush=True)
        self._click(*center, label="Agents")
        time.sleep(_jitter(_NAV_SETTLE_S, 0.2))
        deadline = time.time() + _SCREEN_TIMEOUT_S
        poll = 0
        while True:
            frame = self._capture_fn()
            if _is_agent_selection_menu(frame, self._calib):
                return frame
            if time.time() >= deadline:
                raise ScreenAssertError(
                    f"Agent selection menu did not appear within {_SCREEN_TIMEOUT_S:.0f}s."
                )
            poll += 1
            if poll % 10 == 0:
                self._focus()
                print("  [auto-nav] re-clicking Agents…", flush=True)
                center = (
                    locate_bottom_nav_button(frame, self._calib, "agents") or _NAV_AGENTS_CENTER
                )
                self._click(*center, label="Agents")
            time.sleep(_SCREEN_POLL_S)


# ── Screen preflight checks ───────────────────────────────────────────────────


def _check_disc_screen(frame: Image.Image, calib, ocr_engine: str = "tesseract") -> None:
    """Raise ScreenAssertError if the Drive Disc inventory is not open."""
    from youkai_ocr.disc_scanner import read_disc_count
    from youkai_ocr.recognize import make_recognizer

    recognizer = make_recognizer(ocr_engine)
    if read_disc_count(frame, calib, recognizer) is None:
        raise ScreenAssertError(
            "Drive Disc inventory not detected — '[N / M]' count header not found.\n"
            "Make sure Drive Disc Storage is open before pressing Enter."
        )


def _check_engine_screen(frame: Image.Image, calib, ocr_engine: str = "tesseract") -> None:
    """Warn (do not abort) if the W-Engine Storage count header isn't readable.

    The scanner handles a missing count via thumb-stop; an abort here just wastes
    the disc phase when the user presses Enter a moment early on the transition.
    """
    from youkai_ocr.recognize import make_recognizer
    from youkai_ocr.wengine_scanner import read_engine_count

    recognizer = make_recognizer(ocr_engine)
    if read_engine_count(frame, calib, recognizer) is None:
        print(
            "  WARNING: W-Engine Storage header not found — '[N / M]' count unreadable.\n"
            "  Continuing with thumb-stop traversal.  Press Esc to abort if wrong screen."
        )


def _check_agent_screen(frame: Image.Image, calib) -> None:
    """Warn (do not abort) if we can't confirm the agent menu is open.

    The H1 grid detector (detect_owned_agent_cells) was retired in H8; the strip-based
    scanner handles wrong screens by finding 0 agents and ring-closing immediately.
    """
    import numpy as np

    arr = np.array(frame)
    mean_luma = float(arr.mean())
    if mean_luma < 5.0:
        print(
            "  WARNING: captured frame is almost black — game may not be visible.\n"
            "  Press Esc to abort if the agent menu is not open."
        )


# ── Stdout tee ────────────────────────────────────────────────────────────────


class _Tee:
    """Duplicate stdout writes to a log file.  Replace sys.stdout on construction;
    restore it on close()."""

    def __init__(self, log_path: Path, *, mirror=None) -> None:
        self._orig = sys.stdout
        self._mirror = mirror if mirror is not None else self._orig
        self._file = log_path.open("w", encoding="utf-8")
        sys.stdout = self  # type: ignore[assignment]

    def write(self, data: str) -> int:
        try:
            self._mirror.write(data)
        except OSError:
            pass
        self._file.write(data)
        return len(data)

    def flush(self) -> None:
        try:
            self._mirror.flush()
        except OSError:
            pass
        self._file.flush()

    def isatty(self) -> bool:
        return hasattr(self._orig, "isatty") and self._orig.isatty()

    def close(self) -> None:
        sys.stdout = self._orig
        self._file.close()


# ── Storage category-tab detection ───────────────────────────────────────────

# Glow-stripe bboxes (game-area coords, x1 y1 x2 y2) for the vertical pill tabs
# at the right edge of the storage panel (game x≈1413-1430).
# Active tab shows a bright stripe; inactive tabs are near-black.
# Tab 0 = W-Engine  (active in ref_2: yellow [213,207,0], luma≈185)
# Tab 1 = Drive Disc (active in ref_1: white [255,255,255], luma≈255)
_STORAGE_TAB_BBOXES: tuple[tuple[int, int, int, int], ...] = (
    (1413, 135, 1430, 203),  # 0: W-Engine
    (1413, 304, 1430, 325),  # 1: Drive Disc
)

# Measured active luma levels: engine≈185, disc≈255.  Inactive ≈ 12–30.
# Any tab with mean_luma > this threshold can be considered active.
STORAGE_TAB_ACTIVE_LUMA = 50


def active_storage_tab(
    frame: Image.Image,
    calib: CalibrationResult,
) -> int:
    """Return the index of the currently active Storage category tab (0-based).

    Samples the glow-stripe bbox for each known tab and returns the index with
    the highest mean luma.  Tab 0 = W-Engine, Tab 1 = Drive Disc.

    Raises ``ScreenAssertError`` if no tab exceeds ``STORAGE_TAB_ACTIVE_LUMA``
    (i.e. the storage screen is probably not open).
    """
    import numpy as np

    arr = np.array(frame)
    best_idx, best_luma = 0, -1.0
    for i, bbox in enumerate(_STORAGE_TAB_BBOXES):
        x1, y1, x2, y2 = calib.scale_bbox(bbox)
        region = arr[y1:y2, x1:x2]
        if region.size == 0:
            continue
        luma = float(
            0.299 * region[..., 0].mean()
            + 0.587 * region[..., 1].mean()
            + 0.114 * region[..., 2].mean()
        )
        if luma > best_luma:
            best_luma = luma
            best_idx = i
    if best_luma < STORAGE_TAB_ACTIVE_LUMA:
        raise ScreenAssertError(
            f"No storage tab glow detected (max mean luma={best_luma:.1f}); "
            "is the Storage inventory open?"
        )
    return best_idx


# ── Helpers shared by all scan commands ──────────────────────────────────────


def _countdown(seconds: int) -> None:
    """Count down, then bring the game window to the foreground."""
    from youkai_ocr.capture import focus_game_window

    for i in range(seconds, 0, -1):
        print(f"  Starting in {i}s...", end="\r", flush=True)
        time.sleep(1)
    focused = focus_game_window()
    time.sleep(0.3)  # let the OS process the foreground change
    status = "game window focused" if focused else "WARNING: could not focus game window"
    print(f"  Scanning... ({status})", flush=True)


def _make_first_item_check(phase: str, *, interactive: bool = True, emitter=None):
    """Return a callback that warns if the first scanned item has uniformly low confidence."""

    def _check(item, conf: dict) -> None:
        # conf doubles as a metadata channel: the scanners stash "_repairs" /
        # "_violations" (lists) and "_fail_reason" / "_error" (strings) next to
        # the per-field confidence floats, and only pop them during export
        # assembly — long after this callback runs.  Strip them before doing any
        # arithmetic or comparison on the values.
        scores = {k: v for k, v in conf.items() if not k.startswith("_")}
        if item is None:
            reason = conf.get("_fail_reason") or conf.get("_error")
            raise RuntimeError(
                f"First {phase} completely failed OCR"
                + (f" ({reason})" if reason else "")
                + ". Check that the game is on the correct screen and the window is "
                "unobscured.\n"
                "Inspect the preflight PNG in your archive dir to see what the scanner captured."
            )
        if not scores:
            return
        mean_conf = sum(scores.values()) / len(scores)
        low_fields = {k: v for k, v in scores.items() if v < 30}
        if mean_conf < 25:
            raise RuntimeError(
                f"First {phase} completely failed OCR (mean confidence {mean_conf:.0f}%). "
                "Check that the game is on the correct screen and the window is unobscured.\n"
                "Inspect the preflight PNG in your archive dir to see what the scanner captured."
            )
        if len(low_fields) >= len(scores) // 2:
            msg = (
                f"First {phase} has low confidence on {len(low_fields)}/{len(scores)} fields: "
                + ", ".join(
                    f"{k}={v:.0f}%" for k, v in sorted(low_fields.items(), key=lambda x: x[1])
                )
                + ". Inspect the preflight PNG in your archive dir."
            )
            if not interactive:
                if emitter is not None:
                    emitter.warning(msg)
                else:
                    print(f"\n  WARNING: {msg}")
                return
            print(
                f"\n  WARNING: first {phase} has low confidence "
                f"on {len(low_fields)}/{len(scores)} fields:"
            )
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
    archive_dir: Path | None,
    phase: str,
    *,
    interactive: bool = True,
    emitter=None,
) -> Image.Image:
    """Capture one frame, run basic sanity checks, save it, and return it.

    Raises RuntimeError if the frame looks unusable (black, wrong size).
    In interactive mode, prompts the user to confirm marginal brightness.
    In non-interactive mode (porcelain), emits a warning event and continues.
    """
    import numpy as np

    frame = capture_fn()

    if archive_dir:
        from PIL import ImageDraw

        from youkai_ocr.grid import DEFAULT_GRID

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

    # A5/F2 negative control: refuse Night-Light/filter-tinted frames outright —
    # color matching (rarity) and Otsu thresholds degrade silently under tint.
    from youkai_ocr.capture import check_color_hygiene

    try:
        check_color_hygiene(frame)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc

    arr = np.array(frame)
    brightness = float(arr.mean())
    print(f"  Frame brightness: {brightness:.1f}/255", end="")

    if brightness < 5:
        print()
        raise RuntimeError(
            f"Captured frame is nearly black (mean brightness {brightness:.1f}). "
            "The game may be minimized, covered, or in fullscreen mode."
        )
    if brightness < 15:
        msg = f"Frame looks very dark (brightness {brightness:.1f}), game may be obscured."
        print(f"  — {msg}")
        if not interactive:
            if emitter is not None:
                emitter.warning(msg)
            return frame
        ans = input("  Continue anyway? [y/N] ").strip().lower()
        if ans != "y":
            raise RuntimeError("Scan aborted by user after dark-frame warning.")
    else:
        print("  — OK")

    return frame


# ── Sub-commands ──────────────────────────────────────────────────────────────


def _cmd_windows(args: argparse.Namespace) -> None:
    """List every visible top-level window and mark which the scanner would pick."""
    from youkai_ocr.capture import (
        get_accepted_titles,
        list_all_windows,
        list_game_windows,
        pick_best_window,
    )

    all_wins = list_all_windows()
    matched = list_game_windows()  # already filtered to accepted titles
    chosen = pick_best_window(matched)

    if sys.platform != "win32":
        print("Window enumeration is only available on Windows.")
        return

    if not all_wins:
        print("No visible windows found (is the desktop accessible?).")
        return

    titles_str = ", ".join(f'"{t}"' for t in get_accepted_titles())
    matched_hwnds = {c["hwnd"] for c in matched}

    print(f"All visible windows ({len(all_wins)} total; accepted titles: {titles_str}):")
    print(f"  {'hwnd':>10}  {'size':>12}  {'ar':>6}  {'position':>16}  title")
    for w in all_wins:
        flag = "16:9" if w["is_16_9"] else f"{w['aspect']:.3f}"
        pos = f"@({w['left']},{w['top']})"
        mark = ""
        if w["hwnd"] in matched_hwnds:
            mark = " [matched]"
        if chosen and w["hwnd"] == chosen["hwnd"]:
            mark = " [matched] <-- scanner pick"
        print(
            f"  {w['hwnd']:>10}  {w['w']}×{w['h']:>4} [{flag:>6}]  {pos:>16}  {w['title']!r}{mark}"
        )

    print()
    if matched:
        print(
            f"{len(matched)} window(s) match the accepted titles; "
            f"scanner would pick hwnd={chosen['hwnd']}."
        )
    else:
        print(
            "No windows match the accepted titles.\n"
            "  Tip: run Chiaki (or your streaming client) and make a note of the\n"
            "  title column above, then pass it to the scanner:\n"
            '    youkai-ocr --window-title "exact title here" calibrate'
        )


def _cmd_calibrate(args: argparse.Namespace) -> None:
    from PIL import Image

    from youkai_ocr.capture import (
        calibrate,
        get_accepted_titles,
        grab_window,
        list_game_windows,
        pick_best_window,
    )

    if args.file:
        frame = Image.open(args.file).convert("RGB")
    else:
        # Show every same-title window so a wrong-window grab is obvious.
        cands = list_game_windows()
        if cands:
            print(f"Matching game windows ({len(cands)} — the scanner picks 16:9, then largest):")
            chosen = pick_best_window(cands)
            for c in cands:
                mark = " <-- chosen" if c["hwnd"] == chosen["hwnd"] else ""
                flag = "16:9" if c["is_16_9"] else f"{c['aspect']:.3f}"
                print(
                    f"  hwnd={c['hwnd']:>10}  {c['w']}×{c['h']} [{flag}]  "
                    f"@({c['left']},{c['top']})  title={c['title']!r}{mark}"
                )
        else:
            titles_str = ", ".join(f'"{t}"' for t in get_accepted_titles())
            print(
                f"No visible, non-minimized game window found matching {titles_str}. "
                "Is the game running in Windowed mode?"
            )
        frame = grab_window()

    result = calibrate(frame)
    print(f"Frame:  {result.frame_width}×{result.frame_height}")
    print(f"Scale:  x={result.scale_x:.4f}  y={result.scale_y:.4f}")
    print(f"Identity: {result.is_identity}")


def _cmd_scan_engines(args: argparse.Namespace) -> None:
    import time

    from PIL import Image

    from youkai_ocr.capture import calibrate, grab_window
    from youkai_ocr.wengine_scanner import export_engines, scan_engines, scan_single_frame_engine

    output = Path(args.output)
    archive_dir = Path(args.archive_dir) if args.archive_dir else None

    if args.file:
        frame = Image.open(args.file).convert("RGB")
        if args.crop:
            x0, y0, x1, y1 = (int(v) for v in args.crop.split(","))
            frame = frame.crop((x0, y0, x1, y1))
        calib = calibrate(frame)
        print(
            f"Offline mode — frame: {frame.width}×{frame.height}, "
            f"scale: {calib.scale_x:.3f}×{calib.scale_y:.3f}"
        )

        if archive_dir:
            archive_dir.mkdir(parents=True, exist_ok=True)
            print(f"Archiving crops to: {archive_dir}")

        t0 = time.perf_counter()
        eng, conf = scan_single_frame_engine(
            frame, calib, archive_dir=archive_dir, engine=args.engine
        )
        elapsed = time.perf_counter() - t0

        print(f"\nExtraction complete ({elapsed:.1f}s)")
        print(f"Confidence: {json.dumps(conf, indent=2)}")

        if eng is None:
            print(
                "\nCRITICAL FAIL — could not extract engine. "
                "Check bboxes and OCR output in archive."
            )
            sys.exit(1)

        print(f"\nEngine: {json.dumps(eng.to_dict(), indent=2)}")
        export_engines([eng], output)
        print(f"\nExported to: {output}")

    else:
        frame = grab_window()
        calib = calibrate(frame)
        print(
            f"Game window found: {frame.width}×{frame.height}, "
            f"scale: {calib.scale_x:.3f}×{calib.scale_y:.3f}"
        )
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

    from youkai_ocr.agent_scanner import export_agents, scan_agents, scan_single_frame_agent
    from youkai_ocr.capture import calibrate, grab_window

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
        print(
            f"Offline mode — frame: {base_frame.width}×{base_frame.height}, "
            f"scale: {calib.scale_x:.3f}×{calib.scale_y:.3f}"
        )

        if archive_dir:
            archive_dir.mkdir(parents=True, exist_ok=True)

        t0 = time.perf_counter()
        agent, conf = scan_single_frame_agent(
            base_frame, skills_frame, calib, ocr_engine=args.engine
        )
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
        print(
            f"Game window found: {frame.width}×{frame.height}, "
            f"scale: {calib.scale_x:.3f}×{calib.scale_y:.3f}"
        )
        capture_fn = grab_window

        print("Starting agent scan. Make sure an agent detail page is open.")
        print("Press Esc at any time to stop.")

        if archive_dir:
            archive_dir.mkdir(parents=True, exist_ok=True)
            print(f"Archiving crops to: {archive_dir}")

        t0 = time.perf_counter()
        agents, issues, _eq_discs, _eq_engines = scan_agents(
            capture_fn=capture_fn,
            calib=calib,
            archive_dir=archive_dir,
            ocr_engine=args.engine,
            debug_overlays=getattr(args, "debug_overlays", False),
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

    from youkai_ocr.capture import calibrate, grab_window
    from youkai_ocr.disc_scanner import export_discs, scan_discs, scan_single_frame

    output = Path(args.output)
    archive_dir = Path(args.archive_dir) if args.archive_dir else None

    if args.file:
        # Offline mode — extracts from a single static frame, no pynput needed.
        frame = Image.open(args.file).convert("RGB")
        if args.crop:
            x0, y0, x1, y1 = (int(v) for v in args.crop.split(","))
            frame = frame.crop((x0, y0, x1, y1))
        calib = calibrate(frame)
        print(
            f"Offline mode — frame: {frame.width}×{frame.height}, "
            f"scale: {calib.scale_x:.3f}×{calib.scale_y:.3f}"
        )

        if archive_dir:
            archive_dir.mkdir(parents=True, exist_ok=True)
            print(f"Archiving crops to: {archive_dir}")

        t0 = time.perf_counter()
        disc, conf = scan_single_frame(frame, calib, archive_dir=archive_dir, engine=args.engine)
        elapsed = time.perf_counter() - t0

        print(f"\nExtraction complete ({elapsed:.1f}s)")
        print(f"Confidence: {json.dumps(conf, indent=2)}")

        if disc is None:
            print(
                "\nCRITICAL FAIL — could not extract disc. Check bboxes and OCR output in archive."
            )
            sys.exit(1)

        print(f"\nDisc: {json.dumps(disc.to_dict(), indent=2)}")
        violations = conf.get("_violations") or []
        if any(v["severity"] == "error" for v in violations):
            print("\nFAILED VALIDATION — disc excluded from export (T13):")
            for v in violations:
                print(
                    f"  {v['field']}: {v['code']} observed={v['observed']} expected={v['expected']}"
                )
            sys.exit(1)
        export_discs([disc], output)
        print(f"\nExported to: {output}")

    else:
        # Live mode — drives the grid navigator with synthetic mouse input.
        # Requires Windows (win32gui / dxcam) and the game window to be open.
        frame = grab_window()
        calib = calibrate(frame)
        print(
            f"Game window found: {frame.width}×{frame.height}, "
            f"scale: {calib.scale_x:.3f}×{calib.scale_y:.3f}"
        )
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


# ── T10: offline archive revalidation ────────────────────────────────────────

# Same 439×770 panel-crop-onto-1920×1080-canvas trick as
# tests/test_golden_replay.py:_panel_to_frame and
# tests/test_disc_scanner.py:_panel_file_to_frame — archived `disc_NNNN/panel.png`
# crops are reference-scale, so an identity CalibrationResult applies unchanged.
_REVALIDATE_PANEL_ORIGIN = (1421, 100)


def _revalidate_panel_to_frame(panel_path):
    from PIL import Image

    panel = Image.open(panel_path).convert("RGB")
    frame = Image.new("RGB", (1920, 1080), color=(0, 0, 0))
    frame.paste(panel, _REVALIDATE_PANEL_ORIGIN)
    return frame


def _cmd_revalidate(args: argparse.Namespace) -> None:
    """T10: replay an archived scan offline through the current validator/repair
    tables and write a corrected export + repair report — no game, no pynput.

    Preserves location/lock by merging from the archive's discs.json on
    matching index (a static panel.png has no thumbnail strip to read lock from).
    """
    from youkai_ocr.capture import CalibrationResult
    from youkai_ocr.disc_rules import evidence_from_conf, validate_disc
    from youkai_ocr.disc_scanner import export_discs, scan_single_frame

    archive_dir = Path(args.archive)
    raw_discs = json.loads((archive_dir / "discs.json").read_text(encoding="utf-8"))
    if args.limit is not None:
        raw_discs = raw_discs[: args.limit]

    calib = CalibrationResult(scale_x=1.0, scale_y=1.0, frame_width=1920, frame_height=1080)

    discs: list[ZodDisc] = []
    disc_reports: list[dict] = []
    clean = repaired = unrepairable = 0

    t0 = time.perf_counter()
    for i, raw in enumerate(raw_discs):
        # T13: a disc that can't be read or doesn't validate is EXCLUDED from
        # the export — a known-wrong value poisons downstream optimizers, and
        # the pre-T13 critical-fail path even passed the *old uncorrected*
        # discs.json entry through. Failed discs live only in the report.
        panel_path = archive_dir / f"disc_{i:04d}" / "panel.png"
        if not panel_path.exists():
            disc_reports.append(
                {
                    "index": i,
                    "status": "missing_panel",
                    "excluded_from_export": True,
                    "disc": raw,
                    "repairs": [],
                    "violations": [],
                }
            )
            unrepairable += 1
            continue

        frame = _revalidate_panel_to_frame(panel_path)
        try:
            disc, conf = scan_single_frame(frame, calib, engine=args.engine)
        except Exception as exc:  # noqa: BLE001 — one bad panel must not abort a 2090-disc sweep
            disc_reports.append(
                {
                    "index": i,
                    "status": "critical_fail",
                    "excluded_from_export": True,
                    "disc": raw,
                    "reason": f"{type(exc).__name__}: {exc}",
                    "repairs": [],
                    "violations": [],
                }
            )
            unrepairable += 1
            continue

        if disc is None:
            disc_reports.append(
                {
                    "index": i,
                    "status": "critical_fail",
                    "excluded_from_export": True,
                    "disc": raw,
                    "reason": conf.get("_fail_reason", "?"),
                    "repairs": [],
                    "violations": [],
                }
            )
            unrepairable += 1
            continue

        disc.location = raw["location"]
        disc.lock = raw["lock"]

        # Re-run explicitly on the merged disc for the report's gate. location/
        # lock aren't validated fields, but the evidence (main-stat value, roll
        # suffixes, pct_seen) captured in conf MUST be passed: the evidence-only
        # main_value_mismatch check is otherwise silently skipped, letting a
        # main-key/level/rarity misread leak into the corrected export — the very
        # T13 guarantee this tool exists to enforce (same evidence the live
        # scan_discs path and _extract_disc's internal validate use).
        evidence = evidence_from_conf(conf, len(disc.substats))
        final_violations = validate_disc(disc, evidence)
        repairs = conf.get("_repairs", [])

        report_entry = {
            "index": i,
            "status": "unrepairable" if final_violations else ("repaired" if repairs else "clean"),
            "repairs": repairs,
            "violations": [
                {
                    "field": v.field,
                    "code": v.code,
                    "observed": v.observed,
                    "expected": v.expected,
                    "severity": v.severity,
                }
                for v in final_violations
            ],
        }
        if final_violations:
            # Excluded: keep the disc's values in the report so the failure is
            # reviewable, but never in the export.
            report_entry["excluded_from_export"] = True
            report_entry["disc"] = disc.to_dict()
            unrepairable += 1
        else:
            discs.append(disc)
            if repairs:
                repaired += 1
            else:
                clean += 1
        disc_reports.append(report_entry)

        if (i + 1) % 200 == 0:
            print(f"  ...{i + 1}/{len(raw_discs)} discs processed", flush=True)

    elapsed = time.perf_counter() - t0

    output = Path(args.out)
    export_discs(discs, output)

    summary = {
        "total": len(disc_reports),
        "clean": clean,
        "repaired": repaired,
        "unrepairable": unrepairable,
        "exported": len(discs),
        "excluded": unrepairable,
        "elapsed_s": round(elapsed, 1),
    }
    print(f"\nRevalidated {summary['total']} disc(s) in {elapsed:.1f}s.")
    print(f"  clean: {clean}  repaired: {repaired}  unrepairable: {unrepairable}")
    print(f"Corrected export written to: {output} ({len(discs)} disc(s))")

    # T13: failed discs exist ONLY in the report now, so it is always written —
    # default path sits next to the export when --report isn't given.
    report_path = (
        Path(args.report) if args.report else output.with_name(output.stem + ".report.json")
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps({"summary": summary, "discs": disc_reports}, indent=2),
        encoding="utf-8",
    )
    print(f"Report written to: {report_path}")

    if unrepairable:
        print(
            f"\n{unrepairable} disc(s) failed validation and were EXCLUDED from the "
            f"export — review them in the report and re-scan in-game to recover."
        )


def _write_review_report(issues: list[dict], path: Path) -> None:
    """F3: Write a human-readable review.txt for manual verification of low-confidence items."""
    from io import StringIO

    buf = StringIO()

    def _section(title: str, rows: list[str]) -> None:
        if not rows:
            return
        buf.write(f"\n{'─' * 72}\n{title} ({len(rows)})\n{'─' * 72}\n")
        for r in rows:
            buf.write(r + "\n")

    # ── Critical fails (unknown_agent, no_slot, …) ───────────────────────────
    critical = [i for i in issues if i.get("status") == "critical_fail"]
    crit_rows = []
    for issue in critical:
        if "agent" in issue:
            crit_rows.append(
                f"  [agent #{issue['agent']:03d}] "
                f"{issue.get('type', '?')}: {issue.get('message', '')}"
            )
        elif "cell" in issue:
            phase = "disc" if "disc" in issue else "engine"
            crit_rows.append(
                f"  [{phase} cell #{issue['cell']:04d}] "
                f"{issue.get('type', '?')}: {issue.get('message', '')}"
            )
        else:
            crit_rows.append(f"  {issue}")
    _section("CRITICAL FAILS — require manual fix before importing", crit_rows)

    # ── Unknown / blank-key agents ───────────────────────────────────────────
    unknown_agents = [
        i
        for i in issues
        if "agent" in i
        and i.get("status") in ("critical_fail", "low_confidence")
        and i.get("key", "?") in ("", None)
    ]
    unk_rows = [
        f"  [agent #{i['agent']:03d}] raw OCR name: "
        f"{i.get('raw_name', i.get('fields', {}).get('name_raw', '(no raw)'))!r}  "
        f"score={i.get('fields', {}).get('name', i.get('score', '?'))}"
        for i in unknown_agents
    ]
    _section("UNKNOWN AGENT NAMES — add alias to agents.json or fix OCR", unk_rows)

    # ── Low-confidence agents ────────────────────────────────────────────────
    low_agents = [
        i
        for i in issues
        if "agent" in i
        and i.get("status") == "low_confidence"
        and i.get("key", "?") not in ("", None)
    ]
    agent_rows = []
    for issue in low_agents:
        fields_str = "  ".join(f"{k}={v:.0f}%" for k, v in sorted(issue.get("fields", {}).items()))
        agent_rows.append(
            f"  [agent #{issue['agent']:03d}] key={issue['key']!r}  low: {fields_str}"
        )
    _section("LOW-CONFIDENCE AGENT FIELDS — verify in-game", agent_rows)

    # ── Low-confidence engines ───────────────────────────────────────────────
    low_engines = [i for i in issues if "engine" in i and i.get("status") == "low_confidence"]
    eng_rows = []
    for issue in low_engines:
        eng = issue["engine"]
        fields_str = "  ".join(f"{k}={v:.0f}%" for k, v in sorted(issue.get("fields", {}).items()))
        eng_rows.append(
            f"  [cell #{issue['cell']:04d}] key={eng['key']!r}  lv={eng['level']}  "
            f"ref={eng['refinement']}  low: {fields_str}"
        )
    _section("LOW-CONFIDENCE ENGINE FIELDS — verify key/rarity in-game", eng_rows)

    # ── Failed discs (T13: excluded from the export entirely) ────────────────
    failed_discs = [i for i in issues if i.get("status") == "failed_validation"]
    failed_rows = []
    for issue in failed_discs:
        disc = issue.get("disc", {})
        failed_rows.append(
            f"  [cell #{issue.get('cell', '?'):>4}] set={disc.get('setKey', '?')!r}  "
            f"slot={disc.get('slotKey', '?')}  lv={disc.get('level', '?')}"
        )
        for v in issue.get("violations", []):
            failed_rows.append(
                f"      {v['field']}: {v['code']}  "
                f"observed={v['observed']}  expected={v['expected']}"
            )
    _section("FAILED DISCS — EXCLUDED from export; re-scan in-game to recover", failed_rows)

    # ── Low-confidence discs ─────────────────────────────────────────────────
    low_discs = [i for i in issues if "disc" in i and i.get("status") == "low_confidence"]
    disc_rows = []
    for issue in low_discs:
        disc = issue["disc"]
        fields_str = "  ".join(f"{k}={v:.0f}%" for k, v in sorted(issue.get("fields", {}).items()))
        disc_rows.append(
            f"  [cell #{issue.get('cell', '?'):>4}] set={disc.get('setKey', '?')!r}  "
            f"slot={disc.get('slotKey', '?')}  lv={disc.get('level', '?')}  low: {fields_str}"
        )
    _section("LOW-CONFIDENCE DISC FIELDS — verify set/stat in-game", disc_rows)

    # ── Auto-repaired disc fields (T9: disc_rules.repair_disc) ───────────────
    repaired_discs = [i for i in issues if "disc" in i and i.get("repairs")]
    repair_rows = []
    for issue in repaired_discs:
        disc = issue["disc"]
        for r in issue["repairs"]:
            repair_rows.append(
                f"  [cell #{issue.get('cell', '?'):>4}] set={disc.get('setKey', '?')!r}  "
                f"{r['field']}: {r['before']} -> {r['after']}  (rule={r['rule']})"
            )
    _section("AUTO-REPAIRED DISC FIELDS — verify in-game", repair_rows)

    # ── Orphan equipment ─────────────────────────────────────────────────────
    orphans = [i for i in issues if i.get("status") == "orphan"]
    orp_rows = [f"  {i}" for i in orphans]
    _section("ORPHAN EQUIPMENT — location cross-ref could not resolve", orp_rows)

    summary_line = (
        f"youkai-ocr review report\n"
        f"  critical: {len(critical)}  unknown_agents: {len(unknown_agents)}  "
        f"low_agents: {len(low_agents)}  low_engines: {len(low_engines)}  "
        f"failed_discs: {len(failed_discs)}  low_discs: {len(low_discs)}  "
        f"repaired_discs: {len(repaired_discs)}  orphans: {len(orphans)}\n"
    )
    content = summary_line + buf.getvalue()
    if not buf.getvalue().strip():
        content += "\nNo issues to review — all fields resolved above confidence threshold.\n"

    path.write_text(content, encoding="utf-8")


_VALID_PHASES: frozenset[str] = frozenset({"agents", "discs", "engines"})


# ── T1.5: fingerprint reconciliation ─────────────────────────────────────────


def _substat_key_overlap(a: ZodDisc, b: ZodDisc) -> int:
    """Count of matching non-empty substat keys between two discs."""
    ak = {s.key for s in a.substats if s.key}
    bk = {s.key for s in b.substats if s.key}
    return len(ak & bk)


def _backfill_disc_substats(inv: ZodDisc, eq: ZodDisc) -> None:
    """Fill empty substat keys in inv from eq when values match closely."""
    for inv_sub in inv.substats:
        if inv_sub.key:
            continue
        for eq_sub in eq.substats:
            if eq_sub.key and abs(eq_sub.value - inv_sub.value) < 0.01:
                inv_sub.key = eq_sub.key
                break


def _reconcile_locations(
    equipped_discs: list[ZodDisc],
    equipped_engines: list[ZodWEngine],
    discs: list[ZodDisc],
    engines: list[ZodWEngine],
) -> list[dict]:
    """T1.5: Match equipped gear against inventory by fingerprint.

    For each equipped disc/engine (location already set by scan_agents):
      match    → stamp location on the inventory entry; backfill empty substat keys.
      no-match → append the equipped entry to the list (inventory missed it; never drop).
    Guarantees 1:1: each inventory entry is matched at most once.
    Returns informational orphan dicts for entries that were appended rather than matched.
    """
    from youkai_ocr.zod import ZodDisc, ZodWEngine

    orphans: list[dict] = []
    matched_disc_idx: set[int] = set()

    for eq in equipped_discs:
        if not eq.location:
            continue
        # Primary filter: set + slot + main_stat_key (most discriminating trio)
        candidates = [
            (i, d)
            for i, d in enumerate(discs)
            if i not in matched_disc_idx
            and d.set_key == eq.set_key
            and d.slot_key == eq.slot_key
            and d.main_stat_key == eq.main_stat_key
        ]
        if not candidates:
            # Widen to set+slot only (main_stat OCR can drift between reads)
            candidates = [
                (i, d)
                for i, d in enumerate(discs)
                if i not in matched_disc_idx
                and d.set_key == eq.set_key
                and d.slot_key == eq.slot_key
            ]

        if not candidates:
            discs.append(
                ZodDisc(
                    set_key=eq.set_key,
                    slot_key=eq.slot_key,
                    level=eq.level,
                    rarity=eq.rarity,
                    main_stat_key=eq.main_stat_key,
                    location=eq.location,
                    lock=eq.lock,
                    substats=list(eq.substats),
                )
            )
            orphans.append(
                {
                    "status": "orphan",
                    "type": "disc",
                    "agent": eq.location,
                    "set_key": eq.set_key,
                    "slot_key": eq.slot_key,
                    "message": "equipped disc not found in inventory scan; appended",
                }
            )
        else:
            best_i, best_d = max(
                candidates,
                key=lambda x: (_substat_key_overlap(x[1], eq), -abs(x[1].level - eq.level)),
            )
            best_d.location = eq.location
            _backfill_disc_substats(best_d, eq)
            matched_disc_idx.add(best_i)

    matched_eng_idx: set[int] = set()
    for eq in equipped_engines:
        if not eq.location:
            continue
        candidates = [
            (i, e) for i, e in enumerate(engines) if i not in matched_eng_idx and e.key == eq.key
        ]
        if not candidates:
            engines.append(
                ZodWEngine(
                    key=eq.key,
                    level=eq.level,
                    ascension=eq.ascension,
                    refinement=eq.refinement,
                    location=eq.location,
                    lock=eq.lock,
                )
            )
            orphans.append(
                {
                    "status": "orphan",
                    "type": "engine",
                    "agent": eq.location,
                    "key": eq.key,
                    "message": "equipped engine not found in inventory scan; appended",
                }
            )
        else:
            best_i, best_e = min(candidates, key=lambda x: abs(x[1].level - eq.level))
            best_e.location = eq.location
            matched_eng_idx.add(best_i)

    return orphans


def select_phases(args) -> frozenset[str]:
    """Return the validated set of phases to run.

    Maps deprecated --agents-only to {"agents"}.
    Raises ValueError on unknown or empty names.
    """
    if getattr(args, "agents_only", False):
        return frozenset({"agents"})
    raw = getattr(args, "phases", None) or "engines,discs,agents"
    names = frozenset(p.strip() for p in raw.split(",") if p.strip())
    if not names:
        raise ValueError("--phases must not be empty")
    unknown = names - _VALID_PHASES
    if unknown:
        raise ValueError(
            f"Unknown phase name(s): {', '.join(sorted(unknown))}. "
            f"Valid: {', '.join(sorted(_VALID_PHASES))}"
        )
    return names


_PHASE_ORDER = ("engines", "discs", "agents")


def _phase_summary_line(phase_results: dict) -> str:
    """Render phase_results as e.g. 'engines=done(412) discs=FAILED agents=not-reached'.

    phase_results only gains an entry once a phase finishes (or is skipped/resumed),
    so the first phase in canonical order missing from it is the one that was
    running when the failure hit; anything after that was never reached.
    """
    parts = []
    failed_marked = False
    for name in _PHASE_ORDER:
        v = phase_results.get(name)
        if v is not None:
            if v.get("skipped"):
                parts.append(f"{name}=skipped")
            elif v.get("resumed"):
                parts.append(f"{name}=resumed({v.get('count')})")
            else:
                parts.append(f"{name}=done({v.get('count')})")
        elif not failed_marked:
            parts.append(f"{name}=FAILED")
            failed_marked = True
        else:
            parts.append(f"{name}=not-reached")
    return " ".join(parts)


def _is_user_abort(exc: BaseException, msg: str) -> bool:
    """True for a deliberate user stop, as opposed to a real crash.

    Covers Ctrl+C at a terminal (KeyboardInterrupt) and the interactive
    decline paths in `_make_first_item_check`/`_preflight_frame`, which both
    raise RuntimeError("Scan aborted by user ...").
    """
    return isinstance(exc, KeyboardInterrupt) or msg.startswith("Scan aborted by user")


def _write_crash_report(
    crash_path: Path,
    *,
    run_dir: Path,
    started: str,
    argv: list[str],
    phase_results: dict,
    calib,
    engine: str,
    exc: BaseException,
    tb_str: str,
) -> None:
    """Write a single self-contained diagnostic file for a failed scan-all run.

    Caller wraps this in try/except — a write failure here must never mask the
    original exception, so this function does not need to be defensive itself
    beyond falling back to "unknown" for fields that may not exist yet.
    """
    import datetime
    import platform as _platform

    from youkai_ocr import __version__

    lines = [
        f"youkai-ocr {__version__}",
        f"run dir : {run_dir}",
        f"started : {started}      failed: {datetime.datetime.now().isoformat(timespec='seconds')}",
        f"command : {' '.join(argv)}",
        f"platform: {_platform.system()} {_platform.release()}  "
        f"python {_platform.python_version()}",
        f"engine  : {engine}",
    ]
    if calib is not None:
        lines.append(
            f"window  : {calib.frame_width}x{calib.frame_height} @ "
            f"({calib.window_left},{calib.window_top}) scale "
            f"{calib.scale_x:.3f}x{calib.scale_y:.3f}"
        )
    else:
        lines.append("window  : unknown (failure occurred before calibration)")
    lines.append(f"phases  : {_phase_summary_line(phase_results)}")
    lines.append("---")
    lines.append(str(exc) or type(exc).__name__)
    lines.append("---")
    lines.append(tb_str)
    lines.append("---")

    log_path = run_dir / "scan.log"
    if log_path.exists():
        log_lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        tail_lines = log_lines[-50:]
        tail_text = "\n".join(tail_lines)
        tail_bytes = tail_text.encode("utf-8")
        if len(tail_bytes) > 16 * 1024:
            tail_text = tail_bytes[-16 * 1024 :].decode("utf-8", errors="replace")
        lines.append(f"last {len(tail_lines)} line(s) of scan.log:")
        lines.append(tail_text)
    else:
        lines.append("scan.log: unavailable")

    crash_path.write_text("\n".join(lines), encoding="utf-8")


def _cmd_scan_all(args: argparse.Namespace) -> None:
    """H5/H7c: Full ZodExport with run-dir persistence, screen assertions, and resume.

    Default: auto-nav (no manual gates).  Pass --manual-nav to use the original
    input()-gated flow.
    """
    import datetime
    import json as _json
    import time

    from youkai_ocr.agent_scanner import scan_agents
    from youkai_ocr.capture import calibrate_window
    from youkai_ocr.disc_scanner import scan_discs
    from youkai_ocr.progress import NullEmitter, ProgressEmitter
    from youkai_ocr.wengine_scanner import scan_engines
    from youkai_ocr.zod import ZodDisc, ZodExport, ZodWEngine

    output = Path(args.output)
    resume_dir = Path(args.resume) if getattr(args, "resume", None) else None
    manual_nav = getattr(args, "manual_nav", False)
    porcelain = getattr(args, "porcelain", False)
    interactive = not porcelain

    # Run dir: always timestamped so consecutive runs don't overwrite frames.
    run_ts = datetime.datetime.now().strftime("live_%Y%m%d_%H%M%S")
    run_start_iso = datetime.datetime.now().isoformat(timespec="seconds")
    if args.archive_dir:
        run_dir = Path(args.archive_dir) / run_ts
    else:
        run_dir = Path("archive") / run_ts
    run_dir.mkdir(parents=True, exist_ok=True)

    # Declared before the try so the except/finally handlers can always see them,
    # even if the failure happens before the phases below assign anything.
    all_issues: list[dict] = []
    phase_results: dict = {}
    grid_count = 0  # owned cells visible in the initial agent-menu frame (coverage check)
    coverage: dict = {}
    success_summary: dict | None = None
    calib = None
    t_start = time.perf_counter()
    run_status = "failed"
    error_info: dict | None = None

    # Emitter captures real stdout before _Tee redirects sys.stdout.
    emitter: ProgressEmitter | NullEmitter = (
        ProgressEmitter(sys.stdout) if porcelain else NullEmitter()
    )
    tee = _Tee(run_dir / "scan.log", mirror=sys.stderr if porcelain else None)
    import logging as _logging

    _pkg_log = _logging.getLogger("youkai_ocr")
    _log_handler = _logging.FileHandler(run_dir / "agent_scan.log", encoding="utf-8")
    _log_handler.setFormatter(_logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    _log_handler.setLevel(_logging.DEBUG)
    _prev_level = _pkg_log.level
    _pkg_log.setLevel(_logging.DEBUG)
    _pkg_log.addHandler(_log_handler)
    try:
        print(f"Run dir: {run_dir}")

        calib, capture_fn = calibrate_window()
        print(
            f"Game window found: {calib.frame_width}×{calib.frame_height}, "
            f"offset: ({calib.window_left},{calib.window_top}), "
            f"scale: {calib.scale_x:.3f}×{calib.scale_y:.3f}"
        )

        phases = select_phases(args)
        emitter.run_start(
            run_dir=str(run_dir),
            output=str(output),
            phases=[p for p in ("engines", "discs", "agents") if p in phases],
        )
        discs_cache = run_dir / "discs.json"
        engines_cache = run_dir / "engines.json"
        resume_discs = resume_dir / "discs.json" if resume_dir else None
        resume_engines = resume_dir / "engines.json" if resume_dir else None

        if not manual_nav:
            # ── Auto-nav path ────────────────────────────────────────────────
            from youkai_ocr.capture import focus_game_window

            focused = focus_game_window()
            print(
                f"  Game window {'focused' if focused else 'WARNING: could not focus game window'}"
            )
            time.sleep(0.3)
            frame = capture_fn()
            if not _is_main_menu(frame, calib):
                raise ScreenAssertError(
                    "auto-nav: not on the Inter-Knot main-menu hub.\n"
                    "Navigate there first, or use --manual-nav to gate each phase manually."
                )
            driver = _NavDriver(calib, capture_fn, archive_dir=run_dir)

            storage_visited = False

            # ── Phase 1/3: W-Engines (tab 0 in Storage) ─────────────────────
            emitter.phase_start(phase="engines")
            if "engines" not in phases:
                print("\n[1/3] W-Engine phase: skipped (--phases).")
                engines = []
                phase_results["engines"] = {"count": 0, "skipped": True}
                emitter.phase_done(phase="engines", count=0, issues=0, elapsed=0.0)
            elif resume_engines and resume_engines.exists():
                print("\n[1/3] W-Engine phase: loading from resume cache.")
                raw = _json.loads(resume_engines.read_text())
                engines = [ZodWEngine.from_dict(e) for e in raw]
                phase_results["engines"] = {
                    "count": len(engines),
                    "issues": 0,
                    "elapsed": 0.0,
                    "resumed": True,
                }
                print(f"  Loaded {len(engines)} engine(s) from cache.")
                emitter.phase_done(
                    phase="engines", count=len(engines), issues=0, elapsed=0.0, resumed=True
                )
            else:
                driver.navigate_to_storage()
                storage_visited = True
                driver.switch_storage_tab(0, archive_dir=run_dir)
                print("\n[1/3] W-Engine inventory — scanning…")
                t0 = time.perf_counter()
                engines, engine_issues = scan_engines(
                    capture_fn=capture_fn,
                    calib=calib,
                    archive_dir=run_dir,
                    engine=args.engine,
                    on_item=lambda s, t: emitter.progress(phase="engines", scanned=s, total=t),
                )
                elapsed = time.perf_counter() - t0
                all_issues.extend(engine_issues)
                phase_results["engines"] = {
                    "count": len(engines),
                    "issues": len(engine_issues),
                    "elapsed": round(elapsed, 1),
                }
                print(
                    f"  Scanned {len(engines)} engine(s) in {elapsed:.1f}s. "
                    f"Issues: {len(engine_issues)}"
                )
                engines_cache.write_text(
                    _json.dumps([e.to_dict() for e in engines], indent=2), encoding="utf-8"
                )
                print(f"  Phase output → {engines_cache}")
                emitter.phase_done(
                    phase="engines",
                    count=len(engines),
                    issues=len(engine_issues),
                    elapsed=round(elapsed, 1),
                )

            # ── Phase 2/3: Drive Discs (tab 1 in Storage) ───────────────────
            emitter.phase_start(phase="discs")
            if "discs" not in phases:
                print("\n[2/3] Drive Disc phase: skipped (--phases).")
                discs = []
                phase_results["discs"] = {"count": 0, "skipped": True}
                emitter.phase_done(phase="discs", count=0, issues=0, elapsed=0.0)
            elif resume_discs and resume_discs.exists():
                print("\n[2/3] Drive Disc phase: loading from resume cache.")
                raw = _json.loads(resume_discs.read_text())
                discs = [ZodDisc.from_dict(d) for d in raw]
                phase_results["discs"] = {
                    "count": len(discs),
                    "issues": 0,
                    "elapsed": 0.0,
                    "resumed": True,
                }
                print(f"  Loaded {len(discs)} disc(s) from cache.")
                emitter.phase_done(
                    phase="discs", count=len(discs), issues=0, elapsed=0.0, resumed=True
                )
            else:
                if not storage_visited:
                    driver.navigate_to_storage()
                    storage_visited = True
                else:
                    time.sleep(2.0)  # let the game settle after engine scan scroll activity
                driver.switch_storage_tab(1, archive_dir=run_dir)
                print("\n[2/3] Drive Disc inventory — scanning…")
                from youkai_ocr.grid import DEFAULT_GRID

                cell0 = DEFAULT_GRID.cell_0_0_center
                sx, sy = calib.to_screen(*cell0)
                print(
                    f"  First cell ref=({cell0[0]},{cell0[1]}) → screen=({sx},{sy})  "
                    f"window origin=({calib.window_left},{calib.window_top})"
                )
                t0 = time.perf_counter()
                discs, disc_issues = scan_discs(
                    capture_fn=capture_fn,
                    calib=calib,
                    archive_dir=run_dir,
                    engine=args.engine,
                    on_first_item=_make_first_item_check(
                        "disc", interactive=interactive, emitter=emitter
                    ),
                    on_item=lambda s, t: emitter.progress(phase="discs", scanned=s, total=t),
                )
                elapsed = time.perf_counter() - t0
                all_issues.extend(disc_issues)
                phase_results["discs"] = {
                    "count": len(discs),
                    "issues": len(disc_issues),
                    "elapsed": round(elapsed, 1),
                }
                print(
                    f"  Scanned {len(discs)} disc(s) in {elapsed:.1f}s. Issues: {len(disc_issues)}"
                )
                discs_cache.write_text(
                    _json.dumps([d.to_dict() for d in discs], indent=2), encoding="utf-8"
                )
                print(f"  Phase output → {discs_cache}")
                emitter.phase_done(
                    phase="discs",
                    count=len(discs),
                    issues=len(disc_issues),
                    elapsed=round(elapsed, 1),
                )

            # Return to main menu before navigating to Agents
            if "agents" in phases and storage_visited:
                driver.return_to_main()

            # ── Phase 3/3: Agent roster ──────────────────────────────────────
            emitter.phase_start(phase="agents")
            if "agents" in phases:
                print("\n[3/3] Agent roster — navigating…")
                agent_menu_frame = driver.navigate_to_agents()
                from youkai_ocr.agent_scanner import detect_owned_agent_cells as _detect_cells

                grid_count = len(_detect_cells(agent_menu_frame, calib))
                print(f"  Roster grid (first page): {grid_count} owned cell(s) visible")
                t0 = time.perf_counter()
                agents, agent_issues, equipped_discs, equipped_engines = scan_agents(
                    capture_fn=capture_fn,
                    calib=calib,
                    archive_dir=run_dir,
                    ocr_engine=args.engine,
                    debug_overlays=getattr(args, "debug_overlays", False),
                    on_item=lambda s, t: emitter.progress(phase="agents", scanned=s, total=t),
                )
            else:
                agents, agent_issues, equipped_discs, equipped_engines = [], [], [], []
                phase_results["agents"] = {"count": 0, "skipped": True}
                print("\n[3/3] Agent phase: skipped (--phases).")
                emitter.phase_done(phase="agents", count=0, issues=0, elapsed=0.0)

        else:
            # ── Manual-nav path (--manual-nav) ───────────────────────────────
            # ── Step 1: Drive Discs ──────────────────────────────────────────
            emitter.phase_start(phase="discs")
            if "discs" not in phases:
                print("\n[1/3] Drive Disc phase: skipped (--phases).")
                discs = []
                phase_results["discs"] = {"count": 0, "skipped": True}
                emitter.phase_done(phase="discs", count=0, issues=0, elapsed=0.0)
            elif resume_discs and resume_discs.exists():
                print("\n[1/3] Drive Disc phase: loading from resume cache.")
                raw = _json.loads(resume_discs.read_text())
                discs = [ZodDisc.from_dict(d) for d in raw]
                phase_results["discs"] = {
                    "count": len(discs),
                    "issues": 0,
                    "elapsed": 0.0,
                    "resumed": True,
                }
                print(f"  Loaded {len(discs)} disc(s) from cache.")
                emitter.phase_done(
                    phase="discs", count=len(discs), issues=0, elapsed=0.0, resumed=True
                )
            else:
                print("\n[1/3] Drive Disc inventory — navigate there, then press Enter.")
                if interactive:
                    input()
                _countdown(5)
                frame = _preflight_frame(
                    capture_fn, calib, run_dir, "discs", interactive=interactive, emitter=emitter
                )
                _check_disc_screen(frame, calib, args.engine)
                from youkai_ocr.grid import DEFAULT_GRID

                cell0 = DEFAULT_GRID.cell_0_0_center
                sx, sy = calib.to_screen(*cell0)
                print(
                    f"  First cell ref=({cell0[0]},{cell0[1]}) → screen=({sx},{sy})  "
                    f"window origin=({calib.window_left},{calib.window_top})"
                )
                t0 = time.perf_counter()
                discs, disc_issues = scan_discs(
                    capture_fn=capture_fn,
                    calib=calib,
                    archive_dir=run_dir,
                    engine=args.engine,
                    on_first_item=_make_first_item_check(
                        "disc", interactive=interactive, emitter=emitter
                    ),
                    on_item=lambda s, t: emitter.progress(phase="discs", scanned=s, total=t),
                )
                elapsed = time.perf_counter() - t0
                all_issues.extend(disc_issues)
                phase_results["discs"] = {
                    "count": len(discs),
                    "issues": len(disc_issues),
                    "elapsed": round(elapsed, 1),
                }
                print(
                    f"  Scanned {len(discs)} disc(s) in {elapsed:.1f}s. Issues: {len(disc_issues)}"
                )
                discs_cache.write_text(
                    _json.dumps([d.to_dict() for d in discs], indent=2), encoding="utf-8"
                )
                print(f"  Phase output → {discs_cache}")
                emitter.phase_done(
                    phase="discs",
                    count=len(discs),
                    issues=len(disc_issues),
                    elapsed=round(elapsed, 1),
                )

            # ── Step 2: W-Engines ────────────────────────────────────────────
            emitter.phase_start(phase="engines")
            if "engines" not in phases:
                print("\n[2/3] W-Engine phase: skipped (--phases).")
                engines = []
                phase_results["engines"] = {"count": 0, "skipped": True}
                emitter.phase_done(phase="engines", count=0, issues=0, elapsed=0.0)
            elif resume_engines and resume_engines.exists():
                print("\n[2/3] W-Engine phase: loading from resume cache.")
                raw = _json.loads(resume_engines.read_text())
                engines = [ZodWEngine.from_dict(e) for e in raw]
                phase_results["engines"] = {
                    "count": len(engines),
                    "issues": 0,
                    "elapsed": 0.0,
                    "resumed": True,
                }
                print(f"  Loaded {len(engines)} engine(s) from cache.")
                emitter.phase_done(
                    phase="engines", count=len(engines), issues=0, elapsed=0.0, resumed=True
                )
            else:
                print("\n[2/3] W-Engine inventory — navigate there, then press Enter.")
                if interactive:
                    input()
                _countdown(5)
                frame = _preflight_frame(
                    capture_fn, calib, run_dir, "engines", interactive=interactive, emitter=emitter
                )
                _check_engine_screen(frame, calib, args.engine)
                t0 = time.perf_counter()
                engines, engine_issues = scan_engines(
                    capture_fn=capture_fn,
                    calib=calib,
                    archive_dir=run_dir,
                    engine=args.engine,
                    on_item=lambda s, t: emitter.progress(phase="engines", scanned=s, total=t),
                )
                elapsed = time.perf_counter() - t0
                all_issues.extend(engine_issues)
                phase_results["engines"] = {
                    "count": len(engines),
                    "issues": len(engine_issues),
                    "elapsed": round(elapsed, 1),
                }
                print(
                    f"  Scanned {len(engines)} engine(s) in {elapsed:.1f}s. "
                    f"Issues: {len(engine_issues)}"
                )
                engines_cache.write_text(
                    _json.dumps([e.to_dict() for e in engines], indent=2), encoding="utf-8"
                )
                print(f"  Phase output → {engines_cache}")
                emitter.phase_done(
                    phase="engines",
                    count=len(engines),
                    issues=len(engine_issues),
                    elapsed=round(elapsed, 1),
                )

            # ── Step 3: Agent roster ─────────────────────────────────────────
            emitter.phase_start(phase="agents")
            if "agents" in phases:
                print("\n[3/3] Agent roster — open the agent menu, then press Enter.")
                if interactive:
                    input()
                _countdown(5)
                frame = _preflight_frame(
                    capture_fn, calib, run_dir, "agents", interactive=interactive, emitter=emitter
                )
                _check_agent_screen(frame, calib)
                from youkai_ocr.agent_scanner import detect_owned_agent_cells as _detect_cells

                grid_count = len(_detect_cells(frame, calib))
                print(f"  Roster grid (first page): {grid_count} owned cell(s) visible")
                t0 = time.perf_counter()
                agents, agent_issues, equipped_discs, equipped_engines = scan_agents(
                    capture_fn=capture_fn,
                    calib=calib,
                    archive_dir=run_dir,
                    ocr_engine=args.engine,
                    debug_overlays=getattr(args, "debug_overlays", False),
                    on_item=lambda s, t: emitter.progress(phase="agents", scanned=s, total=t),
                )
            else:
                agents, agent_issues, equipped_discs, equipped_engines = [], [], [], []
                phase_results["agents"] = {"count": 0, "skipped": True}
                print("\n[3/3] Agent phase: skipped (--phases).")
                emitter.phase_done(phase="agents", count=0, issues=0, elapsed=0.0)

        if "agents" not in phase_results:
            elapsed = time.perf_counter() - t0
            all_issues.extend(agent_issues)
            phase_results["agents"] = {
                "count": len(agents),
                "issues": len(agent_issues),
                "elapsed": round(elapsed, 1),
            }
            emitter.phase_done(
                phase="agents",
                count=len(agents),
                issues=len(agent_issues),
                elapsed=round(elapsed, 1),
            )
            print(
                f"  Scanned {len(agents)} agent(s) in {elapsed:.1f}s. Issues: {len(agent_issues)}"
            )
            agents_cache = run_dir / "agents.json"
            agents_cache.write_text(
                _json.dumps([a.to_dict() for a in agents], indent=2), encoding="utf-8"
            )
            print(f"  Phase output → {agents_cache}")

        # ── T1.5: fingerprint reconciliation ────────────────────────────────
        reconcile_orphans = _reconcile_locations(
            equipped_discs,
            equipped_engines,
            discs,
            engines,
        )
        if reconcile_orphans:
            print(
                f"  Reconciliation: {len(reconcile_orphans)} equipped item(s) "
                "not found in inventory — appended to export."
            )
        all_issues.extend(reconcile_orphans)

        # ── Dedupe + stable sort ─────────────────────────────────────────────
        seen_agents: set[str] = set()
        unique_agents = []
        for a in agents:
            if a.key not in seen_agents:
                seen_agents.add(a.key)
                unique_agents.append(a)
        unique_agents.sort(key=lambda a: a.key)
        discs.sort(key=lambda d: (d.set_key, d.slot_key))
        engines.sort(key=lambda e: e.key)

        # ── Assemble and write export ────────────────────────────────────────
        export = ZodExport(characters=unique_agents, discs=discs, weapons=engines)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(export.to_json(), encoding="utf-8")
        print(f"\nExport written to: {output}")
        print(f"  {len(unique_agents)} agent(s), {len(discs)} disc(s), {len(engines)} engine(s)")

        if all_issues:
            issues_path = run_dir / "issues.json"
            issues_path.write_text(_json.dumps(all_issues, indent=2), encoding="utf-8")
            print(f"  {len(all_issues)} issue(s) written to: {issues_path}")
            review_path = run_dir / "review.txt"
            _write_review_report(all_issues, review_path)
            print(f"  Review report   → {review_path}")

        # ── T3.1: Roster coverage check ──────────────────────────────────────
        if "agents" in phases and grid_count > 0:
            crit_fail_agents = [
                i for i in all_issues if i.get("status") == "critical_fail" and "agent" in i
            ]
            scanned_keys = [a.key for a in unique_agents]
            gap = grid_count - len(unique_agents)
            coverage = {
                "roster_grid_visible": grid_count,
                "agents_scanned": len(unique_agents),
                "gap": max(gap, 0),
                "warning": gap > 0,
                "scanned_keys": scanned_keys,
            }
            if crit_fail_agents:
                coverage["critical_fail_count"] = len(crit_fail_agents)
            if gap > 0:
                print(
                    f"\n  WARNING: roster coverage: scanned {len(unique_agents)} agent(s) but "
                    f"roster grid (first page) shows {grid_count} owned. "
                    f"Gap: {gap}. Some agents may have been missed "
                    f"or the grid was not fully visible."
                )
                if crit_fail_agents:
                    print(f"  {len(crit_fail_agents)} agent visit(s) failed OCR — see issues.json.")

        # ── Stash the success summary; results.json itself is written in `finally`
        # so both the success and failure paths go through one write site. ──────
        success_summary = {
            "agents": len(unique_agents),
            "discs": len(discs),
            "engines": len(engines),
            "issues": len(all_issues),
        }
        run_status = "ok"

        review_str = str(run_dir / "review.txt") if all_issues else None
        emitter.done(
            output=str(output),
            run_dir=str(run_dir),
            summary=success_summary,
            review_path=review_str,
        )

    except BaseException as _exc:
        import traceback as _tb

        _tb_str = _tb.format_exc().strip()
        _msg = str(_exc) or type(_exc).__name__

        run_status = "aborted" if _is_user_abort(_exc, _msg) else "failed"
        error_info = {"type": type(_exc).__name__, "message": _msg}

        crash_path = run_dir / "crash.txt"
        crash_written = False
        try:
            # _Tee buffers writes to scan.log; flush so the tail we're about to
            # read actually reflects everything printed before this exception.
            tee.flush()
        except Exception:
            pass
        try:
            _write_crash_report(
                crash_path,
                run_dir=run_dir,
                started=run_start_iso,
                argv=sys.argv,
                phase_results=phase_results,
                calib=calib,
                engine=getattr(args, "engine", "unknown"),
                exc=_exc,
                tb_str=_tb_str,
            )
            crash_written = True
        except Exception:
            crash_written = False

        error_msg = f"{_msg}\n---\n{_tb_str}" if _tb_str else _msg
        if crash_written:
            error_msg += (
                f"\nFull details written to {crash_path} — attach this file when reporting."
            )
        emitter.error(message=error_msg)
        raise
    finally:
        total_elapsed = round(time.perf_counter() - t_start, 1)
        results: dict = {
            "run_dir": str(run_dir),
            "output": str(output),
            "total_elapsed": total_elapsed,
            "phases": phase_results,
            "status": run_status,
        }
        if run_status == "ok":
            results["summary"] = success_summary
            if coverage:
                results["coverage"] = coverage
        elif error_info is not None:
            results["error"] = error_info
        try:
            results_path = run_dir / "results.json"
            results_path.write_text(_json.dumps(results, indent=2), encoding="utf-8")
            print(f"  Results summary → {results_path}")
        except Exception:
            pass

        _pkg_log.removeHandler(_log_handler)
        _log_handler.close()
        _pkg_log.setLevel(_prev_level)
        tee.close()


# ── CLI entry point ───────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="youkai-ocr",
        description="ZZZ inventory OCR scanner — exports ZodExport/eZOD JSON.",
    )
    from youkai_ocr import __version__

    parser.add_argument("--version", action="version", version=f"youkai-ocr {__version__}")
    # Global option — repeatable; appended to the accepted-titles list so the
    # scanner also looks for windows whose title contains TITLE.
    parser.add_argument(
        "--window-title",
        action="append",
        metavar="TITLE",
        default=None,
        help=(
            "Additional window title to accept (repeatable). "
            'e.g. --window-title "chiaki-ng". '
            "Run `youkai-ocr windows` to discover the title of your streaming client. "
            "Also settable via YOUKAI_WINDOW_TITLES env var (comma-separated)."
        ),
    )
    subparsers = parser.add_subparsers(dest="command")

    # -- windows ------------------------------------------------------------------
    subparsers.add_parser(
        "windows",
        help="List all visible windows and show which one the scanner would pick.",
    )

    # -- calibrate ----------------------------------------------------------------
    cal = subparsers.add_parser("calibrate", help="Verify window detection and scale.")
    cal.add_argument(
        "--file", metavar="PATH", help="Use a screenshot file instead of the live window."
    )

    # -- scan-engines -------------------------------------------------------------
    def _add_scan_args(p: argparse.ArgumentParser, default_output: str, subject: str) -> None:
        p.add_argument(
            "--output",
            "-o",
            default=default_output,
            metavar="PATH",
            help=f"Output JSON path (default: {default_output}).",
        )
        p.add_argument(
            "--archive-dir",
            "-a",
            default=None,
            metavar="DIR",
            help="Save raw field crops here for debugging.",
        )
        p.add_argument(
            "--file",
            "-f",
            default=None,
            metavar="PATH",
            help="Offline mode: use a static screenshot instead of the live window.",
        )
        p.add_argument(
            "--crop",
            default=None,
            metavar="X0,Y0,X1,Y1",
            help="Crop screenshot to game area before calibrating.",
        )
        p.add_argument(
            "--engine",
            default="tesseract",
            choices=["tesseract"],
            help="OCR engine (default: tesseract).",
        )

    scan_eng = subparsers.add_parser(
        "scan-engines", help="Scan the W-Engine inventory and export JSON."
    )
    _add_scan_args(scan_eng, "export/engines.json", "W-Engine")

    # -- scan-agents --------------------------------------------------------------
    scan_agt = subparsers.add_parser(
        "scan-agents", help="Scan agent roster (stats, skills, equipment) and export JSON."
    )
    _add_scan_args(scan_agt, "export/agents.json", "agent")
    scan_agt.add_argument(
        "--skills-file",
        default=None,
        metavar="PATH",
        help="Offline mode: skills-tab screenshot (defaults to --file if omitted).",
    )
    scan_agt.add_argument(
        "--debug-overlays",
        action="store_true",
        help="Also save *_overlay.png frames with click targets + OCR crops drawn "
        "(needs --archive-dir).",
    )

    # -- scan ---------------------------------------------------------------------
    scan = subparsers.add_parser("scan", help="Scan the Drive Disc inventory and export JSON.")
    _add_scan_args(scan, "export/discs.json", "disc")

    # -- revalidate -----------------------------------------------------------------
    revalidate = subparsers.add_parser(
        "revalidate",
        help="Replay an archived disc scan offline through the current validator/repair "
        "tables and write a corrected export (archive-only, no game/pynput).",
    )
    revalidate.add_argument(
        "--archive",
        required=True,
        metavar="DIR",
        help="Archive run dir containing discs.json and disc_NNNN/panel.png crops.",
    )
    revalidate.add_argument(
        "--out", required=True, metavar="PATH", help="Corrected export JSON output path."
    )
    revalidate.add_argument(
        "--report",
        default=None,
        metavar="PATH",
        help="Optional path to write the per-disc violations/repairs report JSON.",
    )
    revalidate.add_argument(
        "--engine",
        default="tesseract",
        choices=["tesseract"],
        help="OCR engine (default: tesseract).",
    )
    revalidate.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Only process the first N discs (for faster dev iteration).",
    )

    # -- scan-all -----------------------------------------------------------------
    scan_all = subparsers.add_parser(
        "scan-all",
        help="Full scan: discs + engines + agents merged into one ZodExport JSON.",
    )
    scan_all.add_argument(
        "--output",
        "-o",
        default="export/youkai_export.json",
        metavar="PATH",
        help="Output JSON path (default: export/youkai_export.json).",
    )
    scan_all.add_argument(
        "--archive-dir",
        "-a",
        default=None,
        metavar="DIR",
        help="Use this directory as the run dir (default: archive/run_<timestamp>).",
    )
    scan_all.add_argument(
        "--resume",
        default=None,
        metavar="DIR",
        help="Resume from an existing run dir; skip phases with completed JSON files.",
    )
    scan_all.add_argument(
        "--engine",
        default="tesseract",
        choices=["tesseract"],
        help="OCR engine (default: tesseract).",
    )
    scan_all.add_argument(
        "--debug-overlays",
        action="store_true",
        help="Also save *_overlay.png agent frames with click targets + OCR crops drawn.",
    )
    scan_all.add_argument(
        "--phases",
        default=None,
        metavar="LIST",
        help="Comma-separated phases to run: engines,discs,agents (default: all).",
    )
    scan_all.add_argument(
        "--agents-only",
        action="store_true",
        help="Deprecated: use --phases agents. Skip disc and engine phases.",
    )
    scan_all.add_argument(
        "--manual-nav",
        action="store_true",
        dest="manual_nav",
        help="Gate each phase with a manual Enter prompt instead of "
        "auto-navigating from the main-menu hub.",
    )
    scan_all.add_argument(
        "--porcelain",
        action="store_true",
        help="Emit machine-readable JSONL progress events on stdout; "
        "redirect human-readable output to stderr.",
    )

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(0)

    # Resolve accepted window titles from all sources (defaults, env, CLI flags)
    # before any subcommand runs, so every capture call uses the merged list.
    from youkai_ocr import capture as _capture

    _capture.set_accepted_titles(
        _capture.resolve_accepted_titles(
            extra=args.window_title,
            env=os.environ.get("YOUKAI_WINDOW_TITLES"),
        )
    )

    try:
        if args.command == "windows":
            _cmd_windows(args)
        elif args.command == "calibrate":
            _cmd_calibrate(args)
        elif args.command == "scan":
            _cmd_scan(args)
        elif args.command == "revalidate":
            _cmd_revalidate(args)
        elif args.command == "scan-engines":
            _cmd_scan_engines(args)
        elif args.command == "scan-agents":
            _cmd_scan_agents(args)
        elif args.command == "scan-all":
            _cmd_scan_all(args)
    except ScreenAssertError as exc:
        print(f"\nABORT — wrong screen: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
