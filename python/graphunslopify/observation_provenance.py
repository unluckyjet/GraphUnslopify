"""Bounded local observation ancestry, separate from provider review packets.

This ledger records caller-supplied computation evidence. Its hashes establish
identity and internal consistency, not scientific validity or authenticity.
Generated programs can record reader, filter and preparation dependencies.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import sys
import tempfile
import uuid
import weakref
from collections import defaultdict
from collections.abc import Iterable, Mapping
from decimal import Decimal
from numbers import Integral, Real
from pathlib import Path
from typing import Any

import pandas as pd

_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_MAX_BYTES = 20 * 1024 * 1024
_MAX_NODES = 50_000
_RUN_ID_ENV = "GRAPHUNSLOPIFY_OBSERVATION_RUN_ID"


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
        max_nodes: int = _MAX_NODES,
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

    def explain_matrix_cell(
        self, geometry_node_id: str, png: str | Path, x: float, y: float
    ) -> dict[str, Any] | None:
        """Explain the cell at a top-left PNG coordinate in this exact saved run."""
        from .observation_geometry import inspect_png, resolve_matrix_cell, validate_matrix_geometry

        geometry = validate_matrix_geometry(self._nodes.get(geometry_node_id, {}), self._nodes)
        actual = inspect_png(png, self._context["run_id"])
        if any(geometry["image"].get(key) != value for key, value in actual.items()):
            raise ValueError("PNG bytes or dimensions changed since the matrix draw")
        node_id = resolve_matrix_cell(geometry, self._nodes, x, y)
        return self.explain(node_id) if node_id is not None else None

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


def _summary_group_codes(grouped):
    # Unlike dictionary iteration over GroupBy.indices, these positions follow
    # the order of the actual group reduction across supported pandas versions.
    return grouped.ngroup().to_numpy(dtype="int64", na_value=-1)


def _summary_input_witness(original, numeric, measured):
    statuses = [
        None
        if available
        else "missing_measurement"
        if absent
        else "nonfinite_measurement"
        if parsed
        else "invalid_numeric_measurement"
        for available, absent, parsed in zip(
            measured.notna(), original.isna(), numeric.notna(), strict=True
        )
    ]
    converted = (
        (measured.tolist(), str(original.dtype), str(measured.dtype))
        if original.dtype != measured.dtype
        else None
    )
    return statuses, converted


def _summary_groups(codes, count):
    groups = [[] for _ in range(count)]
    for position, code in enumerate(codes):
        if code >= 0:
            groups[code].append(position)
    if any(not group for group in groups):
        raise ValueError("Observation groups do not match the summary result")
    return groups


def _matrix_key(row, column):
    return tuple(None if pd.isna(label) else label for label in (row, column))


class _ObservationSelection:
    """Track parsed positions through the renderer's actual pandas operations."""

    def __init__(
        self, snapshot, *, reader, record_count, spec_json, program_sha256, runtime_sha256
    ):
        if record_count >= _MAX_NODES:
            raise ValueError("Observation selection exceeds its node budget")
        run_id = os.environ.get(_RUN_ID_ENV)
        self.run_id = uuid.uuid4().hex if run_id is None else run_id
        if not re.fullmatch(r"[a-f0-9]{32}", self.run_id):
            raise ValueError("Invalid observation selection run ID")
        self.ledger = ObservationLedger.from_snapshot(
            snapshot,
            reader=reader,
            record_count=record_count,
            context={
                "run_id": self.run_id,
                "spec_sha256": hashlib.sha256(spec_json.encode("utf8")).hexdigest(),
                "program_sha256": program_sha256,
                "runtime_source_sha256": runtime_sha256,
            },
        )
        self.positions = list(range(record_count))
        self.exclusions = []
        self.node_id = None
        self.preparation_node_id = None
        self._rows = []
        self._fields = {}
        self._preparation_exclusions = []
        self._identifier_steps = []
        self._prepared_frames = {}
        self._summary_roots = {}
        self._matrix_roots = {}
        self._matrix_geometry = None
        self._interval_column = object()
        self._estimate_column = object()
        self._estimate_geometry = None
        self._interval_geometry = None

    def sort(self, frame, field):
        # Carry positions through the actual sort, including duplicate labels and NaT.
        position = object()
        tagged = frame.copy(deep=False)
        tagged[position] = range(len(frame))
        ordered = tagged.sort_values(field)
        order = ordered.pop(position).tolist()
        ordered.columns = frame.columns
        if self.node_id is None:
            self.positions = [self.positions[i] for i in order]
        else:
            self._remap(order)
        return ordered

    def filter(self, frame, mask, step):
        if len(frame) != len(self.positions) or not mask.index.equals(frame.index):
            raise ValueError("Observation filter mask is not aligned to the parsed positions")
        selected = frame[mask]
        kept = []
        missing = []
        rejected = []
        for ordinal, keep, absent in zip(
            self.positions, mask.to_numpy(dtype=bool, na_value=False), mask.isna(), strict=True
        ):
            if keep:
                kept.append(ordinal)
            elif absent:
                missing.append(ordinal)
            else:
                rejected.append(ordinal)
        if len(selected) != len(kept):
            raise ValueError("Observation filter membership differs from pandas selection")
        for reason, records in (
            ("filter_predicate_false", rejected),
            ("filter_predicate_missing", missing),
        ):
            if records:
                self.exclusions.append(
                    self.ledger.exclude(
                        reason,
                        map(self.ledger.observation, records),
                        stage="filter",
                        metadata={"step": step},
                    )
                )
        self.positions = kept
        return selected

    def seal_filters(self, sort_field: str | None, filter_count: int) -> None:
        self._rows = [self.ledger.observation(i) for i in self.positions]
        self.node_id = self.ledger.calculate(
            "reader_filter_selection",
            self._rows,
            value=len(self.positions),
            metadata={"temporal_sort_field": sort_field, "filter_count": filter_count},
            excluded=self.exclusions,
        )

    def _remap(self, order):
        self._rows = [self._rows[i] for i in order]
        self._fields = {field: [refs[i] for i in order] for field, refs in self._fields.items()}

    def identifiers(self, frame, normalize, fields, *, final=True):
        normalized = normalize(frame, final=final)
        present = [field for field in fields if field in normalized]
        if present:
            lexical = frame.attrs.get("_graphunslopify_identity_rows", {})
            self._identifier_steps.append(
                {"fields": present, "lexical_fields": [f for f in present if f in lexical]}
            )
        return normalized

    def melt(self, frame, *, id_vars, value_vars, var_name, value_name):
        # A string label keeps pandas' original string column dtype on pandas 3.
        marker = "_graphunslopify_lineage_position"
        while marker in frame.columns or marker in (var_name, value_name):
            marker += "_"
        tagged = frame.copy(deep=False)
        tagged[marker] = range(len(frame))
        result = tagged.melt(
            id_vars=[*id_vars, marker],
            value_vars=value_vars,
            var_name=var_name,
            value_name=value_name,
        )
        self._remap(result.pop(marker).tolist())
        self._rows = [
            self.ledger.calculate(
                "wide_reshape",
                [row],
                value=None,
                metadata={"source_field": field, "measurement_field": value_name},
            )
            for row, field in zip(self._rows, result[var_name], strict=True)
        ]
        return result

    @staticmethod
    def _number(value):
        if isinstance(value, Decimal):
            if value.is_finite():
                return str(value), "finite"
            if value.is_nan():
                return None, "missing"
            return None, "negative_infinity" if value.is_signed() else "positive_infinity"
        if pd.isna(value):
            return None, "missing"
        if isinstance(value, Integral):
            return int(value), "finite"
        if isinstance(value, Real):
            value = float(value)
            if math.isfinite(value):
                return value, "finite"
            return None, "positive_infinity" if value > 0 else "negative_infinity"
        raise ValueError("Unexpected numeric value in observation preparation")

    def numeric(self, field, before, after, stage):
        refs = self._fields.get(field, self._rows)
        missing = [ref for ref, absent in zip(refs, after.isna(), strict=True) if absent]
        if missing:
            self._preparation_exclusions.append(
                self.ledger.exclude(
                    "missing_measurement", missing, stage=stage, metadata={"field": field}
                )
            )
        if before.dtype != after.dtype:
            metadata = {
                "field": field,
                "from_dtype": str(before.dtype),
                "to_dtype": str(after.dtype),
                "stage": stage,
            }
            self._fields[field] = [
                self._measurement("numeric_conversion", [ref], value, metadata)
                for ref, value in zip(refs, after.tolist(), strict=True)
            ]

    def _measurement(self, operation, inputs, value, metadata, *, excluded=()):
        number, status = self._number(value)
        if isinstance(value, Decimal):
            metadata = {**metadata, "numeric_encoding": "decimal"}
        return self.ledger.calculate(
            operation,
            inputs,
            value=number,
            metadata={**metadata, "value_status": status},
            excluded=excluded,
        )

    def _excluded_measurement(self, reason, ref, field):
        return self.ledger.exclude(reason, [ref], stage="transform", metadata={"field": field})

    def _grouped_measurements(self, operation, field, after, groups, visit):
        refs = self._fields.get(field, self._rows)
        values = after.tolist()
        result = [None] * len(refs)
        for key, positions in groups.items():
            visit(key, positions, refs, values, result)
        for index, ref in enumerate(refs):
            if result[index] is None:
                excluded = self._excluded_measurement("missing_transform_group", ref, field)
                result[index] = self._measurement(
                    operation, [], values[index], {"field": field}, excluded=[excluded]
                )
        self._fields[field] = result

    def cumulative(self, field, before, after, groups):
        missing = before.isna().tolist()

        def group(_key, positions, refs, values, result):
            previous = None
            skipped = []
            for index in positions:
                inputs = [] if previous is None else [previous]
                if missing[index]:
                    absent = self._excluded_measurement("missing_measurement", refs[index], field)
                    skipped.append(absent)
                    result[index] = self._measurement(
                        "cumulative", inputs, values[index], {"field": field}, excluded=[absent]
                    )
                else:
                    previous = result[index] = self._measurement(
                        "cumulative",
                        [*inputs, refs[index]],
                        values[index],
                        {"field": field},
                        excluded=skipped,
                    )
                    # Later outputs inherit these exclusions through the prefix node.
                    skipped.clear()

        self._grouped_measurements("cumulative", field, after, groups, group)

    def normalize(self, field, before, after, groups, ranges):
        missing = before.isna().tolist()

        def group(key, positions, refs, values, result):
            low, high = ranges[key]
            low_value, low_status = self._number(low)
            high_value, high_status = self._number(high)
            present = [refs[i] for i in positions if not missing[i]]
            excluded = [refs[i] for i in positions if missing[i]]
            range_node = self.ledger.calculate(
                "normalization_range",
                present,
                value=[low_value, high_value],
                metadata={
                    "field": field,
                    "constant_range": bool(present) and bool(high == low),
                    "bound_status": [low_status, high_status],
                },
                excluded=(
                    [
                        self.ledger.exclude(
                            "missing_measurement",
                            excluded,
                            stage="normalization_range",
                            metadata={"field": field},
                        )
                    ]
                    if excluded
                    else []
                ),
            )
            for index in positions:
                inputs, absent = [range_node], []
                if missing[index]:
                    absent.append(
                        self._excluded_measurement("missing_measurement", refs[index], field)
                    )
                else:
                    inputs.insert(0, refs[index])
                result[index] = self._measurement(
                    "normalize", inputs, values[index], {"field": field}, excluded=absent
                )

        self._grouped_measurements("normalize", field, after, groups, group)

    def baseline(
        self,
        frame,
        field,
        before,
        *,
        source_mask,
        display_mask,
        reference,
        groups,
        x_field,
        operation,
    ):
        refs = self._fields.get(field, self._rows)
        missing = before.isna().tolist()
        source = [
            i for i, take in enumerate(source_mask.to_numpy(dtype=bool, na_value=False)) if take
        ]
        means = []
        for key, value in reference.items():
            members = [source[i] for i in groups[key]]
            excluded = [refs[i] for i in members if missing[i]]
            absent = (
                [
                    self.ledger.exclude(
                        "missing_measurement",
                        excluded,
                        stage="baseline_mean",
                        metadata={"field": field},
                    )
                ]
                if excluded
                else []
            )
            means.append(
                self._measurement(
                    "baseline_mean",
                    [refs[i] for i in members if not missing[i]],
                    value,
                    {"field": field},
                    excluded=absent,
                )
            )
        match = reference.index.get_indexer(frame[x_field])
        kept, removed = [], []
        result = list(refs)
        for i, (take, value) in enumerate(
            zip(
                display_mask.to_numpy(dtype=bool, na_value=False),
                frame[field].tolist(),
                strict=True,
            )
        ):
            if not take:
                removed.append(self._rows[i])
                continue
            kept.append(i)
            inputs, absent = [], []
            if missing[i]:
                absent.append(self._excluded_measurement("missing_measurement", refs[i], field))
            else:
                inputs.append(refs[i])
            if match[i] < 0:
                absent.append(self._excluded_measurement("baseline_unmatched", refs[i], field))
            else:
                inputs.append(means[match[i]])
            result[i] = self._measurement(
                operation, inputs, value, {"field": field}, excluded=absent
            )
        if removed:
            self._preparation_exclusions.append(
                self.ledger.exclude("baseline_hidden", removed, stage="after_baseline_transform")
            )
        self._fields[field] = result
        self._remap(kept)
        return frame[display_mask]

    def finish_preparation(self, frame) -> None:
        if len(self._rows) != len(frame):
            raise ValueError("Observation preparation does not match the prepared frame")
        rows = []
        for index, row in enumerate(self._rows):
            changed = {
                field: refs[index] for field, refs in self._fields.items() if refs[index] != row
            }
            if changed:
                rows.append(
                    self.ledger.calculate(
                        "prepared_observation",
                        [row, *changed.values()],
                        value=None,
                        metadata={"measurement_fields": list(changed)},
                    )
                )
            else:
                rows.append(row)
        self.preparation_node_id = self.ledger.calculate(
            "prepared_selection",
            rows,
            value=len(rows),
            metadata={"identifier_steps": self._identifier_steps},
            excluded=[*self.exclusions, *self._preparation_exclusions],
        )
        self._prepared_frames[id(frame)] = (weakref.ref(frame), range(len(frame)), None, {})

    def _prepared_frame(self, frame):
        reference, positions, panel, fields = self._prepared_frames.get(
            id(frame), (None, None, None, None)
        )
        if reference is None or reference() is not frame or len(positions) != len(frame):
            raise ValueError("Observation calculation frame has no prepared row mapping")
        return positions, panel, fields

    def prepared_subset(self, frame, mask, panel):
        positions, _, _ = self._prepared_frame(frame)
        if not mask.index.equals(frame.index):
            raise ValueError("Observation panel mask is not aligned to its source frame")
        subset = frame[mask]
        membership = mask.to_numpy(dtype=bool, na_value=False)
        kept = [
            position for position, include in zip(positions, membership, strict=True) if include
        ]
        if len(kept) != len(subset):
            raise ValueError("Observation panel membership differs from pandas selection")
        self._prepared_frames[id(subset)] = (weakref.ref(subset), kept, panel, {})
        return subset

    def _summary_support(self, members, references, witness, field):
        statuses, converted = witness
        inputs = []
        rejected = defaultdict(list)
        for position in members:
            reference = references[position]
            reason = statuses[position]
            if reason is not None:
                rejected[reason].append(reference)
                continue
            if converted is not None:
                values, input_dtype, output_dtype = converted
                reference = self._measurement(
                    "summary_numeric_conversion",
                    [reference],
                    values[position],
                    {"field": field, "from_dtype": input_dtype, "to_dtype": output_dtype},
                )
            inputs.append(reference)
        exclusions = [
            self.ledger.exclude(reason, refs, stage="summary", metadata={"field": field})
            for reason, refs in rejected.items()
        ]
        return inputs, exclusions

    def record_summary(
        self,
        frame,
        result,
        witness,
        unit_codes,
        unit_values,
        point_codes,
        *,
        keys,
        field,
        aggregation,
        unit_field,
        interval,
        bootstrap=None,
        panel=None,
    ):
        positions, registered_panel, summarized_fields = self._prepared_frame(frame)
        if registered_panel is not None:
            panel = registered_panel
        if field in summarized_fields:
            return summarized_fields[field]
        source_field = self._fields.get(field, self._rows)
        references = [source_field[i] for i in positions]
        groups = _summary_groups(point_codes, len(result))
        point_keys = list(result[keys].itertuples(index=False, name=None))
        omitted = defaultdict(list)
        units = None
        if unit_codes is None:
            omitted[None, "missing_summary_key"] = [
                ref for ref, code in zip(references, point_codes, strict=True) if code < 0
            ]
        else:
            unit_groups = _summary_groups(unit_codes, len(unit_values))
            units = []
            for group, value in zip(unit_groups, unit_values, strict=True):
                inputs, excluded = self._summary_support(group, references, witness, field)
                units.append(
                    self._measurement(
                        "technical_repeat_summary",
                        inputs,
                        value,
                        {
                            "field": field,
                            "unit_field": unit_field,
                            "unit": str(frame[unit_field].iat[group[0]]),
                            "estimator": aggregation,
                        },
                        excluded=excluded,
                    )
                )
            lookup = {key: index for index, key in enumerate(point_keys)}
            for i, key in enumerate(frame[keys].itertuples(index=False, name=None)):
                if unit_codes[i] >= 0:
                    continue
                if any(pd.isna(value) for value in key):
                    omitted[None, "missing_summary_key"].append(references[i])
                else:
                    reason = (
                        "missing_unit_identifier"
                        if pd.isna(frame[unit_field].iat[i])
                        else "missing_unit_group_key"
                    )
                    omitted[lookup.get(key), reason].append(references[i])
        exclusions = defaultdict(list)
        for (index, reason), refs in omitted.items():
            if refs:
                exclusions[index].append(
                    self.ledger.exclude(reason, refs, stage="summary", metadata={"field": field})
                )
        roots = []
        estimates = []
        intervals = []
        for index, members in enumerate(groups):
            rejected = exclusions[index]
            if units is None:
                inputs, rejected_measurements = self._summary_support(
                    members, references, witness, field
                )
                rejected += rejected_measurements
            else:
                inputs = [units[i] for i in members if not pd.isna(unit_values[i])]
                invalid_units = [units[i] for i in members if pd.isna(unit_values[i])]
                if invalid_units:
                    rejected.append(
                        self.ledger.exclude(
                            "unusable_unit_measurement", invalid_units, stage="summary"
                        )
                    )
            metadata = {
                "field": field,
                "keys": dict(zip(keys, map(str, point_keys[index]), strict=True)),
                "point": index,
            }
            support = self.ledger.calculate(
                "summary_sample",
                inputs,
                value=len(inputs),
                metadata={**metadata, "unit_field": unit_field},
                excluded=rejected,
            )
            center = self._measurement(
                "summary_estimate",
                [support],
                result[field].iat[index],
                {**metadata, "estimator": aggregation},
            )
            roots.append(center)
            estimates.append(center)
            if interval is not None:
                interval_id = self._summary_interval(
                    result, index, support, center, len(inputs), metadata, interval, bootstrap
                )
                roots.append(interval_id)
                intervals.append(interval_id)
        root = self.ledger.calculate(
            "summary_panel",
            roots,
            value=len(groups),
            metadata={"panel": panel, "field": field, "unit_field": unit_field},
            excluded=exclusions[None],
        )
        self._summary_roots[root] = None
        identities = (tuple(estimates), tuple(intervals))
        summarized_fields[field] = identities
        return identities

    def summary_geometry_frame(self, result, identities):
        """Tag only the drawn frame so sorting and selection keep the calculation IDs."""
        estimates, intervals = identities
        if len(estimates) != len(result) or (intervals and len(intervals) != len(result)):
            raise ValueError("Observation IDs do not match the summary positions")
        tagged = result.copy(deep=False)
        tagged[self._estimate_column] = list(estimates)
        if intervals:
            tagged[self._interval_column] = list(intervals)
        return tagged

    def bind_summary_bars(self, container, drawn):
        """Tag real bars only, keeping reindexed category slots empty."""
        for patch, identity in zip(container.patches, drawn[self._estimate_column], strict=True):
            if isinstance(identity, str):
                patch._graphunslopify_estimate_id = identity

    def bind_summary_dot(self, artist, drawn):
        """Tag the center marker with the estimate from the forest's chosen row."""
        artist._graphunslopify_estimate_id = drawn[self._estimate_column].iloc[0]

    def bind_summary_curve(self, artist, drawn):
        """Attach ordered summary points to the actual primary line artist."""
        artist._graphunslopify_estimate_id = None
        artist._graphunslopify_estimate_ids = tuple(drawn[self._estimate_column])

    def bind_summary_intervals(self, container, drawn):
        """Associate actual error bars with the interval nodes in draw order."""
        # Reindexing grouped bars inserts empty positions between real summaries.
        interval_ids = tuple(
            value if isinstance(value, str) else None for value in drawn[self._interval_column]
        )
        _, caps, stems = container.lines
        if len(stems) != 1:
            raise ValueError("Observation interval binding requires one error-bar collection")
        stems[0]._graphunslopify_interval_ids = interval_ids
        for cap in caps:
            cap._graphunslopify_interval_ids = interval_ids

    def bind_summary_interval_line(self, artist, drawn, role):
        """Bind the interval from the first summary row chosen by the forest drawer."""
        artist._graphunslopify_interval_ids = (drawn[self._interval_column].iloc[0],)
        artist._graphunslopify_interval_role = role

    def bind_summary_band(self, artist, drawn, x_field):
        """Capture the same ordered inputs and unit conversion as the filled artist."""
        import numpy as np

        x = np.asarray(artist.convert_xunits(drawn[x_field]), dtype=float)
        low = drawn["_low"].to_numpy(dtype=float, na_value=np.nan)
        high = drawn["_high"].to_numpy(dtype=float, na_value=np.nan)
        artist._graphunslopify_interval_ids = tuple(drawn[self._interval_column])
        artist._graphunslopify_band_inputs = (x, low, high)

    def _summary_interval(self, result, index, support, center, count, metadata, kind, bootstrap):
        low, lower_status = self._number(result["_low"].iat[index])
        high, upper_status = self._number(result["_high"].iat[index])
        return self.ledger.calculate(
            "summary_interval",
            [support, center] if kind in {"std", "sem"} else [support],
            value=[low, high],
            metadata={
                **metadata,
                "estimator": kind,
                "lower_status": lower_status,
                "upper_status": upper_status,
                **({"ddof": 1} if kind in {"std", "sem"} else {}),
                **({"quantiles": [0.25, 0.75]} if kind == "iqr" else {}),
                **({"bootstrap": bootstrap} if bootstrap is not None else {}),
                **({"unavailable": "insufficient_measurements"} if count < 2 else {}),
            },
        )

    def record_matrix(
        self,
        image,
        frame,
        matrix,
        shown,
        *,
        axes,
        field,
        aggregation,
        text,
        normalization=None,
        totals=None,
        weights=None,
    ):
        """Bind the actual image array to positional memberships and aggregates."""
        positions, panel, _ = self._prepared_frame(frame)
        confusion = normalization is not None
        if shown.shape != matrix.shape:
            raise ValueError("Observation matrix does not match the displayed array")

        # Match the numeric pivot's grouping policy. Its post-aggregation
        # reindexing can add cells, so bind by actual labels rather than group order.
        grouped = frame.groupby(list(axes), observed=True, sort=confusion, dropna=confusion).indices
        groups = {_matrix_key(*key): members for key, members in grouped.items()}
        field_references = self._fields.get(field, self._rows)
        references = [field_references[position] for position in positions]
        if weights is not None:
            metadata = {
                "field": field,
                "from_dtype": str(frame[field].dtype),
                "to_dtype": str(weights.dtype),
            }
            references = [
                self._measurement("confusion_weight", [reference], value, metadata)
                for reference, value in zip(references, weights, strict=True)
            ]
        missing = frame[field].isna().to_numpy() if field is not None and weights is None else None
        unassigned = set(range(len(frame)))
        cell_nodes = []
        cell_metadata = []
        for row, row_label in enumerate(matrix.index):
            row_nodes = []
            row_metadata = []
            for column, column_label in enumerate(matrix.columns):
                members = groups.get(_matrix_key(row_label, column_label), ())
                unassigned.difference_update(members)
                inputs = []
                rejected = []
                for position in members:
                    target = rejected if missing is not None and missing[position] else inputs
                    target.append(references[position])
                excluded = (
                    [
                        self.ledger.exclude(
                            "missing_measurement",
                            rejected,
                            stage="matrix",
                            metadata={"field": field},
                        )
                    ]
                    if rejected
                    else []
                )
                aggregate, aggregate_status = self._number(matrix.iat[row, column])
                metadata = {
                    "row": row,
                    "column": column,
                    "row_label": str(row_label),
                    "column_label": str(column_label),
                    "aggregation": aggregation,
                    "aggregate": aggregate,
                    "aggregate_status": aggregate_status,
                    "record_count": len(members),
                    "contributing_count": len(inputs),
                    "membership": (
                        "unobserved"
                        if len(members) == 0
                        else "observed"
                        if inputs
                        else "all_missing"
                    ),
                }
                if (row, column) in text:
                    metadata["annotation"] = text[row, column]
                row_metadata.append(metadata)
                if totals is None:
                    node = self._measurement(
                        "matrix_cell", inputs, shown[row, column], metadata, excluded=excluded
                    )
                else:
                    count_metadata = {
                        key: value for key, value in metadata.items() if key != "annotation"
                    }
                    node = self._measurement(
                        "matrix_count",
                        inputs,
                        matrix.iat[row, column],
                        count_metadata,
                        excluded=excluded,
                    )
                row_nodes.append(node)
            cell_nodes.append(row_nodes)
            cell_metadata.append(row_metadata)

        if totals is not None:
            cell_nodes = self._normalized_matrix(
                cell_nodes, cell_metadata, shown, totals, normalization
            )
        excluded = (
            [
                self.ledger.exclude(
                    "matrix_key_not_displayed",
                    (references[position] for position in sorted(unassigned)),
                    stage="matrix",
                    metadata={"axes": axes},
                )
            ]
            if unassigned
            else []
        )
        root = self.ledger.calculate(
            "matrix_panel",
            (node for row in cell_nodes for node in row),
            value=int(matrix.size),
            metadata={
                "panel": panel if panel is not None else 0,
                "kind": "confusion_matrix" if confusion else "heatmap",
                "row_field": axes[0],
                "column_field": axes[1],
                "value_field": field,
                "normalization": normalization,
                "shape": matrix.shape,
            },
            excluded=excluded,
        )
        self._matrix_roots[root] = None
        image._graphunslopify_matrix_panel_id = root
        image._graphunslopify_matrix_node_ids = cell_nodes

    def record_matrix_geometry(self, capture, output):
        # Keep only the final saved PNG if an output format was repeated.
        self._matrix_geometry = (capture, output)

    def record_summary_interval_geometry(self, capture, output):
        self._interval_geometry = (capture, output, "strokes")

    def record_summary_band_geometry(self, capture, output):
        self._interval_geometry = (capture, output, "bands")

    def record_summary_marks_geometry(self, capture, output):
        intervals, estimates = capture
        if intervals is not None:
            image, marks, gaps, kind = intervals
            self._interval_geometry = ((image, marks, gaps), output, kind)
        self._estimate_geometry = (estimates, output)

    def _estimate_geometry_reference(self):
        if self._estimate_geometry is None:
            return {}
        (image, entries, gaps, coverage), output = self._estimate_geometry
        if image is None or gaps:
            return {"summary_estimate_geometry_gap": gaps[0]}
        if not entries:
            return {
                "summary_estimate_geometry_gap": next(
                    iter(coverage), "No visible estimates in the final PNG"
                )
            }
        if any(image[key] != output[key] for key in ("sha256", "bytes")):
            return {
                "summary_estimate_geometry_gap": "The PNG changed during estimate geometry capture"
            }
        try:
            entries = [
                self._line_span(entry) if entry["kind"] == "segment" else entry for entry in entries
            ]
            identity = self.ledger.calculate(
                "summary_estimate_png_geometry",
                dict.fromkeys(entry["node_id"] for entry in entries),
                value=len(entries),
                metadata={
                    "coordinates": "pixels_top_left",
                    "image": {"path": output["path"], **image},
                    "estimates": entries,
                    **({"coverage": coverage} if coverage else {}),
                },
            )
        except ValueError as problem:
            return {"summary_estimate_geometry_gap": str(problem)}
        return {"summary_estimate_geometry_node_id": identity}

    def _line_span(self, entry):
        endpoints = entry["endpoint_ids"]
        span = self.ledger.calculate(
            "summary_line_span",
            endpoints,
            value=None,
            metadata={
                "endpoint_keys": [
                    self.ledger._nodes[item]["metadata"]["keys"] for item in endpoints
                ]
            },
        )
        return {**entry, "node_id": span}

    def _interval_geometry_reference(self):
        if self._interval_geometry is None:
            return {}
        (image, entries, gaps), output, kind = self._interval_geometry
        if image is None or gaps:
            return {"summary_interval_geometry_gap": gaps[0]}
        if not entries:
            return {"summary_interval_geometry_gap": "No visible intervals in the final PNG"}
        if any(image[key] != output[key] for key in ("sha256", "bytes")):
            return {
                "summary_interval_geometry_gap": "The PNG changed during interval geometry capture"
            }
        try:
            if kind == "bands":
                entries = [self._band_entry(entry) for entry in entries]
            node_id = self.ledger.calculate(
                "summary_interval_png_geometry",
                dict.fromkeys(entry["node_id"] for entry in entries),
                value=len(entries),
                metadata={
                    "coordinates": "pixels_top_left",
                    "image": {"path": output["path"], **image},
                    "strokes": entries if kind == "strokes" else [],
                    **({"bands": entries} if kind == "bands" else {}),
                },
            )
        except ValueError as problem:
            return {"summary_interval_geometry_gap": str(problem)}
        return {"summary_interval_geometry_node_id": node_id}

    def _band_entry(self, entry):
        intervals = entry["interval_ids"]
        span = self.ledger.calculate(
            "summary_band_span",
            intervals,
            value=None,
            metadata={
                "endpoint_keys": [
                    self.ledger._nodes[node]["metadata"]["keys"] for node in intervals
                ]
            },
        )
        return {**entry, "node_id": span}

    def _matrix_geometry_reference(self):
        if self._matrix_geometry is None:
            return {}
        (image, grids, gaps), output = self._matrix_geometry
        if image is None:
            return {"matrix_geometry_gap": gaps[0]}
        if any(image[key] != output[key] for key in ("sha256", "bytes")):
            return {"matrix_geometry_gap": "The PNG changed during matrix geometry capture"}
        try:
            node_id = self.ledger.calculate(
                "matrix_png_geometry",
                dict.fromkeys(grid["panel_id"] for grid in grids),
                value=len(grids),
                metadata={
                    "coordinates": "pixels_top_left",
                    "image": {"path": output["path"], **image},
                    "grids": grids,
                    "gaps": gaps,
                },
            )
        except ValueError as problem:
            return {"matrix_geometry_gap": str(problem)}
        return {"matrix_geometry_node_id": node_id}

    def _normalized_matrix(self, counts, metadata, shown, totals, normalization):
        by_row = normalization == "row"
        axis_counts = counts if by_row else list(zip(*counts, strict=True))
        values = totals.ravel()
        denominators = [
            self._measurement(
                "matrix_normalization_total",
                inputs,
                value,
                {"axis": normalization, "position": index, "zero_total": bool(value == 0)},
            )
            for index, (inputs, value) in enumerate(zip(axis_counts, values, strict=True))
        ]
        displayed = []
        for row, nodes in enumerate(counts):
            row_nodes = []
            for column, numerator in enumerate(nodes):
                index = row if by_row else column
                row_nodes.append(
                    self._measurement(
                        "matrix_cell",
                        [numerator, denominators[index]],
                        shown[row, column],
                        {
                            **metadata[row][column],
                            "normalization": normalization,
                            "zero_total": bool(values[index] == 0),
                        },
                    )
                )
            displayed.append(row_nodes)
        return displayed

    def write(self, directory: Path) -> dict[str, str]:
        if self.node_id is None:
            raise ValueError("Observation selection is incomplete")
        summary = (
            self.ledger.calculate(
                "ordinary_summaries",
                self._summary_roots,
                value=len(self._summary_roots),
            )
            if self._summary_roots
            else None
        )
        matrix = (
            self.ledger.calculate(
                "matrix_panels", self._matrix_roots, value=len(self._matrix_roots)
            )
            if self._matrix_roots
            else None
        )
        matrix_geometry = self._matrix_geometry_reference()
        interval_geometry = self._interval_geometry_reference()
        estimate_geometry = self._estimate_geometry_reference()
        payload = self.ledger.to_json()
        path = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=directory, prefix=f"observations-{self.run_id}-", suffix=".json", delete=False
            ) as output:
                path = Path(output.name)
                output.write(payload)
        except OSError:
            if path is not None:
                path.unlink(missing_ok=True)
            raise
        # Publish the reference only after the exclusively created file is complete.
        return {
            "path": path.name,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "node_id": self.node_id,
            "run_id": self.run_id,
            **(
                {"preparation_node_id": self.preparation_node_id}
                if self.preparation_node_id
                else {}
            ),
            **({"summary_node_id": summary} if summary is not None else {}),
            **({"matrix_node_id": matrix} if matrix is not None else {}),
            **matrix_geometry,
            **interval_geometry,
            **estimate_geometry,
        }


