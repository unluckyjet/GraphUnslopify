"""Measure renderer-owned text targets during the actual cropped PNG draw."""

from __future__ import annotations

import hashlib
import json
import math
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

TARGET_ATTRIBUTE = "_graphunslopify_text_target"


@contextmanager
def capture_png_geometry(figure: Any, png: Path, destination: Path):
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
        except (AttributeError, ValueError, RuntimeError, TypeError) as problem:
            snapshot.clear()
            snapshot["error"] = str(problem)

    callback = figure.canvas.mpl_connect("draw_event", drawn)
    try:
        yield
    finally:
        figure.canvas.mpl_disconnect(callback)

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
    except (OSError, ValueError, KeyError, TypeError) as problem:
        result = {"schema_version": 1, "available": False, "error": str(problem), "targets": []}
    try:
        destination.write_text(
            json.dumps(result, allow_nan=False, ensure_ascii=False), encoding="utf8"
        )
    except OSError as problem:
        print(f"Preview text geometry unavailable: {problem}", file=sys.stderr)
