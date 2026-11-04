"""Real editor HTTP ownership, reviewed source/data snapshots and native provenance."""

import base64
import hashlib
import io
import json
import zipfile

import pytest
from test_preview import editor as editor  # noqa: PLC0414
from test_preview import request

SOURCE = b"import matplotlib.pyplot as plt\nplt.plot([0,1,2],[3,2,1],label='Model')\nplt.legend()\n"


def call(editor, path, payload=None, **kwargs):
    status, body = request(editor, path, payload, **kwargs)
    return status, json.loads(body)


def proposed(editor, source=SOURCE, **updates):
    payload = {
        "client": "source-owner",
        "generation": 0,
        "data_id": None,
        "palette_id": None,
        "spec": {"kind": "line", "x": {"field": "old"}, "y": {"field": "old"}},
        "source_name": "owned.py",
        "source_base64": base64.b64encode(source).decode(),
        **updates,
    }
    code, proposal = call(editor, "/api/sources/review", payload)
    assert code == 200, proposal
    return payload, proposal


def test_source_asset_and_http_authorization(editor):
    assert request(editor, "/source-imports.js", token=False)[0] == 200
    for operation in ["review", "accept", "cancel"]:
        path = "/api/sources/" + operation
        assert request(editor, path, {}, token=False)[0] == 403
        assert request(editor, path, {}, headers={"Origin": "https://attacker.example"})[0] == 403


def test_review_apply_native_bundle_keeps_original_separate(editor):
    payload, proposal = proposed(editor)
    assert not proposal["applied"] and not proposal["verified"]
    assert not editor.state.uploads and not editor.state.runs
    code, accepted = call(
        editor, "/api/sources/accept", {**payload, "id": proposal["id"], "reviewed": True}
    )
    assert code == 200 and not accepted["verified"], accepted
    record = editor.state.uploads[accepted["data"]["id"]]
    assert record["source_original"].read_bytes() == SOURCE
    code, native = call(
        editor,
        "/api/render",
        {**payload, "generation": 1, "data_id": accepted["data"]["id"], "spec": accepted["spec"]},
    )
    assert code == 200 and native["report"]["status"] == "passed", native
    code, raw = request(editor, f"/bundle/{native['run_id']}")
    assert code == 200
    with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
        name = next(n for n in bundle.namelist() if n.endswith(".source-import.json"))
        report = json.loads(bundle.read(name))
        assert report["original_sha256"] == hashlib.sha256(SOURCE).hexdigest()
        assert not report["source_executed"] and report["applied"]
        assert not any(n.endswith(".csv") or "original-source" in n for n in bundle.namelist())


@pytest.mark.parametrize(
    "change,value", [("client", "other"), ("generation", 1), ("spec", {}), ("data_id", "other")]
)
def test_source_context_fences(editor, change, value):
    payload, proposal = proposed(editor)
    code, result = call(
        editor,
        "/api/sources/accept",
        {**payload, "id": proposal["id"], "reviewed": True, change: value},
    )
    assert code == 400 and not editor.state.uploads, result


def test_source_cancel_expiry_close_and_newer_generation(editor):
    payload, proposal = proposed(editor)
    call(editor, "/api/sources/cancel", {**payload, "id": proposal["id"]})
    assert (
        call(editor, "/api/sources/accept", {**payload, "id": proposal["id"], "reviewed": True})[0]
        == 400
    )
    payload, proposal = proposed(editor)
    editor.state.sources.plans[proposal["id"]]["created"] -= 601
    assert (
        call(editor, "/api/sources/accept", {**payload, "id": proposal["id"], "reviewed": True})[0]
        == 400
    )
    payload, proposal = proposed(editor)
    editor.state.generations[payload["client"]] = 4
    assert (
        call(editor, "/api/sources/accept", {**payload, "id": proposal["id"], "reviewed": True})[0]
        == 400
    )
    editor.state.sources.close()
    assert call(editor, "/api/sources/review", payload)[0] == 400
    assert not editor.state.uploads


def test_source_partial_and_review_acknowledgement(editor):
    source = SOURCE + b"plt.savefig('ignored.png')\n"
    for updates in [{"reviewed": False}, {"reviewed": True}]:
        payload, proposal = proposed(editor, source)
        assert proposal["report"]["requires_partial_review"]
        assert (
            call(editor, "/api/sources/accept", {**payload, "id": proposal["id"], **updates})[0]
            == 400
        )
        assert not editor.state.uploads
    payload, proposal = proposed(editor, source)
    assert (
        call(
            editor,
            "/api/sources/accept",
            {**payload, "id": proposal["id"], "reviewed": True, "accept_partial": True},
        )[0]
        == 200
    )


def test_mapped_csv_is_explicit_and_rechecked(editor):
    info = json.loads(
        request(editor, "/api/upload", b"x,y\n0,3\n1,2\n", headers={"X-Filename": "bound.csv"})[1]
    )
    source = b"import pandas as pd\nimport matplotlib.pyplot as plt\ndf=pd.read_csv('/unread/private.csv')\nplt.plot(df['x'],df['y'])\n"
    _, refused = proposed(editor, source, data_id=info["id"])
    assert not refused["report"]["convertible"] and refused["id"] is None
    payload, proposal = proposed(editor, source, data_id=info["id"], map_current_data=True)
    assert proposal["report"]["convertible"]
    editor.state.uploads[info["id"]]["path"].write_bytes(b"x,y\n0,99\n1,98\n")
    code, result = call(
        editor, "/api/sources/accept", {**payload, "id": proposal["id"], "reviewed": True}
    )
    assert code == 400 and "changed" in result["error"] and len(editor.state.uploads) == 1


def test_source_proposal_quota_and_invalid_bytes(editor):
    for _ in range(8):
        proposed(editor)
    payload, _ = proposed(editor, b"# unsupported but harmless\n")
    assert (
        call(
            editor,
            "/api/sources/review",
            {**payload, "source_base64": base64.b64encode(SOURCE).decode()},
        )[0]
        == 400
    )
    assert call(editor, "/api/sources/review", {**payload, "source_base64": "!notbase64"})[0] == 400
    assert call(editor, "/api/sources/review", {**payload, "source_base64": "x" * 350000})[0] == 400


def test_newer_revision_during_acceptance_read_is_rechecked(editor, monkeypatch):
    payload, proposal = proposed(editor)
    analyze = editor.state.sources._analyze

    def later(*args):
        result = analyze(*args)
        editor.state.generations[payload["client"]] = 3
        return result

    monkeypatch.setattr(editor.state.sources, "_analyze", later)
    assert (
        call(editor, "/api/sources/accept", {**payload, "id": proposal["id"], "reviewed": True})[0]
        == 400
    )
    assert not editor.state.uploads
