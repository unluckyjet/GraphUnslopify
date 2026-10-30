"""Provider doubles test contracts; the separate local-model smoke tests inference."""

from __future__ import annotations

import copy
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from jsonschema import Draft7Validator

from graphunslopify import drafts
from graphunslopify.errors import SpecError
from graphunslopify.preview import PreviewState
from graphunslopify.transport import local_request


@pytest.fixture
def owned(tmp_path):
    state = PreviewState(tmp_path, 1024 * 1024)
    uploaded = state.upload(
        "private-original-name.csv", b"epoch,score,seed\n1,51,NEVER_SEND_A\n2,52,NEVER_SEND_B\n"
    )
    spec, data, _ = state.prepare(
        {
            "data_id": uploaded["id"],
            "spec": {
                "kind": "line",
                "x": {"field": "epoch", "label": "Epoch"},
                "y": {"field": "score", "label": "Score"},
                "title": "Author wording",
            },
        }
    )
    return spec, data


@pytest.fixture
def provider_server():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.server.calls.append((body, dict(self.headers)))
            self.send_response(self.server.status)
            if self.server.status == 302:
                self.send_header("Location", self.server.endpoint + "/redirected")
            self.end_headers()
            self.wfile.write(json.dumps(self.server.reply).encode())

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        server.endpoint = f"http://127.0.0.1:{server.server_port}/model"
        server.status = 200
        server.calls = []
        server.reply = response({"title": "Proposed title"})
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            thread.join(5)


def response(patch, *, protocol="responses", assumptions=None):
    envelope = {"patch": patch, "assumptions": assumptions or [], "questions": []}
    text = json.dumps(envelope)
    if protocol == "chat":
        return {
            "choices": [
                {"finish_reason": "stop", "message": {"role": "assistant", "content": text}}
            ]
        }
    return {
        "status": "completed",
        "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}],
    }


def plan(server, owned, *, context=None, protocol="responses"):
    spec, data = owned
    provider = drafts.DraftProvider(
        server.endpoint, "test-model", protocol, "synthetic-api-key-marker"
    )
    return drafts.DraftPlan(provider, data, spec, "Call the figure Proposed title", context)


def test_input_schema_defaults_all_kinds_and_compaction_preserves_nodes():
    source = local_request("input-schema")
    packed = drafts.compact_schema(source)
    Draft7Validator.check_schema(packed)
    assert len(packed["oneOf"]) == 21
    assert len(drafts._encoded(packed)) < len(drafts._encoded(source)) / 4

    def expand(value):
        if isinstance(value, list):
            return [expand(item) for item in value]
        if not isinstance(value, dict):
            return value
        if "$ref" in value:
            assert len(value) == 1
            return expand(packed["definitions"][value["$ref"].split("/")[-1]])
        return {key: expand(item) for key, item in value.items()}

    assert {key: expand(value) for key, value in packed.items() if key != "definitions"} == source
    minimal = {
        "kind": "line",
        "x": {"field": "epoch", "label": "Epoch"},
        "y": {"field": "score", "label": "Score"},
    }
    assert Draft7Validator(packed).is_valid(minimal)
    assert not Draft7Validator(local_request("schema")).is_valid(minimal)
    for recipe in local_request("recipes"):
        assert Draft7Validator(packed).is_valid(recipe["spec"]), recipe["name"]


@pytest.mark.parametrize("protocol", ["responses", "chat"])
def test_disclosure_consent_real_http_and_unapplied_canonical_proposal(
    provider_server, owned, protocol
):
    provider_server.reply = response({"title": "Proposed title"}, protocol=protocol)
    original = copy.deepcopy(owned[0])
    request = plan(provider_server, owned, protocol=protocol)
    disclosure = request.disclosure()
    shown = json.dumps(disclosure)
    for private in [
        "NEVER_SEND_A",
        "NEVER_SEND_B",
        "private-original-name",
        "synthetic-api-key-marker",
        str(owned[1]["path"]),
    ]:
        assert private not in shown
    body = disclosure["request"]
    context = json.loads(
        body["input"][0]["content"] if protocol == "responses" else body["messages"][1]["content"]
    )
    assert context["selected_data"]["rows"] == 2
    assert [column["name"] for column in context["selected_data"]["columns"]] == [
        "epoch",
        "score",
        "seed",
    ]
    assert all(
        set(column) <= {"name", "dtype", "missing", "non_missing", "finite", "nonfinite"}
        for column in context["selected_data"]["columns"]
    )
    assert context["current_intent"]["title"] == "Author wording"
    assert "data" not in context["current_intent"]
    with pytest.raises(ValueError, match="consent"):
        request.propose()
    assert not provider_server.calls
    # Disclosure is a copy; it cannot change the consented bytes.
    body["model"] = "mutated-client-copy"
    result = request.propose(consent=True)
    assert result["spec"]["title"] == "Proposed title"
    assert result["spec"]["data"] == original["data"]
    assert result["spec"]["x"]["scale"] == "linear"  # canonical compiler defaults
    assert result["applied"] is False and result["verified"] is False
    assert owned[0] == original
    assert provider_server.calls[0][0]["model"] == "test-model"
    assert provider_server.calls[0][1]["Authorization"] == "Bearer synthetic-api-key-marker"
    assert "synthetic-api-key-marker" not in repr(request._provider)
    with pytest.raises(ValueError, match="already attempted"):
        request.propose(consent=True)
    assert len(provider_server.calls) == 1


