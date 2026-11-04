"""Actual saved evidence and loopback reviewer lifecycle; no model-quality claim."""

from __future__ import annotations

import json
import threading
import time

import pytest
from test_project_preview import get, post, request
from test_review_agent import inventory

from graphunslopify.drafts import _encoded
from graphunslopify.project_preview import ProjectServer
from graphunslopify.review_agent import InvalidReview, restore_plan

pytest_plugins = ("test_review_agent",)


@pytest.fixture
def paper_server(paper):
    with ProjectServer(paper) as http:
        thread = threading.Thread(target=http.serve_forever)
        thread.start()
        try:
            yield http
        finally:
            http.shutdown()
            thread.join(10)
            assert not thread.is_alive()


def configure(paper_server, server):
    return post(
        paper_server,
        "/api/reviewer/provider",
        {"endpoint": server.endpoint, "model": "controlled-review", "api_key": "KEY_MARKER"},
    )


def selection(paper_server, generation=1, **changes):
    collection = get(paper_server, "/api/review")
    return {
        "client": "review-ui",
        "generation": generation,
        "expected_revision": collection["evidence_revision"],
        "figures": ["training"],
        "question": "What needs author review before submission?",
        **changes,
    }


def disclose(paper_server, generation=1, **changes):
    payload = selection(paper_server, generation, **changes)
    return post(paper_server, "/api/reviewer/disclose", payload)


def identity(disclosure):
    return {
        "client": "review-ui",
        "generation": disclosure["generation"],
        "review_id": disclosure["review_id"],
    }


def start(paper_server, disclosure):
    return post(
        paper_server,
        "/api/reviewer/start",
        {**identity(disclosure), "consent": True, "consent_sha256": disclosure["consent_sha256"]},
        202,
    )


def wait(paper_server, disclosure):
    worker = paper_server.state.reviewer.records[disclosure["review_id"]]["worker"]
    worker.join(15)
    assert not worker.is_alive(), "Reviewer did not finish its bounded local test"
    return post(paper_server, "/api/reviewer/status", identity(disclosure))


def download(paper_server, disclosure, which, expected=200):
    code, raw, headers = request(
        paper_server,
        "/api/reviewer/download",
        {**identity(disclosure), "which": which},
    )
    assert code == expected, raw
    if expected == 200:
        assert "attachment" in headers["Content-Disposition"]
        assert headers["Content-Type"].startswith("application/json")
    return json.loads(raw)


def test_actual_paper_http_disclosure_consent_result_and_replayable_download(
    paper_server, server, paper
):
    before = inventory(paper)
    public = configure(paper_server, server)
    assert public["configured"] and public["authorization_configured"]
    assert "KEY_MARKER" not in json.dumps(public)
    assert get(paper_server, "/api/reviewer/provider") == public
    disclosure = disclose(paper_server)
    assert disclosure["source_kind"] == "paper-project"
    assert not server.calls
    document = download(paper_server, disclosure, "request")
    restored = restore_plan(document, paper, api_key="KEY_MARKER")
    assert restored.disclosure()["request"] == disclosure["request"]
    running = start(paper_server, disclosure)
    assert running["phase"] == "running" and running["result"] is None
    complete = wait(paper_server, disclosure)
    assert complete["phase"] == "completed"
    result = download(paper_server, disclosure, "result")
    assert result == complete["result"]
    assert result["applied"] is False and result["scientific_acceptance"] == "not_established"
    assert result["qualitative"]["citations_validate_references_only"]
    assert result["deterministic_evidence"]["figures"][0]["key"] == "training"
    assert len(server.calls) == 1
    raw, headers = server.calls[0]
    assert raw == _encoded(disclosure["request"])
    assert headers["Authorization"] == "Bearer KEY_MARKER"
    for private in ("KEY_MARKER", "NEVER_SEND_ROOT", "NEVER_SEND_OBSERVATION"):
        assert private.encode() not in raw
        assert private not in json.dumps(document) + json.dumps(result)
    assert inventory(paper) == before
    repeated = post(
        paper_server,
        "/api/reviewer/start",
        {**identity(disclosure), "consent": True, "consent_sha256": disclosure["consent_sha256"]},
        400,
    )
    assert "attempted" in repeated["error"] and len(server.calls) == 1


