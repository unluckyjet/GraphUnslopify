"""Explicit MLflow destinations, immutable snapshots and truthful audit acceptance."""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
import uuid
from pathlib import Path

from .audit import _validate_audit_report
from .comparison import MAX_BYTES, _verified_bytes, artifact_roots


class TrackingError(ValueError):
    """A tracking request lacks an explicit destination or usable saved evidence."""


def _json_bytes(value: dict) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False) + "\n").encode()


def _audit_consistency(report: dict) -> None:
    _validate_audit_report(report, "tracking source")
    figures = report["figures"]
    counts = {
        key: sum(f["status"] == key for f in figures) for key in ("passed", "failed", "incomplete")
    }
    status = "failed" if counts["failed"] else "incomplete" if counts["incomplete"] else "passed"
    if report["counts"] != counts or report["status"] != status:
        raise TrackingError(
            "Saved audit counts/status disagree with its figures; regenerate the audit."
        )
    if report["exit_code"] == 0 and (
        status != "passed"
        or (report["policy"]["fail_on_change"] and (report.get("comparison") or {}).get("changed"))
        or (report.get("visual_comparison") or {}).get("exit_code", 0) != 0
    ):
        raise TrackingError("Saved audit acceptance contradicts its checks/policy; regenerate it.")
    if not re.fullmatch(r"runs/[a-f0-9]{32}", report.get("run_directory", "")):
        raise TrackingError(
            "Tracking needs an owned saved audit run; regenerate with current source."
        )


def _load(source: Path) -> tuple[bytes, dict, dict | None, str]:
    if source.stat().st_size > MAX_BYTES:
        raise TrackingError("Saved report exceeds the 20 MiB tracking limit.")
    raw = source.read_bytes()
    payload = json.loads(raw)
    # Round-tripping also rejects nonfinite values before opening any destination.
    _json_bytes(payload)
    if not isinstance(payload, dict):
        raise TrackingError("Choose an audit.report.json or workflow.report.json file.")
    workflow = "workflow_id" in payload
    report = payload.get("audit") if workflow else payload
    if report is not None:
        _audit_consistency(report)
    if workflow:
        if (
            payload.get("schema_version") != 1
            or not isinstance(payload.get("workflow_id"), str)
            or payload.get("status") not in ("passed", "failed", "incomplete")
            or type(payload.get("exit_code")) is not int
            or payload["exit_code"] not in (0, 2)
            or (payload["status"] != "passed" and payload["exit_code"] == 0)
        ):
            raise TrackingError("Invalid saved workflow status/acceptance; rerun the workflow.")
        if report is None:
            if payload["exit_code"] != 2 or payload.get("audit_status") != "not_run":
                raise TrackingError("Workflow without an audit cannot be accepted.")
        elif payload.get("audit_status") != report.get("status") or (
            payload["exit_code"] == 0 and report.get("exit_code") != 0
        ):
            raise TrackingError("Workflow acceptance disagrees with its saved audit.")
    return raw, payload, report, "workflow" if workflow else "audit"


