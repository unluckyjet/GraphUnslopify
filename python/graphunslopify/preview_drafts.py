"""Session-only provider configuration and fenced, explicitly reviewed drafts."""

from __future__ import annotations

import copy
import threading
import time
import uuid

from .drafts import DraftPlan, DraftProvider, _digest


class PreviewDrafts:
    def __init__(self, state):
        self.state = state
        self.lock = threading.Lock()
        self.inference = threading.Lock()
        self.provider = None
        self.provider_revision = 0
        self.records = {}
        self.revisions = {}

    def info(self):
        with self.lock:
            return self._info()

    def _info(self):
        return {
            "configured": self.provider is not None,
            "revision": self.provider_revision,
            "provider": self.provider.public() if self.provider else None,
            "authorization_configured": bool(self.provider and self.provider.api_key),
        }

    def configure(self, payload):
        provider = (
            None
            if payload.get("enabled") is False
            else DraftProvider(
                endpoint=payload.get("endpoint", ""),
                model=payload.get("model", ""),
                protocol=payload.get("protocol", "responses"),
                api_key=payload.get("api_key", ""),
            )
        )
        with self.lock:
            self.provider = provider
            self.provider_revision += 1
            self.records.clear()
            return self._info()

    @staticmethod
    def _client(payload):
        client, generation = payload.get("client"), payload.get("generation")
        if (
            not isinstance(client, str)
            or not 1 <= len(client) <= 128
            or type(generation) is not int
            or generation < 0
        ):
            raise ValueError("Invalid model-draft revision")
        return client, generation

    def _prune(self):
        cutoff = time.monotonic() - 600
        self.records = {
            key: value for key, value in self.records.items() if value["created"] > cutoff
        }

    def _note(self, client, generation):
        if client not in self.revisions and len(self.revisions) >= 64:
            active = {record["client"] for record in self.records.values()}
            removable = next((key for key in self.revisions if key not in active), None)
            if removable is None:
                raise ValueError("Too many active draft clients")
            self.revisions.pop(removable)
        self.revisions[client] = max(generation, self.revisions.get(client, -1))
        with self.state.lock:
            rendered = self.state.generations.get(client, -1)
        if generation < max(self.revisions[client], rendered):
            raise ValueError("This draft belongs to an older editor revision; review a new request")

    def _prepared(self, payload):
        spec, data, palette = self.state.prepare(payload)
        binding = _digest(
            {"data": data["id"], "palette": palette["id"] if palette else None, "spec": spec}
        )
        return spec, data, palette, binding

    def disclose(self, payload):
        client, generation = self._client(payload)
        with self.lock:
            self._note(client, generation)
            provider, revision = self.provider, self.provider_revision
        if provider is None:
            raise ValueError("Configure a model provider first, or continue with manual authoring")
        spec, data, palette, _ = self._prepared(payload)
        plan = DraftPlan(
            provider,
            data,
            spec,
            payload.get("prompt"),
            payload.get("author_context"),
            palette_id=palette["id"] if palette else None,
            compiler_request=self.state.local_request,
        )
        with self.lock:
            self._note(client, generation)
            if revision != self.provider_revision:
                raise ValueError("The provider changed; review a new request")
            self._prune()
            if len(self.records) >= 8:
                self.records.pop(next(iter(self.records)))
            identity = uuid.uuid4().hex
            self.records[identity] = {
                "plan": plan,
                "client": client,
                "generation": generation,
                "provider_revision": revision,
                "created": time.monotonic(),
                "result": None,
                "consumed": False,
            }
        return {"draft_id": identity, "provider_revision": revision, **plan.disclosure()}

    def _current(self, payload, binding):
        client, generation = self._client(payload)
        self._note(client, generation)
        self._prune()
        record = self.records.get(payload.get("draft_id"))
        if record is None:
            raise ValueError("This draft expired or was cancelled; review a new request")
        if (
            record["client"] != client
            or record["generation"] != generation
            or record["plan"].binding != binding
            or record["provider_revision"] != self.provider_revision
        ):
            raise ValueError("Data, figure or provider changed; review a new request")
        if record["consumed"]:
            raise ValueError("This draft was already accepted; review a new request")
        return record

    def propose(self, payload):
        if payload.get("consent") is not True:
            raise ValueError("Review the disclosed request and explicitly consent before sending")
        _, _, _, binding = self._prepared(payload)
        with self.lock:
            record = self._current(payload, binding)
        if not self.inference.acquire(blocking=False):
            raise ValueError("Another model request is running; try again after it finishes")
        try:
            result = record["plan"].propose(consent=True)
            with self.lock:
                current = self._current(payload, binding)
                if current is not record:
                    raise ValueError("The reviewed request changed")
                record["result"] = result
            return {"draft_id": payload["draft_id"], **copy.deepcopy(result)}
        finally:
            self.inference.release()

    def accept(self, payload):
        if payload.get("reviewed") is not True:
            raise ValueError(
                "Explicitly review source choices, assumptions and scientific meaning first"
            )
        _, _, _, binding = self._prepared(payload)
        with self.lock:
            record = self._current(payload, binding)
            if record["result"] is None:
                raise ValueError("Generate and review a proposal first")
            record["consumed"] = True
            return {**copy.deepcopy(record["result"]), "requires_strict_render": True}

    def cancel(self, payload):
        client, generation = self._client(payload)
        with self.lock:
            if generation < self.revisions.get(client, -1):
                return {"cancelled": True}
            self._note(client, generation)
            self.records = {
                identity: record
                for identity, record in self.records.items()
                if not (
                    record["client"] == client
                    and (identity == payload.get("draft_id") or record["generation"] < generation)
                )
            }
        return {"cancelled": True}
