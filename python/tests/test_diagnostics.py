"""Real source, data and artist correction paths for actionable diagnostics."""

from __future__ import annotations

import ast
import copy
import json
import subprocess
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pytest

from graphunslopify import Figure, SpecError
from graphunslopify.cli import main
from graphunslopify.diagnostics import advice, catalog
from graphunslopify.inspect import inspect_figure as check

ROOT = Path(__file__).resolve().parents[2]


def test_all_current_inspection_and_data_view_codes_have_guidance():
    codes = set()
    for name in ("inspect.py", "data_view.py", "pdf_visual.py"):
        tree = ast.parse((ROOT / "python/graphunslopify" / name).read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            target = (
                node.func.attr
                if isinstance(node.func, ast.Attribute)
                else getattr(node.func, "id", "")
            )
            if (
                target in {"add", "Finding", "finding"}
                and len(node.args) >= 3
                and isinstance(node.args[1], ast.Constant)
            ):
                codes.add(node.args[1].value)
            if target == "_finding" and node.args and isinstance(node.args[0], ast.Constant):
                codes.add(node.args[0].value)
    assert len(codes) >= 15
    assert codes <= catalog()["advice"].keys()


def test_actual_schema_failure_keeps_path_and_structured_guidance(capsys, tmp_path):
    spec = {"kind": "line", "x": {"field": "x", "label": "X"}, "y": {"field": "y"}}
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(spec))
    assert main(["render", str(path), "--json"]) == 2
    output = json.loads(capsys.readouterr().out)
    assert any(
        item["path"] == "y.label" and "y.label" in item["message"] for item in output["diagnostics"]
    )
    assert all(item["consequence"] and item["correction"] for item in output["diagnostics"])
    with pytest.raises(SpecError) as problem:
        Figure(spec).translate(api="local")
    assert problem.value.report is None
    assert problem.value.diagnostics


def test_real_runtime_log_data_correction_preserves_observations_and_strict_policy(tmp_path):
    data = tmp_path / "observations.csv"
    original = "x,y\n1,-2\n2,3\n3,4\n"
    data.write_text(original)
    figure = (
        Figure.line(data)
        .x("x", "X")
        .y("y", "Y")
        .set(y={"field": "y", "label": "Y", "scale": "log"}, legend={"show": False})
        .output(formats=["png"])
    )
    before = copy.deepcopy(figure.spec)
    with pytest.raises(SpecError) as problem:
        figure.render(cwd=tmp_path / "failed")
    report = problem.value.report
    finding = next(item for item in report["findings"] if item["code"] == "log_domain_hidden")
    assert finding["severity"] == "error"
    assert "logarithm" in finding["consequence"].lower() or "log" in finding["consequence"].lower()
    assert "linear" in finding["correction"]
    assert report["exit_code"] == 2 and figure.spec == before
    figure.spec["y"]["scale"] = "linear"
    corrected = figure.render(cwd=tmp_path / "corrected")["report"]
    assert corrected["status"] == "passed" and corrected["data"]["counts"]["read"] == 3
    assert data.read_text() == original
    # Old three-field findings remain valid evidence under report schema1.
    from jsonschema import Draft202012Validator

    legacy = copy.deepcopy(report)
    for item in legacy["findings"]:
        item.pop("consequence", None)
        item.pop("correction", None)
    Draft202012Validator(
        json.loads((ROOT / "docs/runtime-report.schema.json").read_text())
    ).validate(legacy)
    generated = tmp_path / "failed/figure.py"
    replay = subprocess.run(
        [sys.executable, str(generated), "--strict"],
        cwd=generated.parent,
        capture_output=True,
        text=True,
        check=False,
    )
    assert replay.returncode == 2
    assert "Why it matters:" in replay.stdout and "Recommended correction:" in replay.stdout


def test_console_only_repeat_warning_explains_without_changing_acceptance(tmp_path, capsys):
    source = tmp_path / "repeats.csv"
    source.write_text("x,y\n1,1\n1,2\n2,3\n2,4\n")
    figure = (
        Figure.line(source)
        .x("x", "X")
        .y("y", "Y")
        .set(legend={"show": False})
        .output(formats=["png"])
    )
    result = figure.render(cwd=tmp_path / "rendered")
    output = capsys.readouterr().out
    assert "[repeated_x_values]" in output
    assert "correct independent units" in output
    assert result["report"]["exit_code"] == 0
    assert not any(item["code"] == "repeated_x_values" for item in result["report"]["findings"])


def test_actual_export_inspection_explains_and_corrects_small_text():
    fig, ax = plt.subplots()
    text = ax.text(0.5, 0.5, "Measured concentration", fontsize=2)
    first = check(fig)
    finding = next(item for item in first.findings if item.code == "text_too_small")
    assert finding.consequence and finding.correction
    assert "Recommended correction:" in str(first)
    text.set_fontsize(12)
    assert not any(item.code == "text_too_small" for item in check(fig).findings)
    plt.close(fig)


@pytest.mark.parametrize(
    "code,expected", [("uncertainty_unavailable", 0), ("external_plugin_code", 2)]
)
def test_explain_command_runs_without_translation_and_bounds_unknown_codes(code, expected, capsys):
    assert main(["explain", code, "--json"]) == expected
    result = json.loads(capsys.readouterr().out)
    assert result["known"] is (expected == 0)
    assert result["consequence"] and result["correction"]
    assert advice(code)["correction"] == result["correction"]
