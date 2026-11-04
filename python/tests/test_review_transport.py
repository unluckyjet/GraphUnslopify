"""Actual provider processes: complete-body deadline, cancellation, privacy and reaping."""

from __future__ import annotations

import json
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from graphunslopify import review_transport as transport
from graphunslopify.drafts import MAX_REQUEST, MAX_RESPONSE, DraftProvider


@pytest.fixture
def workers(monkeypatch):
    actual = subprocess.Popen
    owned = []

    def launch(*args, **kwargs):
        worker = actual(*args, **kwargs)
        owned.append(worker)
        return worker

    monkeypatch.setattr(transport.subprocess, "Popen", launch)
    yield owned
    for worker in owned:
        assert worker.poll() is not None, "Owned reviewer worker survived its request"
        assert worker.stdin.closed and worker.stdout.closed
        assert "SECRET_HEADER_ONLY" not in " ".join(worker.args)
    assert not any(t.name == "review-provider-cancel" for t in threading.enumerate())


@pytest.fixture
def provider():
    state = SimpleNamespace(
        requests=[],
        status=200,
        protocol="chat",
        reply='Exact reply: Ω, "quoted"\ntext',
        raw=None,
        chunks=1,
        delay=0,
        before_headers=False,
        seen=threading.Event(),
        release=threading.Event(),
        finished=threading.Event(),
        sent=[],
    )

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            state.finished.clear()
            state.requests.append(
                (
                    self.path,
                    self.rfile.read(int(self.headers["Content-Length"])),
                    dict(self.headers),
                )
            )
            state.seen.set()
            try:
                if state.before_headers:
                    state.release.wait(15)
                body = (
                    state.raw
                    or json.dumps(
                        {
                            "choices": [
                                {"finish_reason": "stop", "message": {"content": state.reply}}
                            ]
                        }
                        if state.protocol == "chat"
                        else {
                            "status": "completed",
                            "output": [
                                {
                                    "type": "message",
                                    "content": [{"type": "output_text", "text": state.reply}],
                                }
                            ],
                        }
                    ).encode()
                )
                self.send_response(state.status)
                if state.status == 307:
                    self.send_header("Location", state.endpoint + "/redirected")
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                for index in range(state.chunks):
                    if index and state.release.wait(state.delay):
                        break
                    self.wfile.write(
                        body[
                            index * len(body) // state.chunks : (index + 1)
                            * len(body)
                            // state.chunks
                        ]
                    )
                    self.wfile.flush()
                    state.sent.append(time.monotonic())
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                state.finished.set()

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as http:
        http.daemon_threads = True
        state.endpoint = f"http://127.0.0.1:{http.server_port}/model"
        thread = threading.Thread(target=http.serve_forever)
        thread.start()
        try:
            yield state
        finally:
            state.release.set()
            http.shutdown()
            thread.join(5)
            if state.requests:
                assert state.finished.wait(5)
            assert not thread.is_alive()


def settings(provider):
    return DraftProvider(
        provider.endpoint, "controlled-no-inference", provider.protocol, "SECRET_HEADER_ONLY"
    )


@pytest.mark.parametrize("protocol", ["chat", "responses"])
@pytest.mark.parametrize("size", [64, 192000, MAX_REQUEST])
def test_real_worker_preserves_request_bytes_authorization_and_reply(
    provider, workers, protocol, size
):
    provider.protocol = protocol
    body = b'{"value":"' + b"x" * (size - 13) + b'"}\n'
    assert len(body) == size
    assert transport.reviewer_model_text(settings(provider), body) == provider.reply
    assert len(provider.requests) == 1 and len(workers) == 1
    _, observed, headers = provider.requests[0]
    assert observed == body and headers["Authorization"] == "Bearer SECRET_HEADER_ONLY"
    assert workers[0].returncode == 0


def test_response_larger_than_pipe_buffer_is_drained_without_loss(provider, workers):
    provider.reply = "x" * 800000
    assert transport.reviewer_model_text(settings(provider), b"{}") == provider.reply
    assert len(workers) == 1 and workers[0].returncode == 0


@pytest.mark.parametrize("before_headers", [False, True])
def test_actual_worker_deadline_covers_headers_and_continued_small_reads(
    provider, workers, before_headers
):
    provider.before_headers = before_headers
    provider.chunks, provider.delay = 12, 0.4
    started = time.monotonic()
    with pytest.raises(ValueError, match="2-second request deadline"):
        transport.reviewer_model_text(settings(provider), b"{}", timeout=2)
    elapsed = time.monotonic() - started
    assert 1.8 <= elapsed < 5
    assert len(workers) == 1 and workers[0].returncode is not None
    assert provider.seen.is_set()
    if not before_headers:
        assert len(provider.sent) >= 2, "Exercise an actively progressing body, not only a stall"


def test_cancel_before_launch_sends_nothing_and_starts_no_worker(provider, workers):
    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(ValueError, match="no new request was sent"):
        transport.reviewer_model_text(settings(provider), b"{}", cancelled=cancelled)
    assert not provider.requests and not workers


def test_cancellation_reaps_actual_inflight_worker_and_discards_reply(provider, workers):
    provider.before_headers = True
    cancelled = threading.Event()

    def cancel_after_send():
        assert provider.seen.wait(10)
        cancelled.set()

    cancel = threading.Thread(target=cancel_after_send)
    cancel.start()
    started = time.monotonic()
    try:
        with pytest.raises(ValueError, match="may already have received"):
            transport.reviewer_model_text(settings(provider), b"{}", cancelled=cancelled)
        assert time.monotonic() - started < 5
        assert len(provider.requests) == 1 and len(workers) == 1
    finally:
        cancelled.set()
        provider.release.set()
        cancel.join(12)
    assert not cancel.is_alive()


@pytest.mark.parametrize("status", [429, 307])
def test_provider_failure_preserves_http_status_and_never_redirects_or_retries(
    provider, workers, status
):
    provider.status = status
    with pytest.raises(ValueError, match=f"HTTP {status}"):
        transport.reviewer_model_text(settings(provider), b"{}")
    assert len(provider.requests) == 1 and len(workers) == 1
    assert workers[0].returncode == 0


def test_oversized_response_refuses_and_reaps_worker(provider, workers):
    provider.raw = b"x" * (MAX_RESPONSE + 1)
    with pytest.raises(ValueError, match="response exceeds the size limit"):
        transport.reviewer_model_text(settings(provider), b"{}")
    assert len(provider.requests) == 1 and len(workers) == 1


@pytest.mark.parametrize("timeout", [0, -1, 91, float("nan"), float("inf"), True, "1"])
def test_invalid_deadline_refuses_before_creating_worker(provider, workers, timeout):
    with pytest.raises(ValueError, match="deadline"):
        transport.reviewer_model_text(settings(provider), b"{}", timeout=timeout)
    assert not workers and not provider.requests


def test_oversized_input_refuses_before_creating_worker(provider, workers):
    with pytest.raises(ValueError, match="1MiB"):
        transport.reviewer_model_text(settings(provider), b"x" * (MAX_REQUEST + 1))
    assert not workers and not provider.requests
