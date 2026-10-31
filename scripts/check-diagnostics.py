"""Prove source-installed advice, strict correction and package-free explanations."""

from __future__ import annotations

import argparse
import contextlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    from graphunslopify import Figure, SpecError
    from graphunslopify.diagnostics import catalog

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path)
    args = parser.parse_args()
    where = (
        args.work_dir or Path(tempfile.mkdtemp(prefix="gu-diagnostics-"))
    ).resolve()
    if where.exists() and any(where.iterdir()):
        parser.error("choose a new/empty directory; existing evidence is preserved")
    where.mkdir(parents=True, exist_ok=True)
    data = where / "observations.csv"
    original = b"x,y\n1,-2\n2,3\n3,4\n"
    data.write_bytes(original)
    figure = (
        Figure.line(data)
        .x("x", "X")
        .y("y", "Y")
        .set(y={"field": "y", "label": "Y", "scale": "log"}, legend={"show": False})
        .output(formats=["png"])
    )
    try:
        with contextlib.redirect_stdout(sys.stderr):
            figure.render(cwd=where / "failed")
    except SpecError as problem:
        failed = problem.report
    else:
        raise AssertionError("strict log-domain failure was accepted")
    assert failed["exit_code"] == 2 and failed["status"] == "failed"
    assert all(
        item["consequence"] and item["correction"] for item in failed["findings"]
    )
    assert any(item["code"] == "log_domain_hidden" for item in failed["findings"])
    figure.spec["y"]["scale"] = "linear"
    with contextlib.redirect_stdout(sys.stderr):
        passed = figure.render(cwd=where / "corrected")["report"]
    assert passed["status"] == "passed" and data.read_bytes() == original
    # Deny inspection while retaining the matching shared runtime/advice. Whole-
    # package absence is separately checked by actual standalone archive controls.
    script = where / "corrected/figure.py"
    wrapper = (
        "import builtins,runpy,sys\noriginal=builtins.__import__\n"
        "def guarded(name,globals=None,locals=None,fromlist=(),level=0):\n"
        " if name=='graphunslopify' and 'inspect_figure' in (fromlist or ()):\n"
        "  raise ImportError('checker intentionally absent')\n"
        " return original(name,globals,locals,fromlist,level)\n"
        "builtins.__import__=guarded\n"
        "sys.argv=[sys.argv[1],'--strict','--json']\n"
        "runpy.run_path(sys.argv[0],run_name='__main__')\n"
    )
    without_inspection = subprocess.run(
        [sys.executable, "-c", wrapper, str(script)],
        cwd=script.parent,
        text=True,
        capture_output=True,
        check=False,
        timeout=120,
    )
    assert without_inspection.returncode == 2, without_inspection.stderr
    report = json.loads(without_inspection.stdout)
    finding = next(
        item for item in report["findings"] if item["code"] == "inspection_unavailable"
    )
    assert (
        finding["consequence"]
        and finding["correction"]
        and report["status"] == "incomplete"
    )
    known = subprocess.run(
        [
            sys.executable,
            "-m",
            "graphunslopify.cli",
            "explain",
            "truncated_bar_axis",
            "--json",
        ],
        cwd=where,
        text=True,
        capture_output=True,
        check=True,
        timeout=30,
    )
    assert json.loads(known.stdout)["known"]
    assert len(catalog()["advice"]) >= 132
    print(
        json.dumps(
            {
                "status": "passed",
                "codes": len(catalog()["advice"]),
                "strict_failure_recovery": True,
                "source_data_unchanged": True,
                "advice_without_inspection": True,
                "where": str(where),
            }
        )
    )


if __name__ == "__main__":
    main()
