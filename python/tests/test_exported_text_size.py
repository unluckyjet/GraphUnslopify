"""Physical dimensions and manuscript font floors from real written artifacts."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys

import matplotlib.pyplot as plt
import numpy as np
import pytest
from matplotlib.transforms import Bbox
from PIL import Image

from graphunslopify import inspect_figure
from graphunslopify.transport import local_request


@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close("all")


def simple_figure(width=3.4, font=6):
    fig, ax = plt.subplots(figsize=(width, 2.4))
    ax.set_xticks([])
    ax.set_yticks([])
    ax.text(0.5, 0.5, "Measured text", ha="center", fontsize=font)
    return fig, ax


@pytest.mark.parametrize("extension", ["png", "svg", "pdf"])
def test_fixed_size_exports_have_independent_known_physical_width(tmp_path, extension):
    fig, _ = simple_figure(font=8)
    path = tmp_path / f"fixed.{extension}"
    fig.savefig(path, dpi=150)
    report = inspect_figure(fig, target_width_in=3.4, export_paths=[path])
    assert report.ok, report
    measurement = report.measurements
    assert measurement["basis"] == "exports"
    assert measurement["nominal_width_in"] == 3.4
    assert measurement["widths_in"][str(path)] == pytest.approx(3.4, abs=0.002)
    assert measurement["evaluated_width_in"] == pytest.approx(3.4, abs=0.002)
    assert measurement["text_scale"] == pytest.approx(1, abs=0.001)


@pytest.mark.parametrize("extension", ["png", "svg", "pdf"])
def test_tight_export_expansion_catches_false_nominal_font_pass(tmp_path, extension):
    fig, ax = simple_figure()
    ax.text(
        1.2,
        0.7,
        "A long external label expands the exported figure well beyond its nominal width",
        transform=ax.transAxes,
        fontsize=6,
    )
    nominal = inspect_figure(fig, target_width_in=3.4)
    assert nominal.ok and nominal.measurements["basis"] == "nominal"
    path = tmp_path / f"expanded.{extension}"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    report = inspect_figure(fig, target_width_in=3.4, export_paths=[path])
    assert not report.ok
    assert any(f.code == "text_too_small" for f in report.findings)
    assert report.measurements["evaluated_width_in"] > 6
    assert 6 * report.measurements["text_scale"] < 3.4


def test_a_tightly_cropped_canvas_does_not_get_false_nominal_shrinkage(tmp_path):
    fig = plt.figure(figsize=(12, 2.4))
    ax = fig.add_axes([0, 0, 0.1, 1])
    ax.set_xticks([])
    ax.set_yticks([])
    ax.text(0.5, 0.5, "Cropped", fontsize=6, ha="center")
    assert not inspect_figure(fig, target_width_in=3.4).ok
    path = tmp_path / "cropped.pdf"
    fig.savefig(path, bbox_inches="tight")
    report = inspect_figure(fig, target_width_in=3.4, export_paths=[path])
    assert report.ok, report
    assert report.measurements["evaluated_width_in"] < 2
    assert report.measurements["text_scale"] == 1


def test_multiple_formats_use_the_widest_actual_file(tmp_path):
    fig, _ = simple_figure()
    paths = [tmp_path / "fixed.png", tmp_path / "wide.svg", tmp_path / "crop.pdf"]
    fig.savefig(paths[0], dpi=150)
    fig.savefig(paths[1], bbox_inches=Bbox.from_bounds(0, 0, 7, 2.4))
    fig.savefig(paths[2], bbox_inches=Bbox.from_bounds(0, 0, 2, 2.4))
    report = inspect_figure(fig, target_width_in=3.4, export_paths=paths)
    assert not report.ok
    assert list(report.measurements["widths_in"].values()) == pytest.approx([3.4, 7, 2], abs=0.002)
    assert report.measurements["evaluated_width_in"] == 7
    assert report.measurements["text_scale"] == pytest.approx(3.4 / 7)


@pytest.mark.parametrize("extension", ["png", "svg", "pdf", "html"])
def test_unknown_or_broken_export_dimensions_cannot_pass(tmp_path, extension):
    fig, _ = simple_figure()
    path = tmp_path / f"broken.{extension}"
    path.write_text("unreadable dimension evidence", encoding="utf8")
    report = inspect_figure(fig, target_width_in=3.4, export_paths=[path])
    assert not report.ok
    assert any(f.code == "export_size_unavailable" for f in report.findings)
    assert report.measurements["basis"] == "unavailable"
    assert report.measurements["evaluated_width_in"] is None
    assert report.measurements["text_scale"] is None


def test_png_without_physical_dpi_is_not_assumed_to_match_the_canvas(tmp_path):
    fig, _ = simple_figure()
    path = tmp_path / "no-dpi.png"
    Image.new("RGB", (510, 360), "white").save(path)
    report = inspect_figure(fig, target_width_in=3.4, export_paths=[path])
    assert not report.ok and report.measurements["basis"] == "unavailable"


@pytest.mark.parametrize(
    ("width", "unit"), [(244.8, "pt"), (3.4, "in"), (8.636, "cm"), (86.36, "mm")]
)
def test_absolute_svg_units_keep_the_same_physical_width(tmp_path, width, unit):
    fig, _ = simple_figure(font=8)
    path = tmp_path / "units.svg"
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}{unit}" height="100pt"/>'
    )
    report = inspect_figure(fig, target_width_in=3.4, export_paths=[path])
    assert report.ok and report.measurements["evaluated_width_in"] == pytest.approx(3.4)


def test_one_valid_file_cannot_hide_unknown_dimensions_in_another_format(tmp_path):
    fig, _ = simple_figure()
    good = tmp_path / "good.png"
    bad = tmp_path / "bad.pdf"
    fig.savefig(good, dpi=150)
    bad.write_bytes(b"not a PDF")
    report = inspect_figure(fig, target_width_in=3.4, export_paths=[good, bad])
    assert not report.ok and str(good) in report.measurements["widths_in"]
    assert report.measurements["evaluated_width_in"] is None


def test_empty_export_evidence_is_unavailable_not_a_nominal_pass():
    fig, _ = simple_figure()
    report = inspect_figure(fig, target_width_in=3.4, export_paths=[])
    assert not report.ok and report.measurements["basis"] == "unavailable"


def test_a_non_svg_xml_root_does_not_certify_svg_size(tmp_path):
    fig, _ = simple_figure()
    path = tmp_path / "pretend.svg"
    path.write_text('<other width="244.8pt" height="100pt"/>')
    assert not inspect_figure(fig, target_width_in=3.4, export_paths=[path]).ok


def test_mislabeled_jpeg_does_not_certify_png_size(tmp_path):
    fig, _ = simple_figure()
    path = tmp_path / "pretend.png"
    Image.new("RGB", (510, 360), "white").save(path, format="JPEG", dpi=(150, 150))
    assert not inspect_figure(fig, target_width_in=3.4, export_paths=[path]).ok


@pytest.mark.parametrize(("font", "bad"), [(5, False), (4.99999, True)])
def test_font_floor_does_not_fail_float_representation_noise_or_round_real_failure(
    tmp_path, font, bad
):
    fig, _ = simple_figure(font=font)
    path = tmp_path / "boundary.pdf"
    fig.savefig(path)
    report = inspect_figure(fig, target_width_in=3.4, export_paths=[path])
    assert any(f.code == "text_too_small" for f in report.findings) is bad


@pytest.mark.parametrize("width", ["nanpt", "infpt", "0pt", "-2pt", "100%"])
def test_invalid_or_relative_svg_width_is_unknown_not_zero(tmp_path, width):
    fig, _ = simple_figure()
    path = tmp_path / "bad.svg"
    path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="100pt"/>')
    report = inspect_figure(fig, target_width_in=3.4, export_paths=[path])
    assert not report.ok and report.measurements["text_scale"] is None


@pytest.mark.parametrize("target", [0, -1, np.nan, np.inf])
def test_invalid_target_width_cannot_disable_the_floor(target):
    fig, _ = simple_figure()
    with pytest.raises(ValueError, match="target_width_in"):
        inspect_figure(fig, target_width_in=target)


def generated(tmp_path, *, kind="line", title=None):
    spec = {
        "kind": kind,
        "x": {"field": "step", "label": "Step"},
        "y": {"field": "value", "label": "Value"},
        "data": {"path": "data.csv"},
        "output": {"stem": "figure", "formats": ["png", "svg", "pdf"], "dpi": 150},
    }
    if title:
        spec["title"] = title
    result = local_request("convert", spec)
    assert result["ok"], result
    path = tmp_path / "figure.py"
    path.write_text(result["code"], encoding="utf8")
    (tmp_path / "data.csv").write_text("step,value\n1,1\n2,2\n3,3\n", encoding="utf8")
    definition = importlib.util.spec_from_file_location("export_reference", path)
    module = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(module)
    return module, path


@pytest.mark.parametrize("kind", ["line", "table"])
def test_generated_strict_reports_measure_the_actual_written_static_files(tmp_path, kind):
    _, path = generated(tmp_path, kind=kind)
    process = subprocess.run(
        [sys.executable, str(path), "--strict", "--json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    report = json.loads(process.stdout)
    assert process.returncode == 0 and report["status"] == "passed", process.stderr
    measured = report["inspection"]["measurements"]
    assert measured["basis"] == "exports" and len(measured["widths_in"]) == 3
    assert measured["evaluated_width_in"] == max(measured["widths_in"].values())
    assert report["data"]["counts"]["read"] == 3


@pytest.mark.parametrize(
    ("title", "accepted"),
    [("A very long scientific title " * 8, True), ("UnbreakableIdentifier" * 12, False)],
)
def test_generated_title_layout_and_column_font_floor_keep_actual_artifacts(
    tmp_path, title, accepted
):
    _, path = generated(tmp_path, title=title)
    process = subprocess.run(
        [sys.executable, str(path), "--strict", "--json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    report = json.loads(process.stdout)
    assert process.returncode == (0 if accepted else 2), process.stderr
    assert report["status"] == ("passed" if accepted else "failed")
    assert report["spec"]["title"] == title and report["data"]["counts"]["read"] == 3
    assert len(report["outputs"]) == 3
    if not accepted:
        assert any(f["code"] == "text_too_small" for f in report["findings"])
        assert report["inspection"]["measurements"]["text_scale"] < 0.5


def test_outdated_inspector_is_incomplete_instead_of_silently_using_nominal_size(
    tmp_path, monkeypatch
):
    import graphunslopify

    module, _ = generated(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        graphunslopify, "inspect_figure", lambda figure, target_width_in, min_text_pt: None
    )
    code = module.run_cli(["--strict", "--json"])
    assert code == 2 and module.RUN_REPORT["status"] == "incomplete"
    assert any(f["code"] == "inspection_outdated" for f in module.RUN_REPORT["findings"])
    assert len(module.RUN_REPORT["outputs"]) == 3


def test_inspector_proxy_that_discards_export_paths_cannot_certify_final_size(
    tmp_path, monkeypatch
):
    import graphunslopify

    module, _ = generated(tmp_path)
    original = graphunslopify.inspect_figure
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        graphunslopify,
        "inspect_figure",
        lambda figure, **kwargs: original(figure, target_width_in=kwargs["target_width_in"]),
    )
    assert module.run_cli(["--strict", "--json"]) == 2
    assert module.RUN_REPORT["status"] == "incomplete"
    assert not module.RUN_REPORT["inspection"]["checked"]
