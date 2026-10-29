"""Bounded PDF visual metrics. These do not establish scientific correctness."""

from __future__ import annotations

import ctypes
import math
from contextlib import closing

from .diagnostics import explain

MAX_CHARACTERS = 50000
MAX_OBJECTS = 5000
MAX_DEPTH = 15


def _finding(code, message):
    return explain({"severity": "warning", "code": code, "message": message})


def _projection(page, size, raw):
    """Recover continuous page→bitmap coordinates from PDFium's viewport edges."""
    left, bottom, right, top = page.get_bbox()
    if (
        not all(math.isfinite(v) for v in (left, bottom, right, top))
        or not right > left
        or not top > bottom
    ):
        raise ValueError("PDF page bounds have no positive area")

    def device(x, y):
        dx, dy = ctypes.c_int(), ctypes.c_int()
        if not raw.FPDF_PageToDevice(page, 0, 0, *size, 0, x, y, dx, dy):
            raise ValueError("PDF page coordinates could not be projected")
        return dx.value, dy.value

    origin, horizontal, vertical = device(left, bottom), device(right, bottom), device(left, top)

    def project(x, y):
        u, v = (x - left) / (right - left), (y - bottom) / (top - bottom)
        return tuple(
            origin[j] + u * (horizontal[j] - origin[j]) + v * (vertical[j] - origin[j])
            for j in range(2)
        )

    return project


def _bounds(points):
    return [
        min(p[0] for p in points),
        min(p[1] for p in points),
        max(p[0] for p in points),
        max(p[1] for p in points),
    ]


def _intersects(a, b):
    return max(a[0], b[0]) < min(a[2], b[2]) and max(a[1], b[1]) < min(a[3], b[3])


def _polygon_intersects(points, box):
    """Clip a placement quadrilateral so rotated bounding-box corners do not count."""
    for axis, boundary, sign in [(0, box[0], 1), (0, box[2], -1), (1, box[1], 1), (1, box[3], -1)]:
        clipped = []
        if not points:
            return False
        previous = points[-1]
        for current in points:
            inside, was_inside = (
                sign * (current[axis] - boundary) >= 0,
                sign * (previous[axis] - boundary) >= 0,
            )
            if inside != was_inside:
                fraction = (boundary - previous[axis]) / (current[axis] - previous[axis])
                clipped.append(
                    tuple(previous[j] + fraction * (current[j] - previous[j]) for j in range(2))
                )
            if inside:
                clipped.append(current)
            previous = current
        points = clipped
    area = (
        abs(
            sum(
                a[0] * b[1] - b[0] * a[1]
                for a, b in zip(points, points[1:] + points[:1], strict=True)
            )
        )
        / 2
    )
    return area > 1e-7


def _compose(outer, inner):
    a, b, c, d, e, f = outer
    g, h, i, j, k, l = inner
    return (
        a * g + c * h,
        b * g + d * h,
        a * i + c * j,
        b * i + d * j,
        a * k + c * l + e,
        b * k + d * l + f,
    )


def _image_matrix(obj):
    matrix = obj.get_matrix()
    result = (matrix.a, matrix.b, matrix.c, matrix.d, matrix.e, matrix.f)
    parent = obj.container
    depth = 0
    while parent is not None:
        m = parent.get_matrix()
        result = _compose((m.a, m.b, m.c, m.d, m.e, m.f), result)
        parent = parent.container
        depth += 1
        if depth >= MAX_DEPTH:
            raise ValueError("image form transform depth exceeded")
    return result


