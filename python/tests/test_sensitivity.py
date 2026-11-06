"""Native sensitivity comparisons, failures and evidence ownership."""

from __future__ import annotations

import copy
import hashlib
import json

import pytest

from graphunslopify.cli import main
from graphunslopify.sensitivity import run_sensitivity, sensitivity_plan

DATA = b"""x,arm,y,unit
1,A,1,u1
1,A,1,u2
1,A,16,u3
1,B,4,u1
1,B,4,u2
1,B,4,u3
2,A,1,u1
2,A,1,u2
2,A,22,u3
2,B,4,u1
2,B,4,u2
2,B,4,u3
"""
SPEC = {
    "kind": "line",
    "title": "Two trial arms",
    "data": {"path": "source.csv", "format": "csv"},
    "x": {"field": "x", "label": "Time point"},
    "y": {"field": "y", "label": "Outcome"},
    "group": "arm",
    "marker": True,
    "aggregation": "mean",
    "claims": [{"kind": "beats_everywhere", "subject": "A", "reference": "B"}],
    "output": {"dpi": 144, "stem": "author-figure"},
}
MEDIAN = {
    "label": "Median by arm",
    "justification": "Test sensitivity to the unusually high observation in each group.",
    "changes": {"aggregation": "median"},
}


def test_native_estimates_claim_change_and_input_ownership(tmp_path):
    baseline = copy.deepcopy(SPEC)
    alternatives = [
        MEDIAN,
        {
            "label": "First time point only",
            "justification": "The early endpoint was specified before follow-up data arrived.",
            "changes": {"filter": [{"field": "x", "op": "eq", "value": 1}]},
        },
    ]
    output = tmp_path / "audit"
    result = run_sensitivity(SPEC, alternatives, data=DATA, destination=output, reviewed=True)
    assert result["status"] == "partial" and result["exit_code"] == 2
    assert baseline == SPEC
    assert result["source"]["sha256"] == hashlib.sha256(DATA).hexdigest()
    assert not (output / "input.csv").exists()
    before, median, filtered = result["choices"]
    assert before["status"] == "checked"
    assert median["status"] == "checked_with_failures"
    assert median["runtime_exit_code"] == 2
    contrast = median["claim_comparison"][0]
    assert contrast["before"]["verdict"] == "holds"
    assert contrast["after"]["verdict"] == "fails"
    assert contrast["changed"] is True
    pair = next(
        row for row in median["comparison"] if row["before"]["keys"] == {"x": "1", "arm": "A"}
    )
    assert pair["before"]["estimate"] == 6 and pair["after"]["estimate"] == 1
    assert pair["difference"] == -5
    assert pair["before"]["units"] == pair["after"]["units"] == 3
    assert filtered["counts"]["after_filter"] == 6
    assert sum(row["after"] is None for row in filtered["comparison"]) == 2
    for item in (before, median, filtered):
        preview = item["preview"]
        assert (
            hashlib.sha256((output / preview["path"]).read_bytes()).hexdigest() == preview["sha256"]
        )
    assert before["preview"]["pixels_sha256"] != median["preview"]["pixels_sha256"]
    assert json.loads((output / "sensitivity.json").read_bytes()) == result
    with pytest.raises(FileExistsError):
        run_sensitivity(SPEC, alternatives, data=DATA, destination=output, reviewed=True)


@pytest.mark.parametrize(
    "changes",
    [{"data": {"path": "other.csv"}}, {"aggregation": "mean"}, {"uncertainty": {"display": "bar"}}],
)
def test_only_distinct_statistical_choices_are_accepted(changes):
    with pytest.raises(ValueError):
        sensitivity_plan(SPEC, [{**MEDIAN, "changes": changes}])


def test_cli_requires_review_before_rendering(tmp_path, capsys):
    spec = tmp_path / "figure.json"
    alternatives = tmp_path / "alternatives.json"
    spec.write_text(json.dumps(SPEC))
    alternatives.write_text(json.dumps([MEDIAN]))
    output = tmp_path / "out"
    args = ["sensitivity", str(spec), "--alternatives", str(alternatives), "--out-dir", str(output)]
    assert main(args) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "review_required"
    assert not output.exists()
    (tmp_path / "source.csv").write_bytes(DATA)
    assert main([*args, "--reviewed"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "partial"
    assert result["choices"][1]["claim_comparison"][0]["changed"]
    assert (tmp_path / "source.csv").read_bytes() == DATA


def test_interval_choice_changes_bounds_and_leaves_mean(tmp_path):
    baseline = {
        **SPEC,
        "claims": [],
        "uncertainty": {"kind": "ci", "level": 0.8, "over": "unit"},
    }
    baseline.pop("claims")
    alternative = {
        "label": "Higher coverage interval",
        "justification": "Show whether the interval is sensitive to the selected confidence level.",
        "changes": {"uncertainty": {"level": 0.95}},
    }
    result = run_sensitivity(
        baseline, [alternative], data=DATA, destination=tmp_path / "interval", reviewed=True
    )
    assert result["status"] == "checked"
    estimates = result["choices"][1]["comparison"]
    arm = next(row for row in estimates if row["before"]["keys"] == {"x": "1", "arm": "A"})
    assert arm["difference"] == 0
    assert arm["before"]["unit_field"] == arm["after"]["unit_field"] == "unit"
    before, after = (arm[side]["interval"] for side in ("before", "after"))
    assert before["bootstrap"]["method"] == after["bootstrap"]["method"] == "percentile"
    assert before["bootstrap"]["level"] == 0.8 and after["bootstrap"]["level"] == 0.95
    assert after["bounds"][0] <= before["bounds"][0] < before["bounds"][1] <= after["bounds"][1]


def test_ignored_or_default_uncertainty_levels_are_duplicate_choices():
    for kind, level in (("ci", 0.95), ("std", 0.8)):
        spec = {**SPEC, "uncertainty": {"kind": kind}}
        with pytest.raises(ValueError, match="distinct"):
            sensitivity_plan(spec, [{**MEDIAN, "changes": {"uncertainty": {"level": level}}}])


def test_cli_invalid_source_type_has_structured_error(tmp_path, capsys):
    spec = tmp_path / "figure.json"
    alternatives = tmp_path / "alternatives.json"
    spec.write_text(json.dumps({**SPEC, "data": ["source.csv"]}))
    alternatives.write_text(json.dumps([MEDIAN]))
    output = tmp_path / "out"
    assert (
        main(
            [
                "sensitivity",
                str(spec),
                "--alternatives",
                str(alternatives),
                "--out-dir",
                str(output),
                "--reviewed",
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().out) == {
        "status": "failed",
        "error": "Select the original figure dataset",
    }
    assert not output.exists()
