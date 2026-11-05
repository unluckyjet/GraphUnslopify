"""Capture matrix-cell geometry from the draw that writes the owned PNG."""

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


def save_matrix_png(figure, path, *, metadata, dpi, run_id):
    """Save once and measure the final draw in the actual tight PNG coordinate system."""
    snapshot = {}

    def drawn(_event):
        snapshot.clear()
        snapshot.update(origin=figure.bbox.p0.tolist(), grids=[], gaps=[])
        try:
            for index, image in enumerate(_visible_matrix_images(figure)):
                if index >= MAX_PANELS:
                    snapshot["gaps"].append("Matrix geometry exceeds the panel capacity")
                    break
                try:
                    snapshot["grids"].append(_grid(image))
                except ValueError as problem:
                    snapshot["gaps"].append(str(problem))
        except (AttributeError, TypeError, RuntimeError) as problem:
            snapshot["gaps"].append(f"Could not measure a matrix draw ({type(problem).__name__})")

    canvas = figure.canvas
    callback = canvas.mpl_connect("draw_event", drawn)
    try:
        figure.savefig(path, bbox_inches="tight", metadata={**metadata, RUN_STAMP: run_id}, dpi=dpi)
    finally:
        canvas.mpl_disconnect(callback)

    try:
        identity = inspect_png(path, run_id)
    except (OSError, ValueError) as problem:
        return None, [], [f"Could not verify the matrix PNG ({type(problem).__name__})"]
    width, height = identity["width"], identity["height"]
    if not snapshot:
        return identity, [], ["No final matrix PNG draw was observed"]
    origin_x, origin_y = snapshot["origin"]
    grids = []
    for grid in snapshot["grids"]:
        left, bottom, right, top = grid["clip"]
        left, right = max(0, left - origin_x), min(width, right - origin_x)
        top, bottom = max(0, height - top + origin_y), min(height, height - bottom + origin_y)
        if left < right and top < bottom:
            grids.append(
                {
                    "panel_id": grid["panel_id"],
                    "x_edges": [x - origin_x for x in grid["x_edges"]],
                    "y_edges": [height - y + origin_y for y in grid["y_edges"]],
                    "clip": [left, top, right, bottom],
                }
            )
    return identity, grids, sorted(set(snapshot["gaps"]))


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
