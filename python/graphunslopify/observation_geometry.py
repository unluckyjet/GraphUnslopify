"""Capture observation geometry from the draw that writes the owned PNG."""

from __future__ import annotations

import hashlib
import math
import os
import stat
from bisect import bisect_left, bisect_right
from itertools import pairwise
from numbers import Real
from operator import neg
from pathlib import Path

RUN_STAMP = "GraphUnslopifyObservationRun"
MAX_PANELS = 512
MAX_INTERVAL_STROKES = 12_000
MAX_ESTIMATE_MARKS = 4_000


def inspect_png(path, run_id):
    """Read the PNG identity and dimensions from the same open file."""
    from PIL import Image

    path = Path(path)
    if not path.is_file():
        raise ValueError("Observation geometry requires a regular PNG export")
    with path.open("rb") as source:
        initial = os.fstat(source.fileno())
        if not stat.S_ISREG(initial.st_mode):
            raise ValueError("Observation geometry requires a regular PNG export")
        try:
            with Image.open(source, formats=["PNG"]) as image:
                if image.info.get(RUN_STAMP) != run_id:
                    raise ValueError("PNG belongs to a different observation run")
                width, height = image.size
        except Image.DecompressionBombError as problem:
            raise ValueError("PNG exceeds the observation geometry image capacity") from problem
        source.seek(0)
        digest = hashlib.sha256()
        length = 0
        for block in iter(lambda: source.read(65536), b""):
            digest.update(block)
            length += len(block)
        final = os.fstat(source.fileno())
        if length != initial.st_size or (initial.st_mtime_ns, initial.st_ctime_ns) != (
            final.st_mtime_ns,
            final.st_ctime_ns,
        ):
            raise ValueError("Observation PNG changed while verifying its bytes")
    return {"sha256": digest.hexdigest(), "bytes": length, "width": width, "height": height}


def _visible_matrix_images(artist):
    from matplotlib.image import AxesImage

    if not artist.get_visible():
        return
    if isinstance(artist, AxesImage):
        alpha = artist.get_alpha()
        if hasattr(artist, "_graphunslopify_matrix_panel_id") and not (
            isinstance(alpha, Real) and alpha == 0
        ):
            yield artist
        return
    for child in artist.get_children():
        yield from _visible_matrix_images(child)


def finite_number(value):
    return (type(value) is float and math.isfinite(value)) or (
        type(value) is int and abs(value) < 2**53
    )


def ordered_edges(edges):
    if len(edges) < 2 or not all(map(finite_number, edges)):
        return False
    if edges[0] < edges[-1]:
        return all(a < b for a, b in pairwise(edges))
    return all(a > b for a, b in pairwise(edges))


def _grid(image):
    import numpy as np

    if image.get_clip_on() and image.get_clip_path() is not None:
        raise ValueError("A matrix has a nonrectangular clip")
    transform = image.get_transform()
    if not transform.is_separable:
        raise ValueError("A matrix has a nonseparable transform")
    rows, columns = image.get_array().shape
    left, right, bottom, top = image.get_extent()
    x_values = np.linspace(left, right, columns + 1)
    y_values = (
        np.linspace(top, bottom, rows + 1)
        if image.origin == "upper"
        else np.linspace(bottom, top, rows + 1)
    )
    x_edges = transform.transform(np.column_stack((x_values, np.full(columns + 1, top))))[
        :, 0
    ].tolist()
    y_edges = transform.transform(np.column_stack((np.full(rows + 1, right), y_values)))[
        :, 1
    ].tolist()
    if not ordered_edges(x_edges) or not ordered_edges(y_edges):
        raise ValueError("A matrix has nonfinite or nonmonotone cell boundaries")
    clip_box = image.get_clip_box() if image.get_clip_on() else None
    left, right = sorted((x_edges[0], x_edges[-1]))
    bottom, top = sorted((y_edges[0], y_edges[-1]))
    if clip_box is not None:
        clip_left, clip_bottom, clip_right, clip_top = map(float, clip_box.extents)
        if not all(map(math.isfinite, (clip_left, clip_bottom, clip_right, clip_top))):
            raise ValueError("A matrix has a nonfinite clip box")
        left, right = max(left, clip_left), min(right, clip_right)
        bottom, top = max(bottom, clip_bottom), min(top, clip_top)
    return {
        "panel_id": image._graphunslopify_matrix_panel_id,
        "x_edges": x_edges,
        "y_edges": y_edges,
        "clip": [left, bottom, right, top],
    }


