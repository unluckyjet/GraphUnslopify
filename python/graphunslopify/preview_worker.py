"""Private canonical-render service: warm libraries, fresh script namespaces."""

from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import io
import json
import os
import random
import re
import runpy
import subprocess
import sys
import traceback
import warnings
from pathlib import Path
from typing import Any

from .worker_process import MAX_REQUEST, PROTOCOL, JsonWorker, WorkerError

LOG_LIMIT = 8 * 1024 * 1024


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _package_signature():
    root = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for path in sorted([*root.glob("*.py"), root / "_translator.mjs"]):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _program(runs: Path, job: Any, stem: Any, signature: Any):
    if not isinstance(job, str) or not re.fullmatch("[0-9a-f]{32}", job):
        raise WorkerError("Worker job identity is invalid")
    if (
        not isinstance(stem, str)
        or not stem
        or Path(stem).name != stem
        or stem in {".", ".."}
        or "\x00" in stem
    ):
        raise WorkerError("Worker output stem is invalid")
    if not isinstance(signature, str) or not re.fullmatch("[0-9a-f]{64}", signature):
        raise WorkerError("Worker script fingerprint is invalid")
    folder = runs / job
    script = folder / f"{stem}.py"
    if (
        folder.is_symlink()
        or script.is_symlink()
        or folder.resolve().parent != runs
        or script.resolve().parent != folder.resolve()
        or not script.is_file()
        or _digest(script) != signature
    ):
        raise WorkerError("Worker script does not match this owned run")
    return folder, script


def arguments(script: Path, stem: str):
    return [
        "--geometry",
        f"{stem}.edit-map.json",
        "--diagnostics",
        f"{stem}.diagnostic-map.json",
        "--png",
        f"{stem}.png",
        str(script),
        "--strict",
        "--json",
        "--report",
        f"{stem}.report.json",
    ]


class RenderWorker:
    """Owned by a server; callers outside a server must close it explicitly."""

    def __init__(
        self,
        root: Path,
        *,
        max_jobs: int = 16,
        profile_driver: Path | None = None,
        cache_statistics: bool = False,
    ):
        self.root = root.resolve()
        self.runs = self.root / "runs"
        self.runs.mkdir(parents=True, exist_ok=True)
        self.profile_driver = profile_driver.resolve() if profile_driver is not None else None
        package = Path(__file__).resolve().parent.parent
        bootstrap = (
            "import os,sys; sys.path[:]=[p for p in sys.path if p and os.path.normcase(os.path.realpath(p)) != os.path.normcase(os.path.realpath(os.getcwd()))]; "
            + f"sys.path.insert(0,{str(package)!r}); "
            + "import runpy; runpy.run_module('graphunslopify.preview_worker',run_name='__main__')"
        )
        command = [
            sys.executable,
            "-c",
            bootstrap,
            "--root",
            str(self.root),
            "--max-jobs",
            str(max_jobs),
        ]
        self.cache_statistics = cache_statistics
        if cache_statistics:
            command.append("--cache-statistics")
        if self.profile_driver is not None:
            command += [
                "--profile-driver",
                str(self.profile_driver),
                "--profile-sha256",
                _digest(self.profile_driver),
            ]
        self.process = JsonWorker(
            command,
            self.root,
            kind="renderer",
            max_requests=max_jobs,
            expected_ready={"statistics_cache": cache_statistics, "statistics_cache_version": 1},
        )
        self.last_execution = None
        self.source_signature = _package_signature()

    def close(self):
        self.process.close()

    def run(self, command, folder, timeout):
        self.last_execution = None
        if _package_signature() != self.source_signature:
            self.close()
            raise WorkerError("Renderer source changed; restart the local editor")
        if command[:2] != [sys.executable, "-c"]:
            raise WorkerError("Worker accepts only the owned native renderer")
        native = command[3:]
        profiled = False
        if len(native) >= 4 and native[0] == "--timings" and native[2] == "--profile-script":
            if self.profile_driver is None or Path(native[1]) != folder / "phase-timings.json":
                raise WorkerError("This worker has no authorized measurement driver")
            profile_script = native[3]
            native = native[4:]
            profiled = True
        provisional = native[:1] == ["--provisional"]
        if provisional:
            native = native[1:]
        if len(native) != 11:
            raise WorkerError("Worker native arguments are invalid")
        script = Path(native[6])
        stem = script.stem
        if (
            folder.resolve().parent != self.runs
            or folder.is_symlink()
            or script.is_symlink()
            or script.resolve().parent != folder.resolve()
        ):
            raise WorkerError("Worker script escapes its owned run")
        signature = _digest(script)
        owned_folder, owned_script = _program(self.runs, folder.name, stem, signature)
        if (
            folder.resolve() != owned_folder.resolve()
            or script != owned_script
            or native != arguments(script, stem)
            or (profiled and profile_script != str(script))
        ):
            raise WorkerError("Worker arguments escape the current owned run")
        result, execution = self.process.request(
            {
                "job": folder.name,
                "stem": stem,
                "sha256": signature,
                "profile": profiled,
                "provisional": provisional,
            },
            timeout,
        )
        if (
            not isinstance(result, dict)
            or type(result.get("returncode")) is not int
            or not isinstance(result.get("stdout"), str)
            or not isinstance(result.get("stderr"), str)
        ):
            self.close()
            raise WorkerError("Worker completion is malformed")
        if _digest(script) != signature or _package_signature() != self.source_signature:
            self.close()
            raise WorkerError("Worker script changed during execution")
        execution["runtime_source_sha256"] = self.source_signature
        execution["instrumented"] = profiled
        if result.get("provisional") is not provisional:
            self.close()
            raise WorkerError("Provisional render completion mode changed")
        execution["provisional"] = provisional
        cache = result.get("statistics_cache")
        if (
            not isinstance(cache, dict)
            or cache.get("version") != 1
            or cache.get("enabled") is not self.cache_statistics
            or cache.get("pid") != execution["pid"]
            or cache.get("runtime_source_sha256") != self.source_signature
        ):
            self.close()
            raise WorkerError("Numerical cache completion identity changed")
        execution["statistics_cache"] = cache
        self.last_execution = execution
        completed = subprocess.CompletedProcess(
            command, result["returncode"], result["stdout"], result["stderr"]
        )
        completed.execution = execution
        return completed