@pytest.mark.parametrize("change", [{"consent": False}, {"consent_sha256": "0" * 64}])
def test_exact_explicit_consent_precedes_any_http(paper_server, server, change):
    configure(paper_server, server)
    disclosure = disclose(paper_server)
    post(
        paper_server,
        "/api/reviewer/start",
        {
            **identity(disclosure),
            "consent": True,
            "consent_sha256": disclosure["consent_sha256"],
            **change,
        },
        400,
    )
    assert not server.calls
    assert post(paper_server, "/api/reviewer/status", identity(disclosure))["phase"] == "disclosed"


def test_http_auth_origin_host_body_bounds_and_unknown_controls(paper_server, server):
    payload = {"enabled": False}
    assert request(paper_server, "/api/reviewer/provider", payload, token=False)[0] == 403
    for headers in ({"Origin": "https://unrelated.invalid"}, {"Host": "unrelated.invalid"}):
        assert request(paper_server, "/api/reviewer/provider", payload, headers=headers)[0] == 403
    assert request(paper_server, "/api/reviewer/provider", token=False)[0] == 403
    post(paper_server, "/api/reviewer/provider", {"enabled": False, "secret": "x"}, 400)
    post(paper_server, "/api/reviewer/provider", {"api_key": "x" * 65536}, 400)
    post(paper_server, "/api/reviewer/unknown", {}, 404)
    configure(paper_server, server)
    payload = selection(paper_server, report={"status": "passed"})
    post(paper_server, "/api/reviewer/disclose", payload, 400)
    assert not server.calls


@pytest.mark.parametrize(
    "change",
    [
        {"generation": True},
        {"client": []},
        {"figures": []},
        {"figures": ["invented"]},
        {"expected_revision": "0" * 64},
        {"question": ""},
        {"structured_output": "yes"},
    ],
)
def test_unowned_or_malformed_context_refuses_before_inference(paper_server, server, change):
    configure(paper_server, server)
    post(paper_server, "/api/reviewer/disclose", selection(paper_server, **change), 400)
    assert not server.calls


def test_invalid_reply_clears_previous_success_and_never_exports_raw_reply(paper_server, server):
    configure(paper_server, server)
    first = disclose(paper_server)
    start(paper_server, first)
    assert wait(paper_server, first)["phase"] == "completed"
    server.text = "INVALID_PRIVATE_PROVIDER_REPLY"
    second = disclose(paper_server, 2)
    start(paper_server, second)
    failed = wait(paper_server, second)
    assert failed["phase"] == "failed" and failed["result"] is None
    assert "invalid review" in failed["error"]
    assert "INVALID_PRIVATE_PROVIDER_REPLY" not in json.dumps(failed)
    download(paper_server, second, "result", 400)
    post(paper_server, "/api/reviewer/status", identity(first), 400)
    assert len(server.calls) == 2


@pytest.mark.parametrize("when", ["before", "during", "after"])
def test_actual_data_change_never_returns_or_downloads_stale_advice(
    paper_server, server, paper, when
):
    configure(paper_server, server)
    disclosure = disclose(paper_server)
    source = paper / "NEVER_SEND_FILENAME.csv"

    def change():
        source.write_bytes(source.read_bytes() + b"\n")

    if when == "before":
        change()
    elif when == "during":
        server.on_request = change
    start(paper_server, disclosure)
    complete = wait(paper_server, disclosure)
    if when == "after":
        assert complete["phase"] == "completed"
        change()
        post(paper_server, "/api/reviewer/status", identity(disclosure), 400)
    else:
        assert complete["phase"] == "failed" and complete["result"] is None
    download(paper_server, disclosure, "result", 400)
    assert len(server.calls) == (0 if when == "before" else 1)
    assert paper_server.state.reviewer.records[disclosure["review_id"]]["result"] is None


