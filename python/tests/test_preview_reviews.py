"""Real native editor executions, exact reviewer HTTP, and evidence ownership."""

from __future__ import annotations

import gc
import hashlib
import json
import shutil
import threading
import weakref
from types import SimpleNamespace

import pytest
from test_preview import request
from test_review_agent import proposal

from graphunslopify import preview_reviews
from graphunslopify.drafts import _encoded
from graphunslopify.preview import PreviewServer
from graphunslopify.review_agent import restore_plan, review_document

pytest_plugins = ("test_preview", "test_review_agent")


def post(editor, route, payload, expected=200):
    code, raw = request(editor, route, payload)
    assert code == expected, raw.decode()
    return json.loads(raw)


@pytest.fixture
def native(editor):
    demo = post(editor, "/api/demo", {})
    demo["spec"]["output"]["formats"] = ["png"]
    payload = {
        "client": "actual-render-client",
        "generation": 7,
        "data_id": demo["data"]["id"],
        "spec": demo["spec"],
    }
    answer = post(editor, "/api/render", payload)
    assert answer["report"]["status"] == "passed" and answer["exit_code"] == 0
    assert answer["review"]["available"], answer["review"]
    selection = {
        "run_id": answer["run_id"],
        "render_client": payload["client"],
        "render_generation": payload["generation"],
    }
    return answer, selection, payload


def disclose(editor, server, selection, generation=1, **extra):
    text = proposal()
    text["suggestions"][0]["figure_key"] = "figure"
    server.text = json.dumps(text)
    post(
        editor,
        "/api/reviewer/provider",
        {
            "endpoint": server.endpoint,
            "model": "controlled-native-review",
            "api_key": "KEY_MARKER",
        },
    )
    collection = post(editor, "/api/reviewer/collection", selection)
    return post(
        editor,
        "/api/reviewer/disclose",
        {
            **selection,
            "client": "reviewer-client",
            "generation": generation,
            "expected_revision": collection["evidence_revision"],
            "figures": ["figure"],
            "question": "What would a skeptical reviewer ask?",
            **extra,
        },
    )


def control(disclosure):
    return {
        "client": "reviewer-client",
        "generation": disclosure["generation"],
        "review_id": disclosure["review_id"],
    }


def start(editor, disclosure):
    return post(
        editor,
        "/api/reviewer/start",
        {
            **control(disclosure),
            "consent": True,
            "consent_sha256": disclosure["consent_sha256"],
        },
        202,
    )


def finish(editor, disclosure):
    worker = editor.state.reviewer.records[disclosure["review_id"]]["worker"]
    worker.join(15)
    assert not worker.is_alive()
    return post(editor, "/api/reviewer/status", control(disclosure))


def test_actual_native_http_consent_result_and_ephemeral_download(editor, native, server):
    answer, selection, _ = native
    disclosure = disclose(editor, server, selection)
    assert disclosure["source_kind"] == "editor-render" and not server.calls
    post(editor, "/api/reviewer/start", {**control(disclosure), "consent": False}, 400)
    assert not server.calls
    download = post(editor, "/api/reviewer/download", {**control(disclosure), "which": "request"})
    assert download["kind"] == "editor-figure-review-request" and not download["replayable"]
    with pytest.raises(ValueError, match="exported reviewer"):
        restore_plan(download, editor.state.root)
    plan = editor.state.reviewer.records[disclosure["review_id"]]["plan"]
    with pytest.raises(ValueError, match="saved paper"):
        review_document(plan)
    assert start(editor, disclosure)["phase"] == "running"
    completed = finish(editor, disclosure)
    assert completed["phase"] == "completed", completed
    result = post(editor, "/api/reviewer/download", {**control(disclosure), "which": "result"})
    assert result == completed["result"]
    assert not result["applied"] and result["scientific_acceptance"] == "not_established"
    evidence = result["deterministic_evidence"]
    assert evidence["project_id"] != editor.state.token
    assert evidence["history_integrity"] == "not_applicable_ephemeral_editor"
    figure = evidence["figures"][0]
    assert figure["evidence_state"] == "ephemeral_native_render"
    assert figure["execution_status"] == answer["report"]["status"]
    assert figure["groups"]["claims"]["items"] == answer["report"]["claims"]
    assert not figure["matches_latest_accepted_inputs"]
    assert len(server.calls) == 1
    raw, headers = server.calls[0]
    assert raw == _encoded(disclosure["request"])
    assert headers["Authorization"] == "Bearer KEY_MARKER"
    for secret in ("KEY_MARKER", editor.state.token, str(editor.state.root)):
        assert secret.encode() not in raw
        assert secret not in json.dumps(download) + json.dumps(result)


