"""The local editor must not turn uploaded intent into arbitrary filesystem access."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path
from zipfile import ZipFile

import pytest

from graphunslopify import preview


@pytest.fixture
def native_workbook():
    pytest.importorskip("python_calamine")
    return (Path(__file__).parent / "fixtures/worksheet-experiments.xlsx").read_bytes()


def upload_workbook(editor, content):
    status, body = request(
        editor, "/api/upload", content, headers={"X-Filename": "experiments.xlsx"}
    )
    assert status == 200, body
    return json.loads(body)


def select_workbook(editor, uploaded, sheet):
    status, body = request(editor, "/api/select-sheet", {"data_id": uploaded["id"], "sheet": sheet})
    assert status == 200, body
    return json.loads(body)


@pytest.fixture
def editor():
    with preview.PreviewServer(0, max_upload_mb=1) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            thread.join(5)


def request(server, path, payload=None, *, token=True, headers=None):
    root = f"http://127.0.0.1:{server.server_address[1]}"
    headers = {**(headers or {})}
    if token:
        headers["X-Preview-Token"] = server.state.token
    if isinstance(payload, dict):
        payload = json.dumps(payload).encode()
    call = urllib.request.Request(root + path, data=payload, headers=headers)
    try:
        response = urllib.request.urlopen(call, timeout=20)
    except urllib.error.HTTPError as problem:
        response = problem
    with response:
        return response.code, response.read()


def test_loopback_origin_token_and_asset_boundaries(editor):
    status, html = request(editor, "/", token=False)
    assert status == 200
    assert b"Make the figure" in html and editor.state.token.encode() in html
    assert request(editor, "/app.js", token=False)[0] == 200
    assert (
        request(editor, "/controls.js", token=False)[1]
        == preview.files("graphunslopify").joinpath("web/controls.js").read_bytes()
    )
    assert (
        request(editor, "/text-editing.js", token=False)[1]
        == preview.files("graphunslopify").joinpath("web/text-editing.js").read_bytes()
    )
    assert request(editor, "/api/info", token=False)[0] == 403
    assert request(editor, "/api/demo", {}, token=False)[0] == 403
    assert request(editor, "/api/demo", {}, headers={"Origin": "https://example.org"})[0] == 403
    assert request(editor, "/", headers={"Host": "attacker.example"})[0] == 403
    assert request(editor, "/artifact/unknown/../../etc/passwd")[0] == 404
    info = json.loads(request(editor, "/api/info")[1])
    assert len(info["kinds"]) == 21 and len(info["recipes"]) == 25
    assert {branch["properties"]["kind"]["const"] for branch in info["schema"]["oneOf"]} == set(
        info["kinds"]
    )
    assert not editor.state.uploads


def test_uploaded_paths_are_owned_and_dataset_not_downloadable(editor, tmp_path):
    external = tmp_path / "private.csv"
    external.write_text("do not read")
    status, result = request(
        editor,
        "/api/upload",
        b"epoch,score\n1,51\n2,52\n",
        headers={"X-Filename": "../../private.csv"},
    )

    assert status == 200
    uploaded = json.loads(result)
    assert uploaded["name"] == "private.csv"
    spec = {
        "kind": "line",
        "data": {"path": str(external)},
        "x": {"field": "epoch", "label": "Epoch"},
        "y": {"field": "score", "label": "Score"},
    }
    prepared, data, _ = editor.state.prepare({"spec": spec, "data_id": uploaded["id"]})
    assert prepared["data"]["path"] == "data.csv"
    assert prepared["data"]["columns"] == ["epoch", "score"]
    assert Path(data["path"]).is_relative_to(editor.state.root)
    assert external.read_text() == "do not read"
    assert request(editor, f"/artifact/{uploaded['id']}/data.csv")[0] == 404
    for stem in ("../../outside", "/tmp/outside", "subdir/file", 'bad"header', "CON"):
        spec["output"] = {"stem": stem}
        status, result = request(editor, "/api/validate", {"spec": spec, "data_id": uploaded["id"]})
        # Windows reserved names are also rejected on POSIX for portable bundles.
        assert status == 400, result
    spec.pop("output")
    spec["palette_lock"] = str(external)
    assert request(editor, "/api/validate", {"spec": spec, "data_id": uploaded["id"]})[0] == 400
    assert request(editor, "/api/upload", b"x", headers={"X-Filename": "bad.py"})[0] == 400
    assert (
        request(
            editor,
            "/api/upload",
            b"x",
            headers={"X-Filename": "large.csv", "Content-Length": str(1024 * 1024 + 1)},
        )[0]
        == 400
    )


def test_upload_exposes_safe_profile_facts_and_preserves_original_bytes(editor):
    content = b"group,value\na,2\nb,inf\nc,-inf\nd,\ne,4\n"
    status, body = request(editor, "/api/upload", content, headers={"X-Filename": "values.csv"})
    assert status == 200, body
    uploaded = json.loads(body)
    profile = uploaded["profile"]
    assert profile["path"] == "data.csv" and profile["rows"] == 5
    value = next(c for c in profile["columns"] if c["name"] == "value")
    assert value["non_missing"] == 4 and value["finite"] == 2 and value["missing"] == 1
    assert value["mean"] == 3
    assert editor.state.uploads[uploaded["id"]]["path"].read_bytes() == content
    assert request(editor, "/api/suggest", {"data_id": uploaded["id"]})[0] == 200


@pytest.mark.parametrize(
    "filename,content,palette",
    [("bad.csv", b'"unterminated', False), ("bad.json", b"not json", True)],
)
def test_failed_upload_leaves_no_published_identity_or_orphaned_files(
    editor, filename, content, palette
):
    before = dict(editor.state.uploads)
    folder = editor.state.root / "uploads"
    existing = set(folder.iterdir()) if folder.exists() else set()
    with pytest.raises((ValueError, TypeError)):
        editor.state.upload(filename, content, palette=palette)
    assert editor.state.uploads == before and set(folder.iterdir()) == existing


def test_workbook_staging_requires_selection_and_existing_auth(editor, native_workbook):
    uploaded = upload_workbook(editor, native_workbook)
    assert uploaded["requires_sheet"] and uploaded["profile"] is None
    assert uploaded["sheets"] == ["Control experiment", "Measured results"]
    assert uploaded["columns"] == [] and uploaded["rows"] is None
    payload = {"data_id": uploaded["id"], "sheet": "Measured results"}
    assert request(editor, "/api/select-sheet", payload, token=False)[0] == 403
    assert (
        request(editor, "/api/select-sheet", payload, headers={"Origin": "https://example.org"})[0]
        == 403
    )
    for route in ["/api/suggest", "/api/validate"]:
        code, body = request(editor, route, {"data_id": uploaded["id"], "spec": {}})
        assert code == 400 and b"Choose a worksheet" in body
    for sheet in ["../other.xlsx", "", None, 0]:
        assert (
            request(editor, "/api/select-sheet", {"data_id": uploaded["id"], "sheet": sheet})[0]
            == 400
        )
    assert len(editor.state.uploads) == 1
    assert editor.state.uploads[uploaded["id"]]["path"].read_bytes() == native_workbook


def test_worksheet_selections_have_immutable_owned_bindings(editor, native_workbook):
    uploaded = upload_workbook(editor, native_workbook)
    measured = select_workbook(editor, uploaded, "Measured results")
    control = select_workbook(editor, uploaded, "Control experiment")
    assert len({uploaded["id"], measured["id"], control["id"]}) == 3
    assert measured["workbook_id"] == control["workbook_id"] == uploaded["id"]
    assert measured["profile"]["path"] == "data.xlsx" and measured["format"] == "excel"
    for selected, expected in [(measured, 31 / 3), (control, 910)]:
        assert next(c for c in selected["columns"] if c["name"] == "score")[
            "mean"
        ] == pytest.approx(expected)
    prepared, _, _ = editor.state.prepare(
        {
            "data_id": measured["id"],
            "spec": {"data": {"sheet": "Control experiment", "path": "/private/other.xlsx"}},
        }
    )
    assert prepared["data"] == {
        "path": "data.xlsx",
        "format": "excel",
        "columns": ["subject", "score"],
        "sheet": "Measured results",
    }
    candidates = json.loads(request(editor, "/api/suggest", {"data_id": measured["id"]})[1])
    assert candidates and all(
        item["spec"]["data"]["sheet"] == "Measured results" for item in candidates
    )
    assert editor.state.uploads[uploaded["id"]]["profile"] is None
    assert editor.state.uploads[measured["id"]]["profile"]["sheet"] == "Measured results"


def test_native_workbook_render_bundle_consent_and_extracted_reproduction(
    editor, native_workbook, tmp_path
):
    uploaded = upload_workbook(editor, native_workbook)
    selected = select_workbook(editor, uploaded, "Measured results")
    spec = {
        "kind": "bar",
        "x": {"field": "subject", "label": "Subject"},
        "y": {"field": "score", "label": "Score", "unit": "points"},
        "aggregation": "none",
        "legend": {"show": False},
        "output": {"stem": "experiment", "formats": ["png", "svg", "pdf"], "dpi": 100},
    }
    code, body = request(
        editor,
        "/api/render",
        {"data_id": selected["id"], "spec": spec, "client": "worksheet-proof", "generation": 1},
    )
    result = json.loads(body)
    assert code == 200 and result["exit_code"] == 0, result
    assert result["report"]["spec"]["data"]["sheet"] == "Measured results"
    with ZipFile(io.BytesIO(request(editor, f"/bundle/{result['run_id']}")[1])) as archive:
        assert "data.xlsx" not in archive.namelist()
    with ZipFile(
        io.BytesIO(request(editor, f"/bundle/{result['run_id']}?data=true")[1])
    ) as archive:
        assert archive.read("data.xlsx") == native_workbook
        assert all(
            not Path(name).is_absolute() and ".." not in Path(name).parts
            for name in archive.namelist()
        )
        assert "_graphunslopify/runtime/graphunslopify/figure_runtime.py" in archive.namelist()
        assert "_graphunslopify/runtime/graphunslopify/LICENSE.txt" in archive.namelist()
        archive.extractall(tmp_path)
    again = subprocess.run(
        [sys.executable, "reproduce.py", "--strict", "--json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert again.returncode == 0, again.stderr
    report = json.loads(again.stdout)
    assert report["spec_hash"] == result["report"]["spec_hash"]
    assert report["data"]["sha256_prefix"] == result["report"]["data"]["sha256_prefix"]
    assert (tmp_path / "data.xlsx").read_bytes() == native_workbook


def test_single_worksheet_legacy_upload_is_ready_and_csv_cannot_select_sheets(editor):
    pytest.importorskip("python_calamine")
    content = (Path(__file__).parent / "fixtures/native-values.xls").read_bytes()
    code, body = request(editor, "/api/upload", content, headers={"X-Filename": "legacy.xls"})
    result = json.loads(body)
    assert code == 200 and not result["requires_sheet"]
    assert result["profile"]["sheet"] == "Measurements" and result["sheets"] == ["Measurements"]
    csv = json.loads(
        request(editor, "/api/upload", b"x,y\n1,2\n", headers={"X-Filename": "data.csv"})[1]
    )
    assert request(editor, "/api/select-sheet", {"data_id": csv["id"], "sheet": "Sheet"})[0] == 400


def test_invalid_workbook_leaves_no_published_or_orphaned_upload(editor):
    pytest.importorskip("python_calamine")
    code, _ = request(editor, "/api/upload", b"not a workbook", headers={"X-Filename": "bad.xlsx"})
    assert code == 400 and not editor.state.uploads
    assert list((editor.state.root / "uploads").iterdir()) == []


def test_static_failure_blocks_execution_and_fixes_are_verifier_owned(editor, monkeypatch):
    _, body = request(editor, "/api/demo", {})
    demo = json.loads(body)
    spec = demo["spec"]
    spec["y"]["temporal"] = True
    payload = {"spec": spec, "data_id": demo["data"]["id"], "client": "contract", "generation": 1}

    def forbidden(*args, **kwargs):
        pytest.fail("Static error reached renderer")

    monkeypatch.setattr(preview, "_run", forbidden)
    status, body = request(editor, "/api/render", payload)
    assert status == 200
    result = json.loads(body)
    assert result["translation"]["ok"] is False
    assert result["report"] is None and result["run_id"] is None
    assert not editor.state.runs
    status, body = request(
        editor,
        "/api/fix",
        {**payload, "code": "temporal_y_axis", "patch": {"output": {"stem": "/tmp/evil"}}},
    )
    assert status == 200
    fixed = json.loads(body)
    assert fixed["spec"]["y"]["temporal"] is False
    assert fixed["spec"]["output"]["stem"] == "figure"
    assert request(editor, "/api/fix", {**payload, "code": "invented_patch"})[0] == 400
    editor.state.generations["contract"] = 5
    payload["spec"]["y"]["temporal"] = False
    stale = editor.state.render(payload)
    assert stale == {"generation": 1, "stale": True}
