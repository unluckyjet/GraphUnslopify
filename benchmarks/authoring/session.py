"""Prospective familiarized authoring episodes using the unchanged NIST v2 verifier."""

from __future__ import annotations

import hashlib
import json
import platform
import runpy
import subprocess
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
R = runpy.run_path(str(ROOT / "benchmarks/certified/runner.py"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clock_origin():
    if platform.system() == "Darwin":
        boot = subprocess.check_output(["sysctl", "-n", "kern.boottime"])
    elif platform.system() == "Linux":
        boot = Path("/proc/sys/kernel/random/boot_id").read_bytes()
    else:
        raise ValueError("live clocks require a supported macOS/Linux boot identity")
    return hashlib.sha256(platform.node().encode() + boot).hexdigest()


def read_protocol(root):
    path = root / "benchmarks/authoring/protocol.json"
    p = json.loads(path.read_text())
    if (
        sha(root / "benchmarks/certified/protocol.json")
        != p["measurement_protocol_sha256"]
    ):
        raise ValueError("the NIST v2 measurement protocol changed")
    for name, expected in p["implementation_sha256"].items():
        if sha(root / name) != expected:
            raise ValueError("authoring study implementation changed after freezing")
    R["M"]["read_protocol"](root)
    return p


def active(events, slots):
    current, ended = None, []
    for event in events:
        if event["event"] == "begin":
            if (
                current
                or len(ended) >= len(slots)
                or event["slot"] != slots[len(ended)]["id"]
                or event["arm"] != slots[len(ended)]["arm"]
                or event["round"] != slots[len(ended)]["round"]
            ):
                raise ValueError("authoring episodes must follow the frozen order")
            current = event
        elif event["event"] in {"attempt", "end"}:
            if not current or any(
                event[k] != current[k] for k in ["session", "slot", "arm", "round"]
            ):
                raise ValueError("authoring event has no matching live begin")
            if event["monotonic_ns"] < current["monotonic_ns"]:
                raise ValueError("monotonic clock reset")
            if event["event"] == "end":
                if not event["passed"]:
                    raise ValueError("an unsuccessful episode cannot end")
                ended.append(event["slot"])
                current = None
        else:
            raise ValueError("unknown authoring event")
    return current, ended


def producer_path(root, slot):
    return root / "benchmarks/authoring/producers" / (slot["id"] + ".py")


def sources(environment):
    return {
        k: environment[k]
        for k in [
            "installed_source_sha256",
            "common_source",
            "versions",
            "python",
            "platform",
        ]
    }


def begin(root, journal, source_dir, prepared_dir):
    p = read_protocol(root)
    current, ended = active(R["journal_events"](journal), p["sessions"])
    if current:
        raise ValueError("the existing authoring clock remains live; never reset it")
    if len(ended) == len(p["sessions"]):
        raise ValueError("all declared episodes are already complete")
    slot = p["sessions"][len(ended)]
    path = producer_path(root, slot)
    if path.exists() or path.is_symlink():
        raise ValueError("the episode producer must be absent before its clock begins")
    R["load_inputs"](root, source_dir, prepared_dir)
    environment = R["environment"](root)
    origin = clock_origin()
    event = {
        "event": "begin",
        "session": str(uuid.uuid4()),
        "slot": slot["id"],
        "arm": slot["arm"],
        "round": slot["round"],
        "clock_origin": origin,
        "protocol_sha256": sha(root / "benchmarks/authoring/protocol.json"),
        "environment": environment,
        "utc": R["utc"](),
        "monotonic_ns": time.monotonic_ns(),
    }
    R["append_event"](journal, event)
    return {**event, "producer": str(path)}


def verify(root, producer, arm, output, source_dir, prepared_dir):
    if output.exists():
        raise ValueError(
            "use a fresh verification directory; earlier attempts are retained"
        )
    p = R["M"]["read_protocol"](root)
    inputs = R["load_inputs"](root, source_dir, prepared_dir)
    lookup = {i["source"]["id"]: i for i in inputs}
    plan = R["schedule"](p, arm)
    output.mkdir(parents=True)
    environment = R["environment"](root)
    records = []
    for entry in plan:
        folder = output / "runs" / entry["dataset"]
        record = R["run_case"](
            root, folder, entry, lookup[entry["dataset"]], p, producer=producer
        )
        records.append(record)
        R["M"]["write_json"](
            output / f"progress-{len(records):03}.json",
            {"completed": len(records), "expected": len(plan)},
        )
    for record in records:
        R["retain_case"](
            root,
            output / "runs" / record["dataset"],
            record,
            lookup[record["dataset"]],
            p,
            producer=producer,
        )
    unchanged = sources(environment) == sources(R["environment"](root))
    report = {
        "phase": "familiarized-authoring-verification",
        "environment": environment,
        "protocol_sha256": sha(root / "benchmarks/authoring/protocol.json"),
        "measurement_protocol_sha256": sha(root / "benchmarks/certified/protocol.json"),
        "producer_sha256": sha(producer) if producer.is_file() else None,
        "runs": len(records),
        "expected_runs": len(plan),
        "records": records,
        "runtime_unchanged": unchanged,
        "passed": len(records) == len(plan)
        and unchanged
        and all(r["task_accepted"] and r["matches_expected"] for r in records),
    }
    R["M"]["write_json"](output / "results.json", report)
    return report


def attempt(root, journal, output, source_dir, prepared_dir):
    p = read_protocol(root)
    events = R["journal_events"](journal)
    start, _ = active(events, p["sessions"])
    if not start:
        raise ValueError("begin the live episode before producer implementation")
    if (
        start["protocol_sha256"] != sha(root / "benchmarks/authoring/protocol.json")
        or start["clock_origin"] != clock_origin()
    ):
        raise ValueError(
            "protocol or machine boot changed; retain the incomplete episode"
        )
    if sources(start["environment"]) != sources(R["environment"](root)):
        raise ValueError("shared runtime changed during the live episode")
    slot = next(s for s in p["sessions"] if s["id"] == start["slot"])
    report = verify(
        root, producer_path(root, slot), slot["arm"], output, source_dir, prepared_dir
    )
    expected = R["schedule"](R["M"]["read_protocol"](root), slot["arm"])
    identity = lambda row: tuple(
        row[k] for k in ["dataset", "arm", "variant", "repeat"]
    )
    proven = (
        len(report.get("records", [])) == len(expected)
        and [identity(r) for r in report["records"]] == [identity(r) for r in expected]
        and all(
            r["task_accepted"]
            and r["matches_expected"]
            and r["producer_sha256"] == sha(producer_path(root, slot))
            for r in report["records"]
        )
    )
    if report["passed"] and not proven:
        raise ValueError("all nine verified clean cases are required before ending")
    number = 1 + sum(
        e["event"] == "attempt" and e["session"] == start["session"] for e in events
    )
    retained = (
        root
        / "benchmarks/authoring/development"
        / start["session"]
        / f"attempt-{number}.json"
    )
    retained.parent.mkdir(parents=True, exist_ok=True)
    R["M"]["write_json"](retained, report)
    stamp = time.monotonic_ns()
    event = {
        "event": "attempt",
        "session": start["session"],
        "slot": start["slot"],
        "arm": start["arm"],
        "round": start["round"],
        "utc": R["utc"](),
        "monotonic_ns": stamp,
        "passed": report["passed"],
        "output": str(output),
        "report": retained.relative_to(root).as_posix(),
        "report_sha256": sha(retained),
        "producer_sha256": report["producer_sha256"],
    }
    R["append_event"](journal, event)
    if report["passed"]:
        R["append_event"](
            journal,
            {**event, "event": "end", "seconds": (stamp - start["monotonic_ns"]) / 1e9},
        )
    return event


def preflight(root, output, source_dir, prepared_dir):
    read_protocol(root)
    if output.exists():
        raise ValueError("use a fresh preflight directory")
    reports = {}
    for arm in ["matplotlib", "graphunslopify"]:
        reports[arm] = verify(
            root,
            R["producer_path"](root, arm),
            arm,
            output / arm,
            source_dir,
            prepared_dir,
        )
    return {
        "phase": "preflight-existing-producers",
        "passed": all(r["passed"] for r in reports.values()),
        "runs": sum(r["runs"] for r in reports.values()),
    }
