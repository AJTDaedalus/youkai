"""Window-selection heuristic (fixes the live ZeroDivisionError / wrong-window grab).

`list_game_windows` already filters out invisible / minimized / 0×0 windows on
Windows; these tests cover the pure picking step that runs on the survivors.
"""

from youkai_ocr.capture import pick_best_window


def _w(hwnd, width, height, **kw):
    aspect = width / height
    d = {
        "hwnd": hwnd,
        "title": "ZenlessZoneZero",
        "left": 0,
        "top": 0,
        "right": width,
        "bottom": height,
        "w": width,
        "h": height,
        "aspect": aspect,
        "is_16_9": abs(aspect - 16 / 9) <= 0.01,
    }
    d.update(kw)
    return d


def test_none_when_empty():
    assert pick_best_window([]) is None


def test_prefers_16_9_over_larger_non_16_9():
    # The launcher can be physically larger but is not 16:9 — must not win.
    launcher = _w(1, 2000, 1400)  # 1.43 aspect, big
    game = _w(2, 1920, 1080)  # 16:9
    assert pick_best_window([launcher, game])["hwnd"] == 2


def test_prefers_largest_among_16_9():
    small = _w(1, 1280, 720)
    big = _w(2, 1920, 1080)
    assert pick_best_window([big, small])["hwnd"] == 2
    assert pick_best_window([small, big])["hwnd"] == 2


def test_falls_back_to_largest_when_none_16_9():
    # No 16:9 candidate → pick the largest so _require_window can report the size.
    a = _w(1, 1000, 800)
    b = _w(2, 1600, 1000)
    assert pick_best_window([a, b])["hwnd"] == 2
