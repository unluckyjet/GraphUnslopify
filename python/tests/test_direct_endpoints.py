"""Direct names must identify actual rendered quantities and native positions."""

import contextlib
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from statistics import NormalDist
from unittest.mock import patch

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from test_shared_series import rows, spec

from graphunslopify import read_provenance
from graphunslopify.preview import PreviewState
from graphunslopify.transport import local_request


def request(kind, scope="facet"):
    raw = spec(kind, explicit=True)
    raw["legend"] = {
        "style": "direct",
        "labels": [{"series": "01", "text": "Alpha"}, {"series": "1", "text": "Beta"}],
    }
    raw["output"].update(formats=["png", "svg", "pdf"], dpi=150)
    data = rows(explicit=True)
    if kind in {"ecdf", "kaplan_meier"}:
        # A separate fixture gives the cohorts different observed endpoints.
        # Identical endpoints remain legitimate strict collision failures.
        data.loc[data.method == "1", "step"] *= 2
    if scope == "single":
        raw.pop("facet")
        data = data[data.site == "second"].copy()
    elif scope == "repeat":
        raw.pop("facet")
        raw["repeat"] = {"fields": ["value", "other"], "columns": 2}
        data = data[data.site == "second"].copy()
    return raw, data


def render(folder, monkeypatch, raw, data):
    csv = data.to_csv(index=False, lineterminator="\n").encode()
    (folder / "data.csv").write_bytes(csv)
    response = local_request("convert", raw)
    assert response["ok"], response
    path = folder / "plot.py"
    path.write_text(response["code"])
    done = subprocess.run(
        [sys.executable, str(path), "--strict", "--json"],
        cwd=folder,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    report = json.loads(done.stdout)
    definition = importlib.util.spec_from_file_location("native_direct", path)
    module = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(module)
    monkeypatch.chdir(folder)
    with patch.object(plt, "close"), contextlib.redirect_stdout(io.StringIO()):
        module.main()
    fig = plt.gcf()
    fig.canvas.draw()
    assert (folder / "data.csv").read_bytes() == csv
    assert report["data"]["sha256_prefix"] == hashlib.sha256(csv).hexdigest()[:16]
    for fmt in ["png", "svg", "pdf"]:
        assert (
            read_provenance(folder / f"series.{fmt}")["spec"]["legend"]
            == module.RUN_REPORT["spec"]["legend"]
        )
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    svg = ET.fromstring((folder / "series.svg").read_bytes(), parser=parser)
    comments = [
        item.text.strip()
        for group in svg.iter()
        if group.attrib.get("id", "").startswith("text_")
        for item in group.iter()
        if item.tag is ET.Comment
    ]
    return done, report, fig, module, comments


def names(ax):
    return [
        text
        for text in ax.texts
        if getattr(text, "_graphunslopify_text_target", {}).get("role") == "legend_entry"
    ]


@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close("all")


@pytest.mark.parametrize(
    "kind",
    ["line", "scatter", "ecdf", "slope", "qq", "scaling_fit", "kaplan_meier", "bar", "dumbbell"],
)
@pytest.mark.parametrize("scope", ["single", "facet"])
def test_direct_names_have_native_endpoints_and_actual_exported_glyphs(
    tmp_path, monkeypatch, kind, scope
):
    raw, data = request(kind, scope)
    done, report, fig, _, comments = render(tmp_path, monkeypatch, raw, data)
    assert done.returncode == 0 and report["status"] == "passed", report
    count = 0
    for ax in fig.axes:
        for text in names(ax):
            count += 1
            target = text._graphunslopify_text_target
            source = target["source"]
            value = 2 if source == "01" else 4
            expected_x, expected_y = 2, value
            if kind == "bar":
                assert 0.5 < text.xy[0] < 1.5
                expected_x = text.xy[0]
            elif kind == "dumbbell":
                expected_x, expected_y = value, 0
            elif kind == "ecdf":
                expected_x, expected_y = (2 if source == "01" else 4), 1
            elif kind == "kaplan_meier":
                expected_x, expected_y = (2 if source == "01" else 4), 0
            elif kind == "slope":
                expected_x = 1
            elif kind == "qq":
                expected_x = NormalDist().inv_cdf((2 - 0.375) / (2 + 0.25))
            np.testing.assert_allclose(text.xy, [expected_x, expected_y], rtol=0, atol=1e-12)
            assert text.get_text() == ("Alpha" if source == "01" else "Beta")
            assert target["path"] == ["legend", "labels", 0 if source == "01" else 1, "text"]
            assert text.get_fontsize() == 8
    assert count == (2 if scope == "single" else 3)
    assert comments.count("Alpha") == (1 if scope == "single" else 2)
    assert comments.count("Beta") == 1


def test_calibration_uses_each_rendered_panels_actual_ece_suffix(tmp_path, monkeypatch):
    raw, _ = request("calibration")
    data = pd.DataFrame(
        {
            "site": ["first", "first", "second", "second"],
            "method": ["01"] * 4,
            "prob": [0.1, 0.9, 0.25, 0.75],
            "event": [0, 1, 0, 1],
        }
    )
    raw["series_order"] = ["01"]
    raw["legend"]["labels"] = [{"series": "01", "text": "Alpha"}]
    done, report, fig, _, comments = render(tmp_path, monkeypatch, raw, data)
    assert done.returncode == 0 and report["status"] == "passed", report
    for ax, endpoint, suffix in zip(fig.axes, [[0.9, 1], [0.75, 1]], ["0.1", "0.25"], strict=True):
        (text,) = names(ax)
        np.testing.assert_allclose(text.xy, endpoint, rtol=0, atol=1e-12)
        assert text.get_text() == f"Alpha (ECE {suffix})"
        assert text.get_text() in comments


def test_scaling_name_tracks_fitted_curve_not_last_observed_point(tmp_path, monkeypatch):
    raw, _ = request("scaling_fit", "single")
    raw["series_order"] = ["01"]
    raw["legend"]["labels"] = [{"series": "01", "text": "Alpha"}]
    data = pd.DataFrame({"step": [1, 2, 4], "value": [1, 3, 4], "method": ["01"] * 3})
    done, report, fig, _, _ = render(tmp_path, monkeypatch, raw, data)
    assert done.returncode == 0 and report["status"] == "passed", report
    (text,) = names(fig.axes[0])
    x = np.log([1, 2, 4])
    y = np.log([1, 3, 4])
    slope = float(np.sum((x - x.mean()) * (y - y.mean())) / np.sum((x - x.mean()) ** 2))
    expected = float(np.exp(y.mean() + slope * (np.log(4) - x.mean())))
    assert expected != 4
    np.testing.assert_allclose(text.xy, [4, expected], rtol=1e-12, atol=1e-12)
    assert report["data"]["counts"]["read"] == 3


@pytest.mark.parametrize("scope", ["single", "facet"])
def test_sparkline_names_belong_only_to_original_child_titles(tmp_path, monkeypatch, scope):
    raw, data = request("sparkline_grid", scope)
    done, report, fig, _, comments = render(tmp_path, monkeypatch, raw, data)
    assert done.returncode == 0 and report["status"] == "passed", report
    assert all(not names(ax) for ax in fig.axes)
    children = [child for ax in fig.axes for child in ax.child_axes]
    assert len(children) == (2 if scope == "single" else 3 if scope == "facet" else 4)
    assert comments.count("Alpha") + comments.count("Beta") == len(children)
    for child in children:
        target = child.title._graphunslopify_text_target
        assert target["source"] in {"01", "1"} and target["role"] == "legend_entry"
        assert len(child.lines[0].get_xdata()) == 2


def test_direct_preview_targets_keep_original_source_ids_and_canonical_alias_paths(tmp_path):
    raw, data = request("ecdf", "single")
    state = PreviewState(tmp_path, 1024 * 1024)
    csv = data.to_csv(index=False, lineterminator="\n").encode()
    upload = state.upload("original.csv", csv)
    result = state.render(
        {"client": "direct-endpoint", "generation": 1, "data_id": upload["id"], "spec": raw}
    )
    assert result["report"]["status"] == "passed", result["report"]
    targets = [
        target for target in result["edit_map"]["targets"] if target["role"] == "legend_entry"
    ]
    assert len(targets) == 2 and all(target["editable"] for target in targets)
    assert {target["source"] for target in targets} == {"01", "1"}
    assert {tuple(target["path"]) for target in targets} == {
        ("legend", "labels", 0, "text"),
        ("legend", "labels", 1, "text"),
    }
    assert result["report"]["data"]["sha256_prefix"] == hashlib.sha256(csv).hexdigest()[:16]


def test_unsupported_sparkline_repeat_remains_refused():
    raw, _ = request("sparkline_grid", "repeat")
    result = local_request("convert", raw)
    assert not result["ok"]
    assert any(
        f["code"] == "unsupported_repeat" and f["severity"] == "error" for f in result["findings"]
    )


def test_unfit_complete_wording_remains_a_strict_failure(tmp_path, monkeypatch):
    import warnings

    raw, data = request("line", "single")
    original = "OriginalSourceIdentifier" * 12
    raw["legend"]["labels"][0]["text"] = original
    with warnings.catch_warnings(record=True) as caught:
        done, report, fig, _, comments = render(tmp_path, monkeypatch, raw, data)
    assert all("Tight layout" in str(item.message) for item in caught)
    assert done.returncode == 2 and report["status"] == "failed"
    assert any(f["code"] == "text_too_small" for f in report["findings"])
    assert original in comments
    assert any(text.get_text() == original for text in names(fig.axes[0]))


def test_temporal_direct_endpoints_use_the_native_date_coordinate(tmp_path, monkeypatch):
    import matplotlib.dates as mdates

    raw, data = request("line", "single")
    raw["x"]["temporal"] = True
    data["step"] = data["step"].map({1: "2026-01-01", 2: "2026-01-02"})
    done, report, fig, _, comments = render(tmp_path, monkeypatch, raw, data)
    assert done.returncode == 0 and report["status"] == "passed", report
    expected = mdates.date2num(np.datetime64("2026-01-02"))
    for text in names(fig.axes[0]):
        assert text.xy[0] == expected
    assert comments.count("Alpha") == comments.count("Beta") == 1


def test_right_censored_survival_name_tracks_probability_one(tmp_path, monkeypatch):
    raw, data = request("kaplan_meier", "single")
    data["event"] = 0
    done, report, fig, _, comments = render(tmp_path, monkeypatch, raw, data)
    assert done.returncode == 0 and report["status"] == "passed", report
    assert all(text.xy[1] == 1 for text in names(fig.axes[0]))
    assert comments.count("Alpha") == comments.count("Beta") == 1


@pytest.mark.parametrize("horizontal", [False, True])
@pytest.mark.parametrize("negative", [False, True])
def test_direct_bar_names_clear_the_actual_signed_bar_ends(
    tmp_path, monkeypatch, horizontal, negative
):
    raw, data = request("bar", "single")
    raw["orientation"] = "horizontal" if horizontal else "vertical"
    if negative:
        data["value"] *= -1
    done, report, fig, _, _ = render(tmp_path, monkeypatch, raw, data)
    assert done.returncode == 0 and report["status"] == "passed", report
    ax = fig.axes[0]
    renderer = fig.canvas.get_renderer()
    for text in names(ax):
        expected = (2 if text._graphunslopify_text_target["source"] == "01" else 4) * (
            -1 if negative else 1
        )
        assert text.xy[0 if horizontal else 1] == expected
        box = text.get_window_extent(renderer)
        point = ax.transData.transform(text.xy)
        if horizontal:
            assert box.x1 < point[0] if negative else box.x0 > point[0]
        else:
            assert box.y1 < point[1] if negative else box.y0 > point[1]


def test_authored_direct_bar_clipping_remains_a_strict_failure(tmp_path, monkeypatch):
    raw, data = request("bar", "single")
    raw["y"]["limits"] = [0, 1.5]
    done, report, _, _, _ = render(tmp_path, monkeypatch, raw, data)
    assert done.returncode == 2 and report["status"] == "failed"
    assert any(f["code"] == "bar_mark_clipped" for f in report["findings"])


def test_mean_curve_name_does_not_identify_the_last_individual_observation(tmp_path, monkeypatch):
    raw, _ = request("line", "single")
    raw["aggregation"] = "mean"
    raw["series_order"] = ["01"]
    raw["legend"]["labels"] = [{"series": "01", "text": "Alpha"}]
    data = pd.DataFrame({"step": [1, 1, 2, 2], "value": [1, 3, 3, 7], "method": ["01"] * 4})
    done, report, fig, _, comments = render(tmp_path, monkeypatch, raw, data)
    assert done.returncode == 0 and report["status"] == "passed", report
    (text,) = names(fig.axes[0])
    np.testing.assert_allclose(text.xy, [2, 5], rtol=0, atol=1e-12)
    np.testing.assert_array_equal(fig.axes[0].lines[0].get_ydata(), [2, 5])
    assert report["data"]["counts"]["read"] == 4
    assert comments.count("Alpha") == 1
