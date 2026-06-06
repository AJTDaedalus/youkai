"""Tests for B2: text recognition wrapper (preprocessing + interface)."""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from youkai_ocr.recognize import (
    TEXT_PROFILES,
    TextRecognizer,
    TesseractRecognizer,
    make_recognizer,
    preprocess,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _solid(color: tuple[int, int, int], w: int = 40, h: int = 20) -> Image.Image:
    """Return a solid-color RGB PIL Image."""
    arr = np.full((h, w, 3), color, dtype=np.uint8)
    return Image.fromarray(arr, "RGB")


def _mean_brightness(img: Image.Image) -> float:
    return float(np.array(img.convert("L")).mean())


# ── TEXT_PROFILES constant ────────────────────────────────────────────────────


def test_text_profiles_contains_expected():
    assert "white_text_on_dark" in TEXT_PROFILES
    assert "brightness_threshold" in TEXT_PROFILES


def test_text_profiles_excludes_b3():
    for p in ("portrait_circle", "color_sample", "template_match", "star_count"):
        assert p not in TEXT_PROFILES


# ── preprocess — output type and size ────────────────────────────────────────


@pytest.mark.parametrize("profile", ["white_text_on_dark", "brightness_threshold"])
def test_preprocess_returns_pil_image(profile):
    img = _solid((30, 30, 30))
    result = preprocess(img, profile)
    assert isinstance(result, Image.Image)


@pytest.mark.parametrize("profile", ["white_text_on_dark", "brightness_threshold"])
def test_preprocess_doubles_resolution(profile):
    img = _solid((30, 30, 30), w=40, h=20)
    result = preprocess(img, profile)
    assert result.size == (80, 40), f"{profile}: expected (80,40), got {result.size}"


@pytest.mark.parametrize("profile", ["white_text_on_dark", "brightness_threshold"])
def test_preprocess_output_is_grayscale(profile):
    img = _solid((50, 100, 150))
    result = preprocess(img, profile)
    assert result.mode == "L", f"{profile}: expected mode 'L', got {result.mode!r}"


# ── preprocess — white_text_on_dark inversion ────────────────────────────────


def _bimodal(text_color: int, bg_color: int, w: int = 60, h: int = 20) -> Image.Image:
    """Return a grayscale-like RGB image: left third = text_color, rest = bg_color.

    Otsu thresholding requires a bimodal histogram to behave deterministically;
    solid uniform images produce a degenerate single-class result.
    """
    arr = np.full((h, w, 3), bg_color, dtype=np.uint8)
    arr[:, : w // 3] = text_color  # left strip = "text" region
    return Image.fromarray(arr, "RGB")


def test_white_text_on_dark_inverts_bright_pixels():
    """White text region should become black after invert+threshold."""
    # Dark background with bright "text" strip — the text strip should become dark.
    img = _bimodal(text_color=230, bg_color=20)
    result = preprocess(img, "white_text_on_dark")
    arr = np.array(result)
    text_col = arr[:, : result.size[0] // 3]
    assert text_col.mean() < 50, "Bright text region should threshold to black after inversion"


def test_white_text_on_dark_dark_background_becomes_white():
    """Dark background should become white after invert+threshold."""
    img = _bimodal(text_color=230, bg_color=20)
    result = preprocess(img, "white_text_on_dark")
    arr = np.array(result)
    # Background is the right two-thirds
    bg_col = arr[:, result.size[0] // 3 :]
    assert bg_col.mean() > 200, "Dark background should threshold to white after inversion"


# ── preprocess — brightness_threshold no inversion ───────────────────────────


def test_brightness_threshold_bright_pixels_stay_white():
    """Bright text region should remain white (no invert)."""
    img = _bimodal(text_color=230, bg_color=20)
    result = preprocess(img, "brightness_threshold")
    arr = np.array(result)
    text_col = arr[:, : result.size[0] // 3]
    assert text_col.mean() > 200, "Bright text region should stay white without inversion"


def test_brightness_threshold_dark_pixels_become_black():
    """Dark background should threshold to black."""
    img = _bimodal(text_color=230, bg_color=20)
    result = preprocess(img, "brightness_threshold")
    arr = np.array(result)
    bg_col = arr[:, result.size[0] // 3 :]
    assert bg_col.mean() < 50, "Dark background should threshold to black"


def test_white_text_on_dark_and_brightness_threshold_differ():
    """The two profiles produce opposite output for the text region of a dark-bg image."""
    img = _bimodal(text_color=230, bg_color=20)
    wod = preprocess(img, "white_text_on_dark")
    bt = preprocess(img, "brightness_threshold")
    wod_arr = np.array(wod)
    bt_arr = np.array(bt)
    text_slice = slice(0, wod.size[0] // 3)
    # white_text_on_dark inverts → text region is dark; brightness_threshold keeps it bright
    assert wod_arr[:, text_slice].mean() < 50
    assert bt_arr[:, text_slice].mean() > 200


# ── preprocess — passthrough for non-text profiles ───────────────────────────


@pytest.mark.parametrize(
    "profile", ["portrait_circle", "color_sample", "template_match", "star_count", "TODO", ""]
)
def test_preprocess_passthrough_for_non_text_profiles(profile):
    """B3/unknown profiles must return RGB without resizing."""
    img = _solid((100, 150, 200), w=30, h=15)
    result = preprocess(img, profile)
    assert result.mode == "RGB"
    assert result.size == (30, 15), f"{profile}: size changed for passthrough profile"


def test_preprocess_passthrough_preserves_pixel_values():
    """Passthrough profiles must not alter pixel values."""
    # np.arange wraps naturally for uint8 (0..255 repeating)
    arr = np.arange(3 * 20 * 40, dtype=np.uint8).reshape(20, 40, 3)
    img = Image.fromarray(arr, "RGB")
    result = preprocess(img, "portrait_circle")
    assert np.array_equal(np.array(result), arr)


# ── TextRecognizer Protocol ───────────────────────────────────────────────────


class _StubRecognizer:
    """Minimal in-test stub that satisfies TextRecognizer."""

    def read_text(self, img: Image.Image, profile: str) -> str:
        return "stub_text"

    def read_line(self, img: Image.Image, profile: str) -> str:
        return "stub_line"

    def read_digits(self, img: Image.Image, profile: str) -> str:
        return "42"

    def read_slot(self, img: Image.Image, profile: str) -> str:
        return "[3]"


def test_stub_satisfies_protocol():
    assert isinstance(_StubRecognizer(), TextRecognizer)


def test_read_text_returns_str():
    rec = _StubRecognizer()
    assert isinstance(rec.read_text(_solid((0, 0, 0)), "white_text_on_dark"), str)


def test_read_digits_returns_str():
    rec = _StubRecognizer()
    result = rec.read_digits(_solid((0, 0, 0)), "white_text_on_dark")
    assert isinstance(result, str)
    assert result.isdigit() or result == ""


# ── TesseractRecognizer — graceful failure without binary ────────────────────


def test_tesseract_recognizer_raises_runtime_error_if_not_installed(monkeypatch):
    """Construction must raise RuntimeError (not an obscure import error) when
    the tesseract binary is absent."""
    import pytesseract

    def _mock_version():
        raise pytesseract.pytesseract.TesseractNotFoundError()

    monkeypatch.setattr(pytesseract, "get_tesseract_version", _mock_version)
    with pytest.raises(RuntimeError, match="Tesseract is not installed"):
        TesseractRecognizer()


# ── make_recognizer factory ───────────────────────────────────────────────────


def test_make_recognizer_unknown_engine_raises():
    with pytest.raises(ValueError, match="Unknown OCR engine"):
        make_recognizer("paddleocr")


def test_make_recognizer_tesseract_raises_runtime_when_missing(monkeypatch):
    """Factory must propagate the RuntimeError from TesseractRecognizer."""
    import pytesseract

    monkeypatch.setattr(
        pytesseract, "get_tesseract_version", lambda: (_ for _ in ()).throw(
            pytesseract.pytesseract.TesseractNotFoundError()
        )
    )
    with pytest.raises(RuntimeError):
        make_recognizer("tesseract")
