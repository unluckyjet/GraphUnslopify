"""Actual SDK/store,real HTTP and actual SDK iterator with controlled protobuf IPC."""

import hashlib
import io
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from graphunslopify import experiment_imports as imports
from graphunslopify import tracker_imports as trackers
from graphunslopify import tracker_worker as worker


@pytest.fixture
def store(tmp_path):
    mlflow = pytest.importorskip("mlflow")
    database = tmp_path / "source.sqlite"
    client = mlflow.MlflowClient(tracking_uri="sqlite:///" + str(database))
    experiment = client.create_experiment(
        "history test", artifact_location=str(tmp_path / "artifacts")
    )
    ids = []
    for i in range(2):
        run = client.create_run(experiment, tags={"mlflow.runName": "same display name"})
        ids.append(run.info.run_id)
        for step, stamp, value in [(0, 900, 4 + i), (0, 1000, 3 + i), (2, 2000, 1 + i)]:
            client.log_metric(run.info.run_id, "loss", value, step=step, timestamp=stamp)
        client.log_metric(run.info.run_id, "accuracy", 0.5 + i / 10, step=1, timestamp=1500)
        client.set_terminated(run.info.run_id)
    return database, client, experiment, ids


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_actual_mlflow_copy_sdk_history_and_no_source_mutation(store):
    source, _, experiment, _ids = store
    before = digest(source)
    settings = {"experiment_ids": [experiment]}
    catalog = imports.experiment_runs(source, provider="mlflow", tracker=settings)
    assert len(catalog["runs"]) == 2 and len({r["id"] for r in catalog["runs"]}) == 2
    assert {r["name"] for r in catalog["runs"]} == {"same display name"}
    assert (
        not catalog["disclosure"]["network_read"]
        and catalog["disclosure"]["source_store_modified"] is False
    )
    proposal = imports.experiment_comparison(
        source,
        provider="mlflow",
        tracker=settings,
        runs=[r["id"] for r in catalog["runs"]],
        metric="loss",
        kind="scatter",
        expected_snapshot=catalog["snapshot"],
    )
    import csv

    rows = list(csv.DictReader(io.StringIO(proposal.csv_bytes.decode())))
    assert len(rows) == 6 and sorted(float(r["value"]) for r in rows) == [1, 2, 3, 4, 4, 5]
    assert proposal.report["duplicate_steps"] == 2 and proposal.report["excluded_records"] == 0
    assert {r["wall_time"] for r in rows} == {"900", "1000", "2000"}
    assert (
        digest(source) == before
        and not proposal.report["verified"]
        and not proposal.report["new_execution"]
    )
    assert len({r["source_file"].split("/")[0] for r in rows}) == 2


def test_changed_real_mlflow_store_refuses_old_catalog_and_never_initializes_missing(
    tmp_path, store
):
    source, client, experiment, ids = store
    catalog = imports.experiment_runs(
        source, provider="mlflow", tracker={"experiment_ids": [experiment]}
    )
    client.log_metric(ids[0], "loss", 8, step=3, timestamp=3000)
    with pytest.raises(imports.ExperimentError, match="changed"):
        imports.experiment_comparison(
            source,
            provider="mlflow",
            tracker={"experiment_ids": [experiment]},
            runs=[r["id"] for r in catalog["runs"]],
            metric="loss",
            kind="scatter",
            expected_snapshot=catalog["snapshot"],
        )
    missing = tmp_path / "not-created.db"
    with pytest.raises(FileNotFoundError):
        imports.experiment_runs(missing, provider="mlflow", tracker={"experiment_ids": ["0"]})
    assert not missing.exists()


@pytest.mark.parametrize(
    "settings",
    [
        {
            "source": "https://mlflow.example",
            "provider": "mlflow",
            "tracker": {"experiment_ids": ["1"]},
        },
        {
            "source": "http://remote.example",
            "provider": "mlflow",
            "tracker": {"experiment_ids": ["1"], "allow_remote": True},
        },
        {
            "source": "https://user:secret@mlflow.example",
            "provider": "mlflow",
            "tracker": {"experiment_ids": ["1"], "allow_remote": True},
        },
        {"source": "entity/project", "provider": "wandb", "tracker": {"allow_remote": True}},
        {
            "source": "entity/project",
            "provider": "wandb",
            "tracker": {"api_key": "explicit-secret"},
        },
        {
            "source": "../other/project",
            "provider": "wandb",
            "tracker": {"api_key": "explicit-secret", "allow_remote": True},
        },
    ],
)
def test_endpoint_account_and_consent_refuse_before_worker(settings, monkeypatch):
    monkeypatch.setattr(
        trackers, "_worker", lambda *a: pytest.fail("Refusal must precede SDK construction")
    )
    with pytest.raises((imports.ExperimentError, FileNotFoundError)):
        imports.experiment_runs(**settings)


