"""Real session review/native drafts, selection integrity, archives and stale-work fences."""

import copy
import io
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from zipfile import ZipFile

import pytest
from test_preview import editor as editor  # noqa: PLC0414
from test_preview import request

from graphunslopify.autopilot import AutopilotError
from graphunslopify.preview import PreviewState


@pytest.fixture
def session(tmp_path):
    state = PreviewState(tmp_path / "editor", 25 * 1024 * 1024)
    original = b"model,loss\n001,1\n001,3\n002,2\n002,4\n001,\n"
    data = state.upload("observations.csv", original)
    payload = {
        "client": "author",
        "generation": 0,
        "data_id": data["id"],
        "palette_id": None,
        "spec": {"kind": "line", "x": {"field": "loss"}, "y": {"field": "loss"}},
        "question": "Compare loss between models",
        "choices": {
            "target": "loss",
            "group": "model",
            "intent": "comparison",
            "units": {"loss": "score"},
        },
    }
    try:
        yield state, payload, original
    finally:
        state.close()


def reviewed(state, payload):
    result = state.autopilot.review(payload)
    assert result["report"]["ready"] and result["id"]
    return {**payload, "id": result["id"], "reviewed": True, "accept_exclusions": True}, result


def generated(state, payload):
    request, proposal = reviewed(state, payload)
    result = state.autopilot.generate(request)
    assert len(result["drafts"]) == 3
    return request, proposal, result


def test_review_leaves_original_editor_unapplied_and_discloses_actual_sample(session):
    state, payload, original = session
    before = copy.deepcopy(payload["spec"])
    result = state.autopilot.review(payload)
    assert result["applied"] is result["verified"] is False
    assert result["report"]["excluded_count"] == 1
    assert result["report"]["excluded_records"][0]["source_record"] == 4
    assert result["report"]["groups"] == ["001", "002"]
    assert result["report"]["choices"]["units"] == {"loss": "score"}
    assert len(result["normalized_sample"]) == 4
    assert [r["group"] for r in result["normalized_sample"]] == ["001", "001", "002", "002"]
    assert len(state.uploads) == 1 and not state.runs
    assert payload["spec"] == before
    assert state.selected_data(payload["data_id"])["path"].read_bytes() == original


def test_numeric_identifier_columns_need_an_explicit_author_mapping(session):
    state, payload, original = session
    result = state.autopilot.review({**payload, "choices": {}})
    assert not result["report"]["ready"] and result["report"]["reason"]
    assert result["id"] is None and result["drafts"] == []
    assert len(state.uploads) == 1
    assert state.selected_data(payload["data_id"])["path"].read_bytes() == original


def test_generation_requires_review_and_exclusions_before_creating_outputs(session):
    state, payload, _ = session
    request, _ = reviewed(state, payload)
    for flags in [{"reviewed": False}, {"accept_exclusions": False}]:
        with pytest.raises(AutopilotError):
            state.autopilot.generate({**request, **flags})
        assert not list(state.autopilot.root.iterdir())


@pytest.mark.parametrize("changed", ["client", "generation", "data", "palette", "spec"])
def test_review_cannot_be_generated_in_another_editor_context(session, changed):
    state, payload, _ = session
    request, _ = reviewed(state, payload)
    if changed == "spec":
        request["spec"] = {**request["spec"], "title": "Newer intent"}
    else:
        key = {"data": "data_id", "palette": "palette_id"}.get(changed, changed)
        request[key] = 1 if key == "generation" else "different"
    with pytest.raises(AutopilotError, match="different editor"):
        state.autopilot.generate(request)
    assert not list(state.autopilot.root.iterdir())


