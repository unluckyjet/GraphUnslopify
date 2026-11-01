"""Retain two real isolated eight-request sessions; pre-seal integrity, not speed."""

from __future__ import annotations

import argparse
import json
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "benchmarks/workspace"


def check(out, *, python=sys.executable, installed=False):
    out = Path(out).resolve()
    if out.is_relative_to(ROOT) and not out.is_relative_to(HERE / "results"):
        raise ValueError("Keep owned outputs outside source or under workspace/results")
    out.mkdir(parents=True, exist_ok=False)
    runpy.run_path(str(ROOT / "scripts/check-workspace-protocol.py"))["check"](ROOT)
    runner = runpy.run_path(str(HERE / "session_runner.py"))
    before = runner["source_snapshot"]()
    plan = runner["schedule"]()
    protocol = json.loads((HERE / "protocol.json").read_text(encoding="utf8"))
    assert len(plan) == 24
    assert sum(len(protocol["single_pipeline"]["steps"]) for _ in plan) == 192
    sessions = []
    for arm in ("matplotlib", "graphunslopify"):
        result = runner["run_sequence"](
            arm, "penguins-mass", out / arm, python=python, installed=installed
        )
        sessions.append(result)
        print(
            json.dumps(
                {
                    "arm": arm,
                    "completed": sum(
                        r["outcome"] == "completed" for r in result["rows"]
                    ),
                    "session_error": result["session_error"],
                    "closure_error": result["closure_error"],
                }
            ),
            flush=True,
        )
    rows = [row for session in sessions for row in session["rows"]]
    errors = []
    for session in sessions:
        if session["session_error"] or session["closure_error"]:
            errors.append("session_or_closure:" + session["arm"])
    for row in rows:
        if row["outcome"] != "completed" or not row.get("timing_envelope_valid"):
            errors.append("request_or_clock:" + row["arm"] + "/" + row["step"])
        elif any(
            not e.startswith("actual_width:") for e in row["evaluation"]["errors"]
        ):
            errors.append(
                "unexpected_independent_gate:" + row["arm"] + "/" + row["step"]
            )
    if runner["source_snapshot"]() != before:
        errors.append("source_changed")
    proof = {
        "formal_comparison_performed": False,
        "scope": "Two pre-seal operational sessions only; no formal192/54/48/64/64/14 cell is filled and task-width failures remain explicit",
        "passed": not errors,
        "source_sha256": before,
        "planned_formal_sessions": len(plan),
        "actual_requests": len(rows),
        "actual_cold": sum(r["phase"] == "cold" for r in rows),
        "actual_warm": sum(r["phase"] == "warm" for r in rows),
        "sessions": sessions,
        "errors": errors,
    }
    runner["write"](out / "untimed-sessions.json", proof)
    if errors:
        raise ValueError("Pre-seal session integrity failed: " + json.dumps(errors))
    return proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--installed", action="store_true")
    args = parser.parse_args()
    proof = check(args.out, python=args.python, installed=args.installed)
    print(
        json.dumps(
            {
                key: proof[key]
                for key in (
                    "passed",
                    "actual_requests",
                    "actual_cold",
                    "actual_warm",
                    "formal_comparison_performed",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
