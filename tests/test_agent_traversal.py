"""H8 dry-run tests: detail-page top-strip traversal (AgentNavigator.scan()).

A `_StripSim` subclass drives the REAL scan()/_advance()/_read_equipment() logic
against synthetic frames — no pynput, no game.  The sim models the live-confirmed
strip behaviour: ">"/"<" move the selection ±1 and WRAP around (H16 — the strip is
CIRCULAR).  Owned agents default to the prefix [0, n_owned) but may be placed
anywhere via `owned_idxs`; the rest are unowned.  Clicking a tab/slot/menu-button
updates rendered state so the real predicates (_on_detail_page, _tab_active,
_chevron_color_fracs, _equip_tab_rendered, _slot_panel_rendered, _strip_id) all fire
correctly.  scan() anchors on the start position and stops when the ring closes.
"""
from __future__ import annotations

import threading

import numpy as np
import pytest
from PIL import Image

from youkai_ocr import agent_scanner as A
from youkai_ocr.agent_scanner import (
    _PHASH_SIZE,
    _portrait_phash,
    AgentNavigator,
    _strip_id,
    _chevron_color_fracs,
    _classify_owned,
    _OWN_CHEVRON_BBOX,
    _phash_hamming,
    _MENU_BASE_BUTTON,
    _STRIP_NEXT,
    _STRIP_PREV,
    _TAB_BASE_STATS,
    _TAB_SKILLS,
    _TAB_EQUIPMENT,
    _TAB_EQUIP_IDX,
    _tab_active,
    _TAB_ACTIVE_BBOXES,
    _ALL_SLOT_CENTERS,
    _EQUIP_GATE_CENTER,
    _EQUIP_GATE_RADIUS,
    _EQUIP_RING_BBOX,
    _SLOT_PANEL_BBOX,
    _CHARACTER_RENDER_BBOX,
    _STRIP_PHASH_BBOX,
)
from youkai_ocr.capture import CalibrationResult


def _identity_calib() -> CalibrationResult:
    return CalibrationResult(scale_x=1.0, scale_y=1.0, frame_width=1920, frame_height=1080)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Make the navigator's time.sleep a no-op so the dry-run is fast."""
    monkeypatch.setattr(A.time, "sleep", lambda *_a, **_k: None)


# ── Strip simulator ───────────────────────────────────────────────────────────

_BAR_STEP = 60   # px the strip identity bar shifts per agent index
_BAR_W    = 40


