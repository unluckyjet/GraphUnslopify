"""Measure the unchanged runtime-v1 workload, retaining setup, failures and raw runs."""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import os
import platform
import runpy
import statistics
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from unittest.mock import patch

DRIVER_READY_NS = time.perf_counter_ns()
ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_SHA = "befa743969611f0dabd46a29ca5d603acf7df8dcff5aa1e7b227179f2c495e91"
PROFILE = ROOT / "scripts/profile-runtime-phases.py"
SCIENCE = [
    "matplotlib",
    "pandas",
    "numpy",
    "pillow",
    "pypdf",
    "typing_extensions",
    "jsonschema",
    "scipy",
    "plotly",
    "pyarrow",
    "python-calamine",
]
PROBE = """
import importlib.metadata as m,importlib.util,json,platform,sys
def version(name):
 try:return m.version(name)
 except m.PackageNotFoundError:return None
print(json.dumps({'python':platform.python_version(),'executable':sys.executable,
 'prefix':sys.prefix,'platform':platform.platform(),'machine':platform.machine(),
 'science':{n:version(n) for n in sys.argv[1:]},
 'graphunslopify_version':version('graphunslopify'),
 'graphunslopify_importable':importlib.util.find_spec('graphunslopify') is not None}))
"""
# Same bootstrap for all direct arms. Original source and __main__ guard execute.
# Parent wall includes this disclosed harness; child timestamps separate its setup.
DIRECT = """
import time
entered=time.perf_counter_ns()
import json,runpy,sys
from pathlib import Path
timing,package,program,*native=sys.argv[1:]
if package!='-':sys.path.insert(0,package)
sys.argv=[program,*native]
ready=time.perf_counter_ns()
try:runpy.run_path(program,run_name='__main__')
finally:
 ended=time.perf_counter_ns()
 Path(timing).write_text(json.dumps({'child_entry_ns':entered,'original_start_ns':ready,
  'original_end_ns':ended,'bootstrap_setup_seconds':(ready-entered)/1e9,
  'original_execution_seconds':(ended-ready)/1e9})+'\\n')
"""


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def fingerprint(folder):
    return {
        str(p.relative_to(folder)): sha(p.read_bytes())
        for p in sorted(folder.rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    }


def metrics(raw):
    try:
        lines = len(raw.decode("utf8").splitlines())
    except UnicodeDecodeError:
        lines = None
    return {"bytes": len(raw), "utf8_lines": lines, "sha256": sha(raw)}


def footprint(files):
    members = {name: metrics(raw) for name, raw in files.items()}
    return {
        "files": len(members),
        "bytes": sum(v["bytes"] for v in members.values()),
        "utf8_lines": sum(v["utf8_lines"] or 0 for v in members.values()),
        "binary_files": sum(v["utf8_lines"] is None for v in members.values()),
        "members": members,
    }


def normalized(signature):
    value = copy.deepcopy(signature)
    value.pop("script_sha256")
    value.pop("artifact_files")
    script = value["scientific_report"]["script"]
    script["sha256"] = "validated actual program"
    script.pop("runtime", None)  # actual descriptor checked before this projection
    # Interpreter/package probes record this deliberate source/no-distribution difference.
    value["scientific_report"]["environment"]["installed_optional_versions"][
        "graphunslopify"
    ] = "validated actual package metadata"
    return value


def signature(folder, case, report, code, archive, stderr=None):
    controls = runpy.run_path(str(ROOT / "scripts/check-runtime-foundation.py"))
    namespace = {"DATA_PATH": case["data"], "DATA_HASH": case["data_sha256"][:16]}
    if "runtime" in report.get("script", {}):
        namespace["RUNTIME_BINDING"] = report["script"]["runtime"]
    if stderr is None:
        stderr = (folder / "render.log").read_text()
    result = controls["inspect_artifacts"](
        namespace, folder, archive, report, code, stderr
    )
    assert (
        code == case["expected_exit_code"]
        and report["status"] == case["expected_status"]
    )
    assert sha((folder / case["data"]).read_bytes()) == case["data_sha256"]
    assert report["data"]["sha256_prefix"] == case["data_sha256"][:16]
    assert sorted(
        i["format"] for i in report["outputs"] if i["format"] in {"png", "svg", "pdf"}
    ) == sorted(case["formats"])
    return result


def maps(folder, original):
    result = {}
    image = folder / "figure.png"
    for kind in ("edit", "diagnostic"):
        path = folder / f"figure.{kind}-map.json"
        actual = json.loads(path.read_text())
        expected = json.loads(
            (original / f"original-figure.{kind}-map.json").read_text()
        )
        assert actual["schema_version"] == expected["schema_version"] == 1
        assert actual["available"] is expected["available"]
        if actual.get("image"):
            assert actual["image"]["sha256"] == sha(image.read_bytes())
            actual["image"]["sha256"] = "validated actual PNG"
            expected["image"]["sha256"] = "validated frozen PNG"
            # Both original image digests are independently verified in prepare().
            expected["image"]["sha256"] = actual["image"]["sha256"]
        assert actual == expected, (kind, "Original geometry/diagnostics changed")
        result[kind] = {"sha256": sha(path.read_bytes()), "normalized": actual}
    return result


def summarize(records, key):
    warm = [r for r in records if r["phase"] == "ordinary-warm-font"]
    values = [r[key] for r in warm if key in r]
    ordered = sorted(values)
    position = (len(ordered) - 1) * 0.9
    low = int(position)
    p90 = (
        ordered[low]
        + (ordered[min(low + 1, len(ordered) - 1)] - ordered[low]) * (position - low)
        if ordered
        else None
    )
    return {
        "scheduled_warm": len(warm),
        "recorded_durations": len(values),
        "accepted_warm": sum(r.get("passed", False) for r in warm),
        "median_all_recorded_seconds": statistics.median(values) if values else None,
        "p90_all_recorded_seconds_linear": p90,
        "includes_unexpected_failures_if_any": True,
    }


def native_case(args, rules):
    imported = time.perf_counter()
    sys.path.insert(0, str(args.package))
    from graphunslopify import preview

    package = Path(preview.__file__).resolve().parent
    assert package.parent == args.package.resolve()
    case = next(c for c in rules["cases"] if c["id"] == args.case)
    original = args.baseline / "cases" / case["id"]
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=False)
    setup = time.perf_counter()
    state = preview.PreviewState(
        out / "session",
        100 * 1024 * 1024,
        reuse_renderer=True,
        reuse_translator=True,
        cache_statistics=True,
        profile_driver=PROFILE,
    )
    result = {
        "case": case["id"],
        "arm": args.arm,
        "constructor_seconds": time.perf_counter() - setup,
        "package": str(package),
        "package_files": fingerprint(package),
        "records": [],
        "passed": False,
    }
    result["driver_ready_ns"] = DRIVER_READY_NS
    result["preconstructor_package_and_case_setup_seconds"] = setup - imported
    result["driver_sha256"] = sha(Path(__file__).read_bytes())
    assert state.worker.process.max_requests == rules["native"]["native_request_budget"]
    assert (
        state.translator.process.max_requests
        == rules["native"]["compiler_request_budget"]
    )
    result["renderer_request_budget"] = state.worker.process.max_requests
    result["compiler_request_budget"] = state.translator.process.max_requests
    result["node_path"] = str(state.translator.node)
    result["node_sha256"] = sha(state.translator.node.read_bytes())
    result["renderer_source_signature"] = state.worker.source_signature
    worker_pids = None
    request, render = state._compiler_request, state._run_generated
    reference = None
    try:
        setup = time.perf_counter()
        uploaded = state.upload(case["data"], (original / case["data"]).read_bytes())
        result["upload_seconds"] = time.perf_counter() - setup
        spec = json.loads((original / "spec.json").read_text())
        warm = (
            rules["smoke"]["warm_native_repetitions"]
            if args.smoke
            else rules["native"]["warm_repetitions"]
        )
        for generation in range(warm + 2):
            instrumented = generation == warm + 1
            record = {
                "generation": generation,
                "phase": "instrumented-warm-font"
                if instrumented
                else "first-fresh-font"
                if generation == 0
                else "ordinary-warm-font",
                "passed": False,
            }
            result["records"].append(record)
            counters = {
                "translation_calls": 0,
                "translation_seconds": 0.0,
                "renderer_calls": 0,
                "renderer_seconds": 0.0,
            }
            phase_path = None

            def convert(operation, payload=None, _counters=counters):
                began = time.perf_counter()
                try:
                    return request(operation, payload)
                finally:
                    _counters["translation_calls"] += 1
                    _counters["translation_seconds"] += time.perf_counter() - began

            def execute(
                command, folder, timeout, _counters=counters, _instrumented=instrumented
            ):
                nonlocal phase_path
                if _instrumented:
                    native = command[3:]
                    program = next(
                        Path(v)
                        for v in native
                        if v.endswith(".py") and Path(v).is_absolute()
                    )
                    phase_path = folder / "phase-timings.json"
                    prefix, separator, _ = command[2].partition("import runpy;")
                    assert separator, "Owned bootstrap changed"
                    bootstrap = (
                        prefix
                        + f'import runpy; runpy.run_path({str(PROFILE)!r},run_name="__main__")'
                    )
                    command = [
                        *command[:2],
                        bootstrap,
                        "--timings",
                        str(phase_path),
                        "--profile-script",
                        str(program),
                        *native,
                    ]
                began = time.perf_counter()
                try:
                    return render(command, folder, timeout)
                finally:
                    _counters["renderer_calls"] += 1
                    _counters["renderer_seconds"] += time.perf_counter() - began

            try:
                with (
                    patch.dict(
                        os.environ,
                        {"MPLCONFIGDIR": str(out / "font-cache"), "MPLBACKEND": "Agg"},
                    ),
                    patch.object(state, "_compiler_request", convert),
                    patch.object(state, "_run_generated", execute),
                ):
                    began = time.perf_counter()
                    try:
                        answer = state.render(
                            {
                                "client": case["id"],
                                "generation": generation,
                                "data_id": uploaded["id"],
                                "spec": spec,
                            }
                        )
                    finally:
                        record["engine_seconds"] = time.perf_counter() - began
                record["counters"] = counters
                assert not answer["stale"] and not answer["export_errors"]
                folder = state.runs[answer["run_id"]]["folder"]
                assert (
                    (folder / "figure.py").read_bytes()
                    == (original / "figure.py").read_bytes()
                    if args.arm == "accepted-inline"
                    else True
                )
                checked = signature(
                    folder,
                    case,
                    answer["report"],
                    answer["exit_code"],
                    out / "retained" / str(generation),
                )
                current = normalized(checked)
                if reference is None:
                    reference = current
                    result["reference"] = current
                assert current == reference, (
                    "Original science/drawings changed across repetitions"
                )
                actual_maps = maps(folder, original)
                record["map_hashes"] = {k: v["sha256"] for k, v in actual_maps.items()}
                execution, compiler = (
                    answer["execution"],
                    answer["translation_execution"],
                )
                if worker_pids is None:
                    worker_pids = [execution["pid"], compiler["pid"]]
                assert worker_pids == [execution["pid"], compiler["pid"]]
                assert (
                    execution["runtime_source_sha256"]
                    == result["renderer_source_signature"]
                )
                for identity in (execution, compiler):
                    assert identity["mode"] == "worker" and type(identity["pid"]) is int
                    assert identity["request_number"] == generation + 1
                    assert identity["process_started"] is (generation == 0)
                assert compiler["runtime_source_sha256"] == sha(
                    (package / "_translator.mjs").read_bytes()
                )
                cache = execution["statistics_cache"]
                assert (
                    cache["enabled"]
                    and cache["max_entries"] == rules["native"]["cache_entries"]
                    and cache["max_bytes"] == rules["native"]["cache_serialized_bytes"]
                )
                assert counters["translation_calls"] == counters["renderer_calls"] == 1
                record.update(
                    execution=execution,
                    translation_execution=compiler,
                    artifacts=checked["artifact_files"],
                    exit_code=answer["exit_code"],
                    status=answer["report"]["status"],
                )
                if instrumented:
                    phases = json.loads(phase_path.read_text())
                    assert (
                        phases["program_sha256"] == checked["script_sha256"]
                        and phases["hooks_restored"]
                    )
                    assert (
                        phases["counts"]["compile_calls"]
                        == phases["counts"]["exec_calls"]
                        == 1
                    )
                    assert phases["counts"]["source_reads"] >= 1
                    record["instrumented_phases"] = phases
                record["passed"] = True
            except Exception as error:  # noqa: BLE001 -- retain actual unexpected outcomes
                record["error"] = f"{type(error).__name__}: {error}"
            save(out / "results.json", result)
        result["passed"] = all(r["passed"] for r in result["records"])
        result["summary"] = summarize(result["records"], "engine_seconds")
    finally:
        state.close()
        result["workers_closed"] = True
        save(out / "results.json", result)
    return 0 if result["passed"] else 1


