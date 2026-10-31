"""Actual strict figures must keep fresh evidence when numerical values are reused."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_preview_worker import image_signature

from graphunslopify.preview import PreviewState
from graphunslopify.preview_worker import RenderWorker

ROOT = Path(__file__).resolve().parents[2]
FIELDS = (
    "schema_version",
    "spec_hash",
    "spec",
    "status",
    "ok",
    "data",
    "findings",
    "inspection",
    "panels",
    "claims",
    "significance",
    "annotations",
    "untested",
    "alt_text",
    "policy",
    "exit_code",
    "script",
)


@pytest.mark.parametrize("name", ["demo-bootstrap", "false-comparison"])
def test_cached_edits_match_uncached_pixels_science_and_current_metadata(tmp_path, name):
    base = ROOT / "benchmarks/incremental"
    protocol = json.loads((base / "protocol.json").read_text())
    case = next(c for c in protocol["cases"] if c["id"] == name)
    states = [
        PreviewState(
            tmp_path / mode,
            1000000,
            reuse_renderer=True,
            reuse_translator=True,
            cache_statistics=enabled,
        )
        for mode, enabled in [("uncached", False), ("cached", True)]
    ]
    try:
        uploads = [state.upload("data.csv", (base / case["data"]).read_bytes()) for state in states]
        for generation, edit in enumerate(case["edits"]):
            spec = json.loads((base / edit["spec"]).read_text())
            answers = [
                state.render(
                    {
                        "client": "cache-edits",
                        "generation": generation,
                        "data_id": upload["id"],
                        "spec": spec,
                    }
                )
                for state, upload in zip(states, uploads, strict=True)
            ]
            left, right = answers
            assert {k: left["report"].get(k) for k in FIELDS} == {
                k: right["report"].get(k) for k in FIELDS
            }
            assert image_signature(states[0], left) == image_signature(states[1], right)
            assert left["exit_code"] == right["exit_code"] == case["expected_exit_code"]
            assert right["report"]["policy"]["strict"]
            for key in ("edit_map", "diagnostic_map"):
                assert right[key]["run_id"] == right["run_id"]
                assert right[key]["spec_hash"] == right["report"]["spec_hash"]
            trace = right["execution"]["statistics_cache"]
            assert trace["enabled"] and trace["pid"] == right["execution"]["pid"]
            assert trace["runtime_source_sha256"] == right["execution"]["runtime_source_sha256"]
            if edit["id"] in {
                "title-a",
                "title-b",
                "title-after-filter",
                "return-to-original-calculation",
            }:
                assert trace["hits"] > 0 and trace["misses"] == 0
            if edit["id"] == "numeric-filter-config":
                assert trace["misses"] > 0
            if "filter" in spec:
                step = right["report"]["data"]["counts"]["filtering"]["steps"][0]
                assert step["before"] == step["after"] == 24 and step["removed"] == 0
    finally:
        for state in states:
            state.close()


def test_recycled_native_process_starts_with_an_empty_numerical_cache(tmp_path):
    base = ROOT / "benchmarks/rendering/cases/demo-bootstrap"
    state = PreviewState(tmp_path, 1000000, reuse_renderer=True, reuse_translator=True)
    state.worker.close()
    state.worker = RenderWorker(tmp_path, max_jobs=2, cache_statistics=True)
    try:
        upload = state.upload("data.csv", (base / "data.csv").read_bytes())
        spec = json.loads((base / "figure.json").read_text())
        traces = []
        for generation in range(3):
            answer = state.render(
                {
                    "client": "recycle",
                    "generation": generation,
                    "data_id": upload["id"],
                    "spec": spec,
                }
            )
            assert answer["report"]["status"] == "passed"
            traces.append(answer["execution"])
        assert traces[0]["pid"] == traces[1]["pid"] != traces[2]["pid"]
        assert traces[1]["statistics_cache"]["misses"] == 0
        assert traces[2]["statistics_cache"]["misses"] > 0 and traces[2]["request_number"] == 1
    finally:
        state.close()
