"""Measure renderer-owned text targets during the actual cropped PNG draw."""

from __future__ import annotations

import hashlib
import json
import math
import sys
from contextlib import contextmanager
from itertools import pairwise
from pathlib import Path
from typing import Any

TARGET_ATTRIBUTE = "_graphunslopify_text_target"
ELEMENT_ATTRIBUTE = "_graphunslopify_inspector_target"


def _element_entries(figure, renderer):
    """Observe known axis bindings and explicitly tagged intervals, never infer marks."""
    from matplotlib.collections import PolyCollection

    entries, gaps = [], []
    for panel, axes in enumerate(figure.get_axes()):
        if not axes.get_visible() or not axes.axison or axes.name != "rectilinear":
            gaps.append(f"Panel {panel + 1} has no supported Cartesian axis targets")
            continue
        for name in ("x", "y"):
            axis = getattr(axes, name + "axis")
            target = getattr(axis.label, TARGET_ATTRIBUTE, None)
            if not target or target.get("role") != "axis_label" or not axis.get_visible():
                continue
            box = axis.get_tightbbox(renderer)
            if box is not None:
                entries.append(
                    {
                        "role": "axis",
                        "path": target["path"][:1],
                        "source": target.get("source"),
                        "visual_axis": name,
                        "panel": panel,
                        "box": list(box.extents),
                    }
                )
        for artist in axes.collections:
            target = getattr(artist, ELEMENT_ATTRIBUTE, None)
            if not target or not artist.get_visible() or artist.get_alpha() == 0:
                continue
            if artist.get_clip_path() is not None:
                gaps.append(f"Panel {panel + 1} interval has an unsupported custom clip")
                continue
            clip_box = artist.get_clip_box() if artist.get_clip_on() else None
            if clip_box is not None and any(
                abs(a - b) > 0.001
                for a, b in zip(
                    clip_box.extents, axes.get_window_extent(renderer).extents, strict=True
                )
            ):
                gaps.append(f"Panel {panel + 1} interval has an unsupported custom clip box")
                continue
            paths = artist.get_paths()
            if (
                sum(len(p.vertices) for p in paths) > 20000
                or len(paths) > 512
                or len(entries) >= 512
            ):
                gaps.append("Interval target capacity exceeded")
                continue
            shapes = []
            for path in paths:
                points = artist.get_transform().transform(path.vertices)
                if not len(points) or not all(math.isfinite(float(v)) for v in points.flat):
                    gaps.append("An interval path has unavailable coordinates")
                    continue
                closed = isinstance(artist, PolyCollection)
                x0, y0 = points[0]
                if closed:
                    area = math.fsum(
                        (a[0] - x0) * (b[1] - y0) - (b[0] - x0) * (a[1] - y0)
                        for a, b in pairwise(points)
                    )
                    visible = abs(area) > 1e-9
                else:
                    visible = any(math.hypot(x - x0, y - y0) > 1e-9 for x, y in points)
                if not visible:
                    gaps.append(
                        "A zero-area or zero-length interval has no selectable visible path"
                    )
                    continue
                shapes.append({"points": points.tolist(), "closed": closed})
            if not shapes:
                continue
            points = [point for shape in shapes for point in shape["points"]]
            width = max(artist.get_linewidths(), default=1)
            padding = renderer.points_to_pixels(width) / 2 + 3
            box = [
                min(p[0] for p in points) - padding,
                min(p[1] for p in points) - padding,
                max(p[0] for p in points) + padding,
                max(p[1] for p in points) + padding,
            ]
            clip = axes.get_window_extent(renderer) if artist.get_clip_on() else figure.bbox
            box = [
                max(box[0], clip.x0),
                max(box[1], clip.y0),
                min(box[2], clip.x1),
                min(box[3], clip.y1),
            ]
            entries.append(
                {
                    **target,
                    "panel": panel,
                    "box": box,
                    "shapes": shapes,
                    "hit_width": padding * 2,
                    "clip": list(clip.extents),
                }
            )
    return entries, gaps


