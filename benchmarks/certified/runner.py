"""Complete-case orchestration and live producer-session evidence for protocol v1."""

from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import io
import json
import platform
import runpy
import statistics
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
M = runpy.run_path(str(ROOT / "benchmarks/certified/measurement.py"))
C = runpy.run_path(str(ROOT / "benchmarks/certified/corpus.py"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unchanged(path, expected):
    try:
        return path.is_file() and not path.is_symlink() and sha(path) == expected
    except OSError:
        return False


def utc():
    return datetime.now(timezone.utc).isoformat()


def load_inputs(root: Path, source_dir: Path, prepared_dir: Path) -> list[dict]:
    """Check original pins and every CSV token, rather than trusting mutable preparation metadata."""
    protocol = M["read_protocol"](root)
    manifest = C["read_manifest"](root / "benchmarks/certified/sources.json")
    preparation = json.loads((prepared_dir / "preparation.json").read_text())
    if (
        preparation["manifest_sha256"] != protocol["source_manifest_sha256"]
        or [r["id"] for r in preparation["sources"]] != protocol["dataset_order"]
    ):
        raise ValueError(
            "prepared corpus identity/order differs from the frozen protocol"
        )
    inputs = []
    for source, meta in zip(manifest["sources"], preparation["sources"], strict=True):
        original = source_dir / source["file"]
        data = prepared_dir / (source["id"] + ".csv")
        if any(p.is_symlink() or not p.is_file() for p in [original, data]):
            raise ValueError("benchmark inputs must be regular files, not symlinks")
        with original.open("rb") as handle:
            raw = handle.read(C["MAX_SOURCE_BYTES"] + 1)
        parsed = C["parse_source"](raw, source)
        with data.open("rb") as handle:
            body = handle.read(1024 * 1024 + 1)
        if (
            len(body) > 1024 * 1024
            or meta["csv"] != data.name
            or hashlib.sha256(body).hexdigest() != meta["csv_sha256"]
        ):
            raise ValueError("prepared CSV differs from its recorded identity")
        reader = csv.DictReader(io.StringIO(body.decode("ascii")))
        if reader.fieldnames != ["observation", "dataset", "value"]:
            raise ValueError("unexpected prepared CSV columns")
        rows = list(reader)
        expected = [
            {"observation": str(i), "dataset": source["id"], "value": value}
            for i, value in enumerate(parsed["values"], 1)
        ]
        if (
            rows != expected
            or meta["certified"] != source["certified"]
            or meta["source_sha256"] != source["sha256"]
            or meta["observations"] != source["observations"]
        ):
            raise ValueError(
                "prepared observations/reference facts differ from original pinned source"
            )
        inputs.append(
            {
                "source": source,
                "values": parsed["values"],
                "data": data.resolve(),
                "original": original.resolve(),
                "csv_sha256": hashlib.sha256(body).hexdigest(),
            }
        )
    if preparation["datasets"] != len(inputs) or preparation["observations"] != sum(
        len(i["values"]) for i in inputs
    ):
        raise ValueError("prepared corpus totals differ")
    return inputs


def schedule(protocol, development_arm=None):
    entries = []
    for repeat in range(1 if development_arm else protocol["repeats"]):
        for index, name in enumerate(protocol["dataset_order"]):
            arms = (
                [development_arm]
                if development_arm
                else protocol["arms"][:: -1 if (index + repeat) % 2 else 1]
            )
            for arm in arms:
                for variant in ["mean_sd"] if development_arm else protocol["variants"]:
                    entries.append(
                        {
                            "dataset": name,
                            "arm": arm,
                            "variant": variant,
                            "repeat": repeat,
                        }
                    )
    return entries


def process(command, folder: Path, label: str, timeout=120):
    start = time.perf_counter()
    code, error, timed_out, stdout, stderr = None, None, False, "", ""
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False
        )
        code, stdout, stderr = result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as problem:
        timed_out, error = True, "process timeout"
        stdout, stderr = problem.stdout or "", problem.stderr or ""
    except OSError as problem:
        error = str(problem)
    elapsed = time.perf_counter() - start
    for stream, value in [("stdout", stdout), ("stderr", stderr)]:
        if isinstance(value, bytes):
            value = value.decode("utf8", errors="replace")
        with (folder / f"{label}.{stream}.log").open("x", encoding="utf8") as handle:
            handle.write(value)
    return {
        "command": command,
        "returncode": code,
        "seconds": elapsed,
        "timed_out": timed_out,
        "error": error,
    }


def assess(
    entry: dict,
    measurement: dict | None,
    reference: dict,
    protocol: dict,
    executable: bool,
) -> dict:
    """Execution failures cannot masquerade as detected sentinel errors."""
    snapshots = measurement.get("snapshots", []) if measurement else []
    counts = [s.get("format") for s in snapshots]
    complete = len(counts) == len(protocol["formats"]) and sorted(counts) == sorted(
        protocol["formats"]
    )
    quantities = [
        {
            "format": s["format"],
            **M["compare_numeric"](s["measurement"]["actual"], reference),
        }
        for s in snapshots
    ]
    numeric = complete and all(r["passed"] for r in quantities)
    expected_labels = {
        "title": protocol["title_template"].format(id=entry["dataset"]),
        "x": protocol["x_label"],
        "y": protocol["y_labels"][entry["dataset"]],
    }
    labels = complete and all(
        s["measurement"]["axes_labels"] == [expected_labels] for s in snapshots
    )
    exports = measurement.get("exports", {}) if measurement else {}
    quality = bool(exports.get("quality_passed"))
    accepted = bool(executable and numeric and labels and quality)
    checks = exports.get("quality_checks", {})
    sentinel = bool(
        executable
        and complete
        and labels
        and not accepted
        and all(r["quantities"]["mean"]["passed"] for r in quantities)
        and all(not s["measurement"]["intervals"] for s in snapshots)
        and checks.get("one_visible_interval") is False
        and all(
            value for name, value in checks.items() if name != "one_visible_interval"
        )
        and all(
            name in checks
            for name in [
                "exports_decoded",
                "one_measured_export_each",
                "requested_png_dpi",
                "nonuniform_png",
                "one_visible_point",
                "text_at_target_width",
            ]
        )
    )
    return {
        "numeric": quantities,
        "numeric_passed": numeric,
        "labels_passed": labels,
        "quality_passed": quality,
        "task_accepted": accepted,
        "matches_expected": accepted if entry["variant"] == "mean_sd" else sentinel,
    }


def run_case(
    root: Path, folder: Path, entry: dict, item: dict, protocol: dict, *, producer=None
) -> dict:
    folder.mkdir(parents=True, exist_ok=False)
    producer = producer if producer is not None else producer_path(root, entry["arm"])
    producer_hash = sha(producer) if producer.is_file() else None
    if producer_hash:
        with (folder / "producer-source.py").open("xb") as handle:
            handle.write(producer.read_bytes())
    reference = M["numeric_reference"](item["source"], item["values"])
    record = {
        **entry,
        "started_at": utc(),
        "producer_sha256": producer_hash,
        "reference": reference,
        "measurement": None,
    }
    record["build"] = process(
        [
            sys.executable,
            str(producer),
            "--dataset",
            entry["dataset"],
            "--data",
            str(item["data"]),
            "--out-dir",
            str(folder),
            "--variant",
            entry["variant"],
        ],
        folder,
        "build",
    )
    script = folder / "figure.py"
    valid_script = script.is_file() and not script.is_symlink()
    if record["build"]["returncode"] == 0 and valid_script:
        generated_hash = sha(script)
        record["generated_script"] = {
            "sha256": generated_hash,
            "bytes": script.stat().st_size,
            "nonblank_lines": sum(
                bool(s.strip()) for s in script.read_text().splitlines()
            ),
        }
        spec = folder / "spec.json"
        if spec.is_file():
            record["declarative_payload"] = {
                "sha256": sha(spec),
                "bytes": spec.stat().st_size,
                "nonblank_lines": sum(
                    bool(s.strip()) for s in spec.read_text().splitlines()
                ),
            }
        record["execution"] = process(
            [
                sys.executable,
                str(root / "scripts/measure-certified-figure.py"),
                "--script",
                str(script),
                "--out-dir",
                str(folder),
            ],
            folder,
            "execute",
        )
        try:
            record["measurement"] = json.loads(
                (folder / "measurement.json").read_text()
            )
        except (OSError, ValueError) as problem:
            record["measurement_error"] = str(problem)
        if record["measurement"]:
            record["generated_script_unchanged"] = (
                script.is_file()
                and sha(script)
                == generated_hash
                == record["measurement"]["script_sha256"]
            )
    else:
        record["execution"] = None
        record["measurement_error"] = (
            "producer failed or did not create a regular figure.py"
        )
    report = folder / "figure.report.json"
    record["built_in_report"] = None
    if report.is_file():
        try:
            value = json.loads(report.read_text())
            record["built_in_report"] = {
                "status": value.get("status"),
                "sha256": sha(report),
            }
        except (OSError, ValueError) as problem:
            record["built_in_report_error"] = str(problem)
    record["producer_unchanged"] = unchanged(producer, producer_hash)
    record["input_unchanged"] = unchanged(
        item["data"], item["csv_sha256"]
    ) and unchanged(item["original"], item["source"]["sha256"])
    measured = record["measurement"]
    executable = bool(
        record["execution"]
        and record["execution"]["returncode"] == 0
        and measured
        and measured["script_exit_code"] == 0
        and record.get("generated_script_unchanged")
        and record["producer_unchanged"]
        and record["input_unchanged"]
    )
    try:
        assessment = assess(entry, measured, reference, protocol, executable)
    except (KeyError, TypeError, ValueError) as problem:
        record["measurement_error"] = str(problem)
        assessment = assess(entry, None, reference, protocol, False)
    record.update(assessment)
    M["write_json"](folder / "case.json", record)
    return record


def retain_case(root, folder, record, item, protocol, *, producer=None):
    """Verify files still exist at study end; retain the original case.json separately."""
    measured = record.get("measurement")
    exports = (
        M["export_measurements"](folder, measured["snapshots"], protocol)
        if measured
        else {}
    )
    record["final_exports"] = exports
    checks = exports.get("quality_checks", {})
    retained = bool(
        checks.get("exports_decoded")
        and checks.get("one_measured_export_each")
        and all(
            exports["files"].get(fmt, {}).get("sha256")
            == measured["exports"]["files"].get(fmt, {}).get("sha256")
            for fmt in protocol["formats"]
        )
        and unchanged(item["data"], item["csv_sha256"])
        and unchanged(item["original"], item["source"]["sha256"])
        and unchanged(
            producer if producer is not None else producer_path(root, record["arm"]),
            record["producer_sha256"],
        )
    )
    record["artifacts_retained"] = retained
    if not retained:
        record.update(
            {"task_accepted": False, "quality_passed": False, "matches_expected": False}
        )


def summarize(records, protocol):
    wanted = schedule(protocol)
    keys = lambda row: (row["dataset"], row["arm"], row["variant"], row["repeat"])
    complete = (
        len(records) == len(wanted)
        and len({keys(r) for r in records}) == len(wanted)
        and {keys(r) for r in records} == {keys(r) for r in wanted}
    )
    pairs = []
    for name in protocol["dataset_order"]:
        for arm in protocol["arms"]:
            for variant in protocol["variants"]:
                selected = sorted(
                    [
                        r
                        for r in records
                        if r["dataset"] == name
                        and r["arm"] == arm
                        and r["variant"] == variant
                    ],
                    key=lambda r: r["repeat"],
                )
                a, b = selected if len(selected) == 2 else [{}, {}]
                images = [
                    r.get("final_exports", r.get("measurement", {}).get("exports", {}))
                    if r.get("measurement")
                    else {}
                    for r in [a, b]
                ]
                reproduced = M["reproduction"](*images)
                fields = [
                    "matches_expected",
                    "task_accepted",
                    "numeric_passed",
                    "quality_passed",
                    "labels_passed",
                ]

                def outcome(row, fields=fields):
                    return [
                        *[row[k] for k in fields],
                        row.get("build", {}).get("returncode"),
                        (row.get("execution") or {}).get("returncode"),
                        (row.get("measurement") or {}).get("script_exit_code"),
                        (row.get("built_in_report") or {}).get("status"),
                    ]

                agree = len(selected) == 2 and outcome(a) == outcome(b)
                pairs.append(
                    {
                        "dataset": name,
                        "arm": arm,
                        "variant": variant,
                        **reproduced,
                        "outcome_agreement": agree,
                    }
                )
    arms = {}
    for arm in protocol["arms"]:
        rows = [r for r in records if r["arm"] == arm]
        clean = [r for r in rows if r["variant"] == "mean_sd"]
        faulty = [r for r in rows if r["variant"] == "missing_interval"]
        errors, measured_counts = {}, {}
        for key in ["mean", "low", "high", "half_span"]:
            values = [
                Decimal(n["quantities"][key]["absolute_error"])
                for r in clean
                for n in r["numeric"]
                if "absolute_error" in n["quantities"][key]
            ]
            errors[key] = str(max(values)) if values else None
            measured_counts[key] = len(values)
        timing = {}
        for key in ["build", "execution"]:
            seconds = [r[key]["seconds"] for r in rows if r.get(key)]
            timing[key + "_seconds_median"] = (
                statistics.median(seconds) if seconds else None
            )
        for key in ["instrumented_execution_seconds", "save_seconds"]:
            seconds = [r["measurement"][key] for r in rows if r.get("measurement")]
            timing[key + "_median"] = statistics.median(seconds) if seconds else None
        arms[arm] = {
            "runs": len(rows),
            "clean_runs": len(clean),
            "clean_accepted": sum(r["task_accepted"] for r in clean),
            "clean_quality_passed": sum(r["quality_passed"] for r in clean),
            "sentinel_runs": len(faulty),
            "sentinels_correctly_rejected": sum(r["matches_expected"] for r in faulty),
            "execution_failures": sum(
                not r.get("execution") or r["execution"]["returncode"] != 0
                for r in rows
            ),
            "max_clean_absolute_error": errors,
            "measured_clean_values": measured_counts,
            "machine_timing": timing,
        }
    return {
        "complete": complete,
        "expected_runs": len(wanted),
        "runs": len(records),
        "passed": complete
        and all(r["matches_expected"] for r in records)
        and all(p["identical"] and p["outcome_agreement"] for p in pairs),
        "arms": arms,
        "repetition_pairs": pairs,
    }


def producer_path(root, arm):
    return root / "benchmarks/certified/producers" / ("build-" + arm + ".py")


def journal_events(path):
    return (
        [json.loads(line) for line in path.read_text().splitlines()]
        if path.exists()
        else []
    )


def active_session(events):
    active = None
    for event in events:
        if event["event"] == "begin":
            if active:
                raise ValueError("overlapping development sessions")
            active = event
        elif event["event"] in {"attempt", "end", "protocol_revision"}:
            if (
                not active
                or active["session"] != event["session"]
                or active["arm"] != event["arm"]
            ):
                raise ValueError("development event has no matching live begin")
            if event["event"] == "protocol_revision":
                if active["protocol_sha256"] != event["from_protocol_sha256"]:
                    raise ValueError(
                        "protocol amendment does not match the live session"
                    )
                active = {
                    **active,
                    "initial_protocol_sha256": active.get(
                        "initial_protocol_sha256", active["protocol_sha256"]
                    ),
                    "protocol_sha256": event["to_protocol_sha256"],
                    "protocol_revisions": [
                        *active.get("protocol_revisions", []),
                        event,
                    ],
                }
            elif event["event"] == "end":
                active = None
        else:
            raise ValueError("unknown development event")
    return active


def append_event(path, event):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf8") as handle:
        handle.write(json.dumps(event, allow_nan=False, sort_keys=True) + "\n")


def begin_session(root, arm, journal):
    protocol = M["read_protocol"](root)
    events = journal_events(journal)
    if active_session(events):
        raise ValueError(
            "finish the existing live producer session; clocks are not reset"
        )
    ended = [e["arm"] for e in events if e["event"] == "end"]
    if (
        ended != protocol["arms"][: len(ended)]
        or len(ended) >= len(protocol["arms"])
        or arm != protocol["arms"][len(ended)]
    ):
        raise ValueError(
            "development sessions must follow the frozen Matplotlib-then-GraphUnslopify order"
        )
    if producer_path(root, arm).exists():
        raise ValueError("producer must be absent before its task clock begins")
    event = {
        "event": "begin",
        "arm": arm,
        "session": str(uuid.uuid4()),
        "utc": utc(),
        "monotonic_ns": time.monotonic_ns(),
        "protocol_sha256": sha(root / "benchmarks/certified/protocol.json"),
    }
    append_event(journal, event)
    return event


def amend_session(root, arm, journal, reason):
    """Retain the original clock and explicitly flag an SVG-evidence protocol correction."""
    active = active_session(journal_events(journal))
    protocol = M["read_protocol"](root)
    previous = protocol["previous_protocol"]
    old_path = root / previous["path"]
    old = json.loads(old_path.read_text())
    if (
        not active
        or active["arm"] != arm
        or active["protocol_sha256"] != previous["sha256"]
        or sha(old_path) != previous["sha256"]
        or not reason.strip()
    ):
        raise ValueError(
            "amendment requires the matching live session and retained prior protocol"
        )
    unchanged_keys = [
        "source_manifest_sha256",
        "dataset_order",
        "arms",
        "variants",
        "repeats",
        "order",
        "formats",
        "width_in",
        "height_in",
        "dpi",
        "minimum_text_pt",
        "minimum_interval_pixels",
        "task",
        "accuracy",
        "reproducibility",
        "timing",
        "development_sessions",
        "x_label",
        "title_template",
        "y_labels",
    ]
    if (
        any(old[k] != protocol[k] for k in unchanged_keys)
        or protocol.get("svg_identity") != "native_graphic_dom_v2"
    ):
        raise ValueError(
            "this correction must not change cases, numerical/physical gates or task-clock rules"
        )
    event = {
        "event": "protocol_revision",
        "arm": arm,
        "session": active["session"],
        "utc": utc(),
        "monotonic_ns": time.monotonic_ns(),
        "from_protocol_sha256": active["protocol_sha256"],
        "to_protocol_sha256": sha(root / "benchmarks/certified/protocol.json"),
        "reason": reason,
        "clock_reset": False,
        "timing_comparison_valid": False,
    }
    append_event(journal, event)
    return event


def finish_attempt(root, arm, journal, report, output):
    events = journal_events(journal)
    start = active_session(events)
    if (
        not start
        or start["arm"] != arm
        or start["protocol_sha256"] != sha(root / "benchmarks/certified/protocol.json")
    ):
        raise ValueError("this producer has no live session for the frozen protocol")
    protocol = M["read_protocol"](root)
    expected = schedule(protocol, arm)
    rows = report.get("records", [])
    identity = lambda row: (row["dataset"], row["arm"], row["variant"], row["repeat"])
    proven = (
        len(rows) == len(expected)
        and [identity(r) for r in rows] == [identity(r) for r in expected]
        and all(
            r["matches_expected"]
            and r["task_accepted"]
            and r["producer_sha256"] == sha(producer_path(root, arm))
            for r in rows
        )
    )
    if report["passed"] and not proven:
        raise ValueError("a session cannot end without all nine verified clean cases")
    number = 1 + sum(
        e["event"] == "attempt" and e["session"] == start["session"] for e in events
    )
    destination = (
        root
        / "benchmarks/certified/development"
        / start["session"]
        / f"attempt-{number}.json"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    M["write_json"](destination, report)
    evidence = {
        "arm": arm,
        "session": start["session"],
        "utc": utc(),
        "monotonic_ns": time.monotonic_ns(),
        "report": destination.relative_to(root).as_posix(),
        "report_sha256": sha(destination),
        "output": str(output),
        "successful": report["passed"],
    }
    append_event(journal, {"event": "attempt", **evidence})
    if report["passed"]:
        end = {
            "event": "end",
            **evidence,
            "seconds": (evidence["monotonic_ns"] - start["monotonic_ns"]) / 1e9,
            "producer_sha256": sha(producer_path(root, arm)),
            "protocol_sha256": start["protocol_sha256"],
            "initial_protocol_sha256": start.get(
                "initial_protocol_sha256", start["protocol_sha256"]
            ),
            "protocol_amended_during_session": bool(start.get("protocol_revisions")),
            "timing_comparison_valid": not bool(start.get("protocol_revisions")),
            "timing_note": "Includes shared evaluator repair; do not compare workflow authoring speed"
            if start.get("protocol_revisions")
            else "One familiar AI operator, fixed order; no causal/human productivity inference",
        }
        if end["seconds"] < 0:
            raise ValueError("monotonic clock reset; retain the session as incomplete")
        append_event(journal, end)
        return end
    return None


def environment(root):
    import graphunslopify

    package = Path(graphunslopify.__file__).resolve().parent
    if package != (root / "python/graphunslopify").resolve():
        raise ValueError("install the current checkout with pip install -e ./python")
    paths = [
        *package.glob("*.py"),
        package / "_translator.mjs",
        *package.glob("schemas/*.json"),
    ]
    common = [
        "benchmarks/certified/corpus.py",
        "benchmarks/certified/measurement.py",
        "benchmarks/certified/runner.py",
        "scripts/measure-certified-figure.py",
        "scripts/certified-benchmark.py",
    ]
    head = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return {
        "git_head": head,
        "git_dirty": bool(dirty),
        "python": sys.version,
        "platform": {"system": platform.system(), "machine": platform.machine()},
        "versions": {
            name: importlib.metadata.version(name)
            for name in [
                "graphunslopify",
                "numpy",
                "pandas",
                "matplotlib",
                "Pillow",
                "pypdf",
                "nodejs-wheel-binaries",
            ]
        },
        "installed_source_sha256": {
            p.relative_to(package).as_posix(): sha(p) for p in sorted(paths)
        },
        "common_source": {
            name: {
                "sha256": sha(root / name),
                "bytes": (root / name).stat().st_size,
                "nonblank_lines": sum(
                    bool(s.strip()) for s in (root / name).read_text().splitlines()
                ),
            }
            for name in common
        },
        "prior_shared_development_time": "unmeasured; excluded from live producer sessions",
    }


def run(root, source_dir, prepared_dir, output, *, development_arm=None, journal=None):
    protocol = M["read_protocol"](root)
    inputs = load_inputs(root, source_dir, prepared_dir)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("choose an empty output directory; prior evidence is retained")
    if development_arm:
        active = active_session(journal_events(journal))
        if (
            not active
            or active["arm"] != development_arm
            or active["protocol_sha256"]
            != sha(root / "benchmarks/certified/protocol.json")
        ):
            raise ValueError(
                "begin the matching live session before producer implementation"
            )
    plan = schedule(protocol, development_arm)
    for arm in {e["arm"] for e in plan}:
        if not producer_path(root, arm).is_file():
            raise ValueError(
                f"missing producer {arm}; implement it under the live session protocol"
            )
    output.mkdir(parents=True, exist_ok=True)
    setup = {
        "schema_version": 1,
        "phase": "development" if development_arm else "benchmark",
        "started_at": utc(),
        "protocol": protocol,
        "protocol_sha256": sha(root / "benchmarks/certified/protocol.json"),
        "environment": environment(root),
        "schedule": plan,
    }
    M["write_json"](output / "setup.json", setup)
    lookup = {i["source"]["id"]: i for i in inputs}
    records = []
    for entry in plan:
        folder = (
            output
            / "runs"
            / str(entry["repeat"])
            / entry["dataset"]
            / entry["arm"]
            / entry["variant"]
        )
        records.append(
            run_case(root, folder, entry, lookup[entry["dataset"]], protocol)
        )
        M["write_json"](
            output / f"progress-{len(records):03}.json",
            {
                "completed": len(records),
                "expected": len(plan),
                "case": entry,
                "matches_expected": records[-1]["matches_expected"],
            },
        )
    for record in records:
        folder = (
            output
            / "runs"
            / str(record["repeat"])
            / record["dataset"]
            / record["arm"]
            / record["variant"]
        )
        retain_case(root, folder, record, lookup[record["dataset"]], protocol)
    if development_arm:
        summary = {
            "complete": len(records) == len(plan),
            "expected_runs": len(plan),
            "runs": len(records),
            "passed": len(records) == len(plan)
            and all(r["matches_expected"] for r in records),
        }
    else:
        summary = summarize(records, protocol)
    report = {
        **setup,
        "completed_at": utc(),
        **summary,
        "records": records,
        "scope": "Project-run evaluation against external NIST facts; live author clocks describe one familiar AI operator, not human or causal productivity; quality proxies are not human judgments",
    }
    M["write_json"](output / "results.json", report)
    if development_arm:
        finish_attempt(root, development_arm, journal, report, output)
    return report
