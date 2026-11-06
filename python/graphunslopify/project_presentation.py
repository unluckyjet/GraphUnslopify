"""Place verified saved figure exports on manuscript pages or a slide."""

from __future__ import annotations

import base64
import tempfile
from contextlib import suppress
from pathlib import Path
from xml.etree.ElementTree import ParseError

from pypdf.errors import PdfReadError

from .comparison import _preview, _verified_bytes
from .journal import _measure, _pdf_text
from .project import ProjectError, _inside

# Local preview layouts, independent of journal compliance profiles.
# Values are page width/height, slot left/top and slot width/height in mm.
_LAYOUTS = {
    "single_column": ("Single column", (210, 297), (16, 66, 85, 215)),
    "double_column": ("Double column", (210, 297), (16, 66, 178, 215)),
    "slide": ("Widescreen slide", (338.6667, 190.5), (20, 48, 298.6667, 121)),
}


def _layout(page, slot, ratio, measurement, text, pixels):
    left, top, width, height = slot
    fitted_width = min(width, height * ratio)
    fitted_height = fitted_width / ratio
    scale = fitted_width / (measurement["width_in"] * 25.4) if measurement else None
    minimum = text["minimum_pt"] if text else None
    return {
        "page_mm": list(page),
        "slot_mm": list(slot),
        "placed_mm": [left + (width - fitted_width) / 2, top, fitted_width, fitted_height],
        "height_limited": fitted_width < width,
        "scale": scale,
        "minimum_text_pt": minimum * scale if minimum is not None and scale is not None else None,
        "raster_dpi": [pixels[0] * 25.4 / fitted_width, pixels[1] * 25.4 / fitted_height]
        if pixels
        else None,
    }


def presentation_preview(state, event_id, figure_id):
    event = state.event(event_id)
    figure = state.audited(event, figure_id)
    root = state.audit_root(event)
    reasons = []
    with tempfile.TemporaryDirectory(prefix="gu-presentation-preview-") as directory:
        temporary = Path(directory)
        for format_ in ("pdf", "png", "svg"):
            item = next((value for value in figure["outputs"] if value["format"] == format_), None)
            if item is None:
                continue
            _inside(root, item["path"])
            side, _ = _preview(item, [root], temporary, "presentation")
            if "preview" not in side:
                reasons.append(side["reason"])
                continue
            raw = _verified_bytes(item, [root])
            try:
                measurement = _measure(raw, format_)
            except (ValueError, OSError, PdfReadError, ParseError) as problem:
                if not side["dimensions"]:
                    reasons.append(str(problem))
                    continue
                measurement = None
            if measurement is None:
                width, height = side["dimensions"]
            else:
                width, height = measurement["width_in"], measurement["height_in"]
            text = None
            if format_ == "pdf" and measurement is not None:
                with suppress(ValueError):
                    text = _pdf_text(raw, unit=measurement["pdf_user_unit"], minimum=1.0)
            preview = side["preview"]
            image = _verified_bytes(preview, [temporary])
            layouts = {
                key: {
                    "label": label,
                    **_layout(
                        page,
                        slot,
                        width / height,
                        measurement,
                        text,
                        side["dimensions"] if format_ == "png" else None,
                    ),
                }
                for key, (label, page, slot) in _LAYOUTS.items()
            }
            return {
                "event": event["id"],
                "figure": figure["id"],
                "exit_code": event["result"]["exit_code"],
                "export": {
                    "format": format_,
                    "sha256": item["sha256"],
                    "measurement": measurement,
                },
                "text": text,
                "image": f"data:{preview['mime']};base64,"
                + base64.b64encode(image).decode("ascii"),
                "layouts": layouts,
            }
    raise ProjectError(
        "No verified PNG, SVG or single-page PDF can be placed in a layout."
        + (" " + reasons[0] if reasons else "")
    )
