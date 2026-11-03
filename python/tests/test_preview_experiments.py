"""Real local HTTP:read-only discovery,review/accept ownership,source changes and bundles."""

import hashlib
import io
import json
import zipfile

import pytest
from test_preview import editor as editor  # noqa: PLC0414
from test_preview import request


@pytest.fixture
def source(tmp_path):
    folder = tmp_path / "runs"
    folder.mkdir()
    (folder / "a.csv").write_text("step,loss\n0,3\n1,2\n2,1\n")
    (folder / "b.csv").write_text("step,loss\n0,4\n1,3\n2,2\n")
    return folder


def call(editor, path, payload=None, **kwargs):
    code, body = request(editor, path, payload, **kwargs)
    return code, json.loads(body)


def proposed(editor, source, **updates):
    code, catalog = call(editor, "/api/experiments/catalog", {"source": str(source)})
    assert code == 200, catalog
    payload = {
        "source": str(source),
        "snapshot": catalog["snapshot"],
        "runs": [r["id"] for r in catalog["runs"]],
        "metric": "loss",
        "client": "import-owner",
        "generation": 0,
        "data_id": None,
        "palette_id": None,
        "spec": {
            "kind": "line",
            "x": {"field": "old", "label": "Old"},
            "y": {"field": "value", "label": "Value"},
        },
        **updates,
    }
    code, proposal = call(editor, "/api/experiments/review", payload)
    assert code == 200, proposal
    return payload, proposal


def test_existing_http_authorization_and_asset_scope(editor, source):
    assert request(editor, "/experiment-imports.js", token=False)[0] == 200
    for operation in ["catalog", "review", "accept", "cancel"]:
        assert (
            call(editor, "/api/experiments/" + operation, {"source": str(source)}, token=False)[0]
            == 403
        )
        assert (
            call(
                editor,
                "/api/experiments/" + operation,
                {"source": str(source)},
                headers={"Origin": "https://attacker.example"},
            )[0]
            == 403
        )


def test_read_only_review_then_actual_accept_render_and_source_free_bundle(editor, source):
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}
    payload, proposal = proposed(editor, source)
    assert not proposal["applied"] and not proposal["verified"]
    assert not editor.state.uploads and not editor.state.runs
    code, accepted = call(
        editor, "/api/experiments/accept", {**payload, "id": proposal["id"], "reviewed": True}
    )
    assert code == 200, accepted
    assert accepted["report"]["applied"] and not accepted["verified"]
    assert accepted["data"]["rows"] == 6
    code, result = call(
        editor,
        "/api/render",
        {**payload, "data_id": accepted["data"]["id"], "spec": accepted["spec"], "generation": 1},
    )
    assert code == 200 and result["report"]["status"] == "passed", result
    code, raw = request(editor, f"/bundle/{result['run_id']}")
    assert code == 200
    with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
        names = bundle.namelist()
        import_name = next(n for n in names if n.endswith(".experiment-import.json"))
        report = json.loads(bundle.read(import_name))
        assert report["snapshot"] == proposal["report"]["snapshot"] and report["records"] == 6
        assert not any(n.endswith(".csv") for n in names)
    assert before == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}


@pytest.mark.parametrize("change", ["client", "generation", "spec", "data_id"])
def test_review_cannot_apply_to_another_editor_context(editor, source, change):
    payload, proposal = proposed(editor, source)
    altered = {**payload, "id": proposal["id"], "reviewed": True}
    altered[change] = {
        "client": "other-owner",
        "generation": 1,
        "spec": {"kind": "bar"},
        "data_id": "not-owned",
    }[change]
    code, result = call(editor, "/api/experiments/accept", altered)
    assert code == 400 and not editor.state.uploads, result


def test_newer_known_server_generation_refuses_old_proposal(editor, source):
    payload, proposal = proposed(editor, source)
    editor.state.generations[payload["client"]] = 2
    code, result = call(
        editor, "/api/experiments/accept", {**payload, "id": proposal["id"], "reviewed": True}
    )
    assert code == 400 and "newer editor revision" in result["error"]
    assert not editor.state.uploads


def test_actual_source_mutation_after_review_does_not_publish_upload(editor, source):
    payload, proposal = proposed(editor, source)
    with (source / "a.csv").open("a") as out:
        out.write("3,0\n")
    code, result = call(
        editor, "/api/experiments/accept", {**payload, "id": proposal["id"], "reviewed": True}
    )
    assert code == 400 and "changed" in result["error"] and not editor.state.uploads


def test_review_and_exclusion_acknowledgement_are_explicit(editor, source):
    with (source / "a.csv").open("a") as out:
        out.write("3,\n")
    payload, proposal = proposed(editor, source)
    assert proposal["report"]["excluded_records"] == 1
    assert (
        call(
            editor, "/api/experiments/accept", {**payload, "id": proposal["id"], "reviewed": False}
        )[0]
        == 400
    )
    payload, proposal = proposed(editor, source)
    assert (
        call(
            editor, "/api/experiments/accept", {**payload, "id": proposal["id"], "reviewed": True}
        )[0]
        == 400
    )
    assert not editor.state.uploads
    payload, proposal = proposed(editor, source)
    code, result = call(
        editor,
        "/api/experiments/accept",
        {**payload, "id": proposal["id"], "reviewed": True, "accept_exclusions": True},
    )
    assert code == 200 and result["report"]["excluded_records"] == 1 and result["data"]["rows"] == 6
