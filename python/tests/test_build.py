"""The builder has to produce the same specs an agent would write by hand.

Every method here is sugar over one JSON field, so the tests check the field
that comes out rather than that the call did not raise.
"""

from __future__ import annotations

import json
from typing import get_args

import pytest

from graphunslopify import Figure, SpecError
from graphunslopify.build import Kind
from graphunslopify.transport import local_request


def test_each_constructor_sets_its_kind():
    kinds = local_request("info")["kinds"]
    assert set(get_args(Kind)) == set(kinds)
    for name in kinds:
        spec = getattr(Figure, name)("data.csv").to_dict()
        assert spec["kind"] == name
        assert spec["data"]["path"] == "data.csv"


def test_named_python_constructors_translate_all_canonical_recipes():
    for recipe in local_request("recipes"):
        spec = recipe["spec"]
        figure = getattr(Figure, spec["kind"])(spec.get("data", {}).get("path", "results.csv"))
        figure.spec["data"].update(spec.get("data", {}))
        figure.set(**{k: v for k, v in spec.items() if k not in {"kind", "data"}})
        assert figure.translate(api="local") == local_request("convert", spec)


def test_builder_infers_supported_json_input_and_reads_it(tmp_path):
    path = tmp_path / "points.json"
    path.write_text('[{"x":1,"y":2},{"x":2,"y":3}]')
    figure = (
        Figure.scatter(path)
        .x("x", "X")
        .y("y", "Y")
        .set(legend={"show": False})
        .output(formats=["png"])
    )
    assert figure.spec["data"]["format"] == "json"
    result = figure.render(cwd=tmp_path / "output", strict=True, api="local")
    assert result["report"]["data"]["counts"]["read"] == 2


def test_encoding_reaches_the_spec():
    spec = Figure.line().x("epoch", "Epoch").y("acc", "Accuracy", unit="%").to_dict()
    assert spec["x"] == {"field": "epoch", "label": "Epoch"}
    assert spec["y"] == {"field": "acc", "label": "Accuracy", "unit": "%"}


def test_grouping_carries_order_and_emphasis():
    spec = Figure.line().by("model", order=["a", "b"], emphasise="b").to_dict()
    assert spec["group"] == "model"
    assert spec["series_order"] == ["a", "b"]
    assert spec["emphasis"] == {"series": "b"}


def test_average_over_sets_the_spread_too():
    """Aggregating without spread throws away what a reader needs most."""
    spec = Figure.line().average_over("seed").to_dict()
    assert spec["aggregation"] == "mean"
    assert spec["uncertainty"]["kind"] == "ci"
    assert spec["uncertainty"]["over"] == "seed"


def test_median_pairs_with_an_interquartile_range():
    spec = Figure.line().median_over("seed").to_dict()
    assert spec["aggregation"] == "median"
    assert spec["uncertainty"]["kind"] == "iqr"


def test_claims_accumulate_rather_than_replace():
    spec = (
        Figure.line()
        .claim("beats_everywhere", "ours", "baseline")
        .claim("gap_widens", "ours", "baseline")
        .to_dict()
    )
    assert [c["kind"] for c in spec["claims"]] == ["beats_everywhere", "gap_widens"]


def test_notes_and_references_accumulate():
    spec = (
        Figure.line()
        .reference("y", 50, "chance", meaning="chance")
        .reference("x", 8, "warmup")
        .note("max", "best", series="ours")
        .to_dict()
    )
    assert len(spec["reference_lines"]) == 2
    assert spec["reference_lines"][0]["meaning"] == "chance"
    assert spec["annotate"][0] == {"at": "max", "text": "best", "series": "ours"}


def test_filters_accumulate():
    spec = Figure.line().where("epoch", "gte", 10).where("split", "eq", "test").to_dict()
    assert len(spec["filter"]) == 2
    assert spec["filter"][0] == {"field": "epoch", "op": "gte", "value": 10}


def test_composition_helpers():
    spec = (
        Figure.line()
        .layer("scatter", label="observations")
        .repeat(["accuracy", "loss"], columns=2)
        .zoom((10, 20), (60, 80))
        .cut_axis(30, 60)
        .to_dict()
    )
    assert spec["layers"] == [{"mark": "scatter", "label": "observations"}]
    assert spec["repeat"]["fields"] == ["accuracy", "loss"]
    assert spec["inset"]["x"] == [10, 20]
    assert spec["axis_break"] == {"axis": "y", "from": 30, "to": 60}


def test_output_helpers_merge_rather_than_overwrite():
    spec = Figure.line().wide().named("figure-3").output(dpi=300).to_dict()
    assert spec["output"] == {"size": "double_column", "stem": "figure-3", "dpi": 300}


def test_context_is_the_author_half_of_the_alt_text():
    spec = Figure.line().context("The gain comes from section 4.").to_dict()
    assert spec["alt_text"] == "The gain comes from section 4."


def test_set_reaches_anything_the_builder_does_not_wrap():
    spec = Figure.line().set(smooth={"kind": "ema", "window": 5}).to_dict()
    assert spec["smooth"]["window"] == 5


def test_to_dict_is_a_copy_not_the_live_spec():
    figure = Figure.line()
    snapshot = figure.to_dict()
    figure.titled("added later")
    assert "title" not in snapshot


def test_to_json_round_trips():
    figure = Figure.bar().x("a", "A").y("b", "B")
    assert json.loads(figure.to_json()) == figure.to_dict()


def test_an_unreachable_api_raises_a_clear_error():
    figure = Figure.line().x("a", "A").y("b", "B")
    with pytest.raises(SpecError, match="could not reach"):
        figure.translate(api="http://127.0.0.1:9")