def test_native_HTTP_literal_body_and_packet_stay_outside_ephemeral_document(
    editor, native, server
):
    _, selection, _ = native
    disclosure = disclose(editor, server, selection, question="Review Δ ≥ 0; source label café.")
    raw = disclosure["request_body"].encode("utf8")
    assert raw == _encoded(disclosure["request"])
    assert hashlib.sha256(raw).hexdigest() == disclosure["request_sha256"]
    assert len(raw) == disclosure["request_bytes"] and b"\\u0394" in raw
    saved = post(editor, "/api/reviewer/download", {**control(disclosure), "which": "request"})
    assert not saved["replayable"]
    assert "request_body" not in saved["disclosure"]
    assert "deterministic_evidence" not in saved["disclosure"]
    start(editor, disclosure)
    complete = finish(editor, disclosure)
    assert complete["phase"] == "completed"
    assert complete["result"]["deterministic_evidence"] == disclosure["deterministic_evidence"]
    assert server.calls[0][0] == raw


@pytest.mark.parametrize("suffix", ["js", "css"])
def test_native_reviewer_static_assets_preserve_origin_policy(editor, suffix):
    route = "/figure-reviewer." + suffix
    assert request(editor, route, token=False)[0] == 200
    assert (
        request(editor, route, token=False, headers={"Origin": "https://other.invalid"})[0] == 403
    )


def test_strict_failed_claim_stays_failed_in_native_model_result(editor, native, server):
    _, _, payload = native
    spec = json.loads(json.dumps(payload["spec"]))
    spec["claims"][0].update(subject="base", reference="ours")
    failed = post(editor, "/api/render", {**payload, "generation": 8, "spec": spec})
    assert failed["exit_code"] == 2 and failed["report"]["status"] == "failed"
    assert failed["review"]["available"], failed["review"]
    selection = {
        "run_id": failed["run_id"],
        "render_client": payload["client"],
        "render_generation": 8,
    }
    disclosure = disclose(editor, server, selection)
    start(editor, disclosure)
    result = finish(editor, disclosure)["result"]
    assert result["deterministic_evidence"]["recorded_failures"]
    row = result["deterministic_evidence"]["figures"][0]
    assert row["execution_status"] == "failed" and row["policy"]["passed"] is False
    assert row["groups"]["claims"]["items"] == failed["report"]["claims"]
    assert row["evidence_state"] == "ephemeral_needs_review" and row["rerun_recommended"]


@pytest.mark.parametrize(
    "target", ["original-data", "run-data", "script", "report", "spec", "export"]
)
def test_real_bound_file_changes_refuse_before_provider(editor, native, server, target):
    answer, selection, payload = native
    disclosure = disclose(editor, server, selection)
    record = editor.state.runs[answer["run_id"]]
    path = (
        editor.state.uploads[payload["data_id"]]["path"]
        if target == "original-data"
        else record["folder"] / record["data"]
        if target == "run-data"
        else next(
            p
            for n, p in record["files"].items()
            if n.endswith(
                {
                    "script": ".py",
                    "report": ".report.json",
                    "spec": ".figure.json",
                    "export": ".png",
                }[target]
            )
        )
    )
    with path.open("ab") as stream:
        stream.write(b"\nchanged after disclosure\n")
    start(editor, disclosure)
    result = finish(editor, disclosure)
    assert result["phase"] == "failed" and result["result"] is None
    assert not server.calls
    post(editor, "/api/reviewer/download", {**control(disclosure), "which": "result"}, 400)


def test_completed_native_result_is_refused_after_export_changes(editor, native, server):
    answer, selection, _ = native
    disclosure = disclose(editor, server, selection)
    start(editor, disclosure)
    assert finish(editor, disclosure)["phase"] == "completed"
    export = editor.state.runs[answer["run_id"]]["folder"] / "figure.png"
    export.write_bytes(b"changed")
    post(editor, "/api/reviewer/status", control(disclosure), 400)
    post(editor, "/api/reviewer/download", {**control(disclosure), "which": "result"}, 400)
    assert editor.state.reviewer.records[disclosure["review_id"]]["result"] is None


