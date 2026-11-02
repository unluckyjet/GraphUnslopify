"""Run registered environment replays as untimed preparation, retaining every failure."""

from __future__ import annotations

import argparse
import json
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "benchmarks/workspace"


def check(output, configurations, *, native_context=None):
    if not __debug__:
        raise RuntimeError("Do not optimize independent replay guards")
    output = Path(output).resolve()
    if output.is_relative_to(ROOT) and not output.is_relative_to(HERE / "results"):
        raise ValueError(
            "Keep replay evidence outside source or under workspace/results"
        )
    output.mkdir(parents=True, exist_ok=False)
    runpy.run_path(str(ROOT / "scripts/check-workspace-protocol.py"))["check"](ROOT)
    replay = runpy.run_path(str(HERE / "reproduction.py"))
    runner = replay["RUNNER"]
    native = native_context is not None
    profiles = replay["PROTOCOL"]["reproduction"][
        "native_ci_profiles" if native else "local_profiles"
    ]
    if not configurations or any(p not in profiles for p in configurations):
        raise ValueError("Unknown or missing registered environment")
    plan = [
        row
        for profile in profiles
        if profile in configurations
        for row in replay["schedule"](profile, native=native)
    ]
    expected = 16 * len(configurations)
    if (
        len(plan) != expected
        or len({tuple(sorted(r.items())) for r in plan}) != expected
    ):
        raise ValueError("Registered environment plan changed")
    proof = {
        "formal_comparison_performed": False,
        "track": "native_ci" if native else "local",
        "native_context": native_context,
        "scope": "Actual complete selected profile replays, not formal64 study cells",
        "selected_profiles": configurations,
        "full_registered_local_plan": not native
        and len(configurations) == len(profiles),
        "source_sha256": runner["source_snapshot"](),
        "package_sha256": runner["expected_package"](),
        "plan": plan,
        "records": [],
        "errors": [],
        "complete": False,
        "passed": False,
    }
    for index, case in enumerate(plan):
        config = configurations[case["profile"]]
        row = replay["run_case"](
            case,
            output / f"replay-{index:03d}",
            python=config["python"],
            installed=config.get("installed", False),
            expected_ci=native_context["expected_worker_ci"] if native else None,
        )
        proof["records"].append(row)
        if (
            row["outcome"] != "completed"
            or row["session_error"]
            or row["closure_error"]
        ):
            proof["errors"].append({"case": case, "reason": "actual_replay_incomplete"})
        elif row["independent_contract_errors"]:
            proof["errors"].append(
                {"case": case, "reason": "independent_contract_failure"}
            )
        runner["write"](output / "progress.json", proof)
        print(
            json.dumps(
                {
                    "case": case,
                    "outcome": row["outcome"],
                    "task_verified": row.get("evaluation", {}).get(
                        "task_correct_verified"
                    ),
                    "error": row["session_error"],
                }
            ),
            flush=True,
        )
    proof["same_environment_png_comparisons"] = []
    for profile in profiles:
        if profile not in configurations:
            continue
        for figure in replay["PROTOCOL"]["reproduction"]["figures"]:
            for arm in ("matplotlib", "graphunslopify"):
                rows = [
                    r
                    for r in proof["records"]
                    if (r["profile"], r["figure"], r["arm"]) == (profile, figure, arm)
                ]
                identities = [r.get("png_graphic_identity") for r in rows]
                proof["same_environment_png_comparisons"].append(
                    {
                        "profile": profile,
                        "figure": figure,
                        "arm": arm,
                        "identities": identities,
                        "both_available": len(identities) == 2 and all(identities),
                        "reproduced": len(identities) == 2
                        and all(identities)
                        and len(set(identities)) == 1,
                    }
                )
    if runner["source_snapshot"]() != proof["source_sha256"]:
        proof["errors"].append({"reason": "code_or_corpus_changed"})
    if runner["expected_package"]() != proof["package_sha256"]:
        proof["errors"].append({"reason": "sdk_changed"})
    if native:
        try:
            actual_context = replay["ENVIRONMENT"]["checkout_context"](
                ROOT, next(iter(configurations)), native_context["checkout"]
            )
            if actual_context != native_context:
                proof["errors"].append({"reason": "native_environment_changed"})
        except Exception as error:  # noqa: BLE001 - retain an actual end-of-run identity failure
            proof["errors"].append(
                {"reason": "native_checkout_or_context_changed", "error": str(error)}
            )
    proof["complete"] = len(proof["records"]) == len(plan)
    proof["passed"] = proof["complete"] and not proof["errors"]
    runner["write"](output / "conformance.json", proof)
    return proof


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--profile",
        choices=json.loads((HERE / "protocol.json").read_text())["reproduction"][
            "local_profiles"
        ],
    )
    group.add_argument(
        "--profiles-file",
        type=Path,
        help="Mapping all four registered profiles to actual python/installed settings",
    )
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--installed", action="store_true")
    args = parser.parse_args()
    if args.profiles_file:
        configurations = json.loads(args.profiles_file.read_text(encoding="utf8"))
        expected_profiles = json.loads((HERE / "protocol.json").read_text())[
            "reproduction"
        ]["local_profiles"]
        if set(configurations) != set(expected_profiles):
            parser.error("Full reproduction requires all four registered profiles")
    else:
        configurations = {
            args.profile: {"python": args.python, "installed": args.installed}
        }
    result = check(args.out, configurations)
    print(
        json.dumps(
            {
                "passed": result["passed"],
                "replays": len(result["records"]),
                "errors": result["errors"],
            }
        )
    )
    raise SystemExit(0 if result["passed"] else 1)
