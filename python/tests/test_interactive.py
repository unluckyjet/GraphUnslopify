"""Cross-backend numeric checks use actual Matplotlib and Plotly artifacts."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from html.parser import HTMLParser
from importlib.util import find_spec
from pathlib import Path

import pytest

from graphunslopify import read_provenance

ROOT = Path(__file__).resolve().parents[2]


class Scripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.external = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.external.extend(value for key, value in attrs if key == "src")


def render(tmp_path, csv, extra=None, interactive=True):
    if interactive and find_spec("plotly") is None:
        pytest.skip("interactive extra is not installed")
    if shutil.which("node") is None:
        pytest.skip("Node is needed for the real emitter")
    spec = {
        "kind": "line",
        "x": {"field": "epoch", "label": "Epoch"},
        "y": {"field": "score", "label": "Score"},
        "group": "model",
        "aggregation": "mean",
        "legend": {"show": False},
        **(extra or {}),
    }
    if spec.get("group") is None:
        spec.pop("group", None)
    spec["output"] = {"stem": "figure", "formats": ["png"], "dpi": 100, "interactive": interactive}
    generated = subprocess.run(
        [
            "node",
            "--experimental-strip-types",
            "--input-type=module",
            "-e",
            (
                "import{translate}from'./src/translate.ts';import fs from'node:fs';"
                "process.stdout.write(JSON.stringify(translate(JSON.parse(fs.readFileSync(0,'utf8')))));"
            ),
        ],
        input=json.dumps(spec),
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    result = json.loads(generated.stdout)
    assert result.get("ok"), result
    (tmp_path / "figure.py").write_text(result["code"])
    (tmp_path / "results.csv").write_text(csv)
    (tmp_path / "driver.py").write_text("""import figure as m, json
try:
    import plotly.graph_objects as go
except ImportError:
    go = None
original_html = go.Figure.to_html if go else None
original_check = m.check
def capture(self, *args, **kwargs):
    traces = []
    for trace in self.data:
        item = {"type":trace.type, "name":trace.name}
        for field in ("x","y","z","mode","orientation","text"):
            value = getattr(trace,field,None)
            item[field] = list(value) if field in ("x","y","z","text") and value is not None else value
        for axis in ("x","y"):
            error = getattr(trace,"error_"+axis,None)
            if error is not None: item["error_"+axis] = error.to_plotly_json()
        traces.append(item)
    with open("plotly.json","w") as h:
        json.dump({"data":traces,"xaxis":self.layout.xaxis.to_plotly_json(),"yaxis":self.layout.yaxis.to_plotly_json()},h)
    return original_html(self,*args,**kwargs)
def check(fig):
    with open("static.json","w") as h:
        json.dump({"markers":[line.get_marker() for ax in fig.axes for line in ax.lines],
                   "lines":[list(map(float,line.get_ydata())) for ax in fig.axes for line in ax.lines],
                   "images":[image.get_array().tolist() for ax in fig.axes for image in ax.images]},h)
    return original_check(fig)
