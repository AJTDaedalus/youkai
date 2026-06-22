# DECISIONS

Tradeoffs and rejected alternatives, newest first.

---

## D1 — Skill-badge digit reader: per-digit template matching, oracle-sourced, full 0–9 (2026-06-17)

**Context:** T3 proved `_read_skill_badge`'s fill-ratio tier heuristic is exhausted —
the per-digit fill distributions overlap (3⊂5, 6⊂8, two-digit units 0/2/3/4/5 collapse),
so no scalar threshold separates them (see `LOG_run_validation_fixes.md` T3). A
shape-based classifier is required.

**Decision:** Replace the units-digit fill-tier classification with **per-digit template
matching** (normalized-correlation) against reference glyphs. Keep the existing
width/round tens-place logic (single blob → 1; b0 narrow → tens "1"; b0 wide+round →
"0"-prefix) — T3 showed it is reliable; only the units blob (b1) is misclassified.

**Reference-glyph source: oracle-labeled blobs, NOT font rendering.**
- Font rendering rejected: the stylized bold-italic badge font is (a) likely unavailable,
  and (b) would not reproduce the live pipeline's 3× Lanczos upscale + fixed-threshold +
  connected-component artifacts, so rendered glyphs would not pixel-match the runtime
  blobs they must classify.
- Oracle blobs are pixel-identical in rendering domain and give labeled truth for free
  via `oracle_talent.json`.

**Coverage gap (the binding constraint):** the 24-agent oracle set has **zero level-9
samples** and only **one each for 4 and 6** (units-digit counts: 0:8 1:40 2:37 3:5 4:1
5:11 6:1 7:7 8:10 9:0). A pure oracle-template classifier would be *structurally
incapable of ever outputting 9* and fragile on 4/6.

**Resolution (user, 2026-06-17): close the gap first.** Build a complete 0–9 reference
set before shipping the rewrite — source the missing 9 and extra 4/6 (and the high
A-rank 13–16 tens path) from a **fresh capture** of two purpose-built in-game agents
(user has one with a level-9 skill, one with skills at 13–16), hand-labeled into a
dedicated `badge_glyphs` reference. This sidesteps the "find an unlabeled 9 in the
archive" problem (the current classifier can't output 9, so it can't even surface
candidates).

**Defense-in-depth retained even with full coverage:** any units blob whose best
template correlation is below a floor returns a **low-confidence** read (< `_LOW_CONF_THRESHOLD`
70) so it surfaces in issues rather than emitting a silent wrong digit — consistent with
the `gui_layout_fragile` lesson (don't ship heuristics you can't verify) and the T2/T5
"safe failure direction" norm.

**Rejected:**
- *Recalibrate fill tiers* — T3 finding 1: the classes overlap; recalibration only swaps
  which pairs collide and would regress the currently-correct 10/12.
- *Flagged-fallback-only for digit 9 (defer the gap)* — leaves a known blind spot; the
  fallback path is the broken heuristic, so 9 stays wrong (just flagged). User chose full
  coverage instead.
- *Defer Issue 2 entirely* — user opted to fix it now.

**Test honesty:** templates are built from oracle blobs, so evaluating on the same blobs
is circular. Acceptance uses **leave-one-agent-out** cross-validation (build templates
from all-but-one agent, classify the held-out agent) to prove generalization, plus the
fresh-capture agents as a fully held-out set for 9/13–16.
