"""Frozen external-reference measurements; no GraphUnslopify imports or answer computation."""

from __future__ import annotations

import hashlib
import json
import math
import re
import xml.etree.ElementTree as ET
from decimal import Decimal, localcontext
from pathlib import Path

from matplotlib.colors import to_rgba
from matplotlib.container import ErrorbarContainer
from matplotlib.text import Text
from PIL import Image
from pypdf import PdfReader
from pypdf.errors import PyPdfError


def svg_graphic_digest(body: bytes) -> str | None:
    """Identity for static native SVG, allowing only its accessibility/path-space edits."""
    namespace = "{http://www.w3.org/2000/svg}"
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return None
    if root.tag != namespace + "svg" or b"xml-stylesheet" in body:
        return None
    if any(
        e.tag in {namespace + "script", namespace + "foreignObject"}
        for e in root.iter()
    ):
        return None
    # Native Matplotlib's sole default rule has no structural/attribute selectors.
    # Arbitrary CSS could make accessibility additions affect rendering: abstain.
    for style in root.iter(namespace + "style"):
        if (
            re.sub(r"\s+", "", style.text or "")
            != "*{stroke-linejoin:round;stroke-linecap:butt}"
        ):
            return None
    titles = [e for e in root if e.tag == namespace + "title"]
    descriptions = [e for e in root if e.tag == namespace + "desc"]
    if len(titles) > 1 or len(descriptions) > 1:
        return None
    a11y = {
        key: root.attrib.get(key)
        for key in ("role", "aria-labelledby", "aria-describedby")
    }
    if any(v is not None for v in a11y.values()):
        if (
            not titles
            or not descriptions
            or a11y["role"] != "img"
            or a11y["aria-labelledby"] != titles[0].get("id")
            or a11y["aria-describedby"] != descriptions[0].get("id")
        ):
            return None
        for key in a11y:
            root.attrib.pop(key, None)
        titles[0].attrib.pop("id", None)
    for description in descriptions:
        root.remove(description)

    def canonical(element, preserve=False):
        preserve = preserve or element.tag in {
            namespace + "text",
            namespace + "tspan",
            namespace + "metadata",
        }
        attrs = dict(element.attrib)
        if element.tag == namespace + "path" and "d" in attrs:
            attrs["d"] = " ".join(attrs["d"].split())
        text, tail = element.text, element.tail
        if not preserve:
            text = text if text and text.strip() else None
            tail = tail if tail and tail.strip() else None
        return [
            element.tag,
            sorted(attrs.items()),
            text,
            tail,
            [canonical(child, preserve) for child in element],
        ]

    return hashlib.sha256(
        json.dumps(canonical(root), ensure_ascii=True).encode()
    ).hexdigest()


