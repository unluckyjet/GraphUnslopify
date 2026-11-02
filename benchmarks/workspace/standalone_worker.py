"""Execute actual owned standalone sources after proving SDK distribution absence."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import runpy
import sys
import time
import traceback
from pathlib import Path


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write(path, value):
    path.write_text(
        json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf8"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--execution-context", type=Path)
    parser.add_argument("--execution-context-sha256")
    args = parser.parse_args()
    execution_api = runpy.run_path(
        str(Path(__file__).with_name("execution_context.py"))
    )
    context = execution_api["observer"](
        args.execution_context, args.execution_context_sha256
    )
    execution = execution_api["receipt"](context)
    root = args.root.resolve()
    proof = {
        "outcome": "execution_error",
        "formal_comparison_performed": context["formal_comparison_performed"],
        "execution_context": execution,
    }
    started = time.perf_counter_ns()
    native_exit = None
    try:
        if not __debug__:
            raise RuntimeError("Do not optimize standalone guards")
        manifest_raw = (root / "owned-manifest.json").read_bytes()
        if sha(manifest_raw) != args.manifest_sha256:
            raise ValueError("Owned manifest changed")
        manifest = json.loads(manifest_raw)

        def check_owned():
            for name, expected in manifest.items():
                path = (root / name).resolve()
                if not path.is_relative_to(root) or sha(path.read_bytes()) != expected:
                    raise ValueError("Owned standalone source/input changed: " + name)

        check_owned()
        request = json.loads((root / "request.json").read_text(encoding="utf8"))
        if request.get("execution_context") != execution:
            raise ValueError("Standalone worker execution identity differs from parent")
        try:
            installed = importlib.metadata.version("graphunslopify")
        except importlib.metadata.PackageNotFoundError:
            installed = None
        probe = {
            "distribution": installed,
            "import_absent_before_explicit_bundle_path": importlib.util.find_spec(
                "graphunslopify"
            )
            is None,
            "python": sys.version,
            "executable": sys.executable,
            "pid": os.getpid(),
            "observed_distribution_versions": {
                d.metadata["Name"]: d.version
                for d in importlib.metadata.distributions()
            },
            "cwd": str(Path.cwd()),
            "node_override": os.environ.get("GRAPHUNSLOPIFY_NODE"),
        }
        write(root / "absence-probe.json", probe)
        if (
            installed is not None
            or not probe["import_absent_before_explicit_bundle_path"]
        ):
            raise RuntimeError(
                "Standalone replay requires actual SDK distribution/import absence"
            )
        proof["absence_probe"] = probe
        code = root / "code"
        measured = runpy.run_path(str(code / "measurement.py"))
        spec = request["spec"]
        if request["arm"] == "graphunslopify":
            from matplotlib.figure import Figure

            target = root / "bundle"
            program = target / "figure.py"
            original_program = program.read_bytes()
            events = []
            downstream = Figure.savefig

            def save(figure, filename, *positional, **options):
                answer = downstream(figure, filename, *positional, **options)
                available = time.perf_counter_ns()
                if isinstance(filename, (str, Path)):
                    path = Path(filename).resolve()
                    if path.parent == target and path.name in {
                        "figure." + f for f in spec["output"]["formats"]
                    }:
                        events.append(
                            measured["saved_figure"](
                                figure, path, spec["kind"], available_ns=available
                            )
                        )
                        write(root / "original-save-events.json", events)
                return answer

            bundle_manifest = json.loads(
                (target / "_graphunslopify/manifest.json").read_text(encoding="utf8")
            )
            previous_argv = sys.argv
            Figure.savefig = save
            sys.argv = [str(target / bundle_manifest["launcher"]), "--json"]
            try:
                with (
                    (root / "native-stdout.json").open("x", encoding="utf8") as stdout,
                    contextlib.redirect_stdout(stdout),
                ):
                    try:
                        runpy.run_path(sys.argv[0], run_name="__main__")
                        native_exit = 0
                    except SystemExit as exit:
                        native_exit = (
                            exit.code
                            if isinstance(exit.code, int)
                            else 0
                            if exit.code is None
                            else 1
                        )
            finally:
                Figure.savefig = downstream
                sys.argv = previous_argv
                os.chdir(root)
            if program.read_bytes() != original_program:
                raise ValueError("The actual standalone program changed")
            native_raw = (root / "native-stdout.json").read_bytes()
            native = json.loads(native_raw)
            (target / "native-stdout-report.json").write_bytes(native_raw)
            pngs = [e for e in events if e["format"] == "png"]
            if not pngs:
                raise RuntimeError("No actual standalone PNG save observed")
            result = {
                "status": native["status"],
                "exit_code": native_exit,
                "native_exit_code": native_exit,
                "native_report_present": True,
                "exit_code_source": "actual_standalone_main_SystemExit",
                "strict": native["policy"]["strict"],
                "fail_on_warning": native["policy"]["fail_on_warning"],
                "spec": native["spec"],
                "retained_observations": native["data"]["counts"]["finite"],
                "artists": pngs[-1]["artists"],
                "labels": pngs[-1]["labels"],
                "save_observations": events,
                "outputs": {
                    "figure." + f: sha((target / ("figure." + f)).read_bytes())
                    for f in spec["output"]["formats"]
                },
                "data_sha256": sha((target / "data.csv").read_bytes()),
                "producer_sha256": sha(original_program),
                "environment": native["environment"],
                "native_report_file": "native-stdout-report.json",
                "formal_comparison_performed": context["formal_comparison_performed"],
                "execution_context": execution,
            }
            runtime = target / "_graphunslopify/runtime/graphunslopify"
            folder = target
        elif request["arm"] == "matplotlib":
            runtime = root / "inspection-runtime/graphunslopify"
            sys.path.insert(0, str(runtime.parent))
            session = runpy.run_path(str(code / "matplotlib_producer.py"))["Session"](
                root / "producer",
                execution_binding=(
                    args.execution_context,
                    args.execution_context_sha256,
                ),
            )
            with (
                (root / "native-stdout.json").open("x", encoding="utf8") as stdout,
                contextlib.redirect_stdout(stdout),
            ):
                result = session.render(spec, root, "first")
            folder = root / "producer/runs/first"
            native_exit = result["exit_code"]
            proof["current_evidence"] = session.validate("first")
        else:
            raise ValueError("Unknown standalone producer")
        import graphunslopify

        if Path(graphunslopify.__file__).resolve().parent != runtime:
            raise ValueError("Loaded a different runtime than the owned archive")
        actual = {
            p.relative_to(runtime).as_posix(): sha(p.read_bytes())
            for p in runtime.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
        }
        if actual != request["package_sha256"]:
            raise ValueError(
                "Actual bundled package differs from the source being tested"
            )
        check_owned()
        write(root / "workspace-result.json", result)
        proof.update(
            outcome="completed",
            folder=str(folder),
            report_file=str(root / "workspace-result.json"),
            native_exit_code=native_exit,
            loaded_runtime=str(runtime),
            package_sha256=actual,
        )
    except Exception as error:  # noqa: BLE001 - retain the actual failed attempt
        proof["error"] = {
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
        }
    finally:
        proof.update(started_ns=started, completed_ns=time.perf_counter_ns())
        write(root / "execution.json", proof)
    return native_exit if proof["outcome"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
