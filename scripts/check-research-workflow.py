"""Exercise the installed research workspace with real CLI/editor-process commands."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--work-dir", type=Path)
    args = parser.parse_args()
    where = (
        args.work_dir or Path(tempfile.mkdtemp(prefix="gu-research-workflow-"))
    ).resolve()
    if where.exists() and any(where.iterdir()):
        parser.error("choose a new/empty directory; existing evidence is preserved")
    where.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "GRAPHUNSLOPIFY_API": "local",
        "MPLBACKEND": "Agg",
        "PYTHONIOENCODING": "utf-8",
    }
    exits = []

    def command(*words, expected=0):
        done = subprocess.run(
            [args.python, "-m", "graphunslopify.cli", *map(str, words)],
            cwd=where,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf8",
            timeout=120,
            check=False,
        )
        exits.append(done.returncode)
        if done.returncode != expected:
            raise RuntimeError(
                f"{words}: expected {expected}, got {done.returncode}\n{done.stdout}\n{done.stderr}"
            )
        return json.loads(done.stdout)

    project = where / "paper with spaces"
    command("demo", project, "--json")
    command("audit-init", project)
    initialized = command("workflow-init", project)
    config = Path(initialized["config"])
    folder = config.parent
    original_data = (project / "results.csv").read_bytes()
    original_spec = (project / "figure.json").read_bytes()
    workspace = json.loads((folder / "paper.code-workspace").read_text(encoding="utf8"))
    task = workspace["tasks"]["tasks"][0]
    assert (
        task["type"] == "process"
        and task["command"] == "${command:python.interpreterPath}"
    )
    argv = [
        value.replace("${workspaceFolder:paper}", str(project))
        for value in task["args"]
    ]
    editor = subprocess.run(
        [args.python, *argv],
        cwd=where,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf8",
        timeout=120,
        check=False,
    )
    assert editor.returncode == 0, editor.stdout + editor.stderr
    assert json.loads(editor.stdout)["audit_status"] == "passed"
    prepared = command("workflow-run", config, "--latex")
    assert (
        prepared["exit_code"] == 0
        and prepared["latex"]["status"] == "prepared"
        and not prepared["latex"]["compiled"]
    )
    for item in prepared["latex"]["artifacts"]:
        assert (
            hashlib.sha256((folder / item["path"]).read_bytes()).hexdigest()
            == item["sha256"]
        )
    spec = json.loads(original_spec)
    spec["claims"][0].update(subject="base", reference="ours")
    (project / "figure.json").write_text(json.dumps(spec), encoding="utf8")
    failed = command("workflow-run", config, "--latex", expected=2)
    assert (
        failed["audit_status"] == "failed" and failed["latex"]["status"] == "rejected"
    )
    assert "\\PackageError" in (folder / "latex/figures.tex").read_text(encoding="utf8")
    (project / "figure.json").write_bytes(original_spec)
    recovered = command("workflow-run", config, "--latex")
    assert recovered["exit_code"] == 0 and recovered["latex"]["status"] == "prepared"
    assert "\\begin{figure}" in (folder / "latex/figures.tex").read_text(
        encoding="utf8"
    )
    assert (project / "results.csv").read_bytes() == original_data
    notebook = json.loads((folder / "review.ipynb").read_text(encoding="utf8"))
    assert notebook["nbformat"] == 4 and all(
        not cell.get("outputs") for cell in notebook["cells"]
    )
    print(
        json.dumps(
            {
                "status": "passed",
                "work_dir": str(where),
                "config": str(config),
                "exit_codes": exits,
                "editor_process_exit": editor.returncode,
                "latex": "prepared; compilation separate",
                "inputs_unchanged": True,
                "notebook": "cleared; kernel execution covered separately",
            }
        )
    )


if __name__ == "__main__":
    main()
