"""Bind workspace sensitivity review and rendering to the same owned inputs."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock

from .experiment_imports import _contained_bytes
from .sensitivity import _MAX_INPUT_BYTES, run_sensitivity, sensitivity_plan

MAX_REQUEST = 128 * 1024
_MAX_PREVIEW_BYTES = 8 * 1024**2


def owned_input(path, expected, limit=_MAX_INPUT_BYTES):
    """Read an existing owned input and require the captured full digest."""
    path = Path(path)
    raw = _contained_bytes(path.parent, path.name, limit=limit)
    if not raw or hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("A selected sensitivity input changed or is unavailable")
    return raw


class WorkspaceSensitivity:
    def __init__(self):
        self.secret = secrets.token_bytes(32)
        self.rendering = Lock()

    def compare(self, payload, spec, data, palette, *, owner, current, scratch=None):
        mode = payload.get("mode")
        if mode not in ("review", "render"):
            raise ValueError("Review the statistical alternatives before rendering")
        alternatives = payload.get("alternatives")
        plan = sensitivity_plan(spec, alternatives)
        snapshot = {
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
            "format": spec["data"].get("format", "csv"),
            "sheet": spec["data"].get("sheet"),
            "palette_sha256": hashlib.sha256(palette).hexdigest() if palette is not None else None,
        }
        ticket = hmac.digest(
            self.secret,
            json.dumps(
                [owner, spec, snapshot, alternatives], sort_keys=True, allow_nan=False
            ).encode(),
            "sha256",
        ).hex()
        current()
        if mode == "review":
            return {
                "status": "review_required",
                "ticket": ticket,
                "source": snapshot,
                "choices": [
                    {
                        "label": item["label"],
                        "justification": item["justification"],
                        "analysis": {
                            key: item["spec"].get(key)
                            for key in ("kind", "aggregation", "filter", "uncertainty")
                        },
                    }
                    for item in plan
                ],
            }
        supplied = payload.get("ticket")
        if (
            payload.get("reviewed") is not True
            or not isinstance(supplied, str)
            or not supplied.isascii()
            or not hmac.compare_digest(ticket, supplied)
        ):
            raise ValueError(
                "The figure, source or alternatives changed. Review again before rendering."
            )
        if not self.rendering.acquire(blocking=False):
            raise ValueError("A sensitivity comparison is already rendering in this workspace")
        try:
            with TemporaryDirectory(prefix="sensitivity-", dir=scratch) as temporary:
                folder = Path(temporary) / "comparison"
                result = run_sensitivity(
                    spec,
                    alternatives,
                    data=data,
                    palette=palette,
                    destination=folder,
                    reviewed=True,
                )
                remaining = _MAX_PREVIEW_BYTES
                for item in result["choices"]:
                    preview = item.get("preview")
                    if preview is None:
                        continue
                    if preview["bytes"] > remaining:
                        preview["display_error"] = (
                            "This PNG exceeds the remaining 8 MiB workspace preview budget."
                        )
                        continue
                    raw = _contained_bytes(folder, preview["path"], limit=remaining)
                    if (
                        len(raw) != preview["bytes"]
                        or hashlib.sha256(raw).hexdigest() != preview["sha256"]
                    ):
                        raise ValueError("A checked sensitivity preview changed")
                    preview["data_url"] = "data:image/png;base64," + base64.b64encode(raw).decode()
                    remaining -= len(raw)
            current()
            return result
        finally:
            self.rendering.release()