class _StripSim(AgentNavigator):
    def __init__(self, n_owned: int, n_total: int | None = None, start_idx: int | None = None,
                 owned_idxs: set[int] | None = None):
        super().__init__(capture_fn=None, calib=_identity_calib(),
                         kill_event=threading.Event(), suppress_flag=[False])
        self.n_owned = n_owned
        self.n_total = n_total if n_total is not None else n_owned + 3
        # Default: owned is the contiguous prefix [0, n_owned).  Pass owned_idxs to
        # model interleaved ownership (H15 skip-don't-stop traversal).
        self.owned_idxs = owned_idxs if owned_idxs is not None else set(range(n_owned))
        self.idx = start_idx if start_idx is not None else max(0, n_owned - 1)
        self.tab = 0
        self.on_detail = False
        self.panel_open = False
        self.cur_slot = -1        # which hexagon slot's panel is open (H18 slot-switch gate)
        self.empty_slots: set[int] = set()   # slot indices the action-bar gate reports EMPTY (H21)
        self.escapes = 0
        self.click_log: list[tuple[int, int]] = []
        # AgentNavigator stores capture_fn as the instance attr self._capture,
        # so point it at the renderer (a method override would be shadowed).
        self._capture = self._render

    # --- overrides: no pynput, synthetic frames ---
    def _ring_close_key(self, frame) -> str:
        # H23: return the strip-position index as a string so ring-close fires correctly
        # without a real OCR recognizer.  The real implementation uses normalize_agent.
        return str(self.idx)

    def _slot_equipped_from_panel(self, frame) -> bool:
        # H21: model the action-bar equipped/empty gate without OCR — the currently-open slot
        # (cur_slot, set by the click) is equipped unless listed in empty_slots.
        return self.cur_slot not in self.empty_slots

    def _press_escape(self) -> None:
        self.escapes += 1
        self.panel_open = False

    def _click(self, ref_x: int, ref_y: int) -> None:
        self.click_log.append((ref_x, ref_y))
        act = self._match(ref_x, ref_y)
        if act == "enter":
            self.on_detail, self.tab = True, 0
        elif act == "next":
            self.idx = (self.idx + 1) % self.n_total   # H16: circular strip — wraps
        elif act == "prev":
            self.idx = (self.idx - 1) % self.n_total   # H16: circular strip — wraps
        elif act in ("tab0", "tab1", "tab2"):
            self.tab = int(act[-1])
        elif act == "slot":
            self.panel_open = True
            self.cur_slot = next(
                (k for k, (sx, sy) in enumerate(_ALL_SLOT_CENTERS)
                 if self._near(ref_x, ref_y, sx, sy)),
                self.cur_slot,
            )

    @staticmethod
    def _near(x, y, tx, ty) -> bool:
        return abs(x - tx) <= 4 and abs(y - ty) <= 4

    def _match(self, x, y) -> str:
        for (tx, ty), name in (
            (_MENU_BASE_BUTTON, "enter"), (_STRIP_NEXT, "next"), (_STRIP_PREV, "prev"),
            (_TAB_BASE_STATS, "tab0"), (_TAB_SKILLS, "tab1"), (_TAB_EQUIPMENT, "tab2"),
        ):
            if self._near(x, y, *(tx, ty)):
                return name
        if any(self._near(x, y, sx, sy) for sx, sy in _ALL_SLOT_CENTERS):
            return "slot"
        return "none"

    def _render(self) -> Image.Image:
        arr = np.full((1080, 1920, 3), 100, dtype=np.uint8)  # mid-gray base (luma≈100)
        if self.on_detail:
            owned = self.idx in self.owned_idxs
            x0, y0, x1, y1 = _CHARACTER_RENDER_BBOX
            # Render colour no longer drives ownership (D37) — it only feeds the _agent_id
            # pHash.  Owned → red, unowned → blue, both full-colour (the live reality: ZZZ
            # renders unowned agents in colour too, which is why the old hue test failed).
            arr[y0:y1, x0:x1] = (210, 40, 40) if owned else (40, 60, 200)
            # D37 ownership signal: the level-up ">>" chevron — animated GREEN on owned,
            # static WHITE on unowned.  (_agent_level has no recognizer in the sim → 0, so
            # _classify_owned resolves every agent via this chevron.)
            cx0, cy0, cx1, cy1 = _OWN_CHEVRON_BBOX
            arr[cy0:cy1, cx0:cx1] = (0, 200, 0) if owned else (255, 255, 255)
            # H18: unique per-agent identity stripe so _agent_id (render pHash) distinguishes
            # agents — the live reality each full-body render is unique.  The stripe sits in the
            # CHARACTER_RENDER bbox, clear of the ownership chevron, so it never perturbs it.
            ix = x0 + (self.idx % 12) * 53
            arr[y0:y1, ix:ix + 50] = 255
            tx0, ty0, tx1, ty1 = _TAB_ACTIVE_BBOXES[self.tab]
            arr[ty0:ty1, tx0:tx1] = (245, 200, 30)        # ZZZ gold → hue≈24
            sx0, sy0, sx1, sy1 = _STRIP_PHASH_BBOX
            arr[sy0:sy1, sx0:sx1] = 20                     # dark strip bg
            bx = sx0 + 20 + self.idx * _BAR_STEP
            arr[sy0:sy1, bx:bx + _BAR_W] = 255             # identity bar (x encodes idx)
            if self.tab == 2:
                ex, ey = _EQUIP_GATE_CENTER
                r = _EQUIP_GATE_RADIUS + 4
                arr[ey - r:ey + r, ex - r:ex + r] = 255    # bright engine hexagon
            if self.panel_open:
                px0, py0, px1, py1 = _SLOT_PANEL_BBOX
                arr[py0:py1, px0:px1] = 0                  # dark slot-select panel (stays "rendered")
                # H18: per-slot title mark so _open_slot's slot-switch gate sees the panel
                # content change between consecutive slots (kept small → dark_frac stays high).
                mx = px0 + 10 + max(self.cur_slot, 0) * 40
                arr[py0:py1, mx:mx + 30] = 255
                # H19: per-slot BODY signature (models real disc detail — main stat/substats differ
                # between discs even of the same SET).  _open_slot now gates on _SLOT_DETAIL_BBOX
                # (title + body), so a distinct band per slot is what lets the switch test fire.
                by = py1 + 20 + max(self.cur_slot, 0) * 50
                arr[by:by + 40, px0 + 20:px1 - 20] = 200
        return Image.fromarray(arr, "RGB")


