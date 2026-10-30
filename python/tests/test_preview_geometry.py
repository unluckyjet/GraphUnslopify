"""Actual final-raster coordinates, independently checked against pixel ink."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys

import matplotlib
import pytest

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image, ImageChops

from graphunslopify.preview import PreviewState
from graphunslopify.preview_geometry import TARGET_ATTRIBUTE, capture_png_geometry


def mark(artist, path, role="title"):
    setattr(artist, TARGET_ATTRIBUTE, {"path": path, "role": role, "editable": path is not None})
    return artist


@pytest.mark.parametrize("dpi", [73, 144, 300])
def test_tight_crop_coordinates_enclose_actual_raster_ink_at_export_dpi(tmp_path, dpi):
    fig = plt.figure(figsize=(4, 3))
    try:
        mark(fig.text(0.3, 0.7, "WMW", fontsize=20), ["title"])
        image, record = tmp_path / "figure.png", tmp_path / "geometry.json"
        with capture_png_geometry(fig, image, record):
            fig.savefig(image, dpi=dpi, bbox_inches="tight", pad_inches=0.1)
        geometry = json.loads(record.read_text())
        assert geometry["available"]
        assert geometry["image"]["sha256"] == hashlib.sha256(image.read_bytes()).hexdigest()
        with Image.open(image) as raster:
            assert raster.size == (geometry["image"]["width"], geometry["image"]["height"])
            ink = (
                ImageChops.invert(raster.convert("L"))
                .point(lambda value: 255 if value > 50 else 0)
                .getbbox()
            )
        x, y, width, height = geometry["targets"][0]["bounds"]
        assert x == pytest.approx(dpi * 0.1, abs=1)
        assert y == pytest.approx(dpi * 0.1, abs=1)
        assert ink is not None
        left, top, right, bottom = ink
        assert x - 1 <= left < right <= x + width + 1
        assert y - 1 <= top < bottom <= y + height + 1
        assert (right - left) * (bottom - top) > width * height * 0.5
    finally:
        plt.close(fig)


def test_annotation_target_excludes_arrow_and_capture_does_not_change_pixels(tmp_path):
    fig, axes = plt.subplots(figsize=(4, 3))
    try:
        note = axes.annotate("Peak", (0.1, 0.1), xytext=(0.8, 0.8), arrowprops={"arrowstyle": "->"})
        mark(note, ["annotate", 0, "text"], "annotation")
        mark(axes.set_ylabel("Vertical measure"), ["y", "label"], "axis_label")
        mark(axes.text(0.3, 0.3, "Hidden", visible=False), ["title"])
        first, second, record = (
            tmp_path / name for name in ["first.png", "second.png", "geometry.json"]
        )
        fig.savefig(first, dpi=150, bbox_inches="tight")
        callbacks = len(fig.canvas.callbacks.callbacks.get("draw_event", {}))
        with capture_png_geometry(fig, second, record):
            fig.savefig(second, dpi=150, bbox_inches="tight")
        assert len(fig.canvas.callbacks.callbacks.get("draw_event", {})) == callbacks
        with Image.open(first) as before, Image.open(second) as after:
            assert before.convert("RGBA").tobytes() == after.convert("RGBA").tobytes()
        targets = json.loads(record.read_text())["targets"]
        assert len(targets) == 2
        annotation = next(target for target in targets if target["role"] == "annotation")
        assert annotation["bounds"][2] < 80  # The arrow spans several hundred pixels.
        vertical = next(target for target in targets if target["role"] == "axis_label")
        assert vertical["bounds"][3] > vertical["bounds"][2] * 3
    finally:
        plt.close(fig)


def test_missing_draw_is_unavailable_and_failed_export_keeps_original_error(tmp_path):
    fig = plt.figure()
    try:
        record = tmp_path / "geometry.json"
        with capture_png_geometry(fig, tmp_path / "missing.png", record):
            pass
        assert not json.loads(record.read_text())["available"]
        assert "No final PNG draw" in json.loads(record.read_text())["error"]
        callbacks = len(fig.canvas.callbacks.callbacks.get("draw_event", {}))
        with (
            pytest.raises(RuntimeError, match="original export failure"),
            capture_png_geometry(fig, tmp_path / "missing.png", record),
        ):
            raise RuntimeError("original export failure")
        assert len(fig.canvas.callbacks.callbacks.get("draw_event", {})) == callbacks
    finally:
        plt.close(fig)


def test_actual_generated_preview_map_is_bound_to_original_png_and_semantic_paths(tmp_path):
    state = PreviewState(tmp_path, 1024 * 1024)
    uploaded = state.upload("experiment.csv", b"epoch,score\n1,7\n2,11\n3,13\n")
    result = state.render(
        {
            "client": "geometry",
            "generation": 1,
            "data_id": uploaded["id"],
            "spec": {
                "kind": "line",
                "title": "Observed score",
                "x": {"field": "epoch", "label": "Step"},
                "y": {"field": "score", "label": "Result"},
                "legend": {"show": False},
                "annotate": [{"at": "last", "text": "Last observation"}],
                "output": {"stem": "figure", "formats": ["png"]},
            },
        }
    )
    assert result["report"]["status"] == "passed"
    geometry = result["edit_map"]
    assert geometry["available"]
    assert geometry["run_id"] == result["run_id"]
    assert geometry["spec_hash"] == result["report"]["spec_hash"]
    png = next(item for item in result["report"]["outputs"] if item["format"] == "png")
    assert geometry["image"]["sha256"] == png["sha256"]
    paths = {tuple(target["path"]): target["text"] for target in geometry["targets"]}
    assert paths[("title",)] == "Observed score"
    assert paths[("x", "label")] == "Step"
    assert paths[("y", "label")] == "Result"
    assert paths[("annotate", 0, "text")] == "Last observation"


def test_horizontal_forest_keeps_semantic_axis_paths_without_guessing_from_text(tmp_path):
    state = PreviewState(tmp_path, 1024 * 1024)
    data = state.upload("forest.csv", b"condition,score\nA,7\nA,8\nA,9\nB,11\nB,12\nB,13\n")
    result = state.render(
        {
            "client": "forest",
            "generation": 1,
            "data_id": data["id"],
            "spec": {
                "kind": "forest",
                "x": {"field": "condition", "label": "Condition"},
                "y": {"field": "score", "label": "Score"},
                "uncertainty": {"kind": "range"},
                "legend": {"show": False},
                "output": {"formats": ["png"]},
            },
        }
    )
    assert result["report"]["ok"]
    targets = {tuple(item["path"]): item for item in result["edit_map"]["targets"]}
    category, measure = targets[("x", "label")], targets[("y", "label")]
    assert category["source"] == "condition" and measure["source"] == "score"
    assert category["bounds"][3] > category["bounds"][2]
    assert measure["bounds"][2] > measure["bounds"][3]


def test_legend_entries_keep_original_identity_and_derived_labels_stay_read_only(tmp_path):
    state = PreviewState(tmp_path, 1024 * 1024)
    data = state.upload(
        "series.csv", b"epoch,score,loss,model\n1,7,4,base\n2,11,2,base\n1,8,3,ours\n2,13,1,ours\n"
    )
    result = state.render(
        {
            "client": "panels",
            "generation": 1,
            "data_id": data["id"],
            "spec": {
                "kind": "line",
                "group": "model",
                "x": {"field": "epoch", "label": "Epoch"},
                "y": {"field": "score", "label": "Score"},
                "repeat": {"fields": ["score", "loss"]},
                "legend": {"title": "Series identity"},
                "output": {"formats": ["png"]},
            },
        }
    )
    assert result["report"]["ok"]
    targets = result["edit_map"]["targets"]
    legends = [item for item in targets if item["role"] == "legend_entry"]
    assert {item["source"] for item in legends} == {"base", "ours"}
    assert all(item["editable"] and item["path"][:2] == ["legend", "labels"] for item in legends)
    derived = [item for item in targets if item["role"] == "derived_axis_label"]
    assert {item["source"] for item in derived} == {"score", "loss"}
    assert all(not item["editable"] and item["path"] is None for item in derived)
    title = next(item for item in targets if item["role"] == "legend_title")
    assert title["path"] == ["legend", "title"] and title["editable"]


def test_geometry_write_failure_does_not_change_the_export(tmp_path, capsys):
    fig = plt.figure()
    try:
        mark(fig.text(0.2, 0.2, "Observed"), ["title"])
        png = tmp_path / "original.png"
        with capture_png_geometry(fig, png, tmp_path):  # A directory cannot be the JSON file.
            fig.savefig(png)
        assert png.is_file()
        assert "Preview text geometry unavailable" in capsys.readouterr().err
    finally:
        plt.close(fig)


def test_axis_off_labels_with_visible_artist_flags_are_not_real_click_targets(tmp_path):
    fig, axes = plt.subplots()
    try:
        mark(axes.set_xlabel("Ghost label"), ["x", "label"], "axis_label")
        axes.xaxis.set_label_coords(0.5, 0.5)
        axes.set_axis_off()
        assert axes.xaxis.label.get_visible() and axes.xaxis.get_visible()
        png, record = tmp_path / "blank.png", tmp_path / "geometry.json"
        with capture_png_geometry(fig, png, record):
            fig.savefig(png, bbox_inches="tight")
        with Image.open(png) as raster:
            assert ImageChops.invert(raster.convert("L")).getbbox() is None
        assert json.loads(record.read_text())["targets"] == []
    finally:
        plt.close(fig)


@pytest.mark.parametrize("stem", ["graphunslopify", "json", "inspect", "matplotlib"])
def test_output_filename_cannot_shadow_preview_or_standalone_dependencies(tmp_path, stem):
    state = PreviewState(tmp_path, 1024 * 1024)
    data = state.upload("experiment.csv", b"epoch,score\n1,7\n2,11\n3,13\n")
    result = state.render(
        {
            "client": "filename",
            "generation": 1,
            "data_id": data["id"],
            "spec": {
                "kind": "line",
                "x": {"field": "epoch", "label": "Epoch"},
                "y": {"field": "score", "label": "Score"},
                "legend": {"show": False},
                "output": {"stem": stem, "formats": ["png"]},
            },
        }
    )
    assert result["report"]["ok"] and result["edit_map"]["available"]
    folder = state.runs[result["run_id"]]["folder"]
    completed = subprocess.run(
        [sys.executable, str(folder / f"{stem}.py"), "--strict", "--json"],
        cwd=folder,
        env={**os.environ, "MPLBACKEND": "Agg"},
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["ok"]
