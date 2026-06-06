"""C2 + C3: Drive Disc assembler and ZodExport emitter.

Drives the grid navigator (C1), crops fields from each detail panel,
runs B2/B3/B4 recognizers, and assembles ZodDisc objects.
C3: export_discs() writes a ZodExport JSON ready for import.
"""
from __future__ import annotations

import os
import queue
import re
import time
from pathlib import Path
from threading import Lock, Thread
from typing import Callable, Optional

from PIL import Image

from .capture import CalibrationResult
from .grid import DEFAULT_GRID, GridNavigator, GridParams, make_kill_listener
from .matchers import detect_lock_from_text, detect_rarity
from .normalizer import (
    normalize_disc_set,
    normalize_main_stat,
    normalize_substat,
    parse_level,
    parse_numeric,
    parse_panel_slot,
    parse_slot,
)
from .recognize import TextRecognizer, make_recognizer
from .zod import ZodDisc, ZodExport, ZodSubstat

# ── Storage header: "Drive Disc Storage [ <count> / <max> ]" ────────────────

_STORAGE_COUNT_BBOX = (20, 95, 560, 155)
_STORAGE_COUNT_RE = re.compile(r"\[\s*(\d+)\s*/\s*(\d+)\s*\]")


def read_disc_count(
    frame: Image.Image, calib: CalibrationResult, recognizer: TextRecognizer
) -> Optional[int]:
    """Read the current disc count from the storage header, or None if unreadable.

    The count drives deterministic grid traversal (exact row count), so it is far
    more reliable than detecting end-of-inventory from near-identical disc panels.
    """
    crop = frame.crop(calib.scale_bbox(_STORAGE_COUNT_BBOX))
    text = recognizer.read_line(crop, "white_text_on_dark")
    m = _STORAGE_COUNT_RE.search(text.replace(" ", ""))
    if not m:
        # Fallback: any "N/M" pair anywhere in the line.
        m = re.search(r"(\d+)\s*/\s*(\d+)", text.replace(" ", ""))
    if not m:
        print(f"  [count] header OCR did not contain a count: {text!r}")
        return None
    cur, mx = int(m.group(1)), int(m.group(2))
    if not (0 < cur <= mx <= 6000):     # sanity-bound an OCR misread
        print(f"  [count] implausible count {cur}/{mx} from {text!r}; ignoring")
        return None
    return cur


# ── Field bboxes in 1920×1080 reference coords (disc_inventory.detail_panel) ─

# Full detail panel (also saved to archive/). Reference origin = (1421, 100);
# the G5 panel-slot windows below are panel-local (relative to this origin).
_PANEL_BBOX = (1421, 100, 1860, 870)
_PANEL_W = _PANEL_BBOX[2] - _PANEL_BBOX[0]   # 439
_PANEL_H = _PANEL_BBOX[3] - _PANEL_BBOX[1]   # 770

# G5 slot-recovery windows, panel-local. Pass A catches 1-line names whose
# "[N]" is pushed right (past the clipped title bbox); Pass B catches 2-line
# names whose "[N]" wraps down-left (x capped at 180 to exclude the bright icon).
_PANEL_SLOT_PASS_A = (0, 158, 300, 210)
_PANEL_SLOT_PASS_B = (0, 200, 180, 290)

_TITLE_BBOX = (1421, 270, 1660, 385)
_RARITY_BBOX = (1421, 402, 1452, 436)
_LEVEL_BBOX = (1451, 402, 1582, 436)
_MAIN_NAME_BBOX = (1421, 490, 1720, 527)
_MAIN_VAL_BBOX = (1720, 490, 1855, 527)
_SUBSTAT_BBOXES: list[tuple[tuple, tuple]] = [
    ((1421, 566, 1760, 607), (1760, 566, 1855, 607)),
    ((1421, 617, 1760, 658), (1760, 617, 1855, 658)),
    ((1421, 668, 1760, 709), (1760, 668, 1855, 709)),
    ((1421, 720, 1760, 760), (1760, 720, 1855, 760)),
]

# Lock detection: crop bottom strip of each thumbnail cell to read "Lv. N [L]" text.
# Offsets are relative to cell center in reference coords.
_LOCK_STRIP_DX = (-60, 67)
_LOCK_STRIP_DY = (55, 87)

