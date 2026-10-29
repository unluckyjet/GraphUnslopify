"""One manifest audit across notebook, editor, terminal and manuscript workflows."""

from __future__ import annotations

import base64
import hashlib
import html
import json
import math
import re
import uuid
from pathlib import Path

from .audit import audit, load_manifest

DEFAULT_FOLDER = "graphunslopify-workflow"
_KIND = "graphunslopify.research-workflow"
_GUARD = r"""% Generated acceptance guard. Do not use stale figure includes.
\PackageError{GraphUnslopify}{Figure preparation is not accepted}{Run the project workflow with --latex and inspect its report before building the manuscript.}
"""
_DRIVER = """from pathlib import Path
import sys
from graphunslopify.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["workflow-run", str(Path(__file__).with_name("workflow.json")), *sys.argv[1:]]))
"""


class WorkflowError(ValueError):
    """Workflow configuration, acceptance or manuscript evidence is unavailable."""


def _folder_name(value: str) -> str:
    reserved = {
        ".",
        "..",
        ".git",
        ".vscode",
        ".venv",
        "venv",
        "node_modules",
        "con",
        "prn",
        "aux",
        "nul",
    }
    if (
        not isinstance(value, str)
        or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", value)
        or value.casefold() in reserved
        or value.endswith(".")
        or value.split(".")[0].casefold() in {"con", "prn", "aux", "nul"}
        or re.fullmatch(r"(com|lpt)[1-9](\..*)?", value, re.IGNORECASE)
    ):
        raise WorkflowError(
            "folder must be a new portable child name (letters, digits, dots, underscores or hyphens)"
        )
    return value


def _owned(root: Path, relative: str) -> Path:
    target = root / relative
    part = root
    for component in Path(relative).parts:
        part = part / component
        if part.is_symlink():
            raise WorkflowError("owned workflow paths cannot be symlinks")
    if not target.resolve().is_relative_to(root.resolve()):
        raise WorkflowError("owned workflow path escapes its directory")
    return target


def _config_source(path: str | Path) -> Path:
    source = Path(path).expanduser().resolve()
    if source.is_dir():
        source = (
            source / "workflow.json"
            if (source / "workflow.json").is_file()
            else source / DEFAULT_FOLDER / "workflow.json"
        )
    return source


def _owner(folder: Path) -> dict:
    value = json.loads((folder / "owner.json").read_text(encoding="utf8"))
    if (
        not isinstance(value, dict)
        or set(value) != {"kind", "workflow_id"}
        or value["kind"] != _KIND
        or not isinstance(value["workflow_id"], str)
        or not re.fullmatch("[a-f0-9]{32}", value["workflow_id"])
    ):
        raise WorkflowError("not an owned GraphUnslopify workflow folder")
    return value


def _config(path: str | Path) -> tuple[Path, dict]:
    source = _config_source(path)
    owner = _owner(source.parent)
    value = json.loads(source.read_text(encoding="utf8"))
    fields = {"schema_version", "kind", "workflow_id", "manifest", "folder"}
    if (
        not isinstance(value, dict)
        or set(value) != fields
        or type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or value["kind"] != _KIND
        or not isinstance(value["workflow_id"], str)
        or not re.fullmatch("[a-f0-9]{32}", value["workflow_id"])
        or value["workflow_id"] != owner["workflow_id"]
    ):
        raise WorkflowError("not a version1 GraphUnslopify workflow config")
    _folder_name(value["folder"])
    name = value["manifest"]
    if (
        not isinstance(name, str)
        or not name.startswith("../")
        or not name[3:]
        or name[3:] in {".", ".."}
        or "/" in name[3:]
        or "\\" in name[3:]
    ):
        raise WorkflowError(
            "workflow manifest must name a file directly beside the workflow folder"
        )
    return source, value


def locate_workflow(workflow_id: str, folder: str = DEFAULT_FOLDER) -> Path:
    """Find this notebook's specific config from either supported kernel cwd."""
    _folder_name(folder)
    for path in [Path.cwd() / folder / "workflow.json", Path.cwd() / "workflow.json"]:
        try:
            value = _owner(path.parent)
        except (OSError, ValueError):
            continue
        if value["workflow_id"] == workflow_id:
            return path.resolve()
    raise WorkflowError(
        "Open this notebook from its project root or workflow folder, or set CONFIG to its workflow.json path."
    )


def _cell(kind: str, source: str) -> dict:
    cell = {
        "cell_type": kind,
        "id": uuid.uuid4().hex[:8],
        "metadata": {},
        "source": source.splitlines(keepends=True),
    }
    if kind == "code":
        cell.update(execution_count=None, outputs=[])
    return cell