def _run(sim: _StripSim) -> list[int]:
    """Run scan() to completion; return the sim idx at each yielded agent."""
    seq: list[int] = []
    for _agent_idx, _base, _skills, _equip in sim.scan():
        # yield happens before the ">" advance, so sim.idx == this agent's index.
        seq.append(sim.idx)
    return seq


# ── pHash / predicate unit tests ───────────────────────────────────────────────

def test_phash_stable_and_length():
    frame = Image.new("RGB", (1920, 1080), color=(128, 64, 200))
    c = _identity_calib()
    h = _portrait_phash(frame, c, 500, 400)
    assert h == _portrait_phash(frame, c, 500, 400)
    assert len(h) == _PHASH_SIZE * _PHASH_SIZE and set(h) <= {"0", "1"}


def test_strip_id_changes_between_indices():
    c = _identity_calib()
    a = _strip_id(_StripSim(5, start_idx=0)._render_at(2), c)
    b = _strip_id(_StripSim(5, start_idx=0)._render_at(3), c)
    same = _strip_id(_StripSim(5, start_idx=0)._render_at(2), c)
    assert _phash_hamming(a, same) == 0
    assert _phash_hamming(a, b) > A._STRIP_CHANGE_MIN_BITS


def test_chevron_signal_separates_owned_unowned():
    # D37: the ">>" chevron is GREEN on owned, WHITE on unowned.  The sim renders both;
    # the pure pixel op must report green for an owned idx and white for an unowned one.
    c = _identity_calib()
    sim = _StripSim(n_owned=3, n_total=6, owned_idxs={0, 1, 2})
    sim.on_detail = True
    g_owned, w_owned = _chevron_color_fracs(sim._render_at(0), c)
    g_un, w_un = _chevron_color_fracs(sim._render_at(4), c)
    assert g_owned > A._OWN_GREEN_FRAC_MIN and w_owned < A._OWN_WHITE_FRAC_MIN
    assert w_un > A._OWN_WHITE_FRAC_MIN and g_un < A._OWN_GREEN_FRAC_MIN


def test_classify_owned_rules():
    # level >= 2 ⇒ owned regardless of chevron (covers white-pill ascension breakpoints).
    assert _classify_owned(50, 0.0, 0.20)          # owned Lv.50/50 with a WHITE ">>" (agent_023)
    assert _classify_owned(60, 0.0, 0.0)           # owned, maxed ("MAX" pill — no green/white)
    # Lv.1 / unreadable (0) ⇒ chevron decides.
    assert _classify_owned(1, 0.16, 0.0)           # fresh owned: green ">>"
    assert not _classify_owned(0, 0.0, 0.16)       # unowned: blank level + white ">>"
    assert not _classify_owned(1, 0.0, 0.16)       # unowned: Lv.1 + white ">>"
    assert _classify_owned(0, 0.0, 0.0)            # ambiguous ⇒ bias to OWNED (capture)


# ── Traversal dry-runs ─────────────────────────────────────────────────────────