def probe(executable, out, env):
    completed = subprocess.run(
        [str(executable), "-c", PROBE, *SCIENCE],
        cwd=out,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(completed.stdout)


def prepare(out, rules):
    source = ROOT / "python/graphunslopify"
    current = out / "current-source/graphunslopify"
    baseline = out / "accepted-source"
    current.mkdir(parents=True)
    baseline.mkdir()
    files = fingerprint(source)
    for name in files:
        target = current / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((source / name).read_bytes())
    archive = ROOT / "benchmarks/runtime" / rules["baseline_archive"]
    assert sha(archive.read_bytes()) == rules["baseline_archive_sha256"]
    with zipfile.ZipFile(archive) as z:
        manifest = json.loads(z.read("source-manifest.json"))
        assert all(
            sha(z.read(n)) == digest for n, digest in manifest["members"].items()
        )
        for name in z.namelist():
            assert not Path(name).is_absolute() and ".." not in Path(name).parts
            if name.startswith(("graphunslopify/", "cases/")) and not name.endswith(
                "/"
            ):
                target = baseline / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read(name))
    for case in rules["cases"]:
        folder = baseline / "cases" / case["id"]
        assert sha((folder / "figure.py").read_bytes()) == case["program_sha256"]
        assert sha((folder / case["data"]).read_bytes()) == case["data_sha256"]
        spec = (folder / "spec.json").read_bytes()
        assert spec.endswith(b"\n") and sha(spec[:-1]) == case["spec_sha256"]
        for kind in ("edit", "diagnostic"):
            mapping = json.loads(
                (folder / f"original-figure.{kind}-map.json").read_text()
            )
            if mapping.get("image"):
                assert mapping["image"]["sha256"] == sha(
                    (folder / "original-figure.png").read_bytes()
                )
    assert fingerprint(current) == files
    return baseline, current.parent