def initialize_workflow(path: str | Path = ".", *, folder: str = DEFAULT_FOLDER) -> dict:
    source, manifest = load_manifest(path)
    name = _folder_name(folder)
    destination = source.parent / name
    # Exclusively create a new owned folder; never merge into user editor settings.
    destination.mkdir(exist_ok=False)
    identifier = uuid.uuid4().hex
    (destination / "owner.json").write_text(
        json.dumps({"kind": _KIND, "workflow_id": identifier}, indent=2) + "\n", encoding="utf8"
    )
    configuration = {
        "schema_version": 1,
        "kind": _KIND,
        "workflow_id": identifier,
        "manifest": "../" + source.name,
        "folder": name,
    }
    (destination / "workflow.json").write_text(
        json.dumps(configuration, indent=2) + "\n", encoding="utf8"
    )
    (destination / "run.py").write_text(_DRIVER, encoding="utf8")
    (destination / ".gitignore").write_text(
        "audit/\nworkflow.report.json\nlatex/runs/\nlatex/figures.tex\nlatex/*.pdf\nlatex/*.aux\nlatex/*.log\n",
        encoding="utf8",
    )
    command = "${command:python.interpreterPath}"
    driver = "${workspaceFolder:paper}/" + name + "/run.py"
    tasks = []
    for label, flags in [("Audit all figures", []), ("Prepare checked LaTeX figures", ["--latex"])]:
        tasks.append(
            {
                "label": label,
                "type": "process",
                "command": command,
                "args": [driver, *flags],
                "options": {"cwd": "${workspaceFolder:paper}"},
                "problemMatcher": [],
            }
        )
    tasks.append(
        {
            "label": "Build example manuscript",
            "type": "process",
            "command": "pdflatex",
            "args": ["-no-shell-escape", "-interaction=nonstopmode", "-halt-on-error", "paper.tex"],
            "options": {"cwd": "${workspaceFolder:paper}/" + name + "/latex"},
            "dependsOn": "Prepare checked LaTeX figures",
            "dependsOrder": "sequence",
            "problemMatcher": [],
        }
    )
    workspace = {
        "folders": [{"name": "paper", "path": ".."}],
        "extensions": {"recommendations": ["ms-python.python", "ms-toolsai.jupyter"]},
        "tasks": {"version": "2.0.0", "tasks": tasks},
    }
    (destination / "paper.code-workspace").write_text(
        json.dumps(workspace, indent=2) + "\n", encoding="utf8"
    )
    notebook = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "cells": [
            _cell(
                "markdown",
                "# Review project figures\n\nSelect the Python environment with the current GraphUnslopify source installed. This notebook runs the same manifest audit as the terminal/editor. Source data stays in the project. Failed checks remain visible and reject the final cell.\n",
            ),
            _cell(
                "code",
                "from graphunslopify.workflow import locate_workflow, run_workflow, notebook_html\nfrom IPython.display import HTML, display\n\n"
                + f"CONFIG = locate_workflow({identifier!r}, {name!r})\n"
                + "result = run_workflow(CONFIG)\ndisplay(HTML(notebook_html(result)))\n",
            ),
            _cell(
                "markdown",
                "Inspect the source statuses, claims and saved evidence above. A picture is not proof that its scientific checks passed. Run `python run.py --latex` from this workflow folder to prepare accepted manuscript exports.\n",
            ),
            _cell(
                "code",
                'if result["exit_code"] != 0:\n    raise RuntimeError("Figure workflow rejected acceptance; inspect result and the audit report.")\nprint("Figure workflow accepted; manuscript compilation is a separate step.")\n',
            ),
        ],
    }
    (destination / "review.ipynb").write_text(
        json.dumps(notebook, indent=2, ensure_ascii=False) + "\n", encoding="utf8"
    )
    latex = destination / "latex"
    latex.mkdir()
    (latex / "figures.tex").write_text(_GUARD, encoding="utf8")
    (latex / "include.tex").write_text(
        "\\begingroup\n"
        + f"\\def\\GraphUnslopifyFigureRoot{{{name}/latex}}\n"
        + r"\input{\GraphUnslopifyFigureRoot/figures.tex}"
        + "\n\\endgroup\n",
        encoding="utf8",
    )
    (latex / "paper.tex").write_text(
        r"""\documentclass{article}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\ifdefined\pdfgentounicode
\input{glyphtounicode}
\pdfgentounicode=1
\fi
\usepackage[paperwidth=10in,paperheight=12in,margin=1in]{geometry}
\usepackage{graphicx}
\begin{document}
\section*{Checked figure exports}
\input{figures.tex}
\end{document}
""",
        encoding="utf8",
    )
    (destination / "README.md").write_text(
        f"""# GraphUnslopify research workflow

This folder belongs to the generated workflow; inputs and existing editor settings are unchanged.
Use the current source installation after0.8.0 in the selected interpreter/kernel.

- Terminal: `python {name}/run.py` from the project root, or `python run.py` here.
- Notebook: open `review.ipynb` in JupyterLab or VS Code, select that environment, Run All.
- VS Code: open `paper.code-workspace`, select Python, then Run Task: Audit all figures.
- Manuscript: `python run.py --latex`, then run `pdflatex -halt-on-error paper.tex` inside `latex/`.
  The Build example manuscript task chains these operations with process arguments.
- Existing manuscript (compiled from the project root): load `graphicx`, then
  `\\input{{{name}/latex/include.tex}}` where figures belong. Match its line width to
  the recorded figure target width; the include refuses to shrink a validated figure.

`workflow.report.json` retains acceptance and the full audit, including failures.
Each audit keeps a new run under `audit/`. A failed or non-LaTeX workflow run writes
an error guard into `latex/figures.tex`; accepted LaTeX preparation replaces it.
Always run preparation before compiling; edits made outside the workflow are not monitored.
Preparation is not compilation or tagged-PDF certification. Unicode may require your
manuscript's Unicode-capable TeX engine/fonts. Keep generated config, driver and folder together.
This command never merges with an existing workflow folder or writes global kernel/editor settings.
""",
        encoding="utf8",
    )
    return {
        "status": "created",
        "config": str(destination / "workflow.json"),
        "notebook": str(destination / "review.ipynb"),
        "vscode": str(destination / "paper.code-workspace"),
        "figures": len(manifest["figures"]),
    }