# Flat → percent key remapping: if the OCR value has "%" and the stat resolved
# to the flat key, upgrade to the percent key.
_FLAT_TO_PERCENT: dict[str, str] = {
    "hp": "hp_",
    "atk": "atk_",
    "def": "def_",
}

# Minimum confidence for accepting a field match (below → emit to issues).
_LOW_CONF_THRESHOLD = 70.0
# Below this set confidence the whole disc is considered a critical failure.
_CRITICAL_SET_THRESHOLD = 30.0

CaptureFunc = Callable[[], Image.Image]


# ── Crop helpers ──────────────────────────────────────────────────────────────

def _crop(frame: Image.Image, calib: CalibrationResult, ref_bbox: tuple) -> Image.Image:
    x0, y0, x1, y1 = ref_bbox
    return frame.crop((
        int(x0 * calib.scale_x), int(y0 * calib.scale_y),
        int(x1 * calib.scale_x), int(y1 * calib.scale_y),
    ))


def parse_slot_from_panel(
    panel: Image.Image, recognizer: TextRecognizer
) -> Optional[int]:
    """G5 tier-3 slot fallback: two-pass digit+bracket OCR over the un-clipped panel.

    *panel* is the detail-panel crop (reference bbox ``_PANEL_BBOX``) at any
    calibration scale; the panel-local windows are scaled to its actual size.
    Runs only when the title-text ``parse_slot`` (tier-1) returns None, so it
    adds no cadence cost to the common path and cannot regress a passing disc.
    """
    sx = panel.width / _PANEL_W
    sy = panel.height / _PANEL_H

    def _win(box: tuple[int, int, int, int]) -> Image.Image:
        x0, y0, x1, y1 = box
        return panel.crop((int(x0 * sx), int(y0 * sy), int(x1 * sx), int(y1 * sy)))

    pass_a = recognizer.read_slot(_win(_PANEL_SLOT_PASS_A), "white_text_on_dark")
    pass_b = recognizer.read_slot(_win(_PANEL_SLOT_PASS_B), "white_text_on_dark")
    return parse_panel_slot(pass_a, pass_b)


def _lock_strip(
    frame: Image.Image, calib: CalibrationResult, cell_cx: int, cell_cy: int
) -> Image.Image:
    ref = (
        cell_cx + _LOCK_STRIP_DX[0], cell_cy + _LOCK_STRIP_DY[0],
        cell_cx + _LOCK_STRIP_DX[1], cell_cy + _LOCK_STRIP_DY[1],
    )
    return _crop(frame, calib, ref)


# ── Single-disc extraction ────────────────────────────────────────────────────

