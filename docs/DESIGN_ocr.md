# DESIGN — ZZZ Inventory OCR Scanner ("youkai-ocr")

**Date**: 2026-06-01
**Author**: Opus 4.8 (planner)
**Status**: Plan — for execution with Sonnet per `TASKS_ocr.md`.
**Supersedes**: the entire passive-decryption program (v1–v4). Per **D14**, passive game-state
decryption is recommended STOP (session cipher not passively recoverable: C0 + two-sided key
exchange). This document pivots the project from "read the wire" to "read the screen."
**Template**: [AdeptiScanner-ZZZ](https://github.com/D1firehail/AdeptiScanner-ZZZ) (D1firehail) —
a proven, external-only OCR scanner with a long no-ban history across GI and ZZZ.

---

## 1. Problem statement

We want a full, machine-readable export of the player's ZZZ account state:

- **Full Drive Disc inventory** — every disc with set, slot, rarity, level, main stat, substats,
  lock state, and which agent (if any) has it equipped.
- **Full W-Engine inventory** — every engine with level, promotion (ascension), upgrade phase
  (refinement), lock, and equipped agent.
- **Agent roster** — each agent with level, promotion, **Mindscape Cinema** (0–6), the **6 skill /
  talent levels**, and (by reconstruction) their equipped discs and engine.

The packet-sniffer path that previously produced this (`PlayerData` → `ZodExport`) is dead: the
session cipher is not passively decryptable (D14). The data is, however, all rendered on screen. We
extract it with OCR, the same way the community's GI/ZZZ scanners do.

**Output contract is unchanged.** The downstream consumer is the community ZZZ build optimizer that
ingests `ZodExport` JSON (`format: "GOOD"`, `source: "Youkai"`). We preserve that contract exactly
so existing optimizer imports keep working — only the *source of the data* changes (screen, not wire).

## 2. Scope decisions (from the user, 2026-06-01)

| Decision | Choice | Consequence |
|---|---|---|
| **Capture modality** | Automated UI control (Adepti-style) | Tool drives the mouse to scroll inventory + screenshots each item. See §5 — must be **external-only**. |
| **Runtime** | Python (was "sidecar"; now standalone — see below) | OpenCV + Tesseract/PaddleOCR + rapidfuzz. Matches existing `packet_research/` Python. |
| **v1 scope** | Full spec in one milestone | Discs **and** agents (gear + engines + talents + mindscapes) together; ZOD schema extended for talents. |
| **Youkai codebase** | **Full scrap justified** | Youkai is a packet-sniffer clone built around the abandoned decryption path; nothing in `capture.rs`/`monitor.rs`/decrypt bins/`wish.rs` is reusable for OCR. **Carry forward only the ZOD output contract** (`zod.rs`). The "sidecar" therefore becomes the **primary application**, written in Python, not a child process of a Rust app. |

**Net architecture**: a standalone Python application (`youkai-ocr`) modeled on AdeptiScanner-ZZZ,
emitting the same `ZodExport` JSON the optimizer already accepts.

## 3. The output schema (and the one required extension)

The existing contract (`youkai/src/zod.rs`) — reproduced as the Python emitter's target:

```
ZodExport { format:"GOOD", version, source:"Youkai", characters[], discs[], weapons[] }
ZodDisc   { setKey, slotKey "1".."6", level, rarity, mainStatKey, location, lock, substats[{key,value}] }
ZodWEngine{ key, level, ascension, refinement, location, lock }
ZodAgent  { key, level, constellation /*=mindscape 0-6*/, ascension }   ◄── INCOMPLETE
```

**Gap**: `ZodAgent` has no talent levels. ZZZ agents have **6 skills**: Basic Attack, Dodge, Assist,
Special Attack, Chain Attack (numeric), and the **Core Skill / Core Passive** (rank-graded). The user
explicitly wants talent levels, so the schema must grow:

```
ZodAgent { key, level, constellation, ascension,
           talent: { basic, dodge, assist, special, chain, core } }   ◄── NEW
```

This is added in two places that must stay in lockstep: the Rust struct (kept only as the canonical
schema definition / for any residual GI export) **and** the Python emitter. Equipped relationships
stay where they already are — on each disc/engine's `location` — so agents do **not** carry a gear
list; it's reconstructed downstream from `location`. (See **OQ-ocr-3** for the Core-skill encoding.)

## 4. Domain model — what each ZZZ screen shows

The OCR must read these specific fields from these specific screens (English PC client):

**Drive Disc detail panel** (Inventory → Drive Discs → select):
- Name → **set** (fuzzy-match to canonical set list → ZOD key).
- Rarity S/A/B → `rarity` int (per existing convention; **OQ-ocr-2**).
- `Lv. N` → `level` (0–15).
- Slot/Partition number (1–6) → `slotKey`. Read directly; cross-check against main-stat legality.
- Main stat (name + value) → `mainStatKey`.
- 1–4 substats (name + value) → `substats[]`.
- Lock icon state → `lock`.
- "Equipped" + agent portrait → `location` (match portrait to agent-portrait template library).

**W-Engine detail panel** (Inventory → W-Engines → select):
- Name → `key`. Rarity S/A/B. `Lv. N` → `level` (0–60). Promotion stars → `ascension` (0–5).
  Upgrade Phase / Overclock → `refinement` (1–5). Lock. Equipped agent → `location`.

**Agent detail** (Agents → select):
- `Lv. N` → `level`; promotion → `ascension`.
- Mindscape Cinema (film cells 1–6 lit) → `constellation` (0–6).
- Skills page: 6 skill levels → `talent{...}` (Basic/Dodge/Assist/Special/Chain numeric; Core ranked).
- Equipped W-Engine + 6 discs — **not** read here for data (reconstructed from `location`); used only
  as an optional cross-check.

## 5. Safety model — why automated control is acceptable here (the central constraint)

Automated UI control was the user's choice, and the earlier project posture (N1–N4: observation-only,
no client contact) made me flag it. **AdeptiScanner's clean multi-year ban history across HoYo titles
resolves the tension — but only because of *how* it operates.** That "how" becomes a hard, testable
invariant for this project:

