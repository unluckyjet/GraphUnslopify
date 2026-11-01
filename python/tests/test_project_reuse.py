"""Real strict executions, verified copies and conservative cache invalidation."""

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from graphunslopify import Figure
from graphunslopify import audit as auditing
from graphunslopify import project as model
from graphunslopify.cli import main
from graphunslopify.project_review import project_review

ROOT = Path(__file__).resolve().parents[2]


def load(path):
    return json.loads(path.read_text())


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


@pytest.fixture(scope="module")
def accepted(tmp_path_factory):
    root = tmp_path_factory.mktemp("native-reuse") / "paper ü with spaces"
    shutil.copytree(ROOT / "examples/paper", root)
    shutil.copyfile(root / "results.csv", root / "table.csv")
    path = root / "results.figure.json"
    spec = load(path)
    spec["data"]["path"] = "table.csv"
    save(path, spec)
    model.initialize_project(root)
    first = model.run_project(root, baseline=None)
    assert first["exit_code"] == 0 and first["reuse_guard"]["key"], first
    backup = root.parent / "baseline-copy"
    shutil.copytree(root, backup)
    return root, backup, first


@pytest.fixture
def paper(accepted):
    root, backup, first = accepted
    # Restore only this test-owned directory at its original physical path.
    shutil.rmtree(root)
    shutil.copytree(backup, root)
    return root, first


def counts(result, executed, reused, not_run=0):
    assert result["audit"]["execution_counts"] == {
        "executed": executed,
        "reused": reused,
        "not_run": not_run,
    }, result


def row(result, identity):
    return next(f for f in result["audit"]["figures"] if f["id"] == identity)


def observe_executions(monkeypatch):
    calls = []
    actual = auditing._run

    def observed(command, folder, timeout, **options):
        if len(command) > 1 and Path(command[1]).name == "figure.py":
            calls.append(folder.name)
        return actual(command, folder, timeout, **options)

    monkeypatch.setattr(auditing, "_run", observed)
    return calls


def test_real_unchanged_reuse_copies_reports_exports_without_figure_processes(paper, monkeypatch):
    root, first = paper
    calls = observe_executions(monkeypatch)
    second = model.run_project(root, selective=True)
    counts(second, 0, 2)
    assert second["exit_code"] == 0 and not calls
    third = model.run_project(root, selective=True)
    counts(third, 0, 2)
    assert third["exit_code"] == 0 and not calls
    for name in ("training", "results-table"):
        original = row(first, name)
        copied = row(third, name)
        assert copied["report"] == original["report"]
        assert copied["execution"]["origin_event"] == first["id"]
        assert copied["execution"]["source_event"] == second["id"]
        for before, after in zip(original["outputs"], copied["outputs"], strict=True):
            assert (Path(first["directory"]) / "audit" / before["path"]).read_bytes() == (
                Path(third["directory"]) / "audit" / after["path"]
            ).read_bytes()
    assert model.project_history(root)["integrity"] == "verified"
    review = project_review(root)
    assert all(
        f["groups"]["reproduction"]["execution"]["mode"] == "reused" for f in review["figures"]
    )


@pytest.mark.parametrize("change", ["definition", "independent_data"])
def test_only_actual_changed_figure_executes(paper, monkeypatch, change):
    root, _ = paper
    if change == "definition":
        path = root / "results.figure.json"
        spec = load(path)
        spec["title"] = "Current table wording"
        save(path, spec)
    else:
        path = root / "table.csv"
        path.write_text(path.read_text().replace("1,4,ours", "1,6,ours"))
    calls = observe_executions(monkeypatch)
    result = model.run_project(root, selective=True)
    counts(result, 1, 1)
    assert result["exit_code"] == 0 and calls == ["results-table"]
    assert row(result, "training")["execution"]["mode"] == "reused"


@pytest.mark.parametrize(
    "filename",
    [
        "figure.py",
        "runtime.report.json",
        "input.spec.json",
        "stdout.log",
        "stderr.log",
        "training.png",
        "training.svg",
        "training.pdf",
    ],
)
def test_damaged_saved_program_report_or_export_requires_actual_rerun(paper, monkeypatch, filename):
    root, first = paper
    directory = (
        Path(first["directory"]) / "audit" / first["audit"]["run_directory"] / "figures/training"
    )
    path = directory / filename
    path.write_bytes(path.read_bytes() + b"\nchanged")
    calls = observe_executions(monkeypatch)
    result = model.run_project(root, selective=True, baseline=None)
    counts(result, 1, 1)
    assert result["exit_code"] == 0 and calls == ["training"]