def test_visits_each_owned_once_in_order_skipping_grayout():
    # H16: circular strip, anchored on entry.  Start mid-roster at idx=2; the ring walks
    # forward (2,3,4 → grayed 5,6,7 skipped → wrap 0,1) and stops back at the start.
    sim = _StripSim(n_owned=5, start_idx=2)
    seq = _run(sim)
    assert seq == [2, 3, 4, 0, 1]              # ring order from the start position
    assert sorted(seq) == [0, 1, 2, 3, 4]      # every owned agent visited exactly once
    assert sim.idx == 2                          # ring closed: returned to the start
    assert sim.escapes == 5                      # exactly one Escape per OWNED agent (equipment)


def test_skips_interleaved_grayout():
    # H15/H16: ownership is NOT assumed contiguous — grayed agents are skipped, not a stop.
    sim = _StripSim(n_owned=3, n_total=6, start_idx=0, owned_idxs={0, 2, 5})
    seq = _run(sim)
    assert seq == [0, 2, 5]                    # owned at any position are all visited
    assert sim.idx == 0                          # ring closed back at the start
    assert sim.escapes == 3


def test_single_owned_agent():
    # One owned + a grayed tail on a circular strip: the ring wraps through the grayed
    # agents and closes back at the single owned start.
    sim = _StripSim(n_owned=1, start_idx=0)
    assert _run(sim) == [0]
    assert sim.escapes == 1


def test_single_agent_total_advance_no_op():
    # Degenerate strip of ONE total agent: the chevron can't move the selection, so
    # _advance no-ops and the scan terminates without a ring-closure (H16 fallback).
    sim = _StripSim(n_owned=1, n_total=1, start_idx=0)
    assert _run(sim) == [0]
    assert sim.escapes == 1



def test_kill_event_stops_traversal():
    sim = _StripSim(n_owned=5, start_idx=0)
    sim._kill.set()
    assert _run(sim) == []


def test_equipment_reads_seven_slots_no_inter_slot_escape():
    sim = _StripSim(n_owned=1, start_idx=0)
    list(sim.scan())
    slot_clicks = [c for c in sim.click_log if any(
        abs(c[0] - sx) <= 4 and abs(c[1] - sy) <= 4 for sx, sy in _ALL_SLOT_CENTERS)]
    assert len(slot_clicks) == 7               # all 7 slots clicked
    assert sim.escapes == 1                    # one Escape total, not one-per-slot


def test_capture_tab_reclicks_dropped_tab_click():
    # H17: the live failure — the Equipment tab click was DROPPED (fired during the
    # Skills page's entrance animation), so the page stayed on Skills and the 7 "equip"
    # frames were the still-open Skills page.  _capture_tab must re-CLICK (not just
    # re-capture) until the pill goes yellow.
    class _DropFirstTab2(_StripSim):
        def __init__(self, *a, drop=2, **k):
            super().__init__(*a, **k)
            self._drop_remaining = drop

        def _click(self, ref_x, ref_y):
            # Swallow the first `drop` clicks that target the Equipment tab.
            if self._near(ref_x, ref_y, *_TAB_EQUIPMENT) and self._drop_remaining > 0:
                self._drop_remaining -= 1
                self.click_log.append((ref_x, ref_y))   # the click happened, game ignored it
                return
            super()._click(ref_x, ref_y)

    sim = _DropFirstTab2(n_owned=1, start_idx=0, drop=2)
    sim.on_detail = True
    frame = sim._capture_tab(_TAB_EQUIP_IDX)
    assert _tab_active(frame, _identity_calib(), _TAB_EQUIP_IDX)   # recovered onto Equipment
    assert sim.tab == 2
    tab2_clicks = [c for c in sim.click_log if sim._near(c[0], c[1], *_TAB_EQUIPMENT)]
    assert len(tab2_clicks) >= 3       # initial drop ×2 + at least one recovering re-click


