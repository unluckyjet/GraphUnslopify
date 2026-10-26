"""Independent contrast references, actual cell artists, and inspector controls."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import subprocess
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from matplotlib import colors

from graphunslopify import inspect_figure, read_provenance
from graphunslopify.cell_colour import cell_text_contrast
from graphunslopify.transport import local_request


def luminance(rgb):
    channels = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb]
    return sum(a * b for a, b in zip(channels, [0.2126, 0.7152, 0.0722], strict=True))


def contrast(a, b):
    low, high = sorted([luminance(a), luminance(b)])
    return (high + 0.05) / (low + 0.05)


def generated(folder, **extra):
    spec = {
        "kind": "heatmap",
        "x": {"field": "column", "label": "Column"},
        "y": {"field": "row", "label": "Row"},
        "value": "value",
        "value_label": "Value",
        "annotate_cells": True,
        "data": {"path": str(folder / "data.csv")},
        "legend": {"show": False},
        "output": {"stem": "contrast", "formats": ["png", "svg"], "dpi": 150},
        **extra,
    }
    result = local_request("convert", spec)
    assert result.get("ok"), result
    path = folder / "contrast.py"
    path.write_text(result["code"], encoding="utf8")
    definition = importlib.util.spec_from_file_location("cell_reference", path)
    module = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(module)
    return module, path


def frame(values):
    return pd.DataFrame(
        [
            {"column": str(c), "row": str(r), "value": value}
            for r, row in enumerate(values)
            for c, value in enumerate(row)
        ]
    )


@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close("all")


@pytest.mark.parametrize(
    ("values", "diverging"),
    [
        ([[1, 2], [3, 4]], False),
        ([[-4, -3], [-2, -1]], False),
        ([[0, 0], [0, 0]], False),
        ([[0.001, 0.002], [0.003, 0.004]], False),
        ([[-3, 0], [1, 3]], True),
        ([[0, 0], [0, 0]], True),
        ([[1, np.nan], [np.nan, 4]], False),
    ],
)
def test_actual_heatmap_annotations_contrast_with_unchanged_values(tmp_path, values, diverging):
    module, _ = generated(tmp_path, diverging=diverging)
    _, ax = plt.subplots()
    module.draw_panel(ax, module.prepare(frame(values)))
    image = ax.images[0]
    np.testing.assert_allclose(
        image.get_array().filled(np.nan), values, rtol=0, atol=0, equal_nan=True
    )
    assert len(ax.texts) == int(np.isfinite(values).sum())
    for text in ax.texts:
        column, row = map(int, text.get_position())
        background = image.to_rgba(values[row][column])[:3]
        assert contrast(colors.to_rgb(text.get_color()), background) >= 4.5
        assert float(text.get_text()) == pytest.approx(values[row][column], rel=0, abs=1e-12)
    if diverging and not np.any(values):
        assert image.norm(0) == 0.5  # A constant zero grid must retain a neutral center.


@pytest.mark.parametrize("normalization", ["none", "row", "column"])
@pytest.mark.parametrize("zero", [False, True])
def test_confusion_annotations_use_actual_normalized_backgrounds(tmp_path, normalization, zero):
    module, _ = generated(tmp_path, kind="confusion_matrix", normalize=normalization)
    values = [[0, 0], [0, 0]] if zero else [[9, 1], [2, 8]]
    source = frame(values)
    _, ax = plt.subplots()
    module.draw_panel(ax, module.prepare(source))
    expected = np.array(values, dtype=float)
    if normalization == "row":
        np.divide(expected, expected.sum(axis=1, keepdims=True), out=expected, where=expected != 0)
    elif normalization == "column":
        np.divide(expected, expected.sum(axis=0, keepdims=True), out=expected, where=expected != 0)
    image = ax.images[0]
    np.testing.assert_allclose(image.get_array(), expected, rtol=0, atol=1e-12)
    assert len(ax.texts) == 4
    for text in ax.texts:
        column, row = map(int, text.get_position())
        value = expected[row, column]
        assert contrast(colors.to_rgb(text.get_color()), image.to_rgba(value)[:3]) >= 4.5
        assert text.get_text() == (str(int(value)) if normalization == "none" else f"{value:.2f}")


def findings(fig):
    return [f for f in inspect_figure(fig).findings if f.code == "cell_text_low_contrast"]


def test_inspector_catches_both_black_on_black_and_white_on_white():
    fig, ax = plt.subplots()
    ax.imshow([[0, 1]], cmap="gray", vmin=0, vmax=1)
    ax.text(0, 0, "dark", color="black", ha="center", va="center")
    ax.text(1, 0, "light", color="white", ha="center", va="center")
    assert len(findings(fig)) == 2


def test_inspector_accepts_readable_opposite_colors():
    fig, ax = plt.subplots()
    ax.imshow([[0, 1]], cmap="gray", vmin=0, vmax=1)
    ax.text(0, 0, "dark", color="white", ha="center", va="center")
    ax.text(1, 0, "light", color="black", ha="center", va="center")
    assert not findings(fig)


@pytest.mark.parametrize(
    ("face", "cell", "alpha", "text", "bad"),
    [
        ("white", 0, 0.25, "white", True),
        ("white", 0, 0.25, "black", False),
        ("black", 1, 0.25, "black", True),
        ("black", 1, 0.25, "white", False),
    ],
)
def test_inspector_uses_actual_alpha_composition(face, cell, alpha, text, bad):
    fig, ax = plt.subplots()
    ax.set_facecolor(face)
    ax.imshow([[cell]], cmap="gray", vmin=0, vmax=1, alpha=alpha)
    ax.text(0, 0, "value", color=text, ha="center", va="center")
    assert bool(findings(fig)) is bad


def test_inspector_handles_alpha_arrays_and_multiple_image_layers():
    fig, ax = plt.subplots()
    ax.imshow([[0, 0]], cmap="gray", vmin=0, vmax=1)
    ax.imshow([[1, 1]], cmap="gray", vmin=0, vmax=1, alpha=np.array([[0.25, 0.75]]))
    ax.text(0, 0, "a", color="black", ha="center", va="center")
    ax.text(1, 0, "b", color="white", ha="center", va="center")
    assert len(findings(fig)) == 2


def test_inspector_accounts_for_translucent_text_and_opaque_bbox():
    fig, ax = plt.subplots()
    ax.imshow([[1, 0]], cmap="gray", vmin=0, vmax=1)
    ax.text(0, 0, "faint", color="black", alpha=0.25, ha="center", va="center")
    ax.text(
        1,
        0,
        "pill",
        color="white",
        bbox={"facecolor": "white", "edgecolor": "none"},
        ha="center",
        va="center",
    )
    assert len(findings(fig)) == 2


def test_inspector_handles_masked_cells_as_their_visible_background():
    fig, ax = plt.subplots()
    ax.imshow(np.ma.array([[0, 0]], mask=[[True, False]]), cmap="gray", vmin=0, vmax=1)
    ax.text(0, 0, "missing", color="white", ha="center", va="center")
    ax.text(1, 0, "known", color="white", ha="center", va="center")
    assert len(findings(fig)) == 1


def test_inspector_handles_lower_origin_extent_and_axes_text_transform():
    fig, ax = plt.subplots()
    ax.imshow([[0, 1]], cmap="gray", origin="lower", extent=(10, 20, 30, 40), vmin=0, vmax=1)
    ax.text(0.25, 0.5, "wrong", transform=ax.transAxes, color="black", ha="center", va="center")
    ax.text(17.5, 35, "right", color="black", ha="center", va="center")
    assert len(findings(fig)) == 1


def test_an_image_above_the_text_cannot_hide_it_and_pass():
    fig, ax = plt.subplots()
    ax.imshow([[0]], cmap="gray", vmin=0, vmax=1, zorder=0)
    ax.text(0, 0, "occluded", color="white", ha="center", va="center", zorder=1)
    ax.imshow([[0]], cmap="gray", vmin=0, vmax=1, zorder=2)
    assert len(findings(fig)) == 1


def test_normal_text_on_axes_without_cell_images_is_not_a_cell_finding():
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    ax.text(0.5, 0.5, "ordinary annotation", color="black")
    assert not findings(fig)


def test_contrast_threshold_is_not_rounded_up_to_compliance():
    fig, ax = plt.subplots()
    # A gray whose independent linear luminance gives white contrast 4.499:1.
    target = 1.05 / 4.499 - 0.05
    gray = 1.055 * target ** (1 / 2.4) - 0.055
    ax.imshow([[[gray, gray, gray]]])
    ax.text(0, 0, "borderline", color="white", ha="center", va="center")
    assert contrast((1, 1, 1), (gray, gray, gray)) == pytest.approx(4.499, abs=1e-12)
    assert len(findings(fig)) == 1


def test_runtime_and_export_preserve_cell_values_and_pass_readable_inspection(tmp_path):
    _, path = generated(tmp_path)
    frame([[1, 2], [3, 4]]).to_csv(tmp_path / "data.csv", index=False)
    process = subprocess.run(
        [sys.executable, str(path), "--strict", "--json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    report = json.loads(process.stdout)
    assert process.returncode == 0 and report["status"] == "passed", process.stderr
    assert report["data"]["counts"]["read"] == 4
    assert not [f for f in report["findings"] if f["code"] == "cell_text_low_contrast"]
    assert len(report["outputs"]) == 2
    for suffix in ["png", "svg"]:
        assert read_provenance(tmp_path / f"contrast.{suffix}")["alt_text"] == report["alt_text"]


@pytest.mark.parametrize("dtype", ["uint8", "float64"])
def test_rgba_alpha_composition_agrees_with_actual_raster_background(dtype):
    fig, ax = plt.subplots(facecolor="black")
    ax.set_facecolor("white")
    ax.set_axis_off()  # This axes face is not painted; the figure is the background.
    rgba = np.array([[[255, 255, 255, 128]]], dtype=dtype)
    if dtype == "float64":
        rgba /= 255
    ax.imshow(rgba, alpha=0.5)
    text = ax.text(0, 0, "value", color="white", ha="center", va="center")
    text.set_visible(False)
    fig.canvas.draw()
    pixels = np.asarray(fig.canvas.buffer_rgba())
    x, y = ax.transData.transform((0, 0)).astype(int)
    actual = pixels[pixels.shape[0] - 1 - y, x, :3] / 255
    text.set_visible(True)
    expected_background = (128 / 255 * 0.5,) * 3
    # Agg quantizes RGBA and alpha compositing to 8-bit output. The criterion
    # uses declared colours; the raster probe bounds that renderer quantization.
    np.testing.assert_allclose(actual, expected_background, rtol=0, atol=2 / 255)
    assert cell_text_contrast(ax, text) == pytest.approx(
        contrast((1, 1, 1), expected_background), abs=1e-6
    )


def test_outlined_cell_text_is_explicitly_untested_in_required_runtime_checks(tmp_path):
    import matplotlib.patheffects as effects

    module, _ = generated(tmp_path)
    fig, ax = plt.subplots()
    module.draw_panel(ax, module.prepare(frame([[1, 2], [3, 4]])))
    ax.texts[0].set_path_effects([effects.withStroke(linewidth=1, foreground="black")])
    module.check(fig)
    assert any(f["code"] == "cell_text_contrast_untested" for f in module.RUN_REPORT["findings"])
    assert module.RUN_REPORT["untested"]


def test_generated_cell_colours_work_without_the_optional_inspector_package(tmp_path):
    _, path = generated(tmp_path)
    frame([[1, 2], [3, 4]]).to_csv(tmp_path / "data.csv", index=False)
    driver = tmp_path / "without_package.py"
    driver.write_text(
        "import builtins, runpy, sys\n"
        "original = builtins.__import__\n"
        "def guarded(name, *args, **kwargs):\n"
        "    if name == 'graphunslopify' or name.startswith('graphunslopify.'):\n"
        "        raise ImportError('optional inspector unavailable')\n"
        "    return original(name, *args, **kwargs)\n"
        "builtins.__import__ = guarded\n"
        "sys.argv = ['contrast.py', '--json']\n"
        "runpy.run_path('contrast.py', run_name='__main__')\n",
        encoding="utf8",
    )
    process = subprocess.run(
        [sys.executable, str(driver)], cwd=path.parent, capture_output=True, text=True, check=False
    )
    report = json.loads(process.stdout)
    assert process.returncode == 0 and report["status"] == "incomplete", process.stderr
    assert not report["inspection"]["available"] and len(report["outputs"]) == 2


def test_pure_black_white_math_reference_and_midpoint_bound():
    assert contrast((0, 0, 0), (1, 1, 1)) == 21
    mid_luminance = math.sqrt(0.0525) - 0.05
    mid_gray = 1.055 * mid_luminance ** (1 / 2.4) - 0.055
    assert contrast((0, 0, 0), (mid_gray,) * 3) == pytest.approx(math.sqrt(21), abs=1e-12)


@pytest.mark.parametrize(
    ("name", "image"), [("heatmap", "third-pass-heatmap"), ("confusion", "seventh-pass-confusion")]
)
def test_published_cell_illustrations_match_committed_inputs_and_emitter(name, image):
    root = Path(__file__).resolve().parents[2]
    folder = root / "examples/references"
    spec = json.loads((folder / f"{name}.figure.json").read_text())
    result = local_request("convert", spec)
    assert result["ok"], result
    evidence = read_provenance(root / f"docs/{image}.png")
    assert (
        evidence["data_sha256_prefix"]
        == hashlib.sha256((folder / f"{name}.csv").read_bytes()).hexdigest()[:16]
    )
    assert evidence["script_sha256"] == hashlib.sha256(result["code"].encode("utf8")).hexdigest()
    assert evidence["spec"]["annotate_cells"] is True