def test_warning_policy_is_rechecked_by_real_executions(paper, monkeypatch):
    root, _ = paper
    calls = observe_executions(monkeypatch)
    result = model.run_project(root, selective=True, fail_on_warning=True)
    counts(result, 2, 0)
    assert result["exit_code"] == 2 and len(calls) == 2
    assert all(f["report"]["policy"]["fail_on_warning"] for f in result["audit"]["figures"])


def test_real_shared_policy_changes_execute_figures(paper, monkeypatch):
    root, _ = paper
    calls = observe_executions(monkeypatch)
    model.set_project_shared(
        root, {"style": {"grid": True}}, expected_revision=model.project_status(root)["revision"]
    )
    result = model.run_project(root, selective=True)
    counts(result, 2, 0)
    assert result["exit_code"] == 0 and len(calls) == 2
    assert all(f["report"]["spec"]["style"]["grid"] for f in result["audit"]["figures"])


def test_newer_actual_failed_run_cannot_borrow_older_acceptance(paper, monkeypatch):
    root, _ = paper
    path = root / "training.figure.json"
    original = path.read_bytes()
    spec = load(path)
    spec["claims"][0].update(subject="base", reference="ours")
    save(path, spec)
    failed = model.run_project(root, selective=True)
    assert failed["exit_code"] == 2 and row(failed, "training")["status"] == "failed"
    path.write_bytes(original)
    calls = observe_executions(monkeypatch)
    result = model.run_project(root, selective=True)
    counts(result, 2, 0)
    assert result["exit_code"] == 0 and len(calls) == 2
    assert model.project_history(root)["events"][1]["result"]["exit_code"] == 2


@pytest.mark.parametrize("kind", ["receipt", "incomplete"])
def test_damaged_or_incomplete_history_never_falls_back(paper, monkeypatch, kind):
    root, first = paper
    if kind == "receipt":
        (Path(first["directory"]) / "receipt.json").write_text("{}")
    else:
        folder = root / "graphunslopify-project/history" / ("00000002-" + "f" * 32)
        folder.mkdir()
        (folder / "started.json").write_text("{}")
    calls = observe_executions(monkeypatch)
    result = model.run_project(root, selective=True, baseline=None)
    counts(result, 2, 0)
    assert result["exit_code"] == 0 and len(calls) == 2
    assert model.project_history(root)["integrity"] == "partial"


def test_real_environment_configuration_change_prevents_reuse(paper, tmp_path, monkeypatch):
    root, _ = paper
    config = tmp_path / "plot-config"
    config.mkdir()
    (config / "matplotlibrc").write_text("font.size: 17\n")
    monkeypatch.setenv("MPLCONFIGDIR", str(config))
    calls = observe_executions(monkeypatch)
    result = model.run_project(root, selective=True)
    counts(result, 2, 0)
    assert result["exit_code"] == 0 and len(calls) == 2


def test_moved_project_gets_fresh_execution(paper, tmp_path, monkeypatch):
    root, _ = paper
    moved = tmp_path / "moved"
    shutil.copytree(root, moved)
    calls = observe_executions(monkeypatch)
    result = model.run_project(moved, selective=True, baseline=None)
    counts(result, 2, 0)
    assert result["exit_code"] == 0 and len(calls) == 2


@pytest.mark.parametrize("change", ["producer", "legacy"])
def test_legacy_or_inconsistent_producer_needs_fresh_execution(paper, monkeypatch, change):
    root, first = paper
    folder = Path(first["directory"])
    result = load(folder / "result.json")
    if change == "legacy":
        result.pop("reuse_guard")
    else:
        result["execution_source"]["sha256"] = "0" * 64
    # Change optional/local metadata, retaining actual reports/programs/exports.
    # Rebind its receipt to test semantic guards beyond raw-byte corruption.
    save(folder / "result.json", result)
    receipt = load(folder / "receipt.json")
    item = next(f for f in receipt["files"] if f["path"] == "result.json")
    data = (folder / "result.json").read_bytes()
    item.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    save(folder / "receipt.json", receipt)
    assert model.project_history(root)["integrity"] == "verified"
    calls = observe_executions(monkeypatch)
    result = model.run_project(root, selective=True, baseline=None)
    counts(result, 2, 0)
    assert result["exit_code"] == 0 and len(calls) == 2


def test_invalid_intent_has_no_false_execution_count_and_retains_other_figures(paper):
    root, _ = paper
    path = root / "training.figure.json"
    spec = load(path)
    spec["kind"] = "not-a-figure"
    save(path, spec)
    result = model.run_project(root, selective=True, baseline=None)
    counts(result, 0, 1, 1)
    assert result["exit_code"] == 2 and row(result, "training")["report"] is None


