"""Real loopback project workflows, source ownership and saved evidence boundaries."""

from __future__ import annotations

import hashlib
import json
import shutil
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from graphunslopify import project_preview as workspace
from graphunslopify.project import (
    initialize_project,
    project_history,
    run_project,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def complete(tmp_path_factory):
    paper = tmp_path_factory.mktemp("workspace") / "paper with spaces"
    shutil.copytree(ROOT / "examples/paper", paper)
    initialize_project(paper)
    assert run_project(paper)["exit_code"] == 0
    return paper


@pytest.fixture
def editor(complete, tmp_path):
    paper = tmp_path / "paper"
    shutil.copytree(complete, paper)
    server = workspace.ProjectServer(paper)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(10)


def request(server, path, payload=None, *, token=True, headers=None):
    root = f"http://127.0.0.1:{server.server_address[1]}"
    headers = dict(headers or {})
    if token:
        headers["X-Preview-Token"] = server.state.token
    if isinstance(payload, dict):
        payload = json.dumps(payload).encode()
    call = urllib.request.Request(root + path, data=payload, headers=headers)
    try:
        response = urllib.request.urlopen(call, timeout=40)
    except urllib.error.HTTPError as problem:
        response = problem
    with response:
        return response.code, response.read(), dict(response.headers)


def get(server, path):
    code, raw, _ = request(server, path)
    assert code == 200, raw
    return json.loads(raw)


def post(server, path, payload, expected=200):
    code, raw, _ = request(server, path, payload)
    assert code == expected, raw
    return json.loads(raw)


def finished(server):
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        job = get(server, "/api/job")
        if job["phase"] != "running":
            return job
        time.sleep(0.025)
    raise AssertionError("actual bounded audit did not complete")


def test_loopback_session_origin_and_no_raw_dataset_routes(editor):
    assert request(editor, "/", token=False)[0] == 200
    for name in ("project.js", "project.css", "controls.js", "app.css"):
        assert request(editor, "/" + name, token=False)[0] == 200
    assert request(editor, "/api/state", token=False)[0] == 403
    assert request(editor, "/api/run", {}, token=False)[0] == 403
    assert request(editor, "/", headers={"Host": "attacker.example"})[0] == 403
    assert request(editor, "/api/state", headers={"Origin": "https://attacker.example"})[0] == 403
    assert request(editor, "/results.csv")[0] == 404
    assert request(editor, "/api/artifact?event=../../outside&figure=x&index=0")[0] == 400
    assert request(editor, "/api/run", b"[]")[0] == 400
    assert (
        request(editor, "/api/run", b"{}", headers={"Content-Length": str(21 * 1024 * 1024)})[0]
        == 400
    )
    info = get(editor, "/api/info")
    assert len(info["schema"]["oneOf"]) == 21
    assert "size" in info["shared_schema"]["properties"]["output"]["properties"]


def test_read_only_grouped_review_requires_session_and_retains_actual_science(editor):
    assert request(editor, "/api/review", token=False)[0] == 403
    before = get(editor, "/api/state")
    result = get(editor, "/api/review")
    assert result["current_revision"] == before["revision"]
    training = next(r for r in result["figures"] if r["id"] == "training")
    assert training["groups"]["claims"]["items"][0]["verdict"] == "holds"
    assert training["groups"]["legibility"]["inspection"]["available"]
    assert training["groups"]["reproduction"]["saved_exports_verified"]
    assert get(editor, "/api/state") == before
    assert request(editor, "/api/review?event=../../outside")[0] == 400


def test_actual_shared_policy_async_run_history_and_export_retrieval(editor):
    state = get(editor, "/api/state")
    assert state["status"] == "inputs_match_last_run" and len(state["figures"]) == 2
    post(
        editor,
        "/api/shared",
        {
            "shared": {"output": {"size": "double_column", "dpi": 144}},
            "expected_revision": state["revision"],
        },
    )
    state = get(editor, "/api/state")
    assert state["status"] == "needs_audit"
    post(editor, "/api/run", {"expected_revision": state["revision"]}, expected=202)
    job = finished(editor)
    assert job["phase"] == "complete" and job["result"]["exit_code"] == 0
    state = get(editor, "/api/state")
    assert state["status"] == "inputs_match_last_run" and len(state["history"]) == 3
    event = get(editor, "/api/event?id=" + job["result"]["id"])
    figure = event["result"]["audit"]["figures"][0]
    assert figure["report"]["spec"]["output"]["size"] == "double_column"
    index, output = next(
        (i, item) for i, item in enumerate(figure["outputs"]) if item["format"] == "png"
    )
    code, raw, headers = request(
        editor, f"/api/artifact?event={event['id']}&figure=training&index={index}"
    )
    assert code == 200 and hashlib.sha256(raw).hexdigest() == output["sha256"]
    assert headers["Content-Disposition"].startswith("attachment;")
    code, image, headers = request(editor, f"/api/preview?event={event['id']}&figure=training")
    assert code == 200 and image.startswith(b"\x89PNG")
    assert headers["Referrer-Policy"] == "no-referrer"
    source = get(editor, f"/api/saved-source?event={event['id']}&figure=training")
    assert source["context"] == "Source used by this audit"
    assert json.loads(source["text"])["output"].get("size") != "double_column"


def test_definition_and_manifest_edits_retain_historical_sources_and_data(editor):
    state = get(editor, "/api/state")
    old = state["history"][0]["id"]
    definition = get(editor, "/api/figure?id=training")
    data = (editor.state.source.parent.parent / "results.csv").read_bytes()
    value = json.loads(definition["text"])
    value["title"] = "Literal <img src=x onerror=alert(1)> title"
    post(
        editor,
        "/api/definition",
        {"id": "training", "spec": value, "expected_revision": definition["revision"]},
    )
    assert json.loads(get(editor, "/api/figure?id=training")["text"])["title"] == value["title"]
    assert get(editor, "/api/state")["status"] == "needs_audit"
    assert (
        json.loads(get(editor, f"/api/saved-source?event={old}&figure=training")["text"]).get(
            "title"
        )
        != value["title"]
    )
    definition = get(editor, "/api/figure?id=training")
    duplicate = {**definition["clone"], "id": "new-figure"}
    post(
        editor,
        "/api/entry",
        {
            "id": "new-figure",
            "entry": duplicate,
            "mode": "add",
            "expected_revision": definition["revision"],
        },
    )
    state = get(editor, "/api/state")
    assert len(state["figures"]) == 3
    post(
        editor,
        "/api/entry",
        {"id": "new-figure", "mode": "remove", "expected_revision": state["revision"]},
    )
    assert len(get(editor, "/api/state")["figures"]) == 2
    assert (editor.state.source.parent.parent / "results.csv").read_bytes() == data
    assert project_history(editor.state.source)["integrity"] == "verified"


def test_stale_browser_write_preserves_external_edits(editor):
    definition = get(editor, "/api/figure?id=training")
    source = editor.state.source.parent.parent / "training.figure.json"
    original = source.read_bytes() + b"\n"
    source.write_bytes(original)
    rejected = post(
        editor,
        "/api/definition",
        {
            "id": "training",
            "spec": json.loads(definition["text"]),
            "expected_revision": definition["revision"],
        },
        expected=400,
    )
    assert "changed since review" in rejected["error"] and source.read_bytes() == original
    assert len(get(editor, "/api/state")["history"]) == 1


def test_reading_a_script_binding_never_imports_it_and_source_stays_read_only(editor):
    paper = editor.state.source.parent.parent
    marker = paper / "executed.txt"
    script = paper / "authored.py"
    raw = f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n"
    script.write_text(raw)
    (paper / "graphunslopify.json").write_text(
        json.dumps({"schema_version": 1, "figures": [{"id": "script", "script": "authored.py"}]})
    )
    definition = get(editor, "/api/figure?id=script")
    assert definition["source_type"] == "script" and not definition["editable"]
    assert not marker.exists()
    assert get(editor, "/api/state")["figures"][0]["input_coverage"] == "unknown_script_inputs"
    post(
        editor,
        "/api/definition",
        {"id": "script", "spec": {}, "expected_revision": definition["revision"]},
        expected=400,
    )
    assert script.read_text() == raw and not marker.exists()


def test_one_actual_worker_refuses_overlapping_runs_and_definition_writes(editor, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    original = workspace.run_project

    def held(*args, **kwargs):
        entered.set()
        assert release.wait(20)
        return original(*args, **kwargs)

    monkeypatch.setattr(workspace, "run_project", held)
    state = get(editor, "/api/state")
    try:
        post(editor, "/api/run", {"expected_revision": state["revision"]}, expected=202)
        assert entered.wait(5)
        post(editor, "/api/run", {"expected_revision": state["revision"]}, expected=400)
        post(
            editor,
            "/api/shared",
            {"shared": {}, "expected_revision": state["revision"]},
            expected=400,
        )
        assert get(editor, "/api/job")["phase"] == "running"
    finally:
        release.set()
    assert finished(editor)["result"]["exit_code"] == 0


def test_strict_failure_recovery_and_comparison_use_verified_original_exports(editor):
    paper = editor.state.source.parent.parent
    path = paper / "training.figure.json"
    original = path.read_bytes()
    wrong = json.loads(original)
    wrong["claims"][0].update(subject="base", reference="ours")
    path.write_text(json.dumps(wrong))
    state = get(editor, "/api/state")
    post(editor, "/api/run", {"expected_revision": state["revision"]}, expected=202)
    job = finished(editor)
    assert job["result"]["status"] == "failed" and job["result"]["exit_code"] == 2
    event = get(editor, "/api/event?id=" + job["result"]["id"])
    root = editor.state.audit_root(event)
    for image in root.rglob("comparison/images/*.png"):
        image.write_bytes(b"damaged derived cache")
    comparison = get(editor, f"/api/comparison?event={event['id']}&figure=training")
    assert comparison["before"]["status"] == comparison["after"]["status"] == "available"
    assert any(item["field"] == "claims" for item in comparison["changes"])
    figure = event["result"]["audit"]["figures"][0]
    image = next(item for item in figure["outputs"] if item["format"] == "png")
    (root / image["path"]).write_bytes(b"damaged actual export")
    assert request(editor, f"/api/preview?event={event['id']}&figure=training")[0] == 400
    comparison = get(editor, f"/api/comparison?event={event['id']}&figure=training")
    assert comparison["after"]["status"] == "unavailable" and comparison["metrics"] is None
    path.write_bytes(original)
    post(
        editor,
        "/api/run",
        {"expected_revision": get(editor, "/api/state")["revision"], "baseline": None},
        expected=202,
    )
    assert finished(editor)["result"]["exit_code"] == 0


@pytest.mark.parametrize("format", ["svg", "pdf"])
def test_actual_non_png_export_has_a_verified_static_preview(editor, format):
    path = editor.state.source.parent.parent / "training.figure.json"
    value = json.loads(path.read_text())
    value["output"]["formats"] = [format]
    path.write_text(json.dumps(value))
    post(
        editor,
        "/api/run",
        {"expected_revision": get(editor, "/api/state")["revision"], "baseline": None},
        expected=202,
    )
    job = finished(editor)
    assert job["result"]["exit_code"] == 0
    code, raw, headers = request(
        editor, f"/api/preview?event={job['result']['id']}&figure=training"
    )
    assert code == 200
    assert (
        (b"<svg" in raw and headers["Content-Type"] == "image/svg+xml")
        if format == "svg"
        else raw.startswith(b"\x89PNG")
    )


def test_changed_owner_and_damaged_receipt_cannot_serve_history_as_verified(editor):
    event = get(editor, "/api/state")["history"][0]
    receipt = editor.state.source.parent / "history" / event["id"] / "receipt.json"
    receipt.write_text("{}")
    assert request(editor, "/api/event?id=" + event["id"])[0] == 400
    assert get(editor, "/api/state")["status"] == "needs_audit"
    owner = editor.state.source.parent / "owner.json"
    value = json.loads(owner.read_text())
    value["project_id"] = "a" * 32
    owner.write_text(json.dumps(value))
    assert request(editor, "/api/state")[0] == 400
