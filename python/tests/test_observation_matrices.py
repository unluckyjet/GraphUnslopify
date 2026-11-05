"""Verify that generated matrix cells trace the actual plotted values and observations."""

from __future__ import annotations

import copy
import json
import runpy
from importlib.resources import files

import jsonschema
import matplotlib.pyplot as plt
import numpy as np
import pytest

from graphunslopify import Figure, SpecError
from graphunslopify.observation_provenance import ObservationLedger, _read_observation_selection


def matrix_figure(kind, path, **settings):
    return Figure(
        {
            "kind": kind,
            "data": {"path": str(path)},
            "x": {"field": "x", "label": "Column"},
            "y": {"field": "y", "label": "Row"},
            "legend": {"show": False},
            "annotate_cells": True,
            "output": {"stem": "matrix", "formats": ["png"], "dpi": 100},
            **settings,
        }
    )


def matrix_evidence(result):
    report = result["report"]
    reference = report["observation_selection"]
    path = _read_observation_selection(
        result["script"].parent,
        report,
        run_id=reference["run_id"],
        program_sha256=report["script"]["sha256"],
    )
    ledger = ObservationLedger.from_json(path.read_bytes())
    nodes = {node["id"]: node for node in ledger.as_dict()["nodes"]}
    root = nodes[reference["matrix_node_id"]]
    assert root["operation"] == "matrix_panels"
    return ledger, [nodes[node] for node in root["inputs"]], nodes


def cells(panel, nodes):
    assert panel["operation"] == "matrix_panel"
    rows, columns = panel["metadata"]["shape"]
    assert panel["value"] == rows * columns == len(panel["inputs"])
    cell_nodes = [nodes[node] for node in panel["inputs"]]
    assert all(cell["operation"] == "matrix_cell" for cell in cell_nodes)
    assert [(node["metadata"]["row"], node["metadata"]["column"]) for node in cell_nodes] == [
        (row, col) for row in range(rows) for col in range(columns)
    ]
    return cell_nodes


@pytest.mark.parametrize(
    ("reducer", "value"),
    [
        ("mean", [10 / 3, None, 0, None, 8, None]),
        ("median", [2, None, 0, None, 8, None]),
        ("sum", [10, None, 0, None, 16, None]),
        ("count", [3, None, 1, 0, 2, None]),
    ],
)
def test_heatmap_keeps_masked_absent_all_missing_and_observed_zero(tmp_path, reducer, value):
    source = tmp_path / "matrix.csv"
    source.write_text(
        "x,y,w,keep\n01,b,1,1\n1,a,8,1\n01,b,7,1\n01,a,,1\n01,b,2,1\n"
        "2,b,0,1\n1,a,,1\n1,a,8,1\n2,a,99,0\n"
    )
    figure = matrix_figure("heatmap", source, value="w", value_label="Weight", aggregation=reducer)
    result = figure.where("keep", "eq", 1).render(
        cwd=tmp_path / "trace", strict=False, trace_observations=True
    )
    ledger, (panel,), nodes = matrix_evidence(result)
    quantities = cells(panel, nodes)
    assert [node["value"] for node in quantities] == value
    assert [node["metadata"]["membership"] for node in quantities] == [
        "observed",
        "unobserved",
        "observed",
        "all_missing",
        "observed",
        "unobserved",
    ]
    assert [node["metadata"]["column_label"] for node in quantities] == ["01", "1", "2"] * 2
    assert [ledger.explain(node["id"])["contributing_records"] for node in quantities] == [
        [0, 2, 4],
        [],
        [5],
        [],
        [1, 7],
        [],
    ]
    assert [ledger.explain(node["id"])["excluded_records"] for node in quantities] == [
        [],
        [],
        [],
        [3],
        [6],
        [],
    ]
    filter_root = result["report"]["observation_selection"]["node_id"]
    assert ledger.explain(filter_root)["excluded_records"] == [8]
    assert all("annotation" not in node["metadata"] for node in quantities if node["value"] is None)
    if reducer == "mean":
        schema = files("graphunslopify").joinpath("schemas", "runtime-report.schema.json")
        jsonschema.Draft202012Validator(json.loads(schema.read_text())).validate(result["report"])
        tampered = copy.deepcopy(result)
        tampered["report"]["observation_selection"]["matrix_node_id"] = panel["id"]
        with pytest.raises(ValueError, match="matrix root"):
            matrix_evidence(tampered)


