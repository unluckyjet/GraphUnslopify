"""Portable intent must preserve active bindings, literal meanings and strict outcomes."""

import copy
import hashlib
import json

import pytest

from graphunslopify import Figure
from graphunslopify.figure_templates import TemplateError, create_template, presets, review_reuse
from graphunslopify.transport import local_request


@pytest.fixture
def spec():
    return {
        "kind": "line",
        "title": "A saved design",
        "x": {"field": "epoch", "label": "Epoch"},
        "y": {"field": "score", "label": "Score"},
        "group": "model",
        "aggregation": "mean",
        "uncertainty": {"kind": "ci", "over": "seed", "level": 0.95},
        "data": {"path": "private-original.csv", "format": "csv"},
        "output": {"stem": "owned-output", "dpi": 300},
        "claims": [{"kind": "beats_everywhere", "subject": "ours", "reference": "base"}],
    }


def test_roundtrip_excludes_paths_and_preserves_current_claims_and_bindings(spec):
    source = copy.deepcopy(spec)
    source["palette_lock"] = "private-palette.json"
    template = create_template(source, "Reusable design")
    encoded = json.dumps(template)
    assert (
        "private-original" not in encoded
        and "private-palette" not in encoded
        and "owned-output" not in encoded
    )
    active = copy.deepcopy(spec)
    active["title"] = "Active draft"
    active["data"] = {
        "path": "new.xlsx",
        "format": "excel",
        "sheet": "Measured",
        "columns": ["epoch", "score", "model", "seed"],
    }
    active["output"]["stem"] = "active-owner"
    active["palette_lock"] = "active-palette.json"
    active["claims"][0]["subject"] = "another"
    before = copy.deepcopy(active)
    plan = review_reuse(active, template=template)
    assert active == before and source["data"]["path"] == "private-original.csv"
    assert plan["can_apply"] and plan["execution"] == "not_run" and plan["requires_verification"]
    assert (
        plan["spec"]["data"] == active["data"]
        and plan["spec"]["palette_lock"] == active["palette_lock"]
    )
    assert (
        plan["spec"]["output"]["stem"] == "active-owner"
        and plan["spec"]["claims"] == active["claims"]
    )
    changed = review_reuse(active, template=template, replace_claims=True)
    assert changed["spec"]["claims"] == source["claims"] and changed["claims_policy"] == "template"


def test_column_mapping_preserves_units_repeat_semantics_and_actual_available_columns(spec):
    template = create_template(spec, "Mapped design")
    active = copy.deepcopy(spec)
    active["title"] = "A different active design"
    active["x"]["field"] = "step"
    active["y"]["field"] = "accuracy"
    active["group"] = "method"
    active["uncertainty"]["over"] = "replicate"
    active["data"]["columns"] = ["step", "accuracy", "method", "replicate"]
    invalid = review_reuse(active, template=template)
    assert not invalid["can_apply"] and any(
        f["code"] == "unknown_field" for f in invalid["findings"]
    )
    valid = review_reuse(
        active,
        template=template,
        mapping={"epoch": "step", "score": "accuracy", "model": "method", "seed": "replicate"},
    )
    assert valid["can_apply"] and valid["spec"]["uncertainty"]["over"] == "replicate"
    assert (
        valid["spec"]["uncertainty"]["level"] == 0.95
        and valid["spec"]["claims"] == active["claims"]
    )
    assert valid["spec"]["data"] == active["data"]


@pytest.mark.parametrize("preset", [p["id"] for p in presets()])
def test_presets_preserve_science_and_use_canonical_output_choices(spec, preset):
    before = copy.deepcopy(spec)
    plan = review_reuse(spec, preset=preset)
    assert spec == before and plan["can_apply"]
    for key in ("data", "claims", "x", "y", "group", "aggregation", "uncertainty"):
        assert plan["spec"][key] == spec[key]
    assert plan["spec"]["output"]["stem"] == spec["output"]["stem"]
    assert local_request("validate", plan["spec"])["ok"]


@pytest.mark.parametrize(
    "mutation", ["version", "data", "palette", "stem", "extra", "unknown_intent", "unknown_nested"]
)
def test_invalid_or_binding_bearing_templates_are_refused(spec, mutation):
    template = create_template(spec, "Saved")
    if mutation == "version":
        template["schema_version"] = True
    elif mutation == "data":
        template["intent"]["data"] = {"path": "other.csv"}
    elif mutation == "palette":
        template["intent"]["palette_lock"] = "other.json"
    elif mutation == "stem":
        template["intent"]["output"]["stem"] = "overwritten"
    elif mutation == "extra":
        template["claims_verified"] = True
    elif mutation == "unknown_intent":
        template["intent"]["strict"] = False
    else:
        template["intent"]["output"]["skip_checks"] = True
    before = copy.deepcopy(spec)
    with pytest.raises((TemplateError, ValueError)):
        review_reuse(spec, template=template)
    assert spec == before


def test_template_size_and_canonical_errors_never_create_success(spec):
    with pytest.raises(TemplateError):
        create_template(spec, "")
    with pytest.raises(TemplateError):
        create_template({**spec, "caption": "x" * (1024 * 1024)}, "Large")
    with pytest.raises(TemplateError):
        create_template({**spec, "x": {"field": "epoch"}}, "Malformed")
    with pytest.raises(TemplateError):
        review_reuse(spec, preset="unknown")


def test_real_saved_template_replay_reads_two_different_active_datasets(tmp_path):
    original = {
        "kind": "line",
        "x": {"field": "x", "label": "Observed x"},
        "y": {"field": "y", "label": "Observed y"},
        "legend": {"show": False},
        "data": {"path": "never-read-original.csv"},
        "output": {"stem": "original", "formats": ["png"], "dpi": 144},
    }
    template = json.loads(json.dumps(create_template(original, "Portable")))
    hashes = []
    images = []
    for index, values in enumerate(["x,y\n1,10\n2,20\n", "x,y\n1,100\n2,200\n"]):
        data = tmp_path / f"actual-{index}.csv"
        data.write_text(values)
        active = copy.deepcopy(original)
        active["title"] = "Changed title"
        active["data"]["path"] = str(data)
        active["output"]["stem"] = f"active-{index}"
        plan = review_reuse(active, template=template)
        assert plan["can_apply"]
        report = Figure(plan["spec"]).render(cwd=tmp_path / f"out-{index}")["report"]
        assert report["status"] == "passed" and report["data"]["counts"]["read"] == 2
        assert report["data"]["sha256_prefix"] == hashlib.sha256(data.read_bytes()).hexdigest()[:16]
        hashes.append(report["data"]["sha256_prefix"])
        images.append((tmp_path / f"out-{index}" / f"active-{index}.png").read_bytes())
    assert len(set(hashes)) == 2 and images[0] != images[1]
