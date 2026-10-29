"""Clock/whole-task controls, separate from the four actual authoring episodes."""

from __future__ import annotations

import copy
import json
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
S = runpy.run_path(str(ROOT / "benchmarks/authoring/session.py"))
G = S["begin"].__globals__
P = json.loads((ROOT / "benchmarks/authoring/protocol.json").read_text())
MEASURE = json.loads((ROOT / "benchmarks/certified/protocol.json").read_text())


@pytest.fixture
def episode(tmp_path, monkeypatch):
    path = tmp_path / "benchmarks/authoring/protocol.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(P))
    environment = {
        "installed_source_sha256": {"source": "a"},
        "common_source": {},
        "versions": {"python": "fixture"},
        "python": "fixture interpreter",
        "platform": {"system": "fixture", "machine": "fixture"},
    }
    monkeypatch.setitem(G, "read_protocol", lambda root: P)
    monkeypatch.setitem(G, "clock_origin", lambda: "same-boot")
    monkeypatch.setitem(S["R"], "load_inputs", lambda *args: [])
    monkeypatch.setitem(S["R"], "environment", lambda root: copy.deepcopy(environment))
    monkeypatch.setitem(S["R"]["M"], "read_protocol", lambda root: MEASURE)
    return tmp_path, tmp_path / "sessions.jsonl", environment


def test_live_episode_cannot_restart_or_use_an_existing_producer(episode):
    root, journal, _ = episode
    producer = S["producer_path"](root, P["sessions"][0])
    producer.parent.mkdir(parents=True)
    producer.write_text("# preexisting\n")
    with pytest.raises(ValueError, match="absent"):
        S["begin"](root, journal, root, root)
    producer.unlink()
    begin = S["begin"](root, journal, root, root)
    assert begin["slot"] == "round1-graphunslopify"
    with pytest.raises(ValueError, match="remains live"):
        S["begin"](root, journal, root, root)


@pytest.mark.parametrize("contamination", ["boot", "protocol", "runtime"])
def test_incompatible_clock_context_does_not_silently_continue(episode, monkeypatch, contamination):
    root, journal, environment = episode
    S["begin"](root, journal, root, root)
    if contamination == "boot":
        monkeypatch.setitem(G, "clock_origin", lambda: "another-boot")
    elif contamination == "protocol":
        (root / "benchmarks/authoring/protocol.json").write_text("{}")
    else:
        environment["installed_source_sha256"]["source"] = "changed"
    with pytest.raises(ValueError, match="changed"):
        S["attempt"](root, journal, root / "out", root, root)
    assert [e["event"] for e in S["R"]["journal_events"](journal)] == ["begin"]


def complete_report(root, arm):
    producer = S["producer_path"](root, P["sessions"][0])
    return {
        "passed": True,
        "producer_sha256": S["sha"](producer),
        "records": [
            {
                **e,
                "task_accepted": True,
                "matches_expected": True,
                "producer_sha256": S["sha"](producer),
            }
            for e in S["R"]["schedule"](MEASURE, arm)
        ],
    }


@pytest.mark.parametrize(
    "corruption", ["missing", "duplicate", "reordered", "failed", "changed_source"]
)
def test_a_pass_claim_cannot_end_an_incomplete_or_unbound_task(episode, monkeypatch, corruption):
    root, journal, _ = episode
    S["begin"](root, journal, root, root)
    producer = S["producer_path"](root, P["sessions"][0])
    producer.parent.mkdir(parents=True)
    producer.write_text("# synthetic producer\n")
    report = complete_report(root, "graphunslopify")
    if corruption == "missing":
        report["records"].pop()
    elif corruption == "duplicate":
        report["records"][-1] = report["records"][0]
    elif corruption == "reordered":
        report["records"].reverse()
    elif corruption == "failed":
        report["records"][-1]["matches_expected"] = False
    else:
        report["records"][-1]["producer_sha256"] = "changed"
    monkeypatch.setitem(G, "verify", lambda *args: report)
    with pytest.raises(ValueError, match="all nine"):
        S["attempt"](root, journal, root / "out", root, root)
    assert S["active"](S["R"]["journal_events"](journal), P["sessions"])[0]


def test_failed_attempt_is_retained_and_success_uses_the_original_clock(episode, monkeypatch):
    root, journal, _ = episode
    begin = S["begin"](root, journal, root, root)
    producer = S["producer_path"](root, P["sessions"][0])
    producer.parent.mkdir(parents=True)
    producer.write_text("# synthetic producer\n")
    failed = {"passed": False, "records": [], "producer_sha256": S["sha"](producer)}
    monkeypatch.setitem(G, "verify", lambda *args: failed)
    attempt = S["attempt"](root, journal, root / "first", root, root)
    assert not attempt["passed"] and (root / attempt["report"]).is_file()
    monkeypatch.setitem(G, "verify", lambda *args: complete_report(root, "graphunslopify"))
    S["attempt"](root, journal, root / "second", root, root)
    events = S["R"]["journal_events"](journal)
    assert [e["event"] for e in events] == ["begin", "attempt", "attempt", "end"]
    assert events[-1]["seconds"] == (events[-1]["monotonic_ns"] - begin["monotonic_ns"]) / 1e9
    next_begin = S["begin"](root, journal, root, root)
    assert next_begin["slot"] == "round1-matplotlib"


def test_frozen_order_is_counterbalanced_and_tampered_begin_arm_is_rejected():
    assert [s["arm"] for s in P["sessions"]] == [
        "graphunslopify",
        "matplotlib",
        "matplotlib",
        "graphunslopify",
    ]
    event = {"event": "begin", "slot": P["sessions"][0]["id"], "arm": "matplotlib", "round": 1}
    with pytest.raises(ValueError, match="frozen order"):
        S["active"]([event], P["sessions"])


def test_real_frozen_implementation_bindings():
    assert S["read_protocol"](ROOT)["measurement_protocol_sha256"] == S["sha"](
        ROOT / "benchmarks/certified/protocol.json"
    )


def test_clock_reset_cannot_close_an_episode():
    slot = P["sessions"][0]
    begin = {
        "event": "begin",
        "session": "fixture",
        "slot": slot["id"],
        "arm": slot["arm"],
        "round": slot["round"],
        "monotonic_ns": 20,
    }
    end = {**begin, "event": "end", "monotonic_ns": 10, "passed": True}
    with pytest.raises(ValueError, match="clock reset"):
        S["active"]([begin, end], P["sessions"])
