"""Real standalone attempts reject installed SDKs and changed owned archive input."""

from __future__ import annotations

import json
import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "benchmarks/workspace"


@pytest.mark.parametrize("arm", ["matplotlib", "graphunslopify"])
def test_actual_standalone_refuses_an_interpreter_with_installed_sdk(tmp_path, arm):
    replay = runpy.run_path(str(HERE / "reproduction.py"))
    case = {
        "arm": arm,
        "figure": "penguins-mass",
        "repeat": 0,
        "profile": "standalone-bundle-no-installed-graphunslopify3.12",
    }
    result = replay["run_case"](case, tmp_path / "attempt", python=sys.executable)
    execution = json.loads((tmp_path / "attempt/standalone/execution.json").read_text())
    probe = json.loads((tmp_path / "attempt/standalone/absence-probe.json").read_text())
    assert probe["distribution"] is not None
    assert result["outcome"] == "execution_error"
    assert execution["outcome"] == "execution_error"
    assert "actual SDK distribution/import absence" in execution["error"]["message"]
    assert not (tmp_path / "attempt/standalone/workspace-result.json").exists()
    assert not result["formal_comparison_performed"]


@pytest.mark.parametrize("arm", ["matplotlib", "graphunslopify"])
def test_actual_owned_input_change_is_refused_before_any_render(tmp_path, arm):
    replay = runpy.run_path(str(HERE / "reproduction.py"))
    spec = json.loads((HERE / "figures/penguins-mass.json").read_text())
    data = (HERE / "figures" / spec["data"]["path"]).read_bytes()
    manifest = replay["prepare_standalone"]({"arm": arm}, tmp_path, spec, data)
    (tmp_path / "data.csv").write_bytes(data + b"\n")
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    actual = subprocess.run(
        [
            sys.executable,
            str(tmp_path / "code/standalone_worker.py"),
            "--root",
            str(tmp_path),
            "--manifest-sha256",
            manifest,
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    execution = json.loads((tmp_path / "execution.json").read_text())
    assert actual.returncode == 1
    assert execution["outcome"] == "execution_error"
    assert "Owned standalone source/input changed: data.csv" in execution["error"]["message"]
    assert not (tmp_path / "absence-probe.json").exists()
    assert not (tmp_path / "workspace-result.json").exists()
    assert (tmp_path / "data.csv").read_bytes() == data + b"\n"
