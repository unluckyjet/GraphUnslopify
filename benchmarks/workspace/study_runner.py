"""Fixed operational study plans over the actual context-aware producer paths.

Preparation uses the same complete plans without granting formal study credit.
Formal runs additionally require a prospectively qualified implementation seal.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import runpy
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUNNER = runpy.run_path(str(HERE / "session_runner.py"))
EXECUTION = RUNNER["EXECUTION"]
PROTOCOL = json.loads((HERE / "protocol.json").read_text(encoding="utf8"))
TOTALS = {
    "single": 192,
    "paper": 54,
    "reliability": 48,
    "local": 64,
    "native_ci": 64,
    "gui": 14,
}


def utc():
    return datetime.now(timezone.utc).isoformat()


def identity(track, case):
    return hashlib.sha256(EXECUTION["canonical"]({"track": track, **case})).hexdigest()


def plan(track, *, native_profile=None):
    """Return complete sessions/cases in the original registered order."""
    if track == "single":
        cases = RUNNER["schedule"]()
    elif track == "paper":
        cases = runpy.run_path(str(HERE / "paper_sessions.py"))["schedule"]()
    elif track == "reliability":
        cases = runpy.run_path(str(HERE / "reliability.py"))["schedule"]()
    elif track in {"local", "native_ci"}:
        replay = runpy.run_path(str(HERE / "reproduction.py"))
        profiles = PROTOCOL["reproduction"][
            "native_ci_profiles" if track == "native_ci" else "local_profiles"
        ]
        if track == "native_ci":
            if native_profile not in profiles:
                raise ValueError(
                    "Native study dispatch requires one actual registered profile"
                )
            profiles = [native_profile]
        elif native_profile is not None:
            raise ValueError("Local study cannot borrow a native profile")
        cases = [
            case
            for profile in profiles
            for case in replay["schedule"](profile, native=track == "native_ci")
        ]
    elif track == "gui":
        cases = [
            {"arm": "graphunslopify", "profile": p} for p in PROTOCOL["gui"]["profiles"]
        ]
    else:
        raise ValueError("Unknown registered study track")
    answer = []
    for case in cases:
        steps = (
            PROTOCOL["single_pipeline"]["steps"]
            if track == "single"
            else [p["id"] for p in PROTOCOL["paper"]["steps"]]
            if track == "paper"
            else PROTOCOL["gui"]["tasks"]
            if track == "gui"
            else [None]
        )
        answer.append({"id": identity(track, case), "case": case, "cells": list(steps)})
    expected = 16 if track == "native_ci" else TOTALS[track]
    if sum(len(r["cells"]) for r in answer) != expected or len(
        {r["id"] for r in answer}
    ) != len(answer):
        raise ValueError("Registered study denominator or case uniqueness changed")
    return answer


def context_case(track, case):
    return {key: value for key, value in case.items() if key not in {"arm", "track"}}


def configurations(track, supplied):
    if track not in {"local", "gui"}:
        if supplied:
            raise ValueError("This track uses the actual current interpreter")
        return {}
    expected = set(
        PROTOCOL["reproduction"]["local_profiles"]
        if track == "local"
        else PROTOCOL["gui"]["profiles"]
    )
    if not isinstance(supplied, dict) or set(supplied) != expected:
        raise ValueError(
            "Supply every registered environment; do not reduce the study plan"
        )
    answer = copy.deepcopy(supplied)
    for profile, value in answer.items():
        if (
            set(value) != {"python", "installed"}
            or not isinstance(value["python"], str)
            or type(value["installed"]) is not bool
        ):
            raise ValueError(
                "Each profile requires an actual interpreter and explicit install mode"
            )
        if value["installed"] != (profile in {"fresh-wheel", "fresh-wheel3.12"}):
            raise ValueError(
                "Registered source/installed profile and configuration disagree"
            )
    return answer


def create_context(path, track, case, mode, seal):
    document = {
        "schema_version": 1,
        "mode": mode,
        "track": track,
        "arm": case["arm"],
        "case": context_case(track, case),
        "created_utc": utc(),
    }
    if mode == "formal":
        document.update(
            seal=seal,
            seal_sha256=hashlib.sha256(EXECUTION["canonical"](seal)).hexdigest(),
        )
    RUNNER["write"](path, document)
    return EXECUTION["load"](path, repo=ROOT, track=track, arm=case["arm"])


def invoke(track, case, folder, context, configs, native):
    path = context["path"]
    if track == "single":
        return RUNNER["run_sequence"](
            case["arm"], case["figure"], folder, execution_context=path
        )
    if track == "paper":
        return runpy.run_path(str(HERE / "paper_sessions.py"))["run_sequence"](
            case["arm"], folder, execution_context=path
        )
    if track == "reliability":
        return runpy.run_path(str(HERE / "reliability.py"))["run_case"](
            case, folder, execution_context=path
        )
    if track in {"local", "native_ci"}:
        settings = (
            configs[case["profile"]]
            if track == "local"
            else {"python": sys.executable, "installed": False}
        )
        return runpy.run_path(str(HERE / "reproduction.py"))["run_case"](
            case,
            folder,
            **settings,
            expected_ci=native["expected_worker_ci"] if native else None,
            execution_context=path,
        )
    settings = configs[case["profile"]]
    env = {**os.environ, "PYTHON": settings["python"]}
    command = [
        "node",
        "--experimental-strip-types",
        str(ROOT / "scripts/workspace-gui-check.ts"),
        "--out",
        str(folder),
        "--execution-context",
        path,
    ]
    if settings["installed"]:
        command.append("--installed")
    with (
        folder.with_suffix(".stdout.log").open("x", encoding="utf8") as stdout,
        folder.with_suffix(".stderr.log").open("x", encoding="utf8") as stderr,
    ):
        completed = subprocess.run(
            command, cwd=ROOT, env=env, stdout=stdout, stderr=stderr, check=False
        )
    proof = folder / "conformance.json"
    if not proof.is_file():
        raise RuntimeError(
            "Actual browser did not produce independent conformance evidence"
        )
    result = json.loads(proof.read_text(encoding="utf8"))
    result["actual_actor_exit_code"] = completed.returncode
    return result


def actual_cells(track, result):
    return (
        result["rows"]
        if track in {"single", "paper"}
        else result["tasks"]
        if track == "gui"
        else [result]
    )


def integrity_errors(track, result, execution, expected_cells):
    errors = []
    if result.get("execution_context") != execution:
        errors.append("actual_execution_context_differs")
    if result.get("session_error") or result.get("closure_error"):
        errors.append("actual_session_or_closure_error")
    rows = actual_cells(track, result)
    if len(rows) != len(expected_cells):
        errors.append("actual_cell_count_differs")
        return sorted(set(errors))
    for index, row in enumerate(rows):
        if row.get("execution_context") != execution:
            errors.append("actual_cell_execution_differs")
        if track in {"single", "paper"}:
            if (
                row.get("step") != expected_cells[index]
                or row.get("outcome") != "completed"
                or not row.get("timing_envelope_valid")
            ):
                errors.append("actual_request_identity_or_envelope_incomplete")
        elif track == "gui":
            if (
                row.get("task") != expected_cells[index]
                or row.get("controls_outcome") != "completed"
            ):
                errors.append("actual_gui_controls_incomplete")
        elif row.get("outcome") != "completed":
            errors.append("actual_case_incomplete")
    if track == "gui" and (
        not result.get("passed") or result.get("actual_actor_exit_code") != 0
    ):
        errors.append("actual_gui_evidence_guard_failed")
    return sorted(set(errors))


def run(
    track,
    output,
    *,
    mode="preseal",
    seal=None,
    seal_path=None,
    profiles=None,
    native_profile=None,
    expected_revision=None,
):
    """Execute every planned case once; preserve unavailable cells and interruptions."""
    if not __debug__:
        raise RuntimeError("Do not optimize registered study guards")
    if mode not in {"preseal", "formal"} or (
        mode == "preseal" and (seal is not None or seal_path is not None)
    ):
        raise ValueError("Use explicit preparation or a qualified formal seal")
    if seal is not None and seal_path is not None:
        raise ValueError("Choose one unambiguous implementation seal source")
    planned = plan(track, native_profile=native_profile)
    configs = configurations(track, profiles)
    output = Path(output).resolve()
    if output.is_relative_to(ROOT) and not output.is_relative_to(HERE / "results"):
        raise ValueError("Keep study outputs outside source or under workspace/results")
    output.mkdir(parents=True, exist_ok=False)
    contexts = output / "contexts"
    contexts.mkdir()
    proof = {
        "schema_version": 1,
        "mode": mode,
        "track": track,
        "started_utc": utc(),
        "finished_utc": None,
        "output_root": str(output),
        "formal_comparison_performed": False,
        "source_sha256": RUNNER["source_snapshot"](),
        "package_sha256": RUNNER["expected_package"](),
        "profiles": configs,
        "plan": planned,
        "planned_cells": sum(len(r["cells"]) for r in planned),
        "registered_track_total": TOTALS[track],
        "records": [
            {
                **row,
                "attempted": False,
                "outcome": "not_run",
                "unavailable_cells": list(row["cells"]),
            }
            for row in planned
        ],
        "errors": [],
        "interrupted": False,
        "complete": False,
    }
    RUNNER["write"](output / "progress.json", proof)
    native = None
    try:
        if mode == "formal":
            if seal_path is not None:
                raw_seal = Path(seal_path).read_bytes()
                proof["requested_seal_sha256"] = hashlib.sha256(raw_seal).hexdigest()
                seal = json.loads(raw_seal)
            EXECUTION["validate_seal"](seal or {}, ROOT)
        if track == "native_ci":
            native = runpy.run_path(str(HERE / "environment.py"))["checkout_context"](
                ROOT, native_profile, expected_revision
            )
            proof["native_context"] = native
        # Every immutable context is prepared before the first actual case clock.
        loaded = [
            create_context(
                contexts / (row["id"] + ".json"), track, row["case"], mode, seal
            )
            for row in planned
        ]
        for index, row in enumerate(planned):
            record = proof["records"][index]
            if mode == "formal":
                proof["formal_comparison_performed"] = True
            record.update(
                attempted=True, context_sha256=loaded[index]["context_sha256"]
            )
            try:
                result = invoke(
                    track,
                    row["case"],
                    output / ("case-" + row["id"]),
                    loaded[index],
                    configs,
                    native,
                )
                record["result"] = result
                record["errors"] = integrity_errors(
                    track, result, EXECUTION["receipt"](loaded[index]), row["cells"]
                )
                record["outcome"] = (
                    "completed" if not record["errors"] else "evidence_error"
                )
                if record["errors"]:
                    proof["errors"].append(
                        {"case": row["id"], "errors": record["errors"]}
                    )
                record.pop("unavailable_cells", None)
            except Exception as error:  # noqa: BLE001 - every planned cell remains in the result
                record.update(
                    outcome="execution_error",
                    error={
                        "type": type(error).__name__,
                        "message": str(error),
                        "traceback": traceback.format_exc(),
                    },
                )
                proof["errors"].append(
                    {"case": row["id"], "reason": "actual_execution_error"}
                )
            RUNNER["write"](output / "progress.json", proof)
            print(
                json.dumps(
                    {"track": track, "case": row["id"], "outcome": record["outcome"]}
                ),
                flush=True,
            )
    except KeyboardInterrupt:
        proof["interrupted"] = True
        proof["errors"].append({"reason": "actual_host_interruption_no_replacement"})
    except Exception as error:  # noqa: BLE001 - preserve all unstarted cells after actual preflight failure
        proof["errors"].append(
            {
                "reason": "actual_preflight_failure",
                "type": type(error).__name__,
                "message": str(error),
            }
        )
    finally:
        if (
            RUNNER["source_snapshot"]() != proof["source_sha256"]
            or RUNNER["expected_package"]() != proof["package_sha256"]
        ):
            proof["errors"].append({"reason": "implementation_changed_during_study"})
        proof["finished_utc"] = utc()
        proof["retained_cells"] = sum(len(r["cells"]) for r in proof["records"])
        proof["complete"] = not proof["errors"] and all(
            r["outcome"] == "completed" for r in proof["records"]
        )
        proof["same_environment_png_comparisons"] = []
        if track in {"local", "native_ci"}:
            groups = {}
            for record in proof["records"]:
                case = record["case"]
                groups.setdefault(
                    (case["profile"], case["figure"], case["arm"]), []
                ).append(record.get("result", {}).get("png_graphic_identity"))
            proof["same_environment_png_comparisons"] = [
                {
                    "profile": key[0],
                    "figure": key[1],
                    "arm": key[2],
                    "identities": values,
                    "both_available": len(values) == 2 and None not in values,
                    "reproduced": len(values) == 2
                    and None not in values
                    and len(set(values)) == 1,
                }
                for key, values in groups.items()
            ]
        proof["files_sha256"] = {
            p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(output.rglob("*"))
            if p.is_file()
            and p.relative_to(output).as_posix() not in {"study.json", "progress.json"}
        }
        RUNNER["write"](output / "study.json", proof)
    return proof
