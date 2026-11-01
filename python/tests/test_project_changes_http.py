"""Actual CLI/loopback shared proposals, guarded writes and real job exclusion."""

import json
import shutil
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from graphunslopify import project_preview as workspace
from graphunslopify.cli import main
from graphunslopify.project import initialize_project, project_history, project_status

ROOT = Path(__file__).resolve().parents[2]
SHARED = {"output": {"dpi": 144, "size": "double_column"}}


@pytest.fixture
def server(tmp_path):
    paper = tmp_path / "paper"
    shutil.copytree(ROOT / "examples/paper", paper)
    initialize_project(paper)
    instance = workspace.ProjectServer(paper)
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        yield instance, paper
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join(10)


def request(server, path, payload=None, *, expected=200, token=True, headers=None):
    instance, _ = server
    data = None if payload is None else json.dumps(payload).encode()
    call = urllib.request.Request(
        f"http://127.0.0.1:{instance.server_address[1]}" + path,
        data=data,
        headers={**({"X-Preview-Token": instance.state.token} if token else {}), **(headers or {})},
    )
    try:
        response = urllib.request.urlopen(call, timeout=60)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        raw = response.read()
        assert response.code == expected, raw
        return json.loads(raw)


def test_actual_review_apply_and_undo_http_keep_original_data_and_history(server):
    _instance, paper = server
    config = paper / "graphunslopify-project/project.json"
    raw = config.read_bytes()
    files = {p.name: p.read_bytes() for p in paper.iterdir() if p.is_file()}
    state = request(server, "/api/state")
    plan = request(
        server, "/api/shared-review", {"shared": SHARED, "expected_revision": state["revision"]}
    )
    assert len(plan["figures"]) == 2 and plan["can_apply"] and not project_history(paper)["events"]
    result = request(
        server,
        "/api/shared-apply",
        {
            "shared": SHARED,
            "expected_revision": state["revision"],
            "proposal_token": plan["proposal_token"],
        },
    )
    assert result["status"] == "settings_saved"
    state = request(server, "/api/state")
    assert state["history"][0]["shared_change"] and state["shared"] == SHARED
    undo = request(
        server,
        "/api/shared-review",
        {"undo_event": result["id"], "expected_revision": state["revision"]},
    )
    restored = request(
        server,
        "/api/shared-apply",
        {
            "undo_event": result["id"],
            "expected_revision": state["revision"],
            "proposal_token": undo["proposal_token"],
        },
    )
    assert restored["status"] == "settings_saved" and config.read_bytes() == raw
    assert {p.name: p.read_bytes() for p in paper.iterdir() if p.is_file()} == files
    assert request(server, "/api/state")["history"][0]["undo_of"] == result["id"]


@pytest.mark.parametrize("path", ["/api/shared-review", "/api/shared-apply"])
def test_both_routes_require_the_session_and_origin_before_changes(server, path):
    _instance, paper = server
    body = {"shared": SHARED, "expected_revision": project_status(paper)["revision"]}
    request(server, path, body, expected=403, token=False)
    request(server, path, body, expected=403, headers={"Origin": "https://outside.invalid"})
    assert not project_history(paper)["events"] and project_status(paper)["shared"] == {}


def test_apply_without_review_with_changed_payload_and_with_stale_data_never_writes(server):
    _, paper = server
    state = request(server, "/api/state")
    body = {"shared": SHARED, "expected_revision": state["revision"]}
    request(server, "/api/shared-apply", body, expected=400)
    plan = request(server, "/api/shared-review", body)
    request(
        server,
        "/api/shared-apply",
        {**body, "shared": {"output": {"dpi": 145}}, "proposal_token": plan["proposal_token"]},
        expected=400,
    )
    data = paper / "results.csv"
    data.write_bytes(data.read_bytes() + b"\n")
    request(
        server,
        "/api/shared-apply",
        {
            **body,
            "expected_revision": project_status(paper)["revision"],
            "proposal_token": plan["proposal_token"],
        },
        expected=400,
    )
    assert project_status(paper)["shared"] == {} and not project_history(paper)["events"]


def test_read_and_apply_refuse_while_a_real_owned_audit_worker_is_active(server, monkeypatch):
    _instance, paper = server
    state = request(server, "/api/state")
    body = {"shared": SHARED, "expected_revision": state["revision"]}
    plan = request(server, "/api/shared-review", body)
    entered = threading.Event()
    release = threading.Event()
    original = workspace.run_project

    def actual_held_run(*args, **kwargs):
        entered.set()
        assert release.wait(30)
        return original(*args, **kwargs)

    monkeypatch.setattr(workspace, "run_project", actual_held_run)
    try:
        request(
            server,
            "/api/run",
            {"expected_revision": state["revision"], "baseline": None},
            expected=202,
        )
        assert entered.wait(10)
        request(server, "/api/shared-review", body, expected=400)
        request(
            server,
            "/api/shared-apply",
            {**body, "proposal_token": plan["proposal_token"]},
            expected=400,
        )
    finally:
        release.set()
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        job = request(server, "/api/job")
        if job["phase"] != "running":
            break
        time.sleep(0.025)
    assert job["phase"] == "complete" and job["result"]["exit_code"] == 0
    assert len(project_history(paper)["events"]) == 1 and project_status(paper)["shared"] == {}


def test_actual_cli_review_apply_and_undo_use_the_same_proposal_contract(tmp_path, capsys):
    paper = tmp_path / "paper"
    shutil.copytree(ROOT / "examples/paper", paper)
    initialize_project(paper)
    settings = tmp_path / "shared.json"
    settings.write_text(json.dumps(SHARED))
    token = project_status(paper)["revision"]
    assert (
        main(
            [
                "project-review-shared",
                str(paper),
                "--settings",
                str(settings),
                "--expected-revision",
                token,
            ]
        )
        == 0
    )
    plan = json.loads(capsys.readouterr().out)
    assert plan["can_apply"]
    assert (
        main(
            [
                "project-apply-shared",
                str(paper),
                "--settings",
                str(settings),
                "--expected-revision",
                token,
                "--proposal-token",
                plan["proposal_token"],
            ]
        )
        == 0
    )
    saved = json.loads(capsys.readouterr().out)
    current = project_status(paper)["revision"]
    assert (
        main(
            [
                "project-review-shared",
                str(paper),
                "--undo",
                saved["id"],
                "--expected-revision",
                current,
            ]
        )
        == 0
    )
    undo = json.loads(capsys.readouterr().out)
    assert (
        main(
            [
                "project-apply-shared",
                str(paper),
                "--undo",
                saved["id"],
                "--expected-revision",
                current,
                "--proposal-token",
                undo["proposal_token"],
            ]
        )
        == 0
    )
    reverted = json.loads(capsys.readouterr().out)
    assert reverted["undo_of"] == saved["id"]
    assert project_status(paper)["shared"] == {}