def _snapshot(source: Path, folder: Path, artifact_root) -> dict:
    raw, payload, report, kind = _load(source)
    inventory = []

    def store(name: str, data: bytes) -> None:
        target = folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        inventory.append(
            {"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        )

    store(kind + ".report.json", raw)
    skipped = set()
    if report is not None:
        if kind == "workflow":
            store("audit.report.json", _json_bytes(report))
        roots = artifact_roots(
            report,
            source.parent / "audit/audit.report.json" if kind == "workflow" else source,
            artifact_root,
        )
        for figure in report["figures"]:
            for index, item in enumerate(figure["outputs"]):
                fmt = item["format"]
                if fmt not in ("png", "svg", "pdf"):
                    skipped.add(fmt)
                    continue
                prefix = f"{report['run_directory']}/figures/{figure['id']}/"
                if not item["path"].startswith(prefix) or Path(item["path"]).suffix != "." + fmt:
                    raise TrackingError(
                        "Export does not belong to its saved figure run; regenerate the audit."
                    )
                # Read once, verify, then upload only this frozen copy. Never walk caller directories.
                data = _verified_bytes(item, roots)
                store(f"figures/{figure['id']}/export-{index:03d}.{fmt}", data)
        if report.get("comparison") is not None:
            # The machine change evidence is in the source snapshot. Unhashed HTML,
            # logs, scripts and neighbouring files are deliberately not selected.
            store("comparison.json", _json_bytes(report["comparison"]))
    manifest = {
        "schema_version": 1,
        "kind": kind,
        "source_report_sha256": hashlib.sha256(raw).hexdigest(),
        "source_status": payload["status"],
        "source_exit_code": payload["exit_code"],
        "source_accepted": payload["exit_code"] == 0,
        "audit_status": report["status"] if report else "not_run",
        "counts": report["counts"] if report else {},
        "files": list(inventory),
        "skipped_formats": sorted(skipped),
        "comparison_scope": "saved machine change evidence; interactive HTML is not uploaded",
    }
    store("tracking.manifest.json", _json_bytes(manifest))
    return {**manifest, "files": inventory}


def log_mlflow(
    report: str | Path,
    *,
    tracking_uri: str,
    experiment_id: str | None = None,
    run_id: str | None = None,
    artifact_root: str | Path | None = None,
) -> dict:
    """Log a saved audit/workflow to one explicitly chosen MLflow destination.

    An experiment ID creates/finishes an owned run; an existing running run ID
    attaches evidence without changing its lifecycle or the fluent active run.
    The returned exit_code preserves source rejection and also rejects logging
    errors. Source reports and input data are never changed or re-executed.
    """
    if not isinstance(tracking_uri, str) or not tracking_uri.strip():
        raise TrackingError(
            "Provide tracking_uri explicitly; no default service/store is selected."
        )
    if (experiment_id is None) == (run_id is None):
        raise TrackingError("Choose exactly one experiment_id (new run) or run_id (attach).")
    choice = experiment_id if experiment_id is not None else run_id
    if not isinstance(choice, str) or not choice.strip():
        raise TrackingError("Experiment/run ID must be a nonempty string chosen by the caller.")
    source = Path(report).expanduser().resolve()
    with tempfile.TemporaryDirectory(prefix="gu-tracking-") as temporary:
        folder = Path(temporary)
        snapshot = _snapshot(source, folder, artifact_root)
        try:
            from mlflow.tracking import MlflowClient
        except ImportError as problem:
            raise TrackingError(
                "Install graphunslopify[tracking] in this Python environment for MLflow logging."
            ) from problem
        receipt = {
            **snapshot,
            "status": "failed",
            "exit_code": 2,
            "run_id": run_id,
            "created_run": False,
            "artifact_path": "graphunslopify/" + uuid.uuid4().hex,
            "errors": [],
        }
        client = None
        attached = False
        try:
            client = MlflowClient(tracking_uri=tracking_uri, registry_uri=tracking_uri)
            if experiment_id is not None:
                experiment = client.get_experiment(experiment_id)
                if experiment is None or experiment.lifecycle_stage != "active":
                    raise TrackingError("Choose an existing active MLflow experiment ID.")
                run = client.create_run(experiment_id, run_name="GraphUnslopify figure audit")
                receipt.update(run_id=run.info.run_id, created_run=True)
            else:
                run = client.get_run(run_id)
                if run.info.status != "RUNNING" or run.info.lifecycle_stage != "active":
                    raise TrackingError(
                        "Attach to a running, active MLflow run; its lifecycle is caller-owned."
                    )
            destination = receipt["run_id"]
            attached = True
            client.set_tag(destination, "graphunslopify.last_logging_status", "uploading")
            for key, value in {
                "last_artifact_path": receipt["artifact_path"],
                "last_source_status": receipt["source_status"],
                "last_audit_status": receipt["audit_status"],
                "last_source_accepted": str(receipt["source_accepted"]).lower(),
                "last_report_sha256": receipt["source_report_sha256"],
            }.items():
                client.set_tag(destination, "graphunslopify." + key, value)
            for item in receipt["files"]:
                relative = Path(item["path"])
                parent = relative.parent.as_posix()
                target = receipt["artifact_path"] + ("/" + parent if parent != "." else "")
                client.log_artifact(destination, str(folder / relative), artifact_path=target)
            for key, value in receipt["counts"].items():
                client.log_metric(destination, "graphunslopify.figures_" + key, value)
            client.set_tag(destination, "graphunslopify.last_logging_status", "complete")
            if receipt["created_run"]:
                client.set_terminated(
                    destination, "FINISHED" if receipt["source_accepted"] else "FAILED"
                )
            receipt.update(status="logged", exit_code=receipt["source_exit_code"])
        except Exception as problem:  # noqa: BLE001 -- a partial upload is never acceptance
            message = (
                str(problem)
                if isinstance(problem, TrackingError)
                else (
                    f"MLflow logging failed ({type(problem).__name__}); check the explicit store, "
                    "experiment/run permissions and transport. Partial artifacts may remain under artifact_path."
                )
            )
            receipt["errors"].append(message)
            if client is not None and attached:
                try:
                    client.set_tag(
                        receipt["run_id"], "graphunslopify.last_logging_status", "failed"
                    )
                except Exception:  # noqa: BLE001 -- primary error remains actionable
                    receipt["errors"].append(
                        "Could not record logging failure in MLflow; inspect partial artifacts."
                    )
            if client is not None and receipt["run_id"] and receipt.get("created_run"):
                try:
                    client.set_terminated(receipt["run_id"], "FAILED")
                except Exception:  # noqa: BLE001 -- preserve the primary failure/receipt
                    receipt["errors"].append(
                        "Could not mark the owned MLflow run FAILED; inspect its lifecycle."
                    )
        return receipt
