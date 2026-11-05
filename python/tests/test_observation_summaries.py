"""Verify actual rendered estimates and intervals against source membership."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from importlib.resources import files

import jsonschema
import pytest

from graphunslopify import Figure
from graphunslopify.numerical_cache import ACTIVE, NumericalCache
from graphunslopify.observation_provenance import (
    ObservationLedger,
    _read_observation_selection,
)
from graphunslopify.preview_render import _execute


def summary_evidence(report, directory):
    selection = report["observation_selection"]
    path = _read_observation_selection(
        directory,
        report,
        run_id=selection["run_id"],
        program_sha256=report["script"]["sha256"],
    )
    ledger = ObservationLedger.from_json(path.read_bytes())
    nodes = {node["id"]: node for node in ledger.as_dict()["nodes"]}
    root = nodes[selection["summary_node_id"]]
    return ledger, root, [nodes[ref] for ref in root["inputs"]], nodes


@pytest.fixture
def measurements(tmp_path):
    source = tmp_path / "measurements.csv"
    source.write_text(
        "x,series,y,unit,keep\n"
        "1,A,8,u,1\n1,A,12,v,1\n1,A,bad,u,1\n1,A,inf,v,1\n1,A,,w,1\n"
        "1,A,90,,1\n2,A,2,w,1\n2,A,4,w,1\n3,A,100,,1\n,A,100,u,1\n"
        "1,B,100,u,0\n"
    )
    return (
        Figure.line(source)
        .x("x", "X")
        .y("y", "Y")
        .by("series")
        .aggregate("mean")
        .where("keep", "eq", 1)
        .output(formats=["png"], dpi=100)
    )


@pytest.mark.parametrize(
    ("interval", "bounds", "detail"),
    [
        ("std", [10 - 2**1.5, 10 + 2**1.5], {"ddof": 1}),
        ("sem", [8, 12], {"ddof": 1}),
        ("range", [8, 12], {}),
        ("iqr", [9, 11], {"quantiles": [0.25, 0.75]}),
        (
            "ci",
            [8, 12],
            {
                "bootstrap": {
                    "method": "percentile",
                    "statistic": "mean",
                    "seed": 20260902,
                    "draws": 2000,
                    "level": 0.9,
                }
            },
        ),
    ],
)
def test_actual_estimator_reports_exact_members_and_interval_policies(
    tmp_path, measurements, interval, bounds, detail
):
    figure = measurements.set(
        uncertainty={"kind": interval, "level": 0.9, "display": "band", "over": "unit"}
    )
    result = figure.render(cwd=tmp_path / "trace", strict=False, trace_observations=True)
    report = result["report"]
    schema = files("graphunslopify").joinpath("schemas", "runtime-report.schema.json")
    jsonschema.Draft202012Validator(json.loads(schema.read_text(encoding="utf8"))).validate(report)
    ledger, root, (panel,), nodes = summary_evidence(report, result["script"].parent)
    assert panel["metadata"] == {"field": "y", "panel": 0, "unit_field": "unit"}
    first, interval_node, second, unavailable = [nodes[ref] for ref in panel["inputs"]]
    assert first["operation"] == second["operation"] == "summary_estimate"
    assert first["value"] == 10 and second["value"] == 3
    assert interval_node["operation"] == "summary_interval"
    assert interval_node["value"] == pytest.approx(bounds)
    assert interval_node["metadata"]["estimator"] == interval
    assert {key: interval_node["metadata"][key] for key in detail} == detail
    explanation = ledger.explain(interval_node["id"])
    assert explanation["contributing_records"] == [0, 1]
    assert explanation["excluded_records"] == [2, 3, 4, 5]
    assert {item["reason"] for item in explanation["nodes"] if item["kind"] == "exclusion"} == {
        "invalid_numeric_measurement",
        "nonfinite_measurement",
        "missing_measurement",
        "missing_unit_identifier",
        "unusable_unit_measurement",
    }
    assert unavailable["value"] == [None, None]
    assert unavailable["metadata"]["unavailable"] == "insufficient_measurements"
    assert ledger.explain(unavailable["id"])["contributing_records"] == [6, 7]
    support = nodes[second["inputs"][0]]
    assert support["value"] == 1
    assert nodes[support["inputs"][0]]["operation"] == "technical_repeat_summary"
    assert ledger.explain(root["id"])["excluded_records"] == [2, 3, 4, 5, 8, 9]
    assert ledger.explain(report["observation_selection"]["node_id"])["excluded_records"] == [10]

    if interval == "std":
        altered = copy.deepcopy(report)
        reference = altered["observation_selection"]
        reference["summary_node_id"] = reference["preparation_node_id"]
        with pytest.raises(ValueError, match="summary root"):
            summary_evidence(altered, result["script"].parent)


@pytest.mark.parametrize(("how", "values"), [("count", [2, 0]), ("sum", [7, None])])
def test_bar_summary_measures_count_and_empty_sum(tmp_path, how, values):
    source = tmp_path / "data.csv"
    source.write_text("x,y\nfirst,2\nsecond,\nfirst,5\nfirst,\n")
    result = (
        Figure.bar(source)
        .x("x", "X")
        .y("y", "Y")
        .aggregate(how)
        .output(formats=["png"], dpi=100)
        .render(cwd=tmp_path / "trace", strict=False, trace_observations=True)
    )
    ledger, _, (panel,), nodes = summary_evidence(result["report"], result["script"].parent)
    estimate = [nodes[ref] for ref in panel["inputs"]]
    assert [node["value"] for node in estimate] == values
    assert [ledger.explain(node["id"])["contributing_records"] for node in estimate] == [
        [0, 2],
        [],
    ]
    assert [ledger.explain(node["id"])["excluded_records"] for node in estimate] == [
        [3],
        [1],
    ]


@pytest.mark.parametrize("layout", ["nested_facet", "repeat"])
def test_panel_mapping_follows_actual_facet_masks_and_metrics(tmp_path, layout):
    source = tmp_path / "panels.csv"
    source.write_text(
        "x,y,z,site,condition\n"
        "1,6,60,b,two\n1,4,40,a,one\n1,8,80,b,two\n1,2,20,a,one\n1,100,1000,,one\n"
    )
    figure = Figure.line(source).x("x", "X").y("y", "Y").aggregate("median")
    if layout == "nested_facet":
        figure.facet("condition", rows="site", columns=2).where("site", "in", ["a", "b"])
        expected = [(0, "y", 7, [0, 2]), (3, "y", 3, [1, 3])]
    else:
        figure.set(repeat={"fields": ["y", "z"]})
        expected = [(0, "y", 6, list(range(5))), (1, "z", 60, list(range(5)))]
    result = figure.output(formats=["png"], dpi=100).render(
        cwd=tmp_path / "trace", strict=False, trace_observations=True
    )
    ledger, root, panels, nodes = summary_evidence(result["report"], result["script"].parent)
    measured = []
    for panel in panels:
        (estimate,) = [nodes[ref] for ref in panel["inputs"]]
        measured.append(
            (
                panel["metadata"]["panel"],
                panel["metadata"]["field"],
                estimate["value"],
                ledger.explain(estimate["id"])["contributing_records"],
            )
        )
    assert measured == expected
    assert ledger.explain(root["id"])["excluded_records"] == []
    assert ledger.explain(result["report"]["observation_selection"]["node_id"])[
        "excluded_records"
    ] == ([4] if layout == "nested_facet" else [])


def test_cached_preview_rebinds_the_witness_to_each_real_render(
    tmp_path, monkeypatch, measurements
):
    monkeypatch.chdir(tmp_path)
    cache = NumericalCache("a" * 64)
    readings = []
    for index in (1, 2):
        figure = measurements.average_over("unit").set(title=f"Run {index}")
        code = figure.translate(api="local", trace_observations=True)["code"].encode()
        script = tmp_path / f"script-{index}.py"
        report_path = tmp_path / f"report-{index}.json"
        script.write_bytes(code)
        run_id = f"{index:032x}"
        monkeypatch.setenv("GRAPHUNSLOPIFY_OBSERVATION_RUN_ID", run_id)
        monkeypatch.setattr(sys, "argv", [str(script), "--no-strict", "--report", str(report_path)])
        request = cache.request()
        token = ACTIVE.set(request)
        try:
            with pytest.raises(SystemExit) as status:
                _execute(script)
            assert status.value.code == 0
        finally:
            ACTIVE.reset(token)
        report = json.loads(report_path.read_text())
        assert report["observation_selection"]["run_id"] == run_id
        assert report["script"]["sha256"] == hashlib.sha256(code).hexdigest()
        ledger, root, (panel,), nodes = summary_evidence(report, tmp_path)
        interval = nodes[panel["inputs"][1]]
        readings.append((root["id"], ledger.explain(interval["id"]), request.trace()))
    cold, warm = readings
    assert cold[0] != warm[0] and cold[1]["node_id"] != warm[1]["node_id"]
    assert cold[1]["contributing_records"] == warm[1]["contributing_records"] == [0, 1]
    assert cold[1]["excluded_records"] == warm[1]["excluded_records"] == [2, 3, 4, 5]
    cold_counts = cold[2]["functions"]["_summarise_with_membership"]
    warm_counts = warm[2]["functions"]["_summarise_with_membership"]
    assert cold_counts["misses"] == cold_counts["stores"] == 1
    assert warm_counts["hits"] >= 1 and "misses" not in warm_counts
