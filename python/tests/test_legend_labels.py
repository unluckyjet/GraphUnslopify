"""Literal display names must not replace source/claim identity."""

from __future__ import annotations

import json
import re

import pytest

from graphunslopify import read_provenance
from graphunslopify.preview import PreviewState


def render(
    tmp_path,
    labels,
    *,
    style="box",
    data=None,
    claims=None,
    group="model",
    kind="line",
    interactive=False,
    layers=None,
):
    state = PreviewState(tmp_path, 1024 * 1024)
    uploaded = state.upload(
        "experiment.csv", data or b"epoch,score,model\n1,7,base\n2,11,base\n1,8,ours\n2,13,ours\n"
    )
    spec = {
        "kind": kind,
        "x": {"field": "epoch", "label": "Epoch"},
        "y": {"field": "score", "label": "Score"},
        "legend": {"style": style, "position": "outside_bottom", "labels": labels},
        "output": {
            "formats": ["png", "svg", "pdf"],
            "size": "double_column",
            "interactive": interactive,
        },
    }
    if kind == "bar":
        spec["interval"] = "none"
    if group is not None:
        spec["group"] = group
    if claims:
        spec["claims"] = claims
    if layers:
        spec["layers"] = layers
    result = state.render(
        {"client": "aliases", "generation": 1, "data_id": uploaded["id"], "spec": spec}
    )
    return state, result


@pytest.mark.parametrize("style", ["box", "direct"])
def test_aliases_are_actual_rendered_text_while_claim_subjects_and_data_remain_original(
    tmp_path, style
):
    labels = [
        {"series": "base", "text": "Control <literal>"},
        {"series": "ours", "text": "Treatment"},
    ]
    state, result = render(
        tmp_path,
        labels,
        style=style,
        claims=[
            {"kind": "beats_everywhere", "subject": "ours", "reference": "base"},
        ],
    )
    assert result["report"]["ok"], result["report"]
    targets = [item for item in result["edit_map"]["targets"] if item["role"] == "legend_entry"]
    assert {item["source"]: item["text"] for item in targets} == {
        "base": "Control <literal>",
        "ours": "Treatment",
    }
    for item in targets:
        assert item["path"] == ["legend", "labels", 0 if item["source"] == "base" else 1, "text"]
    claim = result["report"]["claims"][0]
    assert (
        claim["subject"] == "ours" and claim["reference"] == "base" and claim["verdict"] == "holds"
    )
    assert "Control <literal> means source series base" in result["report"]["alt_text"]
    folder = state.runs[result["run_id"]]["folder"]
    assert (folder / "data.csv").read_bytes().endswith(b"2,13,ours\n")
    for output in result["report"]["outputs"]:
        provenance = read_provenance(folder / output["path"])
        assert provenance["spec"]["legend"]["labels"] == labels
        assert "Control <literal> means source series base" in provenance["alt_text"]


@pytest.mark.parametrize(
    ("labels", "message"),
    [
        ([{"series": "missing", "text": "Control"}], "unknown source series"),
        ([{"series": "base", "text": "A"}, {"series": "base", "text": "B"}], "only one"),
        (
            [{"series": "base", "text": "Same"}, {"series": "ours", "text": "Same"}],
            "uniquely identify",
        ),
        ([{"series": "ours", "text": "base"}], "uniquely identify"),
        (
            [{"series": "base", "text": "Control "}, {"series": "ours", "text": "Control"}],
            "uniquely identify",
        ),
        ([{"series": "base", "text": "   "}], "visible text"),
    ],
)
def test_ambiguous_or_stale_aliases_fail_strictly_instead_of_renaming_data(
    tmp_path, labels, message
):
    _, result = render(tmp_path, labels)
    assert result["report"]["status"] == "failed"
    assert result["exit_code"] != 0
    assert any(message in item["message"] for item in result["report"]["findings"])


def test_alias_record_values_preserve_special_source_names_without_object_key_semantics(tmp_path):
    data = b"epoch,score,model\n1,7,__proto__\n2,11,__proto__\n1,8,constructor\n2,13,constructor\n"
    labels = [
        {"series": "__proto__", "text": "_Control"},
        {"series": "constructor", "text": "Treatment"},
    ]
    _, result = render(tmp_path, labels, data=data)
    assert result["report"]["ok"]
    assert result["report"]["spec"]["legend"]["labels"] == labels
    assert {
        target["source"]
        for target in result["edit_map"]["targets"]
        if target["role"] == "legend_entry"
    } == {"__proto__", "constructor"}
    assert any(item["text"] == "_Control" for item in result["edit_map"]["targets"])


@pytest.mark.parametrize("kind", ["line", "scatter", "bar"])
def test_interactive_exports_show_literal_aliases_and_retain_source_ids_and_values(tmp_path, kind):
    state, result = render(
        tmp_path, [{"series": "base", "text": "Control <literal>"}], kind=kind, interactive=True
    )
    assert result["report"]["ok"], result["report"]
    folder = state.runs[result["run_id"]]["folder"]
    html = next(item for item in result["report"]["outputs"] if item["format"] == "html")
    body = (folder / html["path"]).read_text()
    start = re.search(
        r'Plotly\.newPlot\(\s*"figure-' + result["report"]["spec_hash"] + r'"\s*,\s*', body
    )
    assert start is not None
    traces, _ = json.JSONDecoder().raw_decode(body[start.end() :])
    grouped = {trace["meta"]["source_series"]: trace for trace in traces if "meta" in trace}
    assert grouped["base"]["name"] == "Control &lt;literal&gt;"
    assert grouped["ours"]["name"] == "ours"
    assert grouped["base"]["y"] == [7.0, 11.0]
    assert grouped["ours"]["y"] == [8.0, 13.0]


def test_aliases_without_a_source_group_fail_with_an_explicit_problem(tmp_path):
    _, result = render(tmp_path, [{"series": "base", "text": "Control"}], group=None)
    assert result["report"]["status"] == "failed"
    assert any(
        "source grouping column" in finding["message"] for finding in result["report"]["findings"]
    )


def test_same_named_reference_entry_is_not_mistaken_for_a_source_series(tmp_path):
    _, result = render(
        tmp_path,
        [{"series": "base", "text": "Control"}],
        layers=[
            {"mark": "rule", "value": 9, "label": "base"},
        ],
    )
    assert result["report"]["ok"], result["report"]
    entries = [item for item in result["edit_map"]["targets"] if item["role"] == "legend_entry"]
    assert {(item["text"], item["editable"]) for item in entries} == {
        ("Control", True),
        ("ours", True),
        ("base", False),
    }


def test_alias_must_not_collapse_a_series_and_a_reference_to_the_same_name(tmp_path):
    _, result = render(
        tmp_path,
        [{"series": "base", "text": "Control"}],
        layers=[
            {"mark": "rule", "value": 9, "label": "Control"},
        ],
    )
    assert result["report"]["status"] == "failed"
    assert any(
        "another visible legend entry" in finding["message"]
        for finding in result["report"]["findings"]
    )
