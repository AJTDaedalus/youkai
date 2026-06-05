"""B2: Text recognition wrapper — preprocessing + pluggable OCR backend.

Preprocessing profiles (driven by navigation.yaml ``preprocess`` hints):
  - ``white_text_on_dark``  — most ZZZ UI text; scale 2×, grayscale, invert, Otsu threshold
  - ``brightness_threshold`` — mindscape cinema cells; scale 2×, grayscale, Otsu (no invert)

Non-text profiles (``portrait_circle``, ``color_sample``, ``template_match``,
``star_count``) are returned unchanged — those are B3's domain.

The ``TextRecognizer`` Protocol lets callers stay engine-agnostic; swap
``TesseractRecognizer`` for a PaddleOCR backend without touching call sites.
"""
from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

import cv2
import numpy as np
from PIL import Image

# Profiles that B2 actively preprocesses for OCR.
TEXT_PROFILES: frozenset[str] = frozenset({"white_text_on_dark", "brightness_threshold"})

# Profiles owned by B3 (template/color matching) — passed through unchanged.
_B3_PROFILES: frozenset[str] = frozenset(
    {"portrait_circle", "color_sample", "template_match", "star_count"}
)

_SCALE = 2  # upscale factor applied before thresholding


# ── Preprocessing ─────────────────────────────────────────────────────────────


def preprocess(img: Image.Image, profile: str) -> Image.Image:
    """Apply profile-specific preprocessing and return a PIL Image ready for OCR.

    For B3 / unknown profiles the image is returned as-is (RGB).
    """
    if profile == "white_text_on_dark":
        return _white_text_on_dark(img)
    if profile == "brightness_threshold":
        return _brightness_threshold(img)
    # B3 profiles and any unknowns — pass through without modification.
    return img.convert("RGB")


def _white_text_on_dark(img: Image.Image) -> Image.Image:
    """Scale 2×, grayscale, invert, Otsu threshold → black text on white."""
    arr = _upscale(np.array(img.convert("RGB")))
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    inv = cv2.bitwise_not(gray)
    _, thresh = cv2.threshold(inv, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return Image.fromarray(thresh, "L")


def _brightness_threshold(img: Image.Image) -> Image.Image:
    """Scale 2×, grayscale, Otsu threshold (no invert — cells are bright on dark)."""
    arr = _upscale(np.array(img.convert("RGB")))
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return Image.fromarray(thresh, "L")


def _upscale(arr: np.ndarray) -> np.ndarray:
    h, w = arr.shape[:2]
    return cv2.resize(arr, (w * _SCALE, h * _SCALE), interpolation=cv2.INTER_CUBIC)


# ── Interface ─────────────────────────────────────────────────────────────────


@runtime_checkable
class TextRecognizer(Protocol):
    """Engine-agnostic text recognition interface."""

    def read_text(self, img: Image.Image, profile: str) -> str:
        """Return raw recognized text from *img* after preprocessing *profile*."""
        ...

    def read_digits(self, img: Image.Image, profile: str) -> str:
        """Digit-optimized pass; returns only ``[0-9.%+]`` characters."""
        ...


# ── Tesseract backend ─────────────────────────────────────────────────────────

_GENERAL_CONFIG = "--oem 1 --psm 6"
_DIGIT_CONFIG = "--oem 1 --psm 7 -c tessedit_char_whitelist=0123456789.%+"
_DIGIT_STRIP = re.compile(r"[^\d.%+]")


class TesseractRecognizer:
    """Tesseract-backed ``TextRecognizer``.

    Import is deferred so the module loads cleanly without Tesseract in PATH.
    Construction raises ``RuntimeError`` if the binary is absent.
    """

    def __init__(self, lang: str = "eng") -> None:
        import pytesseract  # noqa: PLC0415 — intentional deferred import

        try:
            pytesseract.get_tesseract_version()
        except Exception as exc:
            raise RuntimeError(
                "Tesseract is not installed or not in PATH. "
                "Install it (e.g. `apt install tesseract-ocr` or the Windows installer) "
                "and ensure the binary is on PATH."
            ) from exc

        self._tess = pytesseract
        self._lang = lang

    def read_text(self, img: Image.Image, profile: str) -> str:
        processed = preprocess(img, profile)
        return self._tess.image_to_string(
            processed, lang=self._lang, config=_GENERAL_CONFIG
        ).strip()

    def read_digits(self, img: Image.Image, profile: str) -> str:
        processed = preprocess(img, profile)
        raw = self._tess.image_to_string(
            processed, lang=self._lang, config=_DIGIT_CONFIG
        ).strip()
        return _DIGIT_STRIP.sub("", raw)


# ── Factory ───────────────────────────────────────────────────────────────────


def make_recognizer(engine: str = "tesseract", **kwargs: object) -> TextRecognizer:
    """Return a ``TextRecognizer`` for the given engine name.

    Supported engines: ``"tesseract"`` (default).
    """
    if engine == "tesseract":
        return TesseractRecognizer(**kwargs)  # type: ignore[arg-type]
    raise ValueError(f"Unknown OCR engine: {engine!r}. Supported: 'tesseract'")
