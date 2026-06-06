"""E1–E3: Agent roster navigator and assembler.

E1 — AgentNavigator: detects agent portraits in the roster strip and
     iterates each agent across Base Stats → Skills → Equipment tabs,
     clicking every disc/engine slot.
E2 — _extract_base_stats: reads agent key, level, ascension.
E3 — _extract_skills: reads mindscape cinema and six talent levels.

Equipment-tab frames (7 per agent) are archived for E4 cross-reference
but not parsed here.

Usage::

    agents, issues = scan_agents(capture_fn, calib, archive_dir=Path("archive"))
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from threading import Event
from typing import Callable, Optional

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

# 6 disc slots + 1 engine slot (hexagonal arrangement, navigation.yaml disc_slots)
_DISC_SLOT_CENTERS: list[tuple[int, int]] = [
    (1035, 310),   # slot 1 — top right
    (1180, 330),   # slot 2 — right center
    (1185, 500),   # slot 3 — lower right
    (1035, 720),   # slot 4 — bottom center
    (870,  530),   # slot 5 — left center
    (875,  320),   # slot 6 — upper left
]
_ENGINE_SLOT_CENTER = (1038, 515)
_ALL_SLOT_CENTERS   = _DISC_SLOT_CENTERS + [_ENGINE_SLOT_CENTER]  # 7 total

# Base Stats tab field bboxes
_AGENT_NAME_BBOX     = (955, 278, 1350, 330)
_LEVEL_BBOX          = (955, 452, 1100, 497)
_ASCENSION_DOTS_BBOX = (955, 332, 1350, 360)

# Skills tab field bboxes
_MINDSCAPE_BBOX = (35, 980, 200, 1030)
_SKILL_LEVEL_BBOXES: list[tuple[int, int, int, int]] = [
    (920, 510, 1035, 545),    # basic attack
    (1040, 510, 1155, 545),   # dodge
    (1160, 510, 1275, 545),   # assist
    (1280, 510, 1395, 545),   # special attack
    (1400, 510, 1515, 545),   # chain attack
]
# Approximate bboxes for core node icons A-F (hexagonal grid).
# Detection uses the 30×30 center crop to avoid inter-node overlap.
_CORE_NODE_BBOXES: list[tuple[int, int, int, int]] = [
    (965, 178, 1120, 350),    # A
    (965, 270, 1120, 415),    # B
    (1140, 178, 1310, 350),   # C
    (1140, 270, 1310, 415),   # D
    (1325, 178, 1490, 350),   # E
    (1325, 270, 1490, 415),   # F
]

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

    # Five numbered skill levels (basic, dodge, assist, special, chain)
    skill_levels: list[int] = []
    skill_names = ("basic", "dodge", "assist", "special", "chain")
    for name, bbox in zip(skill_names, _SKILL_LEVEL_BBOXES):
        crop = _crop(skills_frame, calib, bbox)
        text = recognizer.read_line(crop, "white_text_on_dark")
        m2 = _SKILL_DIGIT_RE.search(text)
        lvl = int(m2.group()) if m2 else 0
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


# ── AgentNavigator (E1) ───────────────────────────────────────────────────────

class AgentNavigator:
    """Click-driven agent roster iterator.

    Detects all agent portraits in the roster strip from an initial frame,
    then clicks each portrait and navigates Base Stats → Skills → Equipment
    tabs.  On the Equipment tab, clicks all 6 disc slots then the engine slot.

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

    def scan(self):
        """Yield (agent_idx, base_frame, skills_frame, equipment_frames) per agent.

        Portrait positions are sampled once from the first captured frame.
        Stops on Esc or when all detected portraits are visited.
        """
        init_frame = self._capture()
        portrait_xs = _find_agent_portraits(init_frame, self._calib)

        for agent_idx, portrait_x in enumerate(portrait_xs):
            if self._kill.is_set():
                return

            # Select this agent
            self._click(portrait_x, _ROSTER_CENTER_Y)
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

            # Equipment tab — click every disc slot then the engine slot
            self._click(*_TAB_EQUIPMENT)
            time.sleep(jitter(_TAB_CLICK_DELAY_S))

            equipment_frames: list[Image.Image] = []
            for slot_center in _ALL_SLOT_CENTERS:
                if self._kill.is_set():
                    return
                self._click(*slot_center)
                time.sleep(jitter(_SLOT_CLICK_DELAY_S))
                equipment_frames.append(self._capture())

            yield agent_idx, base_frame, skills_frame, equipment_frames


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
