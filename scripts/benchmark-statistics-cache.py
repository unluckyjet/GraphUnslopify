"""Compare actual cached/uncached edit cycles against numerical-cache-v1."""

from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import re
import statistics
import subprocess
import sys
import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.util.spec_from_file_location(
    "rendering_controls", ROOT / "scripts/rendering-benchmark.py"
)
controls = importlib.util.module_from_spec(loader)
loader.loader.exec_module(controls)
digest = controls.digest


def protocol():
    base = ROOT / "benchmarks/incremental"
    path = base / "protocol.json"
    rules = json.loads(path.read_text())
    for case in rules["cases"]:
        data = (base / case["data"]).resolve()
        if (
            not data.is_relative_to(ROOT / "benchmarks")
            or digest(data) != case["data_sha256"]
        ):
            raise ValueError("Frozen cache data changed")
        for edit in case["edits"]:
            spec = (base / edit["spec"]).resolve()
            if not spec.is_relative_to(base) or digest(spec) != edit["spec_sha256"]:
                raise ValueError("Frozen cache edit changed")
    return base, path, rules


def run_case(case, mode, base, out, rules, cycles, result, preview):
    folder = out / case["id"] / mode
    folder.mkdir(parents=True)
    began = time.perf_counter()
    state = preview.PreviewState(
        folder,
        100_000_000,
        reuse_renderer=True,
        reuse_translator=True,
        cache_statistics=mode == "cached",
        profile_driver=ROOT / "scripts/profile-preview-phases.py",
    )
    constructor = time.perf_counter() - began
    original_request, original_run = state._compiler_request, state._run_generated
    current = {
        "id": case["id"],
        "mode": mode,
        "constructor_seconds": constructor,
        "records": [],
        "references": {},
    }
    result["cases"].append(current)
    epochs = {}
    try:
        started = time.perf_counter()
        upload = state.upload("data.csv", (base / case["data"]).read_bytes())
        current["upload_seconds"] = time.perf_counter() - started
        schedule = [("first-fresh-font", None, case["edits"][0])]
        schedule += [
            ("ordinary-warm-font", cycle, edit)
            for cycle in range(cycles)
            for edit in case["edits"]
        ]
        schedule += [("instrumented-warm-font", None, case["edits"][0])]
        for generation, (phase, cycle, edit) in enumerate(schedule):
            counters = {
                "translation_calls": 0,
                "translation_seconds": 0.0,
                "renderer_calls": 0,
                "renderer_seconds": 0.0,
            }
            phase_path = None

            def request(operation, payload=None, _counters=counters):
                start = time.perf_counter()
                try:
                    return original_request(operation, payload)
                finally:
                    _counters["translation_calls"] += 1
                    _counters["translation_seconds"] += time.perf_counter() - start

            def native(command, run_folder, timeout, _counters=counters, _phase=phase):
                nonlocal phase_path
                if _phase == "instrumented-warm-font":
                    native_args = command[3:]
                    program = next(
                        Path(v)
                        for v in native_args
                        if v.endswith(".py") and Path(v).is_absolute()
                    )
                    phase_path = run_folder / "phase-timings.json"
                    prefix, separator, _ = command[2].partition("import runpy;")
                    if not separator:
                        raise ValueError("Owned native bootstrap changed")
                    bootstrap = (
                        prefix
                        + f'import runpy; runpy.run_path({str(ROOT / "scripts/profile-preview-phases.py")!r},run_name="__main__")'
                    )
                    command = [
                        *command[:2],
                        bootstrap,
                        "--timings",
                        str(phase_path),
                        "--profile-script",
                        str(program),
                        *native_args,
                    ]
                start = time.perf_counter()
                try:
                    return original_run(command, run_folder, timeout)
                finally:
                    _counters["renderer_calls"] += 1
                    _counters["renderer_seconds"] += time.perf_counter() - start

            entry = {
                "generation": generation,
                "phase": phase,
                "cycle": cycle,
                "edit": edit["id"],
                "passed": False,
            }
            current["records"].append(entry)
            try:
                intent = json.loads((base / edit["spec"]).read_text())
                with (
                    controls.font_directory(folder / "font-cache"),
                    patch.object(state, "_compiler_request", request),
                    patch.object(state, "_run_generated", native),
                ):
                    start = time.perf_counter()
                    answer = state.render(
                        {
                            "client": case["id"],
                            "generation": generation,
                            "data_id": upload["id"],
                            "spec": intent,
                        }
                    )
                    entry["engine_seconds"] = time.perf_counter() - start
                report = answer["report"]
                if report is None or answer["run_id"] is None:
                    raise ValueError("Compiler produced no runnable figure")
                entry.update(exit_code=answer["exit_code"], status=report["status"])
                if (
                    answer["exit_code"] != case["expected_exit_code"]
                    or report["status"] != case["expected_status"]
                    or not report["policy"]["strict"]
                    or answer["stale"]
                    or answer["export_errors"]
                ):
                    raise ValueError(
                        "Original strict outcome/current export binding changed"
                    )
                evidence = controls.artifacts(state, answer)
                if (
                    evidence["formats"] != sorted(rules["formats"])
                    or report["data"]["sha256_prefix"] != case["data_sha256"][:16]
                    or digest(state.uploads[upload["id"]]["path"])
                    != case["data_sha256"]
                ):
                    raise ValueError(
                        "Actual original input or requested formats changed"
                    )
                for key in ("edit_map", "diagnostic_map"):
                    location = answer[key]
                    if (
                        not location["available"]
                        or location["run_id"] != answer["run_id"]
                        or location["spec_hash"] != report["spec_hash"]
                    ):
                        raise ValueError("Current map ownership unavailable")
                signature = {
                    "semantic_report": controls.semantic(report),
                    "png": evidence["png"],
                    "table_text": evidence["table_text"],
                    "script_sha256": digest(
                        state.runs[answer["run_id"]]["folder"]
                        / f"{answer['spec']['output']['stem']}.py"
                    ),
                }
                previous = current["references"].setdefault(edit["id"], signature)
                if previous != signature:
                    raise ValueError(
                        "Original variant science/script/PNG/table changed across cycles"
                    )
                execution, compiler = (
                    answer["execution"],
                    answer["translation_execution"],
                )
                if (
                    execution.get("mode") != "worker"
                    or compiler.get("mode") != "worker"
                    or compiler.get("kind") != "translator"
                    or compiler.get("runtime_source_sha256")
                    != result["invoked_package_files"]["_translator.mjs"]
                ):
                    raise ValueError("Actual combined-worker/source identity changed")
                if (
                    counters["translation_calls"] != 1
                    or counters["renderer_calls"] != 1
                ):
                    raise ValueError(
                        "Actual one-conversion/one-native sequence changed"
                    )
                for trace in (execution, compiler):
                    if type(trace.get("pid")) is not int or not re.fullmatch(
                        r"[0-9a-f]{32}", trace.get("request_id", "")
                    ):
                        raise ValueError("Actual worker request/PID binding changed")
                epoch = execution["pid"], execution["process_starts"]
                expected = epochs.get(epoch, 0) + 1
                if (
                    execution["request_number"] != expected
                    or expected > rules["schedule"]["native_max_requests"]
                    or execution["process_started"] != (expected == 1)
                ):
                    raise ValueError("Original bounded native lifecycle changed")
                epochs[epoch] = expected
                cache = execution["statistics_cache"]
                if (
                    cache.get("enabled") != (mode == "cached")
                    or cache.get("version") != 1
                    or cache.get("pid") != execution["pid"]
                    or cache.get("runtime_source_sha256")
                    != execution["runtime_source_sha256"]
                ):
                    raise ValueError(
                        "Numerical cache mode/current response binding changed"
                    )
                if mode == "cached" and (
                    cache["entries"] > cache["max_entries"]
                    or cache["serialized_bytes"] > cache["max_bytes"]
                ):
                    raise ValueError("Numerical cache exceeded its declared bound")
                entry.update(
                    execution=execution,
                    translation_execution=compiler,
                    counters=counters,
                    artifacts=evidence,
                )
                if phase == "instrumented-warm-font":
                    phases = json.loads(phase_path.read_text())
                    if (
                        phases["calls"].get("data_read") != 1
                        or phases["calls"].get("data_prepare") != 1
                    ):
                        raise ValueError(
                            "Instrumented request did not keep current input processing"
                        )
                    entry["instrumented_phases"] = phases
                entry["passed"] = True
            except Exception as problem:  # noqa: BLE001 -- retain every actual failed/negative attempt
                entry["error"] = f"{type(problem).__name__}: {problem}"
            (out / "results.json").write_text(
                json.dumps(result, indent=2, allow_nan=False) + "\n"
            )
        current["summary"] = {}
        for edit in case["edits"]:
            warm = [
                r["engine_seconds"]
                for r in current["records"]
                if r["edit"] == edit["id"]
                and r["phase"] == "ordinary-warm-font"
                and r["passed"]
            ]
            current["summary"][edit["id"]] = {
                "expected_repetitions": cycles,
                "accepted_repetitions": len(warm),
                "median_engine_seconds": statistics.median(warm) if warm else None,
                "p90_engine_seconds_linear": controls.percentile90(warm)
                if warm
                else None,
            }
        current["native_epochs"] = len(epochs)
        print(
            case["id"],
            mode,
            "passed",
            sum(r["passed"] for r in current["records"]),
            "of",
            len(schedule),
            flush=True,
        )
    finally:
        state.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--installed", action="store_true")
    args = parser.parse_args()
    base, protocol_path, rules = protocol()
    out = args.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    if not args.installed:
        sys.path.insert(0, str(ROOT / "python"))
    from graphunslopify import preview

    package = Path(preview.__file__).resolve().parent
    assets = [
        "preview.py",
        "preview_render.py",
        "preview_worker.py",
        "worker_process.py",
        "numerical_cache.py",
        "translator_worker.py",
        "transport.py",
        "drafts.py",
        "preview_drafts.py",
        "audit.py",
        "preview_geometry.py",
        "preview_diagnostics.py",
        "_translator.mjs",
    ]
    if args.installed and package == (ROOT / "python/graphunslopify").resolve():
        raise ValueError("Installed comparison resolved to the source checkout")
    if any(
        digest(package / p) != digest(ROOT / "python/graphunslopify" / p)
        for p in assets
    ):
        raise ValueError("Invoked package assets differ from current source")
    dependencies = {}
    for name in (
        "numpy",
        "pandas",
        "matplotlib",
        "pillow",
        "scipy",
        "pyarrow",
        "graphunslopify",
    ):
        try:
            dependencies[name] = version(name)
        except PackageNotFoundError:
            dependencies[name] = None
    cycles = rules["schedule"]["smoke_cycles" if args.smoke else "ordinary_cycles"]
    result = {
        "schema_version": 1,
        "mode": "conformance-smoke" if args.smoke else "formal-edit-cycle",
        "scope": rules["scope"],
        "protocol_sha256": digest(protocol_path),
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "source_git_dirty": bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=ROOT, text=True
            ).strip()
        ),
        "package_mode": "installed" if args.installed else "source",
        "package_root": str(package),
        "invoked_package_files": {p: digest(package / p) for p in assets},
        "sources": {
            str(p.relative_to(ROOT)): digest(p)
            for p in [
                Path(__file__),
                ROOT / "scripts/rendering-benchmark.py",
                ROOT / "scripts/profile-preview-phases.py",
            ]
        },
        "environment": {
            "python": sys.version,
            "executable": sys.executable,
            "platform": platform.platform(),
            "distribution_versions": dependencies,
        },
        "cycles": cycles,
        "expected_records": rules["expected_records"][
            "smoke" if args.smoke else "formal"
        ],
        "complete": False,
        "passed": False,
        "cases": [],
        "comparisons": [],
    }
    for number, case in enumerate(rules["cases"]):
        order = ["uncached", "cached"] if number % 2 == 0 else ["cached", "uncached"]
        for mode in order:
            run_case(case, mode, base, out, rules, cycles, result, preview)
        pair = {c["mode"]: c for c in result["cases"] if c["id"] == case["id"]}
        result["comparisons"].append(
            {
                "case": case["id"],
                "order": order,
                "same_original_variant_science_script_data_png_table": pair["uncached"][
                    "references"
                ]
                == pair["cached"]["references"],
            }
        )
    records = [r for c in result["cases"] for r in c["records"]]
    result["observed_records"] = len(records)
    result["complete"] = True
    result["passed"] = (
        len(records) == result["expected_records"]
        and all(r["passed"] for r in records)
        and all(
            c["same_original_variant_science_script_data_png_table"]
            for c in result["comparisons"]
        )
    )
    (out / "results.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n"
    )
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
