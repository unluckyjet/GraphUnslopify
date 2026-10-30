"""Display aliases keep raw metric/panel identity and actual rendered text separate."""

from __future__ import annotations

import pytest

from graphunslopify.preview import PreviewState

DATA = b"epoch,score,loss,model,condition,phase\n1,1,4,base,A,early\n2,2,3,base,A,early\n1,3,2,ours,A,early\n2,4,1,ours,A,early\n1,1,4,base,B,early\n2,2,3,base,B,early\n1,3,2,ours,B,early\n2,4,1,ours,B,early\n1,1,4,base,A,late\n2,2,3,base,A,late\n1,3,2,ours,A,late\n2,4,1,ours,A,late\n1,1,4,base,B,late\n2,2,3,base,B,late\n1,3,2,ours,B,late\n2,4,1,ours,B,late\n"


def render(tmp_path, layout, *, labels=None, claims=False, data=DATA, **extra):
    state = PreviewState(tmp_path, 1024 * 1024)
    source = state.upload("observations.csv", data)
    spec = {
        "kind": "line",
        "x": {"field": "epoch", "label": "Epoch"},
        "y": {"field": "score", "label": "Score"},
        "legend": {"show": False},
        "output": {"formats": ["png", "svg", "pdf"], "size": "double_column"},
    }
    if layout == "repeat":
        spec["repeat"] = {"fields": ["score", "loss"]}
    elif layout is not None:
        spec["facet"] = {"by": "condition", **({"rows": "phase"} if layout == "grid" else {})}
    if labels is not None:
        spec["repeat" if layout == "repeat" else "facet"]["labels"] = labels
    if claims:
        spec.update(
            group="model",
            claims=[{"kind": "beats_everywhere", "subject": "ours", "reference": "base"}],
        )
    spec.update(extra)
    return state.render(
        {"client": "panels", "generation": 1, "data_id": source["id"], "spec": spec}
    )


def targets(result, role):
    return [t for t in result["edit_map"]["targets"] if t["role"] == role]


def test_repeated_metric_axis_and_letter_heading_share_canonical_text_without_renaming_claims(
    tmp_path,
):
    raw = b"epoch,score,loss,model\n1,1,4,base\n2,2,3,base\n1,3,2,ours\n2,4,1,ours\n"
    before = render(
        tmp_path / "before",
        "repeat",
        claims=True,
        data=raw,
        y={"field": "score", "label": "Shared source", "unit": "points"},
    )
    result = render(
        tmp_path / "after",
        "repeat",
        labels=[{"field": "score", "text": "Quality"}, {"field": "loss", "text": "Error"}],
        claims=True,
        data=raw,
        y={"field": "score", "label": "Shared source", "unit": "points"},
    )
    assert result["report"]["status"] == before["report"]["status"] == "failed"
    signature = lambda r: [(c["metric"], c["subject"], c["verdict"]) for c in r["report"]["claims"]]
    assert (
        signature(result)
        == signature(before)
        == [("score", "ours", "holds"), ("loss", "ours", "fails")]
    )
    assert result["report"]["panels"] == before["report"]["panels"]
    assert result["report"]["data"]["sha256_prefix"] == before["report"]["data"]["sha256_prefix"]
    actual = targets(result, "metric_label")
    assert {t["text"] for t in actual} == {"Quality", "Error", "(a) Quality", "(b) Error"}
    assert all(t["editable"] and t["path"][:2] == ["repeat", "labels"] for t in actual)
    assert {t["value"] for t in actual} == {"Quality", "Error"}
    assert "Quality means source metric score" in result["report"]["alt_text"]
    defaults = targets(before, "metric_label")
    assert {t["value"] for t in defaults} == {"Score", "Loss"}
    assert {t["text"] for t in defaults} == {"Score", "Loss", "(a) Score", "(b) Loss"}
    assert all(t["path"][2] == 0 for t in defaults)  # Prospective append, not a panel index.


@pytest.mark.parametrize("layout", ["facet", "grid"])
def test_facet_heading_owns_source_values_and_preserves_report_names(tmp_path, layout):
    labels = [{"value": "A", "text": "Control", **({"row": "early"} if layout == "grid" else {})}]
    result = render(tmp_path, layout, labels=labels)
    assert result["report"]["ok"], result["report"]
    renamed = next(t for t in targets(result, "panel_title") if t["value"] == "Control")
    assert renamed["text"] == "(a) Control" and renamed["editable"]
    assert renamed["path"] == ["facet", "labels", 0, "text"]
    assert renamed["source"] == {"value": "A", **({"row": "early"} if layout == "grid" else {})}
    assert result["report"]["panels"][0]["name"] == ("early / A" if layout == "grid" else "A")
    assert "Control means source panel condition=A" in result["report"]["alt_text"]