@contextmanager
def capture_png_geometry(figure: Any, png: Path, destination: Path, *, diagnostics: Any = None):
    """Observe savefig without redrawing or changing the saved figure.

    savefig may draw twice for tight cropping. The last draw owns the final
    coordinate system; normal canvas dimensions before savefig do not.
    Geometry failures are independent of scientific acceptance.
    """
    snapshot: dict[str, Any] = {}

    def drawn(event: Any) -> None:
        from matplotlib.axes import Axes
        from matplotlib.axis import Axis
        from matplotlib.text import Text

        if diagnostics is not None:
            try:
                diagnostics.capture(figure, event.renderer)
            except (AttributeError, TypeError, ValueError, RuntimeError) as problem:
                diagnostics.error = str(problem)

        def visible_text(artist: Any):
            if not artist.get_visible():
                return
            if isinstance(artist, Text):
                if artist.get_alpha() != 0:
                    yield artist
                return
            for child in artist.get_children():
                # Axis labels can have axes=None. Follow the actual ownership
                # tree; Axes.draw omits its Axis children when axison=False.
                if isinstance(artist, Axes) and not artist.axison and isinstance(child, Axis):
                    continue
                yield from visible_text(child)

        try:
            entries = []
            for artist in visible_text(figure):
                target = getattr(artist, TARGET_ATTRIBUTE, None)
                if not target or not artist.get_text().strip():
                    continue
                # Annotation.get_window_extent includes its arrow. Only the
                # literal text is a text-editing target.
                box = Text.get_window_extent(artist, event.renderer)
                bounds = [box.x0, box.y0, box.x1, box.y1]
                if not all(math.isfinite(value) for value in bounds):
                    continue
                if box.width <= 0 or box.height <= 0:
                    continue
                entries.append({**target, "text": artist.get_text(), "box": bounds})
            snapshot.clear()
            snapshot.update(entries=entries, origin=list(figure.bbox.p0))
            try:
                snapshot["elements"], snapshot["element_gaps"] = _element_entries(
                    figure, event.renderer
                )
            except (AttributeError, ValueError, RuntimeError, TypeError) as problem:
                snapshot.update(elements=[], element_gaps=[str(problem)])
        except (AttributeError, ValueError, RuntimeError, TypeError) as problem:
            snapshot.clear()
            snapshot["error"] = str(problem)

    callback = figure.canvas.mpl_connect("draw_event", drawn)
    try:
        yield
    finally:
        figure.canvas.mpl_disconnect(callback)

    if diagnostics is not None:
        diagnostics.finish(png)

    try:
        from PIL import Image

        if "entries" not in snapshot:
            raise ValueError(snapshot.get("error", "No final PNG draw was observed"))
        with Image.open(png) as image:
            if image.format != "PNG":
                raise ValueError("Geometry requires the original PNG export")
            width, height = image.size
        origin_x, origin_y = snapshot["origin"]
        targets = []
        for entry in snapshot["entries"]:
            left, bottom, right, top = entry.pop("box")
            left, right = max(0, left - origin_x), min(width, right - origin_x)
            top, bottom = max(0, height - top + origin_y), min(height, height - bottom + origin_y)
            if right <= left or bottom <= top:
                continue
            targets.append({**entry, "bounds": [left, top, right - left, bottom - top]})
        result = {
            "schema_version": 1,
            "available": True,
            "coordinates": "pixels_top_left",
            "image": {
                "name": png.name,
                "width": width,
                "height": height,
                "sha256": hashlib.sha256(png.read_bytes()).hexdigest(),
            },
            "targets": targets,
        }
        elements = [{"role": "figure", "path": [], "bounds": [0, 0, width, height]}]
        for entry in snapshot.get("elements", []):
            left, bottom, right, top = entry.pop("box")
            bounds = [
                max(0, left - origin_x),
                max(0, height - top + origin_y),
                min(width, right - origin_x),
                min(height, height - bottom + origin_y),
            ]
            if (
                not all(math.isfinite(v) for v in bounds)
                or bounds[2] <= bounds[0]
                or bounds[3] <= bounds[1]
            ):
                continue
            for shape in entry.get("shapes", []):
                shape["points"] = [
                    [x - origin_x, height - y + origin_y] for x, y in shape["points"]
                ]
            if "clip" in entry:
                x0, y0, x1, y1 = entry["clip"]
                entry["clip"] = [x0 - origin_x, height - y1 + origin_y, x1 - x0, y1 - y0]
            elements.append(
                {
                    **entry,
                    "bounds": [bounds[0], bounds[1], bounds[2] - bounds[0], bounds[3] - bounds[1]],
                }
            )
        result["elements"] = {
            "schema_version": 1,
            "targets": elements,
            "gaps": snapshot.get("element_gaps", []),
            "scope": "Supported tagged Cartesian axes and intervals; other marks are not mapped",
        }
    except (OSError, ValueError, KeyError, TypeError) as problem:
        result = {"schema_version": 1, "available": False, "error": str(problem), "targets": []}
    try:
        destination.write_text(
            json.dumps(result, allow_nan=False, ensure_ascii=False), encoding="utf8"
        )
    except OSError as problem:
        print(f"Preview text geometry unavailable: {problem}", file=sys.stderr)