if go: go.Figure.to_html = capture
m.check = check
raise SystemExit(m.run_cli(["--strict","--json"]))
""")
    completed = subprocess.run(
        [sys.executable, "driver.py"], cwd=tmp_path, capture_output=True, text=True, check=False
    )
    report = json.loads(completed.stdout)
    assert completed.returncode == report["exit_code"]
    return (
        report,
        json.loads((tmp_path / "plotly.json").read_text())
        if (tmp_path / "plotly.json").exists()
        else None,
        json.loads((tmp_path / "static.json").read_text())
        if (tmp_path / "static.json").exists()
        else None,
    )


CSV = "epoch,score,model\n1,1,a\n1,2,a\n2,2,a\n2,3,a\n1,5,b\n1,6,b\n2,6,b\n2,7,b\n"


def test_line_summary_and_intervals_match_static_numeric_values(tmp_path):
    report, figure, static = render(tmp_path, CSV, {"uncertainty": {"kind": "sem"}})
    assert report["ok"]
    traces = [trace for trace in figure["data"] if trace["name"] in ("a", "b")]
    assert [trace["y"] for trace in traces] == static["lines"] == [[1.5, 2.5], [5.5, 6.5]]
    assert figure["data"][0]["y"] == [1.0, 2.0]
    assert figure["data"][1]["y"] == [2.0, 3.0]


@pytest.mark.parametrize("orientation", ["vertical", "horizontal"])
def test_grouped_bars_share_means_and_asymmetric_interval_fields(tmp_path, orientation):
    report, figure, _ = render(
        tmp_path,
        CSV,
        {
            "kind": "bar",
            "orientation": orientation,
            "uncertainty": {"kind": "sem", "display": "bar"},
        },
    )
    assert report["ok"]
    value_axis = "y" if orientation == "vertical" else "x"
    assert figure["data"][0]["type"] == "bar"
    assert figure["data"][0][value_axis] == [1.5, 2.5]
    assert figure["data"][0]["error_" + value_axis]["array"] == [0.5, 0.5]
    assert figure["yaxis" if orientation == "horizontal" else "xaxis"]["type"] == "category"


def test_heatmap_uses_requested_aggregation_and_describes_displayed_cells(tmp_path):
    report, figure, _ = render(
        tmp_path,
        "epoch,row,value\nA,R,1\nA,R,3\nB,R,2\nB,R,3\n",
        {
            "kind": "heatmap",
            "group": None,
            "x": {"field": "epoch", "label": "Column"},
            "y": {"field": "row", "label": "Row"},
            "value": "value",
            "value_label": "Value",
            "aggregation": "sum",
            "annotate_cells": True,
        },
    )
    assert report["ok"]
    assert figure["data"][0]["z"] == [[4.0, 5.0]]
    assert "Values run from 4 to 5" in report["alt_text"]
    assert figure["yaxis"]["autorange"] == "reversed"


def test_self_contained_html_has_no_external_scripts_and_keeps_safe_provenance(tmp_path):
    report, _, _ = render(tmp_path, CSV, {"alt_text": "Author </script><tag> & context"})
    body = (tmp_path / "figure.html").read_text()
    parsed = Scripts()
    parsed.feed(body)
    assert not parsed.external
    assert "Plotly.newPlot" in body and len(body) > 1_000_000
    assert "Author &lt;/script&gt;&lt;tag&gt; &amp; context" in body
    payload = body.split('id="graphunslopify-provenance">')[1].split("</script>")[0]
    evidence = json.loads(payload)
    assert evidence["alt_text"] == report["alt_text"]
    assert evidence["spec_hash"] == report["spec_hash"]
    assert evidence["runtime"] == report["script"]["runtime"]
    from graphunslopify import figure_runtime

    assert (
        evidence["runtime"]["source_sha256"]
        == hashlib.sha256(Path(figure_runtime.__file__).read_bytes()).hexdigest()
    )
    assert read_provenance(tmp_path / "figure.html") == evidence


def test_one_point_series_are_visible_in_both_backends(tmp_path):
    report, figure, static = render(tmp_path, "epoch,score,model\n1,1,a\n1,2,b\n")
    assert report["ok"]
    assert static["markers"] == ["o", "o"]
    assert all(trace["mode"] == "lines+markers" for trace in figure["data"])


def test_endpoint_comparison_does_not_mix_different_x_values(tmp_path):
    report, _, _ = render(tmp_path, "epoch,score,model\n1,100,a\n1,4,b\n2,9,b\n")
    assert "No finite measurement at that x for a" in report["alt_text"]
    assert "b is 9" in report["alt_text"]
    assert "a is highest" not in report["alt_text"]


def test_ordering_never_silently_filters_observed_series(tmp_path):
    report, figure, static = render(tmp_path, CSV, {"series_order": ["a"]})
    assert len(static["lines"]) == len(figure["data"]) == 2
    assert report["data"]["counts"]["unlisted_series"] == ["b"]
    assert any(item["code"] == "unlisted_series_retained" for item in report["findings"])


def test_log_limits_are_converted_to_plotly_exponents(tmp_path):
    report, figure, _ = render(
        tmp_path,
        CSV,
        {"y": {"field": "score", "label": "Score", "scale": "log", "limits": [1, 100]}},
    )
    assert report["ok"]
    assert figure["yaxis"]["range"] == [0, 2]


def test_all_invalid_measurements_cannot_pass_strict_verification(tmp_path):
    report, _, _ = render(tmp_path, "epoch,score,model\n1,,a\n2,,a\n")
    assert report["status"] == "incomplete"
    assert report["exit_code"] == 2
    assert any("no finite measurements" in reason for reason in report["untested"])


@pytest.mark.parametrize("normalize", ["none", "row", "column"])
def test_precomputed_confusion_counts_drive_both_plot_and_description(tmp_path, normalize):
    report, _, static = render(
        tmp_path,
        "epoch,label,count\nA,A,8\nB,A,2\nA,B,1\nB,B,9\n",
        {
            "kind": "confusion_matrix",
            "group": None,
            "y": {"field": "label", "label": "True class"},
            "value": "count",
            "normalize": normalize,
        },
        interactive=False,
    )
    assert report["ok"]
    assert "85.0% of 20 cases" in report["alt_text"]
    expected = {
        "none": [[8, 2], [1, 9]],
        "row": [[0.8, 0.2], [0.1, 0.9]],
        "column": [[8 / 9, 2 / 11], [1 / 9, 9 / 11]],
    }
    assert static["images"][0] == expected[normalize]


@pytest.mark.parametrize("count", ["-1", ""])
def test_invalid_precomputed_counts_cannot_become_zero_observations(tmp_path, count):
    report, _, _ = render(
        tmp_path,
        f"epoch,label,count\nA,A,8\nB,B,{count}\n",
        {
            "kind": "confusion_matrix",
            "group": None,
            "y": {"field": "label", "label": "True class"},
            "value": "count",
            "normalize": "none",
        },
        interactive=False,
    )
    assert report["status"] == "failed"
    assert report["exit_code"] == 1
    assert any("finite nonnegative integers" in item["message"] for item in report["findings"])


def test_sparse_precomputed_matrix_keeps_unobserved_cells_at_zero(tmp_path):
    report, _, static = render(
        tmp_path,
        "epoch,label,count\nA,A,8\nB,B,9\n",
        {
            "kind": "confusion_matrix",
            "group": None,
            "y": {"field": "label", "label": "True class"},
            "value": "count",
            "normalize": "none",
        },
        interactive=False,
    )
    assert report["ok"]
    assert static["images"][0] == [[8, 0], [0, 9]]
    assert "100.0% of 17 cases" in report["alt_text"]
