"""Actual bounded Node dispatch must preserve one-shot results and owned recovery."""

from __future__ import annotations

import copy
import gc
import hashlib
import json
import subprocess
import sys
import uuid
import weakref
from concurrent.futures import ThreadPoolExecutor

import pytest

from graphunslopify import translator_worker
from graphunslopify.errors import SpecError
from graphunslopify.translator_worker import TranslatorWorker
from graphunslopify.transport import local_request
from graphunslopify.worker_process import MAX_REQUEST, JsonWorker, WorkerError


@pytest.fixture
def compiler(tmp_path):
    client = TranslatorWorker(tmp_path)
    try:
        yield client
    finally:
        client.close()


def original(operation, payload):
    try:
        return {"ok": True, "result": local_request(operation, payload)}
    except SpecError as error:
        return {"ok": False, "error": str(error)}


def test_mixed_canonical_operations_and_all21_conversion_kinds(compiler):
    recipes = local_request("recipes", {})
    cases = [(r["name"], "convert", copy.deepcopy(r["spec"])) for r in recipes]
    box = next(r["spec"] for r in recipes if r["spec"]["kind"] == "box")
    violin = {k: copy.deepcopy(box[k]) for k in ["x", "y", "data"]}
    violin["kind"] = "violin"
    cases.append(("native-violin", "convert", violin))
    bar = next(r["spec"] for r in recipes if r["name"] == "ablation_bar")
    table = {k: copy.deepcopy(bar[k]) for k in ["x", "y", "data", "aggregation", "uncertainty"]}
    table["kind"] = "table"
    cases.append(("native-table", "convert", table))
    good = next(r["spec"] for r in recipes if r["spec"]["kind"] == "line")
    bad = copy.deepcopy(good)
    bad["x"] = {**bad["x"], "temporal": True, "scale": "log"}
    profile = {
        "path": "actual.csv",
        "columns": [
            {"name": "epoch", "role": "ordinal", "distinct": 30},
            {"name": "score", "role": "measure", "distinct": 50, "finite": 50},
        ],
    }
    cases += [
        ("info", "info", {}),
        ("schema", "schema", {}),
        ("input-schema", "input-schema", {}),
        ("recipes", "recipes", {}),
        ("named-recipe", "recipes", {"name": recipes[0]["name"]}),
        ("validate", "validate", good),
        ("score", "score", good),
        ("repair", "repair", {"spec": bad}),
        ("fix", "fix", {"spec": bad, "code": "temporal_log_axis"}),
        ("suggest", "suggest", {"profile": profile}),
        ("invalid", "convert", {"kind": "unknown"}),
    ]
    expected = {name: local_request(operation, payload) for name, operation, payload in cases}
    kinds, identities, pids = set(), [], []
    for round_number in range(2):
        for name, operation, payload in cases if round_number == 0 else reversed(cases):
            value, trace = compiler.request(operation, payload)
            assert value == expected[name]
            assert trace["mode"] == "worker" and trace["kind"] == "translator"
            assert (
                trace["runtime_source_sha256"]
                == hashlib.sha256(compiler.bundle.read_bytes()).hexdigest()
            )
            identities.append(trace["request_id"])
            pids.append(trace["pid"])
            if operation == "convert" and name != "invalid":
                kinds.add(value["resolved"]["kind"] if "resolved" in value else payload["kind"])
    assert len(kinds) == 21 and len(set(identities)) == len(identities)
    assert len(set(pids)) == 2  # More than64 requests actually recycles the process.


def test_application_errors_preserve_same_worker_and_original_error(compiler):
    _, first = compiler.request("info", {})
    for operation, payload in [
        ("unknown-operation", {}),
        ("suggest", {"profile": {"columns": "bad"}}),
    ]:
        expected = original(operation, payload)
        assert not expected["ok"]
        with pytest.raises(SpecError) as problem:
            compiler.call(operation, payload)
        assert str(problem.value) == expected["error"]
    assert compiler.call("info")["version"] == local_request("info")["version"]
    _, last = compiler.request("info")
    assert last["pid"] == first["pid"] and last["request_number"] == 5


def test_compiler_request_bound_and_terminal_close(tmp_path):
    client = TranslatorWorker(tmp_path, max_requests=2)
    try:
        pids = [client.request("info")[1]["pid"] for _ in range(3)]
        assert pids[0] == pids[1] and pids[2] != pids[1]
        owned = client.process.connection.process
    finally:
        client.close()
    assert owned.poll() is not None
    with pytest.raises(SpecError, match="closed"):
        client.call("info")


def test_compiler_crash_and_environment_change_restart(compiler, monkeypatch):
    _, first = compiler.request("info")
    owned = compiler.process.connection.process
    owned.kill()
    owned.wait(timeout=5)
    _, recovered = compiler.request("info")
    assert recovered["pid"] != first["pid"]
    monkeypatch.setenv("GU_COMPILER_ENV_TEST", "changed")
    _, changed = compiler.request("info")
    assert changed["pid"] != recovered["pid"] and changed["process_started"]


