"""Private session-owned compiler client; public one-shot transport is unchanged."""

from __future__ import annotations

import hashlib
import importlib.util
import os
import shutil
import subprocess
import threading
import weakref
from contextlib import ExitStack
from importlib.resources import as_file, files
from pathlib import Path
from typing import Any

from .errors import SpecError
from .worker_process import MAX_FRAME, MAX_REQUEST, JsonWorker, WorkerError


def _node_executable():
    override = os.environ.get("GRAPHUNSLOPIFY_NODE")
    if override:
        selected = shutil.which(override) or str(Path(override).expanduser())
        path = Path(selected).resolve()
    else:
        spec = importlib.util.find_spec("nodejs_wheel")
        if spec is not None and spec.origin is not None:
            root = Path(spec.origin).resolve().parent
            path = root / ("node.exe" if os.name == "nt" else "bin/node")
        elif selected := shutil.which("node"):
            path = Path(selected).resolve()
        else:
            raise SpecError(
                "Node runtime is missing; reinstall graphunslopify with its dependencies"
            )
    if not path.is_file():
        raise SpecError("The selected Node executable is missing; reinstall its runtime")
    return path


def _binary_identity(path):
    stat = path.stat()
    return str(path), stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TranslatorWorker:
    """One explicit private compiler owner; close before removing its session."""

    def __init__(self, root: Path, *, max_requests: int = 64):
        self.lock = threading.RLock()
        self.closed = False
        self.resources = ExitStack()
        self.finalizer = weakref.finalize(self, self.resources.close)
        try:
            self.root = root.resolve()
            self.root.mkdir(parents=True, exist_ok=True)
            self.bundle = self.resources.enter_context(
                as_file(files("graphunslopify").joinpath("_translator.mjs"))
            )
            self.source = _digest(self.bundle)
            self.node = _node_executable()
            self.runtime = _binary_identity(self.node)
            # Own the actual Node process, rather than its Python launcher PID.
            self.process = JsonWorker(
                [str(self.node), str(self.bundle), "--worker", str(max_requests)],
                self.root,
                kind="translator",
                max_requests=max_requests,
                expected_ready={
                    "bundle_sha256": self.source,
                    "max_requests": max_requests,
                    "max_request_bytes": MAX_REQUEST,
                    "max_frame_bytes": MAX_FRAME,
                },
            )
        except BaseException:
            self.finalizer()
            raise

    def close(self):
        with self.lock:
            self.closed = True
            try:
                self.process.close()
            finally:
                self.finalizer()

    def _current(self):
        if self.closed:
            raise SpecError("This editor translator has been closed")
        try:
            same = (
                _digest(self.bundle) == self.source
                and _binary_identity(_node_executable()) == self.runtime
            )
        except (OSError, SpecError) as problem:
            self.close()
            raise SpecError(
                "Translator source/runtime disappeared; restart the local editor"
            ) from problem
        if not same:
            self.close()
            raise SpecError("Translator source/runtime changed; restart the local editor")

    def request(self, operation: str, payload: Any = None, *, timeout: float = 60):
        """Return the application value and trace bound to this specific request."""
        with self.lock:
            self._current()
            try:
                answer, execution = self.process.request(
                    {"operation": operation, "payload": payload}, timeout
                )
            except (WorkerError, OSError, subprocess.TimeoutExpired, ValueError) as problem:
                raise SpecError(
                    f"Could not run the local translator worker: {problem}"
                ) from problem
            self._current()
            if not isinstance(answer, dict) or type(answer.get("ok")) is not bool:
                self.close()
                raise SpecError("Local translator worker returned a malformed completion")
            if not answer["ok"]:
                if not isinstance(answer.get("error"), str):
                    self.close()
                    raise SpecError("Local translator worker returned an invalid error")
                raise SpecError(answer["error"])
            if "result" not in answer:
                self.close()
                raise SpecError("Local translator worker omitted its result")
            execution["runtime_source_sha256"] = self.source
            return answer["result"], execution

    def call(self, operation: str, payload: Any = None, *, timeout: float = 60):
        return self.request(operation, payload, timeout=timeout)[0]