def test_open_slot_reclicks_dropped_second_slot():
    # H18 (issue 1): the live failure — clicking the FIRST slot opens the disc-select view
    # with a slow layout wipe; the SECOND slot click, fired during that animation, is silently
    # DROPPED, so the 2nd disc is never opened.  _open_slot must re-CLICK (not just re-capture)
    # the slot until its panel actually opens/switches.
    class _DropSlot1(_StripSim):
        """Swallow the first `drop` clicks aimed at hexagon slot index 1 (the 2nd slot)."""
        def __init__(self, *a, drop=2, **k):
            super().__init__(*a, **k)
            self._drop_remaining = drop

        def _click(self, ref_x, ref_y):
            sx, sy = _ALL_SLOT_CENTERS[1]
            if self._near(ref_x, ref_y, sx, sy) and self._drop_remaining > 0:
                self._drop_remaining -= 1
                self.click_log.append((ref_x, ref_y))   # the click happened; the game ignored it
                return
            super()._click(ref_x, ref_y)

    sim = _DropSlot1(n_owned=1, start_idx=0, drop=2)
    list(sim.scan())
    # Every one of the 7 slots must end up opened: the panel identity recorded for each slot
    # is distinct, so a dropped 2nd-slot click that was NOT recovered would leave only 6 unique.
    sx1, sy1 = _ALL_SLOT_CENTERS[1]
    slot1_clicks = [c for c in sim.click_log if sim._near(c[0], c[1], sx1, sy1)]
    assert len(slot1_clicks) >= 3              # 2 dropped + ≥1 recovering re-click
    assert sim.escapes == 1                    # still exactly one Escape (the slot loop completed)


def test_open_slot_same_set_adjacent_slots_no_reclick_no_skip():
    # H19 ("disc N skipped" + "errors from clicking repeatedly"): two adjacent slots holding the SAME
    # disc set have near-identical TITLES.  The old title-only switch test could neither tell them
    # apart (endless re-clicks → the disc-4 "hang") nor avoid banking a duplicate (a skipped slot).
    # Gating on the detail BODY (substats differ) fixes both: each slot is opened with exactly ONE
    # click and banked distinctly.
    class _SameSet(_StripSim):
        def _render(self):
            img = super()._render()
            if self.on_detail and self.panel_open:
                arr = np.array(img)
                px0, py0, px1, py1 = _SLOT_PANEL_BBOX
                # Title region identical for every slot (same set) — wipe the per-slot title mark and
                # paint a FIXED glyph.  The body band (drawn by super()) still differs per slot.
                arr[py0:py1, px0:px1] = 0
                arr[py0:py1, px0 + 10:px0 + 40] = 255
                return Image.fromarray(arr, "RGB")
            return img

    sim = _SameSet(n_owned=1, start_idx=0)
    list(sim.scan())
    slot_clicks = [c for c in sim.click_log if any(
        sim._near(c[0], c[1], sx, sy) for sx, sy in _ALL_SLOT_CENTERS)]
    assert len(slot_clicks) == 7    # exactly one click per slot — no spurious same-set re-clicks
    assert sim.escapes == 1


def test_advance_does_not_skip_on_weak_strip_signal():
    # H18 (issue 2): a single ">" moves only the selection highlight by one thumbnail, so the
    # thin strip-band pHash barely changes.  If _advance keyed on the strip band it would
    # mis-read a real move as "no move", re-click, and SKIP an agent.  Keyed on the big
    # character render, one click per advance suffices → every owned agent visited exactly once.
    sim = _StripSim(n_owned=6, n_total=6, start_idx=0)   # all owned, circular ring of 6
    seq = _run(sim)
    assert seq == [0, 1, 2, 3, 4, 5]           # no skips, no duplicates
    # exactly one ">" click per advance (6 advances around the ring) — no spurious re-clicks
    next_clicks = [c for c in sim.click_log if sim._near(c[0], c[1], *_STRIP_NEXT)]
    assert len(next_clicks) == 6