def _extract_disc(
    frame: Image.Image,
    calib: CalibrationResult,
    cell_cx: int,
    cell_cy: int,
    recognizer: TextRecognizer,
    archive_dir: Optional[Path],
    disc_idx: int,
) -> tuple[Optional[ZodDisc], dict]:
    """Extract one ZodDisc from a captured frame.

    Returns (disc, confidence_map). disc is None on critical failure.
    confidence_map maps field names → 0-100 confidence scores.
    """
    conf: dict[str, float] = {}

    # ── Title: set name + slot ─────────────────────────────────────────────
    title_crop = _crop(frame, calib, _TITLE_BBOX)
    title_text = recognizer.read_text(title_crop, "white_text_on_dark").replace("\n", " ").strip()

    panel_crop = _crop(frame, calib, _PANEL_BBOX)
    slot = parse_slot(title_text)
    if slot is None:
        # Tier-3 fallback: long names clip/wrap the title "[N]"; recover it from
        # the un-clipped panel (G5 / D-slot-panel-fallback). Runs only on miss.
        slot = parse_slot_from_panel(panel_crop, recognizer)
    conf["slot"] = 100.0 if slot else 0.0

    set_key, set_conf = normalize_disc_set(title_text)
    conf["set"] = set_conf

    # ── Rarity ────────────────────────────────────────────────────────────
    rarity_crop = _crop(frame, calib, _RARITY_BBOX)
    try:
        rarity = detect_rarity(rarity_crop)
        conf["rarity"] = 95.0
    except ValueError:
        rarity = 4
        conf["rarity"] = 0.0

    # ── Level ──────────────────────────────────────────────────────────────
    level_crop = _crop(frame, calib, _LEVEL_BBOX)
    level_text = recognizer.read_line(level_crop, "white_text_on_dark")
    level = parse_level(level_text)
    if level is None:
        m = re.search(r"\d+", level_text)
        level = int(m.group()) if m else 0
    conf["level"] = 90.0 if 0 <= level <= 15 else 0.0

    # ── Lock (from cell thumbnail level strip) ─────────────────────────────
    lock_strip = _lock_strip(frame, calib, cell_cx, cell_cy)
    lock_text = recognizer.read_text(lock_strip, "white_text_on_dark")
    lock = detect_lock_from_text(lock_text)
    conf["lock"] = 80.0

    # ── Main stat ─────────────────────────────────────────────────────────
    main_name_crop = _crop(frame, calib, _MAIN_NAME_BBOX)
    main_name_text = recognizer.read_line(main_name_crop, "white_text_on_dark").strip()

    main_key, main_conf = normalize_main_stat(main_name_text, slot or 0)
    conf["main_stat"] = main_conf

    # ── Substats ──────────────────────────────────────────────────────────
    substats: list[ZodSubstat] = []
    for i, (name_bbox, val_bbox) in enumerate(_SUBSTAT_BBOXES):
        name_crop = _crop(frame, calib, name_bbox)
        val_crop = _crop(frame, calib, val_bbox)
        name_text = recognizer.read_text(name_crop, "white_text_on_dark").strip()
        val_text = recognizer.read_line(val_crop, "white_text_on_dark").strip()

        if not name_text or name_text in {"-", "--", ""}:
            break

        stat_key, stat_conf = normalize_substat(name_text)
        val = parse_numeric(val_text) or 0.0
        if "%" in val_text and stat_key in _FLAT_TO_PERCENT:
            stat_key = _FLAT_TO_PERCENT[stat_key]
        conf[f"substat_{i + 1}"] = stat_conf
        substats.append(ZodSubstat(key=stat_key, value=val))

    # ── Archive ────────────────────────────────────────────────────────────
    if archive_dir is not None:
        dd = archive_dir / f"disc_{disc_idx:04d}"
        dd.mkdir(parents=True, exist_ok=True)
        panel_crop.save(dd / "panel.png")
        title_crop.save(dd / "title.png")
        rarity_crop.save(dd / "rarity.png")
        level_crop.save(dd / "level.png")
        main_name_crop.save(dd / "main_name.png")

    # ── Critical failure guard ─────────────────────────────────────────────
    if not slot or set_conf < _CRITICAL_SET_THRESHOLD:
        conf["_fail_reason"] = (
            f"no_slot:title={title_text!r}" if not slot
            else f"low_set_conf:{set_conf:.0f}:title={title_text!r}"
        )
        return (None, conf)

    disc = ZodDisc(
        set_key=set_key,
        slot_key=str(slot),
        level=level,
        rarity=rarity,
        main_stat_key=main_key,
        location="",
        lock=lock,
        substats=substats,
    )
    return (disc, conf)


# ── Public scanner ────────────────────────────────────────────────────────────

