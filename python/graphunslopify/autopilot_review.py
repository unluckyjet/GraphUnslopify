"""Saved local proposal reviews;generation rechecks the actual source and every reviewed field."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from .autopilot import AutopilotError, _snapshot, generate_drafts, propose_figures
from .experiment_imports import _contained_bytes

MAX_REVIEW = 32 * 1024 * 1024


def _fingerprint(document):
    try:
        raw = json.dumps(
            {k: v for k, v in document.items() if k != "fingerprint"},
            sort_keys=True,
            allow_nan=False,
            ensure_ascii=False,
        ).encode("utf8")
    except (TypeError, ValueError, RecursionError) as problem:
        raise AutopilotError("Review must contain finite, bounded JSON values") from problem
    if len(raw) > MAX_REVIEW:
        raise AutopilotError("Proposal review exceeds32MiB")
    return hashlib.sha256(raw).hexdigest()


def review_document(plan):
    """Save the actual review without copying source observations into a second input."""
    document = {
        "schema_version": 1,
        "request": {
            "source": str(plan.source),
            "question": plan.report["question"],
            "choices": copy.deepcopy(plan.report["requested_choices"]),
        },
        "report": copy.deepcopy(plan.report),
        "drafts": copy.deepcopy(plan.drafts),
    }
    document["fingerprint"] = _fingerprint(document)
    _validate(document)
    return document


def _validate(document):
    if not isinstance(document, dict) or set(document) != {
        "schema_version",
        "request",
        "report",
        "drafts",
        "fingerprint",
    }:
        raise AutopilotError("Choose an exported autopilot proposal review")
    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        raise AutopilotError("Unsupported proposal review version")
    request = document["request"]
    if (
        not isinstance(request, dict)
        or set(request) != {"source", "question", "choices"}
        or not isinstance(request["source"], str)
        or not 1 <= len(request["source"]) <= 4096
        or not isinstance(request["question"], str)
        or not isinstance(request["choices"], dict)
        or not isinstance(document["report"], dict)
        or not isinstance(document["drafts"], list)
    ):
        raise AutopilotError("Invalid proposal review request or report")
    if document["fingerprint"] != _fingerprint(document):
        raise AutopilotError("Proposal review changed; create and review a fresh proposal")
    if _snapshot(document["report"], document["drafts"]) != document["report"].get("snapshot"):
        raise AutopilotError("Reviewed metadata or drafts changed; review a fresh proposal")


def write_review(document, path):
    _validate(document)
    encoded = (json.dumps(document, indent=2, allow_nan=False, ensure_ascii=False) + "\n").encode()
    if len(encoded) > MAX_REVIEW:
        raise AutopilotError("Proposal review exceeds32MiB")
    target = Path(path).expanduser().absolute()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(encoded)


def read_review(path):
    source = Path(path).expanduser().resolve(strict=True)
    raw = _contained_bytes(source.parent, source.name, limit=MAX_REVIEW)
    if len(raw) > MAX_REVIEW:
        raise AutopilotError("Proposal review exceeds32MiB")
    try:
        document = json.loads(raw)
    except (ValueError, RecursionError) as problem:
        raise AutopilotError("Choose a valid JSON proposal review") from problem
    _validate(document)
    return document


def generate_reviewed(document, destination, *, reviewed=False, accept_exclusions=False):
    if reviewed is not True:
        raise AutopilotError("Review the saved question,mapping,exclusions and assumptions first")
    _validate(document)
    request = document["request"]
    plan = propose_figures(request["source"], request["question"], **request["choices"])
    if plan.report != document["report"] or plan.drafts != document["drafts"]:
        raise AutopilotError("Dataset,reader or reviewed choices changed; create a fresh review")
    result = generate_drafts(plan, destination, reviewed=True, accept_exclusions=accept_exclusions)
    root = Path(destination).expanduser().resolve()
    write_review(document, root / "reviewed-proposal.json")
    result["review"] = {
        "document": "reviewed-proposal.json",
        "fingerprint": document["fingerprint"],
        "acknowledged": True,
        "exclusions_acknowledged": accept_exclusions is True,
    }
    (root / "autopilot.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    return result