def test_trial_agent_equipment_unavailable_is_skipped_not_hung():
    # H18 (issue 4): a trial/preview agent's Equipment tab shows "not available in preview mode"
    # instead of the hexagon, which used to leave the scanner poking a dead modal.  When the
    # hexagon never renders, _read_equipment must Escape (clear the modal) and return the
    # _EQUIP_UNAVAILABLE sentinel so the agent is NOT exported and the ring keeps moving.
    from youkai_ocr.agent_scanner import _EQUIP_UNAVAILABLE  # noqa: F401  (documents the contract)

    class _TrialAt(_StripSim):
        def __init__(self, *a, trial_idx, **k):
            super().__init__(*a, **k)
            self.trial_idx = trial_idx

        def _render(self):
            img = super()._render()
            if self.on_detail and self.tab == 2 and self.idx == self.trial_idx:
                # A real trial/preview frame shows NO hexagon at all — blank the whole ring
                # (all 6 discs AND the engine), not just the engine.  Since H20 the render-gate
                # is rendered if ANY disc reads equipped OR the engine is bright, so blanking the
                # engine alone would still read "rendered" off the discs (D35).
                arr = np.array(img)
                rx0, ry0, rx1, ry1 = _EQUIP_RING_BBOX
                arr[ry0:ry1, rx0:rx1] = 30                # dark (preview modal, no hexagon)
                return Image.fromarray(arr, "RGB")
            return img

    sim = _TrialAt(n_owned=3, n_total=3, start_idx=0, trial_idx=1)
    seq = _run(sim)
    assert seq == [0, 2]                       # the trial agent (idx 1) is skipped, others kept
    assert sim.escapes == 3                     # 2 equipment Escapes + 1 modal-dismiss for the trial


def test_read_equipment_all_empty_clicks_every_slot_records_none():
    # H21/D36: the pre-click pixel skip is GONE (it false-skipped equipped engines on ~4/5 agents).
    # A fully-unequipped agent (Koleda) is now resolved by CLICKING each slot and reading the
    # action bar ("Equip" → empty).  Every slot is clicked, all 7 resolve empty → [None]*7, and ONE
    # Escape restores the strip bar (a panel WAS opened — unlike the old no-click path).
    sim = _StripSim(n_owned=1, start_idx=0)
    sim.on_detail = True
    sim.empty_slots = set(range(7))                    # action-bar reports every slot empty
    frames = sim._read_equipment()
    assert frames is not A._EQUIP_UNAVAILABLE          # render-gate passes (bright engine hexagon)
    assert frames == [None] * 7                         # nothing equipped → nothing recorded
    slot_idxs = {k for c in sim.click_log
                 for k, (sx, sy) in enumerate(_ALL_SLOT_CENTERS) if sim._near(c[0], c[1], sx, sy)}
    assert slot_idxs == set(range(7))                  # every slot visited (incl. the engine)
    assert sim.escapes == 1                            # one Escape after the select view


def test_read_equipment_records_only_equipped_slots_via_action_bar():
    # H21/D36: a mixed agent — slot 2 (a disc) and slot 6 (the engine) empty, the rest equipped.
    # Every slot is clicked; only the equipped ones are recorded (the empties yield None, so no
    # inventory[0] item is mis-assigned).  This is the engine-recovery the fix targets: slot 6 is
    # CLICKED and correctly resolved instead of being pre-skipped.
    sim = _StripSim(n_owned=1, start_idx=0)
    sim.on_detail = True
    sim.empty_slots = {2, 6}
    frames = sim._read_equipment()
    assert len(frames) == 7
    assert frames[2] is None and frames[6] is None
    assert all(frames[i] is not None for i in (0, 1, 3, 4, 5))
    slot_idxs = {k for c in sim.click_log
                 for k, (sx, sy) in enumerate(_ALL_SLOT_CENTERS) if sim._near(c[0], c[1], sx, sy)}
    assert slot_idxs == set(range(7))                  # the engine (slot 6) IS clicked now
    assert sim.escapes == 1


# helper used above: render a frame at a given index without mutating much state
def _render_at(self, idx):
    prev, self.idx, prevd = self.idx, idx, self.on_detail
    self.on_detail = True
    img = self._render()
    self.idx, self.on_detail = prev, prevd
    return img


_StripSim._render_at = _render_at