@pytest.mark.parametrize("action", ["cancel", "provider", "close"])
def test_owned_inflight_cancellation_provider_change_and_close_discard_reply(
    paper_server, server, action
):
    configure(paper_server, server)
    disclosure = disclose(paper_server)
    received, release = threading.Event(), threading.Event()

    def hold():
        received.set()
        release.wait(15)

    server.on_request = hold
    try:
        start(paper_server, disclosure)
        assert received.wait(10)
        row = paper_server.state.reviewer.records[disclosure["review_id"]]
        if action == "cancel":
            post(paper_server, "/api/reviewer/cancel", identity(disclosure))
        elif action == "provider":
            post(paper_server, "/api/reviewer/provider", {"enabled": False})
        else:
            paper_server.shutdown()
            paper_server.server_close()
        row["worker"].join(10)
        assert not row["worker"].is_alive()
        assert row["result"] is None and row["phase"] == "cancelled"
        if action == "cancel":
            assert (
                post(paper_server, "/api/reviewer/status", identity(disclosure))["phase"]
                == "cancelled"
            )
        elif action == "provider":
            post(paper_server, "/api/reviewer/status", identity(disclosure), 400)
        else:
            assert paper_server.state.closing
            assert paper_server.state.reviewer.info()["closed"]
        assert len(server.calls) == 1
    finally:
        release.set()


@pytest.mark.parametrize("action", ["cancel", "provider", "close", "new-generation"])
def test_inflight_disclosure_cannot_reappear_after_context_invalidation(
    paper_server, server, action
):
    configure(paper_server, server)
    coordinator = paper_server.state.reviewer
    factory = coordinator.factory
    entered, release = threading.Event(), threading.Event()
    outcomes = []
    payload = selection(paper_server)

    def held(provider, payload):
        plan = factory(provider, payload)
        entered.set()
        assert release.wait(10)
        return plan

    def work():
        try:
            outcomes.append(coordinator.disclose(payload))
        except ValueError as problem:
            outcomes.append(problem)

    coordinator.factory = held
    worker = threading.Thread(target=work)
    worker.start()
    try:
        assert entered.wait(10)
        if action == "cancel":
            coordinator.cancel({"client": "review-ui", "generation": 1})
        elif action == "provider":
            coordinator.configure({"enabled": False})
        elif action == "close":
            coordinator.close()
        else:
            coordinator.cancel({"client": "review-ui", "generation": 2})
    finally:
        release.set()
        worker.join(10)
    assert not worker.is_alive()
    assert len(outcomes) == 1 and isinstance(outcomes[0], ValueError)
    assert not coordinator.records and not coordinator.building and not server.calls


def test_expired_plans_and_retained_clients_are_bounded(paper_server, server, monkeypatch):
    configure(paper_server, server)
    disclosure = disclose(paper_server)
    coordinator = paper_server.state.reviewer
    now = time.monotonic()
    with monkeypatch.context() as patch:
        patch.setattr("graphunslopify.review_sessions.time.monotonic", lambda: now + 601)
        with pytest.raises(ValueError, match="expired"):
            coordinator.status(identity(disclosure))
    assert not coordinator.records
    for i in range(100):
        coordinator.cancel({"client": "idle-" + str(i), "generation": 0})
    assert len(coordinator.revisions) <= 64
    assert not server.calls


def test_preparing_plans_share_the_bounded_capacity(paper_server, server):
    configure(paper_server, server)
    coordinator = paper_server.state.reviewer
    entered, release = threading.Barrier(9), threading.Event()
    failures = []

    def held(*_):
        entered.wait(10)
        assert release.wait(10)
        raise ValueError("Controlled abandoned disclosure")

    def work(index):
        try:
            coordinator.disclose({"client": str(index), "generation": 1})
        except ValueError as problem:
            failures.append(problem)

    coordinator.factory = held
    workers = [threading.Thread(target=work, args=(i,)) for i in range(8)]
    for worker in workers:
        worker.start()
    try:
        entered.wait(10)
        with pytest.raises(ValueError, match="Too many"):
            coordinator.disclose({"client": "ninth", "generation": 1})
        assert len(coordinator.building) == 8
    finally:
        release.set()
        for worker in workers:
            worker.join(10)
            assert not worker.is_alive()
    assert len(failures) == 8 and not coordinator.building and not server.calls


