"""Explicit bounded tracker access;SDKs run in an owned worker,not the editor."""

from __future__ import annotations

import copy
import hashlib
import ipaddress
import json
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .experiment_imports import (
    ExperimentError,
    ExperimentSnapshot,
    _contained_bytes,
    _digest,
    _number,
    _text,
)
from .worker_process import JsonWorker, WorkerError

MAX_OUTPUT = 64 * 1024 * 1024
MAX_POINTS = 200_000
MAX_RUNS = 256
MAX_RSS = 1024 * 1024 * 1024
DEFAULT_WANDB_ENDPOINT = "https://api.forge.coreweave.com"


def endpoint(value):
    value = _text(value, "Tracker endpoint", 4096).rstrip("/")
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ExperimentError(
            "Tracker endpoints need HTTP(S),a host and no embedded credentials/query"
        )
    try:
        loopback = ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        loopback = parsed.hostname.lower() == "localhost"
    if parsed.scheme == "http" and not loopback:
        raise ExperimentError("Use HTTPS for remote trackers;HTTP is limited to loopback servers")
    return value


def configuration(source, provider, metrics, tracker):
    tracker = tracker or {}
    if not isinstance(tracker, dict):
        raise ExperimentError("Tracker settings must be an object")
    if metrics is not None:
        if not isinstance(metrics, list) or not 1 <= len(metrics) <= 128:
            raise ExperimentError("Choose 1-128 metric names")
        metrics = sorted({_text(name, "Metric", 1024) for name in metrics})
    source = _text(str(source), "Tracker source", 4096)
    key = tracker.get("api_key")
    if key is not None and (
        not isinstance(key, str) or not 1 <= len(key) <= 8192 or any(c in key for c in "\r\n\x00")
    ):
        raise ExperimentError("Tracker credential must be bounded single-line text")
    cfg = {
        "provider": provider,
        "source": source,
        "metrics": metrics,
        "step_field": "step",
        "restart_policy": "preserve_all_records",
        "completed_only": True,
    }
    if provider == "mlflow":
        ids = tracker.get("experiment_ids")
        if not isinstance(ids, list) or not 1 <= len(ids) <= 16:
            raise ExperimentError("Choose 1-16 explicit MLflow experiment IDs")
        cfg["experiment_ids"] = sorted({_text(i, "Experiment ID", 128) for i in ids})
        if urlsplit(source).scheme in {"https", "http"}:
            cfg["source"] = endpoint(source)
            cfg["transport"] = "http"
        else:
            if source.startswith("sqlite:///"):
                source = unquote(source[len("sqlite:///") :])
            elif urlsplit(source).scheme not in {"", "file"}:
                raise ExperimentError("MLflow supports SQLite files or HTTP(S) tracking servers")
            elif source.startswith("file:"):
                source = unquote(urlsplit(source).path)
            path = Path(source).expanduser().resolve(strict=True)
            if not path.is_file():
                raise ExperimentError("Choose an existing MLflow SQLite file,not a new store")
            cfg.update(source=str(path), transport="sqlite_copy")
    elif provider == "wandb":
        import re

        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}/[A-Za-z0-9_.-]{1,128}", source):
            raise ExperimentError("W&B source is an explicit entity/project")
        cfg["endpoint"] = endpoint(tracker.get("endpoint") or DEFAULT_WANDB_ENDPOINT)
        cfg["transport"] = "wandb_sdk"
        if not key:
            raise ExperimentError("W&B needs an explicit API key;interactive SDK login is disabled")
    else:
        raise ExperimentError("Unknown tracker provider")
    if cfg["transport"] != "sqlite_copy" and tracker.get("allow_remote") is not True:
        raise ExperimentError(
            "Review the tracker endpoint/data disclosure and explicitly allow this network read"
        )
    return cfg, {"api_key": key}


