"""Actual environment replays for the frozen four figures, before the formal seal."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import runpy
import subprocess
import sys
import traceback
from pathlib import Path
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUNNER = runpy.run_path(str(HERE / "session_runner.py"))
PROTOCOL = json.loads((HERE / "protocol.json").read_text(encoding="utf8"))
ENVIRONMENT = runpy.run_path(str(HERE / "environment.py"))


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def schedule(profile, *, native=False):
    profiles = PROTOCOL["reproduction"][
        "native_ci_profiles" if native else "local_profiles"
    ]
    if profile not in profiles:
        raise ValueError("Unknown registered local environment")
    return [
        {
            "profile": profile,
            "figure": figure,
            "repeat": repeat,
            "arm": arm,
            **({"track": "native_ci"} if native else {}),
        }
        for repeat in range(PROTOCOL["reproduction"]["repeats"])
        for index, figure in enumerate(PROTOCOL["reproduction"]["figures"])
        for arm in (
            ["matplotlib", "graphunslopify"]
            if (index + repeat) % 2 == 0
            else ["graphunslopify", "matplotlib"]
        )
    ]


def prepare_standalone(case, root, spec, data, context=None):
    """Actual emitted Graph archive or independent baseline plus shared inspector."""
    sys.path.insert(0, str(ROOT / "python"))
    from graphunslopify.runtime_bundle import create_bundle
    from graphunslopify.transport import local_request

    code = root / "code"
    code.mkdir()
    for source, name in [
        (HERE / "standalone_worker.py", "standalone_worker.py"),
        (HERE / "execution_context.py", "execution_context.py"),
        (HERE / "matplotlib_producer.py", "matplotlib_producer.py"),
        (HERE / "measurement.py", "measurement.py"),
        (ROOT / "benchmarks/papers/reference.py", "reference.py"),
        (ROOT / "benchmarks/certified/measurement.py", "certified_measurement.py"),
        (ROOT / "benchmarks/papers/NOTICE.md", "NOTICE.md"),
        (ROOT / "LICENSE", "LICENSE"),
    ]:
        (code / name).write_bytes(source.read_bytes())
    (root / "data.csv").write_bytes(data)
    canonical = copy.deepcopy(spec)
    canonical["data"]["path"] = "data.csv"
    package = RUNNER["expected_package"]()
    if case["arm"] == "graphunslopify":
        translated = local_request("convert", canonical)
        RUNNER["write"](root / "actual-compiler-response.json", translated)
        if not translated["ok"] or translated["status"] != "translated":
            raise RuntimeError(
                "Actual compiler did not generate the requested standalone figure"
            )
        program = translated["code"].encode("utf8")
        raw = create_bundle(
            {"figure.py": program}, script="figure.py", inputs={"data.csv": data}
        )
        archive = root / "actual-figure-bundle.zip"
        archive.write_bytes(raw)
        target = root / "bundle"
        with ZipFile(archive) as zipped:
            if any(
                Path(n).is_absolute() or ".." in Path(n).parts
                for n in zipped.namelist()
            ):
                raise ValueError("Unsafe actual bundle path")
            zipped.extractall(target)
        if (target / "figure.py").read_bytes() != program:
            raise ValueError("Actual original program changed while archiving")
    else:
        target = root / "inspection-runtime/graphunslopify"
        for name, expected in package.items():
            source = ROOT / "python/graphunslopify" / name
            raw = source.read_bytes()
            if sha(raw) != expected:
                raise ValueError("Shared inspection source changed")
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    RUNNER["write"](
        root / "request.json",
        {
            "arm": case["arm"],
            "execution_context": RUNNER["EXECUTION"]["receipt"](
                context or RUNNER["EXECUTION"]["preparation"]()
            ),
            "spec": canonical,
            "package_sha256": package,
            "scope": "Actual standalone sources; no installed SDK, no formal timing",
        },
    )
    files = {
        str(p.relative_to(root)): sha(p.read_bytes())
        for p in root.rglob("*")
        if p.is_file()
    }
    RUNNER["write"](root / "owned-manifest.json", files)
    return sha((root / "owned-manifest.json").read_bytes())


def standalone(case, root, spec, data, python, context=None):
    root.mkdir()
    manifest_sha = prepare_standalone(case, root, spec, data, context=context)
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env.update(
        MPLBACKEND="Agg",
        MPLCONFIGDIR=str(root / "fresh-font-cache"),
        PYTHONIOENCODING="utf-8",
        GRAPHUNSLOPIFY_NODE="/deliberately/not/a/node/executable",
    )
    command = [
        str(python),
        str(root / "code/standalone_worker.py"),
        "--root",
        str(root),
        "--manifest-sha256",
        manifest_sha,
        *RUNNER["EXECUTION"]["arguments"](
            context or RUNNER["EXECUTION"]["preparation"]()
        ),
    ]
    RUNNER["write"](
        root / "actual-command.json",
        {
            "command": command,
            "scope": "Environment reproduction; generation/setup excluded, no latency inference",
        },
    )
    with (
        (root / "worker-stdout.log").open("x") as stdout,
        (root / "worker-stderr.log").open("x") as stderr,
    ):
        completed = subprocess.run(
            command,
            cwd=root,
            env=env,
            stdout=stdout,
            stderr=stderr,
            timeout=240,
            check=False,
        )
    execution = json.loads((root / "execution.json").read_text(encoding="utf8"))
    execution["actual_process_exit_code"] = completed.returncode
    if execution["outcome"] != "completed":
        raise RuntimeError(
            "Actual standalone execution failed: " + json.dumps(execution.get("error"))
        )
    if completed.returncode != execution["native_exit_code"]:
        raise ValueError("Actual process status and native status disagree")
    if not execution["absence_probe"]["python"].startswith("3.12."):
        raise ValueError("Registered standalone profile requires Python3.12")
    return execution


def run_case(
    case,
    output,
    *,
    python=sys.executable,
    installed=False,
    expected_ci=None,
    execution_context=None,
):
    track = "native_ci" if case.get("track") == "native_ci" else "local"
    context = RUNNER["EXECUTION"]["load"](
        execution_context, repo=ROOT, track=track, arm=case["arm"]
    )
    expected_case = {k: case[k] for k in ("profile", "figure", "repeat")}
    if context.get("case", expected_case) != expected_case:
        raise ValueError("Reproduction case differs from execution context")
    output = Path(output).resolve()
    if output.is_relative_to(ROOT) and not output.is_relative_to(HERE / "results"):
        raise ValueError("Keep owned replays outside source or under workspace/results")
    output.mkdir(parents=True, exist_ok=False)
    row = {
        **case,
        "formal_comparison_performed": context["formal_comparison_performed"],
        "execution_context": RUNNER["EXECUTION"]["receipt"](context),
        "outcome": "not_run",
        "session_error": None,
        "closure_error": None,
    }
    live = None
    try:
        spec = json.loads(
            (HERE / "figures" / (case["figure"] + ".json")).read_text(encoding="utf8")
        )
        data = (HERE / "figures" / spec["data"]["path"]).read_bytes()
        (output / "owned-input.csv").write_bytes(data)
        spec["data"]["path"] = "owned-input.csv"
        if case["profile"] == "standalone-bundle-no-installed-graphunslopify3.12":
            if installed:
                raise ValueError("Standalone profile cannot claim an installed SDK")
            execution = standalone(
                case, output / "standalone", spec, data, python, context=context
            )
            folder = Path(execution["folder"])
            result = json.loads(
                Path(execution["report_file"]).read_text(encoding="utf8")
            )
            evaluation = runpy.run_path(str(HERE / "evaluation.py"))["evaluate"](
                result,
                folder,
                spec,
                output,
                json.loads((HERE / "ground-truth.json").read_text())[
                    case["figure"] + "/first"
                ],
                execution_context=execution_context,
            )
            row.update(execution=execution, evaluation=evaluation)
        else:
            expected_installed = case["profile"] == "fresh-wheel3.12"
            if installed != expected_installed:
                raise ValueError(
                    "Registered profile and installed/source mode disagree"
                )
            live = RUNNER["LiveSession"](
                case["arm"],
                output / "live",
                python=str(python),
                installed=installed,
                execution_context=execution_context,
            )
            row["startup"] = live.ready
            if case.get("track") == "native_ci":
                ENVIRONMENT["validate_worker"](
                    live.ready["execution_environment"],
                    case["profile"],
                    expected_ci or {},
                )
                expected_version = ENVIRONMENT["NATIVE_PROFILES"][case["profile"]][0]
            else:
                expected_version = (
                    "3.10." if case["profile"] == "checkout-minimum3.10" else "3.12."
                )

            if not live.ready["python"].startswith(expected_version):
                raise ValueError(
                    "Actual worker interpreter differs from the registered profile"
                )
            from_source = (
                Path(live.ready["package_root"]).resolve()
                == (ROOT / "python/graphunslopify").resolve()
            )
            if from_source == installed:
                raise ValueError(
                    "Actual source/installed package location differs from the registered profile"
                )
            initial = live.request(
                {
                    "operation": "render",
                    "name": "first",
                    "case": case["figure"] + "/first",
                    "spec": spec,
                    "base": str(output),
                }
            )
            row.update(startup=live.ready, initial=initial)
            if (
                initial["outcome"] != "completed"
                or not initial["current_evidence"]["current"]
            ):
                raise RuntimeError("No original intact environment replay")
            evaluation = initial["evaluation"]
            row["evaluation"] = evaluation
            folder = Path(initial["folder"])
        row["png_graphic_identity"] = runpy.run_path(str(HERE / "measurement.py"))[
            "graphic_identity"
        ]((folder / "figure.png").read_bytes(), "png")
        row["physical_task_errors"] = [
            e
            for e in evaluation["errors"]
            if e.startswith(("actual_width:", "actual_effective_font:"))
        ]
        row["independent_contract_errors"] = [
            e for e in evaluation["errors"] if e not in row["physical_task_errors"]
        ]
        row["outcome"] = "completed"
    except Exception as error:  # noqa: BLE001 - preserve every registered failed replay
        row.update(
            outcome="execution_error",
            session_error={
                "type": type(error).__name__,
                "message": str(error),
                "traceback": traceback.format_exc(),
            },
        )
    finally:
        if live is not None:
            row["last_dispatch"] = copy.deepcopy(getattr(live, "last_dispatch", None))
            try:
                live.close()
                row["closure"] = live.closed
            except Exception as error:  # noqa: BLE001 - retain actual process closure failures
                row["closure_error"] = {
                    "type": type(error).__name__,
                    "message": str(error),
                }
        RUNNER["write"](output / "replay.json", row)
    return row