def test_thread_start_failure_preserves_terminal_state(paper_server, server, monkeypatch):
    configure(paper_server, server)
    disclosure = disclose(paper_server)

    def refuse(_):
        raise RuntimeError("Controlled worker start refusal")

    with monkeypatch.context() as patch:
        patch.setattr(threading.Thread, "start", refuse)
        with pytest.raises(ValueError, match="could not start"):
            paper_server.state.reviewer.start(
                {
                    **identity(disclosure),
                    "consent": True,
                    "consent_sha256": disclosure["consent_sha256"],
                }
            )
    status = post(paper_server, "/api/reviewer/status", identity(disclosure))
    assert status["phase"] == "failed" and status["result"] is None
    assert paper_server.state.reviewer.active is None and not server.calls


@pytest.mark.parametrize("change", ["busy", "owner"])
def test_real_workspace_ownership_and_active_job_are_checked_at_send(paper_server, server, change):
    configure(paper_server, server)
    disclosure = disclose(paper_server)
    if change == "busy":
        paper_server.state.job = {"phase": "running"}
    else:
        owner = paper_server.state.source.parent / "owner.json"
        value = json.loads(owner.read_text())
        value["project_id"] = "a-different-owner"
        owner.write_text(json.dumps(value))
    # Start directly so this exercises the plan's own recheck, independently of
    # the HTTP handler's initial ownership check.
    coordinator = paper_server.state.reviewer
    coordinator.start(
        {
            **identity(disclosure),
            "consent": True,
            "consent_sha256": disclosure["consent_sha256"],
        }
    )
    row = coordinator.records[disclosure["review_id"]]
    row["worker"].join(10)
    assert not row["worker"].is_alive()
    assert row["phase"] == "failed" and row["result"] is None and not server.calls


def test_real_historical_selection_uses_its_own_collection_revision(paper_server, server):
    configure(paper_server, server)
    state = get(paper_server, "/api/state")
    event = next(row["id"] for row in state["history"] if row["action"] == "run")
    collection = get(paper_server, "/api/review?event=" + event)
    disclosure = disclose(
        paper_server, event=event, expected_revision=collection["evidence_revision"]
    )
    document = download(paper_server, disclosure, "request")
    assert document["selection"]["event_id"] == event
    assert document["disclosure"]["binding"] == collection["evidence_revision"]
    assert not server.calls


@pytest.mark.parametrize(
    "problem",
    [
        ValueError("Authorization KEY_MARKER refused"),
        RuntimeError("Unexpected KEY_MARKER error"),
        InvalidReview("Bad reply", "PRIVATE_UNACCEPTED_REPLY KEY_MARKER"),
    ],
)
def test_failed_job_status_never_exposes_authorization_or_quarantined_reply(
    paper_server, server, problem, monkeypatch
):
    configure(paper_server, server)
    disclosure = disclose(paper_server)
    row = paper_server.state.reviewer.records[disclosure["review_id"]]

    def fail(**_):
        raise problem

    monkeypatch.setattr(row["plan"], "request", fail)
    start(paper_server, disclosure)
    failed = wait(paper_server, disclosure)
    assert failed["phase"] == "failed" and failed["result"] is None
    assert "KEY_MARKER" not in json.dumps(failed)
    assert "PRIVATE_UNACCEPTED_REPLY" not in json.dumps(failed)
    download(paper_server, disclosure, "result", 400)
    assert not server.calls


def test_one_owned_inference_at_a_time_without_consuming_waiting_plan(paper_server, server):
    configure(paper_server, server)
    first, second = disclose(paper_server), disclose(paper_server)
    received, release = threading.Event(), threading.Event()

    def hold():
        received.set()
        release.wait(15)

    server.on_request = hold
    try:
        start(paper_server, first)
        assert received.wait(10)
        post(
            paper_server,
            "/api/reviewer/start",
            {
                **identity(second),
                "consent": True,
                "consent_sha256": second["consent_sha256"],
            },
            400,
        )
        assert len(server.calls) == 1
        post(paper_server, "/api/reviewer/cancel", identity(first))
        assert wait(paper_server, first)["phase"] == "cancelled"
        post(paper_server, "/api/reviewer/cancel", {"client": "review-ui", "generation": 0})
        assert post(paper_server, "/api/reviewer/status", identity(second))["phase"] == "disclosed"
        release.set()
        server.on_request = None
        start(paper_server, second)
        assert wait(paper_server, second)["phase"] == "completed"
        assert len(server.calls) == 2
    finally:
        release.set()
