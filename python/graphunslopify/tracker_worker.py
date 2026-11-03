"""Private SDK worker. Only its owned result file crosses the bounded transport."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import math
import os
import sqlite3
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .worker_process import MAX_REQUEST, PROTOCOL

MAX_RUNS = 256
MAX_RECORDS = 100_000
MAX_POINTS = 200_000
MAX_OUTPUT = 64 * 1024 * 1024


class Refusal(ValueError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise Refusal("Tracker redirects are refused;configure the final authorized endpoint")


class Quiet(io.TextIOBase):
    def write(self, text):
        return len(text)


def _safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    return value


def _point(points, run_id, metric, step, value, wall_time, index):
    if len(points) >= MAX_POINTS:
        raise Refusal("Tracker exceeds200000 metric points")
    points.append(
        {
            "run_id": run_id,
            "metric": metric,
            "step": _safe(step),
            "value": _safe(value),
            "wall_time": _safe(wall_time),
            "source_record": index,
        }
    )


def _paged(fetch):
    token = None
    seen = set()
    for _ in range(512):
        values, next_token = fetch(token)
        yield values
        if not next_token:
            return
        if not isinstance(next_token, str) or len(next_token) > 8192 or next_token in seen:
            raise Refusal("Tracker pagination repeated or returned invalid tokens")
        seen.add(next_token)
        token = next_token
    raise Refusal("Tracker exceeds the pagination bound")


def _http(config, access):
    opener = build_opener(NoRedirect())

    def call(route, params=None, body=None):
        url = config["source"] + "/api/2.0/mlflow/" + route
        if params:
            url += "?" + urlencode({k: v for k, v in params.items() if v is not None})
        headers = {"Accept": "application/json"}
        if access.get("api_key"):
            headers["Authorization"] = "Bearer " + access["api_key"]
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        request = Request(
            url, data=data, headers=headers, method="POST" if body is not None else "GET"
        )
        try:
            with opener.open(request, timeout=10) as response:
                raw = response.read(8 * 1024 * 1024 + 1)
        except HTTPError as error:
            raise Refusal("Tracker HTTP read failed with status " + str(error.code)) from None
        if len(raw) > 8 * 1024 * 1024:
            raise Refusal("Tracker response exceeds8MiB")
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise Refusal("Tracker response must be an object")
        if result.get("error_code"):
            raise Refusal("Tracker rejected the read request")
        return result

    raw_runs = []

    def runs_page(token):
        response = call(
            "runs/search",
            body={
                "experiment_ids": config["experiment_ids"],
                "filter": "attributes.status != 'RUNNING'",
                "order_by": ["attributes.run_id ASC"],
                "max_results": 100,
                **({"page_token": token} if token else {}),
            },
        )
        values = response.get("runs", [])
        if not isinstance(values, list) or len(values) > 100:
            raise Refusal("Tracker ignored the run page bound")
        return values, response.get("next_page_token")

    for page in _paged(runs_page):
        raw_runs.extend(page)
        if len(raw_runs) > MAX_RUNS:
            raise Refusal("Choose a source with at most256 runs")
    runs = []
    points = []
    ignored = []
    total = 0
    for run in sorted(raw_runs, key=lambda r: r["info"]["run_id"]):
        info = run["info"]
        identity = info["run_id"]
        if info.get("status") in {"RUNNING", "SCHEDULED"}:
            ignored.append(
                {
                    "run_id": identity,
                    "metric": "",
                    "reason": "Active run outside completed-run scope",
                }
            )
            continue
        if info.get("status") not in {"FINISHED", "FAILED", "KILLED"}:
            raise Refusal("MLflow returned an unsupported run status")
        data = run.get("data", {})
        tags = {t["key"]: t["value"] for t in data.get("tags", [])}
        runs.append({"id": identity, "name": tags.get("mlflow.runName", identity)})
        metrics = config["metrics"] or sorted({m["key"] for m in data.get("metrics", [])})
        if len(metrics) > 128:
            raise Refusal("Choose at most128 metrics")
        for metric in metrics:

            def history_page(token, identity=identity, metric=metric):
                response = call(
                    "metrics/get-history",
                    params={
                        "run_id": identity,
                        "metric_key": metric,
                        "max_results": 1000,
                        "page_token": token,
                    },
                )
                values = response.get("metrics", [])
                if not isinstance(values, list) or len(values) > 1000:
                    raise Refusal("Tracker ignored the history page bound")
                return values, response.get("next_page_token")

            index = 0
            for page in _paged(history_page):
                for row in page:
                    total += 1
                    if total > MAX_RECORDS:
                        raise Refusal("Tracker exceeds100000 history records")
                    if row.get("key", metric) != metric:
                        raise Refusal("Tracker returned a different metric")
                    _point(
                        points,
                        identity,
                        metric,
                        row.get("step"),
                        row.get("value"),
                        row.get("timestamp"),
                        index,
                    )
                    index += 1
    return {
        "runs": runs,
        "points": points,
        "ignored": ignored,
        "reader": {
            "name": "MLflow REST paginated read",
            "sampling": "none",
            "page_records": 1000,
            "timestamp_unit": "milliseconds",
        },
    }


def _mlflow_copy(config):
    root = Path.cwd()
    database = root / "source.sqlite"
    if database.is_symlink() or not database.is_file():
        raise Refusal("Missing owned SQLite snapshot")
    with sqlite3.connect(database) as check:
        if check.execute("pragma quick_check").fetchone()[0] != "ok":
            raise Refusal("Owned SQLite snapshot failed integrity")
        tables = {
            row[0] for row in check.execute("select name from sqlite_master where type='table'")
        }
        if not {"runs", "metrics", "experiments"} <= tables:
            raise Refusal("Snapshot is not an initialized MLflow tracking store")
    import inspect

    import mlflow
    from mlflow import MlflowClient

    client = MlflowClient(tracking_uri="sqlite:///" + str(database))
    store = client._tracking_client.store
    if not {"max_results", "page_token"} <= set(
        inspect.signature(store.get_metric_history).parameters
    ):
        raise Refusal("This MLflow SDK lacks bounded store history paging")
    all_runs = []

    def runs_page(token):
        page = client.search_runs(
            config["experiment_ids"],
            filter_string="attributes.status != 'RUNNING'",
            order_by=["attributes.run_id ASC"],
            max_results=100,
            page_token=token,
        )
        return page, page.token

    for page in _paged(runs_page):
        all_runs.extend(page)
        if len(all_runs) > MAX_RUNS:
            raise Refusal("Choose at most256 runs")
    runs = []
    points = []
    ignored = []
    total = 0
    for run in sorted(all_runs, key=lambda r: r.info.run_id):
        identity = run.info.run_id
        if run.info.status in {"RUNNING", "SCHEDULED"}:
            ignored.append(
                {
                    "run_id": identity,
                    "metric": "",
                    "reason": "Active run outside completed-run scope",
                }
            )
            continue
        if run.info.status not in {"FINISHED", "FAILED", "KILLED"}:
            raise Refusal("MLflow returned an unsupported run status")
        runs.append({"id": identity, "name": run.data.tags.get("mlflow.runName", identity)})
        metrics = config["metrics"] or sorted(run.data.metrics)
        if len(metrics) > 128:
            raise Refusal("Choose at most128 metrics")
        for metric in metrics:

            def history_page(token, identity=identity, metric=metric):
                page = store.get_metric_history(
                    identity, metric, max_results=1000, page_token=token
                )
                if len(page) > 1000:
                    raise Refusal("MLflow store ignored its page bound")
                return page, page.token

            index = 0
            for page in _paged(history_page):
                for row in page:
                    total += 1
                    if total > MAX_RECORDS:
                        raise Refusal("MLflow exceeds100000 history records")
                    _point(points, identity, metric, row.step, row.value, row.timestamp, index)
                    index += 1
    return {
        "runs": runs,
        "points": points,
        "ignored": ignored,
        "reader": {
            "name": "MLflow owned SQLite copy/private store paging",
            "mlflow": mlflow.__version__,
            "sampling": "none",
            "page_records": 1000,
            "timestamp_unit": "milliseconds",
        },
    }


def _wandb(config, access):
    import wandb

    if not access.get("api_key"):
        raise Refusal("Explicit W&B key is required;SDK login prompts are disabled")
    root = Path.cwd()
    for name, folder in [
        ("WANDB_DIR", "runs"),
        ("WANDB_CACHE_DIR", "cache"),
        ("WANDB_CONFIG_DIR", "config"),
        ("WANDB_DATA_DIR", "data"),
    ]:
        path = root / folder
        path.mkdir(exist_ok=True)
        os.environ[name] = str(path)
    os.environ.update(WANDB_SILENT="true", WANDB_ERROR_REPORTING="false", WANDB_MODE="online")
    setup = wandb.setup(
        settings=wandb.Settings(mode="online", base_url=config["endpoint"], root_dir=str(root))
    )
    service = setup.ensure_service()
    if not service.owns_service:
        raise Refusal("Tracker worker must own its native service")
    try:
        api = wandb.Api(
            overrides={"base_url": config["endpoint"]}, timeout=5, api_key=access["api_key"]
        )
        collected = []
        for run in api.runs(
            config["source"],
            filters={"state": {"$nin": ["running", "pending"]}},
            order="+created_at",
            per_page=25,
            include_sweeps=False,
            lazy=True,
        ):
            collected.append(run)
            if len(collected) > MAX_RUNS:
                raise Refusal("Choose a W&B project with at most256 runs")
        runs = []
        points = []
        ignored = []
        total = 0
        for run in sorted(collected, key=lambda r: r.id):
            if run.state in {"running", "pending"}:
                ignored.append(
                    {
                        "run_id": run.id,
                        "metric": "",
                        "reason": "Active run outside completed-run scope",
                    }
                )
                continue
            if run.state not in {
                "finished",
                "failed",
                "crashed",
                "killed",
                "preempted",
                "canceled",
                "cancelled",
            }:
                raise Refusal("W&B returned an unsupported run state")
            runs.append({"id": run.id, "name": run.name or run.id})
            run_metrics = set()
            for index, row in enumerate(
                run.scan_history(keys=None, page_size=100, use_cache=False)
            ):
                total += 1
                if total > MAX_RECORDS:
                    raise Refusal("W&B exceeds100000 unsampled history records")
                if not isinstance(row, dict):
                    raise Refusal("W&B history record must be an object")
                metrics = config["metrics"] or sorted(key for key in row if not key.startswith("_"))
                run_metrics.update(metrics)
                if len(run_metrics) > 128:
                    raise Refusal("Choose at most128 metric names")
                for metric in metrics:
                    # Absent metrics are explicit missing records;never inner-join keys.
                    value = row.get(metric)
                    if value is not None and not isinstance(value, (int, float, str, bool)):
                        ignored.append(
                            {
                                "run_id": run.id,
                                "metric": metric,
                                "source_record": index,
                                "reason": "Unsupported non-scalar history value",
                            }
                        )
                        continue
                    _point(
                        points,
                        run.id,
                        metric,
                        row.get("_step"),
                        value,
                        row.get("_timestamp"),
                        index,
                    )
                    if len(ignored) > MAX_POINTS:
                        raise Refusal("Too many unsupported W&B records")
        return {
            "runs": runs,
            "points": points,
            "ignored": ignored,
            "reader": {
                "name": "W&B unsampled HistoryScan",
                "wandb": wandb.__version__,
                "sampling": "none",
                "page_step_window": 100,
                "use_cache": False,
                "timestamp_unit": "seconds",
            },
        }
    finally:
        wandb.teardown()


def main():
    # A fresh worker never discovers an inherited account/service configuration.
    for name in list(os.environ):
        if name.startswith(("WANDB_", "_WANDB_", "MLFLOW_")):
            os.environ.pop(name, None)
    print(
        json.dumps(
            {
                "protocol": PROTOCOL,
                "kind": "tracker",
                "pid": os.getpid(),
                "ready": True,
                "adapter_version": 1,
            }
        ),
        flush=True,
    )
    raw = sys.stdin.buffer.readline(MAX_REQUEST + 1)
    if len(raw) > MAX_REQUEST or not raw.endswith(b"\n"):
        return 2
    request = json.loads(raw)
    identity = request.get("id")
    if request.get("protocol") != PROTOCOL:
        return 2
    payload = request["payload"]
    config = payload["config"]
    access = payload["access"]
    try:
        with contextlib.redirect_stdout(Quiet()):
            if config["provider"] == "wandb":
                result = _wandb(config, access)
            elif config["transport"] == "sqlite_copy":
                result = _mlflow_copy(config)
            else:
                result = _http(config, access)
        # Incremental encoding bounds bytes before a potentially large final allocation.
        path = Path.cwd() / "history.json"
        size = 0
        digest = hashlib.sha256()
        with path.open("xb") as stream:
            for chunk in json.JSONEncoder(allow_nan=False, separators=(",", ":")).iterencode(
                result
            ):
                encoded = chunk.encode()
                size += len(encoded)
                if size > MAX_OUTPUT:
                    raise Refusal("Normalized tracker history exceeds64MiB")
                stream.write(encoded)
                digest.update(encoded)
        reply = {
            "protocol": PROTOCOL,
            "id": identity,
            "ok": True,
            "result": {"file": path.name, "bytes": size, "sha256": digest.hexdigest()},
            "retire": True,
        }
    except ImportError:
        reply = {
            "protocol": PROTOCOL,
            "id": identity,
            "ok": False,
            "error": "Install graphunslopify[experiments] for this tracker SDK",
            "retire": True,
        }
    except Refusal as problem:
        reply = {
            "protocol": PROTOCOL,
            "id": identity,
            "ok": False,
            "error": str(problem),
            "retire": True,
        }
    except Exception as problem:  # noqa: BLE001 -- SDK errors cross a credential-redacted process boundary
        # SDK exception text can contain credentials/response bodies. Return its type only.
        reply = {
            "protocol": PROTOCOL,
            "id": identity,
            "ok": False,
            "error": "Tracker SDK/transport rejected the query (" + type(problem).__name__ + ")",
            "retire": True,
        }
    print(json.dumps(reply, allow_nan=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