class LimitedLog(io.StringIO):
    def __init__(self):
        super().__init__()
        self.bytes = 0

    def write(self, value):
        self.bytes += len(value.encode("utf8"))
        if self.bytes > LOG_LIMIT:
            raise WorkerError("Render log exceeds the private worker budget")
        return super().write(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--max-jobs", type=int, default=16)
    parser.add_argument("--profile-driver", type=Path)
    parser.add_argument("--profile-sha256")
    parser.add_argument("--cache-statistics", action="store_true")
    config = parser.parse_args()
    if not 1 <= config.max_jobs <= 128:
        parser.error("Worker job bound must be between1 and128")
    runs = config.root.resolve() / "runs"
    if not runs.is_dir():
        parser.error("Worker run root does not exist")
    profile_driver = config.profile_driver.resolve() if config.profile_driver else None
    if profile_driver is not None and _digest(profile_driver) != config.profile_sha256:
        parser.error("Measurement driver changed before service startup")
    # Initialization belongs to the first request deadline and benchmark clock.
    import gc

    import matplotlib
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas  # noqa: F401 -- intentionally preload the reader/runtime
    from matplotlib.figure import Figure

    import graphunslopify

    from . import preview_render
    from .numerical_cache import ACTIVE, VERSION, NumericalCache

    source_signature = _package_signature()
    numerical = NumericalCache(source_signature) if config.cache_statistics else None

    matplotlib.use("Agg")
    baseline = {
        "cwd": Path.cwd(),
        "argv": sys.argv[:],
        "path": sys.path[:],
        "environment": dict(os.environ),
        "rc": copy.deepcopy(dict(matplotlib.rcParams)),
        "warnings": warnings.filters[:],
        "random": random.getstate(),
        "numpy_random": np.random.get_state(),
        "savefig": Figure.savefig,
        "inspect": graphunslopify.inspect_figure,
    }
    protocol_output = sys.stdout.buffer

    def send(message):
        frame = (
            json.dumps({"protocol": PROTOCOL, **message}, ensure_ascii=False, allow_nan=False)
            + "\n"
        ).encode("utf8")
        protocol_output.write(frame)
        protocol_output.flush()

    send(
        {
            "ready": True,
            "kind": "renderer",
            "pid": os.getpid(),
            "statistics_cache": config.cache_statistics,
            "statistics_cache_version": VERSION,
        }
    )
    for number in range(1, config.max_jobs + 1):
        raw = sys.stdin.buffer.readline(MAX_REQUEST + 1)
        if not raw:
            return 0
        if len(raw) > MAX_REQUEST or not raw.endswith(b"\n"):
            return 1
        identity = None
        try:
            message = json.loads(raw.decode("utf8"))
            identity = message.get("id") if isinstance(message, dict) else None
            if (
                not isinstance(identity, str)
                or not re.fullmatch("[0-9a-f]{32}", identity)
                or message.get("protocol") != PROTOCOL
            ):
                raise WorkerError("Private render envelope is invalid")
            payload = message.get("payload")
            if (
                not isinstance(payload, dict)
                or set(payload) != {"job", "stem", "sha256", "profile", "provisional"}
                or type(payload["profile"]) is not bool
                or type(payload["provisional"]) is not bool
            ):
                raise WorkerError("Private render request is invalid")
            folder, script = _program(runs, payload["job"], payload["stem"], payload["sha256"])
            if payload["profile"] and (
                profile_driver is None or _digest(profile_driver) != config.profile_sha256
            ):
                raise WorkerError("No matching measurement driver is owned by this service")
            stdout, stderr = LimitedLog(), LimitedLog()
            code = 0
            numerical_request = numerical.request() if numerical is not None else None
            token = ACTIVE.set(numerical_request)
            try:
                os.chdir(folder)
                sys.argv = ["preview-worker", *arguments(script, payload["stem"])]
                if payload["provisional"]:
                    sys.argv.insert(1, "--provisional")
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    try:
                        if payload["profile"]:
                            sys.argv[1:1] = [
                                "--timings",
                                str(folder / "phase-timings.json"),
                                "--profile-script",
                                str(script),
                            ]
                            runpy.run_path(str(profile_driver), run_name="__main__")
                        else:
                            preview_render.main()
                    except SystemExit as end:
                        code = end.code if type(end.code) is int else 0 if end.code is None else 1
            finally:
                ACTIVE.reset(token)
                # Canonical data is untrusted; arbitrary Python is not a public API.
                Figure.savefig = baseline["savefig"]
                graphunslopify.inspect_figure = baseline["inspect"]
                plt.close("all")
                matplotlib.rcParams.update(copy.deepcopy(baseline["rc"]))
                os.chdir(baseline["cwd"])
                sys.argv = baseline["argv"][:]
                sys.path[:] = baseline["path"]
                os.environ.clear()
                os.environ.update(baseline["environment"])
                warnings.filters[:] = baseline["warnings"]
                random.setstate(baseline["random"])
                np.random.set_state(baseline["numpy_random"])
                gc.collect()
            if _digest(script) != payload["sha256"] or plt.get_fignums():
                raise WorkerError("Render state or script identity changed before completion")
            send(
                {
                    "id": identity,
                    "ok": True,
                    "result": {
                        "returncode": code,
                        "stdout": stdout.getvalue(),
                        "stderr": stderr.getvalue(),
                        "provisional": payload["provisional"],
                        "statistics_cache": numerical_request.trace()
                        if numerical_request is not None
                        else {
                            "enabled": False,
                            "version": VERSION,
                            "pid": os.getpid(),
                            "runtime_source_sha256": source_signature,
                        },
                    },
                    "retire": number == config.max_jobs,
                }
            )
        except BaseException as problem:  # noqa: BLE001 -- abort protocol on any job/reset failure
            # Never publish a completed scientific report after protocol/reset failure.
            send(
                {
                    "id": identity,
                    "ok": False,
                    "error": f"{type(problem).__name__}: {problem}\n"
                    + traceback.format_exc(limit=3)[-1600:],
                    "retire": True,
                }
            )
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