@pytest.fixture
def http_store():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.server.calls.append(
                {
                    "path": self.path,
                    "params": body,
                    "auth_correct": self.headers.get("Authorization")
                    == "Bearer " + self.server.secret,
                }
            )
            node = {
                "info": {"run_id": "real-protocol-id", "status": self.server.status},
                "data": {
                    "tags": [{"key": "mlflow.runName", "value": "HTTP run"}],
                    "metrics": [{"key": "loss", "value": 1}],
                },
            }
            reply = {"runs": [node]}
            if self.server.repeat:
                reply["next_page_token"] = "repeated"
            self.reply(reply)

        def do_GET(self):
            from urllib.parse import parse_qs, urlsplit

            query = parse_qs(urlsplit(self.path).query)
            self.server.calls.append(
                {
                    "path": urlsplit(self.path).path,
                    "params": query,
                    "auth_correct": self.headers.get("Authorization")
                    == "Bearer " + self.server.secret,
                }
            )
            self.reply(
                {
                    "metrics": [
                        {"key": "loss", "step": 0, "timestamp": 1000, "value": 3},
                        {"key": "loss", "step": 1, "timestamp": 2000, "value": 1},
                    ]
                }
            )

        def reply(self, value):
            data = json.dumps(value).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        server.secret = "private-auth-canary-do-not-persist"
        server.calls = []
        server.repeat = False
        server.status = "FINISHED"
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            thread.join(5)


def test_real_http_protocol_pages_auth_and_no_credentials_in_evidence(http_store):
    url = f"http://127.0.0.1:{http_store.server_port}"
    catalog = imports.experiment_runs(
        url,
        provider="mlflow",
        tracker={"experiment_ids": ["1"], "allow_remote": True, "api_key": http_store.secret},
    )
    assert catalog["runs"][0]["metrics"][0]["valid_records"] == 2
    assert catalog["disclosure"]["network_read"] and http_store.secret not in json.dumps(catalog)
    assert all(c["auth_correct"] for c in http_store.calls)
    assert {c["path"] for c in http_store.calls} == {
        "/api/2.0/mlflow/runs/search",
        "/api/2.0/mlflow/metrics/get-history",
    }
    histories = [c for c in http_store.calls if c["path"].endswith("get-history")]
    assert all(c["params"]["max_results"] == ["1000"] for c in histories)


def test_repeated_remote_cursor_refuses_instead_of_complete_prefix(http_store):
    http_store.repeat = True
    with pytest.raises(imports.ExperimentError):
        imports.experiment_runs(
            f"http://127.0.0.1:{http_store.server_port}",
            provider="mlflow",
            tracker={"experiment_ids": ["1"], "allow_remote": True, "api_key": http_store.secret},
        )
    assert len(http_store.calls) <= 2


def test_unknown_run_status_is_not_reported_as_completed(http_store):
    http_store.status = "UNRECOGNIZED"
    with pytest.raises(imports.ExperimentError):
        imports.experiment_runs(
            f"http://127.0.0.1:{http_store.server_port}",
            provider="mlflow",
            tracker={"experiment_ids": ["1"], "allow_remote": True},
        )


def test_closing_preview_discards_pending_tracker_credentials():
    from graphunslopify.preview_experiments import PreviewExperiments

    state = PreviewExperiments(SimpleNamespace())
    state.plans["synthetic"] = {"options": {"tracker": {"api_key": "synthetic-key"}}}
    state.close()
    assert state.plans == {}


def test_actual_worker_memory_bound_refuses_owned_sdk(store, monkeypatch):
    source, _, experiment, _ = store
    monkeypatch.setattr(trackers, "MAX_RSS", 1)
    with pytest.raises(imports.ExperimentError, match="memory budget"):
        imports.experiment_runs(source, provider="mlflow", tracker={"experiment_ids": [experiment]})