def _save_observation_png(figure, path, *, metadata, dpi, run_id, collect, label):
    """Save once and keep only the final observed tight PNG draw."""
    snapshot = {}

    def drawn(event):
        snapshot.clear()
        snapshot.update(origin=figure.bbox.p0.tolist(), entries=[], gaps=[])
        try:
            collect(figure, event.renderer, snapshot["entries"], snapshot["gaps"])
        except (AttributeError, TypeError, RuntimeError, ValueError) as problem:
            snapshot["gaps"].append(f"Could not measure a {label} draw ({type(problem).__name__})")

    canvas = figure.canvas
    callback = canvas.mpl_connect("draw_event", drawn)
    try:
        figure.savefig(path, bbox_inches="tight", metadata={**metadata, RUN_STAMP: run_id}, dpi=dpi)
    finally:
        canvas.mpl_disconnect(callback)

    try:
        identity = inspect_png(path, run_id)
    except (OSError, ValueError) as problem:
        return (
            None,
            {},
            [f"Could not verify the {label} PNG ({type(problem).__name__})"],
        )
    if not snapshot:
        return identity, {}, [f"No final {label} PNG draw was observed"]
    return identity, snapshot, sorted(set(snapshot["gaps"]))


def _collect_matrix(figure, _renderer, entries, gaps):
    for index, image in enumerate(_visible_matrix_images(figure)):
        if index >= MAX_PANELS:
            gaps.append("Matrix geometry exceeds the panel capacity")
            break
        try:
            entries.append(_grid(image))
        except ValueError as problem:
            gaps.append(str(problem))


def save_matrix_png(figure, path, *, metadata, dpi, run_id):
    """Measure matrix boundaries in the actual tight PNG coordinate system."""
    identity, snapshot, gaps = _save_observation_png(
        figure,
        path,
        metadata=metadata,
        dpi=dpi,
        run_id=run_id,
        collect=_collect_matrix,
        label="matrix",
    )
    if not snapshot:
        return identity, [], gaps
    width, height = identity["width"], identity["height"]
    origin_x, origin_y = snapshot["origin"]
    grids = []
    for grid in snapshot["entries"]:
        left, bottom, right, top = grid["clip"]
        left, right = max(0, left - origin_x), min(width, right - origin_x)
        top, bottom = (
            max(0, height - top + origin_y),
            min(height, height - bottom + origin_y),
        )
        if left < right and top < bottom:
            grids.append(
                {
                    "panel_id": grid["panel_id"],
                    "x_edges": [x - origin_x for x in grid["x_edges"]],
                    "y_edges": [height - y + origin_y for y in grid["y_edges"]],
                    "clip": [left, top, right, bottom],
                }
            )
    return identity, grids, gaps


def _visible_tagged_artists(artist, attribute):
    if not artist.get_visible():
        return
    if hasattr(artist, attribute):
        alpha = artist.get_alpha()
        if not (isinstance(alpha, Real) and alpha == 0):
            yield artist
        return
    for child in artist.get_children():
        yield from _visible_tagged_artists(child, attribute)


def _rectangular_clip(artist):
    if not artist.get_clip_on():
        return None
    if artist.get_clip_path() is not None:
        raise ValueError("An observation mark has a nonrectangular clip")
    box = artist.get_clip_box()
    if box is None:
        return None
    clip = box.extents.tolist()
    if not all(map(finite_number, clip)):
        raise ValueError("An observation mark has a nonfinite clip box")
    return clip


def _interval_strokes(artist, renderer):
    from matplotlib.collections import LineCollection
    from matplotlib.lines import Line2D

    ids = artist._graphunslopify_interval_ids
    clip = _rectangular_clip(artist)
    transform = artist.get_transform()
    if not transform.is_separable:
        raise ValueError("An interval has a nonseparable transform")
    if isinstance(artist, LineCollection):
        segments = artist.get_segments()
        widths = artist.get_linewidths()
        if len(segments) != len(ids) or len(widths) == 0:
            raise ValueError("Error-bar segments do not match their calculation positions")
        for index, (node_id, segment) in enumerate(zip(ids, segments, strict=True)):
            if not len(segment):
                continue
            if node_id is None:
                raise ValueError("An error-bar stem has no calculation at its drawn position")
            if segment.shape != (2, 2):
                raise ValueError("An error-bar stem must have two endpoints")
            endpoints = transform.transform(segment).tolist()
            radius = renderer.points_to_pixels(float(widths[index % len(widths)])) / 2
            yield node_id, endpoints, float(radius), clip, "stem"
    elif isinstance(artist, Line2D) and hasattr(artist, "_graphunslopify_interval_role"):
        points = artist.get_xydata()
        if len(ids) != 1 or points.shape != (2, 2):
            raise ValueError("A forest interval stroke does not match its summary position")
        radius = renderer.points_to_pixels(artist.get_linewidth()) / 2
        yield (
            ids[0],
            transform.transform(points).tolist(),
            float(radius),
            clip,
            artist._graphunslopify_interval_role,
        )
    elif isinstance(artist, Line2D) and artist.get_marker() in ("_", "|"):
        points = transform.transform(artist.get_xydata()).tolist()
        if len(points) != len(ids):
            raise ValueError("Error-bar caps do not match their calculation positions")
        half_span = renderer.points_to_pixels(artist.get_markersize()) / 2
        radius = renderer.points_to_pixels(artist.get_markeredgewidth()) / 2
        horizontal = artist.get_marker() == "_"
        for node_id, (x, y) in zip(ids, points, strict=True):
            if not (finite_number(x) and finite_number(y)):
                continue
            if node_id is None:
                raise ValueError("An error-bar cap has no calculation at its drawn position")
            endpoints = (
                [[x - half_span, y], [x + half_span, y]]
                if horizontal
                else [[x, y - half_span], [x, y + half_span]]
            )
            yield node_id, endpoints, float(radius), clip, "cap"
    else:
        raise ValueError("Unsupported error-bar artist")