def direct_case(
    case, arm, directory, package, program, executable, environment, warm, reference
):
    records = []
    result = {"case": case["id"], "arm": arm, "records": records, "passed": False}
    env = {
        **environment,
        "MPLCONFIGDIR": str(directory / "font-cache"),
        "MPLBACKEND": "Agg",
    }
    if arm == "standalone-bundle":
        env["GRAPHUNSLOPIFY_NODE"] = "/deliberately/not/a/node/executable"
    for generation in range(warm + 1):
        record = {
            "generation": generation,
            "phase": "first-fresh-font" if generation == 0 else "ordinary-warm-font",
            "passed": False,
        }
        records.append(record)
        timing = directory / f"timing-{generation}.json"
        command = [
            str(executable),
            "-c",
            DIRECT,
            str(timing),
            str(package) if package else "-",
            str(program),
            "--json",
        ]
        began = time.perf_counter_ns()
        try:
            completed = subprocess.run(
                command,
                cwd=directory,
                env=env,
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            ended = time.perf_counter_ns()
            record["wall_seconds"] = (ended - began) / 1e9
            (directory / f"stdout-{generation}.json").write_text(completed.stdout)
            (directory / f"stderr-{generation}.txt").write_text(completed.stderr)
            record.update(json.loads(timing.read_text()))
            record["launch_to_child_entry_seconds"] = (
                record["child_entry_ns"] - began
            ) / 1e9
            record["completion_and_teardown_seconds"] = (
                ended - record["original_end_ns"]
            ) / 1e9
            report = json.loads(completed.stdout)
            if arm == "standalone-bundle":
                assert (
                    report["environment"]["installed_optional_versions"][
                        "graphunslopify"
                    ]
                    is None
                )
            checked = signature(
                directory,
                case,
                report,
                completed.returncode,
                directory / "retained" / str(generation),
                completed.stderr,
            )
            assert normalized(checked) == reference, (
                "Original native science/drawings changed in direct execution"
            )
            record.update(
                passed=True,
                exit_code=completed.returncode,
                status=report["status"],
                artifacts=checked["artifact_files"],
            )
        except Exception as error:  # noqa: BLE001 -- retain every failed/partial direct attempt
            record.setdefault("wall_seconds", (time.perf_counter_ns() - began) / 1e9)
            record["error"] = f"{type(error).__name__}: {error}"
        save(directory / "measurements.json", result)
    result["passed"] = all(r["passed"] for r in records)
    result["summary"] = summarize(records, "wall_seconds")
    save(directory / "measurements.json", result)
    return result


def main():
    if not __debug__:
        raise RuntimeError("Run this verifier without Python optimization")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--python",
        type=Path,
        help="Scientific interpreter without an installed/importable GraphUnslopify distribution",
    )
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--native-case", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--package", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--baseline", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--case", help=argparse.SUPPRESS)
    parser.add_argument("--arm", help=argparse.SUPPRESS)
    args = parser.parse_args()
    raw = (ROOT / "benchmarks/runtime/protocol.json").read_bytes()
    assert sha(raw) == PROTOCOL_SHA
    rules = json.loads(raw)
    args.out_dir = args.out_dir.resolve()
    if args.native_case:
        return native_case(args, rules)
    if args.python is None:
        parser.error("--python is required for genuine standalone execution")
    executable = args.python.expanduser().absolute()  # retain the venv symlink
    out = args.out_dir
    if out.is_relative_to(ROOT):
        raise ValueError("Measurement must run outside the checkout")
    out.mkdir(parents=True, exist_ok=False)
    environment = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    sys.path.insert(0, str(ROOT / "python"))
    from graphunslopify.runtime_bundle import create_bundle
    from graphunslopify.translator_worker import _node_executable
    from graphunslopify.transport import local_request

    setup = time.perf_counter()
    baseline, current = prepare(out, rules)
    preparation_seconds = time.perf_counter() - setup
    native_probe = probe(sys.executable, out, environment)
    direct_probe = probe(executable, out, environment)
    assert (
        direct_probe["graphunslopify_version"] is None
        and not direct_probe["graphunslopify_importable"]
    )
    assert native_probe["science"] == direct_probe["science"]
    assert native_probe["python"] == direct_probe["python"]
    node = _node_executable()
    result = {
        "scope": __doc__,
        "protocol_sha256": sha(raw),
        "mode": "smoke" if args.smoke else "formal",
        "source_revision": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip(),
        "python": sys.version,
        "platform": platform.platform(),
        "native_probe": native_probe,
        "direct_probe": direct_probe,
        "node": {
            "path": str(node),
            "sha256": sha(node.read_bytes()),
            "version": subprocess.check_output(
                [str(node), "--version"], text=True
            ).strip(),
        },
        "driver_sha256": sha(Path(__file__).read_bytes()),
        "profile_sha256": sha(PROFILE.read_bytes()),
        "direct_bootstrap_sha256": sha(DIRECT.encode()),
        "package_copy_and_frozen_input_validation_seconds": preparation_seconds,
        "complete": False,
        "passed": False,
        "native": [],
        "direct": [],
        "footprint": [],
    }
    for label, package in (
        ("accepted_package", baseline / "graphunslopify"),
        ("current_package", current / "graphunslopify"),
    ):
        result[label] = footprint(
            {n: (package / n).read_bytes() for n in fingerprint(package)}
        )
    try:
        for number, case in enumerate(rules["cases"]):
            reference = None
            arms = rules["native"]["arms"][:: -1 if number % 2 else 1]
            for arm in arms:
                package = baseline if arm == "accepted-inline" else current
                target = out / case["id"] / "native" / arm
                command = [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--native-case",
                    "--out-dir",
                    str(target),
                    "--package",
                    str(package),
                    "--baseline",
                    str(baseline),
                    "--case",
                    case["id"],
                    "--arm",
                    arm,
                    *(["--smoke"] if args.smoke else []),
                ]
                launched = time.perf_counter_ns()
                completed = subprocess.run(
                    command,
                    cwd=out,
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=900,
                    check=False,
                )
                ended = time.perf_counter_ns()
                target.mkdir(parents=True, exist_ok=True)
                (target / "driver.stdout.txt").write_text(completed.stdout)
                (target / "driver.stderr.txt").write_text(completed.stderr)
                if not (target / "results.json").exists():
                    result["native"].append(
                        {
                            "case": case["id"],
                            "arm": arm,
                            "passed": False,
                            "exit_code": completed.returncode,
                            "error": completed.stderr,
                        }
                    )
                    continue
                actual = json.loads((target / "results.json").read_text())
                actual["driver_exit_code"] = completed.returncode
                actual["launch_to_driver_imports_ready_seconds"] = (
                    actual["driver_ready_ns"] - launched
                ) / 1e9
                actual["child_wall_including_all_validation_seconds"] = (
                    ended - launched
                ) / 1e9
                actual["passed"] = actual["passed"] and completed.returncode == 0
                assert actual["driver_sha256"] == result["driver_sha256"]
                expected_files = result[
                    "accepted_package"
                    if arm == "accepted-inline"
                    else "current_package"
                ]["members"]
                assert actual["package_files"] == {
                    n: v["sha256"] for n, v in expected_files.items()
                }
                assert actual["node_sha256"] == result["node"]["sha256"]
                if reference is None:
                    reference = actual.get("reference")
                actual["matches_other_native_arm"] = (
                    actual.get("reference") == reference
                )
                result["native"].append(actual)
                save(out / "results.json", result)
                print(case["id"], "native", arm, actual["passed"], flush=True)
            original = baseline / "cases" / case["id"]
            spec = json.loads((original / "spec.json").read_text())
            started = time.perf_counter()
            translated = local_request("convert", spec)
            assert translated["ok"] and translated["status"] == "translated"
            translation_seconds = time.perf_counter() - started
            program = translated["code"].encode()
            (expected_runtime,) = [
                ast.literal_eval(n.value)
                for n in ast.parse(program).body
                if isinstance(n, ast.Assign)
                and any(
                    isinstance(t, ast.Name) and t.id == "EXPECTED_RUNTIME"
                    for t in n.targets
                )
            ]
            started = time.perf_counter()
            bundle = create_bundle(
                {"figure.py": program},
                script="figure.py",
                inputs={case["data"]: (original / case["data"]).read_bytes()},
            )
            bundle_seconds = time.perf_counter() - started
            bundle_path = out / case["id"] / "complete-source.zip"
            bundle_path.write_bytes(bundle)
            with zipfile.ZipFile(bundle_path) as z:
                members = {n: z.read(n) for n in z.namelist() if not n.endswith("/")}
                bundle_manifest = json.loads(members["_graphunslopify/manifest.json"])
            result["footprint"].append(
                {
                    "case": case["id"],
                    "entry_inline": metrics((original / "figure.py").read_bytes()),
                    "entry_shared": metrics(program),
                    "bundle_zip": metrics(bundle),
                    "bundle_members": footprint(members),
                    "pinned_scientific_components": footprint(
                        {
                            n: (current / "graphunslopify" / n).read_bytes()
                            for n in expected_runtime["components"]
                        }
                    ),
                    "translation_setup_seconds": translation_seconds,
                    "bundle_creation_setup_seconds": bundle_seconds,
                }
            )
            direct_arms = rules["direct"]["arms"]
            direct_arms = direct_arms[number % 3 :] + direct_arms[: number % 3]
            for arm in direct_arms:
                target = out / case["id"] / "direct" / arm
                target.mkdir(parents=True)
                setup = time.perf_counter()
                if arm == "standalone-bundle":
                    with zipfile.ZipFile(bundle_path) as z:
                        assert all(
                            not Path(n).is_absolute() and ".." not in Path(n).parts
                            for n in z.namelist()
                        )
                        z.extractall(target)
                    for name, descriptor in bundle_manifest["files"].items():
                        data = (target / name).read_bytes()
                        assert (
                            sha(data) == descriptor["sha256"]
                            and len(data) == descriptor["bytes"]
                        )
                    prefix = "_graphunslopify/runtime/graphunslopify/"
                    assert {
                        n[len(prefix) :]: sha(v)
                        for n, v in members.items()
                        if n.startswith(prefix)
                    } == {
                        n: v["sha256"]
                        for n, v in result["current_package"]["members"].items()
                    }
                    script, package = target / bundle_manifest["launcher"], None
                else:
                    (target / "figure.py").write_bytes(
                        (original / "figure.py").read_bytes()
                        if arm == "accepted-inline"
                        else program
                    )
                    (target / case["data"]).write_bytes(
                        (original / case["data"]).read_bytes()
                    )
                    script, package = (
                        target / "figure.py",
                        baseline if arm == "accepted-inline" else current,
                    )
                setup_seconds = time.perf_counter() - setup
                warm = (
                    rules["smoke"]["direct_repetitions"]
                    if args.smoke
                    else rules["direct"]["warm_repetitions"]
                )
                actual = direct_case(
                    case,
                    arm,
                    target,
                    package,
                    script,
                    executable,
                    environment,
                    warm,
                    reference,
                )
                actual["file_setup_or_extraction_seconds"] = setup_seconds
                result["direct"].append(actual)
                save(out / "results.json", result)
                print(case["id"], "direct", arm, actual["passed"], flush=True)
        result["complete"] = len(result["native"]) == 60 and len(result["direct"]) == 90
        result["passed"] = result["complete"] and all(
            r["passed"] and r.get("matches_other_native_arm", True)
            for r in [*result["native"], *result["direct"]]
        )
        assert fingerprint(current / "graphunslopify") == {
            n: v["sha256"] for n, v in result["current_package"]["members"].items()
        }
    finally:
        save(out / "results.json", result)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
