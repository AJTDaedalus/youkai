"""E1–E4 + H1–H3: Agent roster navigator and assembler.

H3 — Equipment-tab slot geometry (re-measured from reference_7) + render-gates.
H2 — scan_roster_grid: grid-based traversal (detect → pHash-dedupe → scroll →
     repeat until no new owned agents); testable in isolation.
H1 — detect_owned_agent_cells: ownership filter via HSV saturation over the
     2-column roster grid on the agent menu screen.
E2 — _extract_base_stats: reads agent key, level, ascension.
E3 — _extract_skills: reads mindscape cinema and six talent levels.

Equipment-tab frames (7 per agent) are archived for E4 cross-reference.

Usage::

    agents, issues = scan_agents(capture_fn, calib, archive_dir=Path("archive"))
"""
from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from threading import Event
from typing import Callable, Generator, Optional

_log = logging.getLogger(__name__)

import cv2
import numpy as np
from PIL import Image

from .capture import CalibrationResult
from .grid import make_kill_listener
from .input_utils import jitter, natural_click
from .normalizer import normalize_agent, normalize_disc_set, normalize_engine, parse_level, parse_slot
from .recognize import TextRecognizer, make_recognizer
from .zod import ZodAgent, ZodDisc, ZodExport, ZodTalent, ZodWEngine

# ── Navigation constants (navigation.yaml, 1920×1080 ref coords) ─────────────

_ROSTER_STRIP_BBOX = (0, 32, 1920, 75)
_ROSTER_CENTER_Y   = 53                  # vertical click target inside strip (strip peak luma y=45-60)
_ROSTER_X_MIN      = 400                 # ignore columns left of this (City/Home UI buttons at x≈40-80)

# Tab bar measured from archive/live_20260605/agent_000/base_stats.png:
# active (yellow) Base Stats bbox x=1011-1294, y=964-1028, center (1152, 996).
# Skills/Equipment inferred from white text clusters and equal-width spacing.
_TAB_BASE_STATS = (1152, 996)
_TAB_SKILLS     = (1435, 996)
_TAB_EQUIPMENT  = (1718, 996)

# ── Agent-menu grid constants (H1 — navigation.yaml agent_menu, 1920×1080 ref coords) ──
# 2-column roster grid on the right side of the agent menu screen (ref_12/13/14).
# Raw screenshots (1922×1112) include 32px chrome; ref coords = raw - (1, 32).
# Ownership filter: 75th-percentile HSV-S over the full column width > threshold.
# Owned portraits are colorful (high S); locked/EMPTY portraits are grayscale (low S).

_AGENT_GRID_LEFT_COL    = (1277, 1537)   # (x0, x1) for left column sampling band
_AGENT_GRID_RIGHT_COL   = (1537, 1797)   # (x0, x1) for right column sampling band
_AGENT_GRID_ROW_CENTERS = [144, 402, 660, 918]  # cy of each visible row
_AGENT_GRID_ROW_STRIDE  = 258            # px between row centers
_AGENT_GRID_ROW_HALF_H  = 100           # ±px around cy for saturation crop
_AGENT_SAT_P75_THRESH   = 15            # 75th-percentile S > this → owned

# 6 disc slots + 1 engine slot, re-measured from reference_7 (H3).
# Engine center raw(1418,590) → game(1417,558).  Disc slots from blob/row-scan analysis.
# TODO(H6): verify slot 2/5 centers in live session (middle-right/left may need ±50px tune).
_DISC_SLOT_CENTERS: list[tuple[int, int]] = [
    (1730, 363),   # slot 1 — upper-right
    (1785, 483),   # slot 2 — right-center  (TODO: verify live)
    (1715, 708),   # slot 3 — lower-right
    (1087, 708),   # slot 4 — lower-left
    (1125, 544),   # slot 5 — left-center   (TODO: verify live)
    (1088, 363),   # slot 6 — upper-left
]
_ENGINE_SLOT_CENTER = (1417, 558)
_ALL_SLOT_CENTERS   = _DISC_SLOT_CENTERS + [_ENGINE_SLOT_CENTER]  # 7 total

# ── Equipment-tab render gates (H3) ──────────────────────────────────────────
# Gate 1: after Equipment-tab click — verify the hexagon is rendered.
# The engine slot is bright white (luma≈210 in ref_7); dark on skills/base-stats (luma≈14).
_EQUIP_GATE_CENTER   = (1417, 558)   # engine slot center, game coords
_EQUIP_GATE_RADIUS   = 20            # px sampling half-window
_EQUIP_GATE_LUMA_MIN = 150           # threshold: >150 → hexagon visible
_EQUIP_GATE_RETRIES  = 2             # attempts before logging fail
_EQUIP_GATE_RETRY_S  = 0.40         # extra settle on re-attempt

