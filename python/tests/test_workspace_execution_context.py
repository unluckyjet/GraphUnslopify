"""A formal label cannot bypass original protocol, case or public CI identity."""

from __future__ import annotations

import copy
import json
import runpy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CONTEXT = runpy.run_path(str(ROOT / "benchmarks/workspace/execution_context.py"))
PROTOCOL = json.loads((ROOT / "benchmarks/workspace/protocol.json").read_text())


def acceptance():
    revision = "a" * 40
    value = {
        "commit": revision,
        "all_nine_main_jobs_figure_and_four_native_passed": True,
        "source_binding_matches": True,
        "expected_check_names_match": True,
        "checks": [
            {"name": name, "status": "completed", "conclusion": "success"}
            for name in CONTEXT["CHECKS"]
        ],
        "workflows": [
            {"name": name, "head_sha": revision, "status": "completed", "conclusion": "success"}
            for name in ("checks", "Figure CI integration", "Workspace native reproduction")
        ],
    }
    base = "https://github.com/unluckyjet/GraphUnslopify/actions/runs/"
    ids = {"checks": 1, "Figure CI integration": 2, "Workspace native reproduction": 3}
    for row in value["workflows"]:
        row.update(id=ids[row["name"]], html_url=base + str(ids[row["name"]]))
    for index, row in enumerate(value["checks"]):
        workflow = (
            "Figure CI integration"
            if row["name"] == "consumer"
            else "Workspace native reproduction"
            if row["name"].startswith("native-reproduction (")
            else "checks"
        )
        row["details_url"] = base + str(ids[workflow]) + "/job/" + str(index + 1)
    return value


def test_no_explicit_context_is_preparation_even_with_ambient_switch(monkeypatch):
    monkeypatch.setenv("GRAPHUNSLOPIFY_FORMAL", "true")
    assert CONTEXT["load"](None, repo=ROOT) == {
        "mode": "preseal",
        "formal_comparison_performed": False,
    }


@pytest.mark.parametrize("change", ["missing", "duplicate", "failed", "head", "workflow"])
def test_incomplete_or_wrong_public_ci_cannot_authorize_formal_work(change):
    value = acceptance()
    if change == "missing":
        value["checks"].pop()
    elif change == "duplicate":
        value["checks"][0] = copy.deepcopy(value["checks"][1])
    elif change == "failed":
        value["checks"][0]["conclusion"] = "failure"
    elif change == "head":
        value["workflows"][0]["head_sha"] = "b" * 40
    else:
        value["workflows"].pop()
    with pytest.raises(ValueError):
        CONTEXT["validate_acceptance"](value, "a" * 40)


@pytest.mark.parametrize(
    "case",
    [
        {"figure": "invented", "session": 0},
        {"figure": "penguins-mass", "session": 3},
        {"figure": "penguins-mass", "session": True},
        {"figure": "penguins-mass", "session": 0, "replacement": True},
    ],
)
def test_unregistered_or_replacement_case_is_refused(case):
    with pytest.raises(ValueError, match="registered"):
        CONTEXT["validate_case"]({"track": "single", "arm": "matplotlib", "case": case}, PROTOCOL)


def test_original_registered_case_and_complete_ci_shape_are_recognized():
    CONTEXT["validate_case"](
        {"track": "single", "arm": "matplotlib", "case": {"figure": "penguins-mass", "session": 0}},
        PROTOCOL,
    )
    CONTEXT["validate_acceptance"](acceptance(), "a" * 40)


def test_formal_document_with_no_implementation_seal_never_loads(tmp_path):
    path = tmp_path / "context.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "mode": "formal",
                "track": "single",
                "arm": "matplotlib",
                "case": {"figure": "penguins-mass", "session": 0},
            }
        )
    )
    with pytest.raises(ValueError, match="seal"):
        CONTEXT["load"](path, repo=ROOT, track="single", arm="matplotlib")


def test_relative_manifest_paths_cannot_escape_the_implementation():
    for name in ("../escape.py", "/absolute.py", "C:/other.py", "a\\other.py"):
        with pytest.raises(ValueError):
            CONTEXT["relative"](name)


@pytest.mark.parametrize("arm", ["matplotlib", "graphunslopify"])
def test_actual_child_producer_and_independent_evaluator_keep_explicit_identity(tmp_path, arm):
    profile = "checkout-minimum3.10" if sys.version_info[:2] == (3, 10) else "checkout-current3.12"
    context = tmp_path / "context.json"
    context.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "mode": "preseal",
                "track": "local",
                "arm": arm,
                "case": {"figure": "iris-scatter", "profile": profile, "repeat": 0},
            }
        )
    )
    replay = runpy.run_path(str(ROOT / "benchmarks/workspace/reproduction.py"))

    result = replay["run_case"](
        {"arm": arm, "figure": "iris-scatter", "profile": profile, "repeat": 0},
        tmp_path / "actual",
        python=sys.executable,
        execution_context=context,
    )
    assert result["outcome"] == "completed", result
    receipt = result["execution_context"]
    assert receipt["context_sha256"] == CONTEXT["digest"](context.read_bytes())
    assert result["startup"]["execution_context"] == receipt
    assert result["initial"]["execution_context"] == receipt
    assert result["evaluation"]["execution_context"] == receipt
    report = json.loads(Path(result["initial"]["report_file"]).read_text())
    assert report["execution_context"] == receipt
    if arm == "graphunslopify":
        phase = json.loads((Path(result["initial"]["folder"]) / "phase-timings.json").read_text())
        assert phase["execution_context"] == receipt
    assert not receipt["formal_comparison_performed"]


