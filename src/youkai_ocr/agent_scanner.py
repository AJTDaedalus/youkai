"""E1–E4 + H3 + H8: Agent roster navigator and assembler.

H8 — Top-strip traversal (D29): iterate agents via the detail-page ">"/"<"
     chevrons (selection ±1, pHash-confirmed), stop at the first grayed-out
     agent.  Supersedes the H1/H2 grid path (`detect_owned_agent_cells` /
     `scan_roster_grid` retired; the detector is kept only for its fixtures).
H3 — Equipment-tab slot geometry (re-measured from reference_7) + render-gates.
E2 — _extract_base_stats: reads agent key, level, ascension.
E3 — _extract_skills: reads mindscape cinema and six talent levels.

Equipment-tab frames (7 per agent) are archived for E4 cross-reference.

Usage::

    agents, issues = scan_agents(capture_fn, calib, archive_dir=Path("archive"))
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from collections.abc import Callable
from pathlib import Path
from threading import Event

import cv2
import numpy as np
from PIL import Image

from .capture import CalibrationResult
from .disc_scanner import scan_equipped_disc_frame
from .grid import make_kill_listener
from .input_utils import jitter, natural_click
from .normalizer import (
    normalize_agent,
    normalize_disc_set,
    normalize_engine,
    parse_level,
)
from .recognize import TextRecognizer, make_recognizer
from .wengine_scanner import scan_equipped_engine_frame
from .zod import ZodAgent, ZodDisc, ZodExport, ZodTalent, ZodWEngine

_log = logging.getLogger(__name__)

# ── Navigation constants (navigation.yaml, 1920×1080 ref coords) ─────────────

_ROSTER_STRIP_BBOX = (0, 32, 1920, 75)
_ROSTER_CENTER_Y = 53  # vertical click target inside strip (strip peak luma y=45-60)
_ROSTER_X_MIN = 400  # ignore columns left of this (City/Home UI buttons at x≈40-80)

# Tab bar measured from archive/live_20260605/agent_000/base_stats.png:
# active (yellow) Base Stats bbox x=1011-1294, y=964-1028, center (1152, 996).
# Skills/Equipment inferred from white text clusters and equal-width spacing.
_TAB_BASE_STATS = (1152, 996)
_TAB_SKILLS = (1435, 996)
_TAB_EQUIPMENT = (1718, 996)

# ── Agent-menu grid constants (H1 — navigation.yaml agent_menu, 1920×1080 ref coords) ──
# 2-column roster grid on the right side of the agent menu screen (ref_12/13/14).
# Raw screenshots (1922×1112) include 32px chrome; ref coords = raw - (1, 32).
# Ownership filter: 75th-percentile HSV-S over the full column width > threshold.
# Owned portraits are colorful (high S); locked/EMPTY portraits are grayscale (low S).

_AGENT_GRID_LEFT_COL = (1277, 1537)  # (x0, x1) for left column sampling band
_AGENT_GRID_RIGHT_COL = (1537, 1797)  # (x0, x1) for right column sampling band
_AGENT_GRID_ROW_CENTERS = [144, 402, 660, 918]  # cy of each visible row
_AGENT_GRID_ROW_STRIDE = 258  # px between row centers
_AGENT_GRID_ROW_HALF_H = 100  # ±px around cy for saturation crop
_AGENT_SAT_P75_THRESH = 15  # 75th-percentile S > this → owned

# 6 disc slots + 1 engine slot.  RE-MEASURED FROM LIVE 2026-06-07 (H11) via
# HoughCircles ring geometry, then VALIDATED against reference_7/15/16 (H12) — all four
# sources agree to ±2px (disc x-span 1137–1662).  The previous "wide" coords
# (1088–1785) were simply WRONG: they passed the old saturation test only because they
# landed on the colorful background filmstrip art in ref_7, not on the discs.  Ring
# geometry (not center saturation, which is disc-set-dependent) is the reliable check.
_DISC_SLOT_CENTERS: list[tuple[int, int]] = [
    (1558, 318),  # slot 1 — upper-right
    (1662, 538),  # slot 2 — right-center
    (1559, 760),  # slot 3 — lower-right
    (1239, 761),  # slot 4 — lower-left
    (1137, 539),  # slot 5 — left-center
    (1239, 320),  # slot 6 — upper-left
]
_ENGINE_SLOT_CENTER = (1398, 515)  # hexagon center (H11 live; disc-symmetry center ≈1398,538)
_ALL_SLOT_CENTERS = _DISC_SLOT_CENTERS + [_ENGINE_SLOT_CENTER]  # 7 total

# ── Equipment-tab render gates (H3) ──────────────────────────────────────────
# Gate 1: after Equipment-tab click — verify the hexagon is rendered.
# The engine slot is bright white (luma≈210 in ref_7); dark on skills/base-stats (luma≈14).
_EQUIP_GATE_CENTER = (1398, 515)  # hexagon center, game coords (H11 live)
_EQUIP_GATE_RADIUS = 20  # px sampling half-window
# Live (H11): an EQUIPPED engine icon reads luma≈125 here (not the ≈210 of the
# empty/bright ref_7 slot); base-stats≈33, skills≈46.  Threshold 80 separates the
# equipment hexagon from the other tabs.  (The RC-2 yellow-pill gate in _capture_tab
# is the primary render confirmation; this is a secondary check that only logs.)
_EQUIP_GATE_LUMA_MIN = 80  # threshold: >80 → hexagon visible
# Tab-switch render gate (H17).  A tab click fired while the PREVIOUS tab's page is
# still animating in is silently DROPPED by the game (live: `skills.png` was banked
# before its nodes painted, then the Equipment click landed during that animation and
# was swallowed — the 7 "equip" frames were all the still-open Skills page).  Re-CAPTURING
# alone never recovers a dropped click, so — like `_enter_detail_page` and `_advance` —
# we re-CLICK the tab periodically until its pill goes yellow.
_TAB_GATE_POLLS = 8  # pill-yellow re-checks after a tab click
_TAB_GATE_POLL_S = 0.35  # wait between re-checks (8×0.35 ≈ 2.8s budget)
_TAB_RECLICK_EVERY = 3  # re-click the tab every N polls to recover a dropped click

# Tab CONTENT render gate (H17).  The yellow pill lights the instant a tab is *selected*,
# BEFORE its page content animates in — so pill-yellow alone banks half-painted frames
# (live: skills.png had its Skills pill yellow but no nodes/levels painted yet).  We add
# an agent-INDEPENDENT content signal per tab (measured: rendered vs the live mid-animation
# frame, cross-checked against reference_3/4):
#   base   — agent-name bbox luma:  rendered ≈57 (ref_3 57.1)  vs mid-anim ≈9   → >30
#   skills — mean skill-level luma: rendered ≈56 (ref_4 57.5)  vs mid-anim ≈21  → >40
# Equipment is intentionally excluded: its only agent-universal element (the engine hexagon)
# reads dark when no W-Engine is equipped, so a content gate there would false-fail — and
# the equipment-tab frame feeds no OCR anyway (the per-slot frames do, each already gated by
# _slot_panel_rendered).  Equipment keeps the pill + re-click gate only.
_BASE_RENDER_LUMA_MIN = 30  # base-stats name bbox painted
_SKILLS_RENDER_LUMA_MIN = 40  # skills skill-level boxes painted

# Gate 2: after each slot click — verify the disc/engine selection panel opened.
# When a disc slot is clicked, ZZZ opens the disc-selection view (ref_8).
# The panel area at game(610,120,965,210) has a dark background (dark_frac≈0.16 in ref_8
# vs 0.01 in ref_7 where the bright agent portrait is visible).
_SLOT_PANEL_BBOX = (610, 120, 965, 210)  # same as _EQUIP_TITLE_BBOX
_SLOT_PANEL_DARK_FRAC_MIN = 0.08  # dark pixels (luma<30) / total > this → panel open

# Slot-open render gate (H18 → H19).  Clicking the FIRST hexagon slot triggers the big
# equipment→disc-select LAYOUT TRANSITION (ref_7 → ref_8: the character render slides out, the disc
# list slides in).  A slot click fired DURING that animation is silently DROPPED by the game — the
# H17 tab-drop class — so the 2nd slot was never opened (its capture re-banked slot 1's panel).
# Each
# slot is render-gated with re-click, like `_capture_tab`/`_advance`:
#   slot 0  → gate on the select panel APPEARING (`_slot_panel_rendered`).
#   slot 1+ → the panel stays open and just SWAPS content (H10-Q4), so gate on the panel BODY
#             switching from the previous slot; a dropped switch (settled-but-unchanged) → re-click.
#
# H19 — the H18 gate used the TITLE region and MISFIRED both ways:
#   • false-NEGATIVE on two adjacent slots of the SAME disc set (near-identical titles → the switch
# is
#     never detected → 8 polls of futile re-clicking → the user's "errors from clicking repeatedly"
#     and the ~2.8s "hangs oddly on disc 4").
#   • false-POSITIVE on a half-faded title (banked a duplicate of the previous slot → "disc 2
# skipped").
# Fix: gate on the full detail-panel BODY (main stat + substats — which DIFFER between two discs of
# one
# set, ref_8 — where the title does not) AND require it to be STABLE across two captures (so a
# mid-fade
# frame is never banked).  Generous budget: the per-agent OCR pause downstream dwarfs this.
_SLOT_GATE_POLLS = 20  # 20×0.35 ≈ 7s; doubled from 10 to survive disc→engine panel transitions
_SLOT_GATE_POLL_S = 0.35
_SLOT_DETAIL_BBOX = (610, 120, 965, 600)  # title + main-stat + substats (stops before the
# same-for-a-set set-effect text); switch-detect signal
_SLOT_CHANGE_MIN_BITS = (
    8  # body pHash Hamming > this vs the previous slot → panel switched (new disc)
)
_SLOT_STABLE_MAX_BITS = (
    10  # body pHash Hamming ≤ this across two captures → panel animation settled
)
# relaxed from 6 to 10 to tolerate minor background/model animation drift

# Empty-slot detection (H18 / issue 3 — calibrated from reference_17, Koleda fully unequipped).
# Equipped discs/engines come in many colour schemes, but the UNEQUIPPED state is distinctive
# (user-confirmed: "equipped sets have many styles, but none look like the unequipped one"), so we
# detect the EMPTY signature on the Equipment-tab frame BEFORE clicking — empty slots are then
# neither clicked nor cross-referenced.  This kills the data-corruption bug where clicking an empty
# slot surfaces the first INVENTORY disc/engine and falsely assigns it this agent's location.
#   empty disc slot → a slot-number glyph on a dark disc → mean luma LOW (ref_17 ≈32 vs equipped
#                     ≥120, even white/low-saturation discs).
#   empty engine    → the colour-shifting "core available" glow → HIGHLY saturated AND only
#                     moderately bright (ref_17 colored_frac≈0.5, luma≈90) vs a bright equipped
#                     render.  The luma<max guard rejects a hypothetical bright colourful engine;
#                     only one equipped-engine sample exists → confirm live (OQ-H18c).
_SLOT_SAMPLE_R = 50  # half-window (px) around a disc slot center for the empty test
_DISC_EQUIPPED_LUMA_MIN = 80  # disc-slot mean luma > this → equipped (empty ≈32, equipped ≥120)
_ENGINE_SAMPLE_R = 45  # half-window around the engine center
_ENGINE_EMPTY_COLORED_MIN = 0.15  # engine colored-px frac > this ...
_ENGINE_EMPTY_LUMA_MAX = 150  # ... AND mean luma < this → empty "core available" icon

# Equipment-frame settle (H19).  Empty-detection samples disc-icon luma on the Equipment-tab frame,
# but `_capture_tab` returns the instant the yellow pill lights — BEFORE the hexagon disc icons fade
# in.  Sampling a half-faded icon reads dark → an EQUIPPED slot is mis-flagged EMPTY and SKIPPED
# (the intermittent "disc N skipped").  So we wait for the hexagon ring region to settle (stable
# across two captures) before empty-detection.  Tolerant bit budget: the fade-in changes the whole
# ring (huge ΔpHash) while the one-slot selection-glow pulse is small — 12 bits separates them.
_EQUIP_RING_BBOX = (1100, 280, 1720, 800)  # bounding box of the 6 disc hexagons + engine
_EQUIP_STABLE_MAX_BITS = 12
_EQUIP_STABLE_POLLS = 8
_EQUIP_STABLE_POLL_S = 0.30


# Disc-slot index → in-game slot NUMBER (H18, from reference_17 Koleda: the unequipped slots show
# their number).  `_DISC_SLOT_CENTERS` is ordered upper-right→…→upper-left, but ZZZ numbers the
# ring left-column-top-down 1,2,3 then right-column-bottom-up 4,5,6 — so upper-RIGHT is slot 6, not
# 1.  The old `slot_idx + 1` was REVERSED and would have made every disc-location match miss.
def _slot_number(slot_idx: int) -> int:
    """In-game disc slot number (1-6) for a `_DISC_SLOT_CENTERS` index (slot# = 6 - idx)."""
    return 6 - slot_idx


# Base Stats tab field bboxes.
#
# The level pill's interior runs y=443–500; y=436–440 and y=501–505 are its dark
# border.  Both crops below must clear the ink AND stay off that border — a crop
# that clips glyph tops or swallows a border row binarises into one fused blob and
# the read silently degrades.  Re-measured 2026-07-30 over all 42 agent frames in
# live_20260730_085008; ink extents are identical on every one.
_AGENT_NAME_BBOX = (935, 278, 1560, 332)
# Sits on the agent name's descenders, NOT on a promotion-dot row — the detail page
# has none.  Retained only for the debug overlay; see _count_ascension_dots.
_ASCENSION_DOTS_BBOX = (955, 332, 1350, 360)
# "Lv. NN": white ink spans x=1070–1173, y=458–484.  The previous y0=460 clipped
# two rows off the digit tops, which read Lv.60 as 90 or 99 on 8 of 42 agents.
_LEVEL_BBOX = (1065, 455, 1180, 490)
# Cap badge: the dim "/ NN" dark-on-dark text immediately right of the level badge.
# Ink spans x=1182–1284, y=447–495.  The previous (1182, 453, 1300, 502) clipped the
# glyph tops and pulled in the pill's bottom border row, fusing the digits to a black
# bar — Tesseract then returned "/" with no digits on 41 of 42 agents, so every
# ascension fell through to the (bogus) fallback.  x1 also trimmed 1300→1288 to keep
# the neighbouring MAX circle out of the crop.
_LEVEL_CAP_BBOX = (1182, 443, 1288, 501)
_VALID_AGENT_CAPS = frozenset({10, 20, 30, 40, 50, 60})
_ASCENSION_FROM_CAP: dict[int, int] = {10: 0, 20: 1, 30: 2, 40: 3, 50: 4, 60: 5}

# Skills tab field bboxes (re-measured from reference_4 in H4)
# Tightened in mindscape-fix T1.1: old bbox (35,980,200,1030) captured the whole
# circular Mindscape progress ring; Otsu thresholding turned the bright ring arcs
# into blobs that swamped the small "N/6" digits. This bbox brackets the teal
# badge itself (with margin tesseract needs to segment glyphs) while excluding
# the dotted ring texture and black arc above it.
_MINDSCAPE_BBOX = (90, 980, 190, 1025)
_SKILL_LEVEL_BBOXES: list[tuple[int, int, int, int]] = [
    (930, 750, 1065, 780),  # basic attack
    (1110, 750, 1245, 780),  # dodge
    (1295, 750, 1425, 780),  # assist
    (1470, 750, 1605, 780),  # special attack
    (1650, 750, 1785, 780),  # chain attack
]
# Core node bboxes A-F: re-measured from reference_4 via teal connected-component
# centroids (H4). Detection samples the 30×30 crop at the bbox center, which lands
# on the bright teal ring (not the dark interior) at these corrected positions.
_CORE_NODE_BBOXES: list[tuple[int, int, int, int]] = [
    (1079, 278, 1139, 338),  # A — center (1109, 308)
    (1031, 446, 1091, 506),  # B — center (1061, 476)
    (1281, 279, 1341, 339),  # C — center (1311, 309)
    (1237, 443, 1297, 503),  # D — center (1267, 473)
    (1487, 278, 1547, 338),  # E — center (1517, 308)
    (1438, 445, 1498, 505),  # F — center (1468, 475)
]

# ── Traversal ─────────────────────────────────────────────────────────────────

_PHASH_SIZE = 16  # hash grid dimension (16×16 = 256 bits)
_PHASH_CROP_HALF = 64  # ±px around a portrait center for the hash crop (grid path / tests)

# ── Top-strip traversal (H8 / D29) ────────────────────────────────────────────
# The agent detail page (ref_3) carries a horizontal agent strip across the top.
# Clicking the ">"/"<" chevrons moves the SELECTED agent ±1 (live-confirmed H10),
# cleanly, staying on the current tab.  The strip is CIRCULAR (H16, user-confirmed):
# the chevrons WRAP around the roster, so there is no terminal first/last agent — we
# anchor on whatever entry lands on and stop when the strip identity returns to it
# (ownership need not be contiguous; grayed-out agents are skipped, not a stop).
#
# The bar RESIZES with the visible-thumbnail count, so the chevrons are not at a
# guaranteed-fixed pixel — we never trust the click blindly: every ">"/"<" is
# confirmed by a strip-region pHash change, and a no-change is the "end reached" /
# missed-click signal (NOT a silent skip — that ambiguity was the RC-1 failure).
# RE-MEASURED FROM LIVE 2026-06-07 (H11), archive/live_20260605/agent_000/base_stats.png:
# the strip bar spans ref x≈1005–1810; "<" glyph centered at ref x≈1025, ">" at ≈1775
# (both at y≈44).  Portrait thumbnails fill x≈1045–1745.  The OLD coords landed ON
# portraits, not the chevrons — "<"@1140 hit the 2nd portrait (selection skipped the
# first agent) and ">"@1745 hit the last portrait's right edge ("hit an agent on the
# bar").  pHash bbox tightened to the portrait band so a selection move is unambiguous.
_STRIP_PHASH_BBOX = (1045, 28, 1750, 72)  # strip identity region (portrait band)
_STRIP_NEXT = (1775, 44)  # ">" next-agent chevron  (H11 live)
_STRIP_PREV = (1025, 44)  # "<" prev-agent chevron  (H11 live)
_STRIP_CHANGE_MIN_BITS = 10  # pHash Hamming > this between reads → selection changed
_SELECT_SETTLE_S = 0.35  # settle after a ">"/"<" click before re-reading
_SELECT_CONFIRM_RETRIES = 2  # re-click attempts when a ">"/"<" shows no change
# The strip is CIRCULAR (H16, user-confirmed): the chevrons wrap around, so there is
# no terminal "first"/"last" agent to rewind to.  We anchor on wherever entry lands and
# detect a completed loop when the strip identity returns to the start (Hamming ≤ this).
_RING_CLOSE_MAX_BITS = _STRIP_CHANGE_MIN_BITS  # strip pHash back within this of start → ring closed

# Agent identity for advance-confirm + ring-closure (H18 — fixes the "double/triple-click skip").
# The thin strip band is a POOR move-detector: a single ">"/"<" moves only the SELECTION
# HIGHLIGHT by one thumbnail — the filmstrip itself does NOT scroll except at an edge (H10-Q3) —
# so the band pHash barely changes (< _STRIP_CHANGE_MIN_BITS).  `_advance` then mis-read a real
# move as "no move", RE-CLICKED, and the second click moved the selection a SECOND time → an
# agent was skipped (two skips on a double miss).  The big full-body character render
# (_CHARACTER_RENDER_BBOX) changes COMPLETELY when the selection moves and is present on every
# detail tab (ref_7/16 show it on Equipment too), so it is the reliable "did we move / are we
# back at the start" identity.  Thresholds are deliberately loose: distinct agents differ by
# tens of bits, the same agent (idle-animated) by only a few.
_AGENT_ID_BBOX = (120, 140, 760, 1000)  # == _CHARACTER_RENDER_BBOX (defined below)
_AGENT_CHANGE_MIN_BITS = 15  # render pHash Hamming > this → selection moved to a new agent
# Ring-close is now name-based (H23); _AGENT_RING_CLOSE_MAX was removed (pHash not separable due
# to idle-animation drift — same-agent range 19–111 bits overlaps cross-agent range 74–109 bits).

# Entry: the agent MENU (ref_12) has a left-side "Base" button that opens the
# detail page for the currently-previewed agent (game coords, measured from ref_12).
_MENU_BASE_BUTTON = (1140, 816)  # re-centered on the "Base" pill (H11 live)

_CHARACTER_RENDER_BBOX = (120, 140, 760, 1000)  # full-body render (agent-identity pHash only)

# Ownership signal (D37 — replaces the non-separable render-hue test, H15/RC).
# WHY THE OLD TEST WAS DOOMED: ZZZ renders UNOWNED agents in FULL COLOUR, identical in
# style to owned (live: unowned "Hugo Vlad" is a blonde man in a blue suit — his
# blue_frac=0.93 is just the SUIT, not a duotone).  Measured across 33 live owned
# captures, owned monochrome/ice agents (blue_frac 0.75-0.87, hue_std 27-29) overlap the
# unowned cluster (0.93 / 24) with no margin — so the hue test flickered with the idle
# animation and SKIPPED real owned agents (Lycaon, Harumasa, Komano: the consecutive
# "agent_skip — unowned" lines in the live log).  No threshold can separate them.
#
# THE RELIABLE SIGNAL (user-confirmed live 2026-06-08), two parts:
#   1. An agent above Lv.1 CANNOT be unowned → level >= 2 ⇒ OWNED.  This fast-path covers
#      every built agent, including maxed ones (whose level-up pill shows gray "MAX") and,
#      crucially, owned agents sitting at an ascension breakpoint (e.g. Lv.50/50) whose
#      ">>" pill is WHITE — agent_023 — so their white pill is never mistaken for unowned.
#   2. Only Lv.1 agents are ambiguous.  There the level-up ">>" chevron decides: it is an
#      animated GREEN on owned agents (shades of green, never white) and a static WHITE on
#      unowned.  Green/white separate cleanly on the live frames (green~0.16, white~0.16,
#      both ~0 on the other class).  Live OCR reads BLANK on the unowned "Lv. 01" pill, so
#      "level unreadable" (parse → 0) is folded in with Lv.1 → consult the chevron.
# Net per-agent rule (see _classify_owned): level>=2 → owned; else green»→owned,
# white»→unowned, neither→owned (bias to CAPTURE — losing an owned agent is the cardinal
# sin; an extra unowned capture is filterable noise).
_OWN_CHEVRON_BBOX = (1315, 455, 1370, 535)  # the level-up ">>" pill, right of "Lv N /cap"
_OWN_GREEN_HUE = (35, 90)  # OpenCV hue band for the green (owned) chevron
_OWN_GREEN_S_MIN = 60
_OWN_GREEN_V_MIN = 60
_OWN_GREEN_FRAC_MIN = 0.03  # > this green fraction in the pill → owned (live green ≈ 0.16)
_OWN_WHITE_S_MAX = 45  # bright-white = low saturation …
_OWN_WHITE_V_MIN = 200  # … and high value → the static unowned ">>"
_OWN_WHITE_FRAC_MIN = 0.06  # > this white fraction in the pill → unowned (live white ≈ 0.16)
_OWN_LEVEL_OWNED_MIN = 2  # level >= this ⇒ owned outright (chevron not consulted)

# ── Timing ─────────────────────────────────────────────────────────────────────

_PORTRAIT_CLICK_DELAY_S = 0.60  # portrait selection + page-transition settle
_PORTRAIT_RETRY_WAIT_S = 0.50  # extra wait before retrying unconfirmed click
# Menu "Base" → detail-page entry must absorb the one-time AGENT-SELECT wipe, which
# can run well past a couple of short retries (H14: a 2-retry/~1.7s budget timed out
# live and left the scanner sitting on the agent menu).  Click ONCE, then poll the
# yellow-tab gate over a generous window; only re-click after a longer interval.
_DETAIL_GATE_POLLS = 12  # gate re-checks after a single Base click
_DETAIL_GATE_POLL_S = 0.40  # wait between gate re-checks (12×0.4 ≈ 4.8s budget)
_DETAIL_RECLICK_EVERY = 6  # re-click Base every N polls in case the click was dropped
_TAB_CLICK_DELAY_S = 0.30  # tab render (~AdeptiScanner recheck 300ms)
_SLOT_CLICK_DELAY_S = 0.45  # equipment slot settle (H18: raised 0.20→0.45 — the first
# slot opens the disc-select view with a slow layout wipe)
_ESCAPE_NAV_DELAY_S = 0.40  # settle after programmatic Escape navigation

# ── Detection thresholds ───────────────────────────────────────────────────────

_PORTRAIT_BRIGHTNESS = 80  # grayscale col-mean above which a column has a portrait
_MIN_PORTRAIT_WIDTH = 20  # minimum bright-region width (px, scaled space)
_PORTRAIT_MERGE_GAP = 8  # merge clusters separated by ≤ this (px, scaled)
_ASCENSION_DOT_BRIGHT = 150  # brightness threshold for counting filled promotion dots
_NODE_LIT_LUMA_MIN = 80  # lit node: character-coloured (luma≥91 observed); locked ≈42
_LOW_CONF_THRESHOLD = 70.0
_CRITICAL_CONF = 30.0

_MINDSCAPE_RE = re.compile(r"([0-6O])\s*/\s*6")  # N/6 pattern; O→0 handled in extraction
_SKILL_DIGIT_RE = re.compile(r"\d+")

# Mindscape numerator classification is done geometrically on the normalised 24×36
# glyph canvas, not by OCR: Tesseract returns empty on this stylized bold-italic
# badge font under every preprocessing tried, and the skill-level badge_glyphs.json
# templates do not transfer (the mindscape strokes are bolder/differently
# proportioned — cosine matching collapses 0↔6 and 6↔4 at ~0.77). The features below
# were measured across 78 live badges (two full scans of the same account) covering
# digits {0,1,2,4,6}; each threshold sits in a gap with no overlap between classes.
#
#   hole count      1 → {0,6}   |   0 → {1,2,3,4,5}   ("4" is an open-top glyph here,
#                   so 0 and 6 are the only holed numerators — matches T2.2.)
#   0-vs-6          hole-centroid vertical position: true-0 0.498–0.500 (centred loop),
#                   true-6 0.609–0.620 (low loop). A top/bottom pixel ratio also
#                   separates them but sits on a knife-edge (~0.99) that a 1px render
#                   shift can flip; the hole centroid has a clean 0.11 gap instead.
#   "1"             glyph aspect (w/h): true-1 ≈0.44 vs 0.89–0.92 for every other digit.
#   "4"             middle-third pixel fraction: true-4 ≈0.56 vs ≤0.41 for 0/1/2/6.
#   "2"             the balanced 0-hole shape: |top-third − bottom-third| ≈0.00.
_MINDSCAPE_ZERO_SIX_HCY = 0.55  # hole centroid below this fraction of height → 0, else 6
_MINDSCAPE_ONE_ASPECT = 0.62  # 0-hole glyph narrower than this (w/h) → "1"
_MINDSCAPE_FOUR_MID = 0.45  # 0-hole glyph with middle-third fraction above this → "4"
_MINDSCAPE_BALANCED_DELTA = 0.08  # |t3−b3| within this → balanced "2"
# 3 and 5 do not occur on the available capture account, so their rules below are
# structural (top-bar-heavy → 5, otherwise → 3) and UNVALIDATED on live frames; they
# are returned at sub-threshold confidence so they always surface for human review.
_MINDSCAPE_UNVALIDATED_CONF = 65.0

# ── Detail-page presence check (RC-2 — yellow active-tab signature) ───────────
# The full agent detail page (ref_3) has a bottom tab bar; the *active* tab is a
# saturated yellow pill.  The agent menu (ref_12) and the "AGENT SELECT"
# transition wipe have no such bar.  The old `mean luma > 60` test was fragile —
# it can't separate a real Equipment page (tab-bbox luma≈6) or the wipe (≈8) from
# the menu (≈33), and the bright wipe could false-positive.  Measured yellow
# fraction in the active-tab bbox is unambiguous (validated on the live archive):
#   real Base/Skills/Equipment-active page → yellowFrac ≈ 0.84–0.87
#   AGENT-SELECT wipe / agent menu / inactive tab → 0.000
# Each tab owns a 283px-wide active-pill bbox; whichever tab is open is the yellow
# one.  `_on_detail_page` = any of the three is yellow-active.
_TAB_ACTIVE_BBOXES: list[tuple[int, int, int, int]] = [
    (1011, 964, 1294, 1028),  # Base Stats   (center 1152)
    (1294, 964, 1577, 1028),  # Skills       (center 1435)
    (1577, 964, 1860, 1028),  # Equipment    (center 1718)
]
_TAB_BASE, _TAB_SKILLS_IDX, _TAB_EQUIP_IDX = 0, 1, 2
# Active-pill yellow: HSV hue 18-38, sat ≥110, val ≥120 (the ZZZ selection gold).
_TAB_YELLOW_HUE = (18, 38)
_TAB_YELLOW_S_MIN = 110
_TAB_YELLOW_V_MIN = 120
_TAB_YELLOW_FRAC_MIN = 0.40  # >this fraction yellow in the bbox → that tab is active

# ── Equipment-tab detail panel (slot_detail_panel in navigation.yaml) ──────────
# Panel appears CENTER-SCREEN (x=610-965) when a slot is clicked.
# Title bbox is fixed regardless of line count; only fields below it shift.
_EQUIP_TITLE_BBOX = (610, 120, 965, 210)  # "SetName [N]" for disc, engine name for engine
_EQUIP_LEVEL_BBOX = (648, 210, 965, 260)  # "Lv. N/MAX" row

# ── Slot-select ACTION-BAR equipped/empty gate (H21 / D36) ────────────────────
# The reliable per-slot equipped signal is the bottom action bar of the disc/engine SELECT view,
# NOT any pre-click pixel heuristic on the hexagon (proven non-separable for the engine — D36) and
# NOT the center detail pane (clicking an EMPTY slot AUTO-LOADS inventory[0] and renders its full
# title/level there — ref_18/19 — so a center-parse would false-assign the first inventory item).
# Equipped slot → leftmost button reads "Unequip All" (disc) / "Unequip" (engine); empty slot →
# "Equip All"/"Equip".  The bbox spans BOTH the disc "Unequip All" (x≈1140–1310) and the
# right-shifted engine "Unequip" (x≈1380–1520); the signal is the substring "unequip" (empty text
# never contains it).  Verified with the recognizer on ref_8 (True), ref_18/ref_19 (False).
_ACTION_BAR_BBOX = (1110, 1000, 1560, 1055)

# Minimum set/engine confidence to treat a slot as equipped (vs empty/dark panel).
_EQUIP_CONF_MIN = 30.0

CaptureFunc = Callable[[], Image.Image]

# Sentinel returned by AgentNavigator._read_equipment when the Equipment tab will not render
# (trial/preview agent, or a dropped tab) — distinct from None (killed) and a 7-frame list.
_EQUIP_UNAVAILABLE = object()


# ── Crop helper (mirrors disc/engine scanners) ─────────────────────────────────


def _crop(frame: Image.Image, calib: CalibrationResult, ref_bbox: tuple) -> Image.Image:
    x0, y0, x1, y1 = ref_bbox
    return frame.crop(
        (
            int(x0 * calib.scale_x),
            int(y0 * calib.scale_y),
            int(x1 * calib.scale_x),
            int(y1 * calib.scale_y),
        )
    )


# ── Image-analysis helpers ─────────────────────────────────────────────────────


def _find_agent_portraits(frame: Image.Image, calib: CalibrationResult) -> list[int]:
    """Return list of agent portrait x-centers (in 1920×1080 ref coords).

    Detects bright clusters in the roster strip (portrait thumbnails on dark
    background). Returns ref-coord x values suitable for clicking.
    """
    strip = _crop(frame, calib, _ROSTER_STRIP_BBOX)
    arr = np.array(strip.convert("L"))  # shape (H, W_scaled)
    col_means: np.ndarray = arr.mean(axis=0)

    # Zero out the left-side UI zone (City/Home buttons) to avoid false portrait detections.
    min_col = int(_ROSTER_X_MIN * calib.scale_x)
    col_means[:min_col] = 0

    bright = col_means > _PORTRAIT_BRIGHTNESS

    # Collect and merge connected bright column regions.
    regions: list[list[int]] = []  # each entry: [start_x, end_x] in scaled px
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
                regions[-1][1] = x - 1  # extend previous region
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
    return [int((r[0] + r[1]) / 2 / calib.scale_x) for r in regions]


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
        (_AGENT_GRID_LEFT_COL, (_AGENT_GRID_LEFT_COL[0] + _AGENT_GRID_LEFT_COL[1]) // 2),
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


_BADGE_THRESHOLD_HI = 180  # primary threshold: works for bright (maxed/near-maxed) badges
_BADGE_THRESHOLD_LO = 130  # H25 fallback: dim sub-maxed badges have max pixel ≈ 177
_BADGE_NARROW_W = 48  # blob width (3× scale) below which a digit is "1"
_BADGE_ROUND_FILL = 0.65  # fill-ratio above which a b0 blob is "0"-shaped (round)
_BADGE_GLYPH_W = 24  # normalised glyph canvas width (must match badge_glyphs.json)
_BADGE_GLYPH_H = 36  # normalised glyph canvas height
_BADGE_MATCH_FLOOR = 0.70  # cosine similarity below which the match is low-confidence

_badge_glyph_templates: dict[int, np.ndarray] | None = None


def _load_badge_glyphs() -> dict[int, np.ndarray]:
    """Lazily load per-digit mean templates from badge_glyphs.json."""
    global _badge_glyph_templates
    if _badge_glyph_templates is not None:
        return _badge_glyph_templates
    if getattr(sys, "frozen", False):
        data_dir = Path(sys._MEIPASS) / "data" / "zzz_1.4"
    else:
        data_dir = Path(__file__).parent.parent.parent / "data" / "zzz_1.4"
    fixture = data_dir / "badge_glyphs.json"
    data = json.loads(fixture.read_text())
    templates: dict[int, np.ndarray] = {}
    for d_str, samples in data["glyphs"].items():
        arrs = np.array(samples, dtype=np.float32) / 255.0
        templates[int(d_str)] = np.median(arrs, axis=0)
    _badge_glyph_templates = templates
    return templates


def _b1_hole_count(canvas: np.ndarray) -> int:
    """Count enclosed background regions (holes) in a 24×36 binary glyph canvas.

    Reliable discriminator for '8' (2 holes) vs '9'/'0'/'6'/'4' (1 hole) vs
    open digits (0 holes).  Pad with background-colour before flood-filling so
    the outer region is always connected regardless of whether the glyph touches
    the canvas edge.
    """
    h, w = canvas.shape
    inv = 255 - canvas
    padded = np.pad(inv, 1, mode="constant", constant_values=255)
    mask = np.zeros((padded.shape[0] + 2, padded.shape[1] + 2), dtype=np.uint8)
    cv2.floodFill(padded, mask, (0, 0), 128)  # flood outer background
    holes = (padded[1 : h + 1, 1 : w + 1] == 255).astype(np.uint8)
    n, _ = cv2.connectedComponents(holes)
    return n - 1  # subtract background label


def _match_b1_glyph(b1_crop: np.ndarray, valid_digits: set[int]) -> tuple[int, float]:
    """Template-match a b1 binary blob against the per-digit reference set.

    b1_crop: binary uint8 array (any size).
    valid_digits: restrict search to these digit values (caller supplies context constraints).

    Uses topological hole-count to pre-constrain candidates before cosine matching:
      2 holes → digit is '8' (returned immediately with high confidence)
      1 hole  → cosine match within {valid ∩ {0,4,6,9}}
      0 holes → cosine match within {valid ∩ {1,2,3,5,7}}

    Returns (digit, confidence) where confidence is cosine similarity × 100.
    """
    scale = min(_BADGE_GLYPH_W / b1_crop.shape[1], _BADGE_GLYPH_H / b1_crop.shape[0])
    new_w = max(1, int(b1_crop.shape[1] * scale))
    new_h = max(1, int(b1_crop.shape[0] * scale))
    scaled = cv2.resize(b1_crop, (new_w, new_h), interpolation=cv2.INTER_AREA)
    _, scaled = cv2.threshold(scaled, 127, 255, cv2.THRESH_BINARY)
    canvas = np.zeros((_BADGE_GLYPH_H, _BADGE_GLYPH_W), dtype=np.uint8)
    y_off = (_BADGE_GLYPH_H - new_h) // 2
    x_off = (_BADGE_GLYPH_W - new_w) // 2
    canvas[y_off : y_off + new_h, x_off : x_off + new_w] = scaled

    holes = _b1_hole_count(canvas)
    if holes >= 2 and 8 in valid_digits:
        # "8" is the only digit that reliably produces two enclosed holes at
        # 24×36.  Bypass cosine matching — it routinely loses to the "9"
        # template (which is identical to "0" in our dataset) for this shape.
        return 8, 90.0

    query = canvas.flatten().astype(np.float32) / 255.0
    query_n = float(np.linalg.norm(query))
    templates = _load_badge_glyphs()
    best_digit, best_score = min(valid_digits), -1.0
    for digit, tmpl in templates.items():
        if digit not in valid_digits:
            continue
        tmpl_n = float(np.linalg.norm(tmpl))
        if query_n < 1e-6 or tmpl_n < 1e-6:
            score = 0.0
        else:
            score = float(np.dot(query, tmpl)) / (query_n * tmpl_n)
        if score > best_score:
            best_score, best_digit = score, digit
    # "3" vs "6" disambiguation: cosine matching confuses open-arc "3" glyphs
    # with the single "6" template when the "6" template (Rina's dim badge) renders
    # similarly to some "3" badges.  Waist density (rows 8–18 / total pixels) is a
    # reliable tiebreaker: "6" has a smooth middle transition (≥ 0.30 density)
    # while "3" has a narrow waist (< 0.30).  Only fires when "6" wins and both
    # "3" and "6" are valid candidates.
    if best_digit == 6 and 3 in valid_digits and holes == 0:
        total_px = float(canvas.sum())
        if total_px > 0:
            waist_density = float(canvas[8:18, :].sum()) / total_px
            if waist_density < 0.30:
                best_digit = 3
                best_score = float(np.dot(query, templates[3])) / (
                    query_n * float(np.linalg.norm(templates[3])) + 1e-9
                )

    conf = best_score * 100.0
    if conf < _BADGE_MATCH_FLOOR * 100.0:
        conf = min(conf, _LOW_CONF_THRESHOLD - 1.0)
    return best_digit, conf


def _read_skill_badge(badge_crop: Image.Image) -> tuple[int, float] | None:
    """Read current skill level from the "N / 12" (or "N / 16") pill badge.

    Returns (value, confidence) or None if completely unclassifiable.

    b0 (tens place): shape heuristic — narrow→"1" prefix, wide+round→"0" prefix.
    b1 (units place): template-matched against badge_glyphs.json reference set.
    Below-floor cosine similarity (<_BADGE_MATCH_FLOOR) → confidence <70, flagged.
    """
    arr = np.array(badge_crop.convert("RGB"))
    h, w = arr.shape[:2]
    arr_up = cv2.resize(arr, (w * 3, h * 3), interpolation=cv2.INTER_LANCZOS4)
    gray = cv2.cvtColor(arr_up, cv2.COLOR_RGB2GRAY)

    def _blobs(binary: np.ndarray) -> list:
        left_w = int(binary.shape[1] * 0.52)
        n, _, stats, centroids = cv2.connectedComponentsWithStats(binary[:, :left_w])
        found = [(stats[i], centroids[i]) for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] > 200]
        found.sort(key=lambda x: x[1][0])
        return found

    def _classify(binary: np.ndarray, dim_fallback: bool) -> tuple[int, float] | None:
        blobs = _blobs(binary)
        if not blobs:
            return None
        b0_s = blobs[0][0]
        b0_w = b0_s[cv2.CC_STAT_WIDTH]
        if len(blobs) == 1:
            return (1, 90.0) if b0_w < _BADGE_NARROW_W else None

        b1_s = blobs[1][0]
        b1_x = int(b1_s[cv2.CC_STAT_LEFT])
        b1_y = int(b1_s[cv2.CC_STAT_TOP])
        b1_bw = int(b1_s[cv2.CC_STAT_WIDTH])
        b1_bh = int(b1_s[cv2.CC_STAT_HEIGHT])
        b1_crop = binary[b1_y : b1_y + b1_bh, b1_x : b1_x + b1_bw]

        if b0_w < _BADGE_NARROW_W:
            # b0 is "1" → level is 10 + b1_digit; valid units are 0–6 (max skill level 16)
            b1_digit, b1_conf = _match_b1_glyph(b1_crop, valid_digits=set(range(7)))
            return (10 + b1_digit, b1_conf)

        if dim_fallback:
            b0_h = b0_s[cv2.CC_STAT_HEIGHT]
            b0_a = b0_s[cv2.CC_STAT_AREA]
            b0_fill = b0_a / (b0_w * b0_h) if b0_w * b0_h > 0 else 0.0
            if b0_fill > _BADGE_ROUND_FILL:
                # b0 is "0" → level is b1_digit; valid units are 1–9 (level 0 doesn't exist)
                b1_digit, b1_conf = _match_b1_glyph(b1_crop, valid_digits=set(range(1, 10)))
                return (b1_digit, b1_conf)
        return None

    _, binary_hi = cv2.threshold(gray, _BADGE_THRESHOLD_HI, 255, cv2.THRESH_BINARY)
    result = _classify(binary_hi, dim_fallback=False)
    if result is not None:
        return result

    _, binary_lo = cv2.threshold(gray, _BADGE_THRESHOLD_LO, 255, cv2.THRESH_BINARY)
    return _classify(binary_lo, dim_fallback=True)


def _classify_mindscape_numerator(cinema_crop: Image.Image) -> tuple[int, float] | None:
    """Geometrically classify the Mindscape "N/6" numerator glyph (0–6).

    OCR is unusable on this stylized badge font (Tesseract returns empty; the
    skill-level templates don't transfer — see the _MINDSCAPE_* constants), so the
    glyph is resolved from shape features on a per-crop Otsu-thresholded, size-
    normalised 24×36 canvas. Otsu is background-colour-agnostic, so the badge's
    per-character theme colour (teal/orange/yellow/blue/gray) is irrelevant.

    Returns (digit, confidence), or None only when no glyph blob can be isolated
    (falls back to the regex/OCR path). Digits 0,1,2,4,6 are returned at high
    confidence (rules validated on 78 live badges); 3 and 5 are best-effort at
    sub-threshold confidence (no live samples available — see module constants).
    """
    w, h = cinema_crop.size
    if w == 0 or h == 0:
        return None
    # Numerator occupies the left ~14-58% of the badge crop across every observed
    # digit (0-2,4,6); the "/6" denominator starts to the right of that band.
    num_crop = cinema_crop.crop((int(0.14 * w), 0, int(0.58 * w), h))
    arr = np.array(num_crop.convert("RGB"))
    up = cv2.resize(arr, (arr.shape[1] * 4, arr.shape[0] * 4), interpolation=cv2.INTER_LANCZOS4)
    gray = cv2.cvtColor(up, cv2.COLOR_RGB2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # Full-width blobs are ring/margin residue leaking in at the crop's top/bottom
    # edge (the bbox brackets the badge tightly but not perfectly, per T1.1), not
    # a glyph stroke — a single numerator digit never spans the whole sub-crop.
    max_glyph_w = 0.85 * binary.shape[1]
    n, _, stats, _ = cv2.connectedComponentsWithStats(binary)
    candidates = [
        (i, stats[i])
        for i in range(1, n)
        if stats[i, cv2.CC_STAT_AREA] > 300 and stats[i, cv2.CC_STAT_WIDTH] < max_glyph_w
    ]
    if not candidates:
        return None
    # The numerator glyph is always a single connected blob in this font — the
    # runner-up candidates here are consistently the "/" separator's left tip and
    # bottom-corner ring residue (near-identical size/position regardless of which
    # digit is showing), not a second stroke of the same glyph, so no merge step.
    candidates.sort(key=lambda c: -c[1][cv2.CC_STAT_AREA])
    _, best = candidates[0]
    x0, y0 = int(best[cv2.CC_STAT_LEFT]), int(best[cv2.CC_STAT_TOP])
    x1, y1 = x0 + int(best[cv2.CC_STAT_WIDTH]), y0 + int(best[cv2.CC_STAT_HEIGHT])
    glyph = binary[y0:y1, x0:x1]

    scale = min(_BADGE_GLYPH_W / glyph.shape[1], _BADGE_GLYPH_H / glyph.shape[0])
    nw, nh = max(1, int(glyph.shape[1] * scale)), max(1, int(glyph.shape[0] * scale))
    scaled = cv2.resize(glyph, (nw, nh), interpolation=cv2.INTER_AREA)
    _, scaled = cv2.threshold(scaled, 127, 255, cv2.THRESH_BINARY)
    canvas = np.zeros((_BADGE_GLYPH_H, _BADGE_GLYPH_W), dtype=np.uint8)
    y_off, x_off = (_BADGE_GLYPH_H - nh) // 2, (_BADGE_GLYPH_W - nw) // 2
    canvas[y_off : y_off + nh, x_off : x_off + nw] = scaled

    return _classify_glyph_canvas(canvas)


def _classify_glyph_canvas(canvas: np.ndarray) -> tuple[int, float]:
    """Resolve a normalised 24×36 binary Mindscape numerator glyph to a digit 0–6.

    Split by decision tree on validated shape features (see _MINDSCAPE_* constants).
    """
    total = float(canvas.sum()) + 1e-6
    H = canvas.shape[0]

    # Locate enclosed holes (background regions not connected to the canvas edge).
    inv = 255 - canvas
    padded = np.pad(inv, 1, mode="constant", constant_values=255)
    mask = np.zeros((padded.shape[0] + 2, padded.shape[1] + 2), dtype=np.uint8)
    cv2.floodFill(padded, mask, (0, 0), 128)
    hole = padded[1 : H + 1, 1 : canvas.shape[1] + 1] == 255
    if hole.any():
        # Only "0" and "6" enclose a hole in this font. "0" is a centred loop
        # (hole centroid ≈ 0.50·H); "6" is a low loop (≈ 0.61·H).
        hole_cy = float(np.where(hole)[0].mean()) / H
        return (0 if hole_cy < _MINDSCAPE_ZERO_SIX_HCY else 6), 90.0

    # 0-hole bucket: {1, 2, 3, 4, 5}. Work from the glyph's tight bounding box.
    ys, xs = np.where(canvas > 0)
    if ys.size == 0:
        return 0, _CRITICAL_CONF
    aspect = (xs.max() - xs.min() + 1) / (ys.max() - ys.min() + 1)
    if aspect < _MINDSCAPE_ONE_ASPECT:
        return 1, 90.0  # narrow single stem

    third = _BADGE_GLYPH_H // 3
    t3 = float(canvas[:third, :].sum()) / total
    m3 = float(canvas[third : 2 * third, :].sum()) / total
    b3 = float(canvas[2 * third :, :].sum()) / total
    if m3 > _MINDSCAPE_FOUR_MID:
        return 4, 90.0  # open-top "4": heavy waist, thin bottom stem
    if abs(t3 - b3) <= _MINDSCAPE_BALANCED_DELTA:
        return 2, 88.0  # balanced top/bottom is the "2" signature (validated)
    # Asymmetric residue — a "5" (top bar heavy) or "3". Unvalidated on live data,
    # so return sub-threshold confidence to force human review rather than trust it.
    return (5 if t3 > b3 else 3), _MINDSCAPE_UNVALIDATED_CONF


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
        arr = np.array(crop.convert("RGB")).astype(float)
        r, g, b = arr[:, :, 0].mean(), arr[:, :, 1].mean(), arr[:, :, 2].mean()
        luma = 0.299 * r + 0.587 * g + 0.114 * b
        if luma > _NODE_LIT_LUMA_MIN:
            lit += 1
    return lit


def _read_level_cap(base_frame: Image.Image, calib: CalibrationResult) -> int:
    """Read the level cap from the dim '/ NN' badge right of the level text.

    The cap digits are rendered dark-on-dark (~luma 0 text on ~luma 33 background).
    Preprocessing: normalize local contrast to [0,255], invert to get white-on-black,
    Otsu threshold, final invert for black-on-white Tesseract input.

    Returns the cap value (10|20|30|40|50|60) or 0 on failure.
    """
    import pytesseract  # lazy import; already loaded by TesseractRecognizer init

    crop = _crop(base_frame, calib, _LEVEL_CAP_BBOX)
    arr = np.array(crop.convert("L"))
    up = cv2.resize(arr, (arr.shape[1] * 3, arr.shape[0] * 3), interpolation=cv2.INTER_CUBIC)
    mn, mx = int(up.min()), int(up.max())
    if mx <= mn:
        return 0
    norm = np.clip((up.astype(int) - mn) * 255 // (mx - mn), 0, 255).astype(np.uint8)
    _, thresh = cv2.threshold(norm, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    # Drop ink that touches the crop edge.  At this dark-on-dark contrast a clipped
    # badge border binarises as one large blob fused to the digits, and Tesseract
    # then reads nothing at all.  The bbox leaves ~4px of margin, so a real glyph
    # never reaches the edge; anything that does is border, not text.
    n_labels, labels = cv2.connectedComponents(thresh)
    if n_labels > 1:
        edge = np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]])
        for lab in np.unique(edge):
            if lab != 0:
                thresh[labels == lab] = 0
    for_ocr = cv2.bitwise_not(thresh)  # black text on white for Tesseract
    raw = pytesseract.image_to_string(
        Image.fromarray(for_ocr),
        config="--oem 1 --psm 7 -c tessedit_char_whitelist=0123456789/",
    ).strip()
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return 0
    # Cap is always 2 digits (10–60).  A spurious leading digit can appear when the
    # thin "1" glyph abuts the next button's circle edge; take last 2 digits.
    last2 = int(digits[-2:]) if len(digits) >= 2 else int(digits)
    return last2 if last2 in _VALID_AGENT_CAPS else 0


def _count_ascension_dots(base_frame: Image.Image, calib: CalibrationResult) -> int:
    """Count filled promotion dots below the agent name → ascension 0-6.

    DEPRECATED — do not use for ascension.  The agent detail page has no promotion-dot
    row: _ASCENSION_DOTS_BBOX sits on the descenders of the agent's *name*, so this
    counts letter strokes and returns arbitrary values (5 for "Ben Bigger", 1 for
    "Anby", 0 for "Zhao").  It read as plausible because the counts land in 0-6.
    Kept only so the debug overlay keeps rendering the region.  Ascension now comes
    from the level cap, with _ascension_floor_from_level as the fallback.
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


def _ascension_floor_from_level(level: int) -> int:
    """Lowest ascension consistent with a level — an agent cannot exceed its cap.

    Level 60 is reachable only at cap 60, so it pins ascension at exactly 5.  Lower
    levels only bound it from below: a Lv.10 agent may sit at cap 10 (ascension 0) or
    have been promoted further and simply not levelled, so 0 is all we can assert.
    Returns 0 for a level outside 1-60, which means the level read is untrustworthy.
    """
    if not 1 <= level <= 60:
        return 0
    for cap in sorted(_ASCENSION_FROM_CAP):
        if level <= cap:
            return _ASCENSION_FROM_CAP[cap]
    return 0


# ── Detail-page presence predicate ───────────────────────────────────────────


def _tab_yellow_frac(frame: Image.Image, calib: CalibrationResult, tab_idx: int) -> float:
    """Fraction of the given tab's active-pill bbox that is ZZZ selection-yellow."""
    crop = _crop(frame, calib, _TAB_ACTIVE_BBOXES[tab_idx])
    arr = np.array(crop.convert("RGB"))
    hsv = cv2.cvtColor(cv2.cvtColor(arr, cv2.COLOR_RGB2BGR), cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    lo, hi = _TAB_YELLOW_HUE
    yellow = (h >= lo) & (h <= hi) & (s >= _TAB_YELLOW_S_MIN) & (v >= _TAB_YELLOW_V_MIN)
    return float(yellow.mean())


def _tab_active(frame: Image.Image, calib: CalibrationResult, tab_idx: int) -> bool:
    """True if the given tab is the open (yellow-highlighted) one and rendered.

    Doubles as a render-gate: during the "AGENT SELECT" wipe / mid-transition the
    pill is not yet yellow, so this returns False until the tab has actually painted.
    """
    return _tab_yellow_frac(frame, calib, tab_idx) > _TAB_YELLOW_FRAC_MIN


def _on_detail_page(frame: Image.Image, calib: CalibrationResult) -> bool:
    """True if the full agent detail page is open (any tab is yellow-active).

    Robust to the bright "AGENT SELECT" transition wipe and the agent menu, both
    of which show 0% yellow in every tab bbox (see _TAB_ACTIVE_BBOXES notes).
    """
    return any(_tab_active(frame, calib, i) for i in range(len(_TAB_ACTIVE_BBOXES)))


# ── Equipment render-gate predicates (H3) ────────────────────────────────────


def _equip_tab_rendered(frame: Image.Image, calib: CalibrationResult) -> bool:
    """True if the Equipment hexagon ring is rendered (engine-independent — H20/D35).

    The render-gate exists to tell a rendered Equipment tab from a trial/preview "not
    available" frame, so the traversal never hangs poking a modal (H18).  It must NOT key
    on the engine slot alone: that is the most agent-variable region.  A dark *equipped*
    W-Engine reads luma≈78 (live: nav_equip_unavailable.png) and an *empty* engine's glow
    dips low too — so the old engine-luma gate false-skipped real owned agents two ways
    (D35, which falsifies D33-Decision-3's "empty engine ≈110, safe" claim).

    Rendered if EITHER:
      - any disc slot reads equipped — rescues every agent wearing ≥1 disc (the common case;
        this is what the live false-skip frame needed: 6 discs + a dark engine), OR
      - the engine slot reads bright (luma > _EQUIP_GATE_LUMA_MIN) — the legacy check, which
        still uniquely catches a fully-naked owned agent: an EMPTY W-Engine shows the bright
        "core available" glow (Koleda: luma≈110), well above a skills/base page (luma≈39).

    This is exactly the UNION of the old engine-luma gate and the new disc path, so it is
    strictly WIDER than the old gate — it can only remove false skips, never add them.

    A structural edge-density fallback on _EQUIP_RING_BBOX was tried and REJECTED: measured
    edge-frac does not separate a rendered-but-empty hexagon (Koleda 0.034) from a non-equipment
    skills page (0.053) — an empty ring is less busy than a content-filled page — so it is not a
    valid discriminator (D35).  The only case neither signal covers is an agent with zero discs
    AND a dark equipped-engine render reading luma < 80; that is both vanishingly rare and
    indistinguishable from a trial/preview frame without the deferred Nangong reference (H18.4b),
    so it stays out of scope.
    """
    if any(_disc_slot_equipped(frame, calib, i) for i in range(6)):
        return True
    cx, cy = _EQUIP_GATE_CENTER
    r = _EQUIP_GATE_RADIUS
    crop = _crop(frame, calib, (cx - r, cy - r, cx + r, cy + r))
    return float(np.array(crop.convert("L"), dtype=float).mean()) > _EQUIP_GATE_LUMA_MIN


def _tab_content_rendered(frame: Image.Image, calib: CalibrationResult, tab_idx: int) -> bool:
    """True if the tab's PAGE CONTENT (not just its yellow pill) has painted (H17).

    The pill goes yellow the instant a tab is selected, before the content animates in,
    so _tab_active alone can pass on a half-rendered page.  This adds an agent-independent
    content signal so _capture_tab never banks a mid-animation frame for OCR.

    base   → agent-name bbox is bright (white text on the rendered stat panel).
    skills → the five skill-level boxes are bright (always present, investment-agnostic).
    equip  → True: the equipment-tab frame feeds no OCR (per-slot frames do, each gated by
             _slot_panel_rendered), and its only agent-universal element reads dark on an
             unequipped engine — so we don't content-gate it (pill + re-click only).
    """
    if tab_idx == _TAB_BASE:
        return (
            float(np.array(_crop(frame, calib, _AGENT_NAME_BBOX).convert("L"), dtype=float).mean())
            > _BASE_RENDER_LUMA_MIN
        )
    if tab_idx == _TAB_SKILLS_IDX:
        lumas = [
            float(np.array(_crop(frame, calib, b).convert("L"), dtype=float).mean())
            for b in _SKILL_LEVEL_BBOXES
        ]
        return (sum(lumas) / len(lumas)) > _SKILLS_RENDER_LUMA_MIN
    return True


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


def _disc_slot_equipped(frame: Image.Image, calib: CalibrationResult, slot_idx: int) -> bool:
    """True if disc slot `slot_idx` holds a disc (H18 — Koleda-calibrated).

    Empty disc slots show only a slot-number glyph on a dark disc (mean luma ≈32); equipped
    discs are bright renders (≥120) regardless of set colour scheme.
    """
    cx, cy = _DISC_SLOT_CENTERS[slot_idx]
    r = _SLOT_SAMPLE_R
    crop = _crop(frame, calib, (cx - r, cy - r, cx + r, cy + r))
    luma = float(np.array(crop.convert("L"), dtype=float).mean())
    return luma > _DISC_EQUIPPED_LUMA_MIN


def _panel_shows_equipped(frame: Image.Image, calib: CalibrationResult, recognizer) -> bool:
    """True if the open disc/engine SELECT panel belongs to an EQUIPPED slot (H21 / D36, H26).

    Reads the bottom action bar:
      • Equipped disc  → "Unequip All" + "Remove"  (contains "unequip")
      • Equipped engine → "Remove" + "Enhance"      (contains "remove", no "unequip")
      • Empty disc     → "Equip All" + "Equip"      (neither)
      • Empty engine   → "Equip" + "Enhance"        (neither)

    The signal is "unequip" OR "remove" — empty-slot text never contains either.
    H26 fix: engine slots were falsely read as empty because only "unequip" was checked.

    `recognizer is None` → returns True (no OCR available: assume equipped and let the downstream
    `_EQUIP_CONF_MIN` parse guard decide).  The live navigator always passes a recognizer.
    """
    if recognizer is None:
        return True
    text = recognizer.read_line(_crop(frame, calib, _ACTION_BAR_BBOX), "white_text_on_dark")
    text_clean = text.lower().replace(" ", "")
    return "unequip" in text_clean or "remove" in text_clean


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

    cap = _read_level_cap(base_frame, calib)
    if cap != 0:
        ascension = _ASCENSION_FROM_CAP.get(cap, 0)
        conf["ascension"] = 90.0
    else:
        # OCR of the dim "/NN" cap text failed.  Derive a floor from the level
        # instead — sound, unlike the promotion-dot count this replaced, which was
        # reading the agent name's descenders.  Exact at level 60, a lower bound
        # below it, so flag it for review rather than passing it off as a real read.
        ascension = _ascension_floor_from_level(level)
        conf["ascension"] = 70.0 if ascension > 0 else 40.0

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

    # Mindscape Cinema counter ("CINEMA N/6").
    # The badge has dark digits on a coloured background — brightness_threshold
    # (no inversion) + psm 8 (single-word) handles all character colour themes.
    # O→0 substitution handles Tesseract mis-classifying "0" as letter "O".
    cinema_crop = _crop(skills_frame, calib, _MINDSCAPE_BBOX)
    cinema_text = recognizer.read_cinema(cinema_crop)
    shape_result = _classify_mindscape_numerator(cinema_crop)
    m = _MINDSCAPE_RE.search(cinema_text)
    if shape_result is not None:
        # Hole-count/shape classification (T2.2) beats OCR on the stylized font:
        # it directly resolves the "0" read as "6" / "6" read as "5" confusions
        # Tesseract still made even after the T1.1 bbox fix and T2.1 regex hardening.
        mindscape, conf["mindscape"] = shape_result
    elif m:
        c = m.group(1)
        mindscape = 0 if c == "O" else int(c)
        conf["mindscape"] = 90.0
    else:
        # No verified "/6" denominator: a lone digit (or noise) is not trustworthy
        # evidence of mindscape rank, so don't stamp it as the value. Surface as
        # low/critical confidence rather than silently accepting a guess.
        mindscape = 0
        conf["mindscape"] = 40.0 if cinema_text.strip() else _CRITICAL_CONF

    # Five numbered skill levels (basic, dodge, assist, special, chain).
    # OCR cannot handle the stylized bold-italic badge font; use blob classifier.
    skill_levels: list[int] = []
    skill_names = ("basic", "dodge", "assist", "special", "chain")
    for name, bbox in zip(skill_names, _SKILL_LEVEL_BBOXES, strict=False):
        crop = _crop(skills_frame, calib, bbox)
        raw = _read_skill_badge(crop)
        if raw is not None:
            lvl, badge_conf = raw
        else:
            lvl, badge_conf = 0, 30.0
        skill_levels.append(lvl)
        conf[f"skill_{name}"] = badge_conf

    basic, dodge, assist, special, chain = skill_levels

    # Core passive rank — count lit teal nodes A-F
    core = _detect_core_rank(skills_frame, calib)
    conf["skill_core"] = 75.0  # heuristic; validate with live screenshots

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
        # slot_key is authoritative from click POSITION, not from OCR title.  The hexagon is
        # numbered 1,2,3 (left col, top→down) then 4,5,6 (right col, bottom→up) — so the
        # `_DISC_SLOT_CENTERS` index maps to slot# = 6 - idx (H18, reference_17 Koleda).
        slot_key = str(_slot_number(slot_idx))
        return {
            "slot_idx": slot_idx,
            "disc_set": set_key,
            "slot_key": slot_key,
            "engine_key": None,
            "confidence": conf,
        }
    else:
        engine_key, conf = normalize_engine(title_text)
        if not engine_key or conf < _EQUIP_CONF_MIN:
            # Empty key = below-floor match rejected by normalize_engine (T2): a disc
            # title bled into the engine slot. No confident engine here.
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
                (
                    d
                    for d in discs
                    if d.set_key == rec["disc_set"] and d.slot_key == rec["slot_key"]
                ),
                None,
            )
            if matched is None:
                orphans.append(
                    {
                        "type": "disc",
                        "agent": agent_key,
                        "slot_idx": rec["slot_idx"],
                        "disc_set": rec["disc_set"],
                        "slot_key": rec["slot_key"],
                        "status": "no_match",
                    }
                )
            else:
                matched.location = agent_key
        else:
            # Engine slot: match by key
            matched_e = next(
                (e for e in engines if e.key == rec["engine_key"]),
                None,
            )
            if matched_e is None:
                orphans.append(
                    {
                        "type": "engine",
                        "agent": agent_key,
                        "engine_key": rec["engine_key"],
                        "status": "no_match",
                    }
                )
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


# ── Top-strip identity + ownership helpers (H8) ───────────────────────────────


def _region_phash(frame: Image.Image, calib: CalibrationResult, ref_bbox: tuple) -> str:
    """Average hash of a fixed reference bbox (length _PHASH_SIZE² binary string)."""
    crop = _crop(frame, calib, ref_bbox)
    small = np.array(
        crop.convert("L").resize((_PHASH_SIZE, _PHASH_SIZE), Image.LANCZOS),
        dtype=float,
    )
    bits = small > small.mean()
    return "".join("1" if b else "0" for b in bits.flatten())


def _phash_hamming(a: str, b: str) -> int:
    """Number of differing bits between two equal-length pHash strings."""
    return sum(c1 != c2 for c1, c2 in zip(a, b, strict=False))


def _strip_id(frame: Image.Image, calib: CalibrationResult) -> str:
    """Identity pHash of the top agent-strip region (changes when selection moves)."""
    return _region_phash(frame, calib, _STRIP_PHASH_BBOX)


def _agent_id(frame: Image.Image, calib: CalibrationResult) -> str:
    """Identity pHash of the big full-body character render (H18).

    The reliable per-agent signal for advance-confirm and ring-closure: it changes
    completely when the selection moves to a different agent, where the strip band only
    shifts a one-thumbnail highlight (too small to detect — see the _AGENT_ID_BBOX notes).
    """
    return _region_phash(frame, calib, _AGENT_ID_BBOX)


def _chevron_color_fracs(frame: Image.Image, calib: CalibrationResult) -> tuple[float, float]:
    """(green_frac, white_frac) of the level-up ">>" pill — the D37 ownership signal.

    GREEN (animated, owned) vs static WHITE (unowned) separate cleanly here; an owned
    agent at an ascension breakpoint also shows WHITE, so this is only meaningful once the
    level has been confirmed to be Lv.1 (see `_classify_owned`).  Pure pixel op, no OCR —
    testable against synthetic frames.
    """
    crop = _crop(frame, calib, _OWN_CHEVRON_BBOX)
    arr = np.array(crop.convert("RGB"))
    hsv = cv2.cvtColor(cv2.cvtColor(arr, cv2.COLOR_RGB2BGR), cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    green = float(
        (
            ((h >= _OWN_GREEN_HUE[0]) & (h <= _OWN_GREEN_HUE[1]))
            & (s > _OWN_GREEN_S_MIN)
            & (v > _OWN_GREEN_V_MIN)
        ).mean()
    )
    white = float(((v > _OWN_WHITE_V_MIN) & (s < _OWN_WHITE_S_MAX)).mean())
    return green, white


def _classify_owned(level: int, green_frac: float, white_frac: float) -> bool:
    """Owned/unowned decision from the level + chevron signals (D37).  Pure → unit-testable.

    Fails toward CAPTURE (returns True) on every ambiguity — dropping an owned agent is the
    cardinal sin; an extra unowned capture is filterable noise downstream.
    """
    if level >= _OWN_LEVEL_OWNED_MIN:
        return True  # built agent (incl. white-pill breakpoints) → owned
    # level is 1, or OCR read blank (→0, which is what the unowned "Lv. 01" pill yields live):
    if green_frac >= _OWN_GREEN_FRAC_MIN:
        return True  # animated green ">>" → owned
    if white_frac >= _OWN_WHITE_FRAC_MIN:
        return False  # static white ">>" at Lv.1 → unowned
    return True  # neither signal → assume owned (bias to capture)


# ── AgentNavigator (H8 — top-strip traversal) ─────────────────────────────────


class AgentNavigator:
    """Click-driven agent roster iterator (H8 — detail-page top-strip traversal).

    Enters the detail page once (from the agent-menu "Base" button; the RC-2
    yellow-tab gate absorbs the one-time AGENT-SELECT wipe), then walks the CIRCULAR
    strip forward with ">" from wherever entry landed (H16 — the chevrons wrap, so
    there is no "first" agent to rewind to).  Each ">" is confirmed by the
    character-render pHash change, so a missed click is retried.  Unowned agents are
    skipped, not a stop; the pass ends when the OCR-extracted agent name returns to
    the start-anchor name (ring closed by name — H23; pHash ring-close was removed
    because idle-animation drift makes it non-separable) — independent of sort order.

    Per agent: Base tab → Skills tab → Equipment tab (click the 7 H3 slots in
    sequence, then ONE Escape to restore the strip bar) → ">" to the next agent.
    All three tab captures are render-gated (`_capture_tab`).

    Yields (agent_idx, base_frame, skills_frame, equipment_frames); equipment_frames
    has 7 elements: [disc_1..disc_6, engine].

    suppress_flag is a list[bool] shared with the kill listener so that
    programmatic Escape presses don't trigger the scan-abort.  Pass the same
    list to make_kill_listener().
    """

    def __init__(
        self,
        capture_fn: CaptureFunc,
        calib: CalibrationResult,
        kill_event: Event | None = None,
        suppress_flag: list | None = None,
        archive_dir: Path | None = None,
        recognizer: TextRecognizer | None = None,
    ) -> None:
        self._capture = capture_fn
        self._calib = calib
        self._kill = kill_event or Event()
        self._suppress_flag = suppress_flag if suppress_flag is not None else [False]
        self._archive = archive_dir
        self._recognizer = recognizer  # for the per-slot action-bar equipped/empty gate (H21)
        self._mouse = None
        self._kbd = None

    def _save_nav(self, name: str, frame: Image.Image) -> None:
        """Persist a navigation diagnostic frame to the archive (H14).

        Entry/rewind/owned-check failures are otherwise invisible — the scan log
        only shows "0 agents".  These `nav_*.png` frames make the next live run
        self-diagnosing: they show exactly which page the scanner was looking at.
        """
        if self._archive is None:
            return
        try:
            self._archive.mkdir(parents=True, exist_ok=True)
            frame.save(self._archive / f"nav_{name}.png")
        except Exception:
            pass

    def _mouse_ctrl(self):
        if self._mouse is None:
            from pynput.mouse import Button, Controller

            self._mouse = Controller()
            self._Button = Button
        return self._mouse

    def _kbd_ctrl(self):
        if self._kbd is None:
            from pynput.keyboard import Controller as KbdController

            self._kbd = KbdController()
        return self._kbd

    def _ref_to_screen(self, ref_x: int, ref_y: int) -> tuple[int, int]:
        return self._calib.to_screen(ref_x, ref_y)

    def _click(self, ref_x: int, ref_y: int) -> None:
        sx, sy = self._ref_to_screen(ref_x, ref_y)
        natural_click(self._mouse_ctrl(), sx, sy)

    def _press_escape(self) -> None:
        """Send one Escape keypress for in-game back-navigation.

        Temporarily suppresses the kill listener so the programmatic Escape
        is not mistaken for a user abort.  Uses the shared suppress_flag that
        must also be passed to make_kill_listener().
        """
        from pynput.keyboard import Key

        self._suppress_flag[0] = True
        time.sleep(0.02)  # ensure listener thread sees the flag before event fires
        kbd = self._kbd_ctrl()
        kbd.press(Key.esc)
        time.sleep(0.05)
        kbd.release(Key.esc)
        time.sleep(_ESCAPE_NAV_DELAY_S)

    def _enter_detail_page(self) -> bool:
        """Open the agent detail page (idempotent).

        If already on the detail page, returns True immediately.  Otherwise clicks
        the agent-menu "Base" button and waits for the RC-2 yellow-tab gate (which
        absorbs the one-time AGENT-SELECT wipe).
        """
        pre = self._capture()
        self._save_nav("enter_pre", pre)
        if _on_detail_page(pre, self._calib):
            return True

        # Click the menu "Base" button ONCE, then poll the yellow-tab gate over a
        # generous window so the AGENT-SELECT wipe has time to finish (H14).  Re-click
        # only periodically, to recover a genuinely dropped click without spamming the
        # detail page mid-transition.
        self._click(*_MENU_BASE_BUTTON)
        time.sleep(jitter(_PORTRAIT_CLICK_DELAY_S))
        for poll in range(_DETAIL_GATE_POLLS):
            frame = self._capture()
            if _on_detail_page(frame, self._calib):
                self._save_nav("enter_ok", frame)
                return True
            if poll and poll % _DETAIL_RECLICK_EVERY == 0:
                _log.debug("enter_detail_reclick poll=%d — gate still not yellow", poll)
                self._click(*_MENU_BASE_BUTTON)
            time.sleep(_DETAIL_GATE_POLL_S)
        self._save_nav("enter_fail", self._capture())
        _log.error(
            "enter_detail_fail — Base click did not reach the detail page after "
            "%d polls; see nav_enter_fail.png",
            _DETAIL_GATE_POLLS,
        )
        return False

    def _advance(self, direction: int) -> bool:
        """Click the ">" (direction>0) or "<" (direction<0) chevron, confirm the
        selected agent actually changed (character-render pHash — H18), retrying on a
        missed click.

        Returns True if the selection moved, False if it did not after retries
        (= a stuck click / degenerate single-agent strip).  Confirming on the big
        render (not the thin strip band) is what avoids the H18 over-click SKIP: the
        band barely moves on a single advance, so it false-negatived real moves and
        the retry double-advanced.
        """
        target = _STRIP_NEXT if direction > 0 else _STRIP_PREV
        before = _agent_id(self._capture(), self._calib)
        for _ in range(_SELECT_CONFIRM_RETRIES + 1):
            self._click(*target)
            time.sleep(_SELECT_SETTLE_S)
            after = _agent_id(self._capture(), self._calib)
            if _phash_hamming(before, after) > _AGENT_CHANGE_MIN_BITS:
                return True
        return False

    def _ring_close_key(self, frame: Image.Image) -> str:
        """Return the ring-close key for this frame: the normalised agent name (H23).

        Returns "" when no recognizer is available (ring-close disabled; kill event is the only
        stop).
        Overridable in tests — the strip sim has no OCR, so it returns str(self.idx).
        """
        if self._recognizer is None:
            return ""
        name_crop = _crop(frame, self._calib, _AGENT_NAME_BBOX)
        raw = self._recognizer.read_line(name_crop, "white_text_on_dark").strip()
        key, _ = normalize_agent(raw)
        return key

    def _wait_region_stable(
        self,
        first_frame: Image.Image,
        ref_bbox: tuple,
        max_bits: int,
        polls: int,
        poll_s: float,
    ) -> Image.Image:
        """Re-capture until a reference region is STABLE across two consecutive frames (H19).

        Returns the first settled frame (or the last captured, if the budget runs out).  Used to
        wait out fade-in animations before sampling a region — the disc-hexagon icons (empty
        detection) and, inside `_open_slot`, the slot detail panel.
        """
        prev_hash = _region_phash(first_frame, self._calib, ref_bbox)
        frame = first_frame
        for _ in range(polls):
            time.sleep(poll_s)
            frame = self._capture()
            cur = _region_phash(frame, self._calib, ref_bbox)
            if _phash_hamming(cur, prev_hash) <= max_bits:
                return frame
            prev_hash = cur
        return frame

    def _slot_equipped_from_panel(self, frame: Image.Image) -> bool:
        """True if the open select panel is for an EQUIPPED slot (action-bar gate — H21/D36).

        Wraps the module `_panel_shows_equipped` with the navigator's recognizer.  Overridable in
        tests (the strip sim models equipped/empty per slot without OCR).
        """
        return _panel_shows_equipped(frame, self._calib, self._recognizer)

    def _agent_level(self, base_frame: Image.Image) -> int:
        """OCR the "Lv. N" pill on the Base tab → int (0 if no recognizer / unreadable).

        Live, the unowned "Lv. 01" pill OCRs to blank → 0, which `_classify_owned` folds in
        with Lv.1 and resolves via the chevron.  Overridable in tests (the sim has no OCR).
        """
        if self._recognizer is None:
            return 0
        text = self._recognizer.read_line(
            _crop(base_frame, self._calib, _LEVEL_BBOX), "white_text_on_dark"
        )
        return parse_level(text) or 0

    def _agent_owned(self, base_frame: Image.Image) -> bool:
        """Owned/unowned decision for the Base-tab frame (D37): level OCR + ">>" chevron.

        Replaces the non-separable render-hue test.  Reads the level, falls back to the
        green/white level-up chevron only for Lv.1/unreadable agents, and biases every
        ambiguity toward OWNED (capture) so a real agent is never dropped.
        """
        level = self._agent_level(base_frame)
        green, white = _chevron_color_fracs(base_frame, self._calib)
        return _classify_owned(level, green, white)

    def _open_slot(
        self,
        slot_center: tuple[int, int],
        slot_no: int,
        prev_equipped_id: str | None,
    ) -> tuple[Image.Image, bool, str | None]:
        """Click a hexagon slot; resolve it once the panel SETTLES (H21 closed-loop contract).

        Returns ``(frame, equipped, panel_id)``:
          • ``equipped`` — the action-bar gate (`_slot_equipped_from_panel`): "Unequip" → equipped,
            "Equip" → empty.  This is the authoritative equipped/empty signal (D36), read from the
            settled select panel; the old pre-click pixel heuristic is gone.
          • ``panel_id`` — the equipped frame's BODY pHash (None when empty).  Pass it back as
            ``prev_equipped_id`` so the next EQUIPPED slot can confirm it switched to a NEW disc.

        Flow once the panel is rendered AND stable across two captures (H19 anti-fade):
          - EMPTY → return immediately.  Two empty slots auto-load the SAME inventory[0] detail, so
          a
            body-switch test would never fire — but their result (no record) is identical, so a
            dropped click between empties is harmless; no switch-detect, no futile re-clicks.
          - EQUIPPED → accept if first equipped or the body changed from the previous equipped slot
            (substats differ between two discs even of one set, ref_8); else the click was dropped
            (panel still shows the previous disc) → re-click.
        Banks the last frame after the poll budget so a genuinely odd slot never hangs.
        """
        self._click(*slot_center)
        time.sleep(jitter(_SLOT_CLICK_DELAY_S))
        prev_hash: str | None = None
        frame = self._capture()
        for poll in range(_SLOT_GATE_POLLS):
            if _slot_panel_rendered(frame, self._calib):
                cur = _region_phash(frame, self._calib, _SLOT_DETAIL_BBOX)
                if (
                    prev_hash is not None
                    and _phash_hamming(cur, prev_hash) <= _SLOT_STABLE_MAX_BITS
                ):
                    # Panel settled (two stable captures).  Resolve equipped/empty from the action
                    # bar.
                    if not self._slot_equipped_from_panel(frame):
                        return frame, False, None
                    # Equipped — confirm it's a NEW disc (not a dropped click banking the prev
                    # slot).
                    if (
                        prev_equipped_id is None
                        or _phash_hamming(cur, prev_equipped_id) > _SLOT_CHANGE_MIN_BITS
                    ):
                        return frame, True, cur
                    _log.debug(
                        "slot_reclick slot=%d poll=%d — equipped panel settled but unchanged "
                        "from previous slot (dropped click)",
                        slot_no,
                        poll,
                    )
                    self._click(*slot_center)
                    prev_hash = None
                    time.sleep(_SLOT_GATE_POLL_S)
                    frame = self._capture()
                    continue
                prev_hash = cur
            time.sleep(_SLOT_GATE_POLL_S)
            frame = self._capture()
        _log.warning(
            "slot_gate_fail slot=%d — panel never settled in %d polls; banking frame",
            slot_no,
            _SLOT_GATE_POLLS,
        )
        equipped = self._slot_equipped_from_panel(frame)
        return (
            frame,
            equipped,
            (_region_phash(frame, self._calib, _SLOT_DETAIL_BBOX) if equipped else None),
        )

    def _read_equipment(self):
        """Open the Equipment tab, visit all 7 slots, capture the EQUIPPED ones, restore the bar.

        H21 closed-loop contract: every slot is clicked, then resolved from the SELECT panel's
        action bar (`_open_slot` → equipped/empty).  The old pre-click pixel skip is gone — it
        false-skipped equipped engines on ~4/5 agents (D36, proven non-separable).  Clicking an
        empty
        slot is safe: we never press "Equip", and the action-bar gate prevents recording the
        inventory[0] item that an empty slot auto-loads (the H18 corruption path).

        Per H10-Q4: a slot click hides the strip bar but slots stay clickable, so we switch between
        slots in the open select view with NO inter-slot Escape; ONE Escape after the last slot
        restores the bar.

        Returns:
          - list of 7 elements (Image per equipped slot, None per empty slot) on success,
          - None if the scan was killed mid-read,
          - _EQUIP_UNAVAILABLE if the Equipment tab never rendered the hexagon — a trial/preview
            agent ("not available in preview mode") OR a dropped tab.  We Escape (dismiss any modal)
            and bail so the traversal is never left stuck on a popup (H18).  This is a SAFETY NET,
            not
            proactive trial detection (see DESIGN_agents.md H18-Q / H21).
        """
        equip_frame = self._capture_tab(_TAB_EQUIP_IDX)
        # Let the hexagon finish fading in before the render-gate so an equipped engine has time to
        # brighten / discs to paint (H19) — the gate still keys on the disc ring (D35).
        equip_frame = self._wait_region_stable(
            equip_frame,
            _EQUIP_RING_BBOX,
            _EQUIP_STABLE_MAX_BITS,
            _EQUIP_STABLE_POLLS,
            _EQUIP_STABLE_POLL_S,
        )
        if not _equip_tab_rendered(equip_frame, self._calib):
            _log.warning(
                "equip_unavailable — hexagon not rendered after tab switch "
                "(trial/preview agent or empty engine); escaping to clear any modal"
            )
            self._save_nav("equip_unavailable", equip_frame)
            self._press_escape()
            return _EQUIP_UNAVAILABLE

        # Visit every slot; the action-bar gate (D36) decides equipped (record) vs empty (skip).
        frames: list[Image.Image | None] = []
        prev_equipped_id: str | None = None
        clicked_any = False
        for slot_no, slot_center in enumerate(_ALL_SLOT_CENTERS):
            if self._kill.is_set():
                return None
            slot_frame, equipped, panel_id = self._open_slot(slot_center, slot_no, prev_equipped_id)
            clicked_any = True
            if equipped:
                frames.append(slot_frame)
                prev_equipped_id = panel_id
            else:
                _log.info(
                    "slot_empty slot=%d — action-bar shows 'Equip' (nothing equipped); "
                    "not recorded",
                    slot_no,
                )
                frames.append(None)

        # ONE Escape exits the select view (every slot was clicked, so the bar is hidden) and
        # restores
        # the top strip bar (Q4) so ">" works.
        if clicked_any:
            self._press_escape()
        return frames

    def _capture_tab(self, tab_idx: int) -> Image.Image:
        """Click a bottom tab and capture once its yellow pill has painted (RC-2).

        Render-gate: poll until `_tab_active(tab_idx)` (the tab is the open,
        yellow-highlighted one), so a frame caught during the "AGENT SELECT"
        wipe / mid-transition is never banked.

        H17 — a click fired while the previous tab's page is still animating in is
        silently DROPPED by the game; re-capturing alone can never recover it (the
        pill stays the OLD tab's colour forever).  So we re-CLICK the tab every
        `_TAB_RECLICK_EVERY` polls — the same dropped-click recovery `_advance` and
        `_enter_detail_page` already rely on — until the pill goes yellow.
        """
        centers = (_TAB_BASE_STATS, _TAB_SKILLS, _TAB_EQUIPMENT)
        self._click(*centers[tab_idx])
        time.sleep(jitter(_TAB_CLICK_DELAY_S))
        for poll in range(_TAB_GATE_POLLS):
            frame = self._capture()
            # Gate on BOTH pill-yellow (tab selected) AND content painted (H17): the pill
            # lights before the page animates in, so the first condition alone banks
            # half-rendered frames.
            if _tab_active(frame, self._calib, tab_idx) and _tab_content_rendered(
                frame, self._calib, tab_idx
            ):
                return frame
            # A click fired during the previous tab's entrance animation is silently
            # dropped — re-CLICK (not just re-capture) periodically to recover it.
            if (
                poll
                and poll % _TAB_RECLICK_EVERY == 0
                and not _tab_active(frame, self._calib, tab_idx)
            ):
                _log.debug(
                    "tab_reclick tab=%d poll=%d — pill still not yellow (dropped click?)",
                    tab_idx,
                    poll,
                )
                self._click(*centers[tab_idx])
            time.sleep(_TAB_GATE_POLL_S)
        _log.warning(
            "tab_gate_fail tab=%d — not selected+rendered after %d polls; banking last frame",
            tab_idx,
            _TAB_GATE_POLLS,
        )
        return self._capture()

    def scan(self):
        """Top-strip roster traversal. Yields (agent_idx, base_frame, skills_frame,
        equipment_frames).

        Game must be on the agent menu (or already on a detail page) before calling.
        Enters the detail page, then walks the strip in one direction with the advance
        chevron, reading Base/Skills/Equipment for each OWNED agent.

        H16 — the strip is CIRCULAR (user-confirmed: the chevrons wrap around).  There is
        no terminal "first" agent to rewind to — pressing "<" forever just cycles, which
        is exactly the `_REWIND_MAX` failure the old `_rewind_to_first` hit.  So we don't
        rewind at all: we anchor on the agent entry lands on, record its strip identity,
        and walk forward.  An UNOWNED agent (D37: Lv.1 + static white ">>" chevron) is
        SKIPPED after a single Base capture (no Skills/Equipment), not a stop — owned agents
        need not be contiguous.  We stop when the strip identity returns to the start (the
        ring has closed → every agent visited once), or on a true advance no-op (a
        degenerate single-agent / non-looping strip), or on the kill event.
        This is independent of sort order and of which way the chevrons actually
        move (the user saw the pass run "in reverse" — now benign: a ring traversed
        backward still returns to its start).

        Ownership is decided by `_agent_owned` (level OCR + level-up chevron colour), which
        REPLACED the H15 render-hue test — that test was non-separable (ZZZ renders unowned
        agents in full colour) and silently skipped owned monochrome/ice agents.
        """
        if not self._enter_detail_page():
            _log.error("agent_scan_abort — could not open the agent detail page")
            return

        self._save_nav("start", self._capture())

        # Ring-close anchor — keyed on the AGENT NAME (H23), not the character-render
        # pHash.  The render pHash was unreliable: the same character's idle animation
        # causes 19–111-bit frame-to-frame drift, entirely overlapping the cross-agent
        # range (74–109 bits) so there is no safe threshold.  Name OCR is deterministic
        # for the same settled base_stats frame (offline calibration confirmed identical
        # (key, score) on both visits for every same-agent pair).  We set start_name
        # from the first non-empty normalised key we see; ring closes when any subsequent
        # non-empty key matches it.  The ring always closes; kill event and advance no-op are
        # backstops.
        start_name: str = ""  # first reliable agent name seen (set on first non-empty read)

        agent_idx = 0  # owned agents yielded (archive index)
        visited = 0  # total strip positions visited (for logging)
        while not self._kill.is_set():
            visited += 1
            # D37: capture the Base tab FIRST — it carries both the "Lv. N" pill and the
            # ownership ">>" chevron, and is the one tab where ownership can be read.  The
            # decision happens here, BEFORE the expensive Skills/Equipment captures, so an
            # unowned agent costs a single Base frame, not a 7-slot equipment walk.
            base_frame = self._capture_tab(_TAB_BASE)
            if self._kill.is_set():
                return

            # Ring-close check: use the settled base_frame to extract the agent name (H23).
            # Same-agent pHash drifts 19–111 bits between visits (idle animation); name OCR is
            # deterministic (offline calibration: all 7 same-agent pairs returned identical keys).
            current_name = self._ring_close_key(base_frame)
            if not start_name:
                if current_name:
                    start_name = current_name  # anchor on entry position (retried until it lands)
            elif current_name == start_name:
                _log.info(
                    "agent_scan_done — ring closed (returned to '%s') after %d owned (%d visited)",
                    start_name,
                    agent_idx,
                    visited,
                )
                return

            if self._agent_owned(base_frame):
                skills_frame = self._capture_tab(_TAB_SKILLS_IDX)
                if self._kill.is_set():
                    return
                equipment_frames = self._read_equipment()
                if equipment_frames is None:
                    return  # killed mid-equipment
                if equipment_frames is _EQUIP_UNAVAILABLE:
                    # Trial/preview agent (or a dropped Equipment tab): equipment was
                    # already escaped out of.  Don't export it — its base/skills are the
                    # trial preset, not the user's — just advance past (H18).
                    _log.info(
                        "agent_skip_trial — equipment unavailable at strip position %d; "
                        "not exported",
                        visited,
                    )
                else:
                    yield agent_idx, base_frame, skills_frame, equipment_frames
                    agent_idx += 1
            else:
                # Unowned (Lv.1 + static white ">>") → skip cheaply and advance past.  We
                # SKIP, never STOP: even if one owned agent were ever misread, the ring still
                # closes after the rest are captured (completeness > the speed of an early-out
                # — entry lands on an arbitrary strip position, so "stop at first unowned"
                # could orphan the owned agents before the entry point).
                _log.info(
                    "agent_skip — unowned agent (Lv.1 + static white chevron) at strip position %d",
                    visited,
                )
                if visited == 1:
                    self._save_nav("first_unowned", base_frame)

            # Advance to the next strip position.  A no-op means the chevron didn't move
            # the selection at all (degenerate / non-looping strip) → nothing left to do.
            if not self._advance(+1):
                _log.info(
                    "agent_scan_done — advance no-op after %d owned (%d visited)",
                    agent_idx,
                    visited,
                )
                return


# ── Public scanner ────────────────────────────────────────────────────────────


def scan_agents(
    capture_fn: CaptureFunc,
    calib: CalibrationResult,
    archive_dir: Path | None = None,
    ocr_engine: str = "tesseract",
    debug_overlays: bool = False,
    on_item: callable | None = None,
) -> tuple[list[ZodAgent], list[dict], list[ZodDisc], list[ZodWEngine]]:
    """Scan all agents in the roster. Game must be on the agent detail page.

    on_item: optional callback(scanned, total) called after each agent position
    is processed (owned or skipped). total is always None for agents.

    Returns (agents, issues, equipped_discs, equipped_engines).
    equipped_discs and equipped_engines carry full ZodDisc/ZodWEngine objects
    with location already set to the owning agent key. Pass these to the
    fingerprint reconciliation step (T1.5) to stamp location on scanned discs/engines.
    """
    recognizer = make_recognizer(ocr_engine)
    suppress_flag: list = [False]  # shared with kill listener to allow nav Escapes
    kill_event, listener = make_kill_listener(suppress_flag=suppress_flag)
    navigator = AgentNavigator(
        capture_fn,
        calib,
        kill_event,
        suppress_flag=suppress_flag,
        archive_dir=archive_dir,
        recognizer=recognizer,
    )

    agents: list[ZodAgent] = []
    issues: list[dict] = []
    equipped_discs: list[ZodDisc] = []
    equipped_engines: list[ZodWEngine] = []
    scanned = 0

    try:
        for agent_idx, base_frame, skills_frame, equipment_frames in navigator.scan():
            key, level, ascension, base_conf = _extract_base_stats(base_frame, calib, recognizer)
            mindscape, talent, skill_conf = _extract_skills(skills_frame, calib, recognizer)
            conf = {**base_conf, **skill_conf}

            if archive_dir is not None:
                dd = archive_dir / f"agent_{agent_idx:03d}"
                dd.mkdir(parents=True, exist_ok=True)
                base_frame.save(dd / "base_stats.png")
                skills_frame.save(dd / "skills.png")
                for i, ef in enumerate(equipment_frames):
                    if ef is not None:  # None = empty slot (H18), not captured
                        ef.save(dd / f"equip_slot_{i}.png")
                if debug_overlays:
                    # Self-validating artifacts: draw the scanner's click targets +
                    # OCR crop boxes onto each frame so misalignment is visible (H12).
                    from . import debug_overlay as _dbg

                    _dbg.draw_base_overlay(base_frame, calib).save(dd / "base_stats_overlay.png")
                    _dbg.draw_skills_overlay(skills_frame, calib).save(dd / "skills_overlay.png")
                    for i, ef in enumerate(equipment_frames):
                        if ef is not None:
                            _dbg.draw_equip_overlay(ef, calib, active_slot=i).save(
                                dd / f"equip_slot_{i}_overlay.png"
                            )

            scanned += 1
            # Empty key = normalize_agent rejected a below-floor match (T5); its real
            # sub-floor score (e.g. 30–84) sails past the < _CRITICAL_CONF gate, so the
            # key itself must be checked or we'd build an agent with an empty key.
            if not key or base_conf["key"] < _CRITICAL_CONF:
                issues.append(
                    {
                        "agent": agent_idx,
                        "status": "critical_fail",
                        "confidence": conf,
                    }
                )
                if on_item is not None:
                    on_item(scanned, None)
                continue

            low = {k: v for k, v in conf.items() if v < _LOW_CONF_THRESHOLD}
            if low:
                issues.append(
                    {
                        "agent": agent_idx,
                        "key": key,
                        "status": "low_confidence",
                        "fields": low,
                    }
                )

            # H25.1 Lv.60 talent floor: a built agent reading 0 on any skill is almost
            # certainly an OCR miss (badge classifier failed) — surface it explicitly.
            if level >= 60:
                for _sname in ("basic", "dodge", "assist", "special", "chain"):
                    if getattr(talent, _sname) == 0:
                        issues.append(
                            {
                                "agent": agent_idx,
                                "key": key,
                                "status": "talent_zero_lv60",
                                "skill": _sname,
                            }
                        )

            # E4: parse each equipment slot frame with full extractors
            for slot_idx, equip_frame in enumerate(equipment_frames):
                if equip_frame is None:  # empty slot (H18) — nothing equipped
                    continue
                if slot_idx < 6:
                    disc, _ = scan_equipped_disc_frame(
                        equip_frame,
                        calib,
                        agent_key=key,
                        slot_key=_slot_number(slot_idx),
                        engine=recognizer,
                    )
                    if disc is not None:
                        equipped_discs.append(disc)
                else:
                    w_engine = scan_equipped_engine_frame(
                        equip_frame,
                        calib,
                        agent_key=key,
                        engine=recognizer,
                    )
                    if w_engine is not None:
                        equipped_engines.append(w_engine)

            agents.append(
                ZodAgent(
                    key=key,
                    level=level,
                    constellation=mindscape,
                    ascension=ascension,
                    talent=talent,
                )
            )
            if on_item is not None:
                on_item(scanned, None)
    finally:
        listener.stop()

    return agents, issues, equipped_discs, equipped_engines


# ── Offline single-frame extraction ──────────────────────────────────────────


def scan_single_frame_agent(
    base_frame: Image.Image,
    skills_frame: Image.Image,
    calib: CalibrationResult,
    ocr_engine: str = "tesseract",
) -> tuple[ZodAgent | None, dict]:
    """Extract one agent from static frames — no synthetic input, no navigator.

    Used for offline testing / debugging from reference screenshots.
    Returns (agent, confidence_map). agent is None on critical failure.
    """
    recognizer = make_recognizer(ocr_engine)
    key, level, ascension, base_conf = _extract_base_stats(base_frame, calib, recognizer)
    mindscape, talent, skill_conf = _extract_skills(skills_frame, calib, recognizer)
    conf = {**base_conf, **skill_conf}
    # Empty key = normalize_agent rejected a below-floor match (T5); see scan_agents.
    if not key or base_conf["key"] < _CRITICAL_CONF:
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
