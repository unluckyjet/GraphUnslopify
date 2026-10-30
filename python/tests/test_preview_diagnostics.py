"""Measured diagnostics belong to actual findings and the final cropped PNG."""

from __future__ import annotations

import copy
import gc
import hashlib
import json
import weakref
from dataclasses import asdict

import matplotlib.pyplot as plt
import numpy as np
import pytest
from PIL import Image

from graphunslopify import Finding, inspect_figure
from graphunslopify.preview import PreviewState
from graphunslopify.preview_diagnostics import DiagnosticSnapshot, bind_diagnostic_map
from graphunslopify.preview_geometry import capture_png_geometry


@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close("all")


def capture(tmp_path, figure, dpi=144):
    before, png = tmp_path / "before.png", tmp_path / "figure.png"
    figure.savefig(before, dpi=dpi, bbox_inches="tight")
    original = inspect_figure(figure, export_paths=[before])
    snapshot = DiagnosticSnapshot()
    with capture_png_geometry(figure, png, tmp_path / "edit.json", diagnostics=snapshot):
        figure.savefig(png, dpi=dpi, bbox_inches="tight")
    report = inspect_figure(figure, export_paths=[png])
    assert [asdict(f) for f in original.findings] == [asdict(f) for f in report.findings]
    assert all(set(asdict(f)) == {"severity", "code", "message"} for f in report.findings)
    with Image.open(before) as a, Image.open(png) as b:
        assert a.size == b.size and a.convert("RGBA").tobytes() == b.convert("RGBA").tobytes()
    candidate = snapshot.project(figure, report)
    raw = {"spec_hash": "owned-spec", "findings": [asdict(f) for f in report.findings]}
    exported = {"sha256": hashlib.sha256(png.read_bytes()).hexdigest()}
    bound = bind_diagnostic_map(candidate, png, exported, raw, "owned-run")
    assert bound["available"], bound.get("error", bound)
    assert bound["run_id"] == "owned-run" and bound["spec_hash"] == "owned-spec"
    assert bound["image"]["sha256"] == exported["sha256"]
    assert "_spatial_sources" not in json.dumps(bound)
    return snapshot, report, candidate, raw, bound


def targets(bound, raw, code):
    return [t for t in bound["targets"] if raw["findings"][t["finding_index"]]["code"] == code]


@pytest.mark.parametrize("dpi", [73, 144, 300])
def test_small_text_target_matches_actual_tight_crop_ink(tmp_path, dpi):
    fig = plt.figure(figsize=(4, 3))
    fig.text(-0.15, 0.7, "WMW", fontsize=3)
    _, _, _, raw, bound = capture(tmp_path, fig, dpi)
    found = targets(bound, raw, "text_too_small")
    assert len(found) == 1
    with Image.open(tmp_path / "figure.png") as image:
        import PIL.ImageChops

        rgb = image.convert("RGB")
        ink = PIL.ImageChops.difference(rgb, Image.new("RGB", rgb.size, "white")).getbbox()
    assert ink is not None
    x, y, w, h = found[0]["bounds"]
    assert x - 1 <= ink[0] < ink[2] <= x + w + 1
    assert y - 1 <= ink[1] < ink[3] <= y + h + 1


@pytest.mark.parametrize("kind", ["ticks", "labels", "legend"])
def test_real_collision_sources_have_actual_regions(tmp_path, kind):
    fig, ax = plt.subplots(figsize=(4, 3))
    if kind == "ticks":
        ax.set_xlim(0, 1)
        ax.set_xticks([0.4, 0.41], ["Long left label", "Long right label"])
        code, minimum = "tick_labels_collide", 2
    elif kind == "labels":
        ax.text(0.5, 0.5, "First label", fontsize=20)
        ax.text(0.51, 0.5, "Second label", fontsize=20)
        code, minimum = "labels_collide", 2
    else:
        ax.plot([0, 0.5, 1], [0, 0.5, 1], label="Measured")
        ax.legend(loc="center")
        code, minimum = "legend_covers_data", 1
    _, _, _, raw, bound = capture(tmp_path, fig)
    assert len(targets(bound, raw, code)) >= minimum


@pytest.mark.parametrize("orientation", ["vertical", "horizontal"])
@pytest.mark.parametrize("inverted", [False, True])
def test_clipped_interval_target_is_the_actual_visible_stem(tmp_path, orientation, inverted):
    fig, ax = plt.subplots()
    if orientation == "vertical":
        ax.bar([0], [2], yerr=[[1], [7]], ecolor="red", capsize=0)
        ax.set_ylim(*(5, 0) if inverted else (0, 5))
    else:
        ax.barh([0], [2], xerr=[[1], [7]], ecolor="red", capsize=0)
        ax.set_xlim(*(5, 0) if inverted else (0, 5))
    _, _, _, raw, bound = capture(tmp_path, fig)
    found = targets(bound, raw, "bar_interval_clipped")
    assert len(found) == 1 and found[0]["kind"] == "bar_interval"
    _, _, width, height = found[0]["bounds"]
    assert (height > width * 5) if orientation == "vertical" else (width > height * 5)
    with Image.open(tmp_path / "figure.png") as image:
        rgb = np.asarray(image.convert("RGB"))
    red = np.argwhere((rgb[:, :, 0] > 180) & (rgb[:, :, 1] < 100) & (rgb[:, :, 2] < 100))
    assert len(red)
    x, y, width, height = found[0]["bounds"]
    assert x - 1 <= red[:, 1].min() <= red[:, 1].max() < x + width + 1
    assert y - 1 <= red[:, 0].min() <= red[:, 0].max() < y + height + 1


