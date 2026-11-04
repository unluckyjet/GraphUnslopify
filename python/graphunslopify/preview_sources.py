"""Session-only source proposals reuse editor context, ownership and cancellation fences."""

from __future__ import annotations

import base64
import copy
import hashlib
import secrets
import threading
import time

from .preview_experiments import PreviewExperiments, _context
from .source_imports import MAX_DATA, SourceImportError, import_source
from .source_parser import MAX_SOURCE


class PreviewSources(PreviewExperiments):
    def __init__(self, state):
        super().__init__(state)
        self.inference = threading.BoundedSemaphore(2)
        self.closed = False

    def close(self):
        with self.lock:
            self.closed = True
            self.plans.clear()

    def _data(self, payload):
        if payload.get("map_current_data") is not True:
            return None
        record = self.state.selected_data(payload.get("data_id"))
        if record["format"] != "csv" or record["path"].stat().st_size > MAX_DATA:
            raise SourceImportError("Map a current CSV dataset of at most20MiB")
        with record["path"].open("rb") as stream:
            raw = stream.read(MAX_DATA + 1)
        if len(raw) > MAX_DATA:
            raise SourceImportError("Mapped dataset exceeds20MiB")
        return raw

    def _analyze(self, original, data, name):
        if not self.inference.acquire(blocking=False):
            raise SourceImportError("Two source readers are active; retry after one finishes")
        try:
            return import_source(original, data=data, name=name)
        finally:
            self.inference.release()

    def review(self, payload):
        client, context = _context(payload)
        encoded = payload.get("source_base64")
        if not isinstance(encoded, str) or len(encoded) > 4 * ((MAX_SOURCE + 2) // 3):
            raise SourceImportError("Choose Python source of at most256KiB")
        try:
            original = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError) as problem:
            raise SourceImportError("Invalid source bytes") from problem
        name = payload.get("source_name", "original.py")
        proposal = self._analyze(original, self._data(payload), name)
        identity = None
        if proposal.report["convertible"]:
            identity = secrets.token_urlsafe(24)
            with self.lock:
                self._expire()
                if self.closed or len(self.plans) >= 8:
                    raise SourceImportError("Source session closed or too many pending proposals")
                self.plans[identity] = {
                    "client": client,
                    "context": context,
                    "created": time.monotonic(),
                    "original": original,
                    "name": name,
                    "map_current_data": payload.get("map_current_data") is True,
                    "snapshot": proposal.report["snapshot"],
                }
        return {
            "id": identity,
            "spec": proposal.spec,
            "report": proposal.report,
            "applied": False,
            "verified": False,
        }

    def accept(self, payload):
        client, context = _context(payload)
        with self.state.lock:
            if self.state.generations.get(client, -1) > payload["generation"]:
                raise SourceImportError("A newer editor revision superseded this source import")
        with self.lock:
            self._expire()
            plan = self.plans.get(payload.get("id"))
            if (
                self.closed
                or plan is None
                or plan["client"] != client
                or plan["context"] != context
            ):
                raise SourceImportError("Source proposal no longer matches this editor context")
            self.plans.pop(payload["id"])
        if payload.get("reviewed") is not True:
            raise SourceImportError(
                "Review source, mapped data and proposed figure before applying"
            )
        data = self._data({**payload, "map_current_data": plan["map_current_data"]})
        proposal = self._analyze(plan["original"], data, plan["name"])
        if proposal.report["snapshot"] != plan["snapshot"]:
            raise SourceImportError("Mapped source/data changed; review the import again")
        if proposal.report["requires_partial_review"] and payload.get("accept_partial") is not True:
            raise SourceImportError(
                "Explicitly review unsupported behavior before accepting partial extraction"
            )
        if not proposal.report["convertible"]:
            raise SourceImportError("Source is no longer convertible")
        with self.state.lock:
            if self.state.generations.get(client, -1) > payload["generation"]:
                raise SourceImportError("A newer editor revision superseded this source import")
        with self.lock:
            if self.closed:
                raise SourceImportError("Source session closed")
        info = self.state.upload("imported-source.csv", proposal.csv_bytes)
        report = copy.deepcopy(proposal.report)
        report.update(
            applied=True,
            verified=False,
            materialized_csv_sha256=hashlib.sha256(proposal.csv_bytes).hexdigest(),
        )
        with self.state.lock:
            record = self.state.uploads[info["id"]]
            record["source_import"] = report
            original_path = record["path"].parent / "original-source.py"
            original_path.write_bytes(proposal.original)
            record["source_original"] = original_path
        return {"data": info, "spec": proposal.spec, "report": report, "verified": False}