# Gate 2: after each slot click — verify the disc/engine selection panel opened.
# When a disc slot is clicked, ZZZ opens the disc-selection view (ref_8).
# The panel area at game(610,120,965,210) has a dark background (dark_frac≈0.16 in ref_8
# vs 0.01 in ref_7 where the bright agent portrait is visible).
_SLOT_PANEL_BBOX          = (610, 120, 965, 210)   # same as _EQUIP_TITLE_BBOX
_SLOT_PANEL_DARK_FRAC_MIN = 0.08    # dark pixels (luma<30) / total > this → panel open
_SLOT_PANEL_RETRY_S       = 0.30    # extra settle on re-attempt

# Base Stats tab field bboxes
_AGENT_NAME_BBOX     = (955, 278, 1350, 330)
_LEVEL_BBOX          = (1060, 460, 1200, 495)  # "Lv. N" badge (re-measured H4)
_ASCENSION_DOTS_BBOX = (955, 332, 1350, 360)

# Skills tab field bboxes (re-measured from reference_4 in H4)
_MINDSCAPE_BBOX = (35, 980, 200, 1030)
_SKILL_LEVEL_BBOXES: list[tuple[int, int, int, int]] = [
    ( 930, 750, 1065, 780),   # basic attack
    (1110, 750, 1245, 780),   # dodge
    (1295, 750, 1425, 780),   # assist
    (1470, 750, 1605, 780),   # special attack
    (1650, 750, 1785, 780),   # chain attack
]
# Core node bboxes A-F: re-measured from reference_4 via teal connected-component
# centroids (H4). Detection samples the 30×30 crop at the bbox center, which lands
# on the bright teal ring (not the dark interior) at these corrected positions.
_CORE_NODE_BBOXES: list[tuple[int, int, int, int]] = [
    (1079, 278, 1139, 338),   # A — center (1109, 308)
    (1031, 446, 1091, 506),   # B — center (1061, 476)
    (1281, 279, 1341, 339),   # C — center (1311, 309)
    (1237, 443, 1297, 503),   # D — center (1267, 473)
    (1487, 278, 1547, 338),   # E — center (1517, 308)
    (1438, 445, 1498, 505),   # F — center (1468, 475)
]

# ── Traversal ─────────────────────────────────────────────────────────────────

AGENT_MAX              = 60      # hard cap (mirrors SCAN_MAX_ROWS in grid.py)
_BACK_ARROW            = (75, 38)    # TODO: verify from live session (ref_3 detail page)
_AGENT_SCROLL_CENTER   = (1537, 660) # grid center for wheel scroll
_SCROLL_TICKS_PER_PAGE = 4           # TODO: refine from H0 live probe
_AGENT_SCROLL_WAIT_S   = 0.60        # settle after scroll
_PHASH_SIZE            = 16          # hash grid dimension (16×16 = 256 bits)
_PHASH_CROP_HALF       = 64          # ±px around cell center for portrait hash crop

# ── Timing ─────────────────────────────────────────────────────────────────────

_PORTRAIT_CLICK_DELAY_S = 0.20   # portrait selection settle
_TAB_CLICK_DELAY_S      = 0.30   # tab render (~AdeptiScanner recheck 300ms)
_SLOT_CLICK_DELAY_S     = 0.20   # equipment slot settle

# ── Detection thresholds ───────────────────────────────────────────────────────

_PORTRAIT_BRIGHTNESS  = 80    # grayscale col-mean above which a column has a portrait
_MIN_PORTRAIT_WIDTH   = 20    # minimum bright-region width (px, scaled space)
_PORTRAIT_MERGE_GAP   = 8     # merge clusters separated by ≤ this (px, scaled)
_ASCENSION_DOT_BRIGHT = 150   # brightness threshold for counting filled promotion dots
_NODE_GREEN_MIN       = 140   # green-channel mean for "lit" node detection
_NODE_TEAL_GR_DIFF    = 50    # green-red difference required to confirm teal (not white)
_LOW_CONF_THRESHOLD   = 70.0
_CRITICAL_CONF        = 30.0

_MINDSCAPE_RE = re.compile(r"(\d)")
_SKILL_DIGIT_RE = re.compile(r"\d+")