def scan_discs(
    capture_fn: CaptureFunc,
    calib: CalibrationResult,
    archive_dir: Optional[Path] = None,
    grid: GridParams = DEFAULT_GRID,
    engine: str = "tesseract",
    on_first_item: Optional[callable] = None,
) -> tuple[list[ZodDisc], list[dict]]:
    """Scan the disc inventory. Game must already be on the disc inventory screen.

    on_first_item: optional callback(disc, conf) called after the first item is
    assembled. Raise RuntimeError from it to abort the scan early.

    Returns (discs, issues). issues lists per-disc problems for the review report.
    """
    print("  Initialising OCR engine…", end=" ", flush=True)
    recognizer = make_recognizer(engine)
    print("ready.")
    kill_event, listener = make_kill_listener()
    navigator = GridNavigator(capture_fn, calib, grid, kill_event, debug_dir=archive_dir)

    total_discs = read_disc_count(capture_fn(), calib, recognizer)
    if total_discs is None:
        print("  ⚠ could not read disc count from header; using thumb-based end detection.")
    else:
        print(f"  Storage reports {total_discs} discs.")

    # ── Pipeline: navigation (this thread) captures frames and feeds a bounded
    # job queue; a pool of OCR workers drains it in parallel.  The bound applies
    # backpressure so navigation never clicks faster than OCR can keep up, which
    # also caps memory.  pytesseract shells out per call, so threads parallelise.
    n_workers = max(1, min(8, (os.cpu_count() or 4) - 1))
    job_q: queue.Queue = queue.Queue(maxsize=n_workers)
    results: dict[int, tuple] = {}
    lock = Lock()
    done = [0]
    abort: list[Optional[BaseException]] = [None]
    _SENTINEL = object()

    def worker() -> None:
        while True:
            item = job_q.get()
            if item is _SENTINEL:
                return
            cell_idx, visual_row, frame = item
            col = cell_idx % grid.columns
            cx, cy = grid.cell_center(col, visual_row)
            try:
                disc, conf = _extract_disc(
                    frame, calib, cx, cy, recognizer, archive_dir, cell_idx
                )
            except Exception as exc:  # OCR/crop failure → record, keep scanning
                with lock:
                    results[cell_idx] = (None, {"_error": str(exc)})
                    done[0] += 1
                continue
            with lock:
                results[cell_idx] = (disc, conf)
                done[0] += 1
                n = done[0]
            print(f"\r  read {n}{'/' + str(total_discs) if total_discs else ''} discs…",
                  end="", flush=True)
            if cell_idx == 0 and on_first_item is not None:
                try:
                    on_first_item(disc, conf)
                except BaseException as exc:   # early-abort signal from caller
                    abort[0] = exc
                    kill_event.set()

    workers = [Thread(target=worker, name=f"ocr-{i}", daemon=True)
               for i in range(n_workers)]
    for w in workers:
        w.start()

    try:
        for cell_idx, visual_row, frame in navigator.scan(total_discs):
            if kill_event.is_set():
                break
            # kill-responsive put: blocks (backpressure) but still polls Esc.
            while not kill_event.is_set():
                try:
                    job_q.put((cell_idx, visual_row, frame), timeout=0.25)
                    break
                except queue.Full:
                    continue
    finally:
        for _ in workers:
            job_q.put(_SENTINEL)
        for w in workers:
            w.join()
        listener.stop()
        print()

    if abort[0] is not None:
        raise abort[0]

    # Assemble in scan order from the parallel results.
    discs: list[ZodDisc] = []
    issues: list[dict] = []
    for cell_idx in sorted(results):
        disc, conf = results[cell_idx]
        if disc is None:
            entry: dict = {"cell": cell_idx, "status": "critical_fail", "confidence": conf}
            if "_fail_reason" in conf:
                entry["reason"] = conf.pop("_fail_reason")
            issues.append(entry)
        else:
            low = {k: v for k, v in conf.items() if v < _LOW_CONF_THRESHOLD}
            if low:
                issues.append({
                    "cell": cell_idx,
                    "disc": disc.to_dict(),
                    "status": "low_confidence",
                    "fields": low,
                })
            discs.append(disc)

    return discs, issues


# ── Offline single-frame extraction (no pynput / no grid navigation) ─────────

def scan_single_frame(
    frame: "Image.Image",
    calib: CalibrationResult,
    archive_dir: Optional[Path] = None,
    engine: str = "tesseract",
) -> tuple[Optional["ZodDisc"], dict]:
    """Extract one disc from a static frame — no synthetic input, no navigator.

    Assumes the disc detail panel is already visible on the right side of the
    frame. Used for offline testing / debugging from reference screenshots.

    Returns (disc, confidence_map). disc is None on critical failure.
    """
    recognizer = make_recognizer(engine)
    # Use cell (0, 0) center as a dummy position for the lock strip crop.
    cx, cy = DEFAULT_GRID.cell_center(0, 0)
    return _extract_disc(frame, calib, cx, cy, recognizer, archive_dir, 0)


# ── C3: Export ────────────────────────────────────────────────────────────────

def export_discs(discs: list[ZodDisc], path: Path) -> None:
    """Write a ZodExport JSON containing the given discs (weapons=[], characters=[])."""
    export = ZodExport(discs=discs)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(export.to_json(), encoding="utf-8")