def test_all_three_real_drafts_selection_native_ancestry_and_explicit_data_archive(session):
    state, payload, original = session
    request, proposal, result = generated(state, payload)
    assert result["status"] == "passed" and all(d["status"] == "passed" for d in result["drafts"])
    assert all(d["native_report"]["policy"]["strict"] for d in result["drafts"])
    for draft in result["drafts"]:
        assert draft["preview_url"] and draft["why"] and draft["tradeoff"]
    assert len(state.uploads) == 1
    for include in [False, True]:
        saved = state.autopilot.packet({**request, "include_data": include})
        name = saved["url"].rsplit("/", 1)[1]
        with ZipFile(io.BytesIO(state.autopilot.artifact(request["id"], name))) as archive:
            assert ("autopilot-data.json" in archive.namelist()) is include
            report = json.loads(archive.read("autopilot.json"))
            assert len(report["drafts"]) == 3
            assert all(d["status"] == "passed" for d in report["drafts"])
            manifest = json.loads(archive.read("comparison-manifest.json"))
            assert manifest["files"]["autopilot-data.json"]["included"] is include
            assert "observations.csv" not in archive.namelist()
    with pytest.raises(AutopilotError, match="explicit"):
        state.autopilot.artifact(request["id"], "autopilot-data.json")
    selection = state.autopilot.select({**request, "draft_id": "quartiles"})
    assert selection["verified"] is False
    ancestry = selection["report"]
    assert ancestry["chosen_draft"] == "quartiles"
    assert len(ancestry["comparison"]["drafts"]) == 3
    assert ancestry["comparison"]["proposal"]["snapshot"] == proposal["report"]["snapshot"]
    normal = state.render(
        {**payload, "data_id": selection["data"]["id"], "spec": selection["spec"]}
    )
    assert normal["report"]["status"] == "passed"
    with ZipFile(io.BytesIO(state.bundle(normal["run_id"], False))) as archive:
        names = [n for n in archive.namelist() if n.endswith(".autopilot.json")]
        assert len(names) == 1
        assert json.loads(archive.read(names[0])) == ancestry
        assert "data.json" not in archive.namelist()
    assert state.selected_data(payload["data_id"])["path"].read_bytes() == original
    with pytest.raises(AutopilotError, match="already selected"):
        state.autopilot.select({**request, "draft_id": "means"})
    # Applying changes the editor generation, but recorded comparisons remain exportable.
    state.generations["author"] = 2
    assert state.autopilot.packet(request)["url"].endswith("comparison.zip")


@pytest.mark.parametrize("changed", ["source", "normalized", "native-export"])
def test_changed_actual_inputs_or_outputs_refuse_selection_before_new_upload(session, changed):
    state, payload, _ = session
    request, _, _ = generated(state, payload)
    if changed == "source":
        path = state.selected_data(payload["data_id"])["path"]
    elif changed == "normalized":
        path = state.autopilot.root / request["id"] / "autopilot-data.json"
    else:
        path = next((state.autopilot.root / request["id"]).rglob("*.png"))
    with path.open("ab") as stream:
        stream.write(b" ")
    before = len(state.uploads)
    with pytest.raises(AutopilotError, match="changed"):
        state.autopilot.select({**request, "draft_id": "quartiles"})
    assert len(state.uploads) == before


def test_selected_worksheet_is_actual_upload_binding_not_a_requested_other_sheet(session, tmp_path):
    import pandas as pd

    state, payload, _ = session
    workbook = tmp_path / "two.xlsx"
    with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
        pd.DataFrame({"unused": [1]}).to_excel(writer, sheet_name="Ignore", index=False)
        pd.DataFrame({"model": ["A", "A", "B", "B"], "loss": [1, 3, 2, 4]}).to_excel(
            writer, sheet_name="Measured", index=False
        )
    uploaded = state.upload(workbook.name, workbook.read_bytes())
    with pytest.raises(ValueError, match="worksheet"):
        state.autopilot.review({**payload, "data_id": uploaded["id"]})
    selected = state.select_sheet(uploaded["id"], "Measured")
    request = {**payload, "data_id": selected["id"]}
    result = state.autopilot.review(request)
    assert result["report"]["choices"]["sheet"] == "Measured"
    assert result["report"]["selected_rows"] == 4
    with pytest.raises(AutopilotError, match="actually selected"):
        state.autopilot.review({**request, "choices": {"sheet": "Ignore"}})


