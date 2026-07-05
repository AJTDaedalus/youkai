"""C2 + C3: Drive Disc assembler and ZodExport emitter.

Drives the grid navigator (C1), crops fields from each detail panel,
runs B2/B3/B4 recognizers, and assembles ZodDisc objects.
C3: export_discs() writes a ZodExport JSON ready for import.
"""
from __future__ import annotations

import os
import queue
import re
from pathlib import Path
from threading import Lock, Thread
from typing import Callable, Optional

from PIL import Image
from rapidfuzz import fuzz

from .capture import CalibrationResult
from .disc_rules import evidence_from_conf, repair_disc
from .grid import DEFAULT_GRID, GridNavigator, GridParams, make_kill_listener
from .matchers import detect_lock_from_text, detect_rarity
from .normalizer import (
    normalize_disc_set,
    normalize_main_stat,
    normalize_substat,
    parse_level,
    parse_numeric,
    parse_panel_slot,
    parse_roll_suffix,
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

# Panel origin for the disc inventory detail view. All _*_REL constants below
# are panel-local (relative to this origin). Call _abs_bbox(rel, origin) to
# translate before passing to _crop().
_PANEL_ORIGIN: tuple[int, int] = (1421, 100)
_PANEL_W = 439   # 1860 - 1421
_PANEL_H = 770   # 870  - 100

# Kept for make_golden_draft.py and any other callers that import _PANEL_BBOX.
_PANEL_BBOX = (_PANEL_ORIGIN[0], _PANEL_ORIGIN[1],
               _PANEL_ORIGIN[0] + _PANEL_W, _PANEL_ORIGIN[1] + _PANEL_H)

# G5 slot-recovery windows, panel-local. Pass A catches 1-line names whose
# "[N]" is pushed right (past the clipped title bbox); Pass B catches 2-line
# names whose "[N]" wraps down-left (x capped at 180 to exclude the bright icon).
_PANEL_SLOT_PASS_A = (0, 158, 300, 210)
_PANEL_SLOT_PASS_B = (0, 200, 180, 290)

# Panel-local field bboxes (x0, y0, x1, y1 relative to _PANEL_ORIGIN).
_TITLE_REL        = (0,   170, 239, 285)   # abs: (1421,270,1660,385)
_RARITY_REL       = (0,   302,  31, 336)   # abs: (1421,402,1452,436)
_LEVEL_REL        = (30,  302, 161, 336)   # abs: (1451,402,1582,436)
_MAIN_NAME_REL    = (0,   390, 299, 427)   # abs: (1421,490,1720,527)
_MAIN_VAL_REL     = (299, 390, 434, 427)   # abs: (1720,490,1855,527)
_SUBSTAT_RELS: list[tuple[tuple, tuple]] = [
    ((0, 466, 339, 507), (339, 466, 434, 507)),   # abs rows: 566-607
    ((0, 517, 339, 558), (339, 517, 434, 558)),   # abs rows: 617-658
    ((0, 568, 339, 609), (339, 568, 434, 609)),   # abs rows: 668-709
    ((0, 620, 339, 660), (339, 620, 434, 660)),   # abs rows: 720-760
]


def _abs_bbox(rel: tuple[int, int, int, int], origin: tuple[int, int]) -> tuple[int, int, int, int]:
    ox, oy = origin
    x0, y0, x1, y1 = rel
    return (x0 + ox, y0 + oy, x1 + ox, y1 + oy)

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
_PERCENT_TO_FLAT: dict[str, str] = {v: k for k, v in _FLAT_TO_PERCENT.items()}

# Plausible substat value ranges (B4 range validators; F2 golden-set finding).
# ZZZ substats roll fixed increments of the base value, 1–6 rolls on an S disc,
# so value ∈ [base, base×6]. Bounds are padded (×8 upper) to avoid rejecting a
# legitimate read on A/B discs; they only arbitrate between conflicting OCR
# scales (decimal-point loss reads "2.4" as "24" — 10× out, far past the pad).
_SUBSTAT_RANGE: dict[str, tuple[float, float]] = {
    "hp": (112, 896), "atk": (19, 152), "def": (15, 120),
    "hp_": (3, 24), "atk_": (3, 24), "def_": (4.8, 38.4),
    "crit_": (2.4, 19.2), "crit_dmg_": (4.8, 38.4),
    "pen": (9, 72), "anomProf": (9, 72),
}


def _value_plausible(stat_key: str, val: float) -> bool:
    rng = _SUBSTAT_RANGE.get(stat_key)
    return rng is None or (rng[0] <= val <= rng[1])

# Minimum confidence for accepting a field match (below → emit to issues).
_LOW_CONF_THRESHOLD = 70.0

CaptureFunc = Callable[[], Image.Image]

# disc_rules.Violation.field → the conf dict's confidence-key namespace (T9):
# validate_disc names fields after the ZodDisc schema (main_stat_key, slot_key,
# substat[i], …); conf's confidence keys use the OCR pipeline's own names
# (main_stat, slot, substat_{i+1}, …). Map one to the other so a violation can
# push the right field's confidence down.
_VIOLATION_FIELD_TO_CONF_KEY = {
    "rarity": "rarity",
    "level": "level",
    "slot_key": "slot",
    "main_stat_key": "main_stat",
    "main_stat_value": "main_stat",
}
_SUBSTAT_VIOLATION_FIELD_RE = re.compile(r"^substat\[(\d+)\]$")


def _conf_key_for_violation_field(field: str) -> str:
    m = _SUBSTAT_VIOLATION_FIELD_RE.match(field)
    if m:
        return f"substat_{int(m.group(1)) + 1}"
    return _VIOLATION_FIELD_TO_CONF_KEY.get(field, field)


def _repair_and_fold_violations(disc: ZodDisc, conf: dict) -> ZodDisc:
    """Repair `disc` via disc_rules, folding the result back into conf/issues.

    A residual violation pushes that field's confidence to <=30 — a violated
    field must never surface as trustworthy (DESIGN Integration point 1).
    An applied repair is recorded in conf["_repairs"] (popped by the issues
    emitter, never compared as a confidence float).
    """
    evidence = evidence_from_conf(conf, len(disc.substats))
    result = repair_disc(disc, evidence)
    if result.repairs:
        conf["_repairs"] = [
            {"field": r.field, "before": r.before, "after": r.after, "rule": r.rule}
            for r in result.repairs
        ]
    for v in result.violations:
        key = _conf_key_for_violation_field(v.field)
        conf[key] = min(conf.get(key, 100.0), 30.0)
    return result.disc


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
    panel_origin: tuple[int, int] = _PANEL_ORIGIN,
) -> tuple[Optional[ZodDisc], dict]:
    """Extract one ZodDisc from a captured frame.

    Returns (disc, confidence_map). disc is None on critical failure.
    confidence_map maps field names → 0-100 confidence scores.

    panel_origin: top-left of the detail panel in 1920×1080 reference coords.
    Defaults to _PANEL_ORIGIN (inventory view). Pass a different origin to read
    from the agent equipment select-view frame (T1.2).
    """
    conf: dict[str, float] = {}

    # ── Title: set name + slot ─────────────────────────────────────────────
    title_crop = _crop(frame, calib, _abs_bbox(_TITLE_REL, panel_origin))
    title_text = recognizer.read_text(title_crop, "white_text_on_dark").replace("\n", " ").strip()

    set_key, set_conf = normalize_disc_set(title_text)
    if not set_key:
        # Dim-pass retry (T12): the bright threshold intermittently blanks a
        # perfectly legible title ("Dawn's Bloom" read as "v Gi s Bloom") —
        # same failure the substat rows already recover from. Adopt the dim
        # read only when it clears the set floor; cap conf at 65 so the disc
        # still surfaces in issues for review (dim-read precedent).
        dim_text = recognizer.read_text(title_crop, "white_text_on_dark_dim").replace("\n", " ").strip()
        dim_key, dim_conf = normalize_disc_set(dim_text)
        if dim_key:
            title_text = dim_text
            set_key, set_conf = dim_key, min(dim_conf, 65.0)
    conf["set"] = set_conf

    # Slot trust order (T12): clean-bracket title read, then the panel's
    # dedicated slot widget (G5), then the garble-tolerant title fallback.
    # The old order let a garbled bracket ("[ 4" misread of "[1]", disc_2070)
    # confidently beat the panel widget's correct "[1]" read.
    panel_crop = _crop(frame, calib, _abs_bbox((0, 0, _PANEL_W, _PANEL_H), panel_origin))
    slot = parse_slot(title_text, allow_garbled=False)
    if slot is None:
        slot = parse_slot_from_panel(panel_crop, recognizer)
    if slot is None:
        slot = parse_slot(title_text)
    conf["slot"] = 100.0 if slot else 0.0

    # ── Rarity ────────────────────────────────────────────────────────────
    rarity_crop = _crop(frame, calib, _abs_bbox(_RARITY_REL, panel_origin))
    try:
        rarity = detect_rarity(rarity_crop)
        conf["rarity"] = 95.0
    except ValueError:
        rarity = 4
        conf["rarity"] = 0.0

    # ── Level ──────────────────────────────────────────────────────────────
    level_crop = _crop(frame, calib, _abs_bbox(_LEVEL_REL, panel_origin))
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
    main_name_crop = _crop(frame, calib, _abs_bbox(_MAIN_NAME_REL, panel_origin))
    main_name_text = recognizer.read_line(main_name_crop, "white_text_on_dark").strip()
    main_dim_pass = False
    if not main_name_text:
        # Dim-pass / 2× retries (T12): the bright pass intermittently blanks a
        # legible main-stat name ("Wind DMG Bonus", disc_0576/0618) — mirror
        # the substat rows' fallback ladder. Cap conf at 65 (dim precedent) so
        # a fallback-sourced key is surfaced in issues, never fully trusted.
        main_name_text = recognizer.read_line(main_name_crop, "white_text_on_dark_dim").strip()
        main_dim_pass = True
    if not main_name_text:
        main_name_big = main_name_crop.resize(
            (main_name_crop.width * 2, main_name_crop.height * 2), Image.LANCZOS
        )
        main_name_text = recognizer.read_line(main_name_big, "white_text_on_dark").strip()

    main_key, main_conf = normalize_main_stat(main_name_text, slot or 0)
    if main_dim_pass and main_name_text:
        main_conf = min(main_conf, 65.0)
    conf["main_stat"] = main_conf

    # Main-stat value (T5 evidence): displayed on every panel, exactly
    # determined by (rarity, main_key, level) — disc_rules.validate_disc (T6)
    # uses it as a cross-check on level/rarity/main-key. Same dual-scale vote
    # as substat values (decimal point loss / digit confusion at either scale).
    main_val_crop = _crop(frame, calib, _abs_bbox(_MAIN_VAL_REL, panel_origin))
    main_val_big = main_val_crop.resize(
        (main_val_crop.width * 2, main_val_crop.height * 2), Image.LANCZOS
    )
    mv1 = recognizer.read_line(main_val_crop, "white_text_on_dark").strip()
    mv2 = recognizer.read_line(main_val_big, "white_text_on_dark").strip()
    main_v1, main_v2 = parse_numeric(mv1), parse_numeric(mv2)
    if main_v1 is not None and main_v1 == main_v2:
        main_value = main_v1
    elif main_v1 is None and main_v2 is None:
        main_value = None
    else:
        main_value = main_v2 if main_v2 is not None else main_v1
    if main_value is not None:
        conf["main_stat_value"] = main_value
        conf["main_stat_pct_seen"] = "%" in mv1 or "%" in mv2

    # ── Substats ──────────────────────────────────────────────────────────
    # Row contract (golden-replay/F2): a real substat row always has a numeric
    # value; the row after the last substat is the dim "Set Effect" header.
    # Never break on a single empty OCR read — short names ("HP") and dim rows
    # ("PEN") read empty on the bright pass and were silently dropped pre-F2.
    substats: list[ZodSubstat] = []
    for i, (name_rel, val_rel) in enumerate(_SUBSTAT_RELS):
        name_bbox = _abs_bbox(name_rel, panel_origin)
        val_bbox = _abs_bbox(val_rel, panel_origin)
        name_crop = _crop(frame, calib, name_bbox)
        val_crop = _crop(frame, calib, val_bbox)
        name_text = recognizer.read_line(name_crop, "white_text_on_dark").strip()
        dim_pass = False
        if not name_text or name_text in {"-", "--"}:
            name_text = recognizer.read_line(name_crop, "white_text_on_dark_dim").strip()
            dim_pass = True
        if not name_text or name_text in {"-", "--"}:
            # Short names like "HP" (2 chars) are unreadable at native size;
            # 2× upscale gives Tesseract enough pixels to resolve them.
            name_big = name_crop.resize(
                (name_crop.width * 2, name_crop.height * 2), Image.LANCZOS
            )
            name_text = recognizer.read_line(name_big, "white_text_on_dark").strip()
            dim_pass = False
        if name_text and fuzz.partial_ratio(name_text.lower(), "set effect") >= 75:
            break   # footer header — end of the substat list
        # Read the value at two scales and vote: the decimal point vanishes
        # unpredictably at either scale ("4.8%" → "48%" native, "2.4%" → "24"
        # at 2×). Agreement wins; a conflict is arbitrated by _SUBSTAT_RANGE.
        val_big = val_crop.resize((val_crop.width * 2, val_crop.height * 2), Image.LANCZOS)
        t1 = recognizer.read_line(val_crop, "white_text_on_dark").strip()
        t2 = recognizer.read_line(val_big, "white_text_on_dark").strip()
        v1, v2 = parse_numeric(t1), parse_numeric(t2)
        pct_seen = "%" in t1 or "%" in t2

        if not name_text and v1 is None and v2 is None:
            break   # genuinely empty row — end of the substat list
        stat_key, stat_conf = normalize_substat(name_text) if name_text else ("", 0.0)
        # Roll-count evidence (T4): the "+N" _UPGRADE_RE strips before fuzzy-
        # matching the name is deterministic proof of the line's k-value —
        # captured here, alongside conf, for disc_rules.repair_disc (T6/T7/T9).
        roll_suffix = parse_roll_suffix(name_text) if name_text else None
        if roll_suffix is not None:
            conf[f"substat_{i + 1}_roll_suffix"] = float(roll_suffix)
        conf[f"substat_{i + 1}_pct_seen"] = pct_seen
        if dim_pass:
            stat_conf = min(stat_conf, 65.0)   # surfaced in issues for review

        # Percent upgrade only when the value is plausible as a percent —
        # OCR noise can add a stray '%' to a flat read ("112" → hp_ 112).
        key = stat_key
        if pct_seen and stat_key in _FLAT_TO_PERCENT:
            pct_key = _FLAT_TO_PERCENT[stat_key]
            check = v2 if v2 is not None else v1
            if check is not None and _value_plausible(pct_key, check):
                key = pct_key

        if v1 is not None and v1 == v2:
            val = v1
        elif v1 is None and v2 is None:
            val = 0.0
            stat_conf = min(stat_conf, 30.0)   # value unreadable — flag
        else:
            in_range = [v for v in (v2, v1) if v is not None and _value_plausible(key, v)]
            if in_range:
                val = in_range[0]
                stat_conf = min(stat_conf, 65.0)   # scales disagreed — flag
            else:
                val = v2 if v2 is not None else v1
                stat_conf = min(stat_conf, 30.0)
        # Reverse a percent-key resolution when the value says flat: a dim
        # name read ("HP" → "Hi") can fuzzy-match hp_ directly, but a value
        # like 112 with no '%' in sight is unambiguously the flat stat.
        if not pct_seen and not _value_plausible(key, val):
            flat_key = _PERCENT_TO_FLAT.get(key)
            if flat_key and _value_plausible(flat_key, val):
                key = flat_key
        if val is not None and not _value_plausible(key, val):
            stat_conf = min(stat_conf, 30.0)   # out-of-range — never silent

        conf[f"substat_{i + 1}"] = stat_conf
        substats.append(ZodSubstat(key=key, value=val))

    # ── Archive ────────────────────────────────────────────────────────────
    if archive_dir is not None:
        dd = archive_dir / f"disc_{disc_idx:04d}"
        dd.mkdir(parents=True, exist_ok=True)
        panel_crop.save(dd / "panel.png")
        title_crop.save(dd / "title.png")
        rarity_crop.save(dd / "rarity.png")
        level_crop.save(dd / "level.png")
        main_name_crop.save(dd / "main_name.png")
        main_val_crop.save(dd / "main_val.png")

    # ── Critical failure guard ─────────────────────────────────────────────
    # normalize_disc_set already floors unmapped/uncertain titles to an empty
    # key (T3); an empty set_key here means the title scored below the floor,
    # not a slot-parse failure, so the two get distinct reasons.
    if not slot or not set_key:
        conf["_fail_reason"] = (
            f"no_slot:title={title_text!r}" if not slot
            else f"unknown_set:{set_conf:.0f}:title={title_text!r}"
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
    disc = _repair_and_fold_violations(disc, conf)
    return (disc, conf)


# ── Public scanner ────────────────────────────────────────────────────────────

def scan_discs(
    capture_fn: CaptureFunc,
    calib: CalibrationResult,
    archive_dir: Optional[Path] = None,
    grid: GridParams = DEFAULT_GRID,
    engine: str = "tesseract",
    on_first_item: Optional[callable] = None,
    on_item: Optional[callable] = None,
) -> tuple[list[ZodDisc], list[dict]]:
    """Scan the disc inventory. Game must already be on the disc inventory screen.

    on_first_item: optional callback(disc, conf) called after the first item is
    assembled. Raise RuntimeError from it to abort the scan early.
    on_item: optional callback(scanned, total) called after each cell is processed.
    total is the count from the storage header (int) or None if unreadable.

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
                    n = done[0]
                if on_item is not None:
                    on_item(n, total_discs)
                continue
            with lock:
                results[cell_idx] = (disc, conf)
                done[0] += 1
                n = done[0]
            print(f"\r  read {n}{'/' + str(total_discs) if total_discs else ''} discs…",
                  end="", flush=True)
            if on_item is not None:
                on_item(n, total_discs)
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
            repairs = conf.pop("_repairs", None)
            low = {k: v for k, v in conf.items() if v < _LOW_CONF_THRESHOLD}
            if low or repairs:
                entry = {
                    "cell": cell_idx,
                    "disc": disc.to_dict(),
                    "status": "low_confidence" if low else "repaired",
                }
                if low:
                    entry["fields"] = low
                if repairs:
                    entry["repairs"] = repairs
                issues.append(entry)
            discs.append(disc)

    return discs, issues


# ── Offline single-frame extraction (no pynput / no grid navigation) ─────────

def scan_single_frame(
    frame: "Image.Image",
    calib: CalibrationResult,
    archive_dir: Optional[Path] = None,
    engine: str = "tesseract",
    panel_origin: tuple[int, int] = _PANEL_ORIGIN,
) -> tuple[Optional["ZodDisc"], dict]:
    """Extract one disc from a static frame — no synthetic input, no navigator.

    Assumes the disc detail panel is already visible. Used for offline testing
    and for reading equipped-disc select-view frames (pass panel_origin for
    the equipped view's panel position).

    Returns (disc, confidence_map). disc is None on critical failure.
    """
    recognizer = make_recognizer(engine)
    # Use cell (0, 0) center as a dummy position for the lock strip crop.
    cx, cy = DEFAULT_GRID.cell_center(0, 0)
    return _extract_disc(frame, calib, cx, cy, recognizer, archive_dir, 0, panel_origin)


# ── Equip-slot panel extraction (agent equipment select-view) ─────────────────
# Layout: disc info panel sits at x≈610-1065 on the agent equipment page after
# the user clicks a disc slot. Rarity row Y shifts by ~50px when the set name
# wraps to two lines — we probe both positions and anchor from the rarity icon.
#
# Sub-row Y positions are VARIABLE (each roll-count indicator "+N" takes extra
# vertical space). We use a single PSM-6 block read over the stat region and
# parse the resulting multi-line text — no per-row Y calibration needed.

_EQUIP_X0   = 610    # left edge of disc-info panel (absolute, 1920×1080)
_EQUIP_X1   = 1065   # right edge

_EQUIP_TITLE_Y0 = 120    # title always starts here
_EQUIP_TITLE_Y1 = 215    # tall enough for 2-line set names (covers both cases)
_EQUIP_TITLE_X1 = 870    # title text ends well before the rarity icon

# Rarity icon probe: try 1-line title position first, fall back to 2-line.
# Tight 32×28px crop centred on the icon avoids the dark surround that caused p75
# to miss the golden S-rank centroid when using the wider 38×48px cell crop.
_EQUIP_RARITY_PROBE_YS   = (165, 215)
_EQUIP_RARITY_ICON_X0    = 614   # tight icon crop left edge
_EQUIP_RARITY_ICON_X1    = 646   # tight icon crop right edge
_EQUIP_RARITY_ICON_DY0   = 12    # icon crop top relative to probe y0
_EQUIP_RARITY_ICON_DY1   = 40    # icon crop bottom relative to probe y0
_EQUIP_RARITY_H          = 48    # full rarity/level row height (for level bbox)

# Block read: from rarity_y+100 (just past the "Main Stat" dim header) to
# rarity_y+420 (covers 4 substats with roll indicators + "Set Effect" line).
_EQUIP_BLOCK_DY0 = 100
_EQUIP_BLOCK_DY1 = 420

# Lines matching these (case-insensitive) are section headers — skip them.
_EQUIP_HEADER_LINES = frozenset({"main stat", "sub-stats", "sub stats", "substats"})


def _equip_detect_rarity(
    frame: Image.Image, calib: CalibrationResult
) -> tuple[int, int]:
    """Probe for the rarity icon in the equip-slot panel; return (rarity, rarity_y).

    Tries 1-line-title position first (y=165), then 2-line-title (y=215).
    Falls back to 4 (S-rank) and y=165 if neither probe succeeds.
    """
    for y0 in _EQUIP_RARITY_PROBE_YS:
        crop = _crop(frame, calib, (
            _EQUIP_RARITY_ICON_X0, y0 + _EQUIP_RARITY_ICON_DY0,
            _EQUIP_RARITY_ICON_X1, y0 + _EQUIP_RARITY_ICON_DY1,
        ))
        try:
            return detect_rarity(crop), y0
        except ValueError:
            continue
    return 4, _EQUIP_RARITY_PROBE_YS[0]


def _equip_parse_stat_block(
    block_text: str,
) -> tuple[Optional[tuple[str, str]], list[tuple[str, str, Optional[int]]]]:
    """Parse a PSM-6 block read of the equip-slot disc info panel.

    Returns (main_stat_raw, [(sub_name_raw, sub_val_raw, roll_suffix), ...]).
    sub_name_raw includes the roll-count suffix text if present (e.g.
    "CRIT Rate +3"); normalize_substat handles the stripping internally.
    roll_suffix is the parsed N from that suffix (T4 evidence), or None if
    absent/unreadable. Main stats don't carry a roll suffix (only substats
    upgrade), so main_stat_raw stays a plain (name, val) pair.
    """
    main_raw: Optional[tuple[str, str]] = None
    subs_raw: list[tuple[str, str, Optional[int]]] = []
    in_subs = False

    for raw_line in block_text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        llow = line.lower()
        if llow in _EQUIP_HEADER_LINES:
            if "sub" in llow:
                in_subs = True
            continue
        if fuzz.partial_ratio(llow, "set effect") >= 75:
            break
        if re.match(r"^\+\d+$", line):
            continue   # standalone roll-count indicator

        # Split last token as value; rest is name.
        parts = line.split()
        if not parts:
            continue
        val_text = parts[-1]
        if parse_numeric(val_text) is None:
            continue   # no parseable value → noise line
        name_text = " ".join(parts[:-1]).strip()
        if not name_text:
            continue

        if not in_subs:
            if main_raw is None:
                main_raw = (name_text, val_text)
        else:
            subs_raw.append((name_text, val_text, parse_roll_suffix(name_text)))

    return main_raw, subs_raw


def scan_equipped_disc_frame(
    frame: Image.Image,
    calib: CalibrationResult,
    agent_key: str,
    slot_key: int,
    archive_dir: Optional[Path] = None,
    engine: "str | TextRecognizer" = "tesseract",
) -> tuple[Optional[ZodDisc], dict]:
    """Extract a ZodDisc from an equip-slot select-view frame.

    Reads the disc detail panel shown in the agent equipment screen after
    clicking a disc slot. Location is set to agent_key by construction.

    slot_key: in-game disc slot number (1-6), used as the ZodDisc slot_key
    and for main-stat slot normalization.

    Uses PSM-6 block OCR over the stat region — avoids per-row Y calibration
    and correctly reads values even when sub-row pitch varies with roll counts.

    Returns (disc, confidence_map). disc is None on critical failure.
    """
    recognizer = engine if isinstance(engine, TextRecognizer) else make_recognizer(engine)
    conf: dict[str, float] = {}

    # ── Title → set key ───────────────────────────────────────────────────
    title_crop = _crop(frame, calib, (_EQUIP_X0, _EQUIP_TITLE_Y0, _EQUIP_TITLE_X1, _EQUIP_TITLE_Y1))
    title_text = recognizer.read_text(title_crop, "white_text_on_dark").replace("\n", " ").strip()
    set_key, set_conf = normalize_disc_set(title_text)
    conf["set"] = set_conf
    conf["slot"] = 100.0   # authoritative from caller

    # ── Rarity (anchors the dynamic layout) ────────────────────────────────
    rarity, rarity_y = _equip_detect_rarity(frame, calib)
    conf["rarity"] = 95.0

    # ── Level ──────────────────────────────────────────────────────────────
    level_crop = _crop(frame, calib, (
        _EQUIP_RARITY_ICON_X1 + 5, rarity_y,
        _EQUIP_X1, rarity_y + _EQUIP_RARITY_H,
    ))
    level_text = recognizer.read_line(level_crop, "white_text_on_dark")
    level = parse_level(level_text)
    if level is None:
        m = re.search(r"\d+", level_text)
        level = int(m.group()) if m else 0
    conf["level"] = 90.0 if 0 <= level <= 15 else 0.0

    # ── Main stat + substats (single PSM-6 block read) ────────────────────
    block_crop = _crop(frame, calib, (
        _EQUIP_X0, rarity_y + _EQUIP_BLOCK_DY0,
        _EQUIP_X1, rarity_y + _EQUIP_BLOCK_DY1,
    ))
    block_text = recognizer.read_text(block_crop, "white_text_on_dark")
    main_raw, subs_raw = _equip_parse_stat_block(block_text)

    # Main stat
    if main_raw is not None:
        main_name_text, main_val_text = main_raw
        main_key, main_conf = normalize_main_stat(main_name_text, slot_key)
        pct_seen = "%" in main_val_text
        if pct_seen and main_key in _FLAT_TO_PERCENT:
            main_key = _FLAT_TO_PERCENT[main_key]
        main_value = parse_numeric(main_val_text)
        if main_value is not None:
            conf["main_stat_value"] = main_value
            conf["main_stat_pct_seen"] = pct_seen
    else:
        main_key, main_conf = "", 0.0
    conf["main_stat"] = main_conf

    # Substats
    substats: list[ZodSubstat] = []
    for i, (name_text, val_text, roll_suffix) in enumerate(subs_raw[:4]):
        stat_key, stat_conf = normalize_substat(name_text)
        if roll_suffix is not None:
            conf[f"substat_{i + 1}_roll_suffix"] = float(roll_suffix)
        pct_seen = "%" in val_text
        conf[f"substat_{i + 1}_pct_seen"] = pct_seen
        val = parse_numeric(val_text)
        if val is None:
            val = 0.0
            stat_conf = min(stat_conf, 30.0)

        key = stat_key
        if pct_seen and stat_key in _FLAT_TO_PERCENT:
            pct_key = _FLAT_TO_PERCENT[stat_key]
            if _value_plausible(pct_key, val):
                key = pct_key
        if not pct_seen and not _value_plausible(key, val):
            flat_key = _PERCENT_TO_FLAT.get(key)
            if flat_key and _value_plausible(flat_key, val):
                key = flat_key
        if not _value_plausible(key, val):
            stat_conf = min(stat_conf, 30.0)

        conf[f"substat_{i + 1}"] = stat_conf
        substats.append(ZodSubstat(key=key, value=val))

    # ── Archive ────────────────────────────────────────────────────────────
    if archive_dir is not None:
        archive_dir.mkdir(parents=True, exist_ok=True)
        title_crop.save(archive_dir / f"equip_disc_s{slot_key}_title.png")
        block_crop.save(archive_dir / f"equip_disc_s{slot_key}_block.png")

    if not set_key:
        conf["_fail_reason"] = f"unknown_set:{set_conf:.0f}:title={title_text!r}"
        return (None, conf)

    disc = ZodDisc(
        set_key=set_key,
        slot_key=str(slot_key),
        level=level,
        rarity=rarity,
        main_stat_key=main_key,
        location=agent_key,
        lock=False,
        substats=substats,
    )
    disc = _repair_and_fold_violations(disc, conf)
    return (disc, conf)


# ── C3: Export ────────────────────────────────────────────────────────────────

def export_discs(discs: list[ZodDisc], path: Path) -> None:
    """Write a ZodExport JSON containing the given discs (weapons=[], characters=[])."""
    export = ZodExport(discs=discs)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(export.to_json(), encoding="utf-8")
