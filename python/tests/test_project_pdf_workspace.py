"""Real PDF upload/job/asset lifecycle in a genuine no-native paper server."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from urllib.parse import quote, urlencode

import pytest
from test_project_preview import finished, get, post, request

from graphunslopify import project_preview as workspace
from graphunslopify.project import initialize_project

PDF = Path(__file__).resolve().parents[2] / "examples/baseline/01-training-curve.pdf"


@pytest.fixture
def editor(tmp_path):
    initialize_project(tmp_path, review_only=True)
    server = workspace.ProjectServer(tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(10)


def upload(editor, *, token=True):
    state = get(editor, "/api/state")
    query = urlencode(
        {
            "id": "external",
            "expected_revision": state["inspection_revision"],
            "pages": "1",
            "dpi": "72",
        }
    )
    return request(
        editor,
        "/api/pdf-upload?" + query,
        PDF.read_bytes(),
        token=token,
        headers={"Content-Type": "application/pdf", "X-File-Name": quote("Paper ü.pdf")},
    )


def test_real_uploaded_pdf_shared_job_and_verified_page_asset(editor):
    state = get(editor, "/api/state")
    assert state["status"] == "review_only" and not state["figures"] and not state["inspections"]
    assert request(editor, "/api/run", {"expected_revision": state["revision"]})[0] == 400
    code, raw, _ = upload(editor)
    assert code == 202, raw
    job = finished(editor)
    assert job["kind"] == "inspection" and job["result"]["status"] == "incomplete"
    assert job["result"]["exit_code"] == 2
    state = get(editor, "/api/state")
    assert state["status"] == "review_only" and not state["figures"]
    assert state["inspections"][0]["name"] == "Paper ü.pdf"
    review = get(editor, "/api/review")
    row = review["figures"][0]
    assert row["source_type"] == "pdf" and row["inspection"]["science_status"] == "untested"
    index = next(
        i for i, asset in enumerate(row["inspection"]["assets"]) if asset["path"].endswith(".png")
    )
    path = "/api/pdf-asset?" + urlencode(
        {"event": job["result"]["id"], "index": index, "view": "1"}
    )
    code, data, headers = request(editor, path)
    assert code == 200 and data.startswith(b"\x89PNG") and headers["Content-Type"] == "image/png"
    assert request(editor, path, token=False)[0] == 403
    assert request(editor, "/api/pdf-asset?event=../../outside&index=0")[0] == 400
    assert request(editor, "/api/pdf-asset?event=" + job["result"]["id"] + "&index=999")[0] == 400
    assert request(editor, "/sources/source.pdf")[0] == 404
    post(
        editor,
        "/api/pdf-inspection",
        {
            "id": "external",
            "expected_revision": state["inspection_revision"],
            "pages": [1],
            "dpi": 72,
        },
        expected=202,
    )
    assert finished(editor)["result"]["exit_code"] == 2


def test_upload_auth_origin_and_actual_bounds_before_source_write(editor):
    assert upload(editor, token=False)[0] == 403
    assert (
        request(
            editor, "/api/pdf-upload", b"%PDF-bad", headers={"Origin": "https://attacker.example"}
        )[0]
        == 403
    )
    assert (
        request(
            editor,
            "/api/pdf-upload",
            b"bad",
            headers={"Content-Type": "application/pdf", "X-File-Name": "bad.pdf"},
        )[0]
        == 400
    )
    assert (
        request(editor, "/api/pdf-upload", b"%PDF-bad", headers={"Content-Type": "text/plain"})[0]
        == 400
    )
    assert (
        request(editor, "/api/pdf-upload", b"x", headers={"Content-Length": str(51 * 1024 * 1024)})[
            0
        ]
        == 400
    )
    assert not get(editor, "/api/state")["history"]
    assert not (editor.state.source.parent / "sources").exists()


def test_single_job_ownership_rejects_upload_and_style_during_active_inspection(
    editor, monkeypatch
):
    from graphunslopify import project_inspections as inspections

    entered, release = threading.Event(), threading.Event()
    actual = inspections._run

    def held(*args, **kwargs):
        entered.set()
        if not release.wait(10):
            raise RuntimeError("Test did not release the actual PDF worker")
        return actual(*args, **kwargs)

    monkeypatch.setattr(inspections, "_run", held)
    try:
        assert upload(editor)[0] == 202
        assert entered.wait(10)
        assert get(editor, "/api/job")["phase"] == "running"
        code, raw, _ = upload(editor)
        assert code == 400 and "already running" in json.loads(raw)["error"]
        state = get(editor, "/api/state")
        assert (
            request(editor, "/api/shared", {"shared": {}, "expected_revision": state["revision"]})[
                0
            ]
            == 400
        )
        assert len(list((editor.state.source.parent / "sources").rglob("*.pdf"))) == 1
    finally:
        release.set()
    assert finished(editor)["result"]["status"] == "incomplete"
    assert len(get(editor, "/api/state")["history"]) == 1
