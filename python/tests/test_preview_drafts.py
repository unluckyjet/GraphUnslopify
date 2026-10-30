"""Real editor HTTP and controlled provider HTTP: ownership, consent and races."""

from __future__ import annotations

import copy
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from test_drafts import response
from test_preview import editor as editor  # noqa: PLC0414 -- re-export the Pytest fixture
from test_preview import request


@pytest.fixture
def model_api():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            self.server.calls.append(
                json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            )
            self.server.entered.set()
            assert self.server.release.wait(10)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps(self.server.reply).encode())

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        server.endpoint = f"http://127.0.0.1:{server.server_port}/v1/chat/completions"
        server.calls = []
        server.entered = threading.Event()
        server.release = threading.Event()
        server.release.set()
        server.reply = response({"title": "Model draft"}, protocol="chat")
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            yield server
        finally:
            server.release.set()
            server.shutdown()
            thread.join(5)


def call(editor, route, payload=None, **kwargs):
    status, body = request(editor, route, payload, **kwargs)
    return status, json.loads(body)


def configure(editor, model_api):
    status, info = call(
        editor,
        "/api/model-provider",
        {
            "endpoint": model_api.endpoint,
            "model": "controlled-model",
            "protocol": "chat",
            "api_key": "SYNTHETIC_KEY",
        },
    )
    assert status == 200 and info["configured"]
    assert "SYNTHETIC_KEY" not in json.dumps(info)
    return info


def owned_payload(editor):
    status, upload = call(
        editor,
        "/api/upload",
        b"epoch,score\n1,51\n2,54\n",
        headers={"X-Filename": "private-original-name.csv"},
    )
    assert status == 200
    return {
        "client": "model-api-test",
        "generation": 0,
        "data_id": upload["id"],
        "spec": {
            "kind": "line",
            "x": {"field": "epoch", "label": "Epoch"},
            "y": {"field": "score", "label": "Score"},
        },
        "prompt": "Call the figure Model draft",
    }


def disclosed(editor, model_api):
    configure(editor, model_api)
    payload = owned_payload(editor)
    status, disclosure = call(editor, "/api/draft/disclose", payload)
    assert status == 200, disclosure
    return {**payload, "draft_id": disclosure["draft_id"]}, disclosure


def test_model_routes_keep_existing_authorization_and_manual_fallback(editor):
    assert request(editor, "/drafts.js", token=False)[0] == 200
    assert call(editor, "/api/model-provider", token=False)[0] == 403
    for route in [
        "/api/model-provider",
        "/api/draft/disclose",
        "/api/draft/propose",
        "/api/draft/accept",
        "/api/draft/cancel",
    ]:
        assert call(editor, route, {}, token=False)[0] == 403
        assert call(editor, route, {}, headers={"Origin": "https://attacker.example"})[0] == 403
    status, info = call(editor, "/api/model-provider")
    assert status == 200 and info == {
        "configured": False,
        "revision": 0,
        "provider": None,
        "authorization_configured": False,
    }
    payload = owned_payload(editor)
    status, error = call(editor, "/api/draft/disclose", payload)
    assert status == 400 and "manual" in error["error"]
    assert call(editor, "/api/validate", payload)[1]["ok"]


def test_owned_disclosure_not_client_profile_and_no_send_before_consent(editor, model_api):
    configure(editor, model_api)
    payload = owned_payload(editor)
    payload.update(
        {
            "profile": {"rows": 999, "columns": [{"name": "CLIENT_FORGED_COLUMN"}]},
            "columns": ["CLIENT_FORGED_COLUMN"],
        }
    )
    payload["spec"]["data"] = {"path": "/DO_NOT_READ_PRIVATE.csv"}
    status, value = call(editor, "/api/draft/disclose", payload)
    assert status == 200
    shown = json.dumps(value)
    for private in [
        "SYNTHETIC_KEY",
        "CLIENT_FORGED_COLUMN",
        "DO_NOT_READ_PRIVATE",
        "private-original-name.csv",
    ]:
        assert private not in shown
    context = json.loads(value["request"]["messages"][1]["content"])
    assert context["selected_data"]["rows"] == 2
    assert [column["name"] for column in context["selected_data"]["columns"]] == ["epoch", "score"]
    assert not model_api.calls
    for consent in [False, 1, "true", None]:
        assert (
            call(
                editor,
                "/api/draft/propose",
                {**payload, "draft_id": value["draft_id"], "consent": consent},
            )[0]
            == 400
        )
    assert not model_api.calls


