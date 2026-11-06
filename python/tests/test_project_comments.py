"""Versioned reviewer threads on actual saved paper PNGs."""

import hashlib
from pathlib import Path
from urllib.parse import urlencode

from test_project_changes_http import request
from test_project_changes_http import server as server  # noqa: PLC0414

from graphunslopify.project import project_history, run_project
from graphunslopify.project_comments import read_figure_comments
from graphunslopify.project_preview import ProjectState

ROUTE = "/api/figure-comments"


def query(event, figure="training"):
    return ROUTE + "?" + urlencode({"event": event["id"], "figure": figure})


def change(server, snapshot, operation, *, expected=200, **fields):
    anchor = snapshot["anchor"]
    return request(
        server,
        ROUTE,
        {
            "event": anchor["event"],
            "figure": anchor["figure"],
            "anchor_key": snapshot["anchor_key"],
            "expected_revision": snapshot["revision"],
            "operation": operation,
            "author": "Reviewer A",
            **fields,
        },
        expected=expected,
    )


def test_comments_follow_exact_saved_renders_and_preserve_audit_bytes(server):
    _, paper = server
    first = run_project(paper, baseline=None)
    assert first["exit_code"] == 0
    history = Path(first["directory"])
    saved = {p.relative_to(history): p.read_bytes() for p in history.rglob("*") if p.is_file()}
    config = paper / "graphunslopify-project/project.json"
    original = config.read_bytes()
    start = request(server, query(first))
    assert not start["threads"]
    anchor = start["anchor"]
    figure = first["audit"]["figures"][0]
    output = figure["outputs"][anchor["index"]]
    assert anchor["figure"] == figure["id"] and output["format"] == "png"
    assert anchor["sha256"] == hashlib.sha256(saved[Path("audit") / output["path"]]).hexdigest()
    bad = change(server, start, "create", x=anchor["width"], y=0, body="outside", expected=400)
    assert "inside" in bad["error"]
    assert not config.with_name("figure-comments.json").exists()

    created = change(server, start, "create", x=0, y=0, body="<b>Review the baseline.</b>")
    (thread,) = created["threads"]
    assert thread["body"] == "<b>Review the baseline.</b>"
    assert (
        "Reload"
        in change(server, start, "create", x=0, y=0, body="duplicate", expected=400)["error"]
    )
    replied = change(server, created, "reply", thread=thread["id"], body="Checking this.")
    resolved = change(server, replied, "resolve", thread=thread["id"])
    change(server, resolved, "reply", thread=thread["id"], body="closed", expected=400)
    reopened = change(server, resolved, "reopen", thread=thread["id"])
    (retained,) = reopened["threads"]
    assert retained["replies"][0]["body"] == "Checking this."
    assert [r["resolved"] for r in retained["status_history"]] == [True, False]
    assert config.read_bytes() == original
    assert {
        p.relative_to(history): p.read_bytes() for p in history.rglob("*") if p.is_file()
    } == saved
    assert project_history(paper)["integrity"] == "verified"
    assert read_figure_comments(ProjectState(paper), first["id"], "training") == reopened

    second = run_project(paper, baseline=None)
    latest = request(server, query(second))
    assert latest["anchor"]["event"] != anchor["event"] and latest["threads"] == []
    assert latest["anchor_key"] != start["anchor_key"]
    assert request(server, query(first)) == reopened


def test_comments_refuse_foreign_requests_and_changed_exports(server):
    _, paper = server
    first = run_project(paper, baseline=None)
    path = query(first)
    request(server, path, expected=403, token=False)
    request(
        server,
        ROUTE,
        {"operation": "create"},
        expected=403,
        headers={"Origin": "https://outside.invalid"},
    )
    start = request(server, path)
    output = first["audit"]["figures"][0]["outputs"][start["anchor"]["index"]]
    png = Path(first["directory"]) / "audit" / output["path"]
    png.write_bytes(png.read_bytes() + b"modified")
    request(server, path, expected=400)
    change(server, start, "create", x=0, y=0, body="stale export", expected=400)
    assert not (paper / "graphunslopify-project/figure-comments.json").exists()
