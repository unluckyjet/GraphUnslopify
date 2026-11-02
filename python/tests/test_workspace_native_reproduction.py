"""Real worker identity and actual local/native refusal, without simulated CI success."""

from __future__ import annotations

import json
import platform
import runpy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "benchmarks/workspace"


def test_actual_worker_records_its_platform_and_interpreter(tmp_path):
    runner = runpy.run_path(str(HERE / "session_runner.py"))
    live = runner["LiveSession"]("matplotlib", tmp_path / "worker", python=sys.executable)
    try:
        actual = live.ready["execution_environment"]
        assert actual["system"] == platform.system()
        assert actual["machine"] == platform.machine()
        assert actual["python"] == sys.version
        assert actual["executable"] == sys.executable
        assert all("\\" not in name for name in live.ready["package_sha256"])
        assert all("\\" not in name for name in live.source_before)
    finally:
        live.close()
    assert live.process.poll() is not None


def test_actual_wrong_checkout_retains_all_native_cells_without_starting_workers(tmp_path):
    native = runpy.run_path(str(ROOT / "scripts/check-workspace-native-reproduction.py"))
    proof = native["check"](tmp_path / "refused", "macos3.12", "0" * 40)
    assert proof["passed"] is False and proof["complete"] is False
    assert proof["native_context_validated"] is False
    assert len(proof["plan"]) == len(proof["records"]) == 16
    assert "Actual checkout differs" in proof["errors"][0]["message"]
    assert all(
        row["outcome"] == "not_run" and row["dispatch_attempted"] is False
        for row in proof["records"]
    )
    assert all("evaluation" not in row and "startup" not in row for row in proof["records"])
    assert not any((tmp_path / "refused").glob("replay-*"))
    assert json.loads((tmp_path / "refused/conformance.json").read_text()) == proof


@pytest.mark.parametrize("arm", ["matplotlib", "graphunslopify"])
def test_actual_local_attempt_cannot_be_counted_as_native_ci(tmp_path, monkeypatch, arm):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    replay = runpy.run_path(str(HERE / "reproduction.py"))
    profiles = replay["ENVIRONMENT"]["NATIVE_PROFILES"]
    matching = [
        name
        for name, (version, system, _) in profiles.items()
        if sys.version.startswith(version) and platform.system() == system
    ]
    # A nonregistered local OS/version is also a genuine refusal, never CI success.
    profile = matching[0] if matching else next(iter(profiles))
    case = {
        "profile": profile,
        "track": "native_ci",
        "figure": "penguins-mass",
        "repeat": 0,
        "arm": arm,
    }
    row = replay["run_case"](case, tmp_path / "attempt", python=sys.executable)
    assert row["outcome"] == "execution_error"
    assert row["closure_error"] is None
    assert not row["startup"]["execution_environment"]["ci"]["github_actions"]
    assert (
        "actual GitHub Actions context" in row["session_error"]["message"]
        if matching
        else "Actual interpreter/platform differs" in row["session_error"]["message"]
    )
    assert "initial" not in row and "evaluation" not in row
    assert row["closure"]["pid"] == row["startup"]["pid"]
    assert not row["formal_comparison_performed"]
    assert json.loads((tmp_path / "attempt/replay.json").read_text()) == row
