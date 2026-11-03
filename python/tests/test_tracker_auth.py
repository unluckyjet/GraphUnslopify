"""Actual SDK against an explicitly selected rejecting local HTTP endpoint."""

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from graphunslopify import experiment_imports as imports
from graphunslopify import tracker_imports as trackers


@pytest.mark.parametrize("redirect", [False, True])
def test_actual_wandb_sdk_rejected_auth_is_bounded_and_redacted(monkeypatch, redirect):
    pytest.importorskip("wandb")
    psutil = pytest.importorskip("psutil")
    calls = []
    cores = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            for process in psutil.Process().children(recursive=True):
                try:
                    if process.name().startswith("wandb-core"):
                        cores[(process.pid, process.create_time())] = process
                except psutil.Error:
                    pass
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            calls.append(
                {
                    "path": self.path,
                    "authorization_present": bool(self.headers.get("Authorization")),
                    "port": self.server.server_port,
                }
            )
            if self.server.redirect_to:
                self.send_response(307)
                self.send_header("Location", self.server.redirect_to + self.path)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            data = b'{"errors":[{"message":"controlled authorization refusal"}]}'
            self.send_response(401)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(data)

    original = trackers.JsonWorker

    def bounded(*args, **kwargs):
        process = original(*args, **kwargs)
        request = process.request
        process.request = lambda payload, timeout: request(payload, 10)
        return process

    monkeypatch.setattr(trackers, "JsonWorker", bounded)
    with (
        ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server,
        ThreadingHTTPServer(("127.0.0.1", 0), Handler) as target,
    ):
        target.redirect_to = None
        server.redirect_to = f"http://127.0.0.1:{target.server_port}" if redirect else None
        target_thread = threading.Thread(target=target.serve_forever)
        target_thread.start()
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        key = "x" * 40
        try:
            with pytest.raises(imports.ExperimentError) as failure:
                imports.experiment_runs(
                    "fixture/histories",
                    provider="wandb",
                    tracker={
                        "endpoint": f"http://127.0.0.1:{server.server_port}",
                        "api_key": key,
                        "allow_remote": True,
                    },
                )
            assert key not in str(failure.value)
            assert calls and cores
            assert all(
                call["authorization_present"] == (call["port"] == server.server_port)
                for call in calls
            )
            assert not redirect or any(call["port"] == target.server_port for call in calls)
            deadline = time.monotonic() + 3
            while (
                any(p.is_running() and p.status() != psutil.STATUS_ZOMBIE for p in cores.values())
                and time.monotonic() < deadline
            ):
                time.sleep(0.05)
            assert not any(
                p.is_running() and p.status() != psutil.STATUS_ZOMBIE for p in cores.values()
            )
        finally:
            server.shutdown()
            thread.join(5)
            target.shutdown()
            target_thread.join(5)
