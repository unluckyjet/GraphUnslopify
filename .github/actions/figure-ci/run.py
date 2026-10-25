"""Install or run Figure CI. Inputs cross the boundary as data, never shell code."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def _flag(name: str) -> bool:
    value = os.environ.get(name, "false").lower()
    if value not in {"true", "false"}:
        raise ValueError(f"{name} must be true or false")
    return value == "true"


def install() -> int:
    extras = os.environ.get("FIGURE_CI_EXTRAS", "interactive,parquet,statistics")
    names = [name.strip() for name in extras.split(",") if name.strip()]
    if set(names) - {"interactive", "parquet", "statistics"}:
        raise ValueError("extras must be interactive, parquet and/or statistics")
    source = str(Path(__file__).resolve().parents[3] / "python")
    if names:
        source += f"[{','.join(names)}]"
    return subprocess.run(
        [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", source],
        check=False,
    ).returncode


def run() -> int:
    stage = Path(
        tempfile.mkdtemp(prefix="figure-ci-", dir=os.environ.get("RUNNER_TEMP"))
    ).resolve()
    workspace = Path(os.environ.get("GITHUB_WORKSPACE", ".")).resolve()
    output = (
        workspace / os.environ.get("FIGURE_CI_OUTPUT", ".graphunslopify-audit")
    ).resolve()
    result = None
    try:
        from graphunslopify.audit import audit

        manifest = workspace / os.environ.get(
            "FIGURE_CI_MANIFEST", "graphunslopify.json"
        )
        baseline_value = os.environ.get("FIGURE_CI_BASELINE", "")
        result = audit(
            manifest,
            output=output,
            baseline=workspace / baseline_value if baseline_value else None,
            fail_on_warning=_flag("FIGURE_CI_FAIL_ON_WARNING"),
            fail_on_change=_flag("FIGURE_CI_FAIL_ON_CHANGE"),
            timeout=float(os.environ.get("FIGURE_CI_TIMEOUT", "120")),
        )
        # Stage only this run's owned evidence, never the whole caller workspace.
        source = (output / result["run_directory"]).resolve()
        if not source.is_relative_to(output / "runs"):
            raise ValueError("audit run directory is outside its evidence root")
        shutil.copytree(source, stage / result["run_directory"])
        (stage / "audit.report.json").write_text(
            json.dumps(result, indent=2), encoding="utf8"
        )
        shutil.copyfile(output / "audit.summary.md", stage / "audit.summary.md")
        exit_code = int(result["exit_code"])
        command = {"status": result["status"], "exit_code": exit_code}
    except Exception as problem:  # noqa: BLE001 -- publish actionable evidence even for setup/input errors
        exit_code = 2
        command = {
            "status": "failed",
            "exit_code": 2,
            "error": f"{type(problem).__name__}: {problem}",
        }
        (stage / "audit.summary.md").write_text(
            "# Figure audit\n\nCommand failed; see command.report.json.\n",
            encoding="utf8",
        )
    (stage / "command.report.json").write_text(
        json.dumps(command, indent=2), encoding="utf8"
    )
    if summary_file := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(summary_file).open("a", encoding="utf8") as handle:
            handle.write((stage / "audit.summary.md").read_text(encoding="utf8"))
    values = {
        "artifact-path": str(stage),
        "report-file": str(stage / "audit.report.json")
        if (stage / "audit.report.json").is_file()
        else "",
        "status": command["status"],
        "exit-code": str(exit_code),
        "changed": str(
            bool(
                result and result.get("comparison") and result["comparison"]["changed"]
            )
        ).lower(),
    }
    if output_file := os.environ.get("GITHUB_OUTPUT"):
        with Path(output_file).open("a", encoding="utf8") as handle:
            handle.writelines(f"{key}={value}\n" for key, value in values.items())
    print(json.dumps({**command, **values}))
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true")
    args = parser.parse_args()
    return install() if args.install else run()


if __name__ == "__main__":
    raise SystemExit(main())
