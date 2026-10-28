"""Bounded cross-feature references; actual marks, saved files and strict outcomes.

Independent hand answers are based on unit summaries [1, 2, 9] and [4, 6, 20].
This is an interaction matrix, not a Cartesian or experiment-validity certificate.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from jsonschema import validate
from matplotlib.collections import LineCollection, PolyCollection
from matplotlib.container import BarContainer
from PIL import Image
from pypdf import PdfReader

from graphunslopify import read_provenance
from graphunslopify.transport import local_request

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "docs/runtime-report.schema.json").read_text())
PRESENTATIONS = ["line", "line-band", "bar", "bar-horizontal", "forest", "table"]
ESTIMATORS = [("mean", "sem"), ("median", "ci"), ("median", "iqr")]


@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close("all")


def spec(folder, kind="line", **extra):
    return {
        "kind": kind,
        "data": {"path": str(folder / "data.csv")},
        "x": {"field": "x", "label": "Input"},
        "y": {"field": "score", "label": "Score"},
        "legend": {"show": False},
        "output": {
            "stem": "matrix",
            "formats": ["png", "svg", "pdf"],
            "size": "double_column",
            "dpi": 100,
        },
        **extra,
    }


def generated(folder, raw, allow_errors=False):
    result = local_request("convert", raw)
    assert result.get("ok") or allow_errors, result
    path = folder / "figure.py"
    path.write_text(result["code"], encoding="utf8")
    definition = importlib.util.spec_from_file_location("interaction_reference", path)
    module = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(module)
    return module


def execute(module, folder, frame, monkeypatch):
    frame.to_csv(folder / "data.csv", index=False)
    monkeypatch.chdir(folder)
    figures = []
    original = module.check

    def inspect(fig):
        figures.append(fig)
        return original(fig)

    monkeypatch.setattr(module, "check", inspect)
    code = module.run_cli(["--json"])
    report = json.loads((folder / "matrix.report.json").read_text())
    validate(report, SCHEMA)
    assert code == report["exit_code"]
    return report, figures


def unit_rows(gap=False):
    rows = []
    for x in [1, 3]:
        for unit, value in zip(
            ["01", "01", "01", "01", "1", "B", "Z", None],
            [0, 2, 0, 2, 2, 9, np.nan, 1000],
            strict=True,
        ):
            rows.append((x, value if x == 1 else 2 * value + 2, unit))
    if gap:
        rows.extend((2, np.nan, unit) for unit in ["01", "1", "B"])
    return pd.DataFrame(rows, columns=["x", "score", "unit"])


def expected(aggregation, uncertainty):
    centers = np.array([4, 10]) if aggregation == "mean" else np.array([2, 6])
    if uncertainty == "sem":
        error = np.array([1, 2]) * math.sqrt(19 / 3)
        return centers, centers - error, centers + error
    if uncertainty == "ci":
        # Each n=3 empirical bootstrap median's endpoint mass exceeds 2.5%.
        return centers, np.array([1, 4]), np.array([9, 20])
    return centers, np.array([1.5, 5]), np.array([5.5, 13])


class ScriptSources(HTMLParser):
    def __init__(self):
        super().__init__()
        self.external = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.external.extend(value for key, value in attrs if key == "src")


def html_traces(path):
    body = path.read_text(encoding="utf8")
    parser = ScriptSources()
    parser.feed(body)
    assert not parser.external
    # Read the serialized call in the saved artifact, not a patched Plotly object.
    call = body[body.rindex("Plotly.newPlot(") :]
    traces, _ = json.JSONDecoder().raw_decode(call.split(",", 1)[1].lstrip())
    assert traces
    return traces


def exported_files(report, folder, label="Score"):
    for item in report["outputs"]:
        path = folder / item["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
        assert path.stat().st_size == item["bytes"] > 0
        if item["format"] not in {"png", "svg", "pdf", "html"}:
            continue
        evidence = read_provenance(path)
        assert evidence["spec_hash"] == report["spec_hash"]
        assert evidence["script_sha256"] == report["script"]["sha256"]
        assert evidence["data_sha256_prefix"] == report["data"]["sha256_prefix"]
        assert evidence["alt_text"] == report["alt_text"]
        if item["format"] == "png":
            with Image.open(path) as image:
                assert (
                    min(image.size) > 50
                    and len(image.convert("RGB").getcolors(image.width * image.height)) > 10
                )
        elif item["format"] == "svg":
            document = ET.parse(path).getroot()
            assert document.get("role") == "img"
            assert document.find("{http://www.w3.org/2000/svg}desc").text == report["alt_text"]
            assert document.findall(".//{http://www.w3.org/2000/svg}path")
        elif item["format"] == "pdf":
            pdf = PdfReader(path)
            assert len(pdf.pages) == 1 and label in pdf.pages[0].extract_text()


def assert_native(fig, presentation, centers, low, high):
    ax = fig.axes[0]
    if presentation == "table":
        table = ax.tables[0]
        for row, (center, a, b) in enumerate(zip(centers, low, high, strict=True), start=1):
            text = table[row, 0].get_text().get_text()
            np.testing.assert_allclose(
                [float(v) for v in re.findall(r"-?\d+\.\d+", text)], [center, a, b], atol=0.0051
            )
    elif presentation == "forest":
        markers = [line for line in ax.lines if line.get_marker() == "o"]
        np.testing.assert_allclose([line.get_xdata()[0] for line in markers], centers)
        intervals = [
            line.get_xdata()
            for line in ax.lines
            if line.get_transform() == ax.transData
            and len(line.get_xdata()) == 2
            and len(set(line.get_ydata())) == 1
        ]
        np.testing.assert_allclose(intervals, np.column_stack([low, high]))
    elif presentation.startswith("bar"):
        bar = next(c for c in ax.containers if isinstance(c, BarContainer))
        horizontal = presentation == "bar-horizontal"
        np.testing.assert_allclose(
            [p.get_width() if horizontal else p.get_height() for p in bar.patches], centers
        )
        segments = bar.errorbar.lines[2][0].get_segments()
        np.testing.assert_allclose(
            np.array(segments)[:, :, 0 if horizontal else 1], np.column_stack([low, high])
        )
    else:
        np.testing.assert_allclose(ax.lines[0].get_ydata(), centers)
        if presentation == "line-band":
            vertices = (
                next(c for c in ax.collections if isinstance(c, PolyCollection))
                .get_paths()[0]
                .vertices
            )
            for index, x in enumerate([1, 3]):
                ys = vertices[vertices[:, 0] == x, 1]
                np.testing.assert_allclose([ys.min(), ys.max()], [low[index], high[index]])
        else:
            segments = next(
                c for c in ax.collections if isinstance(c, LineCollection)
            ).get_segments()
            np.testing.assert_allclose(np.array(segments)[:, :, 1], np.column_stack([low, high]))


@pytest.mark.parametrize("presentation", PRESENTATIONS)
@pytest.mark.parametrize(("aggregation", "uncertainty"), ESTIMATORS)
def test_unit_estimator_missingness_and_export_matrix(
    tmp_path, monkeypatch, presentation, aggregation, uncertainty
):
    kind = presentation.split("-")[0]
    raw = spec(
        tmp_path,
        kind,
        aggregation=aggregation,
        uncertainty={
            "kind": uncertainty,
            "over": "unit",
            "display": "band" if presentation == "line-band" else "bar",
        },
    )
    if presentation == "bar-horizontal":
        raw["orientation"] = "horizontal"
    interactive = kind in {"line", "bar"}
    raw["output"]["interactive"] = interactive
    module = generated(tmp_path, raw)
    report, figures = execute(module, tmp_path, unit_rows(), monkeypatch)
    assert report["status"] == "passed" and report["exit_code"] == 0, report
    counts = report["data"]["counts"]
    assert counts["missing_unit_ids"] == 2
    assert counts["sample_sizes"] == [3, 3]
    centers, low, high = expected(aggregation, uncertainty)
    assert_native(figures[0], presentation, centers, low, high)
    exported_files(report, tmp_path)
    assert {f["format"] for f in report["outputs"]} >= {"png", "svg", "pdf"}
    if interactive:
        traces = html_traces(tmp_path / "matrix.html")
        coordinate = "x" if presentation == "bar-horizontal" else "y"
        primary = [t for t in traces if t["type"] == "bar" or t.get("line", {}).get("width", 1) > 0]
        assert len(primary) == 1, traces
        np.testing.assert_allclose(primary[0][coordinate], centers)
        error = primary[0].get("error_" + coordinate)
        if error:
            np.testing.assert_allclose(error["array"], high - centers)
            np.testing.assert_allclose(error["arrayminus"], centers - low)
        else:
            assert presentation == "line-band"
            np.testing.assert_allclose(traces[0]["y"], low)
            np.testing.assert_allclose(traces[1]["y"], high)


@pytest.mark.parametrize("display", ["bar", "band"])
def test_unknown_middle_interval_remains_a_gap_in_both_backends(tmp_path, monkeypatch, display):
    raw = spec(
        tmp_path,
        aggregation="mean",
        uncertainty={"kind": "sem", "over": "unit", "display": display},
    )
    raw["output"]["interactive"] = True
    module = generated(tmp_path, raw)
    report, figures = execute(module, tmp_path, unit_rows(gap=True), monkeypatch)
    assert report["status"] == "incomplete" and report["exit_code"] == 2, report
    np.testing.assert_allclose(
        figures[0].axes[0].lines[0].get_ydata(), [4, np.nan, 10], equal_nan=True
    )
    traces = html_traces(tmp_path / "matrix.html")
    primary = next(t for t in traces if t.get("line", {}).get("width", 1) > 0)
    assert primary["y"] == [4, None, 10]
    assert 0 in report["data"]["counts"]["sample_sizes"]
    assert any("uncertainty" in reason for reason in report["untested"])
    exported_files(report, tmp_path)


@pytest.mark.parametrize("aggregation", ["sum", "count"])
def test_sparse_cells_keep_observed_zero_unknown_and_absent_cells_distinct(
    tmp_path, monkeypatch, aggregation
):
    raw = spec(
        tmp_path,
        "heatmap",
        aggregation=aggregation,
        value="weight",
        value_label="Weight",
        y={"field": "row", "label": "Rows"},
        annotate_cells=True,
    )
    raw["output"]["interactive"] = True
    module = generated(tmp_path, raw)
    rows = pd.DataFrame(
        {
            "x": ["A", "A", "A", "B", "B"],
            "row": ["R1", "R1", "R2", "R1", "R1"],
            "weight": [0, 0, np.nan, 1, 3],
        }
    )
    report, figures = execute(module, tmp_path, rows, monkeypatch)
    assert report["status"] == "passed", report
    expected_cells = [[0, 4], [np.nan, np.nan]] if aggregation == "sum" else [[2, 2], [0, np.nan]]
    actual = figures[0].axes[0].images[0].get_array().filled(np.nan)
    np.testing.assert_allclose(actual, expected_cells, equal_nan=True)
    trace = html_traces(tmp_path / "matrix.html")[0]
    np.testing.assert_allclose(np.asarray(trace["z"], dtype=float), expected_cells, equal_nan=True)
    exported_files(report, tmp_path, label="Rows")


@pytest.mark.parametrize("filtered", [False, True])
def test_log_domain_and_source_selection_policies_compose_with_real_exports(
    tmp_path, monkeypatch, filtered
):
    raw = spec(tmp_path, "scatter", x={"field": "x", "label": "Input", "scale": "log"})
    if filtered:
        raw["filter"] = [{"field": "x", "op": "gt", "value": 0}]
    module = generated(tmp_path, raw)
    report, figures = execute(
        module, tmp_path, pd.DataFrame({"x": [-1, 1, 2, 4], "score": [10, 2, 3, 4]}), monkeypatch
    )
    assert report["exit_code"] == (0 if filtered else 2), report
    if filtered:
        assert report["status"] == "passed"
        assert report["data"]["counts"]["filtering"]["removed_rows"] == 1
        assert "Selected 3 of 4" in report["alt_text"]
        np.testing.assert_allclose(
            figures[0].axes[0].collections[0].get_offsets(), [[1, 2], [2, 3], [4, 4]]
        )
    else:
        assert report["status"] == "failed"
        assert any(f["code"] == "log_domain_hidden" for f in report["findings"])
    exported_files(report, tmp_path)


@pytest.mark.parametrize("permuted", [False, True])
def test_repeated_metrics_keep_units_annotation_targets_and_exports_separate(
    tmp_path, monkeypatch, permuted
):
    rows = unit_rows()
    rows["cost"] = 2 * rows["score"] + 3
    if permuted:
        rows = rows.sample(frac=1, random_state=14)
    raw = spec(
        tmp_path,
        aggregation="mean",
        uncertainty={"kind": "sem", "over": "unit", "display": "bar"},
        repeat={"fields": ["score", "cost"], "share_y": False},
        annotate=[{"at": "last", "text": "Displayed end"}],
    )
    module = generated(tmp_path, raw)
    report, figures = execute(module, tmp_path, rows, monkeypatch)
    assert report["status"] == "passed", report
    axes = figures[0].axes
    np.testing.assert_allclose(axes[0].lines[0].get_ydata(), [4, 10])
    np.testing.assert_allclose(axes[1].lines[0].get_ydata(), [11, 23])
    points = {item["metric"]: item["resolved"]["value"] for item in report["annotations"]}
    assert points == {"score": 10, "cost": 23}
    assert {item["metric"] for item in report["panels"]} == {"score", "cost"}
    exported_files(report, tmp_path)


@pytest.mark.parametrize("correction", ["holm", "benjamini_hochberg"])
def test_faceted_pairing_preserves_units_planned_families_and_actual_bars(
    tmp_path, monkeypatch, correction
):
    rows = []
    for panel, offset in [("A", 0), ("B", 100)]:
        for unit, base, delta in zip(
            ["01", "1", "B", "C"], [10, 20, 30, 40], [1, 4, 2, 6], strict=True
        ):
            for category, value in [("base", base), ("new", base + delta)]:
                for technical in [-1, 1]:
                    rows.append((panel, category, unit, value + offset + technical))
    raw = spec(
        tmp_path,
        "bar",
        aggregation="mean",
        uncertainty={"kind": "sem", "over": "unit"},
        facet={"by": "panel", "share_y": False},
        category_order=["base", "new"],
        significance={
            "method": "bootstrap",
            "design": "paired",
            "pair_by": "unit",
            "correction": correction,
            "pairs": [["base", "new"], ["base", "absent"], ["new", "absent"]],
        },
    )
    module = generated(tmp_path, raw)
    frame = pd.DataFrame(rows, columns=["panel", "x", "unit", "score"]).sample(
        frac=1, random_state=7
    )
    report, figures = execute(module, tmp_path, frame, monkeypatch)
    assert report["status"] == "incomplete" and report["exit_code"] == 2, report
    for panel in [0, 1]:
        records = [record for record in report["significance"] if record["panel"] == panel]
        assert len(records) == 3
        tested = next(record for record in records if record["status"] == "tested")
        # All four matched differences are positive: two of16 sign assignments
        # are as extreme in absolute mean. Two planned pairs remain untestable.
        assert tested["raw_p"] == 1 / 8 and tested["adjusted_p"] == 3 / 8
        assert (tested["family_size"], tested["tested_family_size"], tested["matched_pairs"]) == (
            3,
            1,
            4,
        )
        assert sum(record["status"] == "untested" for record in records) == 2
    for ax in figures[0].axes:
        name = next(p["name"] for p in report["panels"] if p["index"] == figures[0].axes.index(ax))
        offset = 0 if name == "A" else 100
        assert ax.xaxis.get_major_formatter().format_ticks(ax.get_xticks()) == ["base", "new"]
        np.testing.assert_allclose(
            [
                patch.get_height()
                for container in ax.containers
                if isinstance(container, BarContainer)
                for patch in container.patches
            ],
            [25 + offset, 28.25 + offset],
        )
    exported_files(report, tmp_path)


@pytest.mark.parametrize(
    ("change", "finding"),
    [
        ({"aggregation": "median"}, "median_sem_unsupported"),
        ({"kind": "bar", "group": "model", "stacked": True}, "stacked_uncertainty_unsupported"),
        (
            {"facet": {"by": "panel"}, "repeat": {"fields": ["score", "cost"]}},
            "facet_repeat_conflict",
        ),
        (
            {
                "kind": "forest",
                "output": {"stem": "matrix", "formats": ["png"], "interactive": True},
            },
            "interactive_not_supported",
        ),
    ],
)
def test_unsupported_interactions_cannot_pass_direct_strict_execution(
    tmp_path, monkeypatch, change, finding
):
    raw = spec(
        tmp_path,
        **{"aggregation": "mean", "uncertainty": {"kind": "sem", "over": "unit"}, **change},
    )
    translated = local_request("convert", raw)
    assert not translated["ok"] and any(f["code"] == finding for f in translated["findings"])
    module = generated(tmp_path, raw, allow_errors=True)
    rows = unit_rows().assign(model="one", panel="A", cost=lambda df: df.score * 2)
    report, _ = execute(module, tmp_path, rows, monkeypatch)
    assert report["status"] == "failed" and report["exit_code"] != 0
    assert any(f["code"] == finding and f["severity"] == "error" for f in report["findings"])


@pytest.mark.parametrize("gap", [False, True])
def test_real_process_matches_strict_policy_and_saved_evidence(tmp_path, gap):
    raw = spec(
        tmp_path,
        aggregation="median",
        uncertainty={"kind": "ci", "over": "unit", "display": "band"},
        annotate=[{"at": "last", "text": "Displayed end"}],
    )
    module = generated(tmp_path, raw)
    unit_rows(gap=gap).to_csv(tmp_path / "data.csv", index=False)
    run = subprocess.run(
        [sys.executable, module.__file__, "--json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    report = json.loads(run.stdout)
    validate(report, SCHEMA)
    assert report == json.loads((tmp_path / "matrix.report.json").read_text())
    assert run.returncode == report["exit_code"] == (2 if gap else 0), report
    assert report["status"] == ("incomplete" if gap else "passed")
    assert report["policy"]["strict"]
    assert report["annotations"][0]["resolved"]["value"] == 6
    exported_files(report, tmp_path)