def _sqlite_files(config, destination=None):
    source = Path(config["source"])
    files = []
    total = 0
    names = [source.name] + [
        source.name + suffix
        for suffix in ["-wal", "-journal"]
        if source.with_name(source.name + suffix).exists()
        or source.with_name(source.name + suffix).is_symlink()
    ]
    for name in names:
        content = _contained_bytes(source.parent, name)
        total += len(content)
        if len(content) > 20 * 1024 * 1024 or total > MAX_OUTPUT:
            raise ExperimentError("MLflow SQLite snapshot exceeds byte limits")
        if name == source.name and not content.startswith(b"SQLite format 3\x00"):
            raise ExperimentError("Source is not an existing SQLite database")
        files.append(
            {"path": name, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
        )
        if destination is not None:
            suffix = name[len(source.name) :]
            (destination / ("source.sqlite" + suffix)).write_bytes(content)
    return files


def _worker(config, access):
    try:
        import psutil
    except ImportError as problem:
        raise ExperimentError(
            "Install graphunslopify[experiments] for bounded tracker workers"
        ) from problem
    with tempfile.TemporaryDirectory(prefix="gu-tracker-") as directory:
        root = Path(directory)
        local_before = _sqlite_files(config, root) if config["transport"] == "sqlite_copy" else []
        if local_before and _sqlite_files(config) != local_before:
            raise ExperimentError("MLflow source changed during snapshot copying")
        package = Path(__file__).resolve().parent.parent
        bootstrap = (
            "import os,sys; sys.path[:]=[p for p in sys.path if p and os.path.normcase(os.path.realpath(p)) != os.path.normcase(os.path.realpath(os.getcwd()))]; "
            + f"sys.path.insert(0,{str(package)!r}); "
            + "import runpy; runpy.run_module('graphunslopify.tracker_worker',run_name='__main__')"
        )
        worker = JsonWorker(
            [sys.executable, "-c", bootstrap],
            root,
            kind="tracker",
            max_requests=1,
            expected_ready={"adapter_version": 1},
        )
        stopped = threading.Event()
        overflow = threading.Event()
        owned = {}

        def monitor():
            while not stopped.wait(0.05):
                connection = worker.connection
                if connection is None:
                    continue
                try:
                    parent = psutil.Process(connection.process.pid)
                    processes = [parent, *parent.children(recursive=True)]
                    rss = 0
                    for process in processes:
                        owned[(process.pid, process.create_time())] = process
                        rss += process.memory_info().rss
                    if rss > MAX_RSS:
                        overflow.set()
                        connection.process.kill()
                        return
                except (psutil.Error, OSError):
                    continue

        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()
        try:
            try:
                answer, _ = worker.request({"config": config, "access": access}, timeout=90)
            except (WorkerError, TimeoutError, subprocess.TimeoutExpired) as problem:
                if overflow.is_set():
                    raise ExperimentError(
                        "Tracker worker exceeded the1GiB process-tree memory budget"
                    ) from problem
                if isinstance(problem, WorkerError) and str(problem).startswith(
                    "Install graphunslopify[experiments]"
                ):
                    raise ExperimentError(
                        "Install graphunslopify[experiments] for this tracker SDK"
                    ) from problem
                raise ExperimentError(
                    "Tracker worker refused,failed or exceeded its deadline;no partial history accepted"
                ) from problem
            if overflow.is_set():
                raise ExperimentError("Tracker worker exceeded memory budget")
            if (
                not isinstance(answer, dict)
                or answer.get("file") != "history.json"
                or type(answer.get("bytes")) is not int
                or not 0 <= answer["bytes"] <= MAX_OUTPUT
            ):
                raise ExperimentError("Invalid tracker output descriptor")
            path = root / "history.json"
            if path.is_symlink():
                raise ExperimentError("Tracker output is not an owned regular file")
            with path.open("rb") as stream:
                raw = stream.read(MAX_OUTPUT + 1)
            if len(raw) != answer["bytes"] or hashlib.sha256(raw).hexdigest() != answer.get(
                "sha256"
            ):
                raise ExperimentError("Tracker output bytes changed")
            result = json.loads(raw)
            if local_before and _sqlite_files(config) != local_before:
                raise ExperimentError("MLflow source changed during history collection")
            return result, local_before
        finally:
            worker.close()
            stopped.set()
            thread.join(timeout=1)
            # SDK native cores may use another process group. Only recorded descendants
            # with the same creation time belong to this worker invocation.
            for (_pid, created), process in owned.items():
                try:
                    if (
                        process.create_time() == created
                        and process.is_running()
                        and process.status() != psutil.STATUS_ZOMBIE
                    ):
                        process.terminate()
                        try:
                            process.wait(timeout=2)
                        except psutil.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=2)
                except psutil.Error:
                    pass


