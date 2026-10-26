"""Physical widths of the static files emitted by Matplotlib, in inches."""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image
from pypdf import PdfReader


def export_width_in(path: str | Path) -> float:
    """Read physical dimensions; never infer missing DPI or relative units."""
    path = Path(path)
    if path.suffix.lower() == ".png":
        with Image.open(path) as bitmap:
            if bitmap.format != "PNG":
                raise ValueError("A PNG export must contain PNG image data")
            dpi = bitmap.info.get("dpi")
            if dpi is None or len(dpi) != 2 or not math.isfinite(dpi[0]) or dpi[0] <= 0:
                raise ValueError("PNG has no usable physical horizontal DPI")
            width = bitmap.width / dpi[0]
    elif path.suffix.lower() == ".pdf":
        reader = PdfReader(path)
        if len(reader.pages) != 1:
            raise ValueError("A figure PDF must have one page")
        width = float(reader.pages[0].mediabox.width) / 72
    elif path.suffix.lower() == ".svg":
        root = ET.parse(path).getroot()
        if root.tag not in {"svg", "{http://www.w3.org/2000/svg}svg"}:
            raise ValueError("An SVG export needs an SVG root element")
        value = root.get("width", "")
        match = re.fullmatch(
            r"\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(pt|in|cm|mm)\s*", value
        )
        if match is None:
            raise ValueError("SVG needs an absolute width in pt, in, cm or mm")
        width = float(match[1]) * {"pt": 1 / 72, "in": 1, "cm": 1 / 2.54, "mm": 1 / 25.4}[match[2]]
    else:
        raise ValueError("Physical figure dimensions support PNG, SVG and PDF")
    if not math.isfinite(width) or width <= 0:
        raise ValueError("Export width must be finite and positive")
    return float(width)
