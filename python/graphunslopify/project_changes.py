"""Reviewed shared intent and revision-guarded undo; no observations or programs are edited."""

from __future__ import annotations

import copy
import hashlib
import json

from .errors import SpecError
from .project import (
    EVENT,
    MAX_SOURCE_BYTES,
    ProjectError,
    _bytes,
    _capture,
    _commit_shared,
    _config,
    _execution_source,
    _expected,
    _hash,
    _inside,
    _native,
    _operation,
    _review_token,
    _validate_shared,
    project_history,
)
from .project_inspections import project_inspections
from .transport import local_request


def _differences(before, after, path=""):
    if isinstance(before, dict) and isinstance(after, dict):
        result = []
        for key in sorted(before.keys() | after.keys()):
            name = path + "/" + key.replace("~", "~0").replace("/", "~1")
            if key not in before or key not in after:
                result.append(
                    {
                        "path": name,
                        "before_present": key in before,
                        "after_present": key in after,
                        "before": before.get(key),
                        "after": after.get(key),
                    }
                )
            else:
                result.extend(_differences(before[key], after[key], name))
        return result
    return (
        []
        if before == after
        else [
            {
                "path": path,
                "before_present": True,
                "after_present": True,
                "before": before,
                "after": after,
            }
        ]
    )


def _target(source, config, history, shared, undo_event):
    if undo_event is None:
        if not isinstance(shared, dict):
            raise ProjectError("Review a shared settings object or select an undo event.")
        return copy.deepcopy(shared), None
    if shared is not None or not isinstance(undo_event, str) or not EVENT.fullmatch(undo_event):
        raise ProjectError("Choose either shared settings or one saved settings event to undo.")
    event = next((e for e in history["events"] if e["id"] == undo_event), None)
    if not event or not event["integrity"] or event.get("action") != "settings":
        raise ProjectError("Undo requires an intact saved settings event.")
    result = event["result"]
    if result.get("status") != "settings_saved" or result.get("exit_code") != 0:
        raise ProjectError("Only completed settings changes can be undone.")
    entry = next((item for item in event["files"] if item["path"] == "source/project.json"), None)
    if entry is None:
        raise ProjectError("The event has no recorded original configuration to restore.")
    raw = _inside(source.parent, "history/" + undo_event + "/source/project.json").read_bytes()
    if len(raw) != entry["bytes"] or hashlib.sha256(raw).hexdigest() != entry["sha256"]:
        raise ProjectError("Recorded undo configuration changed; restore intact history.")
    old = json.loads(raw)
    if not isinstance(old, dict) or {k: v for k, v in old.items() if k != "shared"} != {
        k: v for k, v in config.items() if k != "shared"
    }:
        raise ProjectError(
            "Project ownership or manifest binding changed; this undo is unavailable."
        )
    if config["shared"] != result.get("snapshot", {}).get("shared"):
        raise ProjectError(
            "Later shared settings conflict with this undo; choose their change instead."
        )
    if old.get("shared") != result.get("before", {}).get("shared"):
        raise ProjectError("Recorded original settings and saved before-snapshot disagree.")
    return old["shared"], raw


def _presentation(entry):
    if "spec" not in entry:
        return None, [], []
    try:
        checked = local_request("validate", entry["spec"])
        errors = [f["message"] for f in checked["findings"] if f["severity"] == "error"]
        resolved = checked["resolved"]
        return (
            {k: resolved[k] for k in ("style", "output", "palette_lock") if k in resolved},
            errors,
            checked["findings"],
        )
    except (OSError, ValueError, KeyError, TypeError, SpecError) as problem:
        return None, [str(problem)], []