@pytest.mark.parametrize(
    "layout,labels,message",
    [
        ("repeat", [{"field": "ghost", "text": "Other"}], "unknown"),
        ("repeat", [{"field": "score", "text": "A"}, {"field": "score", "text": "B"}], "unique"),
        ("repeat", [{"field": "score", "text": "Loss"}], "uniquely"),
        ("repeat", [{"field": "score", "text": "  "}], "visibly"),
        ("facet", [{"value": "missing", "text": "Other"}], "unknown"),
        ("facet", [{"value": "A", "text": "B"}], "uniquely"),
        ("facet", [{"value": "A", "text": "Other", "row": "early"}], "row values"),
        ("grid", [{"value": "A", "text": "Other"}], "row values"),
        (
            "grid",
            [
                {"value": "A", "row": "early", "text": "Other"},
                {"value": "A", "row": "early", "text": "Again"},
            ],
            "unique",
        ),
        ("grid", [{"value": "A", "row": "early", "text": "   "}], "visibly"),
    ],
)
def test_invalid_panel_display_names_fail_before_outputs(tmp_path, layout, labels, message):
    result = render(tmp_path, layout, labels=labels)
    assert result["report"]["status"] == "failed" and result["exit_code"] != 0
    assert not result["report"]["outputs"]
    assert any(message in f["message"] for f in result["report"]["findings"])


def test_empty_facet_cell_keeps_no_data_evidence_and_its_source_key(tmp_path):
    data = b"epoch,score,condition,phase\n1,1,A,early\n2,2,A,early\n1,3,B,late\n2,4,B,late\n"
    result = render(
        tmp_path, "grid", data=data, labels=[{"value": "B", "row": "early", "text": "Pending"}]
    )
    target = next(t for t in targets(result, "panel_title") if t["value"] == "Pending")
    assert target["source"] == {"value": "B", "row": "early"}
    assert any("has no data" in message for message in result["report"]["untested"])
    assert any(p["name"] == "early / B" for p in result["report"]["panels"])


def test_facet_keys_are_not_concatenated_visible_headings(tmp_path):
    data = b"epoch,score,condition,phase\n1,1,C,A / B\n2,2,C,A / B\n1,1,B / C,A / B\n2,2,B / C,A / B\n1,1,C,A\n2,2,C,A\n1,1,B / C,A\n2,2,B / C,A\n"
    labels = [
        {"value": value, "row": row, "text": name}
        for value, row, name in [
            ("C", "A / B", "One"),
            ("B / C", "A / B", "Two"),
            ("C", "A", "Three"),
            ("B / C", "A", "Four"),
        ]
    ]
    result = render(tmp_path, "grid", data=data, labels=labels)
    assert result["report"]["ok"], result["report"]
    assert {tuple(t["source"].items()) for t in targets(result, "panel_title")} == {
        tuple({"value": item["value"], "row": item["row"]}.items()) for item in labels
    }
    assert {t["value"] for t in targets(result, "panel_title")} == {"One", "Two", "Three", "Four"}


def test_horizontal_forest_retains_semantic_labels_and_unsupported_repeat_stays_explicit(tmp_path):
    data = b"condition,score,loss\nA,1,4\nA,2,3\nA,3,2\nB,2,3\nB,3,2\nB,4,1\n"
    options = {
        "data": data,
        "kind": "forest",
        "x": {"field": "condition", "label": "Condition"},
        "uncertainty": {"kind": "range"},
    }
    unsupported = render(
        tmp_path / "repeat", "repeat", labels=[{"field": "score", "text": "Quality"}], **options
    )
    assert unsupported["report"] is None
    assert any(f["code"] == "unsupported_repeat" for f in unsupported["translation"]["findings"])
    result = render(tmp_path / "native", None, **options)
    assert result["report"]["ok"], result["report"]
    labels = targets(result, "axis_label")
    measurement = next(t for t in labels if t["source"] == "score")
    category = next(t for t in labels if t["source"] == "condition")
    assert (
        measurement["path"] == ["y", "label"]
        and measurement["bounds"][2] > measurement["bounds"][3]
    )
    assert category["path"] == ["x", "label"] and category["bounds"][3] > category["bounds"][2]


def test_reserved_metric_names_are_literal_source_values_in_array_records(tmp_path):
    data = b"epoch,__proto__,constructor\n1,7,4\n2,11,2\n"
    result = render(
        tmp_path,
        None,
        data=data,
        repeat={
            "fields": ["__proto__", "constructor"],
            "labels": [{"field": "__proto__", "text": "Quality"}],
        },
        y={"field": "__proto__", "label": "Source"},
    )
    assert result["report"]["ok"], result["report"]
    actual = targets(result, "metric_label")
    assert {t["source"] for t in actual} == {"__proto__", "constructor"}
    assert any(t["text"] == "Quality" and t["source"] == "__proto__" for t in actual)