def _collect_intervals(figure, renderer, entries, gaps):
    for artist in _visible_tagged_artists(figure, "_graphunslopify_interval_ids"):
        try:
            for stroke in _interval_strokes(artist, renderer):
                if len(entries) >= MAX_INTERVAL_STROKES:
                    gaps.append("Interval geometry exceeds its stroke capacity")
                    return
                entries.append(stroke)
        except ValueError as problem:
            gaps.append(str(problem))


def _pixel_clip(raw_clip, origin, width, height):
    if raw_clip is None:
        return [0, 0, width, height]
    origin_x, origin_y = origin
    left, bottom, right, top = raw_clip
    return [
        max(0, left - origin_x),
        max(0, height - top + origin_y),
        min(width, right - origin_x),
        min(height, height - bottom + origin_y),
    ]


def save_summary_interval_png(figure, path, *, metadata, dpi, run_id):
    """Capture the actual transformed strokes for visible summary error bars."""
    identity, snapshot, gaps = _save_observation_png(
        figure,
        path,
        metadata=metadata,
        dpi=dpi,
        run_id=run_id,
        collect=_collect_intervals,
        label="summary interval",
    )
    return (
        identity,
        _stroke_pixels(identity, snapshot, snapshot.get("entries", ()), gaps),
        sorted(set(gaps)),
    )


def _stroke_pixels(image, snapshot, entries, gaps):
    if not snapshot:
        return []
    width, height = image["width"], image["height"]
    origin_x, origin_y = snapshot["origin"]
    strokes = []
    for node_id, points, radius, raw_clip, role in entries:
        if not all(finite_number(value) for point in points for value in point):
            gaps.append("An error-bar stem has nonfinite endpoints")
            continue
        bounds = _pixel_clip(raw_clip, snapshot["origin"], width, height)
        if bounds[0] >= bounds[2] or bounds[1] >= bounds[3]:
            continue
        pixels = [[x - origin_x, height - y + origin_y] for x, y in points]
        if radius == 0:
            continue
        if not finite_number(radius) or not 0 < radius <= 128:
            gaps.append("An error-bar stroke has an unsupported width")
            continue
        (x0, y0), (x1, y1) = pixels
        left, top, right, bottom = bounds
        if (
            max(x0, x1) + radius <= left
            or min(x0, x1) - radius >= right
            or max(y0, y1) + radius <= top
            or min(y0, y1) - radius >= bottom
        ):
            continue
        strokes.append(
            {
                "node_id": node_id,
                "endpoints": pixels,
                "radius": radius,
                "clip": bounds,
                "role": role,
            }
        )
    return strokes


def _band_strips(artist):
    import numpy as np

    ids = artist._graphunslopify_interval_ids
    x, low, high = artist._graphunslopify_band_inputs
    if x.ndim != 1 or x.shape != low.shape or low.shape != high.shape or len(x) != len(ids):
        raise ValueError("Band inputs do not match their summary positions")
    transform = artist.get_transform()
    if not transform.is_separable:
        raise ValueError("A band has a nonseparable transform")
    clip = _rectangular_clip(artist)
    valid = np.flatnonzero(np.isfinite(x) & np.isfinite(low) & np.isfinite(high))
    runs = np.split(valid, np.flatnonzero(np.diff(valid) != 1) + 1) if len(valid) else []
    paths = artist.get_paths()
    if len(runs) != len(paths):
        raise ValueError("Band paths do not match the runs of finite intervals")
    for run, path in zip(runs, paths, strict=True):
        lower = np.column_stack((x[run], low[run]))
        upper = np.column_stack((x[run], high[run]))
        expected = np.vstack((upper[:1], lower, upper[-1:], upper[::-1], upper[:1]))
        if not np.array_equal(path.vertices, expected):
            raise ValueError("A drawn band path differs from its interval endpoints")
        if len(run) == 1:
            continue
        projected = transform.transform_path(path).vertices
        if projected.shape != expected.shape or not np.isfinite(projected).all():
            raise ValueError("A projected band path differs from its drawn endpoints")
        size = len(run)
        bottom = projected[1 : size + 1]
        top = projected[size + 2 : 2 * size + 2][::-1]
        if not np.array_equal(bottom[:, 0], top[:, 0]) or not ordered_edges(bottom[:, 0].tolist()):
            raise ValueError("Band positions are not monotone in the final PNG")
        for i, (first, second) in enumerate(pairwise(run)):
            if bottom[i, 1] == top[i, 1] and bottom[i + 1, 1] == top[i + 1, 1]:
                continue
            points = [bottom[i], top[i], bottom[i + 1], top[i + 1]]
            yield [ids[first], ids[second]], [point.tolist() for point in points], clip