> **S-OCR-1 (External-only invariant).** The scanner interacts with the game through **exactly two
> OS-level channels and no others**: (a) reading framebuffer pixels of the game window (screen
> capture), and (b) emitting synthetic mouse/keyboard input via the OS input API. It **never**
> attaches to, reads, writes, allocates in, or injects into the game process; never reads game memory;
> never touches game files; never reads or modifies network traffic. This is the property that makes
> Adepti-class tools non-flagging, and it is non-negotiable.

Supporting rules:
- **S-OCR-2.** No DLL injection, no debugger attach, no `OpenProcess`/`ReadProcessMemory`, no overlay
  that hooks the game's render pipeline. Capture is window/desktop-level (DXGI/BitBlt-class), external.
- **S-OCR-3.** Human-pace input with jitter; honor a global **kill/pause key** (Adepti uses Esc) that
  halts automation immediately and releases the mouse. Never fight the user for the cursor.
- **S-OCR-4.** Read-only against the account: the scanner only *navigates and looks*. It must never
  change a setting, equip/unequip gear, lock/unlock, sell, or craft. Navigation is restricted to
  opening menus and scrolling lists.
- **S-OCR-5.** If any field genuinely cannot be obtained without violating S-OCR-1 (e.g. would require
  memory reads), STOP and surface it — do not improvise a process-attach path.
- **S-OCR-6.** Keep the user's exported account data and any screenshots out of git (`.gitignore`).

A **passive live-capture fallback** (user drives, tool only reads frames — zero synthetic input) is
retained as a documented mode (§9) for users who want even that input channel gone.

## 6. Architecture

Standalone Python app. Layered so each layer is independently testable and the whole thing is
**deterministic and replayable from saved frames** (an audit/debug asset, and a nod to the project's
"files are the source of truth" ethos).

