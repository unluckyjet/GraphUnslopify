"""Synthetic orchestration/session controls; no NIST plotting outputs are evaluated here."""

from __future__ import annotations

import copy
import hashlib
import json
import runpy
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
R = runpy.run_path(str(ROOT / "benchmarks/certified/runner.py"))
P = json.loads((ROOT / "benchmarks/certified/protocol.json").read_text())


def test_complete_schedule_preserves_all_cases_variants_repeats_and_alternating_order():
    rows = R["schedule"](P)
    assert len(rows) == 72 and Counter(r["dataset"] for r in rows) == dict.fromkeys(
        P["dataset_order"], 8
    )
    assert len({tuple(r.values()) for r in rows}) == 72
    assert rows[0]["arm"] == "matplotlib" and rows[4]["arm"] == "graphunslopify"
    assert rows[36]["arm"] == "graphunslopify"
    development = R["schedule"](P, "matplotlib")
    assert len(development) == 9 and all(r["variant"] == "mean_sd" for r in development)


def fake_records():
    return [
        {
            **r,
            "matches_expected": True,
            "task_accepted": r["variant"] == "mean_sd",
            "numeric_passed": r["variant"] == "mean_sd",
            "quality_passed": r["variant"] == "mean_sd",
            "labels_passed": True,
            "numeric": [],
            "built_in_report": None,
            "build": {"returncode": 0, "seconds": 0.01},
            "execution": {"returncode": 0, "seconds": 0.1},
            "measurement": {
                "script_exit_code": 0,
                "instrumented_execution_seconds": 0.08,
                "save_seconds": 0.03,
                "exports": {
                    "files": {"png": {"rgba_sha256": r["dataset"] + r["arm"] + r["variant"]}}
                },
            },
        }
        for r in R["schedule"](P)
    ]


def test_summary_includes_second_repeat_failures_and_refuses_missing_or_duplicate_cases():
    rows = fake_records()
    assert R["summarize"](rows, P)["passed"]
    rows[-1]["matches_expected"] = False
    summary = R["summarize"](rows, P)
    changed = next(
        p
        for p in summary["repetition_pairs"]
        if all(p[k] == rows[-1][k] for k in ["dataset", "arm", "variant"])
    )
    assert not summary["passed"] and not changed["outcome_agreement"]
    assert not R["summarize"](rows[:-1], P)["complete"]
    assert not R["summarize"]([*rows[:-1], rows[0]], P)["complete"]


def test_missing_images_are_not_successful_reproduction_and_exit_disagreements_are_visible():
    rows = fake_records()
    targets = [
        r
        for r in rows
        if r["dataset"] == "PiDigits" and r["arm"] == "matplotlib" and r["variant"] == "mean_sd"
    ]
    for i, row in enumerate(targets):
        row["matches_expected"] = False
        row["execution"]["returncode"] = i + 2
        row["measurement"]["script_exit_code"] = i + 2
        row["measurement"]["exports"] = {}
    pair = R["summarize"](rows, P)["repetition_pairs"][0]
    assert pair == {
        "dataset": "PiDigits",
        "arm": "matplotlib",
        "variant": "mean_sd",
        "comparable": False,
        "identical": False,
        "outcome_agreement": False,
    }


def test_input_validation_rejects_rebound_csv_metadata_with_changed_observations(
    tmp_path, monkeypatch
):
    fixture = runpy.run_path(str(ROOT / "python/tests/test_certified_corpus.py"))["fixture"]
    data, row, manifest = fixture()
    root = tmp_path / "root"
    source = root / "benchmarks/certified/sources.json"
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps(manifest))
    cache = tmp_path / "sources"
    cache.mkdir()
    (cache / row["file"]).write_bytes(data)
    prepared = tmp_path / "prepared"
    R["C"]["prepare"](manifest_path=source, source_dir=cache, output=prepared)
    protocol = {"source_manifest_sha256": R["sha"](source), "dataset_order": ["Fixture"]}
    monkeypatch.setitem(R["M"], "read_protocol", lambda root: protocol)
    assert len(R["load_inputs"](root, cache, prepared)) == 1
    path = prepared / "Fixture.csv"
    path.write_bytes(path.read_bytes().replace(b"1.0000", b"9.0000"))
    meta = prepared / "preparation.json"
    changed = json.loads(meta.read_text())
    changed["sources"][0]["csv_sha256"] = R["sha"](path)
    meta.write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="original pinned source"):
        R["load_inputs"](root, cache, prepared)