def _artifact(item: dict, root: Path) -> bytes:
    name = item["path"]
    path = Path(name)
    if path.is_absolute() or "\\" in name or ".." in path.parts:
        raise WorkflowError("saved output must be contained in its audit root")
    source = (root / path).resolve()
    if not source.is_relative_to(root.resolve()):
        raise WorkflowError("saved output escapes its audit root")
    data = source.read_bytes()
    if len(data) != item["bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
        raise WorkflowError("saved output changed since audit; rerun the workflow")
    return data


def _latex_text(value) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "{": r"\{",
        "}": r"\}",
        "$": r"\$",
        "&": r"\&",
        "#": r"\#",
        "%": r"\%",
        "_": r"\_",
        "^": r"\textasciicircum{}",
        "~": r"\textasciitilde{}",
        "\n": " ",
        "\r": " ",
        "\t": " ",
    }
    return "".join(replacements.get(char, char) for char in str(value))


def _prepare_latex(folder: Path, report: dict) -> dict:
    identifier = Path(report["run_directory"]).name
    target = _owned(folder, "latex/runs/" + identifier)
    target.mkdir(parents=True, exist_ok=False)
    lines = [
        r"% Generated from accepted audit evidence. Do not edit.",
        r"\providecommand{\GraphUnslopifyFigureRoot}{.}",
        r"\providecommand{\Description}[1]{}",
    ]
    artifacts = []
    for index, figure in enumerate(report["figures"], start=1):
        runtime = figure["report"]
        width = (runtime.get("environment") or {}).get("rendering", {}).get("target_width_in")
        if type(width) not in (int, float) or not math.isfinite(width) or not 0 < width <= 20:
            raise WorkflowError(
                "LaTeX needs a recorded manuscript target width; regenerate this figure with current source"
            )
        item = next(
            (x for fmt in ["pdf", "png"] for x in figure["outputs"] if x["format"] == fmt), None
        )
        if item is None:
            raise WorkflowError(
                "LaTeX needs a verified PDF or PNG export; enable one in the figure spec"
            )
        name = f"figure-{index:03d}." + item["format"]
        data = _artifact(item, folder / "audit")
        (target / name).write_bytes(data)
        size = f"{width:.8f}".rstrip("0").rstrip(".")
        caption = runtime["spec"].get("caption") or figure["id"]
        environment = (
            "figure*"
            if runtime["spec"].get("output", {}).get("size") == "double_column"
            else "figure"
        )
        lines.extend(
            [
                f"\\begin{{{environment}}}[htbp]",
                r"\centering",
                f"\\ifdim {size}in>\\linewidth\\PackageError{{GraphUnslopify}}{{Figure {index} needs {size}in line width}}{{Use the intended manuscript column or regenerate and recheck for a narrower target.}}\\fi",
                f"\\includegraphics[width={size}in]{{\\GraphUnslopifyFigureRoot/runs/{identifier}/{name}}}",
                f"\\caption{{{_latex_text(caption)}}}",
                f"\\Description{{{_latex_text(runtime.get('alt_text', ''))}}}",
                f"\\label{{fig:graphunslopify-{figure['id']}}}",
                f"\\end{{{environment}}}",
            ]
        )
        artifacts.append(
            {
                "id": figure["id"],
                "path": str((target / name).relative_to(folder)),
                "sha256": hashlib.sha256(data).hexdigest(),
                "target_width_in": width,
            }
        )
    _owned(folder, "latex/figures.tex").write_text("\n".join(lines) + "\n", encoding="utf8")
    return {
        "status": "prepared",
        "compiled": False,
        "include": str(folder / "latex/include.tex"),
        "artifacts": artifacts,
    }