```
┌─ orchestrator ─ scan plan: discs → engines → agents; resume; progress; kill-switch ─┐
│                                                                                      │
│  capture        window locate + resolution/DPI calibration (anchor-based)            │
│      │          external framebuffer grab of detail panel + grid cell                │
│      ▼                                                                                │
│  navigate       synthetic input: open menu, click cell, scroll page, detect end      │
│      │          (Adepti pattern: fixed sort order, known grid geometry)              │
│      ▼                                                                                │
│  preprocess     OpenCV: crop declarative field regions, scale, grayscale, threshold  │
│      │                                                                                │
│      ▼                                                                                │
│  recognize      text → Tesseract/PaddleOCR (+ digit pass);                           │
│      │          icons/colors → template match (rarity, set, portrait, lock, slot)    │
│      ▼                                                                                │
│  normalize      rapidfuzz against canonical ZZZ name DB → ZOD keys;                  │
│      │          numeric range validation; per-field confidence                       │
│      ▼                                                                                │
│  assemble       build ZodDisc/ZodWEngine/ZodAgent → ZodExport JSON                   │
│                 + low-confidence review report + raw-crop archive                    │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

**Key design choices** (full rationale in DECISIONS D15–D18):

- **Resolution strategy — anchor-based calibration, not hard-coded pixels.** Adepti recommends a
  reference window size and depends on exact colors/positions. We require a reference resolution
  (target **1920×1080 windowed**, validate Adepti's 1600×900 too) but compute a scale+offset transform
  from detected anchor UI elements, so non-reference setups degrade gracefully instead of silently
  misreading. Reject unsupported aspect ratios (ultrawide relayouts) in v1.
- **Color hygiene preflight.** Like Adepti, recognition is color-sensitive. On startup, detect/ warn
  about Night Light / f.lux / Reshade / Nvidia filters / HDR and refuse to scan until clean (these are
  the #1 cause of garbage reads in Adepti's issue tracker).
- **Icons & colors via template match, not OCR.** Rarity (color), disc set (icon), equipped agent
  (portrait), lock (overlay), slot (number/position). OCR is reserved for text and numbers.
- **Never trust raw OCR.** Every name is fuzzy-matched to a canonical list; every number is
  range-checked; mismatches are flagged for review rather than written blindly.
- **Name normalization uses small hand-authored lists, not an external data dump.** Numerics are pure
  OCR; stats are a closed ~12-item enum; set/agent/engine names are OCR'd from on-screen text and
  fuzzy-matched against hand-written lists (~20–40 entries each) under `data/zzz_<version>/`. **No
  community data dump is required** (D19). Icon/template matching is reserved for the *one* field where
  text may be absent — the equipped-agent indicator on a disc (portrait vs. name; OQ-ocr-7).

## 7. Goals / Non-goals

**Goals**
- G1. Full Drive Disc inventory → `ZodExport.discs`, Adepti-faithful, end-to-end.
- G2. Full W-Engine inventory → `ZodExport.weapons`.
- G3. Agent roster → `ZodExport.characters` incl. level, promotion, mindscape, and **talent levels**
  (schema extension), with equipped gear reconstructed from `location`.
- G4. Output is byte-compatible with the existing ZOD/GOOD optimizer import.
- G5. External-only operation (S-OCR-1) verified; clean by construction.
- G6. Deterministic replay from a saved frame archive (test + debug).

**Non-goals**
- N-OCR-1. No reading game memory / process / files / traffic (S-OCR-1).
- N-OCR-2. No modifying account state — navigation + screenshots only (S-OCR-4).
- N-OCR-3. Not preserving the Youkai Rust app, packet capture, or decryption code (full scrap).
- N-OCR-4. No multi-language client support in v1 (English only; architecture leaves room).
- N-OCR-5. No mobile/console capture in v1 (PC windowed only).

## 8. Approach — phased (build order within the single v1 milestone)

Even though v1 ships the full spec, tasks are ordered so the pipeline is testable incrementally and a
killed session resumes from disk. Disc scanning (the proven Adepti path) is built first as the
recognition spine; agent scanning (the novel, undocumented-in-Adepti part) is built on top of it.

```
Phase A  Foundations    co-op nav-map + reference capture (A0.5), schema+ZOD emitter, hand name lists, calibration, preflight
Phase B  Recognition    field-crop config, OCR wrappers, template library, fuzzy-normalizer+validation
Phase C  Discs          grid traversal + disc assembler  → first real ZodExport.discs   ◄ proves the spine
Phase D  Engines        W-Engine traversal + assembler   → ZodExport.weapons
Phase E  Agents         agent navigation + talents/mindscape/promotion + reconstruct equip → characters
Phase F  QA + ship      ground-truth accuracy gate, review report, replay archive, runbook
```

Each phase ends with a concrete, testable artifact. See `TASKS_ocr.md`.

## 9. Fallbacks
- **Color/calibration too fragile on a user's setup** → fall back to passive live-capture mode (§5):
  user navigates, tool only grabs frames on a hotkey and OCRs them. Same recognition stack, zero
  synthetic input. Slower, maximally safe.
- **Canonical ZZZ data unavailable for current version** → ship with the last-known name lists; new
  agents/engines/sets fuzzy-miss and land in the review report for manual keying (graceful, not fatal).
- **Tesseract too weak on ZZZ's stylized font** → swap the text engine to PaddleOCR behind the same
  recognize-layer interface (D17 keeps the engine pluggable).

## 10. Testing strategy
- **Unit**: ZOD emitter round-trips against the Rust schema; `to_zod_key` parity with `zod.rs`;
  fuzzy-normalizer maps known noisy strings to correct keys; range validators reject out-of-range.
- **Golden replay**: a committed archive of raw field crops (a labeled ground-truth set — e.g. 30
  discs, 8 engines, 8 agents) drives the recognize→assemble layers with **no game running**. CI-able.
- **Accuracy gate** (ship criterion): on the ground-truth set, ≥99% on names (post-fuzzy), ≥98% on
  numerics; every miss must appear in the review report (no silent wrong values).
- **Negative controls**: a Night-Light-tinted frame and a wrong-resolution frame must be *detected and
  refused*, not silently mis-scanned.
- **Safety audit**: static check that the codebase contains no process-attach / memory-read / file- or
  packet-touching calls against the game (enforces S-OCR-1).

## 11. Open questions
- **OQ-ocr-1** *(reframed, D19)*: Hand-author the name lists (agents/engines/disc-sets/stats) and keep
  them patch-updatable. No external dump. → Phase A (A2).
- **OQ-ocr-2**: `ZodDisc.rarity` / engine rarity encoding — what ints does the target optimizer expect
  for S/A/B? Confirm against an existing optimizer import sample. → Phase A.
- **OQ-ocr-3**: Core Skill encoding in `talent.core` — numeric level vs letter rank (A–F). What does
  the optimizer's schema want? → Phase A / confirm with a real optimizer.
- **OQ-ocr-4** *(resolved-path)*: Panel geometry / anchor elements + reference screenshots at 1920×1080
  and 1600×900 — produced in the **co-op navigation+capture session (A0.5)**, user-supplied. → A0.5.
- **OQ-ocr-5**: End-of-inventory + dedupe strategy for the disc grid (scrollbar position vs sort-order
  fixing vs last-page detection) — mirror whatever AdeptiScanner-ZZZ does. → Phase C.
- **OQ-ocr-6**: Does the target optimizer want agent→gear as explicit lists, or is `location` on each
  disc/engine sufficient (as today)? → confirm before Phase E assembler.
- **OQ-ocr-7**: Does a disc's equipped-agent indicator show the agent **name as text** (OCR it, no
  templates) or **portrait only** (needs a portrait-template library, A3)? → resolved in A0.5 from a
  real disc screenshot.
```