@pytest.mark.parametrize("orientation", ["vertical", "horizontal"])
def test_clipped_bar_body_has_its_own_region(tmp_path, orientation):
    fig, ax = plt.subplots()
    if orientation == "vertical":
        ax.bar([0], [9])
        ax.set_ylim(0, 5)
    else:
        ax.barh([0], [9])
        ax.set_xlim(0, 5)
    _, _, _, raw, bound = capture(tmp_path, fig)
    assert len(targets(bound, raw, "bar_mark_clipped")) == 1


def tiny(tmp_path):
    fig = plt.figure()
    fig.text(0.5, 0.5, "Tiny", fontsize=2)
    return fig, capture(tmp_path, fig)


@pytest.mark.parametrize(
    "mutation",
    [
        "version",
        "boolean_version",
        "coordinates",
        "digest",
        "dimensions",
        "identity",
        "primitive",
        "nan",
        "negative",
        "zero",
        "outside",
        "boolean_bound",
    ],
)
def test_malformed_or_stale_geometry_cannot_create_targets(tmp_path, mutation):
    _, (_, _, candidate, raw, _) = tiny(tmp_path)
    candidate = copy.deepcopy(candidate)
    if mutation == "version":
        candidate["schema_version"] = 999
    elif mutation == "boolean_version":
        candidate["schema_version"] = True
    elif mutation == "coordinates":
        candidate["coordinates"] = "canvas_before_crop"
    elif mutation == "digest":
        candidate["image"]["sha256"] = "0" * 64
    elif mutation == "dimensions":
        candidate["image"]["width"] += 1
    elif mutation == "identity":
        candidate["findings"][0]["finding"]["message"] = "Invented finding"
    elif mutation == "primitive":
        candidate["findings"][0]["regions"][0]["kind"] = "imaginary"
    else:
        bounds = candidate["findings"][0]["regions"][0]["bounds"]
        if mutation == "nan":
            bounds[0] = float("nan")
        elif mutation == "negative":
            bounds[0] = -1
        elif mutation == "zero":
            bounds[2] = 0
        elif mutation == "outside":
            bounds[2] = candidate["image"]["width"] * 2
        else:
            bounds[0] = True
    bound = bind_diagnostic_map(
        candidate,
        tmp_path / "figure.png",
        {"sha256": hashlib.sha256((tmp_path / "figure.png").read_bytes()).hexdigest()},
        raw,
        "current-run",
    )
    assert not bound["available"] and bound["targets"] == [] and bound["unlocated"]


def test_unknown_checks_and_ambiguous_finding_identities_stay_unlocated(tmp_path):
    fig, (snapshot, report, candidate, raw, _) = tiny(tmp_path)
    unknown = Finding("warning", "future_check", "No measured source")
    report.findings.append(unknown)
    candidate = snapshot.project(fig, report)
    raw["findings"].append(asdict(unknown))
    exported = {"sha256": snapshot.image["sha256"]}
    bound = bind_diagnostic_map(candidate, tmp_path / "figure.png", exported, raw, "run")
    assert bound["available"] and any(item["finding_index"] == 1 for item in bound["unlocated"])
    raw["findings"].append(copy.deepcopy(raw["findings"][0]))
    ambiguous = bind_diagnostic_map(candidate, tmp_path / "figure.png", exported, raw, "run")
    assert not ambiguous["available"] and not ambiguous["targets"]


def test_missing_draw_wrong_figure_and_capacity_are_explicit(tmp_path, monkeypatch):
    fig, (snapshot, report, _, _, _) = tiny(tmp_path)
    assert not DiagnosticSnapshot().project(fig, report)["available"]
    other = plt.figure()
    assert not snapshot.project(other, report)["available"]
    monkeypatch.setattr("graphunslopify.preview_diagnostics.MAX_SOURCES", 0)
    limited = DiagnosticSnapshot()
    with capture_png_geometry(
        fig, tmp_path / "limited.png", tmp_path / "limited-edit.json", diagnostics=limited
    ):
        fig.savefig(tmp_path / "limited.png", bbox_inches="tight")
    result = limited.project(fig, report)
    assert result["available"] and result["truncated"] and not result["findings"][0]["regions"]


def test_report_and_snapshot_do_not_retain_a_closed_figure(tmp_path):
    fig = plt.figure()
    fig.text(0.5, 0.5, "Tiny", fontsize=2)
    snapshot, report, _, _, _ = capture(tmp_path, fig)
    reference = weakref.ref(fig)
    plt.close(fig)
    del fig
    gc.collect()
    assert reference() is None
    assert snapshot.boxes and report.findings
    assert set(asdict(report)) == {"findings", "measurements"}


