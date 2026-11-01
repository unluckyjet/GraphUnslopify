"""Common observational measurements of actual saves, not producer calculations."""

from __future__ import annotations

import hashlib
import io
import json
import runpy
import time
from pathlib import Path

from matplotlib.text import Text
from PIL import Image
from pypdf import PdfReader

REFERENCE_SOURCE = Path(__file__).with_name("reference.py")
if not REFERENCE_SOURCE.is_file():
    REFERENCE_SOURCE = Path(__file__).resolve().parents[1] / "papers/reference.py"
CERTIFIED_SOURCE = Path(__file__).with_name("certified_measurement.py")
if not CERTIFIED_SOURCE.is_file():
    CERTIFIED_SOURCE = Path(__file__).resolve().parents[1] / "certified/measurement.py"
REFERENCE = runpy.run_path(str(REFERENCE_SOURCE))
CERTIFIED = runpy.run_path(str(CERTIFIED_SOURCE))


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def graphic_identity(raw, fmt):
    """Exclude non-drawing metadata; preserve actual pixels or vector contents."""
    if fmt == "png":
        with Image.open(io.BytesIO(raw)) as image:
            rgba = image.convert("RGBA")
            return digest(str(rgba.size).encode() + rgba.tobytes())
    if fmt == "svg":
        return CERTIFIED["svg_graphic_digest"](raw)
    if fmt == "pdf":
        pages = []
        for page in PdfReader(io.BytesIO(raw)).pages:
            stream = page.get_contents()
            pages.append(
                [
                    list(map(float, page.mediabox)),
                    stream.get_data().hex() if stream else None,
                ]
            )
        return digest(json.dumps(pages, allow_nan=False).encode())
    raise ValueError("The frozen tasks require PNG/SVG/PDF only")


def saved_figure(figure, filename, kind, *, available_ns=None):
    """Read the very figure that just saved, without an extra draw or data reload."""
    available_ns = time.perf_counter_ns() if available_ns is None else available_ns
    path = Path(filename)
    if len(figure.axes) != 1 or kind not in {"bar", "scatter"}:
        raise ValueError("This observer is scoped to the four single-axis frozen tasks")
    axes = figure.axes[0]
    categories = (
        [text.get_text() for text in axes.get_xticklabels()] if kind == "bar" else []
    )
    artists = (
        REFERENCE["artists"](axes, categories)
        if kind == "bar"
        else REFERENCE["scatter_artists"](axes)
    )
    raw = path.read_bytes()
    visible = [
        float(text.get_fontsize())
        for text in figure.findobj(Text)
        if text.get_visible() and text.get_text().strip()
    ]
    return {
        "file": path.name,
        "available_monotonic_ns": available_ns,
        "format": path.suffix.removeprefix("."),
        "sha256": digest(raw),
        "graphic_identity": graphic_identity(raw, path.suffix.removeprefix(".")),
        "artists": artists,
        "labels": {
            "title": axes.get_title(),
            "x": axes.get_xlabel(),
            "y": axes.get_ylabel(),
        },
        "categories": categories,
        "series_order": axes.get_legend_handles_labels()[1],
        "minimum_visible_font_pt": min(visible) if visible else None,
        "nominal_figure_width_in": float(figure.get_size_inches()[0]),
        "measurement_source_sha256": digest(Path(__file__).read_bytes()),
    }