def test_prior_source_edit_during_other_execution_refuses_copied_acceptance(paper, monkeypatch):
    root, first = paper
    path = root / "results.figure.json"
    spec = load(path)
    spec["title"] = "Fresh table"
    save(path, spec)
    original_program = (
        Path(first["directory"])
        / "audit"
        / first["audit"]["run_directory"]
        / "figures/training/figure.py"
    )
    actual = auditing._audit_one

    def edit_during(entry, *args, **kwargs):
        original_program.write_bytes(original_program.read_bytes() + b"\n# concurrent edit\n")
        return actual(entry, *args, **kwargs)

    monkeypatch.setattr(auditing, "_audit_one", edit_during)
    result = model.run_project(root, selective=True, baseline=None)
    counts(result, 1, 1)
    assert result["exit_code"] == 2
    assert any("evidence changed during" in message for message in result["errors"])


def test_cli_reports_actual_reuse_counts(paper, capsys):
    root, _ = paper
    assert main(["project-run", str(root), "--selective"]) == 0
    result = json.loads(capsys.readouterr().out)
    counts(result, 0, 2)


def test_non_boolean_request_refuses_before_new_history(paper):
    root, _ = paper
    before = model.project_history(root)
    with pytest.raises(model.ProjectError, match="true or false"):
        model.run_project(root, selective="yes")
    assert before == model.project_history(root)


def test_authored_script_with_declared_data_always_actually_executes(paper):
    root, _ = paper
    spec = load(root / "training.figure.json")
    spec["output"]["stem"] = "authored"
    code = Figure(spec).translate(api="local")["code"]
    lines = code.splitlines(keepends=True)
    index = max(
        (i + 1 for i, line in enumerate(lines) if line.startswith("from __future__")), default=0
    )
    lines.insert(
        index,
        "_reuse_test_counter = __import__('pathlib').Path(__file__).with_name('executions.txt')\n_reuse_test_counter.write_text((_reuse_test_counter.read_text() if _reuse_test_counter.exists() else '') + 'x')\n",
    )
    (root / "authored.py").write_text("".join(lines))
    manifest = load(root / "graphunslopify.json")
    manifest["figures"].append({"id": "authored", "script": "authored.py", "data": "results.csv"})
    save(root / "graphunslopify.json", manifest)
    first = model.run_project(root, baseline=None)
    counts(first, 3, 0)
    assert first["exit_code"] == 0, first
    assert (root / "executions.txt").read_text() == "x"
    second = model.run_project(root, selective=True)
    counts(second, 1, 2)
    assert second["exit_code"] == 0 and (root / "executions.txt").read_text() == "xx"
    assert row(second, "authored")["execution"]["mode"] == "executed"


def test_actual_render_configuration_change_during_work_refuses_reuse(paper, tmp_path, monkeypatch):
    root, _ = paper
    config = tmp_path / "matplotlib"
    config.mkdir()
    settings = config / "matplotlibrc"
    settings.write_text("font.size: 10\n")
    monkeypatch.setenv("MPLCONFIGDIR", str(config))
    first = model.run_project(root, baseline=None)
    assert first["exit_code"] == 0
    spec = load(root / "results.figure.json")
    spec["title"] = "A fresh table"
    save(root / "results.figure.json", spec)
    actual = auditing._audit_one

    def change_configuration(entry, *args, **kwargs):
        settings.write_text("font.size: 17\n")
        return actual(entry, *args, **kwargs)

    monkeypatch.setattr(auditing, "_audit_one", change_configuration)
    result = model.run_project(root, selective=True, baseline=None)
    counts(result, 1, 1)
    assert result["exit_code"] == 2
    assert any("environment changed during" in message for message in result["errors"])


def test_native_program_identity_survives_windows_style_host_text_writes(tmp_path, monkeypatch):
    root = tmp_path / "paper"
    shutil.copytree(ROOT / "examples/paper", root)
    actual = Path.write_text

    def windows_text(path, content, *args, **options):
        if path.name == "figure.py":
            options["newline"] = "\r\n"
        return actual(path, content, *args, **options)

    # Exercise actual strict programs with the host text conversion that Windows
    # applies, without treating normalized source as the original executed bytes.
    monkeypatch.setattr(Path, "write_text", windows_text)
    model.initialize_project(root)
    first = model.run_project(root, baseline=None)
    assert first["exit_code"] == 0
    second = model.run_project(root, selective=True, baseline=None)
    counts(second, 0, 2)
    assert second["exit_code"] == 0
    for before, after in zip(first["audit"]["figures"], second["audit"]["figures"], strict=True):
        directory = Path(first["directory"]) / "audit" / first["audit"]["run_directory"]
        raw = (directory / "figures" / before["id"] / "figure.py").read_bytes()
        assert b"\r\n" not in raw
        assert hashlib.sha256(raw).hexdigest() == before["report"]["script"]["sha256"]
        assert after["report"] == before["report"]
        assert after["execution"]["origin_event"] == first["id"]