def _prepare(path, shared, expected_revision, undo_event):
    _review_token(expected_revision)
    source, config = _config(path)
    _native(config)
    producer = _execution_source()
    before, old_effective, originals = _capture(source, config)
    _expected(expected_revision, before)
    history = project_history(source)
    if history["integrity"] != "verified":
        raise ProjectError("Repair incomplete/damaged history before reviewing shared changes.")
    target, raw = _target(source, config, history, shared, undo_event)
    _validate_shared(target)
    proposed, effective, _ = _capture(source, config, shared_override=target)
    rows = []
    for prior, item, snapshot in zip(
        old_effective["figures"], effective["figures"], proposed["figures"], strict=True
    ):
        old, _, _ = _presentation(prior)
        new, errors, findings = _presentation(item)
        changes = _differences(old or {}, new) if new is not None else []
        script = "script" in item
        rows.append(
            {
                "id": item["id"],
                "source_type": "script" if script else "spec",
                "affected": bool(changes) or (script and target != config["shared"]),
                "changes": changes,
                "before": old,
                "after": new,
                "state": "manual_source_review"
                if script
                else "invalid"
                if errors or snapshot["errors"]
                else "validated_intent",
                "errors": snapshot["errors"] + errors,
                "findings": findings,
                "proposed_inputs": snapshot["files"],
                "reason": "Authored Python is not executed or rewritten. Its reported settings must satisfy this policy at audit."
                if script
                else "Canonical intent validation only; data, claims and final exports are not checked here.",
            }
        )
    pdfs = project_inspections(source)
    if pdfs["native_revision"] != before["revision"]:
        raise ProjectError("Project inputs changed while reviewing shared settings; refresh.")
    content = _bytes({**config, "shared": target}) if raw is None else raw
    plan = {
        "schema_version": 1,
        "project_id": config["project_id"],
        "revision": before["revision"],
        "inspection_revision": pdfs["revision"],
        "history_sha256": _hash(history),
        "execution_source": producer,
        "operation": "undo" if undo_event else "apply",
        "undo_event": undo_event,
        "before_shared": config["shared"],
        "shared": target,
        "target_config_sha256": hashlib.sha256(content).hexdigest(),
        "proposed_snapshot_sha256": _hash(proposed),
        "figures": rows,
        "affected_ids": [r["id"] for r in rows if r["affected"]],
        "pdf_excluded": [
            {
                "id": r["id"],
                "name": r["name"],
                "reason": "Source-free PDFs cannot be restyled; numerical claims remain untested.",
            }
            for r in pdfs["sources"]
        ],
        "can_apply": target != config["shared"] and not any(r["errors"] for r in rows),
        "requires_audit": True,
        "execution": "not_run",
        "exit_code": 0,
        "scope": "Review of canonical shared intent only. All native figures inherit the policy; authored scripts need manual source review. Saving settings does not verify science or produce exports.",
    }
    if len(_bytes(plan)) > MAX_SOURCE_BYTES:
        raise ProjectError("Shared review exceeds the 20 MiB metadata limit.")
    _live(source, config, plan)
    plan["proposal_token"] = _hash(plan)
    # The retained result must also fit the history reader, including both snapshots.
    retained = {
        "status": "settings_saved",
        "exit_code": 0,
        "before": before,
        "snapshot": proposed,
        "audit": None,
        "review": plan,
        "undo_of": undo_event,
    }
    if len(_bytes(retained)) > MAX_SOURCE_BYTES:
        raise ProjectError("Saved shared review exceeds the 20 MiB history limit.")
    return source, config, before, originals, target, raw, plan


def _live(source, config, plan):
    if (
        _capture(source, config)[0]["revision"] != plan["revision"]
        or _hash(_capture(source, config, shared_override=plan["shared"])[0])
        != plan["proposed_snapshot_sha256"]
        or _hash(project_history(source)) != plan["history_sha256"]
        or project_inspections(source)["revision"] != plan["inspection_revision"]
        or _execution_source() != plan["execution_source"]
    ):
        raise ProjectError("Project/inspection/history/producer changed during review; refresh.")


def review_project_shared(path=".", shared=None, *, expected_revision, undo_event=None):
    """Produce a content-bound review without saving settings or history."""
    return _prepare(path, shared, expected_revision, undo_event)[-1]


def apply_project_shared(
    path=".", shared=None, *, expected_revision, proposal_token, undo_event=None
):
    """Recompute a reviewed proposal under the operation lock before changing configuration."""
    _review_token(proposal_token)
    source, _ = _config(path)
    with _operation(source.parent):
        source, config, before, originals, target, raw, plan = _prepare(
            path, shared, expected_revision, undo_event
        )
        if proposal_token != plan["proposal_token"]:
            raise ProjectError("Shared review is stale or differs from this action; review again.")
        if not plan["can_apply"]:
            raise ProjectError("Review contains invalid intent or no shared settings change.")
        _live(source, config, plan)
        return _commit_shared(source, config, before, originals, target, review=plan, raw=raw)