def _collect_bands(figure, _renderer, entries, gaps):
    for artist in _visible_tagged_artists(figure, "_graphunslopify_interval_ids"):
        try:
            for strip in _band_strips(artist):
                if len(entries) >= MAX_INTERVAL_STROKES:
                    gaps.append("Band geometry exceeds its strip capacity")
                    return
                entries.append(strip)
        except ValueError as problem:
            gaps.append(str(problem))


def save_summary_band_png(figure, path, *, metadata, dpi, run_id):
    identity, snapshot, gaps = _save_observation_png(
        figure,
        path,
        metadata=metadata,
        dpi=dpi,
        run_id=run_id,
        collect=_collect_bands,
        label="summary band",
    )
    return identity, _band_pixels(identity, snapshot, snapshot.get("entries", ())), gaps


def _band_pixels(image, snapshot, entries):
    if not snapshot:
        return []
    width, height = image["width"], image["height"]
    origin_x, origin_y = snapshot["origin"]
    strips = []
    for ids, points, raw_clip in entries:
        bounds = _pixel_clip(raw_clip, snapshot["origin"], width, height)
        left, top, right, bottom = bounds
        pixels = [[x - origin_x, height - y + origin_y] for x, y in points]
        xs, ys = zip(*pixels, strict=True)
        if left >= right or top >= bottom or max(xs) <= left or min(xs) >= right:
            continue
        if max(ys) <= top or min(ys) >= bottom:
            continue
        strips.append({"interval_ids": ids, "endpoints": pixels, "clip": bounds})
    return strips


def _estimate_shape(artist, renderer):
    from matplotlib.lines import Line2D
    from matplotlib.patches import Rectangle

    transform = artist.get_transform()
    if not transform.is_separable:
        raise ValueError("A summary estimate has a nonseparable transform")
    if isinstance(artist, Rectangle):
        if artist.get_width() == 0 or artist.get_height() == 0 or artist.get_facecolor()[3] == 0:
            return None
        bounds = artist.get_window_extent(renderer).extents.tolist()
        if not all(map(finite_number, bounds)):
            return None
        return "bar", bounds
    if isinstance(artist, Line2D) and artist.get_marker() == "o":
        points = artist.get_xydata()
        if points.shape != (1, 2):
            raise ValueError("A forest dot must have one calculated position")
        x, y = transform.transform(points)[0].tolist()
        if not (finite_number(x) and finite_number(y)):
            return None
        radius = renderer.points_to_pixels(
            (artist.get_markersize() + artist.get_markeredgewidth()) / 2
        )
        if radius == 0:
            return None
        if not finite_number(radius) or not 0 < radius <= 128:
            raise ValueError("A forest dot has an unsupported marker size")
        return "dot", [x, y, float(radius)]
    raise ValueError("Unsupported summary estimate artist")


def _estimate_curve(artist, renderer):
    from matplotlib.lines import Line2D

    if not isinstance(artist, Line2D) or artist.get_drawstyle() != "default":
        raise ValueError("An estimate curve requires the ordinary line draw style")
    if artist.get_path_effects() or not artist.get_transform().is_separable:
        raise ValueError("An estimate curve uses an unsupported transform or path effect")
    identities = artist._graphunslopify_estimate_ids
    xy = artist.get_xydata()
    if len(identities) != len(xy):
        raise ValueError("Estimate positions do not match the rendered curve")
    points = artist.get_transform().transform(xy).tolist()
    finite = [all(map(finite_number, point)) for point in points]
    marker = artist.get_marker()
    has_markers = marker == "o" and artist.get_markersize() > 0
    if marker not in ("o", "None", "none", None, "", " ") or artist.get_markevery() is not None:
        raise ValueError("An estimate curve has unsupported marker geometry")
    line_radius = renderer.points_to_pixels(artist.get_linewidth()) / 2
    has_stroke = artist.get_linestyle() != "None" and line_radius > 0
    stroke_supported = (
        has_stroke and not artist.is_dashed() and not artist.get_path().should_simplify
    )
    marker_radius = (
        renderer.points_to_pixels((artist.get_markersize() + artist.get_markeredgewidth()) / 2)
        if has_markers
        else 0
    )
    if any(
        not finite_number(radius) or not 0 <= radius <= 128
        for radius in (line_radius, marker_radius)
    ):
        raise ValueError("An estimate curve has an unsupported stroke or marker width")
    connected = [False] * len(points)
    segments = []
    if stroke_supported:
        for index, (first, second) in enumerate(pairwise(points)):
            if finite[index] and finite[index + 1] and first != second:
                connected[index] = connected[index + 1] = True
                segments.append(
                    (
                        identities[index : index + 2],
                        ("segment", [first, second, float(line_radius)]),
                    )
                )
    for identity, point, valid, on_stroke in zip(
        identities, points, finite, connected, strict=True
    ):
        if valid and (has_markers or on_stroke):
            x, y = point
            radius = max(marker_radius, line_radius if on_stroke else 0)
            yield identity, ("dot" if has_markers else "vertex", [x, y, float(radius)])
    yield from segments


