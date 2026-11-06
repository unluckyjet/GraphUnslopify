"""Physical placement from actual saved native figure exports."""

import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode

import pytest
from test_project_changes_http import request
from test_project_changes_http import server as server  # noqa: PLC0414

from graphunslopify.project import run_project
from graphunslopify.project_presentation import _layout


def test_saved_figure_presentation_preserves_aspect_and_audit_evidence(server):
    _, paper = server
    saved = run_project(paper, baseline=None)
    assert saved["exit_code"] == 0
    folder = Path(saved["directory"])
    initial = {p.relative_to(folder): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
    query = "/api/presentation?" + urlencode({"event": saved["id"], "figure": "training"})
    request(server, query, expected=403, token=False)
    view = request(server, query)
    assert view["event"] == saved["id"] and view["exit_code"] == 0
    output = next(
        f
        for f in saved["audit"]["figures"][0]["outputs"]
        if f["format"] == view["export"]["format"]
    )
    assert (
        view["export"]["sha256"]
        == hashlib.sha256(initial[Path("audit") / output["path"]]).hexdigest()
    )
    measure = view["export"]["measurement"]
    expected_ratio = measure["width_in"] / measure["height_in"]
    for key, frame in view["layouts"].items():
        left, top, width, height = frame["placed_mm"]
        x, y, slot_width, slot_height = frame["slot_mm"]
        assert left >= x and top >= y
        assert left + width <= x + slot_width + 1e-9 and top + height <= y + slot_height + 1e-9
        assert width / height == pytest.approx(expected_ratio)
        assert frame["scale"] == pytest.approx(width / (25.4 * measure["width_in"]))
        if key == "slide":
            assert frame["page_mm"][0] / frame["page_mm"][1] == pytest.approx(16 / 9)
        if view["export"]["format"] == "pdf":
            assert view["text"]["minimum_pt"] > 0
            assert frame["minimum_text_pt"] == pytest.approx(
                view["text"]["minimum_pt"] * frame["scale"]
            )
            assert frame["raster_dpi"] is None
        else:
            assert frame["minimum_text_pt"] is None
            assert frame["raster_dpi"][0] == pytest.approx(measure["pixels"][0] * 25.4 / width)
    assert view["layouts"]["single_column"]["placed_mm"][2] == 85
    assert view["layouts"]["double_column"]["placed_mm"][2] == 178
    assert {
        p.relative_to(folder): p.read_bytes() for p in folder.rglob("*") if p.is_file()
    } == initial


def test_height_limited_placement_keeps_uniform_scale():
    frame = _layout((338, 190), (20, 39, 298, 130), 0.5, None, None, (400, 800))
    assert frame["height_limited"] and frame["placed_mm"] == [136.5, 39, 65, 130]
    assert frame["scale"] is None and frame["minimum_text_pt"] is None
    assert frame["raster_dpi"][0] == pytest.approx(frame["raster_dpi"][1])


def test_png_only_preview_has_measured_resolution_without_assumed_font_sizes(server):
    _, paper = server
    spec = paper / "training.figure.json"
    figure = json.loads(spec.read_bytes())
    figure["output"]["formats"] = ["png"]
    spec.write_text(json.dumps(figure))
    saved = run_project(paper, baseline=None)
    assert saved["exit_code"] == 0
    query = "/api/presentation?" + urlencode({"event": saved["id"], "figure": "training"})
    view = request(server, query)
    assert view["export"]["format"] == "png" and view["text"] is None
    for frame in view["layouts"].values():
        assert frame["minimum_text_pt"] is None
        assert min(frame["raster_dpi"]) > 0
