"""Debug overlays for the agent scanner (H12).

Draws the scanner's actual click targets and OCR crop boxes onto the captured
frames, so a live run leaves self-validating artifacts: you can SEE whether a
chevron/slot click landed on target and whether each OCR crop frames its field,
instead of reverse-engineering coordinates from a raw screenshot after the fact.

All coordinates are imported from `agent_scanner` (single source of truth) and
converted to pixel space via the same `calib.scale_*` the scanner uses, so the
overlay can never drift from what the scanner really does.

Saved alongside each archived frame as `*_overlay.png` when `--debug-overlays`
is passed (see cli.py).  Pure visualization — no effect on scan logic.
"""
from __future__ import annotations

from PIL import Image, ImageDraw

from .capture import CalibrationResult
from . import agent_scanner as A

# Colors: click targets = red, OCR/region crops = cyan, gates = yellow,
# the active/!current target = bright green.
_CLICK = (255, 40, 40)
_CROP = (0, 210, 210)
_GATE = (255, 210, 0)
_ACTIVE = (0, 255, 0)


def _pt(calib: CalibrationResult, x: int, y: int) -> tuple[int, int]:
    return round(x * calib.scale_x), round(y * calib.scale_y)


def _box(calib: CalibrationResult, bbox: tuple) -> tuple:
    x0, y0, x1, y1 = bbox
    return (round(x0 * calib.scale_x), round(y0 * calib.scale_y),
            round(x1 * calib.scale_x), round(y1 * calib.scale_y))


def _dot(draw: ImageDraw.ImageDraw, calib, x, y, color, label="", r=10):
    px, py = _pt(calib, x, y)
    draw.line((px - r - 4, py, px + r + 4, py), fill=color, width=2)  # crosshair
    draw.line((px, py - r - 4, px, py + r + 4), fill=color, width=2)
    draw.ellipse((px - r, py - r, px + r, py + r), outline=color, width=2)
    if label:
        draw.text((px + r + 2, py - r - 10), label, fill=color)


def _rect(draw: ImageDraw.ImageDraw, calib, bbox, color, label=""):
    px0, py0, px1, py1 = _box(calib, bbox)
    draw.rectangle((px0, py0, px1, py1), outline=color, width=2)
    if label:
        draw.text((px0 + 2, py0 + 1), label, fill=color)


def draw_base_overlay(frame: Image.Image, calib: CalibrationResult) -> Image.Image:
    """Base-Stats tab: OCR field crops + strip chevrons + bottom tabs."""
    out = frame.copy().convert("RGB")
    d = ImageDraw.Draw(out)
    _rect(d, calib, A._AGENT_NAME_BBOX, _CROP, "name")
    _rect(d, calib, A._LEVEL_BBOX, _CROP, "level")
    _rect(d, calib, A._ASCENSION_DOTS_BBOX, _CROP, "ascension")
    _rect(d, calib, A._CHARACTER_RENDER_BBOX, _GATE, "owned-gate (p75 sat)")
    # Top agent strip controls.
    _rect(d, calib, A._STRIP_PHASH_BBOX, _CROP, "strip phash")
    _dot(d, calib, *A._STRIP_PREV, _CLICK, "<prev")
    _dot(d, calib, *A._STRIP_NEXT, _CLICK, "next>")
    # Bottom tabs (click centers + active-pill bboxes).
    for bbox in A._TAB_ACTIVE_BBOXES:
        _rect(d, calib, bbox, _GATE, "")
    for c, lbl in ((A._TAB_BASE_STATS, "Base"), (A._TAB_SKILLS, "Skills"),
                   (A._TAB_EQUIPMENT, "Equip")):
        _dot(d, calib, *c, _CLICK, lbl)
    return out


def draw_skills_overlay(frame: Image.Image, calib: CalibrationResult) -> Image.Image:
    """Skills tab: mindscape crop, skill-level crops, core-node sample boxes."""
    out = frame.copy().convert("RGB")
    d = ImageDraw.Draw(out)
    _rect(d, calib, A._MINDSCAPE_BBOX, _CROP, "cinema")
    for i, bbox in enumerate(A._SKILL_LEVEL_BBOXES):
        _rect(d, calib, bbox, _CROP, f"sk{i+1}")
    for i, bbox in enumerate(A._CORE_NODE_BBOXES):
        _rect(d, calib, bbox, _GATE, "ABCDEF"[i])
    return out


def draw_equip_overlay(
    frame: Image.Image,
    calib: CalibrationResult,
    active_slot: int | None = None,
) -> Image.Image:
    """Equipment tab / disc-select: all 7 slot click targets + gate + panel crops.

    `active_slot` (0-6) is drawn in bright green — the slot whose click produced
    this frame — so a miss is obvious at a glance.
    """
    out = frame.copy().convert("RGB")
    d = ImageDraw.Draw(out)
    for i, (cx, cy) in enumerate(A._ALL_SLOT_CENTERS):
        is_active = (i == active_slot)
        lbl = ("engine" if i == 6 else f"slot{i+1}")
        _dot(d, calib, cx, cy, _ACTIVE if is_active else _CLICK,
             ("*" + lbl if is_active else lbl), r=14 if is_active else 10)
    # Equip render-gate sample window.
    gx, gy = A._EQUIP_GATE_CENTER
    gr = A._EQUIP_GATE_RADIUS
    _rect(d, calib, (gx - gr, gy - gr, gx + gr, gy + gr), _GATE, "luma-gate")
    # Disc-detail panel crops (where the title/level OCR reads after a slot opens).
    _rect(d, calib, A._SLOT_PANEL_BBOX, _GATE, "panel-gate")
    _rect(d, calib, A._EQUIP_TITLE_BBOX, _CROP, "title")
    _rect(d, calib, A._EQUIP_LEVEL_BBOX, _CROP, "lvl")
    return out