def test_actual_worker_rejects_a_request_for_another_registered_figure(tmp_path):
    path = tmp_path / "context.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "mode": "preseal",
                "track": "local",
                "arm": "matplotlib",
                "case": {"figure": "iris-scatter", "profile": "checkout-current3.12", "repeat": 0},
            }
        )
    )
    runner = runpy.run_path(str(ROOT / "benchmarks/workspace/session_runner.py"))
    session = runner["LiveSession"]("matplotlib", tmp_path / "worker", execution_context=path)
    try:
        with pytest.raises(ValueError, match="registered execution case"):
            session.request({"operation": "render", "name": "first", "case": "penguins-mass/first"})
        assert session.request_sequence == 0
    finally:
        session.close()


def test_actual_child_also_rejects_wrong_case_when_parent_guard_is_bypassed(tmp_path):
    import subprocess
    import sys

    context = tmp_path / "context.json"
    context.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "mode": "preseal",
                "track": "local",
                "arm": "matplotlib",
                "case": {"figure": "iris-scatter", "profile": "checkout-current3.12", "repeat": 0},
            }
        )
    )
    root = tmp_path / "worker"
    root.mkdir()
    wrong = {"operation": "render", "name": "first", "case": "penguins-mass/first"}
    actual = subprocess.run(
        [
            sys.executable,
            str(ROOT / "benchmarks/workspace/session_worker.py"),
            "--root",
            str(root),
            "--arm",
            "matplotlib",
            "--execution-context",
            str(context),
        ],
        input=json.dumps(wrong) + "\n",
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert actual.returncode != 0
    assert "registered execution case" in actual.stderr
    assert not list((root / "producer").rglob("figure.png"))


def test_observer_refuses_changed_context_bytes(tmp_path):
    path = tmp_path / "context.json"
    path.write_text(json.dumps({"schema_version": 1, "mode": "preseal"}))
    original = CONTEXT["digest"](path.read_bytes())
    path.write_text(path.read_text() + "\n")
    with pytest.raises(ValueError, match="differs from its parent"):
        CONTEXT["observer"](path, original)


def test_actual_git_byte_closure_cannot_be_resealed_around_changed_sdk(tmp_path):
    """Synthetic CI metadata is only a validator fixture, never public CI evidence."""
    import shutil
    import subprocess

    runner = runpy.run_path(str(ROOT / "benchmarks/workspace/session_runner.py"))
    sources, package = runner["source_snapshot"](), runner["expected_package"]()
    repo = tmp_path / "implementation"
    for name in [*sources, *("python/graphunslopify/" + n for n in package)]:
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    executable = Path("/Library/Developer/CommandLineTools/usr/bin/git")
    command = str(executable) if executable.is_file() else shutil.which("git")
    assert command
    hooks = tmp_path / "empty-hooks"
    hooks.mkdir()

    def git(*args):
        return subprocess.check_output(
            [
                command,
                "-c",
                "gc.auto=0",
                "-c",
                "maintenance.auto=false",
                "-c",
                "core.hooksPath=" + str(hooks),
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                *args,
            ],
            cwd=repo,
            stderr=subprocess.PIPE,
        )

    git("init", "-q")
    git("add", ".")
    git("commit", "-qm", "Validator fixture")
    revision = git("rev-parse", "HEAD").decode().strip()
    ci = acceptance()
    ci["commit"] = revision
    for row in ci["workflows"]:
        row["head_sha"] = revision
    seal = {
        "schema_version": 1,
        "revision": revision,
        "protocol_sha256": CONTEXT["PROTOCOL_SHA256"],
        "exact_ci_acceptance": ci,
        "source_sha256": sources,
        "package_sha256": package,
    }
    # Correct Git/CI shape still lacks the complete prospective preparation qualification.
    with pytest.raises(ValueError, match="prospective preparation qualification"):
        CONTEXT["validate_seal"](seal, repo)
    omitted = copy.deepcopy(seal)
    omitted["source_sha256"].pop("benchmarks/workspace/execution_context.py")
    with pytest.raises(ValueError, match="closure"):
        CONTEXT["validate_seal"](omitted, repo)
    path = repo / "python/graphunslopify/preview.py"
    path.write_bytes(path.read_bytes() + b"\n# changed actual SDK bytes\n")
    resealed = copy.deepcopy(seal)
    resealed["package_sha256"]["preview.py"] = CONTEXT["digest"](path.read_bytes())
    with pytest.raises(ValueError, match="Sealed implementation bytes differ"):
        CONTEXT["validate_seal"](resealed, repo)
