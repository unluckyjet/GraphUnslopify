"""Use actual cropped PNGs to check matrix placement and ownership refusals."""

from __future__ import annotations

import matplotlib.pyplot as plt
import pytest
from matplotlib.patches import Circle
from PIL import Image

from graphunslopify.observation_geometry import (
    cell_index,
    resolve_matrix_cell,
    save_matrix_png,
    validate_matrix_geometry,
)


def test_reversed_and_clipped_matrix_edges_own_actual_png_pixels(tmp_path):
    figure, axes = plt.subplots(figsize=(4, 2))
    try:
        artist = axes.imshow(
            [[0, 1, 2], [3, 4, 5]],
            extent=(0, 12, 0, 6),
            interpolation="nearest",
            origin="lower",
            aspect="auto",
        )
        artist._graphunslopify_matrix_panel_id = "panel"
        axes.set_xlim(9, 2)
        axes.set_ylim(1, 5)
        png = tmp_path / "clipped.png"
        identity, (grid,), gaps = save_matrix_png(
            figure, png, metadata={}, dpi=183, run_id="a" * 32
        )
        assert not gaps
        assert grid["panel_id"] == "panel"
        left, top, right, bottom = grid["clip"]
        x_edges, y_edges = grid["x_edges"], grid["y_edges"]
        assert x_edges[-1] < left < right < x_edges[0]
        assert y_edges[-1] < top < bottom < y_edges[0]
        with Image.open(png) as saved:
            assert saved.size == (identity["width"], identity["height"])
            pixels = saved.convert("RGB")
            for row in range(2):
                for column in range(3):
                    x_lo, x_hi = sorted(x_edges[column : column + 2])
                    y_lo, y_hi = sorted(y_edges[row : row + 2])
                    x = int((max(x_lo, left) + min(x_hi, right)) / 2)
                    y = int((max(y_lo, top) + min(y_hi, bottom)) / 2)
                    assert cell_index(x_edges, x) == column
                    assert cell_index(y_edges, y) == row
                    color = tuple(
                        int(value * 255) for value in artist.cmap(artist.norm(row * 3 + column))[:3]
                    )
                    assert pixels.getpixel((x, y)) == pytest.approx(color, abs=1)
        assert [cell_index([6, 4, 2], x) for x in (1, 2, 3, 4, 5, 6)] == [None, 1, 1, 0, 0, None]
    finally:
        plt.close(figure)


def test_overlapping_matrix_images_and_unknown_clips_refuse_pixel_lookup(tmp_path):
    figure, axes = plt.subplots()
    try:
        artists = [axes.imshow([[v]], aspect="auto") for v in (1, 2)]
        nodes = {}
        for index, artist in enumerate(artists):
            panel, cell = f"panel-{index}", f"cell-{index}"
            artist._graphunslopify_matrix_panel_id = panel
            nodes[panel] = {
                "operation": "matrix_panel",
                "metadata": {"shape": [1, 1]},
                "inputs": [cell],
            }
            nodes[cell] = {"operation": "matrix_cell", "metadata": {"row": 0, "column": 0}}
        png = tmp_path / "overlap.png"
        identity, grids, gaps = save_matrix_png(figure, png, metadata={}, dpi=96, run_id="a" * 32)
        assert not gaps and len(grids) == 2
        node = {
            "operation": "matrix_png_geometry",
            "inputs": ["panel-0", "panel-1"],
            "value": 2,
            "metadata": {
                "coordinates": "pixels_top_left",
                "image": identity,
                "grids": grids,
                "gaps": gaps,
            },
        }
        info = validate_matrix_geometry(node, nodes)
        x, y = sum(grids[0]["x_edges"]) / 2, sum(grids[0]["y_edges"]) / 2
        with pytest.raises(ValueError, match="More than one matrix cell"):
            resolve_matrix_cell(info, nodes, x, y)
        assert resolve_matrix_cell(info, nodes, 0, 0) is None

        artists[0].set_clip_path(Circle((0, 0), 0.25, transform=axes.transData))
        _, grids, gaps = save_matrix_png(figure, png, metadata={}, dpi=96, run_id="b" * 32)
        assert len(grids) == 1 and gaps == ["A matrix has a nonrectangular clip"]
        with pytest.raises(ValueError, match="nonrectangular clip"):
            resolve_matrix_cell({**info, "grids": grids, "gaps": gaps}, nodes, x, y)
    finally:
        plt.close(figure)