def test_process_failures_and_timeouts_keep_status_and_both_logs(tmp_path):
    failed = R["process"]([sys.executable, "-c", "raise SystemExit(7)"], tmp_path, "failure")
    assert failed["returncode"] == 7 and not failed["timed_out"]
    timed = R["process"](
        [sys.executable, "-c", "import time; print('partial', flush=True); time.sleep(5)"],
        tmp_path,
        "timeout",
        timeout=0.1,
    )
    assert timed["returncode"] is None and timed["timed_out"]
    assert all(
        (tmp_path / f"{label}.{stream}.log").is_file()
        for label in ["failure", "timeout"]
        for stream in ["stdout", "stderr"]
    )


def test_development_clocks_cannot_reset_skip_order_or_end_after_partial_success(
    tmp_path, monkeypatch
):
    root = tmp_path / "root"
    protocol_file = root / "benchmarks/certified/protocol.json"
    protocol_file.parent.mkdir(parents=True)
    protocol_file.write_text(json.dumps(P))
    monkeypatch.setitem(R["M"], "read_protocol", lambda root: P)
    journal = tmp_path / "sessions.jsonl"
    with pytest.raises(ValueError, match="order"):
        R["begin_session"](root, "graphunslopify", journal)
    first = R["begin_session"](root, "matplotlib", journal)
    with pytest.raises(ValueError, match="clocks are not reset"):
        R["begin_session"](root, "matplotlib", journal)
    producer = R["producer_path"](root, "matplotlib")
    producer.parent.mkdir(parents=True)
    producer.write_text("# Synthetic session control\n")
    partial = {"passed": True, "records": []}
    with pytest.raises(ValueError, match="all nine"):
        R["finish_attempt"](root, "matplotlib", journal, partial, tmp_path)
    failed = {"passed": False, "records": []}
    assert R["finish_attempt"](root, "matplotlib", journal, failed, tmp_path) is None
    assert R["active_session"](R["journal_events"](journal))["session"] == first["session"]
    rows = [
        {
            **entry,
            "matches_expected": True,
            "task_accepted": True,
            "producer_sha256": R["sha"](producer),
        }
        for entry in R["schedule"](P, "matplotlib")
    ]
    success = {"passed": True, "records": rows}
    ended = R["finish_attempt"](root, "matplotlib", journal, success, tmp_path)
    assert ended["seconds"] >= 0 and R["active_session"](R["journal_events"](journal)) is None
    assert [e["event"] for e in R["journal_events"](journal)] == [
        "begin",
        "attempt",
        "attempt",
        "end",
    ]
    R["begin_session"](root, "graphunslopify", journal)


def test_existing_producer_is_not_a_newly_started_implementation_session(tmp_path, monkeypatch):
    monkeypatch.setitem(R["M"], "read_protocol", lambda root: P)
    producer = R["producer_path"](tmp_path, "matplotlib")
    producer.parent.mkdir(parents=True)
    producer.write_text("# Existing producer\n")
    with pytest.raises(ValueError, match="absent"):
        R["begin_session"](tmp_path, "matplotlib", tmp_path / "session.jsonl")


@pytest.mark.parametrize("changed", [None, "accuracy", "dataset_order", "minimum_text_pt"])
def test_svg_protocol_amendment_retains_clock_and_refuses_numeric_or_case_changes(
    tmp_path, monkeypatch, changed
):
    root = tmp_path / "root"
    folder = root / "benchmarks/certified"
    folder.mkdir(parents=True)
    original = (ROOT / "benchmarks/certified/protocol-v1.json").read_bytes()
    (folder / "protocol-v1.json").write_bytes(original)
    current = folder / "protocol.json"
    current.write_bytes(original)
    monkeypatch.setitem(
        R["M"],
        "read_protocol",
        lambda root: json.loads((root / "benchmarks/certified/protocol.json").read_text()),
    )
    journal = tmp_path / "events.jsonl"
    start = R["begin_session"](root, "matplotlib", journal)
    amended = copy.deepcopy(P)
    if changed == "accuracy":
        amended["accuracy"]["mean_allowance"] += " changed"
    elif changed == "dataset_order":
        amended["dataset_order"] = amended["dataset_order"][:-1]
    elif changed == "minimum_text_pt":
        amended["minimum_text_pt"] = 1
    current.write_text(json.dumps(amended))
    if changed:
        with pytest.raises(ValueError, match="must not change"):
            R["amend_session"](root, "matplotlib", journal, "Synthetic SVG correction")
        assert len(R["journal_events"](journal)) == 1
    else:
        event = R["amend_session"](root, "matplotlib", journal, "Synthetic SVG correction")
        state = R["active_session"](R["journal_events"](journal))
        assert state["monotonic_ns"] == start["monotonic_ns"]
        assert state["protocol_sha256"] == R["sha"](current)
        assert event["clock_reset"] is False and event["timing_comparison_valid"] is False
        assert state["initial_protocol_sha256"] == start["protocol_sha256"]


