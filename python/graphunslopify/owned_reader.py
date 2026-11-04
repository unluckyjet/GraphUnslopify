"""Bounded, one-request readers for trusted adapters handling untrusted inputs."""

from __future__ import annotations

import hashlib
import json
import stat
import subprocess
import sys
import threading
from pathlib import Path

from .worker_process import JsonWorker, WorkerError


class ReaderError(ValueError):
    pass


def run_reader(
    root,
    *,
    module,
    kind,
    payload,
    filename,
    max_output,
    max_rss,
    timeout=90,
    worker_factory=JsonWorker,
):
    """Run a package-owned adapter; module/filename are trusted caller constants."""
    try:
        import psutil
    except ImportError as problem:
        raise ReaderError("Install psutil>=6 for bounded reader processes") from problem
    root = Path(root)
    package = Path(__file__).resolve().parent.parent
    bootstrap = (
        "import os,sys; sys.path[:]=[p for p in sys.path if p and os.path.normcase(os.path.realpath(p)) != os.path.normcase(os.path.realpath(os.getcwd()))]; "
        + f"sys.path.insert(0,{str(package)!r}); "
        + f"import runpy; runpy.run_module({module!r},run_name='__main__')"
    )
    worker = worker_factory(
        [sys.executable, "-c", bootstrap],
        root,
        kind=kind,
        max_requests=1,
        expected_ready={"adapter_version": 1},
    )
    stopped = threading.Event()
    overflow = threading.Event()
    owned = {}

    def monitor():
        while not stopped.wait(0.05):
            connection = worker.connection
            if connection is None:
                continue
            try:
                parent = psutil.Process(connection.process.pid)
                processes = [parent, *parent.children(recursive=True)]
                rss = 0
                for process in processes:
                    owned[(process.pid, process.create_time())] = process
                    rss += process.memory_info().rss
                if rss > max_rss:
                    overflow.set()
                    connection.process.kill()
                    return
            except (psutil.Error, OSError):
                continue

    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    try:
        try:
            answer, _ = worker.request(payload, timeout=timeout)
        except (WorkerError, TimeoutError, subprocess.TimeoutExpired) as problem:
            if overflow.is_set():
                raise ReaderError("Reader exceeded its process-tree memory budget") from problem
            if isinstance(problem, WorkerError) and str(problem).startswith(
                "Install graphunslopify[experiments]"
            ):
                raise ReaderError(
                    "Install graphunslopify[experiments] for this tracker SDK"
                ) from problem
            raise ReaderError(
                "Reader refused, failed or exceeded its deadline; no partial result accepted"
            ) from problem
        if overflow.is_set():
            raise ReaderError("Reader exceeded its memory budget")
        if (
            not isinstance(answer, dict)
            or answer.get("file") != filename
            or type(answer.get("bytes")) is not int
            or not 0 <= answer["bytes"] <= max_output
        ):
            raise ReaderError("Invalid reader output descriptor")
        path = root / filename
        if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
            raise ReaderError("Reader output is not an owned regular file")
        with path.open("rb") as stream:
            raw = stream.read(max_output + 1)
        if len(raw) != answer["bytes"] or hashlib.sha256(raw).hexdigest() != answer.get("sha256"):
            raise ReaderError("Reader output bytes changed")
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ReaderError("Reader output must be an object")
        return result
    finally:
        worker.close()
        stopped.set()
        thread.join(timeout=1)
        # A native service can use a different group; PID plus creation time
        # identifies only descendants observed during this invocation.
        for (_pid, created), process in owned.items():
            try:
                if (
                    process.create_time() == created
                    and process.is_running()
                    and process.status() != psutil.STATUS_ZOMBIE
                ):
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except psutil.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=2)
            except psutil.Error:
                pass
