"""Real preview server with out-of-band post-clock evidence, never held checks."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import platform
import re
import shutil
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", choices=["final-only", "staged"], required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    out = args.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    os.environ["MPLCONFIGDIR"] = str(out / "fresh-font-cache")
    os.environ["MPLBACKEND"] = "Agg"
    from graphunslopify import preview, preview_worker

    loader = importlib.util.spec_from_file_location(
        "rendering_controls", ROOT / "scripts/rendering-benchmark.py"
    )
    controls = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(controls)
    started = time.perf_counter()
    server = preview.PreviewServer(0, staged_preview=args.arm == "staged")
    state = server.state
    state.worker.close()  # No process has started; both arms authorize the same profiler.
    state.worker = preview_worker.RenderWorker(
        state.root,
        profile_driver=ROOT / "scripts/profile-preview-phases.py",
        cache_statistics=True,
    )
    constructor_seconds = time.perf_counter() - started
    current = {"label": None, "instrumented": False}
    compiler_events, native_events, completed = [], [], {}
    request_original = state._compiler_request
    native_original = state._run_generated
    render_original = state.render

    def compiler(operation, payload=None):
        label = current["label"]
        began = time.perf_counter()
        answer, execution = request_original(operation, payload)
        compiler_events.append(
            {
                "label": label,
                "operation": operation,
                "seconds": time.perf_counter() - began,
                "execution": execution,
            }
        )
        return answer, execution

    def native(command, folder, timeout):
        label, instrumented = current["label"], current["instrumented"]
        if instrumented:
            native_args = command[3:]
            script = next(
                Path(v)
                for v in native_args
                if v.endswith(".py") and Path(v).is_absolute()
            )
            prefix, separator, _ = command[2].partition("import runpy;")
            if not separator:
                raise ValueError("Original owned native bootstrap changed")
            bootstrap = prefix + (
                f"import runpy; runpy.run_path({str(ROOT / 'scripts/profile-preview-phases.py')!r},run_name='__main__')"
            )
            command = [
                *command[:2],
                bootstrap,
                "--timings",
                str(folder / "phase-timings.json"),
                "--profile-script",
                str(script),
                *native_args,
            ]
        began = time.perf_counter()
        result = native_original(command, folder, timeout)
        native_events.append(
            {
                "label": label,
                "seconds": time.perf_counter() - began,
                "execution": result.execution,
            }
        )
        return result

    def render(payload):
        label = current["label"]
        began = time.perf_counter()
        answer = render_original(payload)
        if answer.get("run_id"):
            completed[answer["run_id"]] = {
                "label": label,
                "answer": answer,
                "engine_seconds": time.perf_counter() - began,
                "payload": payload,
            }
        return answer

    state._compiler_request, state._run_generated, state.render = (
        compiler,
        native,
        render,
    )
    package = Path(preview.__file__).resolve().parent
    suffixes = {".py", ".mjs", ".js", ".json", ".txt", ".css", ".html", ".ipynb"}
    package_files = {
        str(p.relative_to(package)): digest(p)
        for p in sorted(package.rglob("*"))
        if p.is_file() and p.suffix in suffixes
    }
    environment = {
        "python": platform.python_version(),
        "executable": sys.executable,
        "prefix": sys.prefix,
        "platform": platform.platform(),
        "package_root": str(package),
    }
    for name in ["numpy", "pandas", "matplotlib", "scipy", "pyarrow"]:
        try:
            spec = importlib.util.find_spec(name)
            environment[name] = {
                "version": importlib.metadata.version(name),
                "module": spec.origin if spec else None,
            }
        except importlib.metadata.PackageNotFoundError:
            environment[name] = None

    def proof(message):
        record = completed[message["run_id"]]
        if record["label"] != message["label"]:
            raise ValueError("Evidence does not own this actual completed request")
        answer = record["answer"]
        report = answer["report"]
        folder = state.runs[answer["run_id"]]["folder"]
        stem = answer["spec"]["output"]["stem"]
        artifact = controls.artifacts(state, answer)
        png = folder / f"{stem}.png"
        maps = {}
        for name in ["edit_map", "diagnostic_map"]:
            value = answer[name]
            if not value.get("available") or value["run_id"] != answer["run_id"]:
                raise ValueError("Current map is unavailable or belongs to another run")
            if value["spec_hash"] != report["spec_hash"] or value["image"][
                "sha256"
            ] != digest(png):
                raise ValueError("Map differs from the actual final spec/PNG")
            maps[name] = {k: v for k, v in value.items() if k != "run_id"}
        signature = {
            "semantic_report": controls.semantic(report),
            "script_sha256": digest(folder / f"{stem}.py"),
            "input_sha256": digest(state.uploads[record["payload"]["data_id"]]["path"]),
            "png": artifact["png"],
            "png_sha256": digest(png),
            "table_text": artifact["table_text"],
            **maps,
        }
        raw = json.dumps(signature, sort_keys=True, allow_nan=False).encode()
        evidence = {
            **record,
            "signature": signature,
            "artifacts": artifact,
            "signature_sha256": hashlib.sha256(raw).hexdigest(),
            "compiler_events": [
                e for e in compiler_events if e["label"] == record["label"]
            ],
            "native_events": [
                e for e in native_events if e["label"] == record["label"]
            ],
        }
        timing = folder / "phase-timings.json"
        if timing.exists():
            evidence["instrumented_phases"] = json.loads(timing.read_text())
        path = out / "proofs" / (record["label"] + ".json")
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(evidence, indent=2, allow_nan=False) + "\n")
        if message.get("preserve_reference"):
            target = out / "references" / record["label"]
            target.mkdir(parents=True)
            for source in folder.iterdir():
                if source.is_file() and not source.name.startswith("."):
                    shutil.copyfile(source, target / source.name)
        return {
            "proof": str(path),
            "signature_sha256": evidence["signature_sha256"],
            "input_sha256": signature["input_sha256"],
            "png_sha256": signature["png_sha256"],
            "formats": artifact["formats"],
            "engine_seconds": record["engine_seconds"],
            "compiler_events": evidence["compiler_events"],
            "native_events": evidence["native_events"],
        }

    def emit(value):
        print(json.dumps(value, allow_nan=False), flush=True)

    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    emit(
        {
            "url": f"http://127.0.0.1:{server.server_port}/",
            "arm": args.arm,
            "constructor_seconds": constructor_seconds,
            "environment": environment,
            "package_files": package_files,
            "runtime_source_sha256": preview_worker._package_signature(),
            "profiler_sha256": digest(ROOT / "scripts/profile-preview-phases.py"),
        }
    )
    try:
        for line in sys.stdin:
            message = json.loads(line)
            try:
                if message["op"] == "prepare":
                    if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", message["label"]):
                        raise ValueError("Invalid evidence label")
                    current.update(
                        label=message["label"],
                        instrumented=message["instrumented"] is True,
                    )
                    result = {"prepared": True}
                elif message["op"] == "proof":
                    result = proof(message)
                elif message["op"] == "close":
                    break
                else:
                    raise ValueError("Unknown benchmark control operation")
                emit({"id": message["id"], "result": result})
            except (ValueError, KeyError, TypeError, OSError, RuntimeError) as error:
                emit({"id": message["id"], "error": str(error)})
    finally:
        server.shutdown()
        thread.join()
        native_connection = state.worker.process.connection
        compiler_connection = state.translator.process.connection
        owned_root = state.root
        server.server_close()
        closure = {
            "native_closed": native_connection is None
            or native_connection.process.poll() is not None,
            "compiler_closed": compiler_connection is None
            or compiler_connection.process.poll() is not None,
            "temporary_root_removed": not owned_root.exists(),
            "compiler_events": compiler_events,
            "native_events": native_events,
        }
        (out / "closed.json").write_text(json.dumps(closure, indent=2) + "\n")
        if not all(
            closure[k]
            for k in ["native_closed", "compiler_closed", "temporary_root_removed"]
        ):
            raise RuntimeError("Owned benchmark resources did not close")


if __name__ == "__main__":
    main()