@pytest.mark.parametrize("weighted", [False, True])
@pytest.mark.parametrize("normalization", ["none", "row", "column"])
def test_confusion_cells_bind_distinct_numerator_and_denominator_records(
    tmp_path, weighted, normalization
):
    source = tmp_path / "matrix.csv"
    columns = "x,y,w" if weighted else "x,y"
    observations = [
        ("01", "01", "3"),
        ("1", "01", "2"),
        ("01", "1", "1"),
        ("01", "01", "3"),
        ("1", "1", "0"),
        ("1", "2", "0"),
    ]
    source.write_text(
        columns
        + "\n"
        + "\n".join(",".join(row if weighted else row[:2]) for row in observations)
        + "\n"
    )
    result = matrix_figure(
        "confusion_matrix", source, normalize=normalization, **({"value": "w"} if weighted else {})
    ).render(cwd=tmp_path / "trace", strict=False, trace_observations=True)
    ledger, (panel,), nodes = matrix_evidence(result)
    quantities = cells(panel, nodes)
    raw = [[6, 2, 0], [1, 0, 0], [0, 0, 0]] if weighted else [[2, 1, 0], [1, 1, 0], [0, 1, 0]]
    membership = [[[0, 3], [1], []], [[2], [4], []], [[], [5], []]]
    assert panel["metadata"]["normalization"] == normalization
    for cell in quantities:
        metadata = cell["metadata"]
        row, column = metadata["row"], metadata["column"]
        contributors = membership[row][column]
        assert metadata["membership"] == ("observed" if contributors else "unobserved")
        if normalization == "none":
            assert cell["value"] == raw[row][column]
            assert metadata["annotation"] == str(raw[row][column])
            assert ledger.explain(cell["id"])["contributing_records"] == contributors
            continue
        numerator, denominator = [nodes[node] for node in cell["inputs"]]
        assert numerator["operation"] == "matrix_count"
        assert numerator["value"] == raw[row][column]
        assert ledger.explain(numerator["id"])["contributing_records"] == contributors
        assert denominator["operation"] == "matrix_normalization_total"
        if normalization == "row":
            total = sum(raw[row])
            scope = sorted(item for group in membership[row] for item in group)
        else:
            total = sum(line[column] for line in raw)
            scope = sorted(item for line in membership for item in line[column])
        assert denominator["value"] == total
        assert ledger.explain(denominator["id"])["contributing_records"] == scope
        assert metadata["zero_total"] == (total == 0)
        expected = raw[row][column] / total if total else 0.0
        assert cell["value"] == expected
        assert metadata["annotation"] == f"{expected:.2f}"
    assert any(node.get("operation") == "confusion_weight" for node in nodes.values()) == weighted


def test_matrix_native_artist_ids_and_nested_facet_transform_dependencies(tmp_path, monkeypatch):
    source = tmp_path / "matrix.csv"
    source.write_text(
        "x,y,w,site,subset\n01,row,2,left,one\n01,row,6,left,one\n"
        "1,row,8,right,two\n1,row,12,right,two\n"
    )
    result = (
        matrix_figure("heatmap", source, value="w", value_label="Weight", aggregation="mean")
        .facet("subset", rows="site", columns=2)
        .set(transform={"kind": "normalize"})
        .render(cwd=tmp_path / "trace", strict=False, trace_observations=True)
    )
    ledger, panels, nodes = matrix_evidence(result)
    assert [panel["metadata"]["panel"] for panel in panels] == [0, 3]
    expected = [0.2, 0.8]
    for panel, value in zip(panels, expected, strict=True):
        (cell,) = cells(panel, nodes)
        assert cell["value"] == pytest.approx(value)
        assert len(cell["inputs"]) == 2
        assert ledger.explain(cell["id"])["contributing_records"] == [0, 1, 2, 3]
        assert any(
            node.get("operation") == "normalization_range" and node["value"] == [2, 12]
            for node in ledger.explain(cell["id"])["nodes"]
        )

    monkeypatch.chdir(result["script"].parent)
    program = runpy.run_path(str(result["script"]))
    context = program["draw_panel"].__globals__
    loaded, selection = context["load"]()
    prepared = context["prepare"](loaded, selection)
    context["OBSERVATION_CAPTURE"] = selection
    figure, axes = plt.subplots()
    try:
        panels = context["panels"](prepared)
        context["draw_panel"](axes, panels[3][1])
        (image,) = axes.images
        ((node_id,),) = image._graphunslopify_matrix_node_ids
        explanation = selection.ledger.explain(node_id)
        (cell,) = [node for node in explanation["nodes"] if node["id"] == node_id]
        assert cell["metadata"]["annotation"] == axes.texts[0].get_text()
        np.testing.assert_array_equal(image.get_array(), [[cell["value"]]])
        assert cell["metadata"]["column_label"] == "1"
    finally:
        plt.close(figure)


def test_invalid_confusion_weights_keep_preparation_without_a_matrix(tmp_path):
    source = tmp_path / "invalid.csv"
    source.write_text("x,y,w\n01,01,1\n1,01,-1\n")
    with pytest.raises(SpecError, match="confusion counts must be finite"):
        matrix_figure("confusion_matrix", source, value="w", normalize="row").render(
            cwd=tmp_path / "trace", strict=False, trace_observations=True
        )
    report = json.loads((tmp_path / "trace/matrix.report.json").read_text())
    assert "preparation_node_id" in report["observation_selection"]
    assert "matrix_node_id" not in report["observation_selection"]
