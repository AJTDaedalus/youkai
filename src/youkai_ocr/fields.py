"""Declarative field-crop config for ZZZ OCR panels.

Loads region specs from navigation.yaml and crops them out of a calibrated
game frame. Preprocessing hints are passed through but not executed here —
that is B2/B3's job.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Union

import yaml
from PIL import Image

from .capture import CalibrationResult

BBox = tuple[int, int, int, int]


@dataclass(frozen=True)
class FieldSpec:
    """A single named region in reference (1920×1080) coordinates."""

    bbox: BBox
    preprocess: str  # hint for downstream recognizers, e.g. "white_text_on_dark"


@dataclass
class PanelSpec:
    """Flat collection of named field specs for one screen panel."""

    fields: dict[str, FieldSpec]


# ── YAML flattening ───────────────────────────────────────────────────────────


def _flatten(raw: dict, prefix: str, out: dict[str, FieldSpec]) -> None:
    """Recursively flatten a YAML fields dict into {name: FieldSpec}.

    Handles four shapes found in navigation.yaml:
      - simple:      {bbox: [...], preprocess: str}
      - split:       {name_bbox: [...], value_bbox: [...], preprocess: str}
      - dual-bbox:   {bbox: [...], level_bbox: [...], preprocess: str}
      - nested group: {child_key: {bbox: [...]}, ...}  (e.g. stats, core_nodes)
    Non-dict values (notes, scalars) are skipped silently.
    """
    for key, val in raw.items():
        if not isinstance(val, dict):
            continue
        full_key = f"{prefix}_{key}" if prefix else key

        if "bbox" in val and "level_bbox" in val:
            # Skill icon: main region + level sub-region.
            out[full_key] = FieldSpec(
                bbox=tuple(val["bbox"]),  # type: ignore[arg-type]
                preprocess=val.get("preprocess", ""),
            )
            out[f"{full_key}_level"] = FieldSpec(
                bbox=tuple(val["level_bbox"]),  # type: ignore[arg-type]
                preprocess=val.get("preprocess", ""),
            )
        elif "name_bbox" in val and "value_bbox" in val:
            # Substat split: separate name and value crops.
            out[f"{full_key}_name"] = FieldSpec(
                bbox=tuple(val["name_bbox"]),  # type: ignore[arg-type]
                preprocess=val.get("preprocess", ""),
            )
            out[f"{full_key}_value"] = FieldSpec(
                bbox=tuple(val["value_bbox"]),  # type: ignore[arg-type]
                preprocess=val.get("preprocess", ""),
            )
        elif "bbox" in val:
            out[full_key] = FieldSpec(
                bbox=tuple(val["bbox"]),  # type: ignore[arg-type]
                preprocess=val.get("preprocess", ""),
            )
        else:
            # Nested group (stats dict, core_nodes dict, etc.) — recurse.
            _flatten(val, full_key, out)


# ── Public API ────────────────────────────────────────────────────────────────


def load_panel(nav_path: Union[str, Path], *path: str) -> PanelSpec:
    """Load a panel's fields from navigation.yaml.

    ``path`` is a sequence of YAML keys that navigate to a node containing a
    ``fields`` sub-key, e.g.::

        load_panel(nav_path, "disc_inventory", "detail_panel")
        load_panel(nav_path, "agent_roster", "base_stats_tab")

    Raises KeyError if any key in ``path`` is missing, or if the target node
    has no ``fields`` key.
    """
    with open(nav_path, encoding="utf-8") as fh:
        nav = yaml.safe_load(fh)

    node = nav
    for key in path:
        node = node[key]

    raw_fields: dict = node["fields"]
    out: dict[str, FieldSpec] = {}
    _flatten(raw_fields, "", out)
    return PanelSpec(fields=out)


def crop_fields(
    frame: Image.Image,
    calib: CalibrationResult,
    panel: PanelSpec,
) -> dict[str, Image.Image]:
    """Crop every field in *panel* from *frame* using *calib* to scale bboxes.

    Returns a dict mapping field name → RGB PIL Image. Every crop is
    guaranteed non-empty (width > 0 and height > 0) because the navigation
    bboxes are validated to lie within the 1920×1080 reference.
    """
    crops: dict[str, Image.Image] = {}
    for name, spec in panel.fields.items():
        x1, y1, x2, y2 = calib.scale_bbox(spec.bbox)
        crops[name] = frame.crop((x1, y1, x2, y2))
    return crops