def test_actual_wandb_historyscan_with_controlled_ipc_not_cloud(monkeypatch, tmp_path):
    import os

    for key in [
        "WANDB_DIR",
        "WANDB_CACHE_DIR",
        "WANDB_CONFIG_DIR",
        "WANDB_DATA_DIR",
        "WANDB_MODE",
        "WANDB_ERROR_REPORTING",
        "WANDB_SILENT",
    ]:
        monkeypatch.setenv(key, os.environ.get(key, ""))
    wandb = pytest.importorskip("wandb")
    from wandb.apis.public.history import HistoryScan
    from wandb.proto import wandb_api_pb2 as pb

    rows = [
        {"_step": 0, "loss": 3.0},
        {"_step": 1, "accuracy": 0.5},
        {"_step": 4, "loss": 2.0},
        {"_step": 4, "loss": 1.9},
        {"_step": 4, "accuracy": 0.6},
        {"_step": 7, "loss": 1.0},
    ]
    events = []

    class IPC:
        def send_api_request(self, request):
            response = pb.ApiResponse()
            body = request.read_run_history_request
            if body.HasField("scan_run_history_init"):
                assert (
                    not body.scan_run_history_init.use_cache and not body.scan_run_history_init.keys
                )
                response.read_run_history_response.scan_run_history_init.request_id = 17
                return response
            page = body.scan_run_history
            for record in rows:
                if page.min_step <= record["_step"] < page.max_step:
                    result = response.read_run_history_response.run_history.history_rows.add()
                    for key, value in record.items():
                        result.history_items.add(key=key, value_json=json.dumps(value))
            return response

        def finalize(self, *args):
            events.append("iterator-cleanup")

    class Run:
        id = "run-one"
        name = "Model"
        state = "finished"

        def scan_history(self, **options):
            assert options == {"keys": None, "page_size": 100, "use_cache": False}
            return HistoryScan(
                SimpleNamespace(entity="fixture", project="histories", id=self.id),
                service_api=IPC(),
                min_step=0,
                max_step=8,
                **options,
            )

    class API:
        def __init__(self, **options):
            assert options["api_key"] == "explicit-test-key" and options["timeout"] == 5

        def runs(self, source, **options):
            assert source == "fixture/histories"
            return [Run()]

    monkeypatch.setattr(wandb, "Api", API)
    monkeypatch.setattr(
        wandb,
        "setup",
        lambda **kw: SimpleNamespace(ensure_service=lambda: SimpleNamespace(owns_service=True)),
    )
    monkeypatch.setattr(wandb, "teardown", lambda: events.append("owned-teardown"))
    monkeypatch.chdir(tmp_path)
    result = worker._wandb(
        {
            "endpoint": "http://127.0.0.1:9",
            "source": "fixture/histories",
            "metrics": ["loss", "accuracy"],
        },
        {"api_key": "explicit-test-key"},
    )
    assert (
        len(result["points"]) == 12
        and len([p for p in result["points"] if p["value"] is not None]) == 6
    )
    loss = [
        p["value"] for p in result["points"] if p["metric"] == "loss" and p["value"] is not None
    ]
    assert loss == [3, 2, 1.9, 1] and "owned-teardown" in events and "iterator-cleanup" in events
    assert result["reader"]["sampling"] == "none" and not result["reader"]["use_cache"]
    monkeypatch.setattr(trackers, "_worker", lambda config, access: (result, []))
    settings = {
        "endpoint": "http://127.0.0.1:9",
        "api_key": "explicit-test-key",
        "allow_remote": True,
    }
    catalog = imports.experiment_runs(
        "fixture/histories", provider="wandb", metrics=["loss", "accuracy"], tracker=settings
    )
    assert "explicit-test-key" not in json.dumps(catalog)
    proposal = imports.experiment_comparison(
        "fixture/histories",
        provider="wandb",
        metrics=["loss", "accuracy"],
        tracker=settings,
        runs=[catalog["runs"][0]["id"]],
        metric="loss",
        kind="scatter",
        expected_snapshot=catalog["snapshot"],
    )
    assert (
        proposal.report["records"] == 4
        and proposal.report["excluded_records"] == 2
        and proposal.report["duplicate_steps"] == 1
    )
    native = imports.render_experiment_comparison(
        proposal, tmp_path / "controlled-sdk-native", accept_exclusions=True
    )
    assert native["exit_code"] == 0 and native["scientific_status"] == "passed"

    rows[:] = [{"_step": 1, f"metric-{i}": i} for i in range(129)]
    with pytest.raises(worker.Refusal, match="128 metric"):
        worker._wandb(
            {"endpoint": "http://127.0.0.1:9", "source": "fixture/histories", "metrics": None},
            {"api_key": "explicit-test-key"},
        )


def test_actual_worker_startup_deadline_refuses_instead_of_unbounded_fallback(store, monkeypatch):
    source, _, experiment, _ = store
    original = trackers.JsonWorker

    def short_deadline(*args, **kwargs):
        process = original(*args, **kwargs)
        request = process.request
        process.request = lambda payload, timeout: request(payload, 0.00001)
        return process

    monkeypatch.setattr(trackers, "JsonWorker", short_deadline)
    with pytest.raises(imports.ExperimentError, match="deadline"):
        imports.experiment_runs(source, provider="mlflow", tracker={"experiment_ids": [experiment]})


def test_actual_tracker_comparison_uses_strict_native_renderer(store, tmp_path):
    source, _, experiment, _ = store
    before = digest(source)
    settings = {"experiment_ids": [experiment]}
    catalog = imports.experiment_runs(source, provider="mlflow", tracker=settings)
    comparison = imports.experiment_comparison(
        source,
        provider="mlflow",
        tracker=settings,
        runs=[r["id"] for r in catalog["runs"]],
        metric="loss",
        kind="scatter",
        expected_snapshot=catalog["snapshot"],
    )
    rendered = imports.render_experiment_comparison(comparison, tmp_path / "native-output")
    assert rendered["exit_code"] == 0 and rendered["scientific_status"] == "passed"
    assert rendered["import"]["records"] == 6 and rendered["import"]["duplicate_steps"] == 2
    assert (tmp_path / "native-output/experiment-comparison.png").is_file() and digest(
        source
    ) == before