def test_custom_clip_has_no_invented_text_location(tmp_path):
    from matplotlib.patches import Circle

    fig = plt.figure()
    text = fig.text(0.5, 0.5, "Tiny", fontsize=2, clip_on=True)
    text.set_clip_path(Circle((0.5, 0.5), 0.02, transform=fig.transFigure))
    _, _, _, raw, bound = capture(tmp_path, fig)
    assert any(item["code"] == "text_too_small" for item in raw["findings"])
    assert not targets(bound, raw, "text_too_small")
    assert bound["unlocated"]


def test_capture_failure_leaves_text_map_pixels_and_inspection_intact(tmp_path, monkeypatch):
    from graphunslopify.preview_geometry import TARGET_ATTRIBUTE

    fig = plt.figure()
    text = fig.text(0.5, 0.5, "Measured", fontsize=20)
    setattr(text, TARGET_ATTRIBUTE, {"path": ["title"], "role": "title", "editable": True})
    fig.savefig(tmp_path / "original.png", bbox_inches="tight")
    snapshot = DiagnosticSnapshot()

    def failure(*args):
        raise RuntimeError("Controlled optional capture failure")

    monkeypatch.setattr(snapshot, "capture", failure)
    with capture_png_geometry(
        fig, tmp_path / "figure.png", tmp_path / "edit.json", diagnostics=snapshot
    ):
        fig.savefig(tmp_path / "figure.png", bbox_inches="tight")
    assert json.loads((tmp_path / "edit.json").read_text())["available"]
    report = inspect_figure(fig, export_paths=[tmp_path / "figure.png"])
    assert report.ok
    assert not snapshot.project(fig, report)["available"]
    with Image.open(tmp_path / "original.png") as a, Image.open(tmp_path / "figure.png") as b:
        assert a.convert("RGBA").tobytes() == b.convert("RGBA").tobytes()


def test_same_pixel_image_with_different_bytes_cannot_reuse_old_geometry(tmp_path):
    _, (_, _, candidate, raw, _) = tiny(tmp_path)
    png = tmp_path / "figure.png"
    png.write_bytes(png.read_bytes() + b"changed provenance bytes")
    exported = {"sha256": hashlib.sha256(png.read_bytes()).hexdigest()}
    bound = bind_diagnostic_map(candidate, png, exported, raw, "new-run")
    assert not bound["available"] and not bound["targets"]


def test_missing_actual_png_is_explicitly_unavailable(tmp_path):
    fig, (snapshot, report, candidate, raw, _) = tiny(tmp_path)
    png = tmp_path / "figure.png"
    exported = {"sha256": snapshot.image["sha256"]}
    png.unlink()
    assert not bind_diagnostic_map(candidate, png, exported, raw, "run")["available"]
    snapshot.finish(png)
    assert not snapshot.project(fig, report)["available"]


@pytest.mark.parametrize("clipped", [False, True])
def test_actual_preview_response_binds_diagnostics_without_weakening_strict_status(
    tmp_path, clipped
):
    state = PreviewState(tmp_path, 1024 * 1024)
    data = state.upload("data.csv", b"category,value\nA,1\nA,2\nA,9\n")
    spec = {
        "kind": "bar",
        "x": {"field": "category", "label": "Category"},
        "y": {"field": "value", "label": "Value"},
        "aggregation": "mean",
        "uncertainty": {"kind": "range"},
        "legend": {"show": False},
        "output": {"formats": ["png"]},
    }
    if clipped:
        spec["y"]["limits"] = [0, 5]
    result = state.render(
        {"client": "diagnostics", "generation": 1, "data_id": data["id"], "spec": spec}
    )
    bound = result["diagnostic_map"]
    assert bound["available"] and bound["run_id"] == result["run_id"]
    assert bound["spec_hash"] == result["report"]["spec_hash"]
    assert result["report"]["status"] == ("failed" if clipped else "passed")
    if clipped:
        assert targets(bound, result["report"], "bar_interval_clipped")
    assert result["edit_map"]["available"]


def test_newer_generation_refuses_diagnostic_locations_from_completed_old_run(
    tmp_path, monkeypatch
):
    from graphunslopify import preview

    state = PreviewState(tmp_path, 1024 * 1024)
    data = state.upload("data.csv", b"x,value\n1,2\n2,3\n")
    original = preview._run

    def newer_generation(*args, **kwargs):
        completed = original(*args, **kwargs)
        with state.lock:
            state.generations["diagnostics"] = 2
        return completed

    monkeypatch.setattr(preview, "_run", newer_generation)
    result = state.render(
        {
            "client": "diagnostics",
            "generation": 1,
            "data_id": data["id"],
            "spec": {
                "kind": "line",
                "x": {"field": "x", "label": "X"},
                "y": {"field": "value", "label": "Value"},
                "legend": {"show": False},
                "output": {"formats": ["png"]},
            },
        }
    )
    assert result["stale"] and result["report"]["status"] == "passed"
    assert not result["diagnostic_map"]["available"] and not result["diagnostic_map"]["targets"]
    assert "stale" in result["diagnostic_map"]["error"]
