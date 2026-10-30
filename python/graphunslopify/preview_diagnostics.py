"""Bridge actual inspector sources to the owned final PNG draw."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any

from .inspect import SourceLocator, _source, _visible_texts

MAX_SOURCES = 8192
KINDS = {"text", "legend", "bar", "bar_interval"}


class DiagnosticSnapshot:
    """Only primitive IDs/coordinates are retained; no figure ownership is added."""

    def __init__(self) -> None:
        self.figure_id: int | None = None
        self.boxes: dict[SourceLocator, tuple[float, float, float, float]] = {}
        self.origin = (0.0, 0.0)
        self.image: dict[str, Any] | None = None
        self.error: str | None = "No final PNG draw was observed"
        self.truncated = False

    def capture(self, figure: Any, renderer: Any) -> None:
        from matplotlib.container import BarContainer
        from matplotlib.text import Text

        boxes: dict[SourceLocator, tuple[float, float, float, float]] = {}
        self.figure_id = id(figure)
        self.origin = tuple(float(value) for value in figure.bbox.p0)
        self.truncated = False

        def record(key: SourceLocator, bounds: Any, clip: Any = None) -> None:
            if len(boxes) >= MAX_SOURCES:
                self.truncated = True
                return
            left, bottom, right, top = map(float, bounds)
            if not all(math.isfinite(value) for value in (left, bottom, right, top)):
                return
            if clip is not None:
                left, bottom = max(left, clip.xmin), max(bottom, clip.ymin)
                right, top = min(right, clip.xmax), min(top, clip.ymax)
            if right > left and top > bottom:
                boxes[key] = tuple(float(value) for value in (left, bottom, right, top))

        try:
            for artist in _visible_texts(figure):
                if artist.get_alpha() == 0 or artist.get_clip_path() is not None:
                    continue
                box = Text.get_window_extent(artist, renderer)
                record(
                    _source(artist),
                    box.extents,
                    artist.get_clip_box() if artist.get_clip_on() else None,
                )
            for axes in figure.get_axes():
                if not axes.get_visible():
                    continue
                legend = axes.get_legend()
                if legend is not None and legend.get_visible() and legend.get_alpha() != 0:
                    record(_source(legend, "legend"), legend.get_window_extent(renderer).extents)
                clip = axes.get_window_extent(renderer)
                for container in axes.containers:
                    if not isinstance(container, BarContainer):
                        continue
                    for bar in container.patches:
                        if (
                            bar.get_visible()
                            and bar.get_alpha() != 0
                            and bar.get_clip_path() is None
                        ):
                            record(
                                _source(bar, "bar"),
                                bar.get_window_extent(renderer).extents,
                                clip if bar.get_clip_on() else None,
                            )
                    if container.errorbar is None:
                        continue
                    for collection in container.errorbar.lines[2]:
                        if (
                            not collection.get_visible()
                            or collection.get_alpha() == 0
                            or collection.get_clip_path() is not None
                        ):
                            continue
                        widths = collection.get_linewidths()
                        for index, segment in enumerate(collection.get_segments()):
                            if not len(segment) or not len(widths):
                                continue
                            points = collection.get_transform().transform(segment)
                            if not all(math.isfinite(float(value)) for value in points.flat):
                                continue
                            half = renderer.points_to_pixels(widths[index % len(widths)]) / 2
                            if half <= 0:
                                continue
                            record(
                                _source(collection, "bar_interval", index),
                                (
                                    points[:, 0].min() - half,
                                    points[:, 1].min() - half,
                                    points[:, 0].max() + half,
                                    points[:, 1].max() + half,
                                ),
                                clip if collection.get_clip_on() else None,
                            )
            self.boxes, self.error = boxes, None
        except (AttributeError, TypeError, ValueError, RuntimeError) as problem:
            self.boxes, self.error = {}, str(problem)

    def finish(self, png: Path) -> None:
        from PIL import Image

        try:
            with Image.open(png) as raster:
                if raster.format != "PNG":
                    raise ValueError("Diagnostic geometry requires the original PNG")
                width, height = raster.size
            self.image = {
                "name": png.name,
                "width": width,
                "height": height,
                "sha256": hashlib.sha256(png.read_bytes()).hexdigest(),
            }
        except (OSError, ValueError) as problem:
            self.image, self.error = None, str(problem)

    def project(self, figure: Any, report: Any) -> dict[str, Any]:
        answer: dict[str, Any] = {
            "schema_version": 1,
            "available": False,
            "coordinates": "pixels_top_left",
            "findings": [],
        }
        if self.figure_id != id(figure) or self.error or self.image is None:
            answer["error"] = self.error or "The inspected figure does not own the final PNG"
            return answer
        width, height = self.image["width"], self.image["height"]
        origin_x, origin_y = self.origin
        for finding in report.findings:
            regions = []
            for key in getattr(finding, "_spatial_sources", ()):
                if key not in self.boxes:
                    continue
                left, bottom, right, top = self.boxes[key]
                left, right = max(0.0, left - origin_x), min(width, right - origin_x)
                top, bottom = (
                    max(0.0, height - top + origin_y),
                    min(height, height - bottom + origin_y),
                )
                if right > left and bottom > top:
                    region = {"kind": key[0], "bounds": [left, top, right - left, bottom - top]}
                    if region not in regions:
                        regions.append(region)
            entry = {
                "finding": {
                    "severity": finding.severity,
                    "code": finding.code,
                    "message": finding.message,
                },
                "regions": regions,
            }
            if not regions:
                entry["reason"] = "No reliable visible location was captured for this finding"
            answer["findings"].append(entry)
        answer.update(available=True, image=self.image, truncated=self.truncated)
        return answer


def bind_diagnostic_map(
    candidate: Any, png: Path, exported: Any, report: dict, run_id: str
) -> dict:
    """Validate locations against the actual exported image and unique findings."""
    from PIL import Image

    findings = report.get("findings", [])
    unavailable = {
        "schema_version": 1,
        "available": False,
        "targets": [],
        "unlocated": [
            {"finding_index": index, "reason": "No reliable diagnostic location is available"}
            for index in range(len(findings))
        ],
    }
    try:
        if (
            not isinstance(candidate, dict)
            or type(candidate.get("schema_version")) is not int
            or candidate["schema_version"] != 1
        ):
            raise ValueError("Unsupported diagnostic geometry version")
        if (
            candidate.get("available") is not True
            or candidate.get("coordinates") != "pixels_top_left"
        ):
            raise ValueError(
                str(candidate.get("error", "Diagnostic geometry is unavailable"))[:400]
            )
        if not isinstance(exported, dict):
            raise TypeError("No current PNG export is available")
        image = candidate.get("image")
        if not isinstance(image, dict) or image.get("name") != png.name:
            raise ValueError("Diagnostic geometry does not name the current PNG")
        digest = hashlib.sha256(png.read_bytes()).hexdigest()
        if image.get("sha256") != digest or exported.get("sha256") != digest:
            raise ValueError("Diagnostic geometry does not describe the current PNG")
        with Image.open(png) as raster:
            if raster.format != "PNG":
                raise ValueError("Diagnostic geometry requires a PNG")
            width, height = raster.size
        if (
            type(image.get("width")) is not int
            or type(image.get("height")) is not int
            or (image["width"], image["height"]) != (width, height)
        ):
            raise ValueError("Diagnostic image dimensions do not match the actual PNG")
        entries = candidate.get("findings")
        if not isinstance(entries, list) or len(entries) > MAX_SOURCES:
            raise ValueError("Invalid or excessive diagnostic findings")
        lookup: dict[tuple, list[int]] = {}
        for index, finding in enumerate(findings):
            key = tuple(finding.get(field) for field in ("severity", "code", "message"))
            if all(isinstance(value, str) for value in key):
                lookup.setdefault(key, []).append(index)
        targets, seen, reasons = [], set(), {}
        inspected = 0
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("finding"), dict):
                raise TypeError("Malformed diagnostic identity")
            key = tuple(entry["finding"].get(field) for field in ("severity", "code", "message"))
            if not all(isinstance(value, str) for value in key) or len(lookup.get(key, [])) != 1:
                raise ValueError("Diagnostic identity does not match one actual finding")
            index = lookup[key][0]
            regions = entry.get("regions")
            if not isinstance(regions, list):
                raise TypeError("Malformed diagnostic regions")
            inspected += len(regions)
            if inspected > MAX_SOURCES * 2:
                raise ValueError("Excessive diagnostic regions")
            if not regions:
                reasons[index] = str(
                    entry.get("reason", "No reliable visible location was captured")
                )[:400]
            for region in regions:
                if not isinstance(region, dict) or region.get("kind") not in KINDS:
                    raise ValueError("Unknown diagnostic primitive")
                bounds = region.get("bounds")
                if (
                    not isinstance(bounds, list)
                    or len(bounds) != 4
                    or not all(
                        type(value) in (int, float) and math.isfinite(value) for value in bounds
                    )
                ):
                    raise ValueError("Diagnostic bounds must contain four finite numbers")
                x, y, w, h = bounds
                if (
                    x < 0
                    or y < 0
                    or w <= 0
                    or h <= 0
                    or x + w > width + 1e-7
                    or y + h > height + 1e-7
                ):
                    raise ValueError("Diagnostic bounds lie outside the current PNG")
                identity = index, region["kind"], *bounds
                if identity not in seen:
                    seen.add(identity)
                    targets.append(
                        {
                            "id": f"{index}:{len(targets)}",
                            "finding_index": index,
                            "kind": region["kind"],
                            "bounds": bounds,
                        }
                    )
        located = {target["finding_index"] for target in targets}
        return {
            "schema_version": 1,
            "available": True,
            "coordinates": "pixels_top_left",
            "image": {"name": png.name, "width": width, "height": height, "sha256": digest},
            "spec_hash": report["spec_hash"],
            "run_id": run_id,
            "targets": targets,
            "truncated": candidate.get("truncated") is True,
            "unlocated": [
                {
                    "finding_index": index,
                    "reason": reasons.get(
                        index, "This check did not provide a reliable visible location"
                    ),
                }
                for index in range(len(findings))
                if index not in located
            ],
        }
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as problem:
        return {**unavailable, "error": str(problem)[:400]}