def scan_page(page, *, unit, size):
    """Cache page evidence once; region inspection never rescans the PDF objects."""
    import pypdfium2 as pdfium

    raw = pdfium.raw
    model = {
        "glyphs": [],
        "images": [],
        "text_reasons": [],
        "image_reasons": [],
        "characters_total": None,
        "characters_examined": 0,
        "objects_examined": 0,
    }
    try:
        project = _projection(page, size, raw)
    except (AttributeError, ValueError, pdfium.PdfiumError) as problem:
        model["text_reasons"].append(str(problem))
        model["image_reasons"].append(str(problem))
        return model
    try:
        with closing(page.get_textpage()) as text:
            total = text.count_chars()
            model["characters_total"] = total
            if total > MAX_CHARACTERS:
                model["text_reasons"].append(
                    f"Only the first {MAX_CHARACTERS} of {total} PDF characters were examined"
                )
            unresolved = 0
            for index in range(min(total, MAX_CHARACTERS)):
                model["characters_examined"] += 1
                value = raw.FPDFText_GetUnicode(text, index)
                if not 0 < value <= 0x10FFFF:
                    unresolved += 1
                    continue
                character = chr(value)
                if not character.strip():
                    continue
                obj = raw.FPDFText_GetTextObject(text, index)
                mode = raw.FPDFTextObj_GetTextRenderMode(obj) if obj else -1
                if mode in {3, 7}:  # invisible or clip-only text, not drawn text
                    continue
                if mode not in {0, 1, 2, 4, 5, 6}:
                    unresolved += 1
                    continue
                colors = []
                for getter in (
                    [raw.FPDFText_GetFillColor]
                    if mode in {0, 4}
                    else [raw.FPDFText_GetStrokeColor]
                    if mode in {1, 5}
                    else [raw.FPDFText_GetFillColor, raw.FPDFText_GetStrokeColor]
                ):
                    rgba = [ctypes.c_uint() for _ in range(4)]
                    if getter(text, index, *rgba):
                        colors.append(rgba[3].value)
                if not colors:
                    unresolved += 1
                    continue
                if not any(colors):
                    continue
                m = raw.FS_MATRIX()
                nominal = raw.FPDFText_GetFontSize(text, index)
                if not raw.FPDFText_GetMatrix(text, index, m):
                    unresolved += 1
                    continue
                physical = abs(nominal) * math.hypot(m.c, m.d) * unit
                box = text.get_charbox(index)
                if not all(math.isfinite(v) for v in (*box, physical)) or physical <= 0:
                    unresolved += 1
                    continue
                left, bottom, right, top = box
                if right <= left or top <= bottom:
                    continue
                bounds = _bounds(
                    [
                        project(x, y)
                        for x, y in [(left, bottom), (left, top), (right, bottom), (right, top)]
                    ]
                )
                model["glyphs"].append(
                    {
                        "index": index,
                        "character": character,
                        "points": physical,
                        "pixel_box": bounds,
                    }
                )
            if unresolved:
                model["text_reasons"].append(
                    f"{unresolved} characters had unresolved Unicode, rendering mode or size/transform metrics"
                )
    except (AttributeError, ValueError, pdfium.PdfiumError) as problem:
        model["text_reasons"].append(f"Text metrics unavailable or partial: {problem}")
    try:
        for obj in page.get_objects(max_depth=MAX_DEPTH):
            if model["objects_examined"] >= MAX_OBJECTS:
                model["image_reasons"].append(f"Object scan capped at {MAX_OBJECTS} objects")
                break
            model["objects_examined"] += 1
            if obj.type == raw.FPDF_PAGEOBJ_FORM and obj.level >= MAX_DEPTH - 1:
                model["image_reasons"].append("Nested form scan reached its depth limit")
            if obj.type != raw.FPDF_PAGEOBJ_IMAGE:
                continue
            try:
                a, b, c, d, e, f = _image_matrix(obj)
                width, height = obj.get_px_size()
                xspan, yspan = math.hypot(a, b) * unit, math.hypot(c, d) * unit
                if (
                    not all(math.isfinite(v) for v in (a, b, c, d, e, f, xspan, yspan))
                    or min(width, height, xspan, yspan) <= 0
                ):
                    raise ValueError("degenerate/nonfinite image placement")
                dpi = [width * 72 / xspan, height * 72 / yspan]
                if not all(math.isfinite(v) and v > 0 for v in dpi):
                    raise ValueError("nonfinite image resolution")
                points = [
                    project(a * x + c * y + e, b * x + d * y + f)
                    for x, y in [(0, 0), (1, 0), (1, 1), (0, 1)]
                ]
                model["images"].append(
                    {
                        "pixels": [width, height],
                        "dpi": dpi,
                        "polygon": points,
                        "pixel_box": _bounds(points),
                    }
                )
            except (AttributeError, ValueError, pdfium.PdfiumError) as problem:
                model["image_reasons"].append(f"Image metrics unavailable: {problem}")
    except (AttributeError, ValueError, pdfium.PdfiumError) as problem:
        model["image_reasons"].append(f"Image scan unavailable or partial: {problem}")
    return model


