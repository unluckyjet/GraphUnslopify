"""Reviewed local-history proposals;source and current editor context own acceptance."""

from __future__ import annotations

import copy
import hashlib
import json
import secrets
import threading
import time

from .experiment_imports import ExperimentError, experiment_comparison, experiment_runs


def _context(payload):
    client, generation = payload.get("client"), payload.get("generation")
    if (
        not isinstance(client, str)
        or not 1 <= len(client) <= 128
        or type(generation) is not int
        or generation < 0
    ):
        raise ExperimentError("Invalid editor context for experiment import")
    value = {
        key: payload.get(key) for key in ("client", "generation", "data_id", "palette_id", "spec")
    }
    if not isinstance(value["spec"], dict):
        raise ExperimentError("An experiment proposal requires current figure intent")
    encoded = json.dumps(value, sort_keys=True, allow_nan=False).encode()
    if len(encoded) > 1024 * 1024:
        raise ExperimentError("Current figure context is too large")
    return client, hashlib.sha256(encoded).hexdigest()


def _options(payload):
    source = payload.get("source")
    if not isinstance(source, str):
        raise ExperimentError("Choose a local result folder")
    return source, {
        "provider": payload.get("provider", "csv"),
        "step_field": payload.get("step_field", "step"),
        "metrics": payload.get("metrics"),
    }


class PreviewExperiments:
    def __init__(self, state):
        self.state = state
        self.plans = {}
        self.lock = threading.Lock()

    def _expire(self):
        now = time.monotonic()
        self.plans = {key: plan for key, plan in self.plans.items() if now - plan["created"] < 600}

    def catalog(self, payload):
        source, options = _options(payload)
        return experiment_runs(source, **options)

    def review(self, payload):
        client, context = _context(payload)
        if payload.get("data_id"):
            self.state.selected_data(payload["data_id"])
        source, options = _options(payload)
        choice = {
            "runs": payload.get("runs"),
            "metric": payload.get("metric"),
            "kind": payload.get("kind", "line"),
            "expected_snapshot": payload.get("snapshot"),
        }
        proposal = experiment_comparison(source, **options, **choice)
        identity = secrets.token_urlsafe(24)
        with self.lock:
            self._expire()
            if len(self.plans) >= 8:
                raise ExperimentError("Too many pending experiment imports;cancel or finish one")
            self.plans[identity] = {
                "client": client,
                "context": context,
                "source": source,
                "options": options,
                "choice": copy.deepcopy(choice),
                "created": time.monotonic(),
            }
        return {
            "id": identity,
            "spec": proposal.spec,
            "report": proposal.report,
            "applied": False,
            "verified": False,
            "notice": "Review source,selected runs,raw-value mapping and exclusions. Apply explicitly to create and check a new comparison.",
        }

    def cancel(self, payload):
        client, _ = _context(payload)
        with self.lock:
            plan = self.plans.get(payload.get("id"))
            if plan and plan["client"] == client:
                self.plans.pop(payload["id"])
        return {"cancelled": True}

    def accept(self, payload):
        client, context = _context(payload)
        with self.state.lock:
            if self.state.generations.get(client, -1) > payload["generation"]:
                raise ExperimentError("A newer editor revision superseded this experiment proposal")
        with self.lock:
            self._expire()
            plan = self.plans.get(payload.get("id"))
            if plan is None or plan["client"] != client or plan["context"] != context:
                raise ExperimentError("Experiment proposal no longer matches this editor context")
            self.plans.pop(payload["id"])
        if payload.get("reviewed") is not True:
            raise ExperimentError("Review the proposed experiment comparison before applying")
        proposal = experiment_comparison(plan["source"], **plan["options"], **plan["choice"])
        if proposal.report["excluded_records"] and payload.get("accept_exclusions") is not True:
            raise ExperimentError(
                "Explicitly review the recorded missing/nonfinite exclusions before applying"
            )
        if payload.get("data_id"):
            self.state.selected_data(payload["data_id"])
        data = self.state.upload("experiment-history.csv", proposal.csv_bytes)
        report = copy.deepcopy(proposal.report)
        report["applied"] = True
        report["verified"] = False
        report["materialized_csv_sha256"] = hashlib.sha256(proposal.csv_bytes).hexdigest()
        with self.state.lock:
            self.state.uploads[data["id"]]["experiment_import"] = report
        return {
            "data": data,
            "spec": proposal.spec,
            "report": report,
            "verified": False,
            "notice": "Imported selected records;strict native rendering is still required.",
        }
