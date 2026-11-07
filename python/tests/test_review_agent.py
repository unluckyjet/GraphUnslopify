"""Actual saved paper checks plus controlled HTTP; no model-quality claims."""

from __future__ import annotations

import copy
import csv
import hashlib
import json
import shutil
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from graphunslopify import project
from graphunslopify.cli import main
from graphunslopify.drafts import DraftProvider, _digest, _encoded
from graphunslopify.project_inspections import inspect_project_pdf, project_inspections
from graphunslopify.project_review import project_review
from graphunslopify.review_agent import (
    FigureReviewPlan,
    InvalidReview,
    read_document,
    restore_plan,
    review_document,
    write_document,
)

ROOT = Path(__file__).resolve().parents[2]


def inventory(root):
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


@pytest.fixture(scope="module")
def checked(tmp_path_factory):
    root = tmp_path_factory.mktemp("review-agent-original") / "NEVER_SEND_ROOT"
    shutil.copytree(ROOT / "examples/paper", root)
    source = root / "results.csv"
    with source.open() as stream:
        rows = list(csv.reader(stream))
    with (root / "NEVER_SEND_FILENAME.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow([*rows[0], "private_marker"])
        writer.writerows([*row, "NEVER_SEND_OBSERVATION"] for row in rows[1:])
    source.unlink()
    for path in root.glob("*.figure.json"):
        spec = json.loads(path.read_text())
        spec["data"]["path"] = "NEVER_SEND_FILENAME.csv"
        path.write_text(json.dumps(spec))
    project.initialize_project(root)
    assert project.run_project(root)["exit_code"] == 0
    return root


@pytest.fixture
def paper(checked, tmp_path):
    root = tmp_path / "paper with spaces ü"
    shutil.copytree(checked, root)
    return root


def proposal():
    return {
        "summary": "The saved checks do not establish the experimental design.",
        "suggestions": [
            {
                "figure_key": "training",
                "topic": "uncertainty",
                "suggestion": "Explain what the seed experimental unit represents.",
                "why": "Declared interval settings alone do not establish independence.",
                "evidence_ids": ["F1.uncertainty"],
            }
        ],
        "author_questions": ["Were these genuinely independent experimental units?"],
    }


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            raw = self.rfile.read(int(self.headers["Content-Length"]))
            self.server.calls.append((raw, dict(self.headers)))
            if self.server.on_request:
                self.server.on_request()
            text = self.server.text
            body = (
                {"choices": [{"finish_reason": "stop", "message": {"content": text}}]}
                if self.server.protocol == "chat"
                else {
                    "status": "completed",
                    "output": [
                        {"type": "message", "content": [{"type": "output_text", "text": text}]}
                    ],
                }
            )
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as http:
        http.endpoint = f"http://127.0.0.1:{http.server_port}/model"
        http.text = json.dumps(proposal())
        http.protocol = "responses"
        http.calls = []
        http.on_request = None
        thread = threading.Thread(target=http.serve_forever)
        thread.start()
        try:
            yield http
        finally:
            http.shutdown()
            thread.join(5)


def plan(server, paper, **kwargs):
    return FigureReviewPlan(
        DraftProvider(server.endpoint, "controlled-test-model", server.protocol, "KEY_MARKER"),
        paper,
        **kwargs,
    )


def request(review):
    return review.request(consent=True, consent_sha256=review.disclosure()["consent_sha256"])


def test_role_panel_discloses_three_separate_requests_and_records_failed_role(
    server, paper, tmp_path
):
    from graphunslopify.review_panel_providers import PaperReviewRoles

    roles = {
        "readability": {"legibility"},
        "statistical_claims": {"claims", "uncertainty"},
        "journal_formatting": {"journal_formatting"},
    }
    shared = DraftProvider(server.endpoint, "same-controlled-model")
    before = inventory(paper)
    panel = PaperReviewRoles(
        paper, dict.fromkeys(roles, shared), figures=["training"], journal_profile="plos-one-main"
    )
    disclosed = panel.disclosure()
    digests = {role: row["consent_sha256"] for role, row in disclosed.items()}
    assert set(disclosed) == roles.keys() and len(set(digests.values())) == 3
    for role, document in disclosed.items():
        body = document["request"]
        content = json.loads(body["input"][0]["content"])
        assert set(content["deterministic_evidence"]["figures"][0]["groups"]) == roles[role]
        assert content["deterministic_evidence"]["role"] == role
        assert b"NEVER_SEND" not in _encoded(body)
    journal = json.loads(disclosed["journal_formatting"]["request"]["input"][0]["content"])
    formatting = journal["deterministic_evidence"]["figures"][0]["groups"]["journal_formatting"]
    assert formatting["profile"]["id"] == "plos-one-main"
    assert any(
        check["status"] == "failed" and check["code"] == "file_format"
        for item in formatting["exports"]
        for check in item["report"]["checks"]
    )
    with pytest.raises(project.ProjectError, match="all three digests"):
        panel.request(consent=True, consent_sha256={"readability": digests["readability"]})
    with pytest.raises(project.ProjectError, match="all three digests"):
        panel.request(consent=False, consent_sha256=digests)
    assert not server.calls

    def reply():
        raw = server.calls[-1][0]
        body = json.loads(raw)
        context = json.loads(body["input"][0]["content"])
        role = context["deterministic_evidence"]["role"]
        topic = next(iter(sorted(roles[role])))
        if role == "journal_formatting":
            topic = "claims"
        content = proposal()
        content["suggestions"][0].update(topic=topic, evidence_ids=["F1.status"])
        server.text = json.dumps(content)

    server.on_request = reply
    result = panel.request(consent=True, consent_sha256=digests)
    assert result["status"] == "partial" and result["matches_current_evidence"]
    assert result["shared_provider_configuration"] is True
    assert result["role_reviews"]["readability"]["status"] == "completed"
    assert result["role_reviews"]["statistical_claims"]["status"] == "completed"
    assert result["role_reviews"]["journal_formatting"]["status"] == "unavailable"
    assert result["deterministic_evidence"]["figures"][0]["recorded_outcome"] == "passed"
    assert len(server.calls) == 3 and inventory(paper) == before
    for role, (raw, _) in zip(roles, server.calls, strict=True):
        assert raw == _encoded(disclosed[role]["request"])
        assert hashlib.sha256(raw).hexdigest() == result["role_reviews"][role]["request_sha256"]
    (tmp_path / "provider-role-proof.json").write_text(
        json.dumps({"disclosures": disclosed, "result": result}, indent=2), encoding="utf8"
    )
    with pytest.raises(project.ProjectError, match="already attempted"):
        panel.request(consent=True, consent_sha256=digests)


def test_role_panel_refuses_changed_evidence_before_any_request(server, paper):
    from graphunslopify.review_panel_providers import PaperReviewRoles

    provider = DraftProvider(server.endpoint, "controlled-review")
    roles = ("readability", "statistical_claims", "journal_formatting")
    panel = PaperReviewRoles(paper, dict.fromkeys(roles, provider), figures=["training"])
    digests = {role: row["consent_sha256"] for role, row in panel.disclosure().items()}
    figure = paper / "training.figure.json"
    spec = json.loads(figure.read_bytes())
    spec["title"] = "Changed before consent"
    figure.write_text(json.dumps(spec))
    with pytest.raises(project.ProjectError, match="Paper evidence changed"):
        panel.request(consent=True, consent_sha256=digests)
    assert not server.calls


def test_role_panel_stops_after_evidence_changes_during_the_first_request(server, paper):
    from graphunslopify.review_panel_providers import PaperReviewRoles

    provider = DraftProvider(server.endpoint, "controlled-review")
    roles = ("readability", "statistical_claims", "journal_formatting")
    panel = PaperReviewRoles(paper, dict.fromkeys(roles, provider), figures=["training"])
    digests = {role: row["consent_sha256"] for role, row in panel.disclosure().items()}
    figure = paper / "training.figure.json"
    spec = json.loads(figure.read_bytes())
    spec["title"] = "Changed during provider review"
    server.on_request = lambda: figure.write_text(json.dumps(spec))
    result = panel.request(consent=True, consent_sha256=digests)
    assert result["status"] == "partial" and not result["matches_current_evidence"]
    assert all(row["status"] == "unavailable" for row in result["role_reviews"].values())
    assert len(server.calls) == 1


def test_paper_audit_assembles_reviewed_batches_without_changing_verdicts(
    server, paper, tmp_path, capsys
):
    files, digests = [], []
    for key in ("training", "results-table"):
        review = plan(server, paper, figures=[key])
        file = tmp_path / (key + ".json")
        write_document(review_document(review), file)
        files.append(file)
        digests.append(review.disclosure()["consent_sha256"])

    refuse_second = False

    def respond_to_current_batch():
        raw, _ = server.calls[-1]
        body = json.loads(raw)
        context = json.loads(body["input"][0]["content"])
        key = context["deterministic_evidence"]["figures"][0]["key"]
        if refuse_second and key == "results-table":
            server.text = "unusable provider response"
            return
        reply = proposal()
        reply["suggestions"][0].update(
            figure_key=key, suggestion="<script>review suggestion</script>"
        )
        server.text = json.dumps(reply)

    server.on_request = respond_to_current_batch
    before = inventory(paper)
    output = tmp_path / "review.zip"
    command = ["project-audit", str(paper), "--saved-evidence", "--output", str(output)]
    options = [
        token
        for file, digest in zip(files, digests, strict=True)
        for token in ("--review-plan", str(file), "--consent-sha256", digest)
    ]
    assert main([*command, *options]) == 2
    assert "consent" in capsys.readouterr().out and not server.calls and not output.exists()
    assert main([*command, *options[:4], "--consent"]) == 2
    assert "every current figure" in capsys.readouterr().out and not server.calls
    assert main([*command, *options, "--consent"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "checked" and result["qualitative_status"] == "completed"
    assert len(server.calls) == 2 and inventory(paper) == before
    with zipfile.ZipFile(output) as z:
        report = json.loads(z.read("review.json"))
        qualitative = json.loads(z.read("reports/qualitative-review.json"))
        assert report["paper_audit"]["status"] == "checked"
        assert [row["figures"] for row in qualitative] == [["training"], ["results-table"]]
        assert all(row["status"] == "completed" for row in qualitative)
        assert all(
            row["review"]["qualitative"]["citations_validate_references_only"]
            for row in qualitative
        )
        assert report["review"] == project_review(paper)
        index = z.read("index.html").decode()
        assert "Unverified model suggestions" in index
        assert (
            "<script>review suggestion" not in index and "&lt;script&gt;review suggestion" in index
        )
    refuse_second = True
    partial = tmp_path / "partial.zip"
    assert main([*command[:-1], str(partial), *options, "--consent"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "checked" and result["qualitative_status"] == "partial"
    assert len(server.calls) == 4 and inventory(paper) == before
    with zipfile.ZipFile(partial) as z:
        report = json.loads(z.read("review.json"))
        qualitative = report["qualitative_reviews"]
        assert report["paper_audit"]["status"] == "checked"
        assert [row["status"] for row in qualitative] == ["completed", "unavailable"]
        assert "unusable provider response" not in z.read("index.html").decode()


@pytest.mark.parametrize("protocol", ["responses", "chat"])
@pytest.mark.parametrize("structured", [True, False])
def test_actual_evidence_exact_disclosure_http_and_no_project_mutation(
    server, paper, protocol, structured
):
    server.protocol = protocol
    original = project_review(paper)
    before = inventory(paper)
    review = plan(
        server, paper, question="Review both figures for submission", structured_output=structured
    )
    disclosure = review.disclosure()
    body = disclosure["request"]
    wire_format = body["response_format"] if protocol == "chat" else body["text"]["format"]
    assert wire_format["type"] == ("json_schema" if structured else "json_object")
    if structured:
        schema = (
            wire_format["json_schema"]["schema"] if protocol == "chat" else wire_format["schema"]
        )
        assert schema["additionalProperties"] is False
        assert schema["properties"]["suggestions"]["items"]["properties"]["figure_key"]["enum"] == [
            "training",
            "results-table",
        ]
        assert "maxLength" not in schema["properties"]["summary"]
    shown = json.dumps(disclosure)
    for private in [
        "NEVER_SEND_ROOT",
        "NEVER_SEND_FILENAME",
        "NEVER_SEND_OBSERVATION",
        "KEY_MARKER",
    ]:
        assert private not in shown
    assert not server.calls
    with pytest.raises(ValueError, match="Explicitly consent"):
        review.request()
    with pytest.raises(ValueError, match="Explicitly consent"):
        review.request(consent=True, consent_sha256=disclosure["request_sha256"])
    result = request(review)
    assert len(server.calls) == 1
    assert server.calls[0][0] == _encoded(disclosure["request"])
    assert server.calls[0][1]["Authorization"] == "Bearer KEY_MARKER"
    actual = result["deterministic_evidence"]
    assert len(actual["figures"]) == 2
    for actual_row, source_row in zip(actual["figures"], original["figures"], strict=True):
        for group in ["claims", "uncertainty", "legibility"]:
            assert actual_row["groups"][group] == source_row["groups"][group]
        assert actual_row["evidence_state"] == source_row["evidence_state"] == "current_inputs"
    assert result["qualitative"]["content"] == proposal()
    assert result["qualitative"]["citations_validate_references_only"]
    assert result["scientific_acceptance"] == "not_established" and not result["applied"]
    assert result["evidence_unchanged_during_request"] and not actual["images_supplied"]
    assert inventory(paper) == before
    with pytest.raises(ValueError, match="already attempted"):
        request(review)
    assert len(server.calls) == 1


@pytest.mark.parametrize("selection", [[], ["missing"], ["training", "training"], "training", [1]])
def test_invalid_actual_figure_selection_refuses_without_inference(server, paper, selection):
    with pytest.raises(ValueError, match="figure keys"):
        plan(server, paper, figures=selection)
    assert not server.calls


def test_selected_figure_order_and_unknown_evidence_references(server, paper):
    review = plan(server, paper, figures=["results-table", "training"])
    value = proposal()
    value["suggestions"][0]["evidence_ids"] = ["F2.uncertainty"]
    server.text = json.dumps(value)
    assert request(review)["qualitative"]["content"] == value
    value["suggestions"][0]["evidence_ids"] = ["F1.uncertainty"]
    server.text = json.dumps(value)
    with pytest.raises(ValueError, match="cite evidence for its selected figure"):
        request(plan(server, paper, figures=["results-table", "training"]))


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update(deterministic_evidence={"status": "passed"}),
        lambda value: value.update(patch={"claims": []}),
        lambda value: value["suggestions"][0].update(evidence_ids=["INVENTED"]),
        lambda value: value["suggestions"][0].update(figure_key="INVENTED"),
        lambda value: value["suggestions"][0].update(evidence_ids=[]),
        lambda value: value["suggestions"][0].update(topic="scientific_certification"),
        lambda value: value.update(summary="x" * 2001),
        lambda value: value.update(summary=" \n "),
    ],
)
def test_invalid_model_reply_cannot_change_checks_or_create_references(server, paper, mutation):
    value = proposal()
    mutation(value)
    server.text = json.dumps(value)
    before = inventory(paper)
    with pytest.raises(InvalidReview, match="invalid fields") as caught:
        request(plan(server, paper))
    assert caught.value.reply == server.text
    assert inventory(paper) == before


@pytest.mark.parametrize(
    "text", ['{"summary":"first","summary":"second"}', '{"a":NaN}', "not JSON"]
)
def test_duplicate_nonfinite_and_malformed_model_json_refuses(server, paper, text):
    server.text = text
    with pytest.raises(ValueError):
        request(plan(server, paper))


@pytest.mark.parametrize("when", ["before", "during"])
def test_actual_data_change_fences_outbound_and_returned_inference(server, paper, when):
    review = plan(server, paper)

    def change():
        path = paper / "NEVER_SEND_FILENAME.csv"
        path.write_bytes(path.read_bytes() + b"\n")

    if when == "before":
        change()
    else:
        server.on_request = change
    with pytest.raises(ValueError, match="evidence changed"):
        request(review)
    assert len(server.calls) == (0 if when == "before" else 1)


def test_saved_export_change_fences_request(server, paper):
    review = plan(server, paper)
    export = next((paper / "graphunslopify-project/history").rglob("*.png"))
    export.write_bytes(b"tampered saved image")
    with pytest.raises(ValueError, match="evidence changed"):
        request(review)
    assert not server.calls


@pytest.mark.parametrize("when", ["before", "during"])
def test_cancelled_review_never_returns_advice_or_retries(server, paper, when):
    review = plan(server, paper)
    cancelled = threading.Event()
    if when == "before":
        cancelled.set()
    else:
        server.on_request = cancelled.set
    with pytest.raises(ValueError, match="cancelled"):
        review.request(
            consent=True, consent_sha256=review.disclosure()["consent_sha256"], cancelled=cancelled
        )
    assert len(server.calls) == (0 if when == "before" else 1)
    with pytest.raises(ValueError, match="already attempted"):
        request(review)
    assert len(server.calls) == (0 if when == "before" else 1)


def test_invalid_cancellation_refuses_without_consuming_review(server, paper):
    review = plan(server, paper)
    with pytest.raises(TypeError, match=r"threading\.Event"):
        review.request(
            consent=True, consent_sha256=review.disclosure()["consent_sha256"], cancelled=object()
        )
    assert not server.calls
    assert request(review)["status"] == "completed"


def test_real_failed_claim_and_historical_pass_remain_separate(server, paper):
    old_event = project.project_history(paper)["events"][0]["id"]
    spec_path = paper / "training.figure.json"
    spec = json.loads(spec_path.read_text())
    spec["claims"][0].update(subject="base", reference="ours")
    spec_path.write_text(json.dumps(spec))
    assert project.run_project(paper)["exit_code"] == 2
    current = request(plan(server, paper))
    assert current["status"] == "completed"  # query completion is not a science pass
    row = current["deterministic_evidence"]["figures"][0]
    assert row["execution_status"] == "failed"
    assert row["groups"]["claims"]["items"][0]["verdict"] == "fails"
    agenda = current["deterministic_evidence"]["recorded_failures"]
    assert agenda[0]["recorded"] == row["groups"]["claims"]["items"][0]
    assert agenda[0]["evidence_id"] == "F1.claims.1"
    historical = request(plan(server, paper, event_id=old_event))
    row = historical["deterministic_evidence"]["figures"][0]
    assert row["groups"]["claims"]["items"][0]["verdict"] == "holds"
    assert not row["matches_latest_accepted_inputs"]
    assert historical["deterministic_evidence"]["selection"]["explicit_history_selection"]


def test_unrun_and_broken_latest_evidence_does_not_borrow_saved_pass(server, paper, tmp_path):
    fresh = tmp_path / "fresh"
    shutil.copytree(ROOT / "examples/paper", fresh)
    project.initialize_project(fresh)
    result = request(plan(server, fresh))
    assert all(
        row["evidence_state"] == "not_run" for row in result["deterministic_evidence"]["figures"]
    )
    project._event(paper / "graphunslopify-project", "run")
    result = request(plan(server, paper))
    assert result["deterministic_evidence"]["selection"]["state"] == "unavailable"
    assert all(
        row["groups"]["claims"]["state"] == "unavailable"
        for row in result["deterministic_evidence"]["figures"]
    )


def test_actual_pdf_evidence_remains_visual_only_and_numerically_untested(server, paper):
    pdf = paper / "external.pdf"
    shutil.copyfile(ROOT / "examples/baseline/01-training-curve.pdf", pdf)
    result = inspect_project_pdf(
        paper,
        pdf,
        identity="external",
        expected_revision=project_inspections(paper)["revision"],
        pages=[1],
        dpi=72,
    )
    assert result["status"] == "incomplete"
    reply = proposal()
    reply["suggestions"][0].update(
        figure_key="pdf:external", topic="claims", evidence_ids=["F1.claims"]
    )
    server.text = json.dumps(reply)
    result = request(plan(server, paper, figures=["pdf:external"]))
    row = result["deterministic_evidence"]["figures"][0]
    assert row["source_type"] == "pdf" and row["evidence_state"] == "saved_visual_evidence"
    assert row["groups"]["claims"]["state"] == "untested"
    assert row["groups"]["uncertainty"]["state"] == "untested"
    assert row["groups"]["reproduction"]["native_programs_executed"] is False
    assert not result["deterministic_evidence"]["images_supplied"]


def test_document_binds_destination_request_and_current_evidence(server, paper, tmp_path):
    review = plan(server, paper)
    document = review_document(review)
    path = tmp_path / "request.json"
    write_document(document, path)
    assert read_document(path) == document
    with pytest.raises(FileExistsError):
        write_document(document, path)
    restored = restore_plan(document, paper, api_key="KEY_MARKER")
    assert restored.disclosure() == review.disclosure()
    tampered = copy.deepcopy(document)
    tampered["selection"]["question"] = "Changed question"
    with pytest.raises(ValueError, match="request changed"):
        restore_plan(tampered, paper)
    tampered["fingerprint"] = _digest({k: v for k, v in tampered.items() if k != "fingerprint"})
    with pytest.raises(ValueError, match="context or evidence changed"):
        restore_plan(tampered, paper)
    other = FigureReviewPlan(
        DraftProvider(server.endpoint + "/different-destination", "controlled-test-model"), paper
    )
    assert other.disclosure()["request_sha256"] == review.disclosure()["request_sha256"]
    assert other.disclosure()["consent_sha256"] != review.disclosure()["consent_sha256"]
    with pytest.raises(ValueError, match="Explicitly consent"):
        other.request(consent=True, consent_sha256=review.disclosure()["consent_sha256"])
    assert not server.calls


@pytest.mark.parametrize(
    "kwargs",
    [
        {"question": " "},
        {"question": "q" * 12001},
        {"author_context": "c" * 8001},
        {"event_id": {}},
        {"structured_output": 1},
    ],
)
def test_bounded_question_context_and_history_selection(server, paper, kwargs):
    with pytest.raises(ValueError):
        plan(server, paper, **kwargs)
    assert not server.calls


def test_oversized_evidence_refuses_without_silently_dropping_findings(server, paper, monkeypatch):
    from graphunslopify import review_agent

    monkeypatch.setattr(review_agent, "MAX_REQUEST", 100)
    with pytest.raises(ValueError, match="exceeds 1MiB"):
        plan(server, paper)
    assert not server.calls


def test_cli_saved_review_explicit_consent_json_and_existing_outputs(
    server, paper, tmp_path, capsys
):
    saved = tmp_path / "review.json"
    output = tmp_path / "result.json"
    assert (
        main(
            [
                "review-agent-plan",
                str(paper),
                "--endpoint",
                server.endpoint,
                "--model",
                "controlled-test-model",
                "--out",
                str(saved),
            ]
        )
        == 0
    )
    document = json.loads(capsys.readouterr().out)
    assert saved.exists() and not server.calls
    run = ["review-agent-run", str(saved), "--path", str(paper), "--out", str(output)]
    assert main(run) == 2
    assert "consent" in json.loads(capsys.readouterr().out)["error"]
    assert not output.exists() and not server.calls
    consent = ["--consent", "--consent-sha256", document["disclosure"]["consent_sha256"]]
    assert main([*run, *consent]) == 0
    result = json.loads(capsys.readouterr().out)
    assert json.loads(output.read_text()) == result
    assert len(server.calls) == 1 and result["scientific_acceptance"] == "not_established"
    assert main([*run, *consent]) == 2
    assert "existing files" in json.loads(capsys.readouterr().out)["error"]
    assert len(server.calls) == 1
