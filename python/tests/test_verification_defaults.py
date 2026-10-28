"""Exercise default verification through real generated, CLI and SDK entry points."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from graphunslopify import Figure, SpecError
from graphunslopify.transport import local_request


@pytest.fixture
def figure_input(tmp_path):
    def create(status):
        reference = "absent" if status == "incomplete" else "base"
        subject = "base" if status == "failed" else "ours"
        if status == "failed":
            reference = "ours"
        spec = {
            "kind": "line",
            "data": {"path": "missing.csv" if status == "runtime_error" else "results.csv"},
            "x": {"field": "epoch", "label": "Epoch"},
            "y": {"field": "score", "label": "Score"},
            "group": "model",
            "aggregation": "mean",
            "legend": {"show": False},
            "claims": [{"kind": "beats_everywhere", "subject": subject, "reference": reference}],
            "output": {"stem": "figure", "formats": ["png"], "dpi": 100},
        }
        (tmp_path / "results.csv").write_text(
            "epoch,score,model\n1,1,base\n2,2,base\n1,4,ours\n2,5,ours\n"
        )
        (tmp_path / "figure.json").write_text(json.dumps(spec))
        (tmp_path / "figure.py").write_text(local_request("convert", spec)["code"])
        return spec

    return create


@pytest.mark.parametrize("entry", ["generated", "render", "run", "check"])
@pytest.mark.parametrize("status", ["passed", "failed", "incomplete", "runtime_error"])
@pytest.mark.parametrize("opt_out", [False, True])
def test_execution_defaults_and_explicit_opt_out(tmp_path, figure_input, entry, status, opt_out):
    figure_input(status)
    if entry == "generated":
        command = [sys.executable, "figure.py"]
    else:
        name = "figure.json" if entry == "render" else "figure.py"
        command = [sys.executable, "-m", "graphunslopify.cli", entry, name]
    command.append("--json")
    if opt_out:
        command.append("--no-strict")
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, check=False)
    report = json.loads(result.stdout)
    expected = 1 if status == "runtime_error" else 0 if opt_out or status == "passed" else 2
    assert result.returncode == report["exit_code"] == expected, result.stderr
    assert report["status"] == ("failed" if status == "runtime_error" else status)
    assert report["policy"]["strict"] is not opt_out
    assert report["policy"]["passed"] is (expected == 0)
    assert report == json.loads((tmp_path / "figure.report.json").read_text())
    if status != "runtime_error":
        assert (tmp_path / "figure.png").is_file()


@pytest.mark.parametrize("status", ["passed", "failed", "incomplete"])
@pytest.mark.parametrize("opt_out", [False, True])
def test_builder_defaults_and_explicit_opt_out(tmp_path, figure_input, status, opt_out):
    spec = figure_input(status)
    spec["data"]["path"] = str(tmp_path / "results.csv")
    figure = Figure(spec)
    options = {"strict": False} if opt_out else {}
    if not opt_out and status != "passed":
        with pytest.raises(SpecError) as failure:
            figure.render(cwd=tmp_path, api="local", **options)
        report = failure.value.report
        assert report["exit_code"] == 2
    else:
        report = figure.render(cwd=tmp_path, api="local", **options)["report"]
        assert report["exit_code"] == 0
    assert report["status"] == status
    assert report["policy"]["strict"] is not opt_out


@pytest.mark.parametrize("entry", ["generated", "render", "run", "check"])
def test_warning_policy_cannot_disable_required_verification(tmp_path, figure_input, entry):
    figure_input("failed")
    command = (
        [sys.executable, "figure.py"]
        if entry == "generated"
        else [
            sys.executable,
            "-m",
            "graphunslopify.cli",
            entry,
            "figure.json" if entry == "render" else "figure.py",
        ]
    )
    result = subprocess.run(
        [*command, "--no-strict", "--fail-on-warning", "--json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    report = json.loads(result.stdout)
    assert result.returncode == report["exit_code"] == 2
    assert report["policy"]["strict"] is True
    assert report["status"] == "failed"


def test_builder_warning_policy_keeps_explicit_opt_out_strict(tmp_path, figure_input):
    spec = figure_input("failed")
    spec["data"]["path"] = str(tmp_path / "results.csv")
    with pytest.raises(SpecError) as failure:
        Figure(spec).render(cwd=tmp_path, api="local", strict=False, fail_on_warning=True)
    assert failure.value.report["exit_code"] == 2
    assert failure.value.report["policy"]["strict"] is True


@pytest.mark.parametrize("entry", ["generated", "render", "run", "check"])
def test_conflicting_policy_flags_are_rejected(tmp_path, figure_input, entry):
    figure_input("passed")
    command = (
        [sys.executable, "figure.py"]
        if entry == "generated"
        else [
            sys.executable,
            "-m",
            "graphunslopify.cli",
            entry,
            "figure.json" if entry == "render" else "figure.py",
        ]
    )
    result = subprocess.run(
        [*command, "--strict", "--no-strict"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "not allowed with argument" in result.stderr
    assert not (tmp_path / "figure.report.json").exists()