def test_sentinel_is_not_credited_for_an_execution_failure():
    reference = {
        "values": {"mean": "2", "low": "1", "high": "3", "half_span": "1"},
        "absolute_allowances": dict.fromkeys(["mean", "low", "high", "half_span"], "0.001"),
    }
    entry = {"dataset": "Fixture", "variant": "missing_interval"}
    protocol = {**P, "y_labels": {"Fixture": "Synthetic value"}}
    checks = dict.fromkeys(
        [
            "exports_decoded",
            "one_measured_export_each",
            "requested_png_dpi",
            "nonuniform_png",
            "one_visible_point",
            "text_at_target_width",
        ],
        True,
    )
    checks["one_visible_interval"] = False
    measurement = {
        "exports": {"quality_passed": False, "quality_checks": checks},
        "snapshots": [
            {
                "format": fmt,
                "measurement": {
                    "actual": {"mean": 2},
                    "intervals": [],
                    "axes_labels": [
                        {
                            "title": "Fixture: mean and sample SD",
                            "x": "Dataset",
                            "y": "Synthetic value",
                        }
                    ],
                },
            }
            for fmt in P["formats"]
        ],
    }
    assert R["assess"](entry, measurement, reference, protocol, True)["matches_expected"]
    assert not R["assess"](entry, measurement, reference, protocol, False)["matches_expected"]


@pytest.mark.parametrize("alternative_producer", [False, True])
def test_actual_synthetic_producer_worker_chain(tmp_path, alternative_producer):
    root = tmp_path / "root"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "measure-certified-figure.py").symlink_to(
        ROOT / "scripts/measure-certified-figure.py"
    )
    producer = (
        root / "benchmarks/authoring/producers/synthetic.py"
        if alternative_producer
        else R["producer_path"](root, "matplotlib")
    )
    options = {"producer": producer} if alternative_producer else {}
    producer.parent.mkdir(parents=True)
    code = """import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(3.4, 2.6))
ax.errorbar([0], [5], yerr=[2], fmt="o")
ax.set(title="Fixture: mean and sample SD", xlabel="Dataset", ylabel="Synthetic value")
fig.tight_layout()
for fmt in ("png", "svg", "pdf"):
    fig.savefig("figure."+fmt, dpi=150, bbox_inches="tight")
plt.close(fig)
"""
    producer.write_text(
        'import argparse\nfrom pathlib import Path\np=argparse.ArgumentParser()\np.add_argument("--dataset")\np.add_argument("--data")\np.add_argument("--out-dir")\np.add_argument("--variant")\na=p.parse_args()\n(Path(a.out_dir)/"figure.py").write_text('
        + repr(code)
        + ")\n"
    )
    original = tmp_path / "source.dat"
    original.write_bytes(b"Synthetic fixture")
    data = tmp_path / "data.csv"
    data.write_text("value\n3\n5\n7\n")
    item = {
        "source": {
            "certified": {
                "mean": {"value": "5", "exact": True},
                "sample_sd": {"value": "2", "exact": True},
            },
            "sha256": hashlib.sha256(original.read_bytes()).hexdigest(),
        },
        "values": ["3", "5", "7"],
        "data": data,
        "original": original,
        "csv_sha256": R["sha"](data),
    }
    protocol = copy.deepcopy(P)
    protocol["y_labels"]["Fixture"] = "Synthetic value"
    entry = {"dataset": "Fixture", "arm": "matplotlib", "variant": "mean_sd", "repeat": 0}
    record = R["run_case"](root, tmp_path / "output", entry, item, protocol, **options)
    assert record["matches_expected"] and record["task_accepted"], record
    assert record["input_unchanged"] and record["producer_unchanged"]
    assert (tmp_path / "output/producer-source.py").read_bytes() == producer.read_bytes()
    R["retain_case"](root, tmp_path / "output", record, item, protocol, **options)
    assert record["artifacts_retained"]
    pristine = copy.deepcopy(record)
    original_producer = producer.read_bytes()
    producer.write_text("# changed after verification\n")
    changed_source = copy.deepcopy(pristine)
    R["retain_case"](root, tmp_path / "output", changed_source, item, protocol, **options)
    assert not changed_source["artifacts_retained"]
    producer.write_bytes(original_producer)
    svg = tmp_path / "output/figure.svg"
    original_svg = svg.read_bytes()
    svg.write_bytes(original_svg + b"\n")
    R["retain_case"](root, tmp_path / "output", record, item, protocol, **options)
    assert not record["artifacts_retained"]
    svg.write_bytes(original_svg)
    record = pristine
    (tmp_path / "output/figure.png").unlink()
    R["retain_case"](root, tmp_path / "output", record, item, protocol, **options)
    assert not record["artifacts_retained"] and not record["matches_expected"]
    assert not R["M"]["reproduction"](record["final_exports"], record["final_exports"])[
        "comparable"
    ]
