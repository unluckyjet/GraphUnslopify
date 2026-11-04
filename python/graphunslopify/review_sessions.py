"""Bounded, session-only reviewer requests shared by the local workspaces."""

from __future__ import annotations

import copy
import hmac
import threading
import time
import uuid

from .drafts import DraftProvider, _encoded
from .review_agent import MAX_DOCUMENT, FigureReviewPlan, InvalidReview


class ReviewSessions:
    """Own provider configuration and one consented inference at a time.

    The workspace supplies trusted plan/document factories. Evidence collection
    and provider I/O run outside this object's lock; client report JSON never
    serves as a plan. A client generation describes its reviewer context.
    """

    def __init__(self, factory, document, *, source_kind):
        if not callable(factory) or not callable(document):
            raise TypeError("Configure owned reviewer plan and document factories")
        if source_kind not in {"paper-project", "editor-render"}:
            raise ValueError("Choose an owned workspace review source")
        self.factory, self.document = factory, document
        self.source_kind = source_kind
        self.lock = threading.Lock()
        self.provider = None
        self.provider_revision = 0
        self.records = {}
        self.revisions = {}
        self.building = {}
        self.active = None
        self.closed = False

    @staticmethod
    def _client(payload):
        if not isinstance(payload, dict):
            raise TypeError("Choose a reviewer request object")
        client, generation = payload.get("client"), payload.get("generation")
        if (
            not isinstance(client, str)
            or not 1 <= len(client) <= 128
            or type(generation) is not int
            or not 0 <= generation <= 2**53 - 1
        ):
            raise ValueError("Invalid reviewer client or context generation")
        return client, generation

    def _open(self):
        if self.closed:
            raise ValueError("This reviewer session has closed")

    def _prune(self):
        cutoff = time.monotonic() - 600
        expired = [key for key, row in self.records.items() if row["created"] <= cutoff]
        for key in expired:
            self.records.pop(key)["cancelled"].set()

    def _note(self, client, generation):
        if client not in self.revisions and len(self.revisions) >= 64:
            retained = {row["client"] for row in self.records.values()}
            retained.update(row["client"] for row in self.building.values())
            if self.active is not None:
                retained.add(self.active["client"])
            removable = next((key for key in self.revisions if key not in retained), None)
            if removable is None:
                raise ValueError("Too many active reviewer clients")
            self.revisions.pop(removable)
        previous = self.revisions.get(client, -1)
        if generation < previous:
            raise ValueError("This reviewer request belongs to an older context")
        self.revisions[client] = generation
        if generation > previous:
            for row in self.records.values():
                if row["client"] == client and row["generation"] < generation:
                    row["cancelled"].set()
                    row.update(phase="cancelled", result=None)

    def _info(self):
        return {
            "configured": self.provider is not None,
            "revision": self.provider_revision,
            "provider": self.provider.public() if self.provider else None,
            "authorization_configured": bool(self.provider and self.provider.api_key),
            "source_kind": self.source_kind,
            "closed": self.closed,
        }

    def info(self):
        with self.lock:
            return self._info()

    def configure(self, payload):
        if not isinstance(payload, dict) or set(payload) - {
            "enabled",
            "endpoint",
            "model",
            "protocol",
            "api_key",
        }:
            raise ValueError("Choose reviewer provider configuration fields")
        enabled = payload.get("enabled", True)
        if type(enabled) is not bool:
            raise ValueError("Choose a boolean reviewer provider enabled state")
        provider = (
            DraftProvider(
                endpoint=payload.get("endpoint", ""),
                model=payload.get("model", ""),
                protocol=payload.get("protocol", "responses"),
                api_key=payload.get("api_key", ""),
            )
            if enabled
            else None
        )
        with self.lock:
            self._open()
            for row in self.records.values():
                row["cancelled"].set()
            if self.active is not None:
                self.active["cancelled"].set()
            self.records.clear()
            self.provider = provider
            self.provider_revision += 1
            return self._info()

    def disclose(self, payload):
        client, generation = self._client(payload)
        with self.lock:
            self._open()
            self._prune()
            self._note(client, generation)
            provider, revision = self.provider, self.provider_revision
            if provider is None:
                raise ValueError("Configure a reviewer model provider first")
            if len(self.records) + len(self.building) >= 8:
                removable = next(
                    (key for key, row in self.records.items() if row is not self.active), None
                )
                if removable is None:
                    raise ValueError("Too many reviewer disclosures are being prepared")
                self.records.pop(removable)["cancelled"].set()
            builder = uuid.uuid4().hex
            reservation = {
                "client": client,
                "generation": generation,
                "cancelled": threading.Event(),
            }
            self.building[builder] = reservation
        try:
            plan = self.factory(provider, copy.deepcopy(payload))
            if not isinstance(plan, FigureReviewPlan):
                raise TypeError("The workspace must supply an owned FigureReviewPlan")
            disclosure = plan.disclosure()
            with self.lock:
                self._open()
                self._note(client, generation)
                if reservation["cancelled"].is_set():
                    raise ValueError("This reviewer disclosure was cancelled")
                if revision != self.provider_revision:
                    raise ValueError("The reviewer provider changed; prepare a new disclosure")
                identity = uuid.uuid4().hex
                self.building.pop(builder, None)
                self.records[identity] = {
                    "id": identity,
                    "plan": plan,
                    "client": client,
                    "generation": generation,
                    "provider_revision": revision,
                    "created": time.monotonic(),
                    "cancelled": threading.Event(),
                    "phase": "disclosed",
                    "result": None,
                    "error": None,
                    "worker": None,
                }
            return {
                "review_id": identity,
                "generation": generation,
                "provider_revision": revision,
                "source_kind": self.source_kind,
                "phase": "disclosed",
                **disclosure,
            }
        finally:
            with self.lock:
                self.building.pop(builder, None)

    def _record(self, payload, *, extra=()):
        client, generation = self._client(payload)
        if set(payload) - {"client", "generation", "review_id", *extra}:
            raise ValueError("Choose reviewer request control fields")
        self._open()
        self._prune()
        self._note(client, generation)
        identity = payload.get("review_id")
        if not isinstance(identity, str) or not 1 <= len(identity) <= 128:
            raise ValueError("Choose a reviewer request identity")
        row = self.records.get(identity)
        if (
            row is None
            or row["client"] != client
            or row["generation"] != generation
            or row["provider_revision"] != self.provider_revision
        ):
            raise ValueError("This reviewer request expired or its context changed")
        return row

    @staticmethod
    def _message(problem, row):
        message = str(problem)
        key = row["plan"]._provider.api_key
        return (message.replace(key, "[authorization removed]") if key else message)[:1024]

    @staticmethod
    def _public(row):
        return {
            "review_id": row["id"],
            "generation": row["generation"],
            "provider_revision": row["provider_revision"],
            "phase": row["phase"],
            "error": row["error"],
            "result": copy.deepcopy(row["result"]),
        }

    def start(self, payload):
        with self.lock:
            row = self._record(payload, extra={"consent", "consent_sha256"})
            consent_sha = payload.get("consent_sha256")
            if (
                payload.get("consent") is not True
                or not isinstance(consent_sha, str)
                or not hmac.compare_digest(consent_sha, row["plan"]._consent_sha)
            ):
                raise ValueError("Explicitly consent to the exact disclosed reviewer request")
            if row["phase"] != "disclosed" or row["cancelled"].is_set():
                raise ValueError("This reviewer request was already attempted or cancelled")
            if self.active is not None:
                raise ValueError("Another reviewer request is running; wait for it to finish")
            row.update(phase="running", result=None, error=None)
            self.active = row

            def work():
                try:
                    with self.lock:
                        if self.closed or row["cancelled"].is_set():
                            return
                    result = row["plan"].request(
                        consent=True, consent_sha256=consent_sha, cancelled=row["cancelled"]
                    )
                    if len(_encoded(result)) > MAX_DOCUMENT:
                        raise ValueError("Reviewer result exceeds the bounded document size")
                    with self.lock:
                        current = self.records.get(row["id"])
                        if (
                            not self.closed
                            and current is row
                            and not row["cancelled"].is_set()
                            and row["provider_revision"] == self.provider_revision
                            and self.revisions.get(row["client"]) == row["generation"]
                        ):
                            row.update(phase="completed", result=result, error=None)
                except InvalidReview:
                    with self.lock:
                        row.update(
                            phase="failed",
                            result=None,
                            error="The provider returned an invalid review; prepare a new request.",
                        )
                except (OSError, ValueError) as problem:
                    with self.lock:
                        row.update(
                            phase="cancelled" if row["cancelled"].is_set() else "failed",
                            result=None,
                            error=self._message(problem, row),
                        )
                except Exception:  # noqa: BLE001 -- terminate owned jobs without exposing provider data
                    with self.lock:
                        row.update(
                            phase="failed",
                            result=None,
                            error="Reviewer request failed; prepare a new disclosure.",
                        )
                finally:
                    with self.lock:
                        if row["cancelled"].is_set():
                            row.update(phase="cancelled", result=None)
                        if self.active is row:
                            self.active = None

            row["worker"] = threading.Thread(
                target=work, name="figure-review-" + row["id"], daemon=False
            )
            try:
                row["worker"].start()
            except RuntimeError:
                self.active = None
                row.update(phase="failed", worker=None, error="Reviewer worker could not start")
                raise ValueError("Reviewer worker could not start") from None
            return self._public(row)

    def _fresh(self, payload, *, extra=()):
        with self.lock:
            row = self._record(payload, extra=extra)
        try:
            row["plan"]._check_current()
        except (OSError, ValueError) as problem:
            with self.lock:
                row["cancelled"].set()
                row.update(phase="stale", result=None, error=self._message(problem, row))
            raise ValueError("Reviewer evidence changed; prepare a new disclosure") from problem
        with self.lock:
            if self._record(payload, extra=extra) is not row:
                raise ValueError("This reviewer context changed")
        return row

    def status(self, payload):
        with self.lock:
            row = self._record(payload)
            completed = row["phase"] == "completed"
        if completed:
            row = self._fresh(payload)
        with self.lock:
            if self._record(payload) is not row:
                raise ValueError("This reviewer context changed")
            return self._public(row)

    def download(self, payload):
        which = payload.get("which") if isinstance(payload, dict) else None
        if which not in {"request", "result"}:
            raise ValueError("Choose a reviewer request or result download")
        row = self._fresh(payload, extra={"which"})
        if row["cancelled"].is_set() or row["phase"] in {"cancelled", "stale"}:
            raise ValueError("This reviewer request was cancelled or became stale")
        if which == "request":
            value = self.document(row["plan"])
        else:
            with self.lock:
                if row["phase"] != "completed" or row["result"] is None:
                    raise ValueError("No completed reviewer result is available")
                value = copy.deepcopy(row["result"])
        if len(_encoded(value)) > MAX_DOCUMENT:
            raise ValueError("Reviewer download exceeds the bounded document size")
        with self.lock:
            if self._record(payload, extra={"which"}) is not row or row["cancelled"].is_set():
                raise ValueError("This reviewer context changed during download")
        return value

    def cancel(self, payload):
        client, generation = self._client(payload)
        if set(payload) - {"client", "generation", "review_id"}:
            raise ValueError("Choose reviewer cancellation fields")
        with self.lock:
            self._open()
            self._prune()
            if generation < self.revisions.get(client, -1):
                return {"cancelled": True}
            self._note(client, generation)
            identity = payload.get("review_id")
            if identity is not None and (
                not isinstance(identity, str) or not 1 <= len(identity) <= 128
            ):
                raise ValueError("Choose a reviewer request identity")
            if identity is None:
                for pending in self.building.values():
                    if pending["client"] == client:
                        pending["cancelled"].set()
            for row in self.records.values():
                if row["client"] == client and (identity is None or row["id"] == identity):
                    row["cancelled"].set()
                    row.update(phase="cancelled", result=None)
            if (
                self.active is not None
                and self.active["client"] == client
                and (identity is None or self.active["id"] == identity)
            ):
                self.active["cancelled"].set()
            return {"cancelled": True}

    def close(self):
        with self.lock:
            self.closed = True
            self.provider = None
            rows = [*self.records.values()]
            if self.active is not None and all(self.active is not row for row in rows):
                rows.append(self.active)
            workers = []
            for row in rows:
                row["cancelled"].set()
                if row["worker"] is not None:
                    workers.append(row["worker"])
            self.records.clear()
        for worker in workers:
            worker.join(timeout=10)
            if worker.is_alive():
                raise RuntimeError("Reviewer worker is still closing;retain its workspace")