def _read_observation_selection(
    directory: Path, report: dict, *, run_id: str, program_sha256: str
) -> Path:
    """Read the bounded graph owned by this SDK invocation before returning it."""
    path, _ = _load_observation_selection(
        directory, report, run_id=run_id, program_sha256=program_sha256
    )
    return path


def _load_observation_selection(
    directory: Path,
    report: dict,
    *,
    run_id: str,
    program_sha256: str,
    require_contained_png: bool = False,
) -> tuple[Path, ObservationLedger]:
    selection = report["observation_selection"]
    name = selection["path"]
    if selection["run_id"] != run_id or not re.fullmatch(
        rf"observations-{re.escape(run_id)}-[a-z0-9_]+\.json", name
    ):
        raise ValueError("Observation selection belongs to a different run")
    if report["script"]["sha256"] != program_sha256:
        raise ValueError("Observation selection belongs to a different generated program")
    path = directory / name
    if path.is_symlink() or not path.is_file():
        raise ValueError("Observation selection must be a local regular file")
    with path.open("rb") as source:
        payload = source.read(_MAX_BYTES + 1)
    if len(payload) > _MAX_BYTES or hashlib.sha256(payload).hexdigest() != selection["sha256"]:
        raise ValueError("Observation selection content changed or exceeds its byte budget")
    graph = ObservationLedger.from_json(payload)
    if (
        graph._context["run_id"] != run_id
        or graph._context["program_sha256"] != program_sha256
        or graph._context["spec_sha256"][:16] != report["spec_hash"]
        or graph._context.get("runtime_source_sha256")
        != report["script"]["runtime"]["source_sha256"]
        or graph._source["snapshot_sha256"][:16] != report["data"]["sha256_prefix"]
        or graph._source["record_count"] != report["data"]["counts"]["read"]
    ):
        raise ValueError("Observation selection does not match its render report")
    node = graph._nodes.get(selection["node_id"], {})
    if (
        node.get("operation") != "reader_filter_selection"
        or node["value"] != report["data"]["counts"]["after_filter"]
    ):
        raise ValueError("Observation selection root does not match the rendered selection")
    if "preparation_node_id" in selection:
        preparation = graph._nodes.get(selection["preparation_node_id"], {})
        if (
            preparation.get("operation") != "prepared_selection"
            or preparation["value"] != report["data"]["counts"]["prepared"]
            or len(preparation["inputs"]) != preparation["value"]
        ):
            raise ValueError("Observation preparation root does not match the prepared frame")
    for kind, operation, panel_operation in (
        ("summary", "ordinary_summaries", "summary_panel"),
        ("matrix", "matrix_panels", "matrix_panel"),
    ):
        name = f"{kind}_node_id"
        if name not in selection:
            continue
        root = graph._nodes.get(selection[name], {})
        if (
            "preparation_node_id" not in selection
            or root.get("operation") != operation
            or root["value"] != len(root["inputs"])
            or any(
                graph._nodes[item].get("operation") != panel_operation for item in root["inputs"]
            )
        ):
            raise ValueError(f"Observation {kind} root does not match the calculated panels")
    geometry = None
    if "matrix_geometry_node_id" in selection:
        from .observation_geometry import validate_matrix_geometry

        if "matrix_geometry_gap" in selection:
            raise ValueError("Observation report contains conflicting matrix geometry references")
        geometry_node = graph._nodes.get(selection["matrix_geometry_node_id"], {})
        geometry = validate_matrix_geometry(geometry_node, graph._nodes)
        matrix_root = graph._nodes.get(selection.get("matrix_node_id"), {})
        if not set(geometry_node["inputs"]) <= set(matrix_root.get("inputs", [])):
            raise ValueError("Matrix PNG geometry belongs to a different matrix calculation")
    if "summary_interval_geometry_node_id" in selection:
        from .observation_geometry import validate_summary_interval_geometry

        if geometry is not None or "summary_interval_geometry_gap" in selection:
            raise ValueError("Observation report contains conflicting PNG geometry references")
        geometry_node = graph._nodes.get(selection["summary_interval_geometry_node_id"], {})
        geometry = validate_summary_interval_geometry(geometry_node, graph._nodes)
        summary_root = graph._nodes.get(selection.get("summary_node_id"), {})
        panels = [set(graph._nodes[panel]["inputs"]) for panel in summary_root.get("inputs", [])]
        panel_inputs = set().union(*panels)
        for identity in geometry_node["inputs"]:
            target = graph._nodes[identity]
            if target["operation"] == "summary_band_span":
                valid = any(set(target["inputs"]) <= panel for panel in panels)
            else:
                valid = identity in panel_inputs
            if not valid:
                raise ValueError("Interval PNG geometry belongs to a different summary calculation")
    if "summary_estimate_geometry_node_id" in selection:
        from .observation_geometry import validate_summary_estimate_geometry

        if "matrix_geometry_node_id" in selection or "summary_estimate_geometry_gap" in selection:
            raise ValueError("Observation report contains conflicting estimate geometry references")
        geometry_node = graph._nodes.get(selection["summary_estimate_geometry_node_id"], {})
        estimates = validate_summary_estimate_geometry(geometry_node, graph._nodes)
        summary_root = graph._nodes.get(selection.get("summary_node_id"), {})
        panels = [set(graph._nodes[panel]["inputs"]) for panel in summary_root.get("inputs", [])]
        panel_inputs = set().union(*panels)
        for identity in geometry_node["inputs"]:
            target = graph._nodes[identity]
            if target["operation"] == "summary_line_span":
                valid = any(set(target["inputs"]) <= panel for panel in panels)
            else:
                valid = identity in panel_inputs
            if not valid:
                raise ValueError("Estimate PNG geometry belongs to a different summary calculation")
        if geometry is not None and geometry["image"] != estimates["image"]:
            raise ValueError("Summary interval and estimate geometry belong to different PNGs")
        geometry = estimates
    if geometry is not None:
        from .observation_geometry import inspect_png

        image = geometry["image"]
        output = next(
            (
                row
                for row in reversed(report["outputs"])
                if row["format"] == "png" and row["path"] == image["path"]
            ),
            None,
        )
        if output is None or any(image[key] != output[key] for key in ("sha256", "bytes")):
            raise ValueError("Observation PNG geometry does not match the recorded output")
        png = directory / image["path"]
        if require_contained_png and not png.resolve().is_relative_to(directory.resolve()):
            raise ValueError("Observation PNG escapes the saved render directory")
        actual = inspect_png(png, run_id)
        if any(image.get(key) != value for key, value in actual.items()):
            raise ValueError("PNG bytes or dimensions changed since the observation draw")
    return path, graph