def test_native_renderer_revision_is_distinct_from_reviewer_question_revision(
    editor, native, server
):
    _, selection, _ = native
    disclosure = disclose(editor, server, selection, generation=100)
    start(editor, disclosure)
    assert finish(editor, disclosure)["phase"] == "completed"
    assert editor.state.generations[selection["render_client"]] == 7
    with editor.state.lock:
        editor.state.generations[selection["render_client"]] = 8
    post(editor, "/api/reviewer/collection", selection, 400)
    post(editor, "/api/reviewer/status", control(disclosure), 400)


def test_native_context_change_during_provider_discards_reply(editor, native, server):
    _, selection, _ = native
    disclosure = disclose(editor, server, selection)

    def changed():
        with editor.state.lock:
            editor.state.generations[selection["render_client"]] = 8

    server.on_request = changed
    start(editor, disclosure)
    result = finish(editor, disclosure)
    assert len(server.calls) == 1 and result["phase"] == "failed" and result["result"] is None


def test_unowned_and_client_report_payloads_refuse(editor, native):
    _, selection, _ = native
    for invalid in [
        {**selection, "run_id": "not-owned"},
        {**selection, "render_client": "other-client"},
        {**selection, "render_generation": True},
        {**selection, "report": {"status": "passed"}},
        {**selection, "run_id": []},
    ]:
        post(editor, "/api/reviewer/collection", invalid, 400)
    assert request(editor, "/api/reviewer/collection", selection, token=False)[0] == 403
    assert (
        request(
            editor, "/api/reviewer/collection", selection, headers={"Origin": "https://example.org"}
        )[0]
        == 403
    )
    post(editor, "/api/reviewer/provider", {"api_key": "x" * 66000}, 400)


def test_native_input_change_during_render_keeps_report_but_refuses_review(
    editor, native, monkeypatch
):
    _, _, payload = native
    original = editor.state._run_generated

    def changed(*args):
        result = original(*args)
        with editor.state.uploads[payload["data_id"]]["path"].open("ab") as stream:
            stream.write(b"\n")
        return result

    monkeypatch.setattr(editor.state, "_run_generated", changed)
    answer = post(editor, "/api/render", {**payload, "generation": 8})
    assert answer["report"]["status"] == "passed" and answer["exit_code"] == 0
    assert not answer["review"]["available"]
    post(
        editor,
        "/api/reviewer/collection",
        {
            "run_id": answer["run_id"],
            "render_client": payload["client"],
            "render_generation": 8,
        },
        400,
    )


def test_owned_regular_file_reader_refuses_symlink_and_oversized_file(tmp_path, monkeypatch):
    target = tmp_path / "data.csv"
    target.write_bytes(b"known bytes")
    assert (
        preview_reviews._file(tmp_path, target.name)["sha256"]
        == hashlib.sha256(target.read_bytes()).hexdigest()
    )
    monkeypatch.setattr(preview_reviews, "MAX_FILE_BYTES", 5)
    with pytest.raises(ValueError, match="at most"):
        preview_reviews._file(tmp_path, target.name)
    monkeypatch.setattr(preview_reviews, "MAX_FILE_BYTES", 100)
    link = tmp_path / "link.csv"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("Symlink creation unavailable for this account")
    with pytest.raises(ValueError, match="symlink"):
        preview_reviews._file(tmp_path, link.name)


