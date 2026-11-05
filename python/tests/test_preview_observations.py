"""Observation explorer contracts exercised through actual local render requests."""

from __future__ import annotations

import hashlib
import json

import pytest
from test_preview import request

pytest_plugins = ("test_preview",)

_QUERY = "/api/observations/query"
_DOWNLOAD = "/api/observations/download"


def post(editor, route, payload):
    status, raw = request(editor, route, payload)
    assert status == 200, raw
    return json.loads(raw)


@pytest.fixture
def traced_matrix(editor):
    source = b"truth,prediction\nfirst,first\nfirst,second\nfirst,first\nsecond,first\n"
    status, body = request(editor, "/api/upload", source, headers={"X-Filename": "classes.csv"})
    assert status == 200, body
    data_id = json.loads(body)["id"]
    payload = {
        "client": "matrix-explorer",
        "generation": 3,
        "data_id": data_id,
        "spec": {
            "kind": "confusion_matrix",
            "x": {"field": "prediction", "label": "Predicted class"},
            "y": {"field": "truth", "label": "Observed class"},
            "normalize": "row",
            "annotate_cells": True,
            "output": {"stem": "classes", "formats": ["png"], "dpi": 300, "size": "double_column"},
        },
        "trace_observations": True,
    }
    result = post(editor, "/api/render", payload)
    assert result["report"]["ok"] and result["exit_code"] == 0, result["report"]["findings"]
    binding = result["observations"]
    assert binding["available"], binding
    assert binding["grids"] == [{"rows": 2, "columns": 2}]
    owner = {
        "run_id": result["run_id"],
        "render_client": payload["client"],
        "render_generation": payload["generation"],
        "image_sha256": binding["image"]["sha256"],
    }
    return result, owner, payload


def test_owned_confusion_cell_uses_actual_numerator_and_denominator(editor, traced_matrix):
    result, owner, payload = traced_matrix
    cell = {**owner, "cell": [0, 0, 0]}
    selected = post(editor, _QUERY, cell)["selection"]
    assert selected["node"]["value"] == pytest.approx(2 / 3)
    assert selected["contributing_records"]["items"] == [0, 1, 2]
    assert selected["excluded_records"]["items"] == []
    edge = selected["inputs"]["items"][0]["id"]
    counted = post(editor, _QUERY, {**owner, "node_id": edge})["selection"]
    assert counted["node"]["value"] == 2
    assert counted["contributing_records"]["items"] == [0, 2]

    reference = result["report"]["observation_selection"]
    assert reference["path"] not in {file["name"] for file in result["files"]}
    status, raw = request(editor, _DOWNLOAD, {**owner, "document": "graph"})
    assert status == 200 and hashlib.sha256(raw).hexdigest() == reference["sha256"]
    status, raw = request(editor, _DOWNLOAD, {**owner, "document": "program"})
    assert status == 200 and hashlib.sha256(raw).hexdigest() == result["report"]["script"]["sha256"]

    assert request(editor, _QUERY, cell, token=False)[0] == 403
    assert request(editor, _QUERY, cell, headers={"Origin": "https://example.org"})[0] == 403
    assert request(editor, _QUERY, {**cell, "render_client": "other"})[0] == 400
    assert request(editor, _QUERY, {**cell, "image_sha256": "0" * 64})[0] == 400
    assert request(editor, _QUERY, {**cell, "position": [0, 0]})[0] == 400
    assert post(editor, _QUERY, {**owner, "position": [-1, -1]})["selection"] is None

    ordinary = post(editor, "/api/render", {**payload, "trace_observations": False})
    assert "observations" not in ordinary and "observation_selection" not in ordinary["report"]
    assert request(editor, _QUERY, cell)[0] == 400


def test_owned_query_refuses_mutated_inputs_and_evidence_during_lookup(
    editor, traced_matrix, monkeypatch
):
    result, owner, payload = traced_matrix
    cell = {**owner, "cell": [0, 0, 0]}
    run = editor.state.runs[result["run_id"]]
    folder = run["folder"]
    png = folder / result["observations"]["image"]["path"]
    graph = folder / result["report"]["observation_selection"]["path"]

    for path in (
        editor.state.uploads[payload["data_id"]]["path"],
        folder / "classes.py",
        folder / "classes.figure.json",
        folder / "classes.report.json",
        png,
        graph,
    ):
        original = path.read_bytes()
        path.write_bytes(original + b"\nchanged")
        try:
            assert request(editor, _QUERY, cell)[0] == 400, path.name
            assert request(editor, _DOWNLOAD, {**owner, "document": "graph"})[0] == 400, path.name
        finally:
            path.write_bytes(original)

    original = graph.read_bytes()
    page = editor.state.observations._page

    def change_graph(*args):
        answer = page(*args)
        graph.write_bytes(original + b"\nchanged during lookup")
        return answer

    monkeypatch.setattr(editor.state.observations, "_page", change_graph)
    status, body = request(editor, _QUERY, cell)
    assert status == 400
    assert json.loads(body)["error"] == "The observation graph changed; render again"