def explain_saved_matrix_cell(
    report_path: str | Path,
    x: float,
    y: float,
    *,
    run_directory: str | Path | None = None,
) -> dict[str, Any]:
    """Resolve a saved SDK render without executing its program or rereading its data."""
    return _explain_saved_position(report_path, x, y, run_directory, geometry_key="matrix")


def explain_saved_interval(
    report_path: str | Path, x: float, y: float, *, run_directory: str | Path | None = None
) -> dict[str, Any]:
    """Explain the summary interval at a coordinate in the exact saved PNG."""
    return _explain_saved_position(
        report_path, x, y, run_directory, geometry_key="summary_interval"
    )


def explain_saved_estimate(
    report_path: str | Path, x: float, y: float, *, run_directory: str | Path | None = None
) -> dict[str, Any]:
    """Explain the summary estimate at a coordinate in the exact saved PNG."""
    return _explain_saved_position(
        report_path, x, y, run_directory, geometry_key="summary_estimate"
    )


def _explain_saved_position(report_path, x, y, run_directory, *, geometry_key):
    from .observation_geometry import (
        resolve_matrix_cell,
        resolve_summary_estimate,
        resolve_summary_interval,
    )

    path = Path(report_path).expanduser().resolve()
    report_suffix = ".report.json"
    label = geometry_key.replace("_", " ")
    geometry_id = f"{geometry_key}_geometry_node_id"
    if not path.name.endswith(report_suffix) or not path.is_file():
        raise ValueError(f"Use the {label} render's <stem>.report.json file")
    program = path.with_name(path.name.removesuffix(report_suffix) + ".py")
    directory = Path(run_directory).expanduser().resolve() if run_directory else path.parent
    if not program.resolve().is_relative_to(directory) or not program.is_file():
        raise ValueError("The saved render's generated Python program is missing")
    with path.open("rb") as source:
        raw = source.read(_MAX_BYTES + 1)
    if len(raw) > _MAX_BYTES:
        raise ValueError("Render report exceeds the observation byte budget")
    report = json.loads(raw, object_pairs_hook=_unique_keys)
    if not isinstance(report, dict):
        raise TypeError(f"Use a saved {label} render report")
    selection = report.get("observation_selection")
    if not isinstance(selection, dict) or geometry_id not in selection:
        gap = selection.get(f"{geometry_key}_geometry_gap") if isinstance(selection, dict) else None
        raise ValueError(gap or f"This saved render has no {label} PNG geometry")
    with program.open("rb") as source:
        program_bytes = source.read(_MAX_BYTES + 1)
    if len(program_bytes) > _MAX_BYTES:
        raise ValueError("Generated program exceeds the observation byte budget")
    run_id = selection["run_id"]
    program_sha256 = hashlib.sha256(program_bytes).hexdigest()
    graph_path, graph = _load_observation_selection(
        directory,
        report,
        run_id=run_id,
        program_sha256=program_sha256,
        require_contained_png=True,
    )
    node = graph._nodes[selection[geometry_id]]
    if geometry_key == "matrix":
        target_id = resolve_matrix_cell(node["metadata"], graph._nodes, x, y)
    elif geometry_key == "summary_interval":
        target_id = resolve_summary_interval(node["metadata"], x, y)
    else:
        target_id = resolve_summary_estimate(node["metadata"], x, y)
    return {
        "run_id": run_id,
        "image": copy.deepcopy(node["metadata"]["image"]),
        "program": {"path": str(program), "sha256": program_sha256},
        "observation_selection": {**selection, "path": str(graph_path)},
        "position": [x, y],
        "explanation": graph.explain(target_id) if target_id is not None else None,
    }


def _protect_observation_inputs(directory: Path, inputs, outputs) -> None:
    """Refuse to overwrite data or palette inputs, including existing hard links."""
    for name in inputs:
        if not name or "://" in str(name):
            continue
        source = directory / name
        for output in outputs:
            target = directory / output
            if source.resolve() == target.resolve() or (
                source.exists() and target.exists() and source.samefile(target)
            ):
                raise ValueError(f"Output {target.name} would overwrite an observation input")


def _run_observation_cli(run_cli, stem, inputs, outputs, argv=None) -> int:
    # The canonical renderer still parses and handles all of its own arguments.
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--report", default=f"{stem}.report.json")
    options, _ = parser.parse_known_args(argv)
    try:
        _protect_observation_inputs(Path.cwd(), inputs, [*outputs, options.report])
    except (OSError, ValueError) as problem:
        print(problem, file=sys.stderr)
        return 1
    return run_cli(argv)
