"""Keep explicitly accepted research wording separate from figure definitions."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from .experiment_imports import _contained_bytes
from .project import ProjectError, _atomic, _bytes, _config, _hash, _inside, _operation

_FILE = "research-intent.json"
_CATEGORIES = ("terminology", "model_names", "units", "figure_conventions")
_MAX_ENTRIES = 64
_MAX_BYTES = 2 * 1024**2


def _text(value, limit):
    return (
        isinstance(value, str)
        and 0 < len(value) <= limit
        and value == value.strip()
        and value.isprintable()
    )


def _validate_changes(changes):
    if not isinstance(changes, dict) or not changes or changes.keys() - _CATEGORIES:
        raise ProjectError("Choose terminology, model_names, units or figure_conventions.")
    for category, entries in changes.items():
        if not isinstance(entries, dict) or not 0 < len(entries) <= _MAX_ENTRIES:
            raise ProjectError(f"Supply between 1 and {_MAX_ENTRIES} changes for {category}.")
        for name, value in entries.items():
            if not _text(name, 100) or (value is not None and not _text(value, 300)):
                raise ProjectError(
                    "Use printable names up to 100 characters and values up to 300. "
                    "Use null to forget an accepted value."
                )


def _apply(entries, changes):
    updated = {category: dict(values) for category, values in entries.items()}
    delta = []
    for category, patch in sorted(changes.items()):
        values = updated[category]
        for name, value in sorted(patch.items()):
            before = values.get(name)
            if before != value:
                delta.append({"category": category, "name": name, "before": before, "after": value})
                if value is None:
                    del values[name]
                else:
                    values[name] = value
        if len(values) > _MAX_ENTRIES:
            raise ProjectError(f"Keep at most {_MAX_ENTRIES} accepted entries in {category}.")
    return updated, delta


def _read_ledger(folder, project_id):
    header = {"schema_version": 1, "project_id": project_id}
    path = _inside(folder, _FILE)
    ledger = {**header, "history": []}
    if path.exists():
        raw = _contained_bytes(folder, _FILE, limit=_MAX_BYTES)
        if len(raw) > _MAX_BYTES:
            raise ProjectError("Research intent history exceeds the 2 MiB limit.")
        ledger = json.loads(raw)
    if (
        not isinstance(ledger, dict)
        or ledger.keys() != {*header, "history"}
        or any(ledger[key] != value for key, value in header.items())
        or not isinstance(ledger["history"], list)
    ):
        raise ProjectError("Research intent history is invalid or belongs to another project.")

    revision = _hash({"kind": "graphunslopify.research-intent", **header})
    entries = {category: {} for category in _CATEGORIES}
    for event in ledger["history"]:
        if (
            not isinstance(event, dict)
            or event.keys() != {"parent_revision", "revision", "accepted_at", "changes"}
            or event["parent_revision"] != revision
            or not _text(event["accepted_at"], 40)
        ):
            raise ProjectError("Research intent history contains an invalid revision.")
        body = {key: value for key, value in event.items() if key != "revision"}
        revision = _hash(body)
        if event["revision"] != revision:
            raise ProjectError(
                "Research intent history changed outside the accepted revision chain."
            )
        _validate_changes(event["changes"])
        entries, delta = _apply(entries, event["changes"])
        if len(delta) != sum(map(len, event["changes"].values())):
            raise ProjectError("Research intent history contains an unchanged value.")
    return ledger, entries, revision


def project_intent(path="."):
    """Read current accepted intent and its local acceptance history."""
    source, config = _config(path)
    ledger, entries, revision = _read_ledger(source.parent, config["project_id"])
    return {**ledger, "revision": revision, "entries": entries}


def _proposal(state, changes, expected_revision):
    if expected_revision != state["revision"]:
        raise ProjectError("Research intent changed. Refresh the current memory before reviewing.")
    _validate_changes(changes)
    entries, delta = _apply(state["entries"], changes)
    if not delta:
        raise ProjectError("The proposed changes match the accepted research intent.")
    review = {
        "project_id": state["project_id"],
        "parent_revision": expected_revision,
        "changes": delta,
    }
    return {**review, "review_sha256": _hash(review), "resulting_entries": entries}


def review_project_intent(path, changes, *, expected_revision):
    """Describe the exact additions, replacements and removals before acceptance."""
    return _proposal(project_intent(path), changes, expected_revision)


def accept_project_intent(path, changes, *, expected_revision, review_sha256):
    """Atomically append the exact reviewed changes without modifying figures."""
    source, config = _config(path)
    with _operation(source.parent):
        ledger, entries, revision = _read_ledger(source.parent, config["project_id"])
        state = {**ledger, "entries": entries, "revision": revision}
        review = _proposal(state, changes, expected_revision)
        if review_sha256 != review["review_sha256"]:
            raise ProjectError("Accept only the exact research intent changes you reviewed.")
        effective = {}
        for row in review["changes"]:
            effective.setdefault(row["category"], {})[row["name"]] = row["after"]
        event = {
            "parent_revision": revision,
            "accepted_at": datetime.now(timezone.utc).isoformat(),
            "changes": effective,
        }
        revision = _hash(event)
        updated = {**ledger, "history": [*ledger["history"], {**event, "revision": revision}]}
        if len(_bytes(updated)) > _MAX_BYTES:
            raise ProjectError("Research intent history would exceed the 2 MiB limit.")
        _atomic(source.parent, _FILE, updated)
        return {**updated, "entries": review["resulting_entries"], "revision": revision}
