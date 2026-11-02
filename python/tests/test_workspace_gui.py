"""Actual HTTP observer parity and source/installed refusal; these are not GUI study rows."""

import contextlib
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

from PIL import Image

from graphunslopify.preview import PreviewServer, PreviewState

ROOT = Path(__file__).resolve().parents[2]


def test_preview_accepts_queued_module_connections():
    """Real simultaneous client connections must survive before module handlers accept."""
    server = PreviewServer(0)
    sockets = []
    thread = None
    port = server.server_address[1]
    try:
        # TCP connections precede serve_forever, making listen capacity observable.
        for _ in range(16):
            sockets.append(socket.create_connection(("127.0.0.1", port), timeout=2))
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        for connection in sockets:
            connection.sendall(f"GET /app.js HTTP/1.0\r\nHost: 127.0.0.1:{port}\r\n\r\n".encode())
            received = b""
            while chunk := connection.recv(65536):
                received += chunk
            assert received.startswith(b"HTTP/1.0 200")
            assert b"import { createControls }" in received
    finally:
        for connection in sockets:
            connection.close()
        if thread is not None:
            server.shutdown()
            thread.join(timeout=10)
            assert not thread.is_alive()
        server.server_close()


def test_gui_server_refuses_source_package_as_installed(tmp_path):
    run = subprocess.run(
        [
            sys.executable,
            str(ROOT / "benchmarks/workspace/gui_server.py"),
            "--installed",
            "--out",
            str(tmp_path / "wrong"),
        ],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "python")},
        input='{"operation":"close"}\n',
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )
    assert run.returncode != 0
    assert "GUI source/installed package location does not match profile" in run.stderr
    assert not (tmp_path / "wrong/startup.json").exists()


@contextlib.contextmanager
def observed_server(path):
    process = subprocess.Popen(
        [sys.executable, str(ROOT / "benchmarks/workspace/gui_server.py"), "--out", str(path)],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "python")},
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        line = process.stdout.readline()
        assert line, "Actual observer server exited before readiness"
        yield json.loads(line)
    finally:
        _, stderr = process.communicate('{"operation":"close"}\n', timeout=180)
        assert process.returncode == 0, stderr


def test_gui_observer_preserves_real_http_reply_program_and_png(tmp_path):
    """Compare an actual observed HTTP render with the same unobserved native pipeline."""
    definition = ROOT / "benchmarks/workspace/figures/iris-scatter.json"
    spec = json.loads(definition.read_text())
    data = (definition.parent / spec["data"]["path"]).read_bytes()
    owned = tmp_path / "observed"
    with observed_server(owned) as startup:
        html = urllib.request.urlopen(startup["url"]).read().decode("utf8")
        token = re.search(r'name="preview-token" content="([^"]+)"', html)[1]

        def post(route, raw, headers=None):
            request = urllib.request.Request(
                startup["url"] + route,
                data=raw,
                headers={"X-Preview-Token": token, **(headers or {})},
            )
            return json.loads(urllib.request.urlopen(request, timeout=120).read())

        upload = post("/api/upload", data, {"X-Filename": "iris.csv"})
        observed = post(
            "/api/render",
            json.dumps(
                {
                    "client": "actual-http-parity",
                    "generation": 1,
                    "data_id": upload["id"],
                    "spec": spec,
                }
            ).encode("utf8"),
            {"Content-Type": "application/json"},
        )
    receipts = [json.loads(p.read_text()) for p in (owned / "receipts").glob("*.json")]
    assert len(receipts) == 1 and receipts[0]["response"] == observed
    assert receipts[0]["observation_error"] is None
    captured = receipts[0]["result"]
    plain_root = tmp_path / "plain"
    plain_root.mkdir()
    plain = PreviewState(
        plain_root,
        100 * 1024 * 1024,
        reuse_renderer=True,
        reuse_translator=True,
        cache_statistics=True,
        staged_preview=True,
    )
    try:
        uploaded = plain.upload("iris.csv", data)
        answer = plain.render(
            {"client": "plain-parity", "generation": 1, "data_id": uploaded["id"], "spec": spec}
        )
        folder = plain.runs[answer["run_id"]]["folder"]
        assert answer["exit_code"] == observed["exit_code"] == 0
        assert answer["report"]["spec"] == observed["report"]["spec"]
        assert (
            hashlib.sha256((folder / "figure.py").read_bytes()).hexdigest()
            == captured["producer_sha256"]
        )
        with (
            Image.open(folder / "figure.png") as left,
            Image.open(Path(captured["owned_folder"]) / "figure.png") as right,
        ):
            assert left.size == right.size
            assert left.convert("RGBA").tobytes() == right.convert("RGBA").tobytes()
    finally:
        plain.close()
    closure = json.loads((owned / "closure.json").read_text())
    assert not closure["errors"] and closure["pid"] == startup["pid"]