def test_review_accept_then_explicit_strict_render_with_owned_data(editor, model_api):
    payload, _ = disclosed(editor, model_api)
    before = copy.deepcopy(payload)
    status, proposal = call(editor, "/api/draft/propose", {**payload, "consent": True})
    assert status == 200 and proposal["spec"]["title"] == "Model draft"
    assert proposal["applied"] is False and proposal["verified"] is False
    assert not editor.state.runs and payload == before
    assert call(editor, "/api/draft/accept", payload)[0] == 400
    status, accepted = call(editor, "/api/draft/accept", {**payload, "reviewed": True})
    assert status == 200 and accepted["requires_strict_render"] and not accepted["verified"]
    assert not editor.state.runs  # acceptance alone cannot create verified exports
    status, rendered = call(editor, "/api/render", {**payload, "spec": accepted["spec"]})
    assert status == 200 and rendered["report"]["ok"] and rendered["report"]["status"] == "passed"
    assert {item["format"] for item in rendered["report"]["outputs"]} == {"png", "svg", "pdf"}
    assert (
        editor.state.selected_data(payload["data_id"])["path"].read_bytes()
        == b"epoch,score\n1,51\n2,54\n"
    )
    assert call(editor, "/api/draft/accept", {**payload, "reviewed": True})[0] == 400
    assert len(model_api.calls) == 1


@pytest.mark.parametrize("change", ["data", "spec", "provider", "revision", "client"])
def test_stale_disclosure_is_refused_before_transmission(editor, model_api, change):
    payload, _ = disclosed(editor, model_api)
    if change == "data":
        payload["data_id"] = owned_payload(editor)["data_id"]
    elif change == "spec":
        payload["spec"]["x"]["label"] = "New label"
    elif change == "provider":
        configure(editor, model_api)
    elif change == "revision":
        payload["generation"] += 1
    else:
        payload["client"] = "another-client"
    assert call(editor, "/api/draft/propose", {**payload, "consent": True})[0] == 400
    assert not model_api.calls


@pytest.mark.parametrize("change", ["cancel", "provider", "render-revision"])
def test_late_model_result_cannot_revive_a_stale_proposal(editor, model_api, change):
    payload, _ = disclosed(editor, model_api)
    model_api.release.clear()
    result = []
    thread = threading.Thread(
        target=lambda: result.append(
            call(editor, "/api/draft/propose", {**payload, "consent": True})
        )
    )
    thread.start()
    try:
        assert model_api.entered.wait(5)
        if change == "cancel":
            assert call(editor, "/api/draft/cancel", {**payload, "generation": 1})[0] == 200
        elif change == "provider":
            configure(editor, model_api)
        else:
            with editor.state.lock:
                editor.state.generations[payload["client"]] = 1
    finally:
        model_api.release.set()
        thread.join(10)
    assert result[0][0] == 400
    assert not any(record["result"] for record in editor.state.drafts.records.values())
    assert call(editor, "/api/draft/accept", {**payload, "reviewed": True})[0] == 400
    assert not editor.state.runs


def test_provider_changes_never_reuse_an_old_key(editor, model_api):
    first = configure(editor, model_api)
    status, value = call(
        editor,
        "/api/model-provider",
        {"endpoint": model_api.endpoint, "model": "another-model", "protocol": "chat"},
    )
    assert (
        status == 200
        and not value["authorization_configured"]
        and value["revision"] > first["revision"]
    )
    assert editor.state.drafts.provider.api_key == ""
    assert call(editor, "/api/model-provider", {"enabled": False})[1]["configured"] is False


def test_expiry_and_bounded_disclosures_do_not_transmit(editor, model_api):
    payload, _ = disclosed(editor, model_api)
    editor.state.drafts.records[payload["draft_id"]]["created"] -= 601
    assert call(editor, "/api/draft/propose", {**payload, "consent": True})[0] == 400
    for _ in range(12):
        assert call(editor, "/api/draft/disclose", payload)[0] == 200
    assert len(editor.state.drafts.records) == 8 and not model_api.calls


def test_invalid_output_is_quarantined_without_applying_or_certifying(editor, model_api):
    payload, _ = disclosed(editor, model_api)
    model_api.reply = response({"x": {"label": 7}}, protocol="chat")
    status, value = call(editor, "/api/draft/propose", {**payload, "consent": True})
    assert status == 400 and value["verified"] is False
    assert value["invalid_draft"]["problems"][0]["path"] == ["x", "label"]
    assert call(editor, "/api/draft/accept", {**payload, "reviewed": True})[0] == 400
    assert not editor.state.runs


def test_existing_false_numerical_claim_still_fails_after_model_title_patch(editor, model_api):
    configure(editor, model_api)
    status, data = call(
        editor,
        "/api/upload",
        b"epoch,score,model\n1,1,A\n2,2,A\n1,5,B\n2,6,B\n",
        headers={"X-Filename": "public-synthetic.csv"},
    )
    assert status == 200
    payload = {**owned_payload(editor), "data_id": data["id"]}
    payload["spec"].update(
        {
            "group": "model",
            "claims": [{"kind": "beats_everywhere", "subject": "A", "reference": "B"}],
        }
    )
    status, value = call(editor, "/api/draft/disclose", payload)
    assert status == 200
    payload["draft_id"] = value["draft_id"]
    proposal = call(editor, "/api/draft/propose", {**payload, "consent": True})[1]
    assert proposal["spec"]["claims"] == payload["spec"]["claims"]
    accepted = call(editor, "/api/draft/accept", {**payload, "reviewed": True})[1]
    rendered = call(editor, "/api/render", {**payload, "spec": accepted["spec"]})[1]
    assert rendered["report"]["status"] == "failed" and rendered["report"]["ok"] is False
