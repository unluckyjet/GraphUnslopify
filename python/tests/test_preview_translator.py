"""The editor must bind compiler replies to current native work and its lifetime."""

from __future__ import annotations

import copy
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from graphunslopify.errors import SpecError
from graphunslopify.preview import PreviewState

ROOT = Path(__file__).resolve().parents[2] / "benchmarks/rendering"


def payload(state, name="demo-bootstrap"):
    folder = ROOT / "cases" / name
    upload = state.upload("data.csv", (folder / "data.csv").read_bytes())
    return {
        "client": "compiler-integration",
        "generation": 0,
        "data_id": upload["id"],
        "spec": json.loads((folder / "figure.json").read_text()),
    }


def test_current_compiler_trace_strict_negative_recovery_and_shutdown(tmp_path):
    state = PreviewState(tmp_path, 1000000, reuse_renderer=True, reuse_translator=True)
    try:
        current = payload(state)
        requests = []
        for generation, name in enumerate(("demo-bootstrap", "false-comparison", "demo-bootstrap")):
            current["generation"] = generation
            current["spec"] = json.loads((ROOT / "cases" / name / "figure.json").read_text())
            answer = state.render(current)
            negative = name == "false-comparison"
            assert answer["exit_code"] == (2 if negative else 0)
            assert answer["report"]["status"] == ("failed" if negative else "passed")
            assert answer["report"]["policy"]["strict"]
            for key in ("edit_map", "diagnostic_map"):
                assert answer[key]["run_id"] == answer["run_id"]
                assert answer[key]["spec_hash"] == answer["report"]["spec_hash"]
            trace = answer["translation_execution"]
            assert trace["kind"] == "translator" and trace["mode"] == "worker"
            assert trace["runtime_source_sha256"] == state.translator.source
            assert trace["request_number"] == generation + 1
            requests.append(trace)
        assert len({r["pid"] for r in requests}) == 1
        assert len({r["request_id"] for r in requests}) == 3
        compiler = state.translator.process.connection.process
        native = state.worker.process.connection.process
    finally:
        state.close()
    assert compiler.poll() is not None and native.poll() is not None
    with pytest.raises(SpecError, match="closed"):
        state.local_request("info")


@pytest.mark.parametrize("cache_statistics", [False, True])
def test_concurrent_editor_replies_keep_their_own_compiler_trace(
    tmp_path, monkeypatch, cache_statistics
):
    state = PreviewState(
        tmp_path,
        1000000,
        reuse_renderer=True,
        reuse_translator=True,
        cache_statistics=cache_statistics,
    )
    original = state._compiler_request
    barrier = threading.Barrier(2)
    traces = {}

    def intercepted(operation, spec=None):
        result, trace = original(operation, spec)
        traces[spec["title"]] = trace
        barrier.wait(timeout=30)
        return result, trace

    monkeypatch.setattr(state, "_compiler_request", intercepted)
    try:
        first = payload(state)
        second = copy.deepcopy(first)
        for number, item in enumerate((first, second)):
            item["client"] = f"client-{number}"
            item["spec"]["title"] = f"Current request {number}"
        with ThreadPoolExecutor(max_workers=2) as pool:
            answers = list(pool.map(state.render, (first, second)))
        for item, answer in zip((first, second), answers, strict=True):
            title = item["spec"]["title"]
            assert answer["report"]["spec"]["title"] == title
            assert answer["translation_execution"] == traces[title]
            assert answer["report"]["status"] == "passed" and not answer["stale"]
        assert len({a["translation_execution"]["request_id"] for a in answers}) == 2
    finally:
        state.close()


def test_compiler_closes_even_if_native_teardown_raises(tmp_path):
    state = PreviewState(tmp_path, 1000000, reuse_translator=True)
    state.local_request("info")
    process = state.translator.process.connection.process

    class BrokenNative:
        def close(self):
            raise RuntimeError("controlled teardown failure")

    state.worker = BrokenNative()
    with pytest.raises(RuntimeError, match="controlled teardown failure"):
        state.close()
    assert process.poll() is not None and state.translator.closed
