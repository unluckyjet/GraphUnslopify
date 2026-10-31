"""Reuse actual generated numerical functions without reusing scientific evidence."""

from __future__ import annotations

import copy
import json
import runpy
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
import pytest

from graphunslopify.numerical_cache import NumericalCache
from graphunslopify.transport import local_request

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def generated(tmp_path, monkeypatch):
    base = ROOT / "benchmarks/rendering/cases/demo-bootstrap"
    spec = json.loads((base / "figure.json").read_text())
    spec["data"]["path"] = "data.csv"
    (tmp_path / "data.csv").write_bytes((base / "data.csv").read_bytes())
    number = 0

    def create(change=None, *, padding=0):
        nonlocal number
        intent = copy.deepcopy(spec)
        if change:
            change(intent)
        answer = local_request("convert", intent)
        assert answer["ok"] and answer["status"] == "translated"
        number += 1
        script = tmp_path / f"figure-{number}.py"
        script.write_text("\n" * padding + answer["code"])
        namespace = runpy.run_path(str(script), run_name="__numerical_cache_test__")
        context = namespace["run_cli"].__globals__
        frame = context["prepare"](context["load"]())
        return context, frame

    monkeypatch.chdir(tmp_path)
    with matplotlib.rc_context():
        yield create


def test_generated_results_are_copy_isolated_and_title_filename_line_independent(generated):
    owner = NumericalCache("a" * 64)
    context, frame = generated()
    expected = context["summarise"](frame)
    request = owner.request()
    request.install(context)
    result = context["summarise"](frame)
    pd.testing.assert_frame_equal(result, expected)
    result.iloc[0, result.columns.get_loc("score")] = -999
    result.attrs["poison"] = ["mutable"]
    context, frame = generated(lambda s: s.update(title="Current wording"), padding=11)
    next_request = owner.request()
    next_request.install(context)
    second = context["summarise"](frame)
    pd.testing.assert_frame_equal(second, expected)
    assert "poison" not in second.attrs
    assert next_request.trace()["hits"] == 1 and next_request.trace()["misses"] == 0


@pytest.mark.parametrize("kind", ["title", "axis-label", "legend", "output", "interval-display"])
def test_owned_presentation_edits_reuse_the_same_numerical_result(generated, kind):
    owner = NumericalCache("0" * 64)
    context, frame = generated()
    request = owner.request()
    request.install(context)
    expected = context["summarise"](frame)

    def change(spec):
        if kind == "title":
            spec["title"] = "Current title"
        elif kind == "axis-label":
            spec["y"]["label"] = "Current measurement label"
        elif kind == "legend":
            spec["legend"] = {"show": False}
        elif kind == "output":
            spec.setdefault("output", {})["dpi"] = 200
        else:
            spec["uncertainty"]["display"] = "bar"

    context, frame = generated(change)
    request = owner.request()
    request.install(context)
    pd.testing.assert_frame_equal(context["summarise"](frame), expected)
    assert request.trace()["hits"] == 1 and request.trace()["misses"] == 0


@pytest.mark.parametrize("kind", ["values", "row-order", "dtype", "attributes", "index"])
def test_transformed_typed_arguments_cannot_reuse_previous_results(generated, kind):
    owner = NumericalCache("b" * 64)
    context, frame = generated()
    request = owner.request()
    request.install(context)
    context["summarise"](frame)
    before = request.trace()["functions"]["summarise"]["misses"]
    changed = frame.copy(deep=True)
    if kind == "values":
        changed["score"] += 2
    elif kind == "row-order":
        changed = changed.iloc[::-1]
    elif kind == "dtype":
        changed["score"] = changed["score"].astype(object)
    elif kind == "attributes":
        changed.attrs["current-unit-metadata"] = ["fresh"]
    else:
        changed.index = changed.index + 100
    context["summarise"](changed)
    assert request.trace()["functions"]["summarise"]["misses"] == before + 1


@pytest.mark.parametrize(
    "kind", ["aggregation", "interval-level", "replicate-units", "filter", "unit", "series-order"]
)
def test_numeric_intent_changes_do_not_hit_old_entries(generated, kind):
    owner = NumericalCache("c" * 64)
    context, frame = generated()
    request = owner.request()
    request.install(context)
    context["summarise"](frame)

    def change(spec):
        if kind == "aggregation":
            spec["aggregation"] = "median"
        elif kind == "interval-level":
            spec["uncertainty"]["level"] = 0.9
        elif kind == "replicate-units":
            spec["uncertainty"].pop("over")
        elif kind == "filter":
            spec["filter"] = [{"field": "score", "op": "gte", "value": -1e9}]
        elif kind == "unit":
            spec["y"]["unit"] = "fraction"
        else:
            spec["series_order"] = ["ours", "base"]

    context, frame = generated(change)
    request = owner.request()
    request.install(context)
    context["summarise"](frame)
    assert request.trace()["functions"]["summarise"]["misses"] == 1


@pytest.mark.parametrize("kind", ["source-bytes", "runtime", "seed", "dynamic-y"])
def test_content_runtime_and_dynamic_namespace_invalidation(generated, kind, monkeypatch):
    owner = NumericalCache("d" * 64)
    context, frame = generated()
    request = owner.request()
    request.install(context)
    context["summarise"](frame)
    if kind == "source-bytes":
        path = Path("data.csv")
        path.write_bytes(path.read_bytes() + b"\n")
    context, frame = generated()
    if kind == "runtime":
        monkeypatch.setattr(np, "__version__", "controlled-runtime-change")
    elif kind == "seed":
        context["BOOTSTRAP_SEED"] += 1
    elif kind == "dynamic-y":
        frame["alternate"] = frame["score"] * 2
        context["Y_FIELD"] = "alternate"
    request = owner.request()
    request.install(context)
    context["summarise"](frame)
    assert request.trace()["functions"]["summarise"]["misses"] == 1


def test_corrupt_bytes_recompute_and_calculation_errors_never_reuse_success(generated):
    context, frame = generated()
    expected = context["summarise"](frame)
    owner = NumericalCache("e" * 64)
    request = owner.request()
    request.install(context)
    context["summarise"](frame)
    for key, (_, checksum) in list(owner.entries.items()):
        owner.entries[key] = b"damaged", checksum
    pd.testing.assert_frame_equal(context["summarise"](frame), expected)
    assert request.trace()["invalid"] >= 1
    assert owner.bytes == sum(len(entry[0]) for entry in owner.entries.values())
    for key in list(owner.entries):
        owner.entries[key] = ["malformed"]
    pd.testing.assert_frame_equal(context["summarise"](frame), expected)
    assert owner.bytes == sum(len(entry[0]) for entry in owner.entries.values())
    with pytest.raises(KeyError):
        context["summary_input"](frame, "missing-measurement")


def test_byte_and_entry_budgets_and_unsupported_keys_keep_current_calculation(generated):
    context, frame = generated()
    expected = context["summarise"](frame)
    owner = NumericalCache("f" * 64, max_entries=1)
    request = owner.request()
    request.install(context)
    pd.testing.assert_frame_equal(context["summarise"](frame), expected)
    assert request.trace()["entries"] == 1 and request.trace()["evictions"] > 0
    assert request.trace()["serialized_bytes"] <= request.trace()["max_bytes"]
    context, frame = generated()
    owner = NumericalCache("f" * 64, max_bytes=1)
    request = owner.request()
    request.install(context)
    pd.testing.assert_frame_equal(context["summarise"](frame), expected)
    assert request.trace()["entries"] == 0 and request.trace()["bypassed"] > 0
