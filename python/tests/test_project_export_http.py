"""Real session-protected ZIP responses, owned workers and exclusive CLI destinations."""

import io
import json
import shutil
import threading
import zipfile
from pathlib import Path

import pytest
from test_project_preview import finished, get, request

from graphunslopify import project as model
from graphunslopify import project_preview as workspace
from graphunslopify.cli import main
from graphunslopify.project_review import project_review

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def editor(tmp_path):
    shutil.copytree(ROOT / "examples/paper", tmp_path, dirs_exist_ok=True)
    model.initialize_project(tmp_path)
    assert model.run_project(tmp_path, baseline=None)["exit_code"] == 0
    server = workspace.ProjectServer(tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, tmp_path
    finally:
        server.shutdown()
        server.server_close()
        thread.join(10)


def test_actual_zip_http_session_origin_and_stale_review_guards(editor):
    server, root = editor
    review = get(server, "/api/review")
    body = {"expected_revision": review["evidence_revision"]}
    before = model.project_history(root)
    assert request(server, "/api/review-export", body, token=False)[0] == 403
    assert (
        request(server, "/api/review-export", body, headers={"Origin": "https://other.example"})[0]
        == 403
    )
    assert request(server, "/api/review-export", {})[0] == 400
    code, raw, headers = request(server, "/api/review-export", body)
    assert code == 200 and headers["Content-Type"] == "application/zip"
    assert "attachment" in headers["Content-Disposition"]
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        report = json.loads(z.read("review.json"))
        assert report["review"]["evidence_revision"] == review["evidence_revision"]
        assert not report["science_reexecuted"] and report["review"]["native_run"]["exit_code"] == 0
    assert model.project_history(root) == before
    data = root / "results.csv"
    data.write_bytes(data.read_bytes() + b"\n")
    assert request(server, "/api/review-export", body)[0] == 400
    assert request(server, "/api/review-export", {**body, "event": "../../outside"})[0] == 400


def test_actual_owned_audit_blocks_export_until_the_worker_finishes(editor, monkeypatch):
    server, root = editor
    review = get(server, "/api/review")
    entered, release = threading.Event(), threading.Event()
    actual = model.audit

    def held(*args, **kwargs):
        entered.set()
        assert release.wait(20)
        return actual(*args, **kwargs)

    monkeypatch.setattr(model, "audit", held)
    body = {"expected_revision": get(server, "/api/state")["revision"]}
    assert request(server, "/api/run", body)[0] == 202
    assert entered.wait(10)
    try:
        assert (
            request(
                server, "/api/review-export", {"expected_revision": review["evidence_revision"]}
            )[0]
            == 400
        )
        assert get(server, "/api/job")["phase"] == "running"
    finally:
        release.set()
    assert finished(server)["result"]["exit_code"] == 0
    assert model.project_history(root)["integrity"] == "verified"


def test_cli_packet_exclusive_destination_and_saved_rejection_are_separate(
    editor, tmp_path, capsys
):
    _, root = editor
    target = tmp_path / "actual review.zip"
    before = model.project_history(root)
    assert main(["project-export", str(root), "--output", str(target)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "exported" and result["native_audit_exit"] == 0
    assert result["science_reexecuted"] is False and result["bytes"] == target.stat().st_size
    original = target.read_bytes()
    assert main(["project-export", str(root), "--output", str(target)]) == 2
    capsys.readouterr()
    assert target.read_bytes() == original and model.project_history(root) == before
    protected = root / "graphunslopify-project/history/new.zip"
    assert main(["project-export", str(root), "--output", str(protected)]) == 2
    capsys.readouterr()
    assert not protected.exists()
    review = project_review(root)
    (root / "results.csv").write_bytes((root / "results.csv").read_bytes() + b"\n")
    stale = tmp_path / "stale.zip"
    assert (
        main(
            [
                "project-export",
                str(root),
                "--output",
                str(stale),
                "--expected-revision",
                review["evidence_revision"],
            ]
        )
        == 2
    )
    capsys.readouterr()
    assert not stale.exists()
