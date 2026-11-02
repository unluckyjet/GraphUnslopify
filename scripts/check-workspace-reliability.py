"""Run every registered reliability case as untimed preparation, never a formal study."""

from __future__ import annotations

import argparse
import json
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "benchmarks/workspace"


def check(output, *, python=sys.executable, installed=False):
    if not __debug__:
        raise RuntimeError("Do not optimize independent conformance guards")
    output = Path(output).resolve()
    if output.is_relative_to(ROOT) and not output.is_relative_to(HERE / "results"):
        raise ValueError(
            "Keep owned controls outside source or under workspace/results"
        )
    output.mkdir(parents=True, exist_ok=False)
    runpy.run_path(str(ROOT / "scripts/check-workspace-protocol.py"))["check"](ROOT)
    controls = runpy.run_path(str(HERE / "reliability.py"))
    runner = controls["RUNNER"]
    plan = controls["schedule"]()
    if len(plan) != 48 or len({tuple(sorted(row.items())) for row in plan}) != 48:
        raise ValueError("The fixed complete48-case plan changed")
    proof = {
        "formal_comparison_performed": False,
        "scope": "All48 real pre-seal reliability controls, not formal study cells",
        "source_sha256": runner["source_snapshot"](),
        "package_sha256": runner["expected_package"](),
        "plan": plan,
        "records": [],
        "errors": [],
        "complete": False,
        "passed": False,
    }
    for index, case in enumerate(plan):
        row = controls["run_case"](
            case, output / f"control-{index:03d}", python=python, installed=installed
        )
        proof["records"].append(row)
        if (
            row["outcome"] != "completed"
            or row["session_error"]
            or row["closure_error"]
        ):
            proof["errors"].append(
                {"case": case, "reason": "actual_control_incomplete"}
            )
        elif not row["matched_expected"]:
            proof["errors"].append(
                {"case": case, "reason": "relevant_signal_not_matched"}
            )
        runner["write"](output / "progress.json", proof)
    if runner["source_snapshot"]() != proof["source_sha256"]:
        proof["errors"].append({"reason": "code_or_corpus_changed"})
    if runner["expected_package"]() != proof["package_sha256"]:
        proof["errors"].append({"reason": "sdk_changed"})
    proof["complete"] = len(proof["records"]) == len(plan)
    proof["passed"] = proof["complete"] and not proof["errors"]
    runner["write"](output / "conformance.json", proof)
    return proof


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--installed", action="store_true")
    args = parser.parse_args()
    result = check(args.out, python=args.python, installed=args.installed)
    print(
        json.dumps(
            {
                "passed": result["passed"],
                "controls": len(result["records"]),
                "errors": result["errors"],
            }
        )
    )
    raise SystemExit(0 if result["passed"] else 1)
