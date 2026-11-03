"""Actual SQLite WAL/source-race boundaries using owned MLflow fixtures."""

import hashlib
import sqlite3

import pytest
from test_tracker_imports import store as store  # noqa: PLC0414

from graphunslopify import experiment_imports as imports
from graphunslopify import tracker_imports as trackers


def inventory(source):
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in source.parent.iterdir()
        if p.name.startswith(source.name)
    }


def test_actual_mlflow_wal_snapshot_preserves_original_database_wal_and_shm(store):
    source, client, experiment, ids = store
    client._tracking_client.store.engine.dispose()
    with sqlite3.connect(source) as lease:
        assert lease.execute("pragma journal_mode=WAL").fetchone()[0] == "wal"
        client.log_metric(ids[0], "loss", 8, step=3, timestamp=3000)
        before = inventory(source)
        assert source.name + "-wal" in before and source.name + "-shm" in before
        catalog = imports.experiment_runs(
            source, provider="mlflow", tracker={"experiment_ids": [experiment]}
        )
        losses = [m for r in catalog["runs"] for m in r["metrics"] if m["name"] == "loss"]
        assert sum(m["valid_records"] for m in losses) == 7
        assert inventory(source) == before


def test_source_write_between_copy_and_sdk_read_is_refused(store, monkeypatch):
    source, client, experiment, ids = store
    original = trackers._sqlite_files

    def changed(config, destination=None):
        result = original(config, destination)
        if destination is not None:
            client.log_metric(ids[0], "loss", 8, step=3, timestamp=3000)
        return result

    monkeypatch.setattr(trackers, "_sqlite_files", changed)
    with pytest.raises(imports.ExperimentError, match="source changed"):
        imports.experiment_runs(source, provider="mlflow", tracker={"experiment_ids": [experiment]})


def test_dangling_wal_symlink_is_refused_instead_of_omitted(store):
    source, _, experiment, _ = store
    source.with_name(source.name + "-wal").symlink_to(source.parent / "absent-target")
    with pytest.raises((imports.ExperimentError, FileNotFoundError, OSError)):
        imports.experiment_runs(source, provider="mlflow", tracker={"experiment_ids": [experiment]})