def _curve_connections_unavailable(artist):
    if artist.is_dashed():
        return (
            "Dashed line connections are unavailable. Visible point markers can still be selected."
        )
    if artist.get_path().should_simplify:
        return "Simplified line connections are unavailable. Visible point markers can still be selected."
    return None


def _collect_estimates(figure, renderer, entries, gaps, coverage):
    for artist in _visible_tagged_artists(figure, "_graphunslopify_estimate_id"):
        try:
            identity = artist._graphunslopify_estimate_id
            clip = _rectangular_clip(artist)
            if identity is None:
                limitation = _curve_connections_unavailable(artist)
                if limitation:
                    coverage.append(limitation)
                shapes = _estimate_curve(artist, renderer)
            else:
                shape = _estimate_shape(artist, renderer)
                shapes = () if shape is None else ((identity, shape),)
            for mark_identity, mark_shape in shapes:
                if len(entries) >= MAX_ESTIMATE_MARKS:
                    gaps.append("Estimate geometry exceeds its mark capacity")
                    return
                entries.append((mark_identity, clip, mark_shape))
        except ValueError as problem:
            gaps.append(str(problem))


def _estimate_pixels(image, snapshot, entries):
    width, height = image["width"], image["height"]
    origin_x, origin_y = snapshot["origin"]
    marks = []
    for identity, raw_clip, (kind, points) in entries:
        clip = _pixel_clip(raw_clip, snapshot["origin"], width, height)
        left, top, right, bottom = clip
        if left >= right or top >= bottom:
            continue
        if kind == "bar":
            x0, y0, x1, y1 = points
            bounds = [
                max(left, x0 - origin_x),
                max(top, height - y1 + origin_y),
                min(right, x1 - origin_x),
                min(bottom, height - y0 + origin_y),
            ]
            if bounds[0] < bounds[2] and bounds[1] < bounds[3]:
                marks.append({"node_id": identity, "kind": kind, "bounds": bounds})
        elif kind == "segment":
            first, second, radius = points
            endpoints = [[x - origin_x, height - y + origin_y] for x, y in (first, second)]
            if _segment_intersects_clip(endpoints, clip, radius):
                marks.append(
                    {
                        "endpoint_ids": identity,
                        "kind": kind,
                        "endpoints": endpoints,
                        "radius": radius,
                        "clip": clip,
                    }
                )
        else:
            x, y, radius = points
            x, y = x - origin_x, height - y + origin_y
            if (
                x + radius > left
                and x - radius < right
                and y + radius > top
                and y - radius < bottom
            ):
                marks.append(
                    {
                        "node_id": identity,
                        "kind": kind,
                        "center": [x, y],
                        "radius": radius,
                        "clip": clip,
                    }
                )
    return marks


def _segment_intersects_clip(points, clip, radius):
    """Test the centerline against the clip expanded by the stroke radius."""
    start, end = points
    lo, hi = 0.0, 1.0
    for index, (lower, upper) in enumerate(zip(clip[:2], clip[2:], strict=True)):
        delta = end[index] - start[index]
        minimum, maximum = lower - radius - start[index], upper + radius - start[index]
        if delta == 0:
            if not minimum <= 0 <= maximum:
                return False
        else:
            first, last = sorted((minimum / delta, maximum / delta))
            lo, hi = max(lo, first), min(hi, last)
            if hi < lo:
                return False
    return True


def save_summary_marks_png(figure, path, *, metadata, dpi, run_id, interval_kind="strokes"):
    """Read estimate and interval artists during the same final PNG draw."""
    collectors = {"strokes": _collect_intervals, "bands": _collect_bands}
    interval_collector = collectors.get(interval_kind)

    def collect(figure, renderer, entries, _gaps):
        intervals, interval_gaps, marks, mark_gaps, coverage = [], [], [], [], []
        if interval_collector is not None:
            interval_collector(figure, renderer, intervals, interval_gaps)
        _collect_estimates(figure, renderer, marks, mark_gaps, coverage)
        entries.append((intervals, interval_gaps, marks, mark_gaps, coverage))

    image, snapshot, gaps = _save_observation_png(
        figure,
        path,
        metadata=metadata,
        dpi=dpi,
        run_id=run_id,
        collect=collect,
        label="summary mark",
    )
    if not snapshot or gaps:
        intervals = (image, [], gaps, interval_kind) if interval_collector else None
        return intervals, (image, [], gaps, [])
    ((intervals, interval_gaps, marks, mark_gaps, coverage),) = snapshot["entries"]
    if interval_kind == "strokes":
        intervals = _stroke_pixels(image, snapshot, intervals, interval_gaps)
    elif interval_kind == "bands":
        intervals = _band_pixels(image, snapshot, intervals)
    marks = _estimate_pixels(image, snapshot, marks)
    interval_capture = (
        (image, intervals, sorted(set(interval_gaps)), interval_kind)
        if interval_collector
        else None
    )
    return interval_capture, (image, marks, sorted(set(mark_gaps)), sorted(set(coverage)))


