"""Check generated preparation evidence against independent row and value expectations."""

from __future__ import annotations

import copy
import runpy
from decimal import Decimal

import pandas as pd
import pytest

from graphunslopify import Figure, SpecError
from graphunslopify.observation_provenance import (
    ObservationLedger,
    _read_observation_selection,
)


def preparation(result):
    report = result["report"]
    ledger = ObservationLedger.from_json(result["observation_path"].read_bytes())
    nodes = {item["id"]: item for item in ledger.as_dict()["nodes"]}
    reference = report["observation_selection"]
    root = nodes[reference["preparation_node_id"]]
    assert root["operation"] == "prepared_selection"
    assert root["value"] == len(root["inputs"]) == report["data"]["counts"]["prepared"]
    return ledger, nodes, root


@pytest.mark.parametrize(
    ("kind", "order", "values"),
    [
        ("delta_vs_baseline", [1, 3, 5, 7, 8], [8, 16, 12, None, None]),
        ("percent_of_baseline", [1, 3, 5, 7, 8], [300, 500, 400, None, None]),
        ("cumulative", [1, 5, 3, 7, 8, 2, 4, 0], [12, 28, 48, None, 78, 2, 8, 12]),
        ("normalize", [0, 1, 2, 3, 4, 5, 7, 8], [0.5, 0, 0, 4 / 9, 1, 2 / 9, None, 1]),
    ],
)
def test_generated_transforms_keep_actual_values_and_scoped_inputs(tmp_path, kind, order, values):
    source = tmp_path / "data.csv"
    source.write_text(
        'x,g,y,keep,note\n2,base,4,1,r0\n1,alt,12,1,"quoted\nrecord"\n'
        "1,base,2,1,r2\n2,alt,20,1,r3\n1,base,6,1,r4\n1,alt,16,1,r5\n"
        "1,alt,100,0,r6\n2,alt,,1,r7\n3,alt,30,1,r8\n"
    )
    transform = {"kind": kind}
    if "baseline" in kind:
        transform["baseline"] = "base"
    figure = (
        Figure.line(source)
        .x("x", "Time")
        .y("y", "Score")
        .by("g")
        .aggregate("mean")
        .set(transform=transform, filter=[{"field": "keep", "op": "eq", "value": 1}])
        .output(formats=["png"])
    )
    result = figure.render(cwd=tmp_path / "traced", strict=False, trace_observations=True)
    ledger, nodes, root = preparation(result)
    assert len(root["inputs"]) == len(order)
    measurements = {}
    for expected_position, expected_value, row_id in zip(
        order, values, root["inputs"], strict=True
    ):
        row = nodes[row_id]
        assert row["operation"] == "prepared_observation"
        assert row["metadata"]["measurement_fields"] == ["y"]
        assert ledger.explain(row["inputs"][0])["contributing_records"] == [expected_position]
        value_id = row["inputs"][1]
        node = nodes[value_id]
        assert node["operation"] == kind
        assert node["value"] == (None if expected_value is None else pytest.approx(expected_value))
        assert node["metadata"]["value_status"] == (
            "missing" if expected_value is None else "finite"
        )
        measurements[expected_position] = ledger.explain(value_id)
    selection = ledger.explain(root["id"])
    assert 6 in selection["excluded_records"] and 6 not in selection["contributing_records"]
    if "baseline" in kind:
        assert measurements[1]["contributing_records"] == [1, 2, 4]
        assert measurements[3]["contributing_records"] == [0, 3]
        assert measurements[8]["excluded_records"] == [8]
        assert {
            node["reason"] for node in measurements[8]["nodes"] if node["kind"] == "exclusion"
        } == {"baseline_unmatched"}
        hidden = next(
            node for node in selection["nodes"] if node.get("reason") == "baseline_hidden"
        )
        assert ledger.explain(hidden["id"])["excluded_records"] == [0, 2, 4]
        assert {0, 2, 4} <= set(selection["contributing_records"])
    elif kind == "cumulative":
        assert measurements[8]["contributing_records"] == [1, 3, 5, 8]
        assert measurements[8]["excluded_records"] == [7]
        assert measurements[7]["excluded_records"] == [7]
        assert measurements[0]["contributing_records"] == [0, 2, 4]
    else:
        assert measurements[1]["contributing_records"] == [1, 3, 5, 8]
        assert measurements[1]["excluded_records"] == [7]
        assert measurements[0]["contributing_records"] == [0, 2, 4]


