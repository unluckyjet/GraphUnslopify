"""Bounded local observation ancestry, separate from provider review packets.

This ledger records caller-supplied computation evidence. Its hashes establish
identity and internal consistency, not scientific validity or authenticity.
Renderer/dataflow instrumentation and the interactive explorer consume it later.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections.abc import Iterable, Mapping
from typing import Any

_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_MAX_BYTES = 20 * 1024 * 1024


def _plain(value: Any, depth: int = 0) -> Any:
    """Copy JSON values without coercing keys, nonfinite numbers or custom objects."""
    if depth > 20:
        raise ValueError("Observation metadata is too deeply nested")
    if value is None or type(value) in (str, int, bool):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            raise ValueError("Observation metadata keys must be strings")
        return {key: _plain(item, depth + 1) for key, item in value.items()}
    if type(value) in (list, tuple):
        return [_plain(item, depth + 1) for item in value]
    raise ValueError("Observation metadata must contain finite JSON values")


def _encoded(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf8")


def _text(value: str, name: str, limit: int = 1000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} must be nonempty bounded text")
    return value


def _positive(value: int, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate observation evidence key")
        result[key] = value
    return result


class ObservationLedger:
    """Append-only, content-addressed observations and calculations for one run.

    Record ordinals identify logical parsed records, starting at zero; they are
    neither physical CSV lines nor evidence of independent experimental units.
    No raw source bytes, paths or row values are retained automatically. Explicit
    metadata and calculated values stay local unless a caller exports them.
    """

    def __init__(
        self,
        snapshot_sha256: str,
        *,
        reader: Mapping[str, Any],
        record_count: int,
        context: Mapping[str, Any],
        max_nodes: int = 50000,
        max_edges: int = 200000,
        max_bytes: int = _MAX_BYTES,
    ):
        if not isinstance(snapshot_sha256, str) or not _SHA256.fullmatch(snapshot_sha256):
            raise ValueError("Use the full lowercase SHA256 of the actual reader snapshot")
        if type(record_count) is not int or record_count < 0:
            raise ValueError("Record count must be a nonnegative integer")
        reader = _plain(reader)
        if not isinstance(reader, dict) or reader.get("format") not in {
            "csv",
            "json",
            "parquet",
            "excel",
        }:
            raise ValueError("Reader must identify its actual supported format/configuration")
        context = _plain(context)
        required = {"run_id", "spec_sha256", "program_sha256"}
        if not isinstance(context, dict) or not required <= context.keys():
            raise ValueError("Bind observation evidence to run, specification and program")
        if context.keys() - required - {"runtime_source_sha256"}:
            raise ValueError("Unknown observation context field")
        _text(context["run_id"], "Run ID", 128)
        for name in context.keys() - {"run_id"}:
            if not isinstance(context[name], str) or not _SHA256.fullmatch(context[name]):
                raise ValueError(f"{name} must be a full lowercase SHA256")
        self._source = {
            "snapshot_sha256": snapshot_sha256,
            "reader": reader,
            "record_count": record_count,
        }
        self._context = context
        self._max_nodes = _positive(max_nodes, "Node budget")
        self._max_edges = _positive(max_edges, "Edge budget")
        self._max_bytes = _positive(max_bytes, "Byte budget")
        self._nodes: dict[str, dict[str, Any]] = {}
        self._edges = 0
        self._bytes = len(_encoded(self.as_dict()))
        if self._bytes > self._max_bytes:
            raise ValueError("Observation evidence exceeds its byte budget")
        self._source_id = hashlib.sha256(_encoded(self._source)).hexdigest()
        self._context_id = hashlib.sha256(_encoded(self._context)).hexdigest()

    @classmethod
    def from_snapshot(cls, snapshot: bytes, **kwargs) -> ObservationLedger:
        """Hash the exact bytes consumed by the reader; perform no filesystem reads."""
        if type(snapshot) is not bytes:
            raise ValueError("Reader snapshot must be bytes")
        return cls(hashlib.sha256(snapshot).hexdigest(), **kwargs)

    def _references(self, values: Iterable[str], *, exclusions: bool = False) -> list[str]:
        result = []
        if isinstance(values, (str, bytes)):
            raise TypeError("References must be a sequence of node IDs")
        for value in values:
            if not isinstance(value, str) or value not in self._nodes:
                raise ValueError("Observation reference is unknown to this ledger")
            if (self._nodes[value]["kind"] == "exclusion") is not exclusions:
                raise ValueError("Keep exclusion reasons separate from calculated inputs")
            result.append(value)
            if len(result) > self._max_edges:
                raise ValueError("Observation evidence exceeds its edge budget")
        return result

    def _append(self, payload: dict[str, Any]) -> str:
        identity = {"source": self._source_id, "node": payload}
        # Source observation identity is stable across runs of the same reader.
        # A displayed calculation additionally belongs to its actual run/program.
        if payload["kind"] != "observation":
            identity["context"] = self._context_id
        node_id = payload["kind"] + ":" + hashlib.sha256(_encoded(identity)).hexdigest()
        if node_id in self._nodes:
            return node_id
        node = {"id": node_id, **payload}
        edges = len(payload.get("inputs", [])) + len(payload.get("excluded", []))
        size = len(_encoded(node)) + bool(self._nodes)
        if len(self._nodes) >= self._max_nodes:
            raise ValueError("Observation evidence exceeds its node budget")
        if self._edges + edges > self._max_edges:
            raise ValueError("Observation evidence exceeds its edge budget")
        if self._bytes + size > self._max_bytes:
            raise ValueError("Observation evidence exceeds its byte budget")
        self._nodes[node_id] = node
        self._edges += edges
        self._bytes += size
        return node_id

    def observation(self, record_ordinal: int) -> str:
        if (
            type(record_ordinal) is not int
            or not 0 <= record_ordinal < self._source["record_count"]
        ):
            raise ValueError("Observation ordinal is outside the parsed reader snapshot")
        return self._append({"kind": "observation", "record_ordinal": record_ordinal})

    def calculate(
        self,
        operation: str,
        inputs: Iterable[str],
        *,
        value: Any,
        metadata: Mapping[str, Any] | None = None,
        excluded: Iterable[str] = (),
    ) -> str:
        """Record the actual calculation and explicitly scoped exclusion edges.

        Input order and multiplicity are retained. Distinct source records remain
        distinct even if their values/identifiers happen to be equal.
        """
        return self._append(
            {
                "kind": "calculation",
                "operation": _text(operation, "Operation", 200),
                "inputs": self._references(inputs),
                "excluded": self._references(excluded, exclusions=True),
                "value": _plain(value),
                "metadata": self._metadata(metadata),
            }
        )

    def exclude(self, reason: str, inputs: Iterable[str], *, stage: str, metadata=None) -> str:
        """Record why inputs were excluded at a named stage, not globally erased.

        A baseline can be excluded from display and still contribute to a result.
        Declaring such an exclusion never deletes its calculation ancestry.
        """
        return self._append(
            {
                "kind": "exclusion",
                "reason": _text(reason, "Exclusion reason"),
                "stage": _text(stage, "Exclusion stage", 200),
                "inputs": self._references(inputs),
                "metadata": self._metadata(metadata),
            }
        )

    @staticmethod
    def _metadata(value):
        result = _plain({} if value is None else value)
        if not isinstance(result, dict):
            raise TypeError("Observation metadata must be an object")
        return result

    def as_dict(self) -> dict[str, Any]:
        # Inputs already passed _plain at their own metadata boundary. Wrapping
        # them in the graph must not consume that accepted nesting budget again.
        return copy.deepcopy(
            {
                "schema_version": 1,
                "source": self._source,
                "context": self._context,
                "nodes": list(self._nodes.values()),
            }
        )

    def to_json(self) -> bytes:
        """Return bounded canonical UTF8 JSON; no source row values are added."""
        payload = _encoded(self.as_dict())
        if len(payload) != self._bytes or len(payload) > self._max_bytes:
            raise ValueError("Observation evidence byte accounting changed")
        return payload

    def explain(self, node_id: str) -> dict[str, Any]:
        """Return complete ancestry with contribution and exclusion roles distinct."""
        if node_id not in self._nodes:
            raise ValueError("Observation reference is unknown to this ledger")
        pending = [(node_id, self._nodes[node_id]["kind"] == "exclusion")]
        visited, contributors, excluded = set(), set(), set()
        while pending:
            identity, exclusion_role = pending.pop()
            if (identity, exclusion_role) in visited:
                continue
            visited.add((identity, exclusion_role))
            node = self._nodes[identity]
            if node["kind"] == "observation":
                (excluded if exclusion_role else contributors).add(node["record_ordinal"])
            pending.extend((item, exclusion_role) for item in node.get("inputs", []))
            pending.extend((item, True) for item in node.get("excluded", []))
        known = {identity for identity, _ in visited}
        return copy.deepcopy(
            {
                "node_id": node_id,
                "complete": True,
                "contributing_records": sorted(contributors),
                "excluded_records": sorted(excluded),
                "nodes": [node for key, node in self._nodes.items() if key in known],
            }
        )

    @classmethod
    def from_json(
        cls, payload: bytes, *, expected_context=None, expected_source=None, **budgets
    ) -> ObservationLedger:
        """Validate shape, hashes, references and ownership before reading local evidence.

        This is consistency validation; edited self-consistent evidence is not
        authenticated and must still be checked against its actual source/run.
        """
        limit = _positive(budgets.get("max_bytes", _MAX_BYTES), "Byte budget")
        if type(payload) is not bytes or len(payload) > limit:
            raise ValueError("Observation evidence exceeds its byte budget or is not bytes")
        try:
            raw = json.loads(payload, object_pairs_hook=_unique_keys)
            if not isinstance(raw, dict) or set(raw) != {
                "schema_version",
                "source",
                "context",
                "nodes",
            }:
                raise ValueError("Malformed observation evidence")
            if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
                raise ValueError("Unsupported observation evidence schema")
            if not isinstance(raw["source"], dict) or set(raw["source"]) != {
                "snapshot_sha256",
                "reader",
                "record_count",
            }:
                raise ValueError("Malformed observation source")
            if expected_context is not None and raw["context"] != _plain(expected_context):
                raise ValueError("Observation evidence belongs to a different run/program")
            result = cls(**raw["source"], context=raw["context"], **budgets)
            if expected_source is not None:
                expected = cls(**expected_source, context=result._context, **budgets)
                if result._source != expected._source:
                    raise ValueError("Observation evidence belongs to a different reader snapshot")
            if not isinstance(raw["nodes"], list) or len(raw["nodes"]) > result._max_nodes:
                raise ValueError("Malformed or oversized observation nodes")
            for node in raw["nodes"]:
                if not isinstance(node, dict) or node.get("id") in result._nodes:
                    raise ValueError("Malformed or repeated observation node")
                body = {key: value for key, value in node.items() if key not in {"id", "kind"}}
                if node.get("kind") == "observation":
                    identity = result.observation(**body)
                elif node.get("kind") == "calculation":
                    identity = result.calculate(**body)
                elif node.get("kind") == "exclusion":
                    identity = result.exclude(**body)
                else:
                    raise ValueError("Unknown observation node kind")
                if identity != node.get("id") or result._nodes[identity] != node:
                    raise ValueError("Observation node identity/content changed")
            return result
        except (KeyError, TypeError, UnicodeError, RecursionError, json.JSONDecodeError) as problem:
            raise ValueError("Malformed observation evidence") from problem