def test_unready_comparison_discloses_refusal_without_a_generatable_review(session):
    state, payload, _ = session
    data = state.upload("one-group.csv", b"model,loss\nA,1\nA,2\n")
    result = state.autopilot.review({**payload, "data_id": data["id"]})
    assert result["id"] is None and not result["report"]["ready"] and not result["drafts"]
    assert "two retained groups" in result["report"]["reason"]
    assert not list(state.autopilot.root.iterdir())


def test_real_failed_native_draft_is_retained_and_cannot_be_selected(session):
    state, payload, _ = session
    a, b = "A" * 250, "B" * 250
    source = ("model,loss\n" + "\n".join(f"{g},{v}" for g in [a, b] for v in [1, 2, 3])).encode()
    data = state.upload("long-groups.csv", source)
    request, _, result = generated(state, {**payload, "data_id": data["id"]})
    statuses = {d["id"]: d["status"] for d in result["drafts"]}
    assert statuses == {"quartiles": "passed", "empirical": "failed", "means": "passed"}
    assert result["status"] == "incomplete" and result["exit_code"] == 2
    before = len(state.uploads)
    with pytest.raises(AutopilotError, match="passed"):
        state.autopilot.select({**request, "draft_id": "empirical"})
    assert len(state.uploads) == before
    selected = state.autopilot.select({**request, "draft_id": "means"})
    assert selected["report"]["comparison"]["drafts"][1]["status"] == "failed"


@pytest.mark.parametrize("superseded", ["cancel", "newer-generation"])
def test_completed_native_work_cannot_publish_after_cancellation_or_newer_intent(
    session, monkeypatch, superseded
):
    import graphunslopify.preview_autopilot as module

    state, payload, original = session
    request, _ = reviewed(state, payload)
    actual = module.generate_drafts
    entered, release = threading.Event(), threading.Event()

    def held(*args, **kwargs):
        result = actual(*args, **kwargs)
        assert len(result["drafts"]) == 3
        entered.set()
        assert release.wait(30)
        return result

    monkeypatch.setattr(module, "generate_drafts", held)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(state.autopilot.generate, request)
        try:
            assert entered.wait(60)
            with pytest.raises(AutopilotError, match="already running"):
                state.autopilot.generate(request)
            if superseded == "cancel":
                state.autopilot.cancel(request)
            else:
                state.generations["author"] = 1
        finally:
            release.set()
        with pytest.raises(AutopilotError, match=r"cancelled|newer"):
            future.result(timeout=30)
    assert len(state.uploads) == 1
    assert state.selected_data(payload["data_id"])["path"].read_bytes() == original
    with pytest.raises(AutopilotError):
        state.autopilot.select({**request, "draft_id": "quartiles"})


def test_closed_session_refuses_even_an_unready_review_before_reading(session, monkeypatch):
    state, payload, _ = session
    data = state.upload("one-group.csv", b"model,loss\nA,1\nA,2\n")
    state.autopilot.close()

    def forbidden(*args):
        pytest.fail("A closed session started a dataset reader")

    monkeypatch.setattr(state.autopilot, "_analyze", forbidden)
    with pytest.raises(AutopilotError, match="closed"):
        state.autopilot.review({**payload, "data_id": data["id"]})


