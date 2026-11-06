"""Local reviewer threads bound to the bytes of an audited figure export."""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from uuid import uuid4

from PIL import Image

from .comparison import _size, _verified_bytes
from .project import ProjectError, _atomic, _bytes, _hash, _inside, _operation, _read

_FILE = "figure-comments.json"
_LIMIT = 2 * 1024 * 1024


def _anchor(state, event_id, figure_id):
    event = state.event(event_id)
    figure = state.audited(event, figure_id)
    selected = next(
        ((index, item) for index, item in enumerate(figure["outputs"]) if item["format"] == "png"),
        None,
    )
    if selected is None:
        raise ProjectError("Save an audited PNG to attach figure comments.")
    index, item = selected
    root = state.audit_root(event)
    _inside(root, item["path"])
    data = _verified_bytes(item, [root])
    try:
        with Image.open(BytesIO(data)) as image:
            if image.format != "PNG" or getattr(image, "n_frames", 1) != 1:
                raise ProjectError("Choose a saved static PNG for figure comments.")
            width, height = image.size
            _size(width, height)
            image.verify()
    except (Image.DecompressionBombError, SyntaxError) as problem:
        raise ProjectError("The saved PNG cannot be verified for comments.") from problem
    return {
        "event": event["id"],
        "figure": figure["id"],
        "index": index,
        "sha256": item["sha256"],
        "width": width,
        "height": height,
    }


def _view(state, event_id, figure_id):
    anchor = _anchor(state, event_id, figure_id)
    key = _hash(anchor)
    path = _inside(state.source.parent, _FILE)
    identity = {"schema_version": 1, "project_id": state.project_id}
    store = {**identity, "figures": {}}
    if path.exists():
        if path.stat().st_size > _LIMIT:
            raise ProjectError("The figure comment store exceeds 2 MiB.")
        store = _read(path)
        if (
            not isinstance(store, dict)
            or any(store.get(name) != value for name, value in identity.items())
            or not isinstance(store.get("figures"), dict)
        ):
            raise ProjectError("The figure comment store is invalid or belongs to another project.")
    entry = store["figures"].get(key, {"anchor": anchor, "threads": []})
    if (
        not isinstance(entry, dict)
        or entry.get("anchor") != anchor
        or not isinstance(entry.get("threads"), list)
        or any(not isinstance(thread, dict) for thread in entry["threads"])
    ):
        raise ProjectError("Stored comments do not match this figure revision.")
    return store, key, entry


def _response(key, entry):
    return {**entry, "anchor_key": key, "revision": _hash(entry)}


def _text(payload, field, limit):
    value = payload.get(field)
    if not isinstance(value, str) or not 0 < len(value.strip()) <= limit:
        raise ProjectError(f"Enter {field} using 1 to {limit} characters.")
    return value.strip()


def read_figure_comments(state, event_id, figure_id):
    _, key, entry = _view(state, event_id, figure_id)
    return _response(key, entry)


def change_figure_comments(state, payload):
    with state.job_lock, _operation(state.source.parent):
        if state.closing or (state.job and state.job["phase"] == "running"):
            raise ProjectError("Wait for the active project job before changing comments.")
        store, key, entry = _view(state, payload.get("event"), payload.get("figure"))
        if payload.get("anchor_key") != key or payload.get("expected_revision") != _hash(entry):
            raise ProjectError(
                "Figure evidence or comments changed. Reload comments before saving."
            )
        operation = payload.get("operation")
        if operation not in ("create", "reply", "resolve", "reopen"):
            raise ProjectError("Choose a supported figure comment action.")
        author = _text(payload, "author", 80)
        at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        threads = entry["threads"]
        if operation == "create":
            if len(threads) >= 200:
                raise ProjectError("This saved figure has reached its 200 comment limit.")
            x, y = payload.get("x"), payload.get("y")
            anchor = entry["anchor"]
            if (
                type(x) is not int
                or type(y) is not int
                or not 0 <= x < anchor["width"]
                or not 0 <= y < anchor["height"]
            ):
                raise ProjectError("Choose a pixel inside this saved figure.")
            threads.append(
                {
                    "id": uuid4().hex,
                    "x": x,
                    "y": y,
                    "author": author,
                    "body": _text(payload, "body", 2000),
                    "at": at,
                    "replies": [],
                    "status_history": [],
                }
            )
        else:
            thread = next((row for row in threads if row.get("id") == payload.get("thread")), None)
            if thread is None:
                raise ProjectError("Choose a comment on this figure revision.")
            status = thread["status_history"]
            resolved = bool(status and status[-1]["resolved"])
            if operation == "reply" and not resolved:
                if len(thread["replies"]) >= 100:
                    raise ProjectError("This comment has reached its 100 reply limit.")
                thread["replies"].append(
                    {"author": author, "body": _text(payload, "body", 2000), "at": at}
                )
            elif (operation, resolved) in {("resolve", False), ("reopen", True)}:
                if len(status) >= 100:
                    raise ProjectError("This comment has reached its 100 status change limit.")
                status.append({"resolved": not resolved, "author": author, "at": at})
            else:
                raise ProjectError("Choose an available reply, resolve or reopen action.")
        store["figures"][key] = entry
        if len(_bytes(store)) > _LIMIT:
            raise ProjectError("The figure comment store is full.")
        _atomic(state.source.parent, _FILE, store)
        return _response(key, entry)