def cell_index(edges, position):
    """Resolve half-open physical cells, even when array order is reversed."""
    if edges[0] < edges[-1]:
        if edges[0] <= position < edges[-1]:
            return bisect_right(edges, position) - 1
    elif edges[-1] <= position < edges[0]:
        return bisect_left(edges, -position, key=neg) - 1
    return None


def validate_matrix_geometry(node, nodes):
    """Check grids against their ordered matrix-cell calculations before using them."""
    if node.get("operation") != "matrix_png_geometry":
        raise ValueError("Unknown matrix PNG geometry root")
    info = node.get("metadata", {})
    image = info.get("image", {})
    grids, gaps = info.get("grids"), info.get("gaps")
    if (
        info.get("coordinates") != "pixels_top_left"
        or not isinstance(image, dict)
        or not all(
            type(image.get(key)) is int and image[key] > 0 for key in ("width", "height", "bytes")
        )
        or not isinstance(grids, list)
        or not isinstance(gaps, list)
        or not all(isinstance(gap, str) and 0 < len(gap) <= 250 for gap in gaps)
        or type(node["value"]) is not int
        or len(grids) != node["value"]
        or len(grids) > MAX_PANELS
        or len(gaps) > MAX_PANELS
    ):
        raise ValueError("Malformed matrix PNG geometry")
    roots = {}
    for grid in grids:
        if not isinstance(grid, dict) or not isinstance(grid.get("panel_id"), str):
            raise TypeError("Matrix PNG geometry is missing a panel binding")
        root = nodes.get(grid["panel_id"], {})
        x_edges, y_edges, clip = grid.get("x_edges"), grid.get("y_edges"), grid.get("clip")
        if (
            root.get("operation") != "matrix_panel"
            or not all(
                isinstance(axis, list) and ordered_edges(axis) for axis in (x_edges, y_edges)
            )
            or root["metadata"].get("shape") != [len(y_edges) - 1, len(x_edges) - 1]
            or len(root["inputs"]) != (len(y_edges) - 1) * (len(x_edges) - 1)
            or not isinstance(clip, list)
            or len(clip) != 4
            or not all(map(finite_number, clip))
        ):
            raise ValueError("Matrix PNG grid does not match its panel calculation")
        left, top, right, bottom = clip
        x_low, x_high = sorted((x_edges[0], x_edges[-1]))
        y_low, y_high = sorted((y_edges[0], y_edges[-1]))
        if not (
            max(0, x_low) <= left < right <= min(image["width"], x_high)
            and max(0, y_low) <= top < bottom <= min(image["height"], y_high)
        ):
            raise ValueError("Matrix PNG grid clip is outside its rendered bounds")
        roots[grid["panel_id"]] = None
    if node["inputs"] != list(roots):
        raise ValueError("Matrix PNG geometry does not match its calculation inputs")
    return info


def resolve_matrix_cell(info, nodes, x, y):
    if not finite_number(x) or not finite_number(y):
        raise ValueError("Matrix PNG coordinates must be finite numbers")
    if info["gaps"]:
        raise ValueError("Matrix PNG geometry is incomplete. " + info["gaps"][0])
    matches = set()
    for grid in info["grids"]:
        left, top, right, bottom = grid["clip"]
        if not (left <= x < right and top <= y < bottom):
            continue
        row = cell_index(grid["y_edges"], y)
        column = cell_index(grid["x_edges"], x)
        if row is None or column is None:
            raise ValueError("Matrix PNG geometry is inconsistent at the selected position")
        root = nodes[grid["panel_id"]]
        cell_id = root["inputs"][row * (len(grid["x_edges"]) - 1) + column]
        cell = nodes[cell_id]
        if cell.get("operation") != "matrix_cell" or (
            cell["metadata"].get("row"),
            cell["metadata"].get("column"),
        ) != (row, column):
            raise ValueError("Matrix PNG position does not match its cell calculation")
        matches.add(cell_id)
    if len(matches) > 1:
        raise ValueError("More than one matrix cell occupies that PNG position")
    return next(iter(matches), None)


def _finite_interval(target):
    value = target.get("value")
    return target.get("operation") == "summary_interval" and (
        isinstance(value, list) and len(value) == 2 and all(map(finite_number, value))
    )


def _valid_clip(clip, image):
    if not isinstance(clip, list) or len(clip) != 4 or not all(map(finite_number, clip)):
        return False
    left, top, right, bottom = clip
    return 0 <= left < right <= image["width"] and 0 <= top < bottom <= image["height"]