def read_protocol(root: Path) -> dict:
    """Refuse changed sources/evaluator code under an unchanged frozen protocol."""
    protocol = json.loads((root / "benchmarks/certified/protocol.json").read_text())
    source_path = root / "benchmarks/certified/sources.json"
    manifest = json.loads(source_path.read_text())
    if (
        hashlib.sha256(source_path.read_bytes()).hexdigest()
        != protocol["source_manifest_sha256"]
        or protocol["dataset_order"] != manifest["dataset_order"]
    ):
        raise ValueError("source selection differs from the frozen protocol")
    for name, expected in protocol["implementation_sha256"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise ValueError(
                "measurement implementation differs from the frozen protocol"
            )
    return protocol


def numeric_reference(source: dict, tokens: list[str]) -> dict:
    """Reference facts and predeclared float/printed-precision allowances, not fitted tolerances."""
    with localcontext() as ctx:
        ctx.prec = 80
        facts = source["certified"]
        mean = Decimal(facts["mean"]["value"])
        sd = Decimal(facts["sample_sd"]["value"])
        quantums = {
            key: Decimal(0)
            if facts[key]["exact"]
            else Decimal(1).scaleb(Decimal(facts[key]["value"]).as_tuple().exponent)
            for key in ("mean", "sample_sd")
        }
        if not tokens or not all(math.isfinite(float(t)) for t in tokens):
            raise ValueError(
                "reference observations must be nonempty and representable as finite floats"
            )
        input_error = max(
            abs(Decimal.from_float(float(t)) - Decimal(t)) for t in tokens
        )
        values = {"mean": mean, "low": mean - sd, "high": mean + sd, "half_span": sd}
        allowances = {}
        for key, value in values.items():
            ulp = Decimal.from_float(math.ulp(float(value)))
            if key == "mean":
                bound = quantums["mean"] + input_error + 8 * ulp
            elif key == "half_span":
                continue
            else:
                bound = (
                    quantums["mean"]
                    + quantums["sample_sd"]
                    + 3 * input_error
                    + 16 * ulp
                )
            allowances[key] = str(bound)
        allowances["half_span"] = str(
            (Decimal(allowances["low"]) + Decimal(allowances["high"])) / 2
        )
        return {
            "values": {k: str(v) for k, v in values.items()},
            "absolute_allowances": allowances,
            "max_input_float_error": str(input_error),
            "printed_quantums": {k: str(v) for k, v in quantums.items()},
        }


def compare_numeric(actual: dict, reference: dict) -> dict:
    """Missing/nonfinite quantities fail; large offsets never grant a relative-error shortcut."""
    records = {}
    with localcontext() as ctx:
        ctx.prec = 80
        for key, token in reference["values"].items():
            value = actual.get(key)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                records[key] = {
                    "passed": False,
                    "reason": "missing or nonfinite drawn quantity",
                }
                continue
            expected = Decimal(token)
            error = abs(Decimal.from_float(float(value)) - expected)
            allowance = Decimal(reference["absolute_allowances"][key])
            records[key] = {
                "passed": error <= allowance,
                "actual_hex": float(value).hex(),
                "absolute_error": str(error),
                "absolute_allowance": str(allowance),
                "error_over_allowance": str(error / allowance) if allowance else None,
                "relative_error": str(error / abs(expected)) if expected else None,
                "reference_float_ulp": str(
                    Decimal.from_float(math.ulp(float(expected)))
                ),
            }
    return {"passed": all(r["passed"] for r in records.values()), "quantities": records}


def _shown(artist):
    return artist.get_visible() and artist.get_alpha() != 0


def _marker_shown(line):
    face = to_rgba(line.get_markerfacecolor())[3]
    edge = (
        to_rgba(line.get_markeredgecolor())[3] if line.get_markeredgewidth() > 0 else 0
    )
    return (
        _shown(line)
        and line.get_marker() == "o"
        and line.get_markersize() > 0
        and max(face, edge) > 0
    )


def figure_measurements(figure) -> dict:
    """Inspect actual marker/errorbar artists at the export call, before their figure closes."""
    drawn_text = {}
    original_text_draw = Text.draw

    def text_draw(text, renderer):
        if _shown(text) and text.get_text().strip():
            drawn_text[id(text)] = (text, renderer)
        return original_text_draw(text, renderer)

    try:
        Text.draw = text_draw
        figure.canvas.draw()
    finally:
        Text.draw = original_text_draw
    points, intervals, point_visibility = [], [], []
    for axis in figure.axes:
        if not axis.get_visible():
            continue
        for line in axis.lines:
            if not _marker_shown(line):
                continue
            for x, y in zip(
                line.get_xdata(orig=False), line.get_ydata(orig=False), strict=True
            ):
                x, y = float(x), float(y)
                points.append(
                    {
                        "x": x if math.isfinite(x) else None,
                        "y": y if math.isfinite(y) else None,
                    }
                )
                if not all(math.isfinite(v) for v in (x, y)):
                    point_visibility.append(False)
                    continue
                px, py = axis.transData.transform((x, y))
                point_visibility.append(bool(axis.bbox.contains(px, py)))
        for container in axis.containers:
            if not isinstance(container, ErrorbarContainer) or not container.has_yerr:
                continue
            for collection in container.lines[2]:
                if (
                    not _shown(collection)
                    or not any(v > 0 for v in collection.get_linewidths())
                    or not any(c[3] > 0 for c in collection.get_colors())
                ):
                    continue
                for segment in collection.get_segments():
                    if len(segment) != 2 or not all(
                        math.isfinite(float(v)) for v in segment.flat
                    ):
                        continue
                    if not math.isclose(
                        float(segment[0, 0]),
                        float(segment[1, 0]),
                        rel_tol=0,
                        abs_tol=1e-12,
                    ):
                        continue
                    low, high = sorted(float(v) for v in segment[:, 1])
                    pixels = axis.transData.transform(segment)
                    intervals.append(
                        {
                            "x": float(segment[0, 0]),
                            "low": low,
                            "high": high,
                            "span_pixels": abs(float(pixels[1, 1] - pixels[0, 1])),
                            "within_axes": all(
                                bool(axis.bbox.contains(*p)) for p in pixels
                            ),
                        }
                    )
    actual = {}
    if len(points) == 1:
        actual["mean"] = points[0]["y"]
        if (
            points[0]["x"] is not None
            and len(intervals) == 1
            and math.isclose(
                points[0]["x"], intervals[0]["x"], rel_tol=0, abs_tol=1e-12
            )
        ):
            actual.update({k: intervals[0][k] for k in ("low", "high")})
            actual["half_span"] = (actual["high"] - actual["low"]) / 2
    texts = []
    for text, renderer in drawn_text.values():
        box = text.get_window_extent(renderer)
        if all(math.isfinite(float(v)) for v in box.extents):
            texts.append(
                {
                    "text": text.get_text(),
                    "pt": float(text.get_fontsize()),
                    "bbox": [float(v) for v in box.extents],
                }
            )
    overlaps = []
    # A bounded proxy for title/axis/tick text, not a readability or OCR certificate.
    if len(texts) <= 200:
        for i, first in enumerate(texts):
            for second in texts[i + 1 :]:
                a, b = first["bbox"], second["bbox"]
                area = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(
                    0, min(a[3], b[3]) - max(a[1], b[1])
                )
                if area > 1:
                    overlaps.append([first["text"], second["text"]])
    return {
        "actual": actual,
        "points": points,
        "intervals": intervals,
        "point_visibility": point_visibility,
        "text": texts,
        "text_overlap_candidates": overlaps,
        "overlap_scan_complete": len(texts) <= 200,
        "canvas_dpi": float(figure.dpi),
        "axes_labels": [
            {"title": a.get_title(), "x": a.get_xlabel(), "y": a.get_ylabel()}
            for a in figure.axes
            if a.get_visible()
        ],
    }


def export_measurements(folder: Path, snapshots: list[dict], protocol: dict) -> dict:
    """Decode the files actually written; absence never counts as reproduction/quality success."""
    errors, decoded = [], {}
    for suffix in protocol["formats"]:
        path = folder / ("figure." + suffix)
        try:
            body = path.read_bytes()
            record = {"sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)}
            if suffix == "png":
                with Image.open(path) as image:
                    image.load()
                    rgba = image.convert("RGBA")
                    record.update(
                        {
                            "width": rgba.width,
                            "height": rgba.height,
                            "rgba_sha256": hashlib.sha256(
                                str(rgba.size).encode() + rgba.tobytes()
                            ).hexdigest(),
                            "nonuniform": any(a != b for a, b in rgba.getextrema()),
                        }
                    )
                    record["dpi"] = list(image.info.get("dpi", ()))
            elif suffix == "svg":
                if ET.fromstring(body).tag != "{http://www.w3.org/2000/svg}svg":
                    raise ValueError("not an SVG root")
            elif suffix == "pdf":
                reader = PdfReader(path)
                if len(reader.pages) != 1:
                    raise ValueError("expected exactly one PDF page")
                record["pages"] = 1
            decoded[suffix] = record
        except (OSError, ValueError, ET.ParseError, PyPdfError) as problem:
            errors.append(f"{suffix}: {problem}")
    png = decoded.get("png", {})
    matching = [s for s in snapshots if s.get("format") == "png"]
    measured = matching[0]["measurement"] if len(matching) == 1 else None
    quality = {
        "exports_decoded": not errors and len(decoded) == len(protocol["formats"])
    }
    identity = {}
    for suffix in protocol["formats"]:
        observed = [s for s in snapshots if s.get("format") == suffix]
        basis = None
        if len(observed) == 1 and suffix in decoded:
            if observed[0].get("file_sha256") == decoded[suffix]["sha256"]:
                basis = "exact_bytes"
            elif (
                suffix == "svg"
                and protocol.get("svg_identity") == "native_graphic_dom_v2"
            ):
                digest = svg_graphic_digest((folder / "figure.svg").read_bytes())
                if digest and digest == observed[0].get("svg_graphic_sha256"):
                    basis = "unchanged_native_graphic_dom_accessibility_and_path_whitespace_only"
        identity[suffix] = basis
    quality["one_measured_export_each"] = all(identity.values())
    if measured and png.get("width"):
        dpi = matching[0].get("export_dpi")
        valid_dpi = isinstance(dpi, (int, float)) and math.isfinite(dpi) and dpi > 0
        dpi = dpi if valid_dpi else protocol["dpi"]
        scale = protocol["width_in"] / (png["width"] / dpi)
        fonts = [t["pt"] * scale for t in measured["text"]]
        intervals = measured["intervals"]
        quality.update(
            {
                "requested_png_dpi": valid_dpi
                and dpi == protocol["dpi"]
                and len(png.get("dpi", [])) == 2
                and all(abs(d - dpi) < 0.5 for d in png["dpi"]),
                "nonuniform_png": bool(png.get("nonuniform")),
                "one_visible_point": len(measured["points"]) == 1
                and measured["point_visibility"] == [True],
                "one_visible_interval": len(intervals) == 1
                and intervals[0]["within_axes"]
                and intervals[0]["span_pixels"] * dpi / measured["canvas_dpi"] * scale
                >= protocol["minimum_interval_pixels"],
                "text_at_target_width": bool(fonts)
                and min(fonts) >= protocol["minimum_text_pt"],
            }
        )
        minimum_pt = min(fonts) if fonts else None
    else:
        quality.update(
            {
                k: False
                for k in (
                    "nonuniform_png",
                    "one_visible_point",
                    "one_visible_interval",
                    "text_at_target_width",
                )
            }
        )
        minimum_pt = None
    return {
        "files": decoded,
        "errors": errors,
        "quality_checks": quality,
        "quality_passed": all(quality.values()),
        "minimum_text_pt_at_target": minimum_pt,
        "identity_basis": identity,
        "scope": "Export/artist/physical-size proxies only; overlap candidates require review, human aesthetics/usefulness unmeasured",
    }


def reproduction(first: dict, second: dict) -> dict:
    a = first.get("files", {}).get("png", {}).get("rgba_sha256")
    b = second.get("files", {}).get("png", {}).get("rgba_sha256")
    return {"comparable": bool(a and b), "identical": bool(a and b and a == b)}


def write_json(path: Path, value):
    with path.open("x", encoding="utf8") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write("\n")
