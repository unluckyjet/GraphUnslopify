"""Private bounded JSON-line process transport owned by one local editor session."""

from __future__ import annotations

import contextlib
import hashlib
import json
import ntpath
import os
import queue
import signal
import subprocess
import sys
import threading
import time
import uuid
import weakref
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROTOCOL = 1
MAX_FRAME = 16 * 1024 * 1024
MAX_REQUEST = 4 * 1024 * 1024


class WorkerError(RuntimeError):
    """A private worker failed; this is never scientific acceptance."""


def _owned_launch(command, env, *, windows=None):
    """Bypass Windows venv redirectors while retaining their interpreter context."""
    windows = os.name == "nt" if windows is None else windows
    base = getattr(sys, "_base_executable", None) or sys.executable
    if (
        windows
        and ntpath.normcase(command[0]) == ntpath.normcase(sys.executable)
        and ntpath.normcase(base) != ntpath.normcase(sys.executable)
    ):
        # Match CPython's Lib/multiprocessing/popen_spawn_win32.py: the venv
        # redirector otherwise owns Popen.pid while another process executes.
        return [base, *command[1:]], {**env, "__PYVENV_LAUNCHER__": sys.executable}
    return command, env


@dataclass
class Connection:
    process: subprocess.Popen
    messages: queue.Queue = field(default_factory=lambda: queue.Queue(maxsize=4))
    errors: deque = field(default_factory=lambda: deque(maxlen=16))
    readers: list[threading.Thread] = field(default_factory=list)


def _stdout(pipe, messages):
    try:
        while True:
            line = pipe.readline(MAX_FRAME + 1)
            if not line:
                item = (False, "Worker closed its response stream")
            elif len(line) > MAX_FRAME or not line.endswith(b"\n"):
                item = (False, "Worker exceeded the response frame limit")
            else:
                item = (True, line)
            try:
                messages.put_nowait(item)
            except queue.Full:
                return
            if not item[0]:
                return
    except (OSError, ValueError) as problem:
        with contextlib.suppress(queue.Full):
            messages.put_nowait((False, f"Worker response stream failed: {problem}"))


def _stderr(pipe, tail):
    try:
        while block := pipe.read(4096):
            tail.append(block)
    except (OSError, ValueError):
        pass


def _stop(connection):
    """Kill the owned tree before closing pipes that a reader/writer may hold."""
    process = connection.process
    if os.name != "nt":
        # Descendants may still own pipes after their direct parent exits.
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(process.pid, signal.SIGKILL)
    elif process.poll() is None:
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                check=False,
                timeout=5,
            )
    if process.poll() is None:
        with contextlib.suppress(ProcessLookupError):
            process.kill()
    with contextlib.suppress(subprocess.TimeoutExpired):
        process.wait(timeout=5)
    for reader in connection.readers:
        reader.join(timeout=1)
    for pipe in [process.stdin, process.stdout, process.stderr]:
        with contextlib.suppress(OSError, ValueError):
            pipe.close()