def _finite_points(points, count):
    return (
        isinstance(points, list)
        and len(points) == count
        and all(
            isinstance(point, list) and len(point) == 2 and all(map(finite_number, point))
            for point in points
        )
    )


def _validate_band_strip(strip, nodes, image):
    if not isinstance(strip, dict) or not isinstance(strip.get("node_id"), str):
        raise TypeError("A band strip has no calculation identity")
    span = nodes.get(strip["node_id"], {})
    refs, points = strip.get("interval_ids"), strip.get("endpoints")
    if (
        span.get("operation") != "summary_band_span"
        or not isinstance(refs, list)
        or len(refs) != 2
        or not all(isinstance(identity, str) for identity in refs)
        or refs[0] == refs[1]
        or span["inputs"] != refs
        or not all(_finite_interval(nodes.get(identity, {})) for identity in refs)
        or not _finite_points(points, 4)
        or not _valid_clip(strip.get("clip"), image)
    ):
        raise ValueError("Band geometry does not match two calculated intervals")
    if points[0][0] != points[1][0] or points[2][0] != points[3][0] or points[0][0] == points[2][0]:
        raise ValueError("Band geometry does not have distinct endpoint positions")
    if span["metadata"].get("endpoint_keys") != [
        nodes[identity]["metadata"]["keys"] for identity in refs
    ]:
        raise ValueError("Band endpoint keys do not match the interval calculations")


def validate_summary_interval_geometry(node, nodes):
    if node.get("operation") != "summary_interval_png_geometry":
        raise ValueError("Unknown summary interval PNG geometry root")
    info = node.get("metadata", {})
    image = info.get("image", {})
    strokes = info.get("strokes")
    bands = info.get("bands", [])
    if (
        info.get("coordinates") != "pixels_top_left"
        or not isinstance(image, dict)
        or not all(
            type(image.get(key)) is int and image[key] > 0 for key in ("width", "height", "bytes")
        )
        or not isinstance(strokes, list)
        or not isinstance(bands, list)
        or not 0 < len(strokes) + len(bands) <= MAX_INTERVAL_STROKES
        or type(node["value"]) is not int
        or len(strokes) + len(bands) != node["value"]
    ):
        raise ValueError("Malformed summary interval PNG geometry")
    inputs = {}
    for stroke in strokes:
        if not isinstance(stroke, dict) or not isinstance(stroke.get("node_id"), str):
            raise TypeError("An error-bar stroke has no calculation identity")
        identity = stroke["node_id"]
        endpoints, clip, radius = (
            stroke.get("endpoints"),
            stroke.get("clip"),
            stroke.get("radius"),
        )
        target = nodes.get(identity, {})
        if (
            not _finite_interval(target)
            or stroke.get("role") not in ("stem", "cap")
            or not _finite_points(endpoints, 2)
            or not finite_number(radius)
            or not 0 < radius <= 128
            or not _valid_clip(clip, image)
        ):
            raise ValueError("Error-bar stroke does not match a finite interval")
        inputs[identity] = None
    for strip in bands:
        _validate_band_strip(strip, nodes, image)
        inputs[strip["node_id"]] = None
    if node["inputs"] != list(inputs):
        raise ValueError("Error-bar strokes do not match their calculation inputs")
    return info


def _pick_band(strip, x, y, tolerance):
    left, top, right, bottom = strip["clip"]
    if not (left <= x < right and top <= y < bottom):
        return ()
    (start, low_a), (_, high_a), (end, low_b), (_, high_b) = strip["endpoints"]
    first, last = sorted((start, end))
    if x < first - tolerance or x > last + tolerance:
        return ()
    ratio = min(1, max(0, (x - start) / (end - start)))
    y1, y2 = sorted((low_a + ratio * (low_b - low_a), high_a + ratio * (high_b - high_a)))
    if not y1 <= y <= y2:
        return ()
    endpoints = [
        identity
        for position, identity in zip((start, end), strip["interval_ids"], strict=True)
        if abs(x - position) <= tolerance
    ]
    return endpoints or [strip["node_id"]]


def resolve_summary_interval(info, x, y, *, tolerance=2):
    """Find the unique visible interval stroke near a natural PNG coordinate."""
    if not finite_number(x) or not finite_number(y):
        raise ValueError("Interval PNG coordinates must be finite numbers")
    if not finite_number(tolerance) or not 0 <= tolerance <= 64:
        raise ValueError("Interval PNG pick tolerance must be between 0 and 64 pixels")
    matches = set()
    for stroke in info["strokes"]:
        left, top, right, bottom = stroke["clip"]
        if not (left <= x < right and top <= y < bottom):
            continue
        distance = _distance_to_segment(stroke["endpoints"], x, y)
        if distance <= stroke["radius"] + tolerance:
            matches.add(stroke["node_id"])
    for strip in info.get("bands", ()):
        matches.update(_pick_band(strip, x, y, tolerance))
    if len(matches) > 1:
        raise ValueError("More than one observation interval occupies that PNG position")
    return next(iter(matches), None)


