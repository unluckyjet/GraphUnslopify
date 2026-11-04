"""Owned, deadline-bound HTTP worker for consented reviewer requests.

Provider credentials and request bytes travel through stdin, never arguments or
temporary files. Stopping this worker discards its reply; it cannot unsend an
HTTP request or guarantee that a remote provider stops inference.
"""

from __future__ import annotations

import base64
import contextlib
import json
import math
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from .drafts import MAX_REQUEST, MAX_RESPONSE, DraftProvider, _model_text, _strict_json

REQUEST_DEADLINE = 90
MAX_INPUT = 2 * MAX_REQUEST + 65536
MAX_OUTPUT = 6 * MAX_RESPONSE + 65536
_TRANSPORT_ERRORS = {
    "The model provider could not be reached; manual authoring is available",
    "The model response exceeds the size limit",
    "The model response was incomplete",
    "The model refused or returned a tool call instead of a draft",
    "The model returned a tool call or unsupported output",
    "The model refused or returned unsupported content",
    "The model did not return one draft",
    "The model returned an empty draft",
    "The model returned an unsupported response",
}


def reviewer_model_text(
    provider: DraftProvider,
    body: bytes,
    *,
    timeout: float = REQUEST_DEADLINE,
    cancelled: threading.Event | None = None,
) -> str:
    """Stop and reap one owned worker on deadline or local cancellation.

    The deadline includes connection, headers, body reads and response parsing
    after launch. OS process creation and bounded process reaping add overhead.
    There is no automatic retry and no redirect/proxy policy change.
    """
    if not isinstance(provider, DraftProvider):
        raise TypeError("Configure a DraftProvider for the reviewer")
    if not isinstance(body, bytes) or not 0 < len(body) <= MAX_REQUEST:
        raise ValueError("Choose a nonempty reviewer request no larger than 1MiB")
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or not 0 < timeout <= REQUEST_DEADLINE
    ):
        raise ValueError("Reviewer deadline must be greater than zero and at most 90 seconds")
    if cancelled is not None and not isinstance(cancelled, threading.Event):
        raise TypeError("Reviewer cancellation must be a threading.Event")
    if len(provider.endpoint) > 8192 or len(provider.api_key) > 16384:
        raise ValueError("Reviewer provider settings exceed their size limits")
    if cancelled is not None and cancelled.is_set():
        raise ValueError("Reviewer request was cancelled; no new request was sent")
    payload = json.dumps(
        {
            "provider": {**provider.public(), "api_key": provider.api_key},
            "body": base64.b64encode(body).decode("ascii"),
        },
        ensure_ascii=False,
    ).encode("utf8")
    if len(payload) > MAX_INPUT:
        raise ValueError("Reviewer worker input exceeds its size limit")
    command = [
        sys.executable,
        "-I",
        "-c",
        "import runpy,sys;sys.path.insert(0,"
        + repr(str(Path(__file__).resolve().parent.parent))
        + ");runpy.run_module('graphunslopify.review_transport',run_name='__main__')",
    ]
    deadline = time.monotonic() + timeout
    with subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    ) as worker:
        finished = threading.Event()
        cancel_seen = threading.Event()

        def watch_cancel():
            while not finished.is_set():
                if cancelled.is_set():
                    cancel_seen.set()
                    with contextlib.suppress(ProcessLookupError):
                        worker.kill()
                    return
                finished.wait(0.05)

        watcher = None
        if cancelled is not None:
            watcher = threading.Thread(target=watch_cancel, name="review-provider-cancel")
            watcher.start()
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ValueError(
                    f"Reviewer provider exceeded its {timeout:g}-second request deadline"
                )
            try:
                # One communicate call transfers all stdin while draining stdout.
                # Retrying short time slices with input=None can strand an input
                # larger than the pipe buffer on supported Python versions.
                output, _ = worker.communicate(payload, timeout=remaining)
            except subprocess.TimeoutExpired:
                raise ValueError(
                    f"Reviewer provider exceeded its {timeout:g}-second request deadline"
                ) from None
            if cancel_seen.is_set() or (cancelled is not None and cancelled.is_set()):
                raise ValueError(
                    "Reviewer request cancelled; the provider may already have received it"
                )
            if time.monotonic() > deadline:
                raise ValueError(
                    f"Reviewer provider exceeded its {timeout:g}-second request deadline"
                )
            if worker.returncode != 0 or not output or len(output) > MAX_OUTPUT:
                raise ValueError("Reviewer provider worker did not return a complete response")
            try:
                result = _strict_json(output.decode("utf8"))
            except (UnicodeError, ValueError) as error:
                raise ValueError("Reviewer provider worker returned an invalid response") from error
            if not isinstance(result, dict) or type(result.get("ok")) is not bool:
                raise ValueError("Reviewer provider worker returned an invalid response")
            if result["ok"] is False:
                if set(result) != {"ok", "error"} or not isinstance(result["error"], str):
                    raise ValueError("Reviewer provider worker returned an invalid error")
                raise ValueError(result["error"][:2000])
            if (
                set(result) != {"ok", "text"}
                or not isinstance(result["text"], str)
                or len(result["text"].encode("utf8")) > MAX_RESPONSE
            ):
                raise ValueError("Reviewer provider worker returned an invalid response")
            return result["text"]
        finally:
            finished.set()
            if watcher is not None:
                watcher.join(2)
            if worker.poll() is None:
                worker.kill()
            # Reap before returning, including provider errors, timeout and cancel.
            worker.communicate(timeout=5)


def _worker():
    """Private one-request stdin/stdout protocol; never print credentials or stderr."""
    try:
        content = sys.stdin.buffer.read(MAX_INPUT + 1)
        if not 0 < len(content) <= MAX_INPUT:
            raise ValueError("Reviewer worker input exceeds its size limit")
        request = _strict_json(content.decode("utf8"))
        if not isinstance(request, dict) or set(request) != {"provider", "body"}:
            raise ValueError("Invalid reviewer worker input")
        provider = DraftProvider(**request["provider"])
        body = base64.b64decode(request["body"], validate=True)
        if not 0 < len(body) <= MAX_REQUEST:
            raise ValueError("Reviewer worker request exceeds its size limit")
        text = _model_text(provider, body)
        result = {"ok": True, "text": text}
    except (OSError, ValueError, TypeError, KeyError) as error:
        # Only transport's fixed messages are useful to the author. Never echo
        # arbitrary worker input, provider credentials or traceback diagnostics.
        message = str(error)
        safe = message in _TRANSPORT_ERRORS or re.fullmatch(
            r"The model provider returned HTTP [0-9]{3}; review its configuration", message
        )
        result = {
            "ok": False,
            "error": message
            if safe
            else "Reviewer provider request failed; check its endpoint and response",
        }
    encoded = json.dumps(result, ensure_ascii=False).encode("utf8")
    if len(encoded) > MAX_OUTPUT:
        encoded = b'{"ok":false,"error":"Reviewer provider response exceeds its size limit"}'
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    _worker()