@pytest.mark.parametrize(
    "patch",
    [
        {"data": {"path": "/private.csv"}},
        {"data": None},
        {"palette_lock": "arbitrary.json"},
        {"output": {"stem": "../../outside"}},
        {"output": None},
        {"code": "import os"},
        {"x": {"typo": "ignored"}},
        {"x": {"field": "invented_column"}},
        {"y": {"unit": "ms"}},
        {"uncertainty": {"kind": "ci"}},
        {"uncertainty": {"kind": "sem", "over": "seed"}},
        {"kind": "scaling_fit"},
        {"kind": "kaplan_meier", "event": "seed"},
        {"kind": "box", "notch": True},
    ],
)
def test_invalid_ownership_fields_units_and_inferred_statistics_are_refused(
    provider_server, owned, patch
):
    provider_server.reply = response(patch)
    before = copy.deepcopy(owned[0])
    with pytest.raises((ValueError, SpecError)):
        plan(provider_server, owned).propose(consent=True)
    assert owned[0] == before


def test_declared_units_and_design_are_grounded_not_guessed(provider_server, owned):
    provider_server.reply = response(
        {"y": {"unit": "ms"}, "aggregation": "mean", "uncertainty": {"kind": "ci", "over": "seed"}}
    )
    context = {"units": {"score": "ms"}, "design": "independent", "unit_field": "seed"}
    result = plan(provider_server, owned, context=context).propose(consent=True)
    assert result["spec"]["uncertainty"]["over"] == "seed" and not result["verified"]
    context["unit_field"] = "epoch"
    with pytest.raises(ValueError, match="experimental units"):
        plan(provider_server, owned, context=context).propose(consent=True)


def test_existing_claims_cannot_be_removed_or_weakened(provider_server, owned):
    spec, _ = owned
    spec["group"] = "seed"
    spec["claims"] = [{"kind": "no_worse_than", "subject": "A", "reference": "B", "tolerance": 0}]
    provider_server.reply = response({"claims": None})
    with pytest.raises(ValueError, match="existing claims"):
        plan(provider_server, owned).propose(consent=True)
    provider_server.reply = response({"claims": [{**spec["claims"][0], "tolerance": 100}]})
    with pytest.raises(ValueError, match="existing claims"):
        plan(provider_server, owned).propose(consent=True)


@pytest.mark.parametrize(
    "patch,context",
    [
        ({"uncertainty": {"kind": "ci"}}, {"design": "paired"}),
        ({"kind": "scaling_fit"}, {"design": "paired", "unit_field": "seed"}),
        ({"kind": "scaling_fit"}, {"design": "independent", "unit_field": "seed"}),
        ({"kind": "box", "notch": True}, {"design": "paired", "unit_field": "seed"}),
        ({"kind": "kaplan_meier", "event": "seed"}, {"design": "paired", "unit_field": "seed"}),
    ],
)
def test_declared_pairing_is_not_silently_treated_as_independent_rows(
    provider_server, owned, patch, context
):
    provider_server.reply = response(patch)
    with pytest.raises(ValueError, match=r"experimental units|independent rows"):
        plan(provider_server, owned, context=context).propose(consent=True)


def test_invalid_model_spec_is_quarantined_for_review(provider_server, owned):
    provider_server.reply = response({"x": {"label": 4}})
    with pytest.raises(drafts.InvalidDraft) as problem:
        plan(provider_server, owned).propose(consent=True)
    assert problem.value.envelope["patch"] == {"x": {"label": 4}}
    assert problem.value.problems[0]["path"] == ["x", "label"]
    assert "synthetic-api-key-marker" not in str(problem.value)


@pytest.mark.parametrize(
    "reply",
    [
        {"status": "incomplete", "output": []},
        {"status": "completed", "output": [{"type": "function_call", "arguments": "{}"}]},
        {
            "status": "completed",
            "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "no"}]}],
        },
        {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": '{"patch":{},"assumptions":[],"questions":[],"verified":true}',
                        }
                    ],
                }
            ],
        },
    ],
)
def test_refusal_incomplete_tools_and_fake_verification_are_not_proposals(
    provider_server, owned, reply
):
    provider_server.reply = reply
    with pytest.raises(ValueError):
        plan(provider_server, owned).propose(consent=True)


def test_redirect_and_provider_error_do_not_replay_or_echo_secrets(provider_server, owned):
    for status in [302, 401, 500]:
        provider_server.status = status
        provider_server.reply = {"error": "synthetic-api-key-marker NEVER_SEND_A"}
        with pytest.raises(ValueError, match=f"HTTP {status}") as problem:
            plan(provider_server, owned).propose(consent=True)
        assert "synthetic-api-key-marker" not in str(problem.value)
    assert len(provider_server.calls) == 3


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://example.org/model",
        "http://localhost.evil/model",
        "https://user:password@example.org/model",
        "https://example.org/model?key=private",
        "https://example.org/#fragment",
    ],
)
def test_unsafe_provider_configuration_is_refused(endpoint):
    with pytest.raises(ValueError):
        drafts.DraftProvider(endpoint, "test")


@pytest.mark.parametrize("value", ['{"a":1,"a":2}', '{"x":NaN}', '{"x":Infinity}', '{"x":1e999}'])
def test_nonfinite_or_ambiguous_json_is_refused(value):
    with pytest.raises(ValueError):
        drafts._strict_json(value)
