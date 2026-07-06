"""H12: debug-overlay smoke tests.

The overlays are pure visualization, so we only assert they run and return a
same-size RGB image for each screen type — guarding against import/constant drift
(e.g. a renamed coordinate constant in agent_scanner).
"""

from PIL import Image

from youkai_ocr import debug_overlay as dbg
from youkai_ocr.capture import CalibrationResult

_CALIB = CalibrationResult(scale_x=1.0, scale_y=1.0, frame_width=1920, frame_height=1080)


def _blank() -> Image.Image:
    return Image.new("RGB", (1920, 1080), (20, 20, 20))


def test_base_overlay_runs():
    out = dbg.draw_base_overlay(_blank(), _CALIB)
    assert out.size == (1920, 1080) and out.mode == "RGB"


def test_skills_overlay_runs():
    out = dbg.draw_skills_overlay(_blank(), _CALIB)
    assert out.size == (1920, 1080)


def test_equip_overlay_runs_with_active_slot():
    for active in (None, 0, 6):
        out = dbg.draw_equip_overlay(_blank(), _CALIB, active_slot=active)
        assert out.size == (1920, 1080)
