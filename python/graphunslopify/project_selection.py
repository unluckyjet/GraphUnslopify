"""Reviewed presentation changes for selected JSON figures, with one owned write."""

from __future__ import annotations

import copy
import hashlib
import json

from .project import (
    EVENT,
    MAX_SOURCE_BYTES,
    ProjectError,
    _bytes,
    _capture,
    _config,
    _event,
    _execution_source,
    _expected,
    _finish,
    _hash,
    _inside,
    _native,
    _operation,
    _review_token,
    _validate_figure_settings,
    _write_authoring,
    project_history,
)
from .project_changes import _differences, _presentation
from .project_inspections import project_inspections


def _prepare(path, ids, settings, expected_revision, reset, undo_event):
    _review_token(expected_revision)
    if type(reset) is not bool:
        raise ProjectError("Reset selection must be true or false.")
    source, config = _config(path)
    _native(config)
    producer = _execution_source()
    before, old_effective, originals = _capture(source, config)
    _expected(expected_revision, before)
    history = project_history(source)
    if history["integrity"] != "verified":
        raise ProjectError("Repair incomplete/damaged history before reviewing selected changes.")
    pdfs = project_inspections(source)
    if pdfs["native_revision"] != before["revision"]:
        raise ProjectError("Project inputs changed during selection review; refresh.")
    current = config.get("figure_settings", {})
    target = copy.deepcopy(current)
    raw = None
    if undo_event is not None:
        if (
            ids is not None
            or settings is not None
            or reset
            or not isinstance(undo_event, str)
            or not EVENT.fullmatch(undo_event)
        ):
            raise ProjectError("Choose a selection change or one saved selection event to undo.")
        event = next((e for e in history["events"] if e["id"] == undo_event), None)
        if (
            not event
            or not event["integrity"]
            or event.get("action") != "selection"
            or event["result"].get("status") != "selection_saved"
        ):
            raise ProjectError("Undo requires an intact completed selection event.")
        if current != event["result"].get("snapshot", {}).get("figure_settings", {}):
            raise ProjectError("Later selected settings conflict with this undo.")
        raw = _inside(source.parent, "history/" + undo_event + "/source/project.json").read_bytes()
        old = json.loads(raw)
        ignore = {"schema_version", "figure_settings"}
        if {k: v for k, v in old.items() if k not in ignore} != {
            k: v for k, v in config.items() if k not in ignore
        }:
            raise ProjectError(
                "Other project settings or ownership changed; this undo is unavailable."
            )
        target = old.get("figure_settings", {})
        if target != event["result"].get("before", {}).get("figure_settings", {}):
            raise ProjectError("Recorded selection settings and original configuration disagree.")
        ids = sorted(k for k in current.keys() | target.keys() if current.get(k) != target.get(k))
    else:
        if (
            not isinstance(ids, list)
            or not 1 <= len(ids) <= 1000
            or any(not isinstance(i, str) for i in ids)
            or len(set(ids)) != len(ids)
        ):
            raise ProjectError("Choose 1-1000 distinct figure IDs.")
        if reset:
            if settings is not None:
                raise ProjectError("Choose new settings or reset to paper defaults.")
        else:
            _validate_figure_settings({"candidate": settings})
            if not any(settings.values()):
                raise ProjectError("Choose at least one presentation setting.")
    ids = sorted(ids)
    entries = {e["id"]: e for e in old_effective["figures"]}
    pdf_ids = {"pdf:" + r["id"] for r in pdfs["sources"]}
    if any(i not in entries and i not in pdf_ids for i in ids):
        raise ProjectError("A selected figure is no longer available; refresh the selection.")
    excluded, eligible = [], []
    for identity in ids:
        if identity in pdf_ids:
            excluded.append(
                {
                    "id": identity,
                    "reason": "PDF visual evidence has no editable source; numerical claims remain untested.",
                }
            )
        elif "spec" not in entries[identity]:
            excluded.append(
                {
                    "id": identity,
                    "reason": "Authored Python stays unchanged; edit and audit its trusted source separately.",
                }
            )
        else:
            eligible.append(identity)
            if undo_event is None:
                if reset:
                    target.pop(identity, None)
                else:
                    row = target.setdefault(identity, {})
                    for key, value in settings.items():
                        row[key] = {**row.get(key, {}), **value}
    _validate_figure_settings(target)
    proposed, effective, _ = _capture(source, config, figure_settings_override=target)
    after = {e["id"]: e for e in effective["figures"]}
    snapshots = {r["id"]: r for r in proposed["figures"]}
    rows = []
    for identity in eligible:
        old, _, _ = _presentation(entries[identity])
        new, errors, findings = _presentation(after[identity])
        rows.append(
            {
                "id": identity,
                "before": old,
                "after": new,
                "changes": _differences(old or {}, new or {}),
                "errors": snapshots[identity]["errors"] + errors,
                "findings": findings,
            }
        )
    updated = (
        {**config, "schema_version": 3, "figure_settings": target}
        if raw is None
        else json.loads(raw)
    )
    content = _bytes(updated) if raw is None else raw
    plan = {
        "schema_version": 1,
        "project_id": config["project_id"],
        "revision": before["revision"],
        "inspection_revision": pdfs["revision"],
        "history_sha256": _hash(history),
        "execution_source": producer,
        "operation": "undo" if undo_event else "reset" if reset else "apply",
        "undo_event": undo_event,
        "ids": ids,
        "settings": settings,
        "reset": reset,
        "before_settings": current,
        "figure_settings": target,
        "target_config_sha256": hashlib.sha256(content).hexdigest(),
        "proposed_snapshot_sha256": _hash(proposed),
        "figures": rows,
        "excluded": excluded,
        "affected_ids": [i for i in eligible if current.get(i) != target.get(i)],
        "can_apply": bool(eligible) and target != current and not any(r["errors"] for r in rows),
        "execution": "not_run",
        "requires_audit": True,
        "exit_code": 0,
        "scope": "Selected presentation overrides paper defaults. Data, claims, source definitions and bindings remain unchanged. Review intent, then audit saved outputs.",
    }
    plan["proposal_token"] = _hash(plan)
    retained = {
        "status": "selection_saved",
        "exit_code": 0,
        "before": before,
        "snapshot": proposed,
        "audit": None,
        "review": plan,
        "undo_of": undo_event,
    }
    if max(len(content), len(_bytes(retained))) > MAX_SOURCE_BYTES:
        raise ProjectError("Selected changes exceed the 20 MiB metadata limit.")
    _live(source, config, plan)
    return source, config, before, originals, content, plan


