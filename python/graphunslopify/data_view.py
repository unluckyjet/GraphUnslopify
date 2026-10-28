"""Inspect coordinate visibility without claiming to know unprovided source rows."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import numpy as np


def _coordinates(axes: Any) -> Iterator[tuple[str, Any, Any]]:
    from matplotlib.collections import LineCollection, PathCollection, PolyCollection
    from matplotlib.path import Path

    for line in axes.lines:
        # Axes-fraction reference lines and decoration transforms are not samples.
        if line.get_visible() and line.get_alpha() != 0 and line.get_transform() == axes.transData:
            yield "line", line, line.get_xydata()
    for collection in axes.collections:
        if not collection.get_visible() or collection.get_alpha() == 0:
            continue
        if isinstance(collection, PathCollection):
            if collection.get_offset_transform() == axes.transData:
                yield "scatter", collection, collection.get_offsets()
        elif collection.get_transform() == axes.transData:
            if isinstance(collection, LineCollection):
                for segment in collection.get_segments():
                    yield "segments", collection, segment
            elif isinstance(collection, PolyCollection):
                for path in collection.get_paths():
                    vertices = path.vertices
                    if path.codes is not None:
                        vertices = vertices[~np.isin(path.codes, [Path.CLOSEPOLY, Path.STOP])]
                    yield "polygon", collection, vertices


def inspect_data_view(axes: Any) -> tuple[dict[str, Any], list[tuple[str, str, str]]]:
    """Count finite artist coordinates, never independent source observations.

    Outside-axis centers/vertices can still have visible marker/segment ink.
    These counts are a review warning, not an assertion that every mark vanished.
    Custom clipping paths and child inset axes are outside this axes-bound check.
    """
    report: dict[str, Any] = {
        "basis": "artist_coordinates_not_source_sample_sizes",
        "scope": "intentional_axis_break" if axes.get_label() == "<axis-break>" else "axes_bounds",
        "x_scale": axes.get_xscale(),
        "y_scale": axes.get_yscale(),
        "x_limits": [float(v) for v in axes.get_xlim()],
        "y_limits": [float(v) for v in axes.get_ylim()],
        "artists": [],
    }
    findings: list[tuple[str, str, str]] = []
    if not axes.get_visible() or axes.name != "rectilinear" or axes.get_label() == "<colorbar>":
        report["scope"] = "unsupported_or_invisible_axes"
        return report, findings
    bounds = axes.get_window_extent()
    outside_total = 0
    nonpositive = {"x": 0, "y": 0}
    for kind, artist, values in _coordinates(axes):
        masked = np.ma.asarray(values, dtype=float)
        if masked.ndim != 2 or masked.shape[1] != 2 or not len(masked):
            continue
        points = np.asarray(masked.filled(np.nan))
        finite = np.isfinite(points).all(axis=1) & ~np.ma.getmaskarray(masked).any(axis=1)
        valid = points[finite]
        invalid_log = np.zeros(len(valid), dtype=bool)
        item = {
            "kind": kind,
            "finite_coordinates": int(finite.sum()),
            "unavailable_coordinates": int((~finite).sum()),
            "clip_on": bool(artist.get_clip_on()),
            "outside_axes": 0,
        }
        for index, name in enumerate(("x", "y")):
            bad = (
                valid[:, index] <= 0
                if report[f"{name}_scale"] == "log"
                else np.zeros(len(valid), dtype=bool)
            )
            item[f"nonpositive_{name}"] = int(bad.sum())
            nonpositive[name] += int(bad.sum())
            invalid_log |= bad
        if artist.get_clip_on() and len(valid):
            display = axes.transData.transform(valid[~invalid_log])
            outside = (
                (display[:, 0] < bounds.xmin - 1e-7)
                | (display[:, 0] > bounds.xmax + 1e-7)
                | (display[:, 1] < bounds.ymin - 1e-7)
                | (display[:, 1] > bounds.ymax + 1e-7)
            )
            item["outside_axes"] = int(outside.sum())
            outside_total += int(outside.sum())
        report["artists"].append(item)
    for name, count in nonpositive.items():
        if count:
            findings.append(
                (
                    "error",
                    "log_domain_hidden",
                    (
                        f"{count} finite artist coordinates are zero/negative on log {name}. "
                        "A log scale clips or masks these values, changing the visible evidence. "
                        "Use linear/symlog or explicitly filter and disclose the excluded domain."
                    ),
                )
            )
    if outside_total and report["scope"] != "intentional_axis_break":
        findings.append(
            (
                "warning",
                "data_outside_view",
                (
                    f"{outside_total} finite artist coordinates lie outside the axes with clipping enabled. "
                    "Marker centers/vertices outside a view are not source sample counts; segments may still be visible. "
                    "Widen limits or disclose this zoom and inspect the retained evidence."
                ),
            )
        )
    return report, findings
