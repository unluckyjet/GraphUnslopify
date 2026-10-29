"""Actual notebook kernels, editor process tasks, strict audits and manuscript builds."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest

from graphunslopify.errors import SpecError
from graphunslopify.notebook import execute_notebook
from graphunslopify.workflow import (
    DEFAULT_FOLDER,
    WorkflowError,
    _prepare_latex,
    initialize_workflow,
    locate_workflow,
    notebook_html,
    run_workflow,
)

ROOT = Path(__file__).resolve().parents[2]
CAPTION = r"Literal _&%#${}\^~ \input{sentinel}"


def paper(tmp_path):
    project = tmp_path / "paper ü with spaces"
    shutil.copytree(ROOT / "examples/paper", project)
    path = project / "training.figure.json"
    spec = json.loads(path.read_text())
    spec["caption"] = CAPTION
    path.write_text(json.dumps(spec))
    created = initialize_workflow(project)
    return project, Path(created["config"]).parent


def compile_tex(folder, name="paper.tex", expected=0):
    compiler = shutil.which("pdflatex")
    if not compiler:
        if os.environ.get("GRAPHUNSLOPIFY_REQUIRE_LATEX"):
            pytest.fail("required real pdflatex is missing")
        pytest.skip("real TeX runs in required render CI or with pdflatex installed")
    run = subprocess.run(
        [compiler, "-no-shell-escape", "-interaction=nonstopmode", "-halt-on-error", name],
        cwd=folder,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert (run.returncode == 0) == (expected == 0), run.stdout[-3500:] + run.stderr
    return run


def test_init_preserves_inputs_editor_settings_and_existing_folders(tmp_path):
    project = tmp_path / "project"
    shutil.copytree(ROOT / "examples/paper", project)
    settings = project / ".vscode"
    settings.mkdir()
    (settings / "tasks.json").write_text("original user tasks")
    original = {
        str(p.relative_to(project)): p.read_bytes() for p in project.rglob("*") if p.is_file()
    }
    created = initialize_workflow(project)
    folder = Path(created["config"]).parent
    for name, data in original.items():
        assert (project / name).read_bytes() == data
    assert {p.name for p in folder.iterdir()} == {
        "owner.json",
        "workflow.json",
        "run.py",
        "review.ipynb",
        "paper.code-workspace",
        "latex",
        "README.md",
        ".gitignore",
    }
    notebook = json.loads((folder / "review.ipynb").read_text())
    assert all(
        not cell.get("outputs") and cell.get("execution_count") is None
        for cell in notebook["cells"]
    )
    assert "\\PackageError" in (folder / "latex/figures.tex").read_text()
    before = {str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
    with pytest.raises(FileExistsError):
        initialize_workflow(project)
    assert before == {
        str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob("*") if p.is_file()
    }
    assert (settings / "tasks.json").read_text() == "original user tasks"


@pytest.mark.parametrize(
    "name",
    [
        "../outside",
        "/absolute",
        ".",
        "..",
        ".git",
        ".vscode",
        "CON",
        "con.txt",
        "LPT1",
        "trailing.",
        "bad folder",
        "bad${env:HOME}",
    ],
)
def test_nonportable_or_reserved_names_are_rejected_before_writing(tmp_path, name):
    shutil.copytree(ROOT / "examples/paper", tmp_path / "project")
    before = set((tmp_path / "project").iterdir())
    with pytest.raises(WorkflowError):
        initialize_workflow(tmp_path / "project", folder=name)
    assert set((tmp_path / "project").iterdir()) == before


@pytest.fixture(scope="module")
def accepted(tmp_path_factory):
    configured = os.environ.get("GRAPHUNSLOPIFY_WORKFLOW_EVIDENCE")
    if configured:
        root = Path(configured)
        root.mkdir(parents=True, exist_ok=False)
    else:
        root = tmp_path_factory.mktemp("workflow accepted")
    project, folder = paper(root)
    original = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in project.iterdir() if p.is_file()
    }
    result = run_workflow(folder, latex=True)
    assert result["exit_code"] == 0, result
    return project, folder, result, original


def test_real_multi_figure_audit_prepares_exact_verified_widths_and_preserves_inputs(accepted):
    project, folder, result, original = accepted
    assert result["status"] == "passed" and result["audit_status"] == "passed"
    assert result["audit"]["counts"] == {"passed": 2, "failed": 0, "incomplete": 0}
    assert result["latex"]["status"] == "prepared" and result["latex"]["compiled"] is False
    for item in result["latex"]["artifacts"]:
        data = (folder / item["path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == item["sha256"]
        assert item["target_width_in"] == 3.4
    assert original == {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in project.iterdir() if p.is_file()
    }
    source = (folder / "latex/figures.tex").read_text()
    assert "width=3.4in" in source and "\\ifdim 3.4in>\\linewidth" in source
    assert r"\textbackslash{}input\{sentinel\}" in source
    html = notebook_html(result)
    assert html.count("data:image/png;base64,") == 2
    assert "Source audit: passed" in html


def test_actual_example_and_existing_manuscript_includes_compile_without_interpreting_caption(
    accepted,
):
    pytest.importorskip("pypdf")
    from pypdf import PdfReader

    project, folder, _result, _original = accepted
    latex = folder / "latex"
    (latex / "sentinel.tex").write_text("INJECTED_SENTINEL")
    compile_tex(latex)
    text = "\n".join(page.extract_text() or "" for page in PdfReader(latex / "paper.pdf").pages)
    assert "INJECTED_SENTINEL" not in text
    assert "Literal" in text and "sentinel" in text
    # PDF encodings can expose compatibility ligatures and unreliable spacing.
    # Only the fixed heading assertion is normalized; source data is never changed.
    normalized = "".join(unicodedata.normalize("NFKC", text).split())
    (latex / "extracted-text.json").write_text(
        json.dumps(
            {"raw": text, "normalized_heading_text": normalized}, indent=2, ensure_ascii=False
        ),
        encoding="utf8",
    )
    assert "Checkedfigureexports" in normalized, repr(text)
    assert normalized.index("Checkedfigureexports") < normalized.index("Literal"), repr(text)
    (project / "main.tex").write_text(
        r"\documentclass{article}\usepackage[T1]{fontenc}\usepackage{graphicx}\begin{document}"
        + f"\\input{{{DEFAULT_FOLDER}/latex/include.tex}}"
        + r"\end{document}"
    )
    compile_tex(project, "main.tex")
    assert (project / "main.pdf").is_file()


def test_manuscript_line_width_guard_rejects_silent_rescaling(accepted):
    _, folder, _, _ = accepted
    latex = folder / "latex"
    (latex / "narrow.tex").write_text(
        r"\documentclass{article}\usepackage{graphicx}\setlength{\textwidth}{2in}\begin{document}\input{figures.tex}\end{document}"
    )
    result = compile_tex(latex, "narrow.tex", expected=2)
    assert "needs 3.4in line width" in result.stdout


def test_editor_process_task_uses_selected_interpreter_and_actual_args_from_foreign_cwd(tmp_path):
    project, folder = paper(tmp_path)
    workspace = json.loads((folder / "paper.code-workspace").read_text())
    assert workspace["folders"] == [{"name": "paper", "path": ".."}]
    task = workspace["tasks"]["tasks"][0]
    assert task["type"] == "process" and task["command"] == "${command:python.interpreterPath}"
    args = [x.replace("${workspaceFolder:paper}", str(project)) for x in task["args"]]
    run = subprocess.run(
        [sys.executable, *args], cwd=tmp_path, capture_output=True, text=True, check=False
    )
    assert run.returncode == 0, run.stderr
    result = json.loads(run.stdout)
    assert result["audit"]["counts"]["passed"] == 2 and result["latex"]["status"] == "not_requested"
    assert "\\PackageError" in (folder / "latex/figures.tex").read_text()
    build = workspace["tasks"]["tasks"][2]
    assert build["dependsOn"] == "Prepare checked LaTeX figures"
    assert build["args"] == [
        "-no-shell-escape",
        "-interaction=nonstopmode",
        "-halt-on-error",
        "paper.tex",
    ]


def test_notebook_locator_accepts_only_its_owner_and_both_kernel_working_directories(
    tmp_path, monkeypatch
):
    project, folder = paper(tmp_path)
    identifier = json.loads((folder / "owner.json").read_text())["workflow_id"]
    for cwd in [project, folder]:
        monkeypatch.chdir(cwd)
        assert locate_workflow(identifier) == folder / "workflow.json"
        with pytest.raises(WorkflowError):
            locate_workflow("0" * 32)
    # An unrelated root config is not silently chosen over the notebook's marker.
    (project / "workflow.json").write_text("{}")
    monkeypatch.chdir(project)
    assert locate_workflow(identifier) == folder / "workflow.json"


@pytest.mark.parametrize("cwd", ["notebook", "project"])
def test_real_kernel_runs_generated_project_notebook_with_inline_verified_figures(tmp_path, cwd):
    pytest.importorskip("nbclient")
    pytest.importorskip("ipykernel")
    project, folder = paper(tmp_path)
    if cwd == "notebook":
        execute_notebook(folder / "review.ipynb")
        notebook = json.loads((folder / "review.ipynb").read_text())
    else:
        import nbformat
        from nbclient import NotebookClient

        notebook = nbformat.read(folder / "review.ipynb", as_version=4)
        client = NotebookClient(
            notebook,
            timeout=120,
            kernel_name="python3",
            resources={"metadata": {"path": str(project)}},
        )
        client.km = client.create_kernel_manager()
        client.km.kernel_spec.argv = [
            sys.executable,
            "-m",
            "ipykernel_launcher",
            "-f",
            "{connection_file}",
        ]
        client.execute()
    outputs = [out for cell in notebook["cells"] for out in cell.get("outputs", [])]
    html = "".join("".join(out.get("data", {}).get("text/html", "")) for out in outputs)
    assert html.count("data:image/png;base64,") == 2
    assert "Source audit: passed" in html
    assert any("workflow accepted" in "".join(out.get("text", "")) for out in outputs)


def test_real_kernel_retains_failed_audit_and_rejects_final_cell(tmp_path):
    pytest.importorskip("nbclient")
    pytest.importorskip("ipykernel")
    project, folder = paper(tmp_path)
    path = project / "training.figure.json"
    spec = json.loads(path.read_text())
    spec["claims"][0].update(subject="base", reference="ours")
    path.write_text(json.dumps(spec))
    with pytest.raises(SpecError, match="Notebook execution failed"):
        execute_notebook(folder / "review.ipynb")
    notebook = json.loads((folder / "review.ipynb").read_text())
    outputs = [out for cell in notebook["cells"] for out in cell.get("outputs", [])]
    assert any(out.get("output_type") == "error" for out in outputs)
    html = "".join("".join(out.get("data", {}).get("text/html", "")) for out in outputs)
    assert "Source audit: failed" in html and html.count("data:image/png;base64,") == 2
    saved = json.loads((folder / "workflow.report.json").read_text())
    assert (
        saved["exit_code"] == 2
        and saved["audit"]["figures"][0]["report"]["claims"][0]["verdict"] == "fails"
    )


def test_failed_latex_run_invalidates_previous_include_and_recovers_to_new_owned_run(tmp_path):
    project, folder = paper(tmp_path)
    first = run_workflow(folder, latex=True)
    assert first["exit_code"] == 0, first
    old = (folder / "latex/figures.tex").read_text()
    path = project / "training.figure.json"
    original = path.read_bytes()
    spec = json.loads(original)
    spec["claims"][0].update(subject="base", reference="ours")
    path.write_text(json.dumps(spec))
    failed = run_workflow(folder, latex=True)
    assert (
        failed["exit_code"] == 2
        and failed["audit_status"] == "failed"
        and failed["latex"]["status"] == "rejected"
    )
    assert "\\PackageError" in (folder / "latex/figures.tex").read_text()
    compile_tex(folder / "latex", expected=2)
    for item in first["latex"]["artifacts"]:
        assert (folder / item["path"]).is_file()
    path.write_bytes(original)
    recovered = run_workflow(folder, latex=True)
    assert recovered["exit_code"] == 0, recovered
    assert (folder / "latex/figures.tex").read_text() != old
    compile_tex(folder / "latex")


@pytest.mark.parametrize(
    "fault", ["config_json", "wrong_owner_id", "manifest_removed", "manifest_invalid"]
)
def test_input_errors_do_not_leave_stale_accepted_tex(tmp_path, fault):
    project, folder = paper(tmp_path)
    # Simulate a previously prepared owned include without another render.
    tex = folder / "latex/figures.tex"
    tex.write_text("% prior accepted include")
    if fault == "config_json":
        (folder / "workflow.json").write_text("{broken")
    elif fault == "wrong_owner_id":
        path = folder / "workflow.json"
        data = json.loads(path.read_text())
        data["workflow_id"] = "0" * 32
        path.write_text(json.dumps(data))
    elif fault == "manifest_removed":
        (project / "graphunslopify.json").unlink()
    else:
        (project / "graphunslopify.json").write_text("{}")
    result = run_workflow(folder, latex=True)
    assert result["exit_code"] == 2 and result["errors"]
    assert "\\PackageError" in tex.read_text()
    assert json.loads((folder / "workflow.report.json").read_text())["exit_code"] == 2


def test_owned_symlink_does_not_overwrite_a_manuscript(tmp_path):
    _, folder = paper(tmp_path)
    manuscript = tmp_path / "private.tex"
    manuscript.write_text("keep manuscript")
    target = folder / "latex/figures.tex"
    target.unlink()
    try:
        target.symlink_to(manuscript)
    except OSError:
        pytest.skip("host does not allow symlink creation")
    with pytest.raises(WorkflowError, match="symlink"):
        run_workflow(folder, latex=True)
    assert manuscript.read_text() == "keep manuscript"


def test_notebook_refuses_changed_saved_artifact_bytes(accepted):
    _, _folder, result, _ = accepted
    modified = copy.deepcopy(result)
    modified["audit"]["figures"][0]["outputs"][0]["sha256"] = "0" * 64
    with pytest.raises(WorkflowError, match="changed since audit"):
        notebook_html(modified)


def test_latex_does_not_guess_missing_recorded_width(accepted, tmp_path):
    _, _folder, result, _ = accepted
    alternate = tmp_path / "workflow"
    alternate.mkdir()
    (alternate / "latex").mkdir()
    record = copy.deepcopy(result["audit"])
    record["figures"][0]["report"].pop("environment")
    with pytest.raises(WorkflowError, match="recorded manuscript target width"):
        _prepare_latex(alternate, record)


def test_svg_only_latex_preparation_rejects_without_fabricating_failed_numerical_checks(tmp_path):
    project, folder = paper(tmp_path)
    manifest = json.loads((project / "graphunslopify.json").read_text())
    manifest["figures"] = manifest["figures"][:1]
    (project / "graphunslopify.json").write_text(json.dumps(manifest))
    path = project / "training.figure.json"
    spec = json.loads(path.read_text())
    spec["output"]["formats"] = ["svg"]
    path.write_text(json.dumps(spec))
    result = run_workflow(folder, latex=True)
    assert (
        result["audit_status"] == "passed"
        and result["status"] == "failed"
        and result["exit_code"] == 2
    )
    assert "PDF or PNG" in result["errors"][0]
    assert "\\PackageError" in (folder / "latex/figures.tex").read_text()


def test_copied_project_workflow_stays_relative_and_resolves_without_original(tmp_path):
    project, _folder = paper(tmp_path)
    moved = tmp_path / "moved paper"
    shutil.move(project, moved)
    result = run_workflow(moved / DEFAULT_FOLDER, latex=True)
    assert result["exit_code"] == 0, result
    assert result["audit"]["counts"]["passed"] == 2


def test_double_column_png_is_included_at_its_checked_width_in_a_two_column_manuscript(tmp_path):
    project, folder = paper(tmp_path)
    manifest = json.loads((project / "graphunslopify.json").read_text())
    manifest["figures"] = manifest["figures"][:1]
    (project / "graphunslopify.json").write_text(json.dumps(manifest))
    path = project / "training.figure.json"
    spec = json.loads(path.read_text())
    spec["output"].update(size="double_column", formats=["png"])
    path.write_text(json.dumps(spec))
    result = run_workflow(folder, latex=True)
    assert result["exit_code"] == 0, result
    assert result["latex"]["artifacts"][0]["target_width_in"] == 7
    assert result["latex"]["artifacts"][0]["path"].endswith(".png")
    source = (folder / "latex/figures.tex").read_text()
    assert "\\begin{figure*}" in source and "width=7in" in source
    (folder / "latex/double.tex").write_text(
        r"\documentclass[twocolumn]{article}\usepackage[paperwidth=10in,textwidth=7in]{geometry}\usepackage[T1]{fontenc}\usepackage{graphicx}\begin{document}\input{figures.tex}\end{document}"
    )
    compile_tex(folder / "latex", "double.tex")