def test_compiler_startup_timeout_never_publishes_a_result(compiler):
    command = compiler.process.command[:]
    compiler.process.command = [str(compiler.node), "-e", "setTimeout(()=>{},60000)"]
    with pytest.raises(SpecError, match="timed out"):
        compiler.request("info", timeout=0.1)
    assert compiler.process.connection is None
    compiler.process.command = command
    assert compiler.call("info")["version"] == local_request("info")["version"]


def test_compiler_source_change_closes_owned_runtime(compiler, monkeypatch):
    compiler.call("info")
    owned = compiler.process.connection.process
    monkeypatch.setattr(translator_worker, "_digest", lambda _: "0" * 64)
    with pytest.raises(SpecError, match="source/runtime changed"):
        compiler.call("info")
    assert owned.poll() is not None


def test_compiler_runtime_selection_change_is_not_silently_ignored(compiler, monkeypatch):
    from pathlib import Path

    compiler.call("info")
    owned = compiler.process.connection.process
    monkeypatch.setattr(
        translator_worker, "_node_executable", lambda: Path(sys.executable).resolve()
    )
    with pytest.raises(SpecError, match="source/runtime changed"):
        compiler.call("info")
    assert owned.poll() is not None


def test_compiler_concurrent_responses_have_distinct_correct_owners(compiler):
    recipes = local_request("recipes", {})[:4]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda r: compiler.request("convert", r["spec"]), recipes))
    for recipe, (value, _) in zip(recipes, results, strict=True):
        assert value == local_request("convert", recipe["spec"])
    assert len({trace["request_id"] for _, trace in results}) == 4
    assert len({trace["pid"] for _, trace in results}) == 1


def test_compiler_owner_collection_stops_process_without_reference_cycle(tmp_path):
    client = TranslatorWorker(tmp_path)
    client.call("info")
    owned = client.process.connection.process
    reference = weakref.ref(client)
    del client
    gc.collect()
    assert reference() is None and owned.poll() is not None


@pytest.mark.parametrize(
    "raw",
    [b"not-json\n", b"\xff\n", b"x" * (MAX_REQUEST + 1), b'{"protocol":1}'],
    ids=["malformed-json", "invalid-utf8", "over-budget", "unterminated"],
)
def test_actual_compiler_rejects_bad_or_unbounded_protocol_frames(compiler, raw):
    result = subprocess.run(
        compiler.process.command, input=raw, capture_output=True, timeout=30, check=False
    )
    messages = [json.loads(line) for line in result.stdout.splitlines()]
    assert result.returncode != 0
    assert messages[0]["ready"] is True and messages[-1]["ok"] is False
    assert all("result" not in message for message in messages)


def test_actual_compiler_readiness_must_match_bundle_bytes(compiler):
    service = JsonWorker(
        compiler.process.command,
        compiler.root,
        kind="translator",
        max_requests=64,
        expected_ready={"bundle_sha256": "0" * 64},
    )
    try:
        with pytest.raises(WorkerError, match="readiness"):
            service.request({"operation": "info", "payload": {}}, timeout=30)
        assert service.connection is None
    finally:
        service.close()


def test_actual_compiler_binds_distinct_framed_ids_and_does_not_await_eof(compiler):
    # Real client sends one frame while keeping stdin open; it must get a reply.
    first, owner = compiler.request("info")
    assert len(first["kinds"]) == 21 and owner["request_number"] == 1
    assert compiler.process.connection.process.poll() is None
    request = {
        "protocol": 1,
        "id": uuid.uuid4().hex,
        "payload": {"operation": "info", "payload": {}},
    }
    result = subprocess.run(
        compiler.process.command,
        input=(json.dumps(request) + "\n").encode(),
        capture_output=True,
        timeout=30,
        check=False,
    )
    messages = [json.loads(line) for line in result.stdout.splitlines()]
    assert result.returncode == 0 and len(messages) == 2
    assert messages[1]["id"] == request["id"] and messages[1]["result"]["result"] == first


def test_reserved_source_names_and_repairs_do_not_contaminate_later_requests(compiler):
    spec = {
        "kind": "line",
        "x": {"field": "constructor", "label": "Epoch"},
        "y": {"field": "__proto__", "label": "Score", "temporal": True},
        "data": {"path": "actual.csv", "columns": ["constructor", "__proto__", "prototype"]},
        "__proto__": {"cached_private_name": "must not escape"},
        "constructor": {"prototype": {"cached_private_name": "must not escape"}},
    }
    expected_recipes = local_request("recipes", {})
    _, first = compiler.request("info")
    assert compiler.call("convert", spec) == local_request("convert", spec)
    assert compiler.call("repair", {"spec": spec}) == local_request("repair", {"spec": spec})
    assert compiler.call("recipes") == expected_recipes
    clean, owner = compiler.request("convert", expected_recipes[0]["spec"])
    assert clean == local_request("convert", expected_recipes[0]["spec"])
    assert owner["pid"] == first["pid"]