class JsonWorker:
    """One serialized request at a time, with deadline/restart and no global daemon."""

    def __init__(
        self,
        command: list[str],
        cwd: Path,
        *,
        kind: str,
        max_requests: int = 16,
        expected_ready: dict | None = None,
    ):
        if type(max_requests) is not int or not 1 <= max_requests <= 128:
            raise ValueError("Worker request bound must be between1 and128")
        self.command, self.cwd, self.kind = command, cwd.resolve(), kind
        self.max_requests = max_requests
        self.expected_ready = dict(expected_ready or {})
        self.lock = threading.RLock()
        self.connection: Connection | None = None
        self.finalizer = None
        self.environment = None
        self.count = 0
        self.closed = False
        self.starts = 0

    def _reset(self):
        if self.finalizer is not None:
            self.finalizer()
        self.finalizer = None
        self.connection = None
        self.environment = None
        self.count = 0

    def close(self):
        with self.lock:
            self.closed = True
            self._reset()

    def _receive(self, deadline, timeout):
        try:
            ok, value = self.connection.messages.get(timeout=max(0.0, deadline - time.monotonic()))
        except queue.Empty as problem:
            raise subprocess.TimeoutExpired(self.command, timeout) from problem
        if not ok:
            tail = b"".join(self.connection.errors).decode("utf8", errors="replace")[-1600:]
            raise WorkerError(value + (": " + tail if tail else ""))
        try:
            answer = json.loads(value.decode("utf8"))
        except (UnicodeError, ValueError) as problem:
            raise WorkerError("Worker returned malformed protocol JSON") from problem
        if not isinstance(answer, dict) or answer.get("protocol") != PROTOCOL:
            raise WorkerError("Worker protocol version mismatch")
        return answer

    def _start(self, env, signature, deadline, timeout):
        options = (
            {"start_new_session": True}
            if os.name != "nt"
            else {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        )
        command, launch_env = _owned_launch(self.command, env)
        process = subprocess.Popen(
            command,
            cwd=self.cwd,
            env=launch_env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **options,
        )
        connection = Connection(process)
        self.connection = connection
        # Reader targets retain only pipes/queues, so the owner can be collected.
        for target, args in [
            (_stdout, (process.stdout, connection.messages)),
            (_stderr, (process.stderr, connection.errors)),
        ]:
            reader = threading.Thread(target=target, args=args, daemon=True)
            connection.readers.append(reader)
            reader.start()
        self.finalizer = weakref.finalize(self, _stop, connection)
        ready = self._receive(deadline, timeout)
        if (
            ready.get("kind") != self.kind
            or ready.get("ready") is not True
            or type(ready.get("pid")) is not int
            or ready["pid"] != process.pid
            or any(ready.get(key) != value for key, value in self.expected_ready.items())
        ):
            raise WorkerError("Worker readiness does not match the owned process")
        self.environment = signature
        self.starts += 1

    def request(self, payload: dict[str, Any], timeout: float):
        if timeout <= 0:
            raise ValueError("Worker timeout must be positive")
        with self.lock:
            if self.closed:
                raise WorkerError("This editor worker has been closed")
            deadline = time.monotonic() + timeout
            env = {**os.environ, "MPLBACKEND": "Agg", "PYTHONIOENCODING": "utf-8"}
            # Never persist environment contents or credentials in protocol/evidence.
            signature = hashlib.sha256(json.dumps(env, sort_keys=True).encode()).digest()
            started = False
            writer = None
            try:
                if (
                    self.connection is None
                    or self.environment != signature
                    or self.count >= self.max_requests
                    or self.connection.process.poll() is not None
                ):
                    self._reset()
                    self._start(env, signature, deadline, timeout)
                    started = True
                identity = uuid.uuid4().hex
                frame = (
                    json.dumps(
                        {"protocol": PROTOCOL, "id": identity, "payload": payload},
                        ensure_ascii=False,
                        allow_nan=False,
                    )
                    + "\n"
                ).encode("utf8")
                if len(frame) > MAX_REQUEST:
                    raise WorkerError("Worker request exceeds the frame limit")
                failures = []
                pipe = self.connection.process.stdin

                def write():
                    try:
                        pipe.write(frame)
                        pipe.flush()
                    except (OSError, ValueError) as problem:
                        failures.append(problem)

                writer = threading.Thread(target=write, daemon=True)
                writer.start()
                answer = self._receive(deadline, timeout)
                writer.join(timeout=max(0.0, deadline - time.monotonic()))
                if writer.is_alive():
                    raise subprocess.TimeoutExpired(self.command, timeout)
                if failures:
                    raise WorkerError("Worker request stream failed") from failures[0]
                if answer.get("id") != identity or type(answer.get("ok")) is not bool:
                    raise WorkerError("Worker response belongs to another request")
                if not answer["ok"]:
                    raise WorkerError(str(answer.get("error", "Worker failed"))[:1600])
                self.count += 1
                execution = {
                    "mode": "worker",
                    "kind": self.kind,
                    "pid": self.connection.process.pid,
                    "request_id": identity,
                    "request_number": self.count,
                    "process_started": started,
                    "process_starts": self.starts,
                    "protocol": PROTOCOL,
                }
                result = answer.get("result")
                if answer.get("retire") is True:
                    self._reset()
                return result, execution
            except BaseException:
                self._reset()
                raise
            finally:
                if writer is not None:
                    writer.join(timeout=1)
