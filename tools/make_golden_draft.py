"""F2: generate draft ground-truth labels for the golden replay set.

Replays archived crops through the real extractors (no game) and writes a
draft labels JSON for human verification. Run from the repo root:

    python tools/make_golden_draft.py

Sources:
  - discs:   archive/live_20260605/disc_NNNN/panel.png   (2026-06-05 full scan)
  - engines: archive/live_20260609/live_20260610_065548/engine_NNNN/panel.png
  - agents:  archive/live_20260609/live_20260610_065548/agent_NNN/{base_stats,skills}.png

The draft labels are the *scanner's* current output — they become ground truth
only after a human verifies them against the images (see labels.json
"verified" flags).
"""
import json
import sys
from dataclasses import asdict
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from youkai_ocr.capture import CalibrationResult
from youkai_ocr.disc_scanner import _extract_disc, _PANEL_BBOX
from youkai_ocr.wengine_scanner import _extract_engine
from youkai_ocr.agent_scanner import scan_single_frame_agent
from youkai_ocr.recognize import make_recognizer

ROOT = Path(__file__).parent.parent
DISC_RUN = ROOT / "archive/live_20260605"
MAIN_RUN = ROOT / "archive/live_20260609/live_20260610_065548"

CALIB = CalibrationResult(scale_x=1.0, scale_y=1.0, frame_width=1920, frame_height=1080)
# Lock strip reads outside the panel → black canvas → lock excluded from golden set.
DUMMY_CELL = (300, 300)

DISC_INDICES = [0, 74, 148, 222, 296, 370, 444, 518, 592, 666,
                740, 814, 888, 962, 1036, 1110, 1184, 1258, 1332, 1406,
                1480, 1554, 1628, 1702, 1776, 1850, 1924, 1998, 2072, 2146]
ENGINE_INDICES = [0, 30, 60, 90, 120, 150, 180, 210]


def panel_to_frame(panel_path: Path) -> Image.Image:
    """Reconstruct a synthetic 1920x1080 frame with the panel at its reference origin."""
    frame = Image.new("RGB", (1920, 1080), (10, 10, 10))
    panel = Image.open(panel_path).convert("RGB")
    frame.paste(panel, (_PANEL_BBOX[0], _PANEL_BBOX[1]))
    return frame


def main() -> None:
    recognizer = make_recognizer("tesseract")
    out: dict = {"discs": [], "engines": [], "agents": []}

    for idx in DISC_INDICES:
        p = DISC_RUN / f"disc_{idx:04d}/panel.png"
        if not p.exists():
            print(f"disc_{idx:04d}: MISSING")
            continue
        disc, conf = _extract_disc(panel_to_frame(p), CALIB, *DUMMY_CELL, recognizer, None, idx)
        rec = {"src": f"disc_{idx:04d}", "ok": disc is not None,
               "conf": {k: round(v, 1) for k, v in conf.items() if not k.startswith("_")},
               "fail": conf.get("_fail_reason", "")}
        if disc is not None:
            rec["disc"] = asdict(disc)
        out["discs"].append(rec)
        print(f"disc_{idx:04d}: {'OK ' + disc.set_key if disc else 'FAIL ' + str(conf.get('_fail_reason'))}")

    for idx in ENGINE_INDICES:
        p = MAIN_RUN / f"engine_{idx:04d}/panel.png"
        if not p.exists():
            print(f"engine_{idx:04d}: MISSING")
            continue
        eng, conf = _extract_engine(panel_to_frame(p), CALIB, *DUMMY_CELL, recognizer, None, idx)
        rec = {"src": f"engine_{idx:04d}", "ok": eng is not None,
               "conf": {k: round(v, 1) for k, v in conf.items()}}
        if eng is not None:
            rec["engine"] = asdict(eng)
        out["engines"].append(rec)
        print(f"engine_{idx:04d}: {'OK ' + eng.key if eng else 'FAIL'}")

    for d in sorted(MAIN_RUN.glob("agent_*")):
        base, skills = d / "base_stats.png", d / "skills.png"
        if not (base.exists() and skills.exists()):
            continue
        agent, conf = scan_single_frame_agent(
            Image.open(base).convert("RGB"), Image.open(skills).convert("RGB"), CALIB)
        rec = {"src": d.name, "ok": agent is not None,
               "conf": {k: round(v, 1) for k, v in conf.items()}}
        if agent is not None:
            rec["agent"] = asdict(agent)
        out["agents"].append(rec)
        print(f"{d.name}: {'OK ' + agent.key if agent else 'FAIL'}")

    out_path = ROOT / "tools/golden_draft.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
