"""Offline re-triage of disc critical-failures from an archived live run.

Reproduces the live extraction decision (disc_scanner._extract_disc) for the
title field only, which is what gates a critical fail:
    slot      = parse_slot(read_text(title.png, "white_text_on_dark"))
    set_conf  = normalize_disc_set(same text)[1]
    fail iff  not slot  OR  set_conf < 30
Writes a JSON + a human summary so the failure set is durable on disk.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

from youkai_ocr.recognize import make_recognizer
from youkai_ocr.normalizer import parse_slot, normalize_disc_set

CRIT = 30.0


def main(archive: str, out: str) -> None:
    root = Path(archive)
    rec = make_recognizer("tesseract")
    disc_dirs = sorted(d for d in root.glob("disc_*") if d.is_dir())
    fails: list[dict] = []
    n = 0
    for dd in disc_dirs:
        title = dd / "title.png"
        if not title.exists():
            continue
        n += 1
        text = rec.read_text(Image.open(title), "white_text_on_dark").replace("\n", " ").strip()
        slot = parse_slot(text)
        set_key, set_conf = normalize_disc_set(text)
        if not slot or set_conf < CRIT:
            reason = "no_slot" if not slot else f"low_set_conf:{set_conf:.0f}"
            fails.append({
                "dir": dd.name,
                "reason": reason,
                "slot": slot,
                "set_key": set_key,
                "set_conf": round(set_conf, 1),
                "ocr": text,
            })
        if n % 100 == 0:
            print(f"  ...{n} discs, {len(fails)} fails so far", flush=True)
            Path(out).write_text(json.dumps({"scanned": n, "fails": fails}, indent=2))

    result = {"scanned": n, "fail_count": len(fails), "fails": fails}
    Path(out).write_text(json.dumps(result, indent=2))
    print(f"\nDONE: {n} discs scanned, {len(fails)} critical fails.")
    by_reason: dict[str, int] = {}
    for f in fails:
        key = f["reason"].split(":")[0]
        by_reason[key] = by_reason.get(key, 0) + 1
    print("By reason:", by_reason)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
