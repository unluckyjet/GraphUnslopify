"""Authenticated real selective jobs and unchanged worker/revision boundaries."""

import json
import shutil
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from graphunslopify import project as model
from graphunslopify import project_preview as workspace

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def baseline(tmp_path_factory):
    root = tmp_path_factory.mktemp("reuse-http") / "paper"
    shutil.copytree(ROOT / "examples/paper", root)
    model.initialize_project(root)
    first = model.run_project(root, baseline=None)
    assert first["exit_code"] == 0
    backup = root.parent / "backup"
    shutil.copytree(root, backup)
    return root, backup


@pytest.fixture
def server(baseline):
    root, backup = baseline
    shutil.rmtree(root)
    shutil.copytree(backup, root)
    instance = workspace.ProjectServer(root)
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        yield instance, root
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join(10)


def request(server, path, payload=None, *, status=200, token=True, headers=None):
    instance, _ = server
    call = urllib.request.Request(
        "http://127.0.0.1:" + str(instance.server_address[1]) + path,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={**({"X-Preview-Token": instance.state.token} if token else {}), **(headers or {})},
    )
    try:
        response = urllib.request.urlopen(call, timeout=30)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        data = response.read()
        assert response.code == status, data
        return json.loads(data)


def completed(server, *, error=None):
    end = time.monotonic() + 60
    while time.monotonic() < end:
        state = request(server, "/api/state")
        if state["job"] and state["job"]["phase"] != "running":
            if error:
                assert error in state["job"]["error"], state["job"]
            else:
                assert not state["job"].get("error"), state["job"]
            return state["job"]["result"]
        time.sleep(0.05)
    raise AssertionError("Actual selective worker did not finish")


def test_actual_http_selective_job_reports_saved_counts_and_original_execution(server):
    _, root = server
    state = request(server, "/api/state")
    request(
        server, "/api/run", {"selective": True, "expected_revision": state["revision"]}, status=202
    )
    result = completed(server)
    assert result["exit_code"] == 0
    event = request(server, "/api/event?id=" + result["id"])
    saved = json.loads(
        (root / "graphunslopify-project/history" / result["id"] / "result.json").read_text()
    )
    assert event["result"] == saved
    assert saved["audit"]["execution_counts"] == {"executed": 0, "reused": 2, "not_run": 0}
    assert all(f["execution"]["mode"] == "reused" for f in event["result"]["audit"]["figures"])


def test_saved_paper_cleaning_preview_never_dispatches_or_changes_history(server):
    _, root = server
    state = request(server, "/api/state")
    identity = state["figures"][0]["id"]
    payload = {"id": identity, "expected_revision": state["revision"]}
    route = "/api/cleaning-preview"
    history = model.project_history(root)
    request(server, route, payload, token=False, status=403)
    request(server, route, {**payload, "expected_revision": "stale"}, status=400)
    preview = request(server, route, payload)
    assert preview["status"] == "prepared" and preview["rows"]["read"] > 0
    assert len(preview["source_sha256"]) == 64
    assert request(server, "/api/state")["job"] is None
    assert model.project_history(root) == history


def test_auth_origin_boolean_and_stale_revision_refuse_before_new_history(server):
    _, root = server
    state = request(server, "/api/state")
    payload = {"selective": True, "expected_revision": state["revision"]}
    before = model.project_history(root)
    request(server, "/api/run", payload, token=False, status=403)
    request(server, "/api/run", payload, headers={"Origin": "https://example.invalid"}, status=403)
    request(server, "/api/run", {**payload, "selective": "yes"}, status=400)
    data = root / "results.csv"
    data.write_bytes(data.read_bytes() + b"\n")
    request(server, "/api/run", payload, status=202)
    result = completed(server, error="changed since review")
    # Revision checks execute inside the real worker; failure creates no run.
    assert result is None
    assert before == model.project_history(root)


def test_real_held_selective_job_keeps_the_existing_single_worker_boundary(server, monkeypatch):
    _, root = server
    entered = threading.Event()
    release = threading.Event()
    actual = workspace.run_project

    def held(*args, **kwargs):
        entered.set()
        assert release.wait(30)
        return actual(*args, **kwargs)

    monkeypatch.setattr(workspace, "run_project", held)
    state = request(server, "/api/state")
    payload = {"selective": True, "expected_revision": state["revision"]}
    request(server, "/api/run", payload, status=202)
    assert entered.wait(10)
    try:
        request(server, "/api/run", payload, status=400)
        request(
            server,
            "/api/shared-review",
            {"expected_revision": state["revision"], "shared": {"style": {"grid": True}}},
            status=400,
        )
    finally:
        release.set()
    result = completed(server)
    assert result["exit_code"] == 0
    event = request(server, "/api/event?id=" + result["id"])
    assert event["result"]["audit"]["execution_counts"]["reused"] == 2
    assert model.project_history(root)["integrity"] == "verified"