# ── Equipment-tab detail panel (slot_detail_panel in navigation.yaml) ──────────
# Panel appears CENTER-SCREEN (x=610-965) when a slot is clicked.
# Title bbox is fixed regardless of line count; only fields below it shift.
_EQUIP_TITLE_BBOX = (610, 120, 965, 210)   # "SetName [N]" for disc, engine name for engine
_EQUIP_LEVEL_BBOX = (648, 210, 965, 260)   # "Lv. N/MAX" row

# Minimum set/engine confidence to treat a slot as equipped (vs empty/dark panel).
_EQUIP_CONF_MIN = 30.0

CaptureFunc = Callable[[], Image.Image]


# ── Crop helper (mirrors disc/engine scanners) ─────────────────────────────────

def _crop(frame: Image.Image, calib: CalibrationResult, ref_bbox: tuple) -> Image.Image:
    x0, y0, x1, y1 = ref_bbox
    return frame.crop((
        int(x0 * calib.scale_x), int(y0 * calib.scale_y),
        int(x1 * calib.scale_x), int(y1 * calib.scale_y),
    ))


# ── Image-analysis helpers ─────────────────────────────────────────────────────

def _find_agent_portraits(frame: Image.Image, calib: CalibrationResult) -> list[int]:
    """Return list of agent portrait x-centers (in 1920×1080 ref coords).

    Detects bright clusters in the roster strip (portrait thumbnails on dark
    background). Returns ref-coord x values suitable for clicking.
    """
    strip = _crop(frame, calib, _ROSTER_STRIP_BBOX)
    arr = np.array(strip.convert("L"))      # shape (H, W_scaled)
    col_means: np.ndarray = arr.mean(axis=0)

    # Zero out the left-side UI zone (City/Home buttons) to avoid false portrait detections.
    min_col = int(_ROSTER_X_MIN * calib.scale_x)
    col_means[:min_col] = 0

    bright = col_means > _PORTRAIT_BRIGHTNESS

    # Collect and merge connected bright column regions.
    regions: list[list[int]] = []          # each entry: [start_x, end_x] in scaled px
    in_region = False
    start = 0
    for x, b in enumerate(bright):
        if b and not in_region:
            start = x
            in_region = True
        elif not b and in_region:
            in_region = False
            if x - start < _MIN_PORTRAIT_WIDTH:
                continue
            if regions and x - 1 - regions[-1][1] <= _PORTRAIT_MERGE_GAP:
                regions[-1][1] = x - 1    # extend previous region
            else:
                regions.append([start, x - 1])
    if in_region:
        end = len(bright) - 1
        if end - start >= _MIN_PORTRAIT_WIDTH:
            if regions and end - regions[-1][1] <= _PORTRAIT_MERGE_GAP:
                regions[-1][1] = end
            else:
                regions.append([start, end])

    # Convert crop-space centers to ref coords.
    # strip starts at ref x=0, so ref_x = crop_center_scaled / calib.scale_x
    return [
        int((r[0] + r[1]) / 2 / calib.scale_x)
        for r in regions
    ]