def run_workflow(
    path: str | Path,
    *,
    latex: bool = False,
    baseline: str | Path | None = None,
    baseline_root: str | Path | None = None,
    fail_on_warning: bool = False,
    fail_on_change: bool = False,
    timeout: float = 120,
) -> dict:
    source = _config_source(path)
    folder = source.parent
    owner = _owner(folder)
    # Invalidate any previous accepted include before inputs/programs are touched.
    latex_root = _owned(folder, "latex")
    latex_root.mkdir(exist_ok=True)
    _owned(folder, "latex/figures.tex").write_text(_GUARD, encoding="utf8")
    result = {
        "schema_version": 1,
        "workflow_id": owner["workflow_id"],
        "directory": str(folder),
        "status": "failed",
        "exit_code": 2,
        "audit_status": "not_run",
        "audit": None,
        "errors": [],
        "latex": {"status": "rejected" if latex else "not_requested", "compiled": False},
    }
    try:
        source, config = _config(source)
        audit_root = _owned(folder, "audit")
        report = audit(
            source.parent / config["manifest"],
            output=audit_root,
            baseline=baseline,
            baseline_root=baseline_root,
            fail_on_warning=fail_on_warning,
            fail_on_change=fail_on_change,
            timeout=timeout,
        )
        result.update(
            audit=report,
            audit_status=report["status"],
            exit_code=report["exit_code"],
            status=report["status"],
        )
        if report["exit_code"]:
            result["status"] = "incomplete" if report["status"] == "incomplete" else "failed"
        elif latex:
            result["latex"] = _prepare_latex(folder, report)
    except (OSError, ValueError, KeyError, TypeError) as problem:
        result.update(status="failed", exit_code=2)
        result["errors"].append(f"{type(problem).__name__}: {problem}")
    _owned(folder, "workflow.report.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf8"
    )
    return result


def notebook_html(result: dict) -> str:
    """Use verified PNG data and escaped text; no notebook extension is needed."""

    def text(value):
        return html.escape(str(value), quote=True)

    content = [
        f"<h2>Figure workflow: {text(result['status'])}</h2><p>Acceptance exit: {result['exit_code']}. Source audit: {text(result['audit_status'])}.</p>"
    ]
    content.extend(f"<p>{text(error)}</p>" for error in result["errors"])
    report = result.get("audit")
    if report:
        content.append(
            "<table><tr><th>Figure</th><th>Source checks</th><th>Errors / warnings</th></tr>"
        )
        for figure in report["figures"]:
            content.append(
                f"<tr><td>{text(figure['id'])}</td><td>{text(figure['status'])}</td><td>{text('; '.join(figure['errors'] + figure['warnings']))}</td></tr>"
            )
        content.append("</table>")
        for figure in report["figures"]:
            image = next((x for x in figure["outputs"] if x["format"] == "png"), None)
            if image:
                data = _artifact(image, Path(result["directory"]) / "audit")
                uri = base64.b64encode(data).decode()
                content.append(
                    f'<h3>{text(figure["id"])}</h3><img style="max-width:100%;height:auto" src="data:image/png;base64,{uri}" alt="{text((figure.get("report") or {}).get("alt_text", figure["id"]))}">'
                )
    content.append(
        "<p>Review the saved audit report for claims, findings and per-format evidence. A rendered picture is not scientific acceptance.</p>"
    )
    return "\n".join(content)
