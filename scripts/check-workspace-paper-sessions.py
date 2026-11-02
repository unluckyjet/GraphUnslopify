"""Pre-seal actual process/startup/acceptance checks for both full paper sequences."""

from __future__ import annotations

import argparse
import hashlib
import json
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "benchmarks/workspace"


def check(out, *, python=sys.executable, installed=False):
    runner = runpy.run_path(str(HERE / "session_runner.py"))
    paper = runpy.run_path(str(HERE / "paper_sessions.py"))
    out = Path(out).resolve()
    if out.is_relative_to(ROOT) and not out.is_relative_to(HERE / "results"):
        raise ValueError("Keep evidence outside source or under workspace/results")
    out.mkdir(parents=True, exist_ok=False)
    runpy.run_path(str(ROOT / "scripts/check-workspace-protocol.py"))["check"](ROOT)
    before = runner["source_snapshot"]()
    protocol = json.loads((HERE / "protocol.json").read_text(encoding="utf8"))
    errors = []
    proof = {
        "formal_comparison_performed": False,
        "scope": "Two pre-seal isolated nine-request paper sessions; no formal54 measurement",
        "source_sha256": before,
        "package_sha256": runner["expected_package"](),
        "protocol_sha256": hashlib.sha256(
            (HERE / "protocol.json").read_bytes()
        ).hexdigest(),
        "formal_schedule": paper["schedule"](),
        "sessions": [],
        "errors": errors,
    }
    for arm in ("matplotlib", "graphunslopify"):
        session = paper["run_sequence"](
            arm, out / arm, python=python, installed=installed
        )
        proof["sessions"].append(session)
        if session["session_error"] or session["closure_error"]:
            errors.append(arm + ":actual_session_failure")
        if session.get("startup", {}).get("child_events_enabled"):
            errors.append(arm + ":fault_test_notification_enabled")
        if any(
            c["forced_cleanup"] or c["returncode"] is None
            for c in session.get("closure", {}).get("owned_children", [])
        ):
            errors.append(arm + ":unclean_child_lifecycle")
        if (out / arm / "live/session-group-cleanup.json").exists():
            errors.append(arm + ":forced_group_cleanup")
        for expected, row in zip(
            protocol["paper"]["steps"], session["rows"], strict=True
        ):
            label = arm + "/" + row["step"]
            if row["outcome"] != "completed":
                errors.append(label + ":not_completed")
                continue
            if (
                not row["timing_envelope_valid"]
                or row["tool_exit_code"] != expected["exit_code"]
            ):
                errors.append(label + ":clock_or_status")
            if row["pid"] != session["startup"]["pid"]:
                errors.append(label + ":different_worker")
            for evaluation in row["evaluations"].values():
                if any(not e.startswith("actual_width:") for e in evaluation["errors"]):
                    errors.append(label + ":unexpected_independent_gate")
            verified = row["tool_exit_code"] == 0 and all(
                e["task_correct_verified"] for e in row["evaluations"].values()
            )
            if row["task_verified_ns"] != (
                row["parent_received_ns"] if verified else None
            ):
                errors.append(label + ":unobservable_task_acceptance")
            if row["worker_task_verified_ns"] != (
                row["checked_ns"] if verified else None
            ):
                errors.append(label + ":wrong_worker_acceptance")
            counts = row["paper"]["native"]["audit"]["execution_counts"]
            if arm == "graphunslopify" and (counts["executed"], counts["reused"]) != (
                expected["expected_executed"],
                expected["expected_reused"],
            ):
                errors.append(label + ":actual_native_policy")
            if (
                arm == "matplotlib"
                and row["step"] in {"recover", "add-alias", "remove-alias"}
                and counts["acceptance_reused"]
            ):
                errors.append(label + ":old_baseline_acceptance")
            if row["step"] == "unchanged" and row["first_png_available_ns"] is not None:
                errors.append(label + ":old_save_as_current_image")
            print(
                json.dumps(
                    {
                        "arm": arm,
                        "step": row["step"],
                        "actual_counts": counts,
                        "task_verified": verified,
                    }
                ),
                flush=True,
            )
        runner["write"](out / "conformance-progress.json", proof)
    if before != runner["source_snapshot"]():
        errors.append("actual_comparison_source_changed")
    proof["passed"] = not errors
    proof["paper_requests"] = sum(len(s["rows"]) for s in proof["sessions"])
    proof["figure_evaluations"] = sum(
        len(r.get("evaluations", {})) for s in proof["sessions"] for r in s["rows"]
    )
    runner["write"](out / "conformance.json", proof)
    return proof


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--python", default=sys.executable)
    p.add_argument("--installed", action="store_true")
    args = p.parse_args()
    result = check(args.out, python=args.python, installed=args.installed)
    print(
        json.dumps(
            {
                k: result[k]
                for k in ("passed", "paper_requests", "figure_evaluations", "errors")
            }
        )
    )
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