def detect_owned_agent_cells(
    frame: Image.Image,
    calib: CalibrationResult,
) -> list[tuple[int, int]]:
    """Return click-centers (ref_x, ref_y) of owned agent cells visible in this frame.

    Scans the 2-column roster grid on the right side of the agent menu screen.
    A cell is *owned* when its 75th-percentile HSV saturation exceeds the threshold —
    owned portraits are colorful; locked / EMPTY placeholders are desaturated.

    Returns ref-coord centers suitable for use with calib.to_screen().
    """
    arr = np.array(frame.convert("RGB"))
    bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    frame_h, frame_w = hsv.shape[:2]

    owned: list[tuple[int, int]] = []
    cols = [
        (_AGENT_GRID_LEFT_COL,  (_AGENT_GRID_LEFT_COL[0]  + _AGENT_GRID_LEFT_COL[1])  // 2),
        (_AGENT_GRID_RIGHT_COL, (_AGENT_GRID_RIGHT_COL[0] + _AGENT_GRID_RIGHT_COL[1]) // 2),
    ]

    for ref_cy in _AGENT_GRID_ROW_CENTERS:
        py0 = max(0, int((ref_cy - _AGENT_GRID_ROW_HALF_H) * calib.scale_y))
        py1 = min(frame_h, int((ref_cy + _AGENT_GRID_ROW_HALF_H) * calib.scale_y))

        for (ref_x0, ref_x1), ref_cx in cols:
            px0 = int(ref_x0 * calib.scale_x)
            px1 = int(ref_x1 * calib.scale_x)
            crop_s = hsv[py0:py1, px0:px1, 1]
            if float(np.percentile(crop_s, 75)) > _AGENT_SAT_P75_THRESH:
                owned.append((ref_cx, ref_cy))

    return owned


def _read_skill_badge(badge_crop: Image.Image) -> int | None:
    """Read current skill level from the "N / 12" pill badge via blob-width analysis.

    The badge uses a stylized bold-italic game font that Tesseract cannot reliably
    OCR.  Instead we 3× upscale, threshold at 180 to isolate bright-white pixels,
    restrict to the left 52 % (current level), then classify by connected-component
    widths and fill-ratios:
      - 1 narrow blob  → 1
      - 2 blobs, b2 narrow (w<48)            → 11
      - 2 blobs, b2 wide + high fill (>0.66) → 10  ('0' is round)
      - 2 blobs, b2 wide + lower fill         → 12  ('2' has concave curves)
    Returns None when the badge cannot be classified (callers fall back to 0).
    """
    arr = np.array(badge_crop.convert("RGB"))
    h, w = arr.shape[:2]
    arr_up = cv2.resize(arr, (w * 3, h * 3), interpolation=cv2.INTER_LANCZOS4)
    gray = cv2.cvtColor(arr_up, cv2.COLOR_RGB2GRAY)
    _, binary = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY)
    left_w = int(binary.shape[1] * 0.52)
    left_region = binary[:, :left_w]
    n_labels, _, stats, centroids = cv2.connectedComponentsWithStats(left_region)
    blobs = [
        (stats[i], centroids[i])
        for i in range(1, n_labels)
        if stats[i, cv2.CC_STAT_AREA] > 200
    ]
    blobs.sort(key=lambda x: x[1][0])
    if not blobs:
        return None
    if len(blobs) == 1:
        return 1 if blobs[0][0][cv2.CC_STAT_WIDTH] < 48 else None
    b1_w = blobs[0][0][cv2.CC_STAT_WIDTH]
    b2 = blobs[1][0]
    b2_w, b2_h, b2_a = (b2[cv2.CC_STAT_WIDTH], b2[cv2.CC_STAT_HEIGHT],
                         b2[cv2.CC_STAT_AREA])
    if b1_w < 48:   # first character is narrow '1'
        if b2_w < 48:
            return 11
        fill = b2_a / (b2_w * b2_h) if b2_w * b2_h > 0 else 0.0
        return 10 if fill > 0.66 else 12
    return None


def _detect_core_rank(skills_frame: Image.Image, calib: CalibrationResult) -> int:
    """Count lit (teal-glowing) core nodes A–F → int 0-6.

    Uses the 30×30 center crop of each node bbox.  Teal is identified by high
    green channel AND green significantly exceeding red (distinguishes teal
    from white text artifacts).
    """
    lit = 0
    for bbox in _CORE_NODE_BBOXES:
        x0, y0, x1, y1 = bbox
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        center_ref = (cx - 15, cy - 15, cx + 15, cy + 15)
        crop = _crop(skills_frame, calib, center_ref)
        arr = np.array(crop.convert("RGB"))
        r_mean = float(arr[:, :, 0].mean())
        g_mean = float(arr[:, :, 1].mean())
        if g_mean > _NODE_GREEN_MIN and (g_mean - r_mean) > _NODE_TEAL_GR_DIFF:
            lit += 1
    return lit


def _count_ascension_dots(base_frame: Image.Image, calib: CalibrationResult) -> int:
    """Count filled promotion dots below the agent name → ascension 0-6.

    Each filled dot appears as a distinct bright region in the dots bbox.
    """
    crop = _crop(base_frame, calib, _ASCENSION_DOTS_BBOX)
    arr = np.array(crop.convert("L"))
    col_bright = (arr > _ASCENSION_DOT_BRIGHT).any(axis=0)
    count, in_region = 0, False
    for b in col_bright:
        if b and not in_region:
            count += 1
            in_region = True
        elif not b:
            in_region = False
    return min(count, 6)


# ── Equipment render-gate predicates (H3) ────────────────────────────────────

def _equip_tab_rendered(frame: Image.Image, calib: CalibrationResult) -> bool:
    """True if the Equipment tab hexagon is visible (engine slot is bright white).

    Samples mean luma of the engine-slot area.  Returns False on the skills / base-stats
    tabs where that region is the dark background (luma≈14 vs ≈210 on equipment).
    """
    cx, cy = _EQUIP_GATE_CENTER
    r = _EQUIP_GATE_RADIUS
    crop = _crop(frame, calib, (cx - r, cy - r, cx + r, cy + r))
    return float(np.array(crop.convert("L"), dtype=float).mean()) > _EQUIP_GATE_LUMA_MIN


def _slot_panel_rendered(frame: Image.Image, calib: CalibrationResult) -> bool:
    """True if the disc/engine selection panel opened after a slot click.

    When a slot is clicked the Equipment view switches to the disc-selection screen (ref_8):
    a dark-background panel replaces the bright agent portrait at the panel bbox.
    Checks dark-pixel fraction (luma<30): ≈0.16 when panel is open vs ≈0.01 when not.
    """
    crop = _crop(frame, calib, _SLOT_PANEL_BBOX)
    arr = np.array(crop.convert("L"))
    dark_frac = float((arr < 30).mean())
    return dark_frac > _SLOT_PANEL_DARK_FRAC_MIN


# ── Field extractors ───────────────────────────────────────────────────────────

def _extract_base_stats(
    base_frame: Image.Image,
    calib: CalibrationResult,
    recognizer: TextRecognizer,
) -> tuple[str, int, int, dict[str, float]]:
    """E2: Read agent key, level, ascension from the Base Stats tab frame.

    Returns (key, level, ascension, confidence_map).
    """
    conf: dict[str, float] = {}

    name_crop = _crop(base_frame, calib, _AGENT_NAME_BBOX)
    name_text = recognizer.read_line(name_crop, "white_text_on_dark").strip()
    key, conf["key"] = normalize_agent(name_text)

    level_crop = _crop(base_frame, calib, _LEVEL_BBOX)
    level_text = recognizer.read_line(level_crop, "white_text_on_dark")
    level = parse_level(level_text) or 0
    conf["level"] = 90.0 if 1 <= level <= 60 else 30.0

    ascension = _count_ascension_dots(base_frame, calib)
    conf["ascension"] = 75.0   # heuristic; validate with live screenshots

    return key, level, ascension, conf


def _extract_skills(
    skills_frame: Image.Image,
    calib: CalibrationResult,
    recognizer: TextRecognizer,
) -> tuple[int, ZodTalent, dict[str, float]]:
    """E3: Read mindscape cinema and six talent levels from the Skills tab frame.

    Returns (mindscape, talent, confidence_map).
    """
    conf: dict[str, float] = {}

    # Mindscape Cinema counter ("CINEMA N/6")
    cinema_crop = _crop(skills_frame, calib, _MINDSCAPE_BBOX)
    cinema_text = recognizer.read_line(cinema_crop, "white_text_on_dark")
    m = _MINDSCAPE_RE.search(cinema_text)
    mindscape = int(m.group(1)) if m else 0
    conf["mindscape"] = 85.0 if m else 30.0

    # Five numbered skill levels (basic, dodge, assist, special, chain).
    # OCR cannot handle the stylized bold-italic badge font; use blob classifier.
    skill_levels: list[int] = []
    skill_names = ("basic", "dodge", "assist", "special", "chain")
    for name, bbox in zip(skill_names, _SKILL_LEVEL_BBOXES):
        crop = _crop(skills_frame, calib, bbox)
        lvl = _read_skill_badge(crop) or 0
        skill_levels.append(lvl)
        conf[f"skill_{name}"] = 85.0 if 1 <= lvl <= 12 else 30.0

    basic, dodge, assist, special, chain = skill_levels

    # Core passive rank — count lit teal nodes A-F
    core = _detect_core_rank(skills_frame, calib)
    conf["skill_core"] = 75.0   # heuristic; validate with live screenshots

    talent = ZodTalent(
        basic=basic,
        dodge=dodge,
        assist=assist,
        special=special,
        chain=chain,
        core=core,
    )
    return mindscape, talent, conf


# ── E4 equipment-frame helpers ────────────────────────────────────────────────

def _extract_equip_frame(
    frame: Image.Image,
    calib: CalibrationResult,
    recognizer: TextRecognizer,
    slot_idx: int,
) -> dict | None:
    """E4: Parse one Equipment-tab slot frame. Returns an equip record or None.

    slot_idx 0-5 → disc slots 1-6; slot_idx 6 → engine slot.

    Record keys:
      slot_idx    int           0-5 disc, 6 engine
      disc_set    str | None    set key (disc slots only)
      slot_key    str | None    "1"-"6" (disc slots only; derived from slot_idx)
      engine_key  str | None    engine key (engine slot only)
      confidence  float         0-100
    """
    title_crop = _crop(frame, calib, _EQUIP_TITLE_BBOX)
    title_text = recognizer.read_text(title_crop, "white_text_on_dark").replace("\n", " ").strip()

    if slot_idx < 6:
        set_key, conf = normalize_disc_set(title_text)
        if conf < _EQUIP_CONF_MIN:
            return None
        # slot_key is authoritative from click order, not from OCR title
        slot_key = str(slot_idx + 1)
        return {
            "slot_idx": slot_idx,
            "disc_set": set_key,
            "slot_key": slot_key,
            "engine_key": None,
            "confidence": conf,
        }
    else:
        engine_key, conf = normalize_engine(title_text)
        if conf < _EQUIP_CONF_MIN:
            return None
        return {
            "slot_idx": slot_idx,
            "disc_set": None,
            "slot_key": None,
            "engine_key": engine_key,
            "confidence": conf,
        }


def resolve_locations(
    equip_records: list[dict],
    discs: list[ZodDisc],
    engines: list[ZodWEngine],
) -> list[dict]:
    """E4: Set location on discs and engines from Equipment-tab cross-reference.

    equip_records is a list of dicts produced by scan_agents(), each containing:
        agent_key, slot_idx, disc_set, slot_key, engine_key, confidence.

    Mutates disc/engine objects in-place (sets location = agent_key).
    Returns orphan issues: records that matched no disc/engine in the scanned lists.
    """
    orphans: list[dict] = []

    for rec in equip_records:
        agent_key = rec["agent_key"]

        if rec["slot_idx"] < 6:
            # Disc slot: match by set_key + slot_key
            matched = next(
                (d for d in discs
                 if d.set_key == rec["disc_set"] and d.slot_key == rec["slot_key"]),
                None,
            )
            if matched is None:
                orphans.append({
                    "type": "disc",
                    "agent": agent_key,
                    "slot_idx": rec["slot_idx"],
                    "disc_set": rec["disc_set"],
                    "slot_key": rec["slot_key"],
                    "status": "no_match",
                })
            else:
                matched.location = agent_key
        else:
            # Engine slot: match by key
            matched_e = next(
                (e for e in engines if e.key == rec["engine_key"]),
                None,
            )
            if matched_e is None:
                orphans.append({
                    "type": "engine",
                    "agent": agent_key,
                    "engine_key": rec["engine_key"],
                    "status": "no_match",
                })
            else:
                matched_e.location = agent_key

    return orphans


# ── Portrait pHash (H2) ───────────────────────────────────────────────────────

def _portrait_phash(
    frame: Image.Image,
    calib: CalibrationResult,
    ref_cx: int,
    ref_cy: int,
) -> str:
    """Average hash of the portrait crop centered at (ref_cx, ref_cy).

    Resize to _PHASH_SIZE × _PHASH_SIZE, compare each pixel to the mean.
    Returns a binary string of length _PHASH_SIZE².
    """
    half = _PHASH_CROP_HALF
    crop = _crop(frame, calib, (ref_cx - half, ref_cy - half, ref_cx + half, ref_cy + half))
    small = np.array(
        crop.convert("L").resize((_PHASH_SIZE, _PHASH_SIZE), Image.LANCZOS),
        dtype=float,
    )
    bits = small > small.mean()
    return "".join("1" if b else "0" for b in bits.flatten())


# ── Grid-based roster traversal generator (H2) ────────────────────────────────

def scan_roster_grid(
    capture_fn: CaptureFunc,
    calib: CalibrationResult,
    scroll_fn: Callable[[], None],
    kill_event: Event,
    agent_max: int = AGENT_MAX,
) -> Generator[tuple[int, int], None, None]:
    """Yield (cx, cy) for each new owned agent cell in the roster grid.

    Traversal loop:
      1. Capture current grid frame.
      2. Detect owned cells (H1 saturation filter).
      3. Compute pHash for each; yield only un-seen cells (dedupe).
      4. After all new cells on this page are yielded: scroll_fn() → repeat.
      5. Stop when a page produces no new owned cells (locked tail or wrap-around)
         or when agent_max is reached.

    Caller must handle per-agent navigation (click cell, tabs, back-arrow) between
    consecutive yields. scroll_fn() is called only after every cell on the current
    page has been processed (i.e. when control returns from the last yield).
    """
    seen: set[str] = set()
    yielded = 0
    while not kill_event.is_set():
        frame = capture_fn()
        owned = detect_owned_agent_cells(frame, calib)

        new_cells: list[tuple[int, int]] = []
        for cx, cy in owned:
            h = _portrait_phash(frame, calib, cx, cy)
            if h not in seen:
                seen.add(h)
                new_cells.append((cx, cy))

        if not new_cells:
            return  # locked tail or all-seen wrap-around

        for cx, cy in new_cells:
            if kill_event.is_set() or yielded >= agent_max:
                return
            yield cx, cy
            yielded += 1

        scroll_fn()


# ── AgentNavigator (E1 / H2) ──────────────────────────────────────────────────

class AgentNavigator:
    """Click-driven agent roster iterator.

    Detects all agent portraits in the roster strip from an initial frame,
    Grid-based roster traversal (H2): detects owned cells per page via
    detect_owned_agent_cells(), dedupes by portrait pHash, scrolls down one
    page after all new agents on a page are processed, and stops when no new
    owned cells appear (locked tail or wrap-around).

    Navigates each agent: cell click → Base Stats → Skills → Equipment tabs
    (7 slot clicks) → back-arrow → next agent.

    Yields (agent_idx, base_frame, skills_frame, equipment_frames) for each
    agent.  equipment_frames has 7 elements: [disc_1..disc_6, engine].
    """

    def __init__(
        self,
        capture_fn: CaptureFunc,
        calib: CalibrationResult,
        kill_event: Event | None = None,
    ) -> None:
        self._capture   = capture_fn
        self._calib     = calib
        self._kill      = kill_event or Event()
        self._mouse     = None

    def _mouse_ctrl(self):
        if self._mouse is None:
            from pynput.mouse import Button, Controller
            self._mouse = Controller()
            self._Button = Button
        return self._mouse

    def _ref_to_screen(self, ref_x: int, ref_y: int) -> tuple[int, int]:
        return self._calib.to_screen(ref_x, ref_y)

    def _click(self, ref_x: int, ref_y: int) -> None:
        sx, sy = self._ref_to_screen(ref_x, ref_y)
        natural_click(self._mouse_ctrl(), sx, sy)

    def _scroll_page_down(self) -> None:
        """Scroll the agent roster grid down by one page via mouse wheel."""
        mouse = self._mouse_ctrl()
        sx, sy = self._ref_to_screen(*_AGENT_SCROLL_CENTER)
        mouse.position = (sx, sy)
        time.sleep(0.05)
        for _ in range(_SCROLL_TICKS_PER_PAGE):
            mouse.scroll(0, -1)
            time.sleep(0.05)
        time.sleep(_AGENT_SCROLL_WAIT_S)

    def scan(self):
        """Grid-based roster traversal. Yields (agent_idx, base_frame, skills_frame, equipment_frames).

        Uses scan_roster_grid() for detect/dedupe/scroll loop; handles per-agent
        tab navigation and back-arrow between agents.
        Game must be on the agent menu (grid visible) before calling scan().
        Stops on Esc, locked tail, or AGENT_MAX.
        """
        agent_idx = 0
        for cx, cy in scan_roster_grid(
            self._capture, self._calib, self._scroll_page_down, self._kill
        ):
            if self._kill.is_set():
                return

            # Select this agent from the roster grid
            self._click(cx, cy)
            time.sleep(jitter(_PORTRAIT_CLICK_DELAY_S))

            # Base Stats tab
            self._click(*_TAB_BASE_STATS)
            time.sleep(jitter(_TAB_CLICK_DELAY_S))
            base_frame = self._capture()

            if self._kill.is_set():
                return

            # Skills tab
            self._click(*_TAB_SKILLS)
            time.sleep(jitter(_TAB_CLICK_DELAY_S))
            skills_frame = self._capture()

            if self._kill.is_set():
                return

            # Equipment tab — click with render-gate (H3)
            self._click(*_TAB_EQUIPMENT)
            time.sleep(jitter(_TAB_CLICK_DELAY_S))

            equip_gate_ok = False
            for attempt in range(_EQUIP_GATE_RETRIES):
                _frame_test = self._capture()
                if _equip_tab_rendered(_frame_test, self._calib):
                    equip_gate_ok = True
                    break
                if attempt + 1 < _EQUIP_GATE_RETRIES:
                    time.sleep(_EQUIP_GATE_RETRY_S)
            if not equip_gate_ok:
                _log.warning("equip_gate_fail agent=%d — hexagon not rendered after %d tries",
                             agent_idx, _EQUIP_GATE_RETRIES)

            equipment_frames: list[Image.Image] = []
            for slot_center in _ALL_SLOT_CENTERS:
                if self._kill.is_set():
                    return
                self._click(*slot_center)
                time.sleep(jitter(_SLOT_CLICK_DELAY_S))
                slot_frame = self._capture()
                # Slot render-gate: one retry if panel didn't open (timing)
                if not _slot_panel_rendered(slot_frame, self._calib):
                    time.sleep(_SLOT_PANEL_RETRY_S)
                    slot_frame = self._capture()
                    if not _slot_panel_rendered(slot_frame, self._calib):
                        _log.debug("slot_panel_miss agent=%d slot=%d — empty or timing",
                                   agent_idx, _ALL_SLOT_CENTERS.index(slot_center))
                equipment_frames.append(slot_frame)

            # Return to agent menu grid for next agent
            self._click(*_BACK_ARROW)
            time.sleep(jitter(_TAB_CLICK_DELAY_S))

            yield agent_idx, base_frame, skills_frame, equipment_frames
            agent_idx += 1


# ── Public scanner ────────────────────────────────────────────────────────────

def scan_agents(
    capture_fn: CaptureFunc,
    calib: CalibrationResult,
    archive_dir: Optional[Path] = None,
    ocr_engine: str = "tesseract",
) -> tuple[list[ZodAgent], list[dict], list[dict]]:
    """Scan all agents in the roster. Game must be on the agent detail page.

    Returns (agents, issues, equip_records).
    equip_records contains one entry per equipped slot, suitable for
    resolve_locations(). Call resolve_locations() after scanning discs and
    engines to populate their location fields.
    """
    recognizer = make_recognizer(ocr_engine)
    kill_event, listener = make_kill_listener()
    navigator = AgentNavigator(capture_fn, calib, kill_event)

    agents: list[ZodAgent] = []
    issues: list[dict] = []
    equip_records: list[dict] = []

    try:
        for agent_idx, base_frame, skills_frame, equipment_frames in navigator.scan():
            key, level, ascension, base_conf = _extract_base_stats(
                base_frame, calib, recognizer
            )
            mindscape, talent, skill_conf = _extract_skills(
                skills_frame, calib, recognizer
            )
            conf = {**base_conf, **skill_conf}

            if archive_dir is not None:
                dd = archive_dir / f"agent_{agent_idx:03d}"
                dd.mkdir(parents=True, exist_ok=True)
                base_frame.save(dd / "base_stats.png")
                skills_frame.save(dd / "skills.png")
                for i, ef in enumerate(equipment_frames):
                    ef.save(dd / f"equip_slot_{i}.png")

            if base_conf["key"] < _CRITICAL_CONF:
                issues.append({
                    "agent": agent_idx,
                    "status": "critical_fail",
                    "confidence": conf,
                })
                continue

            low = {k: v for k, v in conf.items() if v < _LOW_CONF_THRESHOLD}
            if low:
                issues.append({
                    "agent": agent_idx,
                    "key": key,
                    "status": "low_confidence",
                    "fields": low,
                })

            # E4: parse each equipment slot frame to build location cross-reference
            for slot_idx, equip_frame in enumerate(equipment_frames):
                rec = _extract_equip_frame(equip_frame, calib, recognizer, slot_idx)
                if rec is not None:
                    rec["agent_key"] = key
                    equip_records.append(rec)

            agents.append(ZodAgent(
                key=key,
                level=level,
                constellation=mindscape,
                ascension=ascension,
                talent=talent,
            ))
    finally:
        listener.stop()

    return agents, issues, equip_records


# ── Offline single-frame extraction ──────────────────────────────────────────

def scan_single_frame_agent(
    base_frame: Image.Image,
    skills_frame: Image.Image,
    calib: CalibrationResult,
    ocr_engine: str = "tesseract",
) -> tuple[Optional[ZodAgent], dict]:
    """Extract one agent from static frames — no synthetic input, no navigator.

    Used for offline testing / debugging from reference screenshots.
    Returns (agent, confidence_map). agent is None on critical failure.
    """
    recognizer = make_recognizer(ocr_engine)
    key, level, ascension, base_conf = _extract_base_stats(base_frame, calib, recognizer)
    mindscape, talent, skill_conf = _extract_skills(skills_frame, calib, recognizer)
    conf = {**base_conf, **skill_conf}
    if base_conf["key"] < _CRITICAL_CONF:
        return None, conf
    return ZodAgent(
        key=key,
        level=level,
        constellation=mindscape,
        ascension=ascension,
        talent=talent,
    ), conf


# ── Export ────────────────────────────────────────────────────────────────────

def export_agents(agents: list[ZodAgent], path: Path) -> None:
    """Write a ZodExport JSON containing the given agents (discs=[], weapons=[])."""
    export = ZodExport(characters=agents)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(export.to_json(), encoding="utf-8")
