"""Run the real consumer wrapper and inspect exactly what it publishes."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / ".github/actions/figure-ci/run.py"


def run_action(tmp_path, manifest="paper"):
    workspace = tmp_path / "caller"
    workspace.mkdir(exist_ok=True)
    if not (workspace / "paper").exists():
        shutil.copytree(ROOT / "examples/paper", workspace / "paper")
    runner_temp = tmp_path / "runner"
    runner_temp.mkdir(exist_ok=True)
    evidence = workspace / "audit"
    evidence.mkdir(exist_ok=True)
    (evidence / "unrelated-private.csv").write_text("must stay outside staged evidence")
    env = {
        **os.environ,
        "GITHUB_WORKSPACE": str(workspace),
        "RUNNER_TEMP": str(runner_temp),
        "GITHUB_OUTPUT": str(tmp_path / "github-output"),
        "GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md"),
        "FIGURE_CI_MANIFEST": manifest,
        "FIGURE_CI_OUTPUT": "audit",
        "FIGURE_CI_BASELINE": "",
        "FIGURE_CI_FAIL_ON_CHANGE": "false",
        "FIGURE_CI_FAIL_ON_WARNING": "false",
        "FIGURE_CI_TIMEOUT": "120",
    }
    completed = subprocess.run(
        [sys.executable, str(WRAPPER)], env=env, capture_output=True, text=True, check=False
    )
    result = json.loads(completed.stdout)
    return completed, result, workspace


def test_action_stages_only_owned_review_evidence(tmp_path):
    completed, result, _ = run_action(tmp_path)
    assert completed.returncode == 0, completed.stderr
    stage = Path(result["artifact-path"])
    assert (stage / "audit.summary.md").is_file()
    assert len(list(stage.rglob("*.png"))) == 2
    assert not list(stage.rglob("*.csv"))
    report = json.loads(Path(result["report-file"]).read_text())
    assert report["counts"] == {"passed": 2, "failed": 0, "incomplete": 0}
    assert "status=passed" in (tmp_path / "github-output").read_text()
    assert "Status: **passed**" in (tmp_path / "summary.md").read_text()


def test_action_fails_on_claims_and_still_stages_reports(tmp_path):
    workspace = tmp_path / "caller"
    shutil.copytree(ROOT / "examples/paper", workspace / "paper")
    path = workspace / "paper/training.figure.json"
    spec = json.loads(path.read_text())
    spec["claims"][0].update(subject="base", reference="ours")
    path.write_text(json.dumps(spec))
    completed, result, _ = run_action(tmp_path)
    assert completed.returncode == 2
    report = json.loads(Path(result["report-file"]).read_text())
    assert report["counts"] == {"passed": 1, "failed": 1, "incomplete": 0}
    assert report["figures"][0]["report"]["claims"][0]["verdict"] == "fails"
    assert (Path(result["artifact-path"]) / "command.report.json").is_file()


def test_bad_manifest_publishes_current_command_error(tmp_path):
    completed, result, _ = run_action(tmp_path, manifest="does-not-exist.json")
    assert completed.returncode == 2
    assert result["report-file"] == ""
    assert (Path(result["artifact-path"]) / "command.report.json").is_file()
    assert not (Path(result["artifact-path"]) / "audit.report.json").exists()