def test_owned_reader_accepts_distinct_path_and_handle_ctime(tmp_path, monkeypatch):
    target = tmp_path / "data.csv"
    raw = b"unchanged observations\r\n1,2\r\n"
    target.write_bytes(raw)
    original = preview_reviews.os.fstat

    def handle_stat(fd):
        actual = original(fd)
        # CPython3.12 Windows path ctime is creation time; handle ctime is
        # metadata-change time. The identity, size and mtime still agree.
        values = {
            key: getattr(actual, key)
            for key in ("st_mode", "st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        }
        values["st_ctime_ns"] += 1000000000
        return SimpleNamespace(**values)

    monkeypatch.setattr(preview_reviews.os, "fstat", handle_stat)
    assert preview_reviews._file(tmp_path, target.name) == {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


@pytest.mark.parametrize("field", ["st_dev", "st_ino", "st_size", "st_mtime_ns"])
def test_owned_reader_keeps_cross_api_identity_and_content_checks(tmp_path, monkeypatch, field):
    target = tmp_path / "data.csv"
    target.write_bytes(b"unchanged observations")
    original = preview_reviews.os.fstat

    def handle_stat(fd):
        actual = original(fd)
        values = {
            key: getattr(actual, key)
            for key in ("st_mode", "st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        }
        values["st_ctime_ns"] += 1000000000
        values[field] += 1
        return SimpleNamespace(**values)

    monkeypatch.setattr(preview_reviews.os, "fstat", handle_stat)
    with pytest.raises(ValueError, match="changed while opening"):
        preview_reviews._file(tmp_path, target.name)


def test_owned_reader_keeps_handle_metadata_change_check(tmp_path, monkeypatch):
    target = tmp_path / "data.csv"
    target.write_bytes(b"unchanged observations")
    original = preview_reviews.os.fstat
    calls = 0

    def handle_stat(fd):
        nonlocal calls
        calls += 1
        actual = original(fd)
        values = {
            key: getattr(actual, key)
            for key in ("st_mode", "st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        }
        values["st_ctime_ns"] += 1000000000 + calls
        return SimpleNamespace(**values)

    monkeypatch.setattr(preview_reviews.os, "fstat", handle_stat)
    with pytest.raises(ValueError, match="changed while reading"):
        preview_reviews._file(tmp_path, target.name)


def test_owned_reader_keeps_path_metadata_change_check(tmp_path, monkeypatch):
    target = tmp_path / "data.csv"
    target.write_bytes(b"unchanged observations")
    original_fstat = preview_reviews.os.fstat
    original_lstat = type(target).lstat
    calls = 0

    def handle_stat(fd):
        nonlocal calls
        calls += 1
        actual = original_fstat(fd)
        values = {
            key: getattr(actual, key)
            for key in ("st_mode", "st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        }
        values["st_ctime_ns"] += 1000000000
        return SimpleNamespace(**values)

    def path_stat(path, *args, **kwargs):
        actual = original_lstat(path, *args, **kwargs)
        if path != target or calls < 2:
            return actual
        values = {
            key: getattr(actual, key)
            for key in ("st_mode", "st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        }
        values["st_ctime_ns"] += 1
        return SimpleNamespace(**values)

    monkeypatch.setattr(preview_reviews.os, "fstat", handle_stat)
    monkeypatch.setattr(type(target), "lstat", path_stat)
    with pytest.raises(ValueError, match="changed while reading"):
        preview_reviews._file(tmp_path, target.name)


def test_owned_reader_refuses_real_replacement_with_same_bytes_and_mtime(tmp_path, monkeypatch):
    target = tmp_path / "data.csv"
    replacement = tmp_path / "replacement.csv"
    raw = b"same bytes do not imply the same file"
    target.write_bytes(raw)
    replacement.write_bytes(raw)
    before = target.stat()
    preview_reviews.os.utime(replacement, ns=(before.st_atime_ns, before.st_mtime_ns))
    original = preview_reviews.os.open

    def swapped_open(path, flags, *args, **kwargs):
        if path == target:
            replacement.replace(target)
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(preview_reviews.os, "open", swapped_open)
    with pytest.raises(ValueError, match="changed while opening"):
        preview_reviews._file(tmp_path, target.name)


def test_native_shutdown_cancels_real_held_request_before_removing_root(editor, native, server):
    _, selection, _ = native
    disclosure = disclose(editor, server, selection)
    entered, release = threading.Event(), threading.Event()
    root = editor.state.root

    def held():
        assert root.is_dir()
        entered.set()
        assert release.wait(10)

    server.on_request = held
    start(editor, disclosure)
    worker = editor.state.reviewer.records[disclosure["review_id"]]["worker"]
    try:
        assert entered.wait(10)
        editor.server_close()
        assert not worker.is_alive() and not root.exists()
    finally:
        release.set()


def test_failed_shutdown_retains_root_and_successful_retry_cleans(monkeypatch):
    editor = PreviewServer(reuse_renderer=False, reuse_translator=False, staged_preview=False)
    root = editor.state.root
    original = editor.state.reviewer.close

    def refused():
        raise RuntimeError("still closing")

    monkeypatch.setattr(editor.state.reviewer, "close", refused)
    with pytest.raises(RuntimeError, match="still closing"):
        editor.server_close()
    assert root.exists()
    monkeypatch.setattr(editor.state.reviewer, "close", original)
    editor.server_close()
    assert not root.exists()


def test_failed_shutdown_has_no_implicit_directory_removal_at_server_gc(monkeypatch):
    editor = PreviewServer(reuse_renderer=False, reuse_translator=False, staged_preview=False)
    root = editor.state.root
    reference = weakref.ref(editor)

    def refused():
        raise RuntimeError("still closing")

    try:
        with monkeypatch.context() as patch:
            patch.setattr(editor.state.reviewer, "close", refused)
            with pytest.raises(RuntimeError, match="still closing"):
                editor.server_close()
        del editor
        gc.collect()
        assert reference() is None and root.exists()
    finally:
        shutil.rmtree(root)


@pytest.mark.parametrize("target", ["original", "run", "observation"])
def test_actual_palette_snapshot_and_legitimate_extension_then_mutation_refusal(
    editor, native, server, target
):
    _, _, payload = native
    original_bytes = b'{"version":1,"series":{}}'
    palette = editor.state.upload("paper.lock.json", original_bytes, palette=True)
    spec = {**payload["spec"], "palette_lock": "owned lock"}
    answer = post(
        editor,
        "/api/render",
        {**payload, "generation": 8, "spec": spec, "palette_id": palette["id"]},
    )
    assert answer["review"]["available"], answer["review"]
    record = editor.state.runs[answer["run_id"]]
    assert editor.state.uploads[palette["id"]]["path"].read_bytes() == original_bytes
    effective = json.loads((record["folder"] / record["palette"]).read_text())
    assert set(effective["series"]) == {"base", "ours"}
    observed = record["review_evidence"]["palette_read"]
    assert observed["sha256"] == hashlib.sha256(original_bytes).hexdigest()
    selection = {
        "run_id": answer["run_id"],
        "render_client": payload["client"],
        "render_generation": 8,
    }
    disclosure = disclose(editor, server, selection)
    path = (
        editor.state.uploads[palette["id"]]["path"]
        if target == "original"
        else record["folder"] / record["palette"]
        if target == "run"
        else record["folder"] / "figure.review-inputs.json"
    )
    with path.open("ab") as stream:
        stream.write(b"changed")
    start(editor, disclosure)
    result = finish(editor, disclosure)
    assert result["phase"] == "failed" and result["result"] is None and not server.calls


@pytest.mark.parametrize("staged", [True, False])
def test_same_generation_retry_retires_old_render_even_if_new_translation_fails(
    editor, native, server, staged
):
    _, selection, payload = native
    disclosure = disclose(editor, server, selection)
    if not staged:
        editor.state.stages.close()
        editor.state.stages = None
    invalid = {**payload["spec"], "kind": "unsupported"}
    new = post(editor, "/api/render", {**payload, "spec": invalid})
    assert new["run_id"] is None
    start(editor, disclosure)
    assert finish(editor, disclosure)["phase"] == "failed" and not server.calls


def test_another_clients_render_of_same_upload_keeps_original_review_current(
    editor, native, server
):
    _, selection, payload = native
    disclosure = disclose(editor, server, selection)
    another = post(editor, "/api/render", {**payload, "client": "another-render-client"})
    assert another["review"]["available"]
    start(editor, disclosure)
    assert finish(editor, disclosure)["phase"] == "completed"


def test_actual_unused_palette_is_reviewable_without_inventing_a_read(editor, server):
    data = editor.state.upload("simple.csv", b"epoch,score\n1,2\n2,3\n3,4\n")
    palette = editor.state.upload("unused.lock.json", b'{"version":1,"series":{}}', palette=True)
    spec = {
        "kind": "line",
        "x": {"field": "epoch", "label": "Epoch"},
        "y": {"field": "score", "label": "Score"},
        "palette_lock": "owned",
        "output": {"stem": "figure", "formats": ["png"]},
    }
    answer = post(
        editor,
        "/api/render",
        {
            "client": "unused-palette",
            "generation": 1,
            "data_id": data["id"],
            "palette_id": palette["id"],
            "spec": spec,
        },
    )
    assert answer["exit_code"] == 0 and answer["report"]["status"] == "passed"
    assert answer["review"]["available"], answer["review"]
    record = editor.state.runs[answer["run_id"]]
    assert record["review_evidence"]["palette_read"] is None
    observed = json.loads((record["folder"] / "figure.review-inputs.json").read_text())
    assert observed == {"schema_version": 1, "palette_reads": []}
    selection = {
        "run_id": answer["run_id"],
        "render_client": "unused-palette",
        "render_generation": 1,
    }
    disclosure = disclose(editor, server, selection)
    start(editor, disclosure)
    assert finish(editor, disclosure)["phase"] == "completed"


@pytest.mark.parametrize("change", ["before-read", "missing-observation"])
def test_actual_palette_read_change_or_missing_producer_proof_keeps_report_unreviewable(
    editor, native, monkeypatch, change
):
    _, _, payload = native
    palette = editor.state.upload("paper.lock.json", b'{"version":1,"series":{}}', palette=True)
    original = editor.state._run_generated

    def changed(*args):
        folder = args[1]
        if change == "before-read":
            (folder / "palette.lock.json").write_bytes(b'{"version":1,"series":{},"changed":true}')
        result = original(*args)
        if change == "missing-observation":
            (folder / "figure.review-inputs.json").unlink()
        return result

    monkeypatch.setattr(editor.state, "_run_generated", changed)
    answer = post(
        editor,
        "/api/render",
        {
            **payload,
            "generation": 8,
            "palette_id": palette["id"],
            "spec": {**payload["spec"], "palette_lock": "owned"},
        },
    )
    assert answer["exit_code"] == 0 and answer["report"]["status"] == "passed"
    assert not answer["review"]["available"]
    post(
        editor,
        "/api/reviewer/collection",
        {
            "run_id": answer["run_id"],
            "render_client": payload["client"],
            "render_generation": 8,
        },
        400,
    )


def test_actual_native_runtime_failure_has_no_invented_exports_or_pass(editor, native):
    _, _, payload = native
    spec = {**payload["spec"], "filter": [{"field": "epoch", "op": "gt", "value": 100000}]}
    answer = post(editor, "/api/render", {**payload, "generation": 8, "spec": spec})
    assert answer["exit_code"] == 1 and answer["report"]["status"] == "failed"
    assert not answer["report"]["outputs"]
    assert answer["review"]["available"], answer["review"]
    result = post(
        editor,
        "/api/reviewer/collection",
        {
            "run_id": answer["run_id"],
            "render_client": payload["client"],
            "render_generation": 8,
        },
    )
    row = result["figures"][0]
    assert row["execution_status"] == answer["report"]["status"] and row["rerun_recommended"]
    assert not row["policy"]["passed"]
    assert not row["groups"]["reproduction"]["saved_exports_verified"]


def test_shutdown_keeps_active_render_tools_and_files_until_http_handler_finishes(
    editor, native, monkeypatch
):
    _, _, payload = native
    entered, release, closing = threading.Event(), threading.Event(), threading.Event()
    run_original, close_original = editor.state._run_generated, editor.state.begin_close
    results, active, executed = [], [], []
    root = editor.state.root

    def held(*args):
        active.extend(
            [
                editor.state.worker.process.connection.process,
                editor.state.translator.process.connection.process,
            ]
        )
        entered.set()
        assert release.wait(10)
        result = run_original(*args)
        executed.append(editor.state.worker.process.connection.process)
        return result

    def begin_close():
        close_original()
        closing.set()

    monkeypatch.setattr(editor.state, "_run_generated", held)
    monkeypatch.setattr(editor.state, "begin_close", begin_close)
    rendering = threading.Thread(
        target=lambda: results.append(post(editor, "/api/render", {**payload, "generation": 8}))
    )
    shutdown = threading.Thread(target=editor.server_close)
    rendering.start()
    try:
        assert entered.wait(10)
        shutdown.start()
        assert closing.wait(10)
        assert shutdown.is_alive() and root.exists()
        assert all(process.poll() is None for process in active)
    finally:
        release.set()
        rendering.join(15)
        if shutdown.ident is not None:
            shutdown.join(15)
    assert not rendering.is_alive() and not shutdown.is_alive()
    assert results[0]["stale"] and not root.exists()
    assert executed and all(process.poll() is not None for process in [*active, *executed])
