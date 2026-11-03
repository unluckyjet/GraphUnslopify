"""Bounded local experiment histories. Importing records never certifies a study."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import re
import stat
import struct
from collections import Counter, defaultdict
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

MAX_FILES = 256
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_NORMALIZED_BYTES = 64 * 1024 * 1024
MAX_RECORDS = 100_000
MAX_POINTS = 200_000
COLUMNS = [
    "run_id",
    "run",
    "metric",
    "step",
    "value",
    "wall_time",
    "source_file",
    "source_record",
    "source_offset",
    "session",
]


class ExperimentError(ValueError):
    """A complete, owned experiment selection cannot be established."""


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def _text(value, label, limit=256):
    if not isinstance(value, str) or not value or len(value) > limit or "\x00" in value:
        raise ExperimentError(f"{label} must be nonempty text of at most {limit} characters")
    return value


def _number(value):
    if value is None or value == "":
        return None, "missing"
    # Preserve signed64 integer literals/tensors;float64 merges adjacent integers above2**53.
    if isinstance(value, int) and not isinstance(value, bool):
        integer = value
    elif isinstance(value, str) and re.fullmatch(r"[+-]?[0-9]+", value.strip()):
        literal = value.strip()
        digits = literal.lstrip("+-").lstrip("0") or "0"
        if len(digits) > 19:
            return None, "integer_out_of_range"
        integer = int(digits) * (-1 if literal.startswith("-") else 1)
    else:
        integer = None
    if integer is not None:
        return (integer, None) if -(2**63) <= integer < 2**63 else (None, "integer_out_of_range")
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        return None, "not_numeric"
    return (number, None) if math.isfinite(number) else (None, "nonfinite")


def _config(source, provider, step_field, metrics):
    if provider not in {"csv", "tensorboard"}:
        raise ExperimentError(
            "Choose csv or tensorboard;remote tracker adapters are not installed here"
        )
    root = Path(_text(str(source), "Source path", 4096)).expanduser().resolve(strict=True)
    if not root.is_dir() and not (provider == "csv" and root.is_file()):
        raise ExperimentError("Choose a result folder,or a CSV file for the CSV provider")
    _text(step_field, "Step column")
    if metrics is not None:
        if not isinstance(metrics, list) or not 1 <= len(metrics) <= 128:
            raise ExperimentError("Metric columns must be a list of 1-128 names")
        metrics = sorted({_text(name, "Metric column") for name in metrics})
    return {
        "source": str(root),
        "provider": provider,
        "step_field": step_field,
        "metrics": metrics,
        "restart_policy": "preserve_all_records",
    }


def _discover(config):
    root = Path(config["source"])
    base = root if root.is_dir() else root.parent
    paths = []
    visited = 0
    candidates = [root] if root.is_file() else None
    if candidates is None:
        candidates = []
        pending = [(root, 0)]
        while pending:
            folder, depth = pending.pop()
            visited += 1
            if visited > 1024 or depth > 8:
                raise ExperimentError("Source folder exceeds the directory/depth bound")
            with os.scandir(folder) as entries:
                for count, entry in enumerate(entries, 1):
                    if count > 4096:
                        raise ExperimentError("A source directory contains too many entries")
                    if entry.is_dir(follow_symlinks=False):
                        if len(pending) + visited >= 1024:
                            raise ExperimentError("Source folder exceeds the directory/depth bound")
                        pending.append((Path(entry.path), depth + 1))
                        continue
                    match = (
                        entry.name.lower().endswith(".csv")
                        if config["provider"] == "csv"
                        else entry.name.startswith("events.out.tfevents.")
                    )
                    if match:
                        candidates.append(Path(entry.path))
                        if len(candidates) > MAX_FILES:
                            raise ExperimentError(f"Choose at most {MAX_FILES} source files")
    for path in sorted(candidates):
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(base) or path.is_symlink() or not resolved.is_file():
            raise ExperimentError(
                "Experiment files must be contained regular files,not symbolic links"
            )
        paths.append((path.relative_to(base).as_posix(), resolved))
    if not paths:
        raise ExperimentError("No matching experiment files in the selected source")
    return paths


def _contained_bytes(base, relative):
    """Open every relative component without following symlinks on POSIX."""
    if os.open in os.supports_dir_fd and hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY"):
        directory = os.open(base, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            parts = Path(relative).parts
            for part in parts[:-1]:
                child = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
                )
                os.close(directory)
                directory = child
            descriptor = os.open(
                parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
            )
            with os.fdopen(descriptor, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_BYTES:
                    raise ExperimentError(f"Source must be a bounded regular file: {relative}")
                return stream.read(MAX_FILE_BYTES + 1)
        finally:
            os.close(directory)
    # Platforms without relative descriptor opens still refuse changed/escaped paths.
    path = base / relative
    before = path.resolve(strict=True)
    if not before.is_relative_to(base) or path.is_symlink():
        raise ExperimentError("Experiment source escaped its selected folder")
    with path.open("rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_BYTES:
            raise ExperimentError(f"Source must be a bounded regular file: {relative}")
        content = stream.read(MAX_FILE_BYTES + 1)
    if (
        path.is_symlink()
        or path.resolve(strict=True) != before
        or path.stat().st_ino != info.st_ino
    ):
        raise ExperimentError("Experiment source changed during its read")
    return content


def _read_files(config):
    files, contents = [], {}
    total = 0
    source = Path(config["source"])
    base = source if source.is_dir() else source.parent
    for relative, _ in _discover(config):
        content = _contained_bytes(base, relative)
        total += len(content)
        if len(content) > MAX_FILE_BYTES or total > MAX_SOURCE_BYTES:
            raise ExperimentError("Experiment source exceeds the bounded byte budget")
        files.append(
            {"path": relative, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
        )
        contents[relative] = content
    return files, contents


def _crc32c(data):
    # Reflected Castagnoli polynomial;TFRecord uses CRC32C,not zlib's CRC32.
    crc = 0xFFFFFFFF
    for byte in data:
        crc = (crc >> 8) ^ _CRC32C_TABLE[(crc ^ byte) & 255]
    return crc ^ 0xFFFFFFFF


def _crc_table():
    table = []
    for index in range(256):
        value = index
        for _ in range(8):
            value = (value >> 1) ^ (0x82F63B78 if value & 1 else 0)
        table.append(value)
    return tuple(table)


_CRC32C_TABLE = _crc_table()


def _masked_crc(data):
    crc = _crc32c(data)
    return (((crc >> 15) | (crc << 17)) + 0xA282EAD8) & 0xFFFFFFFF


def _frames(content, name):
    offset, count = 0, 0
    while offset < len(content):
        start = offset
        if len(content) - offset < 16:
            raise ExperimentError(f"Truncated TensorBoard record: {name} at byte {offset}")
        length, length_crc = struct.unpack_from("<QI", content, offset)
        if _masked_crc(content[offset : offset + 8]) != length_crc:
            raise ExperimentError(f"TensorBoard length CRC mismatch: {name} at byte {offset}")
        if length > MAX_FILE_BYTES or offset + 16 + length > len(content):
            raise ExperimentError(
                f"Truncated/oversized TensorBoard payload: {name} at byte {offset}"
            )
        payload = content[offset + 12 : offset + 12 + length]
        if _masked_crc(payload) != struct.unpack_from("<I", content, offset + 12 + length)[0]:
            raise ExperimentError(f"TensorBoard payload CRC mismatch: {name} at byte {offset}")
        offset += 16 + length
        count += 1
        if count > MAX_RECORDS:
            raise ExperimentError("TensorBoard file exceeds the record bound")
        yield count, start, payload


def _csv_points(config, contents):
    points, labels, ignored = [], {}, []
    for name, content in contents.items():
        identity = _digest([config["source"], "csv", name])[:24]
        labels[identity] = name
        try:
            reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")), strict=True)
            fields = reader.fieldnames
            if not fields or len(fields) > 128 or len(fields) != len(set(fields)):
                raise ExperimentError(f"CSV needs 1-128 unique column names: {name}")
            for field in fields:
                _text(field, "CSV column")
            if config["step_field"] not in fields:
                raise ExperimentError(f"CSV lacks step column {config['step_field']}: {name}")
            metric_names = config["metrics"] or [
                f for f in fields if f not in {config["step_field"], "wall_time"}
            ]
            if set(metric_names) - set(fields):
                raise ExperimentError(f"CSV lacks requested metric columns: {name}")
            start = len(points)
            for index, row in enumerate(reader, 1):
                if index > MAX_RECORDS:
                    raise ExperimentError("CSV exceeds the row bound")
                if None in row or any(value is None for value in row.values()):
                    raise ExperimentError(
                        f"CSV row has a different number of fields: {name}:{reader.line_num}"
                    )
                step, step_issue = _number(row[config["step_field"]])
                wall_time, _ = _number(row.get("wall_time"))
                for metric in metric_names:
                    value, issue = _number(row[metric])
                    points.append(
                        {
                            "run_id": identity,
                            "metric": metric,
                            "step": step,
                            "value": value,
                            "wall_time": wall_time,
                            "source_file": name,
                            "source_record": index,
                            "source_offset": None,
                            "session": 0,
                            "issue": ("step_" + step_issue) if step_issue else issue,
                        }
                    )
                    if len(points) > MAX_POINTS:
                        raise ExperimentError(
                            "Select fewer files/metric columns;point budget exceeded"
                        )
            if config["metrics"] is None:
                numeric = {p["metric"] for p in points[start:] if p["value"] is not None}
                ignored.extend(
                    {"source_file": name, "metric": metric, "reason": "no numeric values"}
                    for metric in metric_names
                    if metric not in numeric
                )
                points[start:] = [p for p in points[start:] if p["metric"] in numeric]
        except (UnicodeError, csv.Error) as error:
            raise ExperimentError(f"Could not parse UTF-8 CSV {name}: {error}") from error
    return points, labels, ignored, {"name": "Python csv.DictReader", "mode": "one_file_per_run"}


def _tensorboard_points(config, contents):
    try:
        from tensorboard.compat.proto import event_pb2
        from tensorboard.util import tensor_util
    except ImportError as error:
        raise ExperimentError(
            "TensorBoard import needs the optional experiments extra;install current source with python[experiments]"
        ) from error
    points, labels, ignored, sessions = [], {}, [], {}
    records, summaries = 0, 0
    for name, content in contents.items():
        directory = Path(name).parent.as_posix()
        identity = _digest([config["source"], "tensorboard", directory])[:24]
        labels[identity] = directory if directory != "." else Path(config["source"]).name
        sessions.setdefault(identity, 0)
        for index, offset, payload in _frames(content, name):
            records += 1
            if records > MAX_RECORDS:
                raise ExperimentError("TensorBoard source exceeds the total record bound")
            try:
                event = event_pb2.Event.FromString(payload)
            except Exception as error:
                raise ExperimentError(
                    f"Invalid TensorBoard event protobuf: {name}:{index}"
                ) from error
            if (
                event.HasField("session_log")
                and event.session_log.status == event_pb2.SessionLog.START
            ):
                sessions[identity] += 1
            summaries += len(event.summary.value)
            if summaries > MAX_POINTS:
                raise ExperimentError("TensorBoard source exceeds the summary bound")
            for summary in event.summary.value:
                tag = _text(summary.tag, "TensorBoard metric tag", 1024)
                if config["metrics"] and tag not in config["metrics"]:
                    continue
                value, issue = None, None
                if summary.HasField("simple_value"):
                    value, issue = _number(summary.simple_value)
                elif summary.HasField("tensor") and summary.metadata.plugin_data.plugin_name in {
                    "",
                    "scalars",
                }:
                    try:
                        if (
                            summary.tensor.tensor_shape.dim
                            or summary.tensor.tensor_shape.unknown_rank
                        ):
                            raise ValueError("only numeric scalar tensors are supported")
                        tensor = tensor_util.make_ndarray(summary.tensor)
                        if tensor.ndim != 0 or tensor.dtype.kind not in "biuf":
                            raise ValueError("only numeric scalar tensors are supported")
                        value, issue = _number(tensor.item())
                    except (ValueError, TypeError, KeyError, OverflowError) as error:
                        ignored.append(
                            {
                                "run_id": identity,
                                "source_file": name,
                                "source_record": index,
                                "metric": tag,
                                "reason": str(error)[:200],
                            }
                        )
                        continue
                else:
                    ignored.append(
                        {
                            "run_id": identity,
                            "source_file": name,
                            "source_record": index,
                            "metric": tag,
                            "reason": "not a supported scalar summary",
                        }
                    )
                    continue
                if len(ignored) > MAX_POINTS:
                    raise ExperimentError("Too many unsupported TensorBoard summaries")
                wall_time, _ = _number(event.wall_time)
                points.append(
                    {
                        "run_id": identity,
                        "metric": tag,
                        "step": event.step,
                        "value": value,
                        "wall_time": wall_time,
                        "source_file": name,
                        "source_record": index,
                        "source_offset": offset,
                        "session": sessions[identity],
                        "issue": issue,
                    }
                )
                if len(points) > MAX_POINTS:
                    raise ExperimentError("TensorBoard source exceeds the scalar point budget")
    return (
        points,
        labels,
        ignored,
        {
            "name": "CRC32C TFRecord + TensorBoard Event protobuf",
            "tensorboard": version("tensorboard"),
            "sampling": "none",
        },
    )


@dataclass
class ExperimentSnapshot:
    config: dict
    files: list
    points: list
    labels: dict
    ignored: list
    reader: dict

    @property
    def identity(self):
        return _digest(
            {"schema_version": 1, "config": self.config, "files": self.files, "reader": self.reader}
        )

    def recheck(self):
        files, _ = _read_files(self.config)
        if files != self.files:
            raise ExperimentError("Experiment source changed;list the runs again before importing")

    def catalog(self):
        runs = []
        grouped = defaultdict(lambda: defaultdict(list))
        for point in self.points:
            grouped[point["run_id"]][point["metric"]].append(point)
        for identity, name in sorted(self.labels.items(), key=lambda item: (item[1], item[0])):
            metrics = []
            for metric, rows in sorted(grouped[identity].items()):
                valid = [p for p in rows if p["issue"] is None]
                counts = Counter(p["step"] for p in valid)
                metrics.append(
                    {
                        "name": metric,
                        "records": len(rows),
                        "valid_records": len(valid),
                        "excluded": dict(Counter(p["issue"] for p in rows if p["issue"])),
                        "duplicate_steps": sum(n - 1 for n in counts.values()),
                        "sessions": len({p["session"] for p in rows}),
                    }
                )
            runs.append({"id": identity, "name": name, "metrics": metrics})
        return {
            "schema_version": 1,
            "snapshot": self.identity,
            "config": self.config,
            "reader": self.reader,
            "files": self.files,
            "runs": runs,
            "ignored": self.ignored[:100],
            "ignored_total": len(self.ignored),
            "complete": True,
            "new_execution": False,
            "scope": "Complete bounded eligible regular-file inventory;directory symlinks are excluded. No sampling,purge,aggregation or scientific acceptance.",
        }


def _snapshot(source, *, provider="csv", step_field="step", metrics=None, tracker=None):
    if provider in {"mlflow", "wandb"}:
        from .tracker_imports import tracker_snapshot

        return tracker_snapshot(source, provider=provider, metrics=metrics, tracker=tracker)
    config = _config(source, provider, step_field, metrics)
    files, contents = _read_files(config)
    points, labels, ignored, reader = (_csv_points if provider == "csv" else _tensorboard_points)(
        config, contents
    )
    result = ExperimentSnapshot(config, files, points, labels, ignored, reader)
    result.recheck()
    return result


def experiment_runs(source, *, provider="csv", step_field="step", metrics=None, tracker=None):
    """List complete local run/metric evidence;never execute programs or modify source files."""
    return _snapshot(
        source, provider=provider, step_field=step_field, metrics=metrics, tracker=tracker
    ).catalog()


@dataclass
class ExperimentComparison:
    csv_bytes: bytes
    spec: dict
    report: dict
    source: ExperimentSnapshot


def experiment_comparison(
    source,
    *,
    runs,
    metric,
    expected_snapshot,
    provider="csv",
    step_field="step",
    metrics=None,
    kind="line",
    tracker=None,
):
    """Prepare an unapplied comparison of selected raw metric values,no inferred statistics."""
    snapshot = _snapshot(
        source, provider=provider, step_field=step_field, metrics=metrics, tracker=tracker
    )
    if expected_snapshot != snapshot.identity:
        raise ExperimentError("Experiment source/reader/options changed;list the runs again")
    if (
        not isinstance(runs, list)
        or not runs
        or len(runs) != len(set(runs))
        or set(runs) - set(snapshot.labels)
    ):
        raise ExperimentError("Choose distinct run IDs from this source snapshot")
    _text(metric, "Metric", 1024)
    if any(p.get("run_id") in runs and p["metric"] == metric for p in snapshot.ignored):
        raise ExperimentError(
            "Selected metric contains unsupported scalar representations;choose a fully supported metric"
        )
    if kind not in {"line", "scatter"}:
        raise ExperimentError("Comparative histories support line or scatter")
    selected = [p for p in snapshot.points if p["run_id"] in runs and p["metric"] == metric]
    valid = [p for p in selected if p["issue"] is None]
    if not valid or any(not any(p["run_id"] == identity for p in valid) for identity in runs):
        raise ExperimentError("Each selected run needs finite observations for the chosen metric")
    duplicates = sum(n - 1 for n in Counter((p["run_id"], p["step"]) for p in valid).values())
    if duplicates and kind == "line":
        raise ExperimentError(
            "Duplicate steps remain in these histories;choose scatter to keep every record without implying a line order"
        )

    class BoundedCSV(io.StringIO):
        size = 0

        def write(self, value):
            self.size += len(value.encode("utf-8"))
            if self.size > MAX_NORMALIZED_BYTES:
                raise ExperimentError("Normalized history exceeds the bounded byte budget")
            return super().write(value)

    text = BoundedCSV(newline="")
    writer = csv.DictWriter(text, fieldnames=COLUMNS)
    writer.writeheader()
    by_run = defaultdict(list)
    for point in valid:
        by_run[point["run_id"]].append(point)
    for identity in runs:
        for point in by_run[identity]:
            writer.writerow(
                {
                    key: (
                        f"{snapshot.labels[identity]} [{identity[:8]}]"
                        if key == "run"
                        else point.get(key)
                    )
                    for key in COLUMNS
                }
            )
    spec = {
        "kind": kind,
        "title": metric + " across selected runs",
        "group": "run",
        "data": {"path": "experiment-history.csv", "format": "csv", "columns": COLUMNS},
        "x": {"field": "step", "label": "Step"},
        "y": {"field": "value", "label": metric},
        "output": {"stem": "experiment-comparison", "formats": ["png", "svg", "pdf"]},
    }
    if kind == "line":
        spec.update(aggregation="none", marker=True)
    excluded = [p for p in selected if p["issue"]]
    report = {
        "schema_version": 1,
        "snapshot": snapshot.identity,
        "config": snapshot.config,
        "reader": snapshot.reader,
        "files": snapshot.files,
        "runs": runs,
        "metric": metric,
        "kind": kind,
        "records": len(valid),
        "duplicate_steps": duplicates,
        "excluded_records": len(excluded),
        "exclusions": excluded[:100],
        "exclusions_truncated": len(excluded) > 100,
        "applied": False,
        "verified": False,
        "new_execution": False,
        "aggregation": "none",
        "restart_policy": "preserve_all_records",
        "scope": "Selected raw values only. Review exclusions and experimental meaning. Run labels are identities,not independent sampling units.",
    }
    snapshot.recheck()
    return ExperimentComparison(text.getvalue().encode(), spec, report, snapshot)


def render_experiment_comparison(comparison, destination, *, accept_exclusions=False):
    """Write a new owned comparison folder and run the canonical renderer strictly."""
    import copy

    from .build import Figure, SpecError

    if comparison.report["excluded_records"] and accept_exclusions is not True:
        raise ExperimentError("Review exclusions and explicitly accept valid rows before rendering")
    source = Path(comparison.source.config["source"])
    out = Path(destination).expanduser().resolve()
    if source.is_dir() and out.is_relative_to(source):
        raise ExperimentError("Choose an output outside the experiment source folder")
    comparison.source.recheck()
    out.mkdir(parents=True, exist_ok=False)
    data = out / "experiment-history.csv"
    data.write_bytes(comparison.csv_bytes)
    (out / "experiment.figure.json").write_text(
        json.dumps(comparison.spec, indent=2), encoding="utf8"
    )
    spec = copy.deepcopy(comparison.spec)
    spec["data"]["path"] = str(data)
    report = copy.deepcopy(comparison.report)
    report.update(
        applied=True, materialized_csv_sha256=hashlib.sha256(comparison.csv_bytes).hexdigest()
    )
    native, error = None, None
    try:
        native = Figure(spec).render(cwd=out, api="local")["report"]
        comparison.source.recheck()
        if data.read_bytes() != comparison.csv_bytes:
            raise ExperimentError("Materialized history changed during rendering")
        code = 0
    except SpecError as problem:
        native, error = problem.report, str(problem)
        code = 2 if native is not None else 1
    except ExperimentError as problem:
        error, code = str(problem), 2
    result = {
        "schema_version": 1,
        "directory": str(out),
        "exit_code": code,
        "scientific_status": native.get("status") if native else "incomplete",
        "import": report,
        "native_report": native,
        "error": error,
        "scope": "Actual strict native comparison;import provenance does not certify scientific assumptions.",
    }
    (out / "experiment-import.json").write_text(
        json.dumps(result, indent=2, allow_nan=False), encoding="utf8"
    )
    return result
