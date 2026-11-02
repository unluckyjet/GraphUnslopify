"""Actual CI platform reproduction preparation; formal measurements require the full seal."""

from __future__ import annotations

import argparse
import json
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "benchmarks/workspace"


def check(output, profile, expected_revision):
    if not __debug__:
        raise RuntimeError("Do not optimize native evidence guards")
    environment = runpy.run_path(str(HERE / "environment.py"))
    protocol = json.loads((HERE / "protocol.json").read_text(encoding="utf8"))
    if set(environment["NATIVE_PROFILES"]) != set(
        protocol["reproduction"]["native_ci_profiles"]
    ):
        raise ValueError("Actual platform registry differs from frozen native profiles")
    if profile not in environment["NATIVE_PROFILES"]:
        raise ValueError("Unknown registered native profile")
    try:
        context = environment["checkout_context"](ROOT, profile, expected_revision)
    except (
        Exception
    ) as error:  # Retain every unstarted cell after real preflight failure.
        replay = runpy.run_path(str(HERE / "reproduction.py"))
        runner = replay["RUNNER"]
        output = Path(output).resolve()
        if output.is_relative_to(ROOT) and not output.is_relative_to(HERE / "results"):
            raise ValueError(
                "Keep native evidence outside source or under workspace/results"
            ) from error
        output.mkdir(parents=True, exist_ok=False)
        plan = replay["schedule"](profile, native=True)
        failure = {"type": type(error).__name__, "message": str(error)}
        proof = {
            "formal_comparison_performed": False,
            "track": "native_ci",
            "scope": "Actual preflight refusal; all planned cells retained without worker execution",
            "requested_revision": expected_revision,
            "observed_parent": environment["observed"](),
            "native_context_validated": False,
            "source_sha256": runner["source_snapshot"](),
            "package_sha256": runner["expected_package"](),
            "plan": plan,
            "records": [
                {
                    **case,
                    "formal_comparison_performed": False,
                    "outcome": "not_run",
                    "dispatch_attempted": False,
                    "session_error": failure,
                    "closure_error": None,
                }
                for case in plan
            ],
            "errors": [{"reason": "native_preflight_refused", **failure}],
            "planned_records_retained": True,
            "complete": False,
            "passed": False,
        }
        runner["write"](output / "conformance.json", proof)
        return proof
    controller = runpy.run_path(str(ROOT / "scripts/check-workspace-reproduction.py"))
    return controller["check"](
        output,
        {profile: {"python": sys.executable, "installed": False}},
        native_context=context,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--profile",
        required=True,
        choices=json.loads((HERE / "protocol.json").read_text())["reproduction"][
            "native_ci_profiles"
        ],
    )
    parser.add_argument("--expected-sha", required=True)
    args = parser.parse_args()
    result = check(args.out, args.profile, args.expected_sha)
    print(
        json.dumps(
            {
                "passed": result["passed"],
                "native_replays": len(result["records"]),
                "formal_comparison_performed": False,
                "errors": result["errors"],
            }
        )
    )
    raise SystemExit(0 if result["passed"] else 1)
