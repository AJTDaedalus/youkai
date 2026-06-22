"""D1 + D2: W-Engine grid navigator and assembler.

Drives the grid navigator (D1) over the W-Engine inventory, crops fields from
each detail panel, runs B2/B3/B4 recognizers, and assembles ZodWEngine objects.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Optional

from PIL import Image

from .capture import CalibrationResult
from .grid import DEFAULT_GRID, GridNavigator, GridParams, make_kill_listener
from .matchers import count_filled_stars, detect_lock_from_text, detect_rarity
from .normalizer import normalize_engine, parse_level_with_ascension
from .recognize import TextRecognizer, make_recognizer
from .zod import ZodExport, ZodWEngine

# ── Storage header: "W-Engine Storage [ <count> / <max> ]" ──────────────────

_ENGINE_COUNT_BBOX = (20, 95, 560, 155)   # same header region as disc storage
_ENGINE_COUNT_RE = re.compile(r"\[\s*(\d+)\s*/\s*(\d+)\s*\]")


def read_engine_count(
    frame: Image.Image, calib: CalibrationResult, recognizer: TextRecognizer
) -> Optional[int]:
    """Read current engine count from the storage header, or None if unreadable."""
    crop = frame.crop(calib.scale_bbox(_ENGINE_COUNT_BBOX))
    text = recognizer.read_line(crop, "white_text_on_dark")
    m = _ENGINE_COUNT_RE.search(text.replace(" ", ""))
    if not m:
        m = re.search(r"(\d+)\s*/\s*(\d+)", text.replace(" ", ""))
    if not m:
        print(f"  [count] engine header OCR did not contain a count: {text!r}")
        return None
    cur, mx = int(m.group(1)), int(m.group(2))
    if not (0 < cur <= mx <= 2000):
        print(f"  [count] implausible engine count {cur}/{mx} from {text!r}; ignoring")
        return None
    return cur

# ── Field bboxes in 1920×1080 reference coords (engine_inventory.detail_panel) ─

_NAME_BBOX = (1421, 270, 1760, 368)
_RARITY_BBOX = (1421, 402, 1452, 436)
_LEVEL_BBOX = (1451, 402, 1640, 436)   # wide enough to include "/60" suffix
_REFINE_BBOX = (1582, 402, 1770, 436)

# Lock strip offsets relative to cell center — identical to disc scanner.
_LOCK_STRIP_DX = (-60, 67)
_LOCK_STRIP_DY = (55, 87)

_LOW_CONF_THRESHOLD = 70.0
_CRITICAL_NAME_THRESHOLD = 30.0

CaptureFunc = Callable[[], Image.Image]


# ── Crop helpers ──────────────────────────────────────────────────────────────

def _crop(frame: Image.Image, calib: CalibrationResult, ref_bbox: tuple) -> Image.Image:
    x0, y0, x1, y1 = ref_bbox
    return frame.crop((
        int(x0 * calib.scale_x), int(y0 * calib.scale_y),
        int(x1 * calib.scale_x), int(y1 * calib.scale_y),
    ))


def _lock_strip(
    frame: Image.Image, calib: CalibrationResult, cell_cx: int, cell_cy: int
) -> Image.Image:
    ref = (
        cell_cx + _LOCK_STRIP_DX[0], cell_cy + _LOCK_STRIP_DY[0],
        cell_cx + _LOCK_STRIP_DX[1], cell_cy + _LOCK_STRIP_DY[1],
    )
    return _crop(frame, calib, ref)


# ── Single-engine extraction ──────────────────────────────────────────────────

def _extract_engine(
    frame: Image.Image,
    calib: CalibrationResult,
    cell_cx: int,
    cell_cy: int,
    recognizer: TextRecognizer,
    archive_dir: Optional[Path],
    engine_idx: int,
) -> tuple[Optional[ZodWEngine], dict]:
    """Extract one ZodWEngine from a captured frame.

    Returns (engine, confidence_map). engine is None on critical failure.
    """
    conf: dict[str, float] = {}

    # ── Engine name ───────────────────────────────────────────────────────
    name_crop = _crop(frame, calib, _NAME_BBOX)
    name_text = recognizer.read_text(name_crop, "white_text_on_dark").replace("\n", " ").strip()
    key, name_conf = normalize_engine(name_text)
    conf["key"] = name_conf

    # ── Rarity ────────────────────────────────────────────────────────────
    rarity_crop = _crop(frame, calib, _RARITY_BBOX)
    try:
        rarity = detect_rarity(rarity_crop)
        conf["rarity"] = 95.0
    except ValueError:
        rarity = 4
        conf["rarity"] = 0.0

    # ── Level + ascension (derived from "Lv. N/MAX") ──────────────────────
    level_crop = _crop(frame, calib, _LEVEL_BBOX)
    level_text = recognizer.read_line(level_crop, "white_text_on_dark")
    level, ascension = parse_level_with_ascension(level_text)
    conf["level"] = 90.0 if 0 <= level <= 60 else 0.0
    conf["ascension"] = 90.0 if 0 <= ascension <= 5 else 0.0

    # ── Refinement (filled gold stars 1–5) ───────────────────────────────
    refine_crop = _crop(frame, calib, _REFINE_BBOX)
    refinement = count_filled_stars(refine_crop)
    conf["refinement"] = 80.0 if 1 <= refinement <= 5 else 0.0

    # ── Lock (from cell thumbnail level strip) ────────────────────────────
    lock_strip = _lock_strip(frame, calib, cell_cx, cell_cy)
    lock_text = recognizer.read_text(lock_strip, "white_text_on_dark")
    lock = detect_lock_from_text(lock_text)
    conf["lock"] = 80.0

    # ── Archive ────────────────────────────────────────────────────────────
    if archive_dir is not None:
        dd = archive_dir / f"engine_{engine_idx:04d}"
        dd.mkdir(parents=True, exist_ok=True)
        _crop(frame, calib, (1421, 100, 1860, 870)).save(dd / "panel.png")
        name_crop.save(dd / "name.png")
        rarity_crop.save(dd / "rarity.png")
        level_crop.save(dd / "level.png")
        refine_crop.save(dd / "refinement.png")

    if not key or name_conf < _CRITICAL_NAME_THRESHOLD:
        # Empty key = normalize_engine rejected a below-floor match (T2); surface as
        # critical_fail/unknown_engine rather than emitting a wrong or blank key.
        return (None, conf)

    engine = ZodWEngine(
        key=key,
        level=level,
        ascension=ascension,
        refinement=refinement,
        location="",
        lock=lock,
    )
    return (engine, conf)


# ── Public scanner ────────────────────────────────────────────────────────────

def scan_engines(
    capture_fn: CaptureFunc,
    calib: CalibrationResult,
    archive_dir: Optional[Path] = None,
    grid: GridParams = DEFAULT_GRID,
    engine: str = "tesseract",
    on_item: Optional[callable] = None,
) -> tuple[list[ZodWEngine], list[dict]]:
    """Scan the W-Engine inventory. Game must already be on that screen.

    on_item: optional callback(scanned, total) called after each cell is processed.
    total is the count from the storage header (int) or None if unreadable.

    Returns (engines, issues). issues lists per-engine problems for the review report.
    """
    recognizer = make_recognizer(engine)
    kill_event, listener = make_kill_listener()
    navigator = GridNavigator(capture_fn, calib, grid, kill_event)

    # Read the engine count from the header so traversal is fully deterministic
    # (same pattern as disc scanner: no phantom cells, correct last-row width).
    preflight = capture_fn()
    total_engines = read_engine_count(preflight, calib, recognizer)
    if total_engines is None:
        print("  [wengine] could not read engine count; falling back to thumb-stop")

    engines: list[ZodWEngine] = []
    issues: list[dict] = []
    scanned = 0

    try:
        for cell_idx, visual_row, frame in navigator.scan(total_engines):
            col = cell_idx % grid.columns
            cx, cy = grid.cell_center(col, visual_row)

            eng, conf = _extract_engine(
                frame, calib, cx, cy, recognizer, archive_dir, cell_idx
            )

            scanned += 1
            if on_item is not None:
                on_item(scanned, total_engines)

            if eng is None:
                issues.append({"cell": cell_idx, "status": "critical_fail", "confidence": conf})
            else:
                low = {k: v for k, v in conf.items() if v < _LOW_CONF_THRESHOLD}
                if low:
                    issues.append({
                        "cell": cell_idx,
                        "engine": eng.to_dict(),
                        "status": "low_confidence",
                        "fields": low,
                    })
                engines.append(eng)
    finally:
        listener.stop()

    return engines, issues


# ── Equip-slot engine extraction (agent equipment select-view) ───────────────
# Layout: when the agent engine slot is clicked, the game shows the W-Engine
# inventory with a detail panel on the right.  The currently-equipped engine is
# highlighted in the grid and its info shown in the detail panel.
#
# Detail panel (1920×1080 reference coords, past the left thumbnail):
#   x: 537–1060  (thumbnail occupies ~455–537)
#   Name row:     y=118–165  (1-line name) or y=118–210 (2-line, ~40px taller)
#   Level row:    y=165–210  (1-line) or y=210–250 (2-line)
#   Star row:     y=210–255  (1-line) or y=250–295 (2-line)
#
# Stars in this view are white OUTLINE stars (refinement=1 shows no gold fill).
# Gold fill appears only for refinement>1 and is detected by count_filled_stars.

_EE_X0 = 537    # left edge of detail text (past thumbnail)
_EE_X1 = 1060   # right edge of detail panel
_EE_NAME_Y0 = 118   # name always starts here
_EE_NAME_Y1 = 215   # covers both 1-line and 2-line names
_EE_SCAN_Y1 = 310   # bottom of combined name+level+star scan region
_EE_STAR_X0 = 600   # left edge of star row (past specialty icon)
_EE_STAR_Y0 = 210   # star row start covering 1-line and 2-line cases
_EE_STAR_Y1 = 305   # star row end
_EE_LV_RE = re.compile(r"[Ll][vV][.\s]+(\d+)\s*/\s*(\d+)")


def scan_equipped_engine_frame(
    frame: Image.Image,
    calib: CalibrationResult,
    agent_key: str = "",
    archive_dir: Optional[Path] = None,
    engine: str | TextRecognizer = "tesseract",
) -> Optional[ZodWEngine]:
    """Extract a ZodWEngine from an equip-slot select-view frame.

    Reads the engine detail panel shown in the agent equipment screen after
    clicking the W-Engine slot (equip_slot_6.png from the archive).

    Returns None on critical failure (key confidence too low).
    """
    recognizer = engine if isinstance(engine, TextRecognizer) else make_recognizer(engine)

    def _c(ref_bbox: tuple) -> Image.Image:
        x0, y0, x1, y1 = ref_bbox
        return frame.crop((
            int(x0 * calib.scale_x), int(y0 * calib.scale_y),
            int(x1 * calib.scale_x), int(y1 * calib.scale_y),
        ))

    # ── Name + level block (covers 1-line and 2-line names) ──────────────────
    block_crop = _c((_EE_X0, _EE_NAME_Y0, _EE_X1, _EE_SCAN_Y1))
    block_text = recognizer.read_text(block_crop, "white_text_on_dark")

    # ── Engine key ────────────────────────────────────────────────────────────
    name_crop = _c((_EE_X0, _EE_NAME_Y0, _EE_X1, _EE_NAME_Y1))
    name_text = recognizer.read_text(name_crop, "white_text_on_dark").replace("\n", " ").strip()
    key, name_conf = normalize_engine(name_text)
    if not key or name_conf < 30.0:
        return None

    # ── Level + ascension from "Lv. N/MAX" in the block ──────────────────────
    m = _EE_LV_RE.search(block_text)
    if m:
        level, ascension = parse_level_with_ascension(f"Lv. {m.group(1)}/{m.group(2)}")
    else:
        level, ascension = 0, 0

    # ── Refinement: count gold-filled stars; default to 1 if none visible ────
    # Stars appear as white outlines at refinement=1; gold fill shows for >1.
    star_crop = _c((_EE_STAR_X0, _EE_STAR_Y0, _EE_X1, _EE_STAR_Y1))
    refinement = count_filled_stars(star_crop)

    # ── Archive ───────────────────────────────────────────────────────────────
    if archive_dir is not None:
        archive_dir.mkdir(parents=True, exist_ok=True)
        name_crop.save(archive_dir / "equip_engine_name.png")
        star_crop.save(archive_dir / "equip_engine_stars.png")

    return ZodWEngine(
        key=key,
        level=level,
        ascension=ascension,
        refinement=refinement,
        location=agent_key,
        lock=False,
    )


# ── Offline single-frame extraction ──────────────────────────────────────────

def scan_single_frame_engine(
    frame: Image.Image,
    calib: CalibrationResult,
    archive_dir: Optional[Path] = None,
    engine: str = "tesseract",
) -> tuple[Optional[ZodWEngine], dict]:
    """Extract one engine from a static frame — no synthetic input, no navigator.

    Used for offline testing / debugging from reference screenshots.
    Returns (engine, confidence_map). engine is None on critical failure.
    """
    recognizer = make_recognizer(engine)
    cx, cy = DEFAULT_GRID.cell_center(0, 0)
    return _extract_engine(frame, calib, cx, cy, recognizer, archive_dir, 0)


# ── Export ────────────────────────────────────────────────────────────────────

def export_engines(engines: list[ZodWEngine], path: Path) -> None:
    """Write a ZodExport JSON containing the given engines (discs=[], characters=[])."""
    export = ZodExport(weapons=engines)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(export.to_json(), encoding="utf-8")