class TrackerSnapshot(ExperimentSnapshot):
    def recheck(self):
        if self.config["transport"] == "sqlite_copy":
            if _sqlite_files(self.config) != self.source_files:
                raise ExperimentError("MLflow source changed;list runs again")
        elif _collect(self.config, self.access).identity != self.identity:
            raise ExperimentError("Tracker source changed;list runs again")

    def catalog(self):
        result = super().catalog()
        result["scope"] = (
            "Complete bounded completed-run query within the selected experiments/project;no sampling,training writes or scientific acceptance."
        )
        result["disclosure"] = {
            "network_read": self.config["transport"] != "sqlite_copy",
            "endpoint": self.config.get("endpoint", self.config["source"]),
            "source_store_modified": False,
            "credentials_persisted": False,
        }
        return result


def _collect(config, access):
    result, source_files = _worker(config, access)
    if (
        not isinstance(result, dict)
        or not isinstance(result.get("runs"), list)
        or not isinstance(result.get("points"), list)
        or len(result["runs"]) > MAX_RUNS
        or len(result["points"]) > MAX_POINTS
    ):
        raise ExperimentError("Tracker exceeded run/record limits or returned invalid history")
    labels = {}
    ids = {}
    for run in result["runs"]:
        raw_id = _text(run.get("id"), "Provider run ID", 512)
        if raw_id in ids:
            raise ExperimentError("Tracker returned repeated run identities")
        identity = _digest(
            {
                "provider": config["provider"],
                "source": config["source"],
                "endpoint": config.get("endpoint"),
                "id": raw_id,
            }
        )[:24]
        ids[raw_id] = identity
        labels[identity] = _text(run.get("name") or raw_id, "Run label", 1024)
    points = []
    for index, row in enumerate(result["points"]):
        if not isinstance(row, dict) or row.get("run_id") not in ids:
            raise ExperimentError("History references an unknown run")
        step, step_issue = _number(row.get("step"))
        value, value_issue = _number(row.get("value"))
        wall, _ = _number(row.get("wall_time"))
        metric = _text(row.get("metric"), "Metric", 1024)
        points.append(
            {
                "run_id": ids[row["run_id"]],
                "metric": metric,
                "step": step,
                "value": value,
                "wall_time": wall,
                "source_file": str(row["run_id"]) + "/" + metric,
                "source_record": row.get("source_record", index),
                "source_offset": None,
                "session": 0,
                "issue": ("step_" + step_issue) if step_issue else value_issue,
            }
        )
    encoded = json.dumps(result, sort_keys=True, allow_nan=False).encode()
    files = [
        *source_files,
        {
            "path": "provider-history.json",
            "bytes": len(encoded),
            "sha256": hashlib.sha256(encoded).hexdigest(),
        },
    ]
    ignored = []
    for item in result.get("ignored", []):
        if not isinstance(item, dict):
            raise ExperimentError("Invalid unsupported-record evidence")
        evidence = copy.deepcopy(item)
        if evidence.get("run_id") in ids:
            evidence["run_id"] = ids[evidence["run_id"]]
        ignored.append(evidence)
        if len(ignored) > MAX_POINTS:
            raise ExperimentError("Tracker exceeded unsupported-record limits")
    snapshot = TrackerSnapshot(
        copy.deepcopy(config),
        files,
        points,
        labels,
        ignored,
        result.get("reader", {}),
    )
    snapshot.access = access
    snapshot.source_files = source_files
    return snapshot


def tracker_snapshot(source, *, provider, metrics=None, tracker=None):
    config, access = configuration(source, provider, metrics, tracker)
    snapshot = _collect(config, access)
    snapshot.recheck()
    return snapshot