def _finite_estimate(node):
    return node.get("operation") == "summary_estimate" and finite_number(node.get("value"))


def _valid_line_span(mark, span, nodes, image):
    endpoints = mark.get("endpoint_ids")
    points = mark.get("endpoints")
    radius = mark.get("radius")
    return (
        span.get("operation") == "summary_line_span"
        and span["value"] is None
        and isinstance(endpoints, list)
        and len(endpoints) == 2
        and all(isinstance(identity, str) for identity in endpoints)
        and endpoints[0] != endpoints[1]
        and span["inputs"] == endpoints
        and all(_finite_estimate(nodes.get(identity, {})) for identity in endpoints)
        and span["metadata"].get("endpoint_keys")
        == [nodes[identity]["metadata"]["keys"] for identity in endpoints]
        and _finite_points(points, 2)
        and points[0] != points[1]
        and finite_number(radius)
        and 0 < radius <= 128
        and _valid_clip(mark.get("clip"), image)
    )


def validate_summary_estimate_geometry(node, nodes):
    if node.get("operation") != "summary_estimate_png_geometry":
        raise ValueError("Unknown summary estimate PNG geometry root")
    info = node["metadata"]
    image, marks = info.get("image"), info.get("estimates")
    coverage = info.get("coverage", [])
    if (
        info.get("coordinates") != "pixels_top_left"
        or not isinstance(image, dict)
        or not all(
            type(image.get(key)) is int and image[key] > 0 for key in ("width", "height", "bytes")
        )
        or not isinstance(marks, list)
        or not 0 < len(marks) <= MAX_ESTIMATE_MARKS
        or type(node["value"]) is not int
        or len(marks) != node["value"]
        or not isinstance(coverage, list)
        or len(coverage) > 10
        or not all(isinstance(gap, str) and 0 < len(gap) <= 250 for gap in coverage)
    ):
        raise ValueError("Malformed summary estimate PNG geometry")
    inputs = {}
    for mark in marks:
        if not isinstance(mark, dict) or not isinstance(mark.get("node_id"), str):
            raise TypeError("An estimate mark has no calculation identity")
        identity = mark["node_id"]
        target = nodes.get(identity, {})
        kind = mark.get("kind")
        if kind == "segment":
            if not _valid_line_span(mark, target, nodes, image):
                raise ValueError("Line connection does not match its two finite endpoint estimates")
        elif not _finite_estimate(target):
            raise ValueError("Estimate geometry does not match a finite summary estimate")
        elif kind == "bar":
            if not _valid_clip(mark.get("bounds"), image):
                raise ValueError("An estimate bar has invalid PNG bounds")
        elif kind in ("dot", "vertex"):
            radius = mark.get("radius")
            if (
                not _finite_points([mark.get("center")], 1)
                or not finite_number(radius)
                or not 0 < radius <= 128
                or not _valid_clip(mark.get("clip"), image)
            ):
                raise ValueError("An estimate point has invalid PNG geometry")
        else:
            raise ValueError("Unknown summary estimate mark")
        inputs[identity] = None
    if list(inputs) != node["inputs"]:
        raise ValueError("Estimate marks do not match their calculation inputs")
    return info


def _distance_to_segment(points, x, y):
    (x0, y0), (x1, y1) = points
    dx, dy = x1 - x0, y1 - y0
    length_squared = dx * dx + dy * dy
    fraction = (
        min(1, max(0, ((x - x0) * dx + (y - y0) * dy) / length_squared)) if length_squared else 0
    )
    return math.hypot(x - (x0 + fraction * dx), y - (y0 + fraction * dy))


def resolve_summary_estimate(info, x, y, *, tolerance=0):
    """Pick a bar, center or line connection in natural PNG coordinates."""
    if not finite_number(x) or not finite_number(y):
        raise ValueError("Estimate PNG coordinates must be finite numbers")
    if not finite_number(tolerance) or not 0 <= tolerance <= 64:
        raise ValueError("Estimate PNG pick tolerance must be between 0 and 64 pixels")
    matches, spans = set(), {}
    for mark in info["estimates"]:
        kind = mark["kind"]
        left, top, right, bottom = mark["bounds"] if kind == "bar" else mark["clip"]
        if not (left <= x < right and top <= y < bottom):
            continue
        if kind == "segment":
            if _distance_to_segment(mark["endpoints"], x, y) <= mark["radius"] + tolerance:
                spans[mark["node_id"]] = mark["endpoint_ids"]
        elif kind == "bar":
            matches.add(mark["node_id"])
        else:
            cx, cy = mark["center"]
            if math.hypot(x - cx, y - cy) <= mark["radius"] + tolerance:
                matches.add(mark["node_id"])
    # A hit on a vertex selects that estimate rather than its adjacent connections.
    connections = {span for span, endpoints in spans.items() if matches.isdisjoint(endpoints)}
    candidates = matches | connections
    if len(candidates) > 1:
        raise ValueError("More than one observation estimate occupies that PNG position")
    return next(iter(candidates), None)
