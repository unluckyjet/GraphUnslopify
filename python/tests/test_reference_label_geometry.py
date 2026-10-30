"""Owned reference/layer wording paths must not be inferred from matching text."""

import pytest

from graphunslopify.preview import PreviewState


def render(tmp_path, layers, *, facet=False, labels=None):
    state = PreviewState(tmp_path, 1024 * 1024)
    data = state.upload(
        "observations.csv",
        b"epoch,score,low,high,model,condition\n1,7,4,5,base,A\n2,11,5,6,base,A\n1,8,4,5,ours,A\n2,13,5,6,ours,A\n1,6,3,4,base,B\n2,10,4,5,base,B\n1,9,3,4,ours,B\n2,14,4,5,ours,B\n",
    )
    spec = {
        "kind": "line",
        "group": "model",
        "x": {"field": "epoch", "label": "Epoch"},
        "y": {"field": "score", "label": "Score"},
        "legend": {"position": "outside_bottom"},
        "layers": layers,
        "reference_lines": [{"axis": "y", "value": 2, "meaning": "target", "label": "Target"}],
        "output": {"formats": ["png"]},
    }
    if facet:
        spec["facet"] = {"by": "condition"}
    if labels is not None:
        spec["legend"]["labels"] = labels
    result = state.render(
        {"client": "references", "generation": 1, "data_id": data["id"], "spec": spec}
    )
    return result


@pytest.mark.parametrize("mark", ["line", "scatter", "rug", "band", "rule"])
def test_actual_layer_and_reference_text_retains_canonical_identity(tmp_path, mark):
    layer = {"mark": mark, "y": "low", "y2": "high", "value": 3, "label": "Comparison"}
    result = render(tmp_path, [layer])
    assert result["report"]["ok"], result["report"]
    targets = result["edit_map"]["targets"]
    reference = next(t for t in targets if t["role"] == "reference_label")
    assert reference["path"] == ["reference_lines", 0, "label"] and reference["editable"]
    assert reference["source"] == {"axis": "y", "value": 2}
    target = next(t for t in targets if t["role"] == "layer_label")
    assert target["text"] == "Comparison" and target["path"] == ["layers", 0, "label"]
    assert target["source"] == {"layer": 0, "mark": mark} and target["editable"]
    assert {t["source"] for t in targets if t["role"] == "legend_entry"} == {"base", "ours"}


def test_shared_legend_keeps_distinct_source_and_layer_even_when_raw_text_matches(tmp_path):
    result = render(
        tmp_path,
        [{"mark": "rule", "value": 3, "label": "base"}],
        facet=True,
        labels=[{"series": "base", "text": "Control"}],
    )
    assert result["report"]["ok"], result["report"]
    targets = result["edit_map"]["targets"]
    actual = [
        (t["role"], t["text"]) for t in targets if t["role"] in {"legend_entry", "layer_label"}
    ]
    assert actual == [
        ("legend_entry", "Control"),
        ("legend_entry", "ours"),
        ("layer_label", "base"),
    ]


def test_layer_underscore_is_literal_and_duplicate_visible_names_fail_strictly(tmp_path):
    result = render(tmp_path, [{"mark": "rule", "value": 3, "label": "_Guide"}])
    assert result["report"]["ok"], result["report"]
    assert any(
        t["text"] == "_Guide" and t["role"] == "layer_label" for t in result["edit_map"]["targets"]
    )
    failed = render(tmp_path / "ambiguous", [{"mark": "rule", "value": 3, "label": "base"}])
    assert failed["report"]["status"] == "failed" and failed["exit_code"] != 0
    assert any("collide" in f["message"] for f in failed["report"]["findings"])


@pytest.mark.parametrize("drifted", ["source", "layer"])
def test_owned_identity_separation_still_detects_actual_colour_drift(
    tmp_path, monkeypatch, drifted
):
    import importlib.util
    from unittest.mock import patch

    import matplotlib.pyplot as plt

    result = render(
        tmp_path,
        [{"mark": "rule", "value": 3, "label": "base"}],
        facet=True,
        labels=[{"series": "base", "text": "Control"}],
    )
    assert result["report"]["ok"]
    script = next(tmp_path.rglob("figure.py"))
    monkeypatch.chdir(script.parent)
    spec = importlib.util.spec_from_file_location("owned_label_test", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original = module.draw_layers

    def change_actual_artist(axes, frame):
        original(axes, frame)
        if module.CURRENT_PANEL != 1:
            return
        for mark in axes.lines:
            source = getattr(mark, "_graphunslopify_legend_identity", None)
            layer = getattr(mark, "_graphunslopify_legend_text_target", None)
            if (drifted == "source" and source and source["series"] == "base") or (
                drifted == "layer" and layer
            ):
                mark.set_color("#009E73")

    module.draw_layers = change_actual_artist
    with patch.object(plt, "close"):
        module.main()
    try:
        errors = [
            f
            for f in module.RUN_REPORT["findings"]
            if f["code"] == "series_colour_drifts_between_panels"
        ]
        assert errors
        assert ("Layer 1 (base)" if drifted == "layer" else "base") in errors[0]["message"]
    finally:
        plt.close("all")