def inspect_region(model, box, *, min_text_pt=6.0, min_image_dpi=150.0):
    """Report measurable attributes of selected content, never a scientific pass."""
    glyphs = [g for g in model["glyphs"] if _intersects(g["pixel_box"], box)]
    images = [
        i
        for i in model["images"]
        if _intersects(i["pixel_box"], box) and _polygon_intersects(i["polygon"], box)
    ]
    small = [g for g in glyphs if g["points"] < min_text_pt - 1e-5]
    groups = []
    for glyph in small:
        if groups and groups[-1][-1]["index"] + 1 == glyph["index"]:
            groups[-1].append(glyph)
        else:
            groups.append([glyph])
    low = [i for i in images if min(i["dpi"]) < min_image_dpi - 1e-5]
    low_ids = {id(i) for i in low}
    samples = low + [i for i in images if id(i) not in low_ids]
    text_reasons = list(dict.fromkeys(model["text_reasons"]))
    image_reasons = list(dict.fromkeys(model["image_reasons"]))
    checks = [
        {
            "name": "text_size",
            "basis": "Extractable non-invisible PDF text metrics; raster-only text is not measured",
            "status": "partial" if text_reasons else "checked" if glyphs else "untested",
            "threshold_pt": min_text_pt,
            "characters_measured": len(glyphs),
            "characters_below_threshold": len(small),
            "minimum_pt": min((g["points"] for g in glyphs), default=None),
            "reasons": text_reasons
            or (
                []
                if glyphs
                else [
                    "No measurable extractable text intersects this selection; raster text is not OCR-inspected"
                ]
            ),
        },
        {
            "name": "raster_resolution",
            "basis": "Embedded page-content image placements; annotation appearances and complex clipping are not certified",
            "status": "partial" if image_reasons else "checked" if images else "not_applicable",
            "threshold_dpi": min_image_dpi,
            "placements_measured": len(images),
            "placements_below_threshold": len(low),
            "minimum_dpi": min((min(i["dpi"]) for i in images), default=None),
            "reasons": image_reasons,
        },
    ]
    findings = []
    if small:
        findings.append(
            _finding(
                "pdf_small_text",
                f"{len(small)} extractable text characters in this selection have a transformed size below {min_text_pt:g}pt (minimum {min(g['points'] for g in small):.3g}pt). Review text at the PDF's declared physical size.",
            )
        )
    if low:
        findings.append(
            _finding(
                "pdf_low_raster_resolution",
                f"{len(low)} embedded image placements in this selection have resolution below {min_image_dpi:g}dpi on at least one axis (minimum {min(min(i['dpi']) for i in low):.4g}dpi). This is source pixel density, not preview-render DPI.",
            )
        )
    if text_reasons or image_reasons:
        findings.append(
            _finding("pdf_visual_checks_partial", "; ".join(text_reasons + image_reasons))
        )
    return {
        "checks": checks,
        "findings": findings,
        "selection_pixel_box": box,
        "text_samples": [
            {
                "text": "".join(g["character"] for g in group[:120]),
                "minimum_pt": min(g["points"] for g in group),
                "pixel_box": _bounds(
                    [(g["pixel_box"][0], g["pixel_box"][1]) for g in group]
                    + [(g["pixel_box"][2], g["pixel_box"][3]) for g in group]
                ),
            }
            for group in groups[:20]
        ],
        "text_samples_truncated": len(groups) > 20 or any(len(g) > 120 for g in groups),
        "image_samples": [
            {"pixels": i["pixels"], "dpi": i["dpi"], "pixel_box": i["pixel_box"]}
            for i in samples[:20]
        ],
        "image_samples_truncated": len(images) > 20,
        "coverage": {
            "page_characters": model["characters_total"],
            "page_characters_examined": model["characters_examined"],
            "page_objects_examined": model["objects_examined"],
        },
        "limits": [
            "Metrics describe extracted PDF content and placement bounds; complex clipping, optional-content visibility and readability are not certified.",
            "Raster-only labels, missing labels, numerical values, source data and scientific/causal claims are not established.",
        ],
    }