def _live(source, config, plan):
    if (
        _capture(source, config)[0]["revision"] != plan["revision"]
        or _hash(_capture(source, config, figure_settings_override=plan["figure_settings"])[0])
        != plan["proposed_snapshot_sha256"]
        or _hash(project_history(source)) != plan["history_sha256"]
        or project_inspections(source)["revision"] != plan["inspection_revision"]
        or _execution_source() != plan["execution_source"]
    ):
        raise ProjectError(
            "Project/inspection/history/producer changed during selection review; refresh."
        )


def review_project_selection(
    path=".", ids=None, settings=None, *, expected_revision, reset=False, undo_event=None
):
    """Resolve selected intent without changing files or executing figures."""
    return _prepare(path, ids, settings, expected_revision, reset, undo_event)[-1]


def apply_project_selection(
    path=".",
    ids=None,
    settings=None,
    *,
    expected_revision,
    proposal_token,
    reset=False,
    undo_event=None,
):
    """Recompute the proposal under the project lock, then save a single owned config."""
    _review_token(proposal_token)
    source, _ = _config(path)
    with _operation(source.parent):
        source, config, before, originals, content, plan = _prepare(
            path, ids, settings, expected_revision, reset, undo_event
        )
        if proposal_token != plan["proposal_token"] or not plan["can_apply"]:
            raise ProjectError("Selection review is stale, invalid or unchanged; review again.")
        _live(source, config, plan)
        folder, event = _event(source.parent, "selection")
        _write_authoring(
            source.parent,
            source,
            content,
            hashlib.sha256(originals["source/project.json"]).hexdigest(),
        )
        after, _, _ = _capture(source, json.loads(content))
        return _finish(
            folder,
            event,
            {
                "status": "selection_saved",
                "exit_code": 0,
                "before": before,
                "snapshot": after,
                "audit": None,
                "review": plan,
                "undo_of": undo_event,
            },
            originals,
        )