@pytest.mark.parametrize("ready", [False, True])
def test_close_during_actual_read_cannot_return_a_new_review(session, monkeypatch, ready):
    state, payload, _ = session
    if not ready:
        data = state.upload("one-group.csv", b"model,loss\nA,1\nA,2\n")
        payload = {**payload, "data_id": data["id"]}
    actual = state.autopilot._analyze
    entered, release = threading.Event(), threading.Event()

    def held(*args):
        result = actual(*args)
        assert result.report["ready"] is ready
        entered.set()
        assert release.wait(30)
        return result

    monkeypatch.setattr(state.autopilot, "_analyze", held)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(state.autopilot.review, payload)
        try:
            assert entered.wait(30)
            state.autopilot.close()
        finally:
            release.set()
        with pytest.raises(AutopilotError, match="closed"):
            future.result(timeout=30)
    assert not state.autopilot.plans


def test_cancel_and_idle_expiry_release_review_quota(session):
    state, payload, _ = session
    identities = [state.autopilot.review(payload)["id"] for _ in range(8)]
    with pytest.raises(AutopilotError, match="Eight pending"):
        state.autopilot.review(payload)
    state.autopilot.cancel({**payload, "id": identities[0]})
    replacement = state.autopilot.review(payload)["id"]
    assert replacement and len(state.autopilot.plans) == 8
    for plan in state.autopilot.plans.values():
        plan["created"] -= 601
    assert state.autopilot.review(payload)["id"]
    assert len(state.autopilot.plans) == 1


def test_expired_artifacts_cannot_bypass_idle_cleanup(session):
    state, payload, _ = session
    context, _, result = generated(state, payload)
    folder = state.autopilot.root / context["id"]
    name = next(n for n in state.autopilot.plans[context["id"]]["files"] if n.endswith(".png"))
    assert state.autopilot.artifact(context["id"], name).startswith(b"\x89PNG")
    state.autopilot.plans[context["id"]]["created"] -= 601
    with pytest.raises(AutopilotError, match="no longer available"):
        state.autopilot.artifact(context["id"], name)
    assert not folder.exists() and not state.autopilot.plans
    assert len(result["drafts"]) == 3 and len(state.uploads) == 1


def test_http_assets_endpoints_and_actual_draft_files_keep_authorization(editor):
    assert request(editor, "/autopilot.js", token=False)[0] == 200
    bad_origin = {"Origin": "https://attacker.example"}
    bad_host = {"Host": "attacker.example"}
    assert request(editor, "/autopilot.js", token=False, headers=bad_origin)[0] == 403
    for operation in ["review", "generate", "select", "cancel", "packet"]:
        endpoint = "/api/autopilot/" + operation
        assert request(editor, endpoint, {}, token=False)[0] == 403
        assert request(editor, endpoint, {}, headers=bad_origin)[0] == 403
        assert request(editor, endpoint, {}, headers=bad_host)[0] == 403
    data = editor.state.upload("owned.csv", b"model,loss\nA,1\nA,3\nB,2\nB,4\n")
    context = {
        "client": "http-author",
        "generation": 0,
        "data_id": data["id"],
        "palette_id": None,
        "spec": {"kind": "line", "x": {"field": "loss"}, "y": {"field": "loss"}},
        "question": "Compare loss between models",
    }
    status, raw = request(editor, "/api/autopilot/review", context)
    assert status == 200, raw
    identity = json.loads(raw)["id"]
    status, raw = request(
        editor, "/api/autopilot/generate", {**context, "id": identity, "reviewed": True}
    )
    assert status == 200, raw
    result = json.loads(raw)
    path = result["drafts"][0]["preview_url"]
    assert request(editor, path)[1].startswith(b"\x89PNG")
    for kwargs in [{"token": False}, {"headers": bad_origin}, {"headers": bad_host}]:
        assert request(editor, path, **kwargs)[0] == 403
    assert request(editor, f"/autopilot-artifact/{identity}/autopilot-data.json")[0] == 404
    assert request(editor, "/autopilot-artifact/unowned/export.png")[0] == 404
    assert request(editor, f"/autopilot-artifact/{identity}/..%2F..%2Fetc%2Fpasswd")[0] == 404