def test_wide_reshape_keeps_duplicate_positions_and_actual_frame_dtypes(tmp_path, monkeypatch):
    pytest.importorskip("pyarrow")
    source = tmp_path / "wide.parquet"
    pd.DataFrame(
        {
            "x": [2, 1, 1],
            "01": ["4", "2", "2"],
            "1": ["8", None, None],
            "_graphunslopify_lineage_position": ["a", "b", "b"],
        },
        index=[7, 7, 7],
    ).to_parquet(source)
    figure = (
        Figure.scatter(source)
        .x("x", "Time")
        .y("value", "Score")
        .set(series_from_columns={"fields": ["01", "1"]}, legend={"show": False})
        .output(formats=["png"])
    )
    untraced = figure.render(cwd=tmp_path / "untraced", strict=False)
    traced = figure.render(cwd=tmp_path / "traced", strict=False, trace_observations=True)
    ledger, nodes, root = preparation(traced)
    for row_id, column, ordinal in zip(
        root["inputs"], ["01"] * 3 + ["1"] * 3, [0, 1, 2] * 2, strict=True
    ):
        row = nodes[row_id]
        assert row["metadata"]["measurement_fields"] == ["value"]
        cell = nodes[row["inputs"][0]]
        assert cell["operation"] == "wide_reshape" and cell["metadata"]["source_field"] == column
        assert ledger.explain(cell["id"])["contributing_records"] == [ordinal]
        conversion = nodes[row["inputs"][1]]
        assert conversion["operation"] == "numeric_conversion"
        assert conversion["value"] == {"01": [4, 2, 2], "1": [8, None, None]}[column][ordinal]
    assert ledger.explain(root["id"])["excluded_records"] == [1, 2]
    assert traced["report"]["data"] == untraced["report"]["data"]
    frames = []
    for result in (untraced, traced):
        monkeypatch.chdir(result["script"].parent)
        program = runpy.run_path(str(result["script"]))
        loaded = program["load"]()
        frames.append(
            program["prepare"](*loaded) if isinstance(loaded, tuple) else program["prepare"](loaded)
        )
    pd.testing.assert_frame_equal(*frames, check_exact=True)
    assert frames[-1]["_graphunslopify_lineage_position"].tolist() == ["a", "b", "b"] * 2

    report = copy.deepcopy(traced["report"])
    evidence = report["observation_selection"]
    evidence["preparation_node_id"] = evidence["node_id"]
    with pytest.raises(ValueError, match="preparation root"):
        _read_observation_selection(
            traced["script"].parent,
            report,
            run_id=evidence["run_id"],
            program_sha256=report["script"]["sha256"],
        )


def test_constant_normalization_without_groups_records_the_actual_range(tmp_path):
    source = tmp_path / "constant.csv"
    source.write_text("x,y\n1,10\n2,10\n3,10\n")
    figure = (
        Figure.line(source)
        .x("x", "Time")
        .y("y", "Score")
        .set(transform={"kind": "normalize"})
        .output(formats=["png"])
    )
    ledger, nodes, root = preparation(
        figure.render(cwd=tmp_path / "trace", strict=False, trace_observations=True)
    )
    for row_id in root["inputs"]:
        value = nodes[nodes[row_id]["inputs"][1]]
        assert value["operation"] == "normalize" and value["value"] == 0
        bounds = nodes[value["inputs"][1]]
        assert bounds["value"] == [10, 10] and bounds["metadata"]["constant_range"]
        assert ledger.explain(bounds["id"])["contributing_records"] == [0, 1, 2]


def test_failed_preparation_keeps_the_completed_filter_evidence(tmp_path):
    source = tmp_path / "invalid.csv"
    source.write_text("x,y,keep\n1,unusable,1\n2,3,0\n")
    figure = (
        Figure.scatter(source)
        .x("x", "Time")
        .y("y", "Score")
        .set(filter=[{"field": "keep", "op": "eq", "value": 1}])
        .output(formats=["png"])
    )
    with pytest.raises(SpecError, match="requires finite numeric measurements") as error:
        figure.render(cwd=tmp_path, trace_observations=True)
    selection = error.value.report["observation_selection"]
    assert "preparation_node_id" not in selection
    ledger = ObservationLedger.from_json((tmp_path / selection["path"]).read_bytes())
    explanation = ledger.explain(selection["node_id"])
    assert explanation["contributing_records"] == [0] and explanation["excluded_records"] == [1]


def test_decimal_normalization_retains_the_exact_prepared_value(tmp_path):
    pytest.importorskip("pyarrow")
    source = tmp_path / "decimal.parquet"
    pd.DataFrame(
        {"x": [1, 2, 3], "y": [Decimal("1.000"), Decimal("4.000"), Decimal("10.000")]}
    ).to_parquet(source)
    figure = (
        Figure.line(source)
        .x("x", "Time")
        .y("y", "Score")
        .aggregate("mean")
        .set(transform={"kind": "normalize"})
        .output(formats=["png"])
    )
    ledger, nodes, root = preparation(
        figure.render(cwd=tmp_path / "trace", strict=False, trace_observations=True)
    )
    value = nodes[nodes[root["inputs"][1]]["inputs"][1]]
    assert value["value"] == "0.3333333333333333333333333333"
    assert value["metadata"]["numeric_encoding"] == "decimal"
    assert ledger.explain(value["id"])["contributing_records"] == [0, 1, 2]
