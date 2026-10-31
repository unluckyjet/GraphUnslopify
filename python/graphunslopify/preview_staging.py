"""Owned, image-only progress for an otherwise unchanged strict render."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

VERSION = 1
MAX_IMAGE_BYTES = 16 * 1024 * 1024
MAX_RECORDS = 64


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def stage_paths(png: Path) -> tuple[Path, Path]:
    return png.with_name(f".{png.stem}.provisional.png"), png.with_name(
        f".{png.stem}.provisional.json"
    )


def publish_png(png: Path, script: Path) -> None:
    """Copy the PNG that was actually saved; never redraw or certify it."""
    from PIL import Image

    if png.is_symlink() or not 0 < png.stat().st_size <= MAX_IMAGE_BYTES:
        raise ValueError("Provisional image exceeds its supported bounds")
    raw = png.read_bytes()
    with Image.open(png) as image:
        if image.format != "PNG":
            raise ValueError("Provisional image must be the actual PNG")
        width, height = image.size
        provenance = json.loads(image.info.get("GraphUnslopify", "null"))
    if not isinstance(provenance, dict) or provenance.get("script_sha256") != _sha(
        script.read_bytes()
    ):
        raise ValueError("Provisional PNG has no matching script provenance")
    target, marker = stage_paths(png)
    temporary = target.with_suffix(".tmp")
    temporary.write_bytes(raw)
    temporary.replace(target)
    value = {
        "version": VERSION,
        "verified": False,
        "producer_pid": os.getpid(),
        "script_sha256": provenance["script_sha256"],
        "spec_hash": provenance.get("spec_hash"),
        "data_sha256_prefix": provenance.get("data_sha256_prefix"),
        "image": {
            "sha256": _sha(raw),
            "bytes": len(raw),
            "width": width,
            "height": height,
        },
    }
    temporary = marker.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, allow_nan=False), encoding="utf8")
    temporary.replace(marker)


@dataclass
class Attempt:
    client: str
    generation: int
    ticket: str | None
    identity: str
    folder: Path | None = None
    stem: str | None = None
    script_sha256: str | None = None
    data_sha256: str | None = None
    data_id: str | None = None
    finished: bool = False


class PreviewStages:
    def __init__(self, root: Path, *, max_records: int = MAX_RECORDS):
        self.runs = (root / "runs").resolve()
        self.max_records = max_records
        self.lock = threading.RLock()
        self.closed = threading.Event()
        self.records: OrderedDict[str, Attempt] = OrderedDict()
        self.current: OrderedDict[str, tuple[int, str]] = OrderedDict()

    def begin(self, client: str, generation: int, ticket: Any) -> Attempt:
        if ticket is not None and (
            not isinstance(ticket, str) or not re.fullmatch("[0-9a-f]{32}", ticket)
        ):
            raise ValueError("Invalid provisional preview ticket")
        with self.lock:
            if self.closed.is_set():
                raise ValueError("This preview session is closed")
            if ticket in self.records:
                raise ValueError("Provisional preview ticket was already used")
            if ticket is not None:
                for key, record in list(self.records.items()):
                    if len(self.records) < self.max_records:
                        break
                    if record.finished or not self._current(record):
                        self.records.pop(key)
                if len(self.records) >= self.max_records:
                    raise ValueError("Too many renders are pending; wait for a current result")
            record = Attempt(client, generation, ticket, uuid.uuid4().hex)
            previous = self.current.get(client)
            if previous is None or generation >= previous[0]:
                self.current[client] = (generation, record.identity)
                self.current.move_to_end(client)
                while len(self.current) > self.max_records * 2:
                    self.current.popitem(last=False)
            if ticket is not None:
                self.records[ticket] = record
            return record

    def _current(self, record: Attempt) -> bool:
        return not self.closed.is_set() and self.current.get(record.client) == (
            record.generation,
            record.identity,
        )

    def is_current(self, record: Attempt) -> bool:
        with self.lock:
            return self._current(record)

    def bind(self, record: Attempt, folder: Path, stem: str, data_id: str, data: Path):
        if folder.is_symlink() or Path(stem).name != stem or stem in {".", ".."}:
            raise ValueError("Provisional image escapes its owned run")
        folder = folder.resolve()
        if folder.parent != self.runs or not folder.is_dir():
            raise ValueError("Provisional image escapes its owned run")
        with self.lock:
            record.folder, record.stem, record.data_id = folder, stem, data_id
            record.script_sha256 = _sha((folder / f"{stem}.py").read_bytes())
            record.data_sha256 = _sha(data.read_bytes())

    def finish(self, record: Attempt):
        with self.lock:
            record.finished = True

    def close(self):
        self.closed.set()

    def _lookup(self, ticket: str, client: str, generation: int) -> Attempt:
        with self.lock:
            record = self.records.get(ticket)
            if record is None or (record.client, record.generation) != (client, generation):
                raise ValueError("This provisional preview is unavailable")
            return record

    def _image(self, record: Attempt) -> tuple[dict[str, Any], bytes] | None:
        if record.folder is None or record.stem is None:
            return None
        png, marker = stage_paths(record.folder / f"{record.stem}.png")
        if not marker.exists():
            return None
        if (
            png.is_symlink()
            or marker.is_symlink()
            or marker.stat().st_size > 4096
            or not 0 < png.stat().st_size <= MAX_IMAGE_BYTES
        ):
            raise ValueError("Provisional image ownership or bounds changed")
        value = json.loads(marker.read_text(encoding="utf8"))
        raw = png.read_bytes()
        if (
            not isinstance(value, dict)
            or set(value)
            != {
                "version",
                "verified",
                "producer_pid",
                "script_sha256",
                "spec_hash",
                "data_sha256_prefix",
                "image",
            }
            or value.get("version") != VERSION
            or value.get("verified") is not False
            or value.get("script_sha256") != record.script_sha256
            or value.get("data_sha256_prefix") != record.data_sha256[:16]
            or not isinstance(value.get("image"), dict)
            or set(value["image"]) != {"sha256", "bytes", "width", "height"}
            or type(value.get("producer_pid")) is not int
            or value["producer_pid"] <= 0
            or any(
                type(value["image"].get(k)) is not int or value["image"][k] <= 0
                for k in ("width", "height", "bytes")
            )
            or value["image"].get("sha256") != _sha(raw)
            or value["image"].get("bytes") != len(raw)
        ):
            raise ValueError("Provisional PNG does not match the current producer")
        from PIL import Image

        with Image.open(BytesIO(raw)) as image:
            provenance = json.loads(image.info.get("GraphUnslopify", "null"))
            if (
                image.format != "PNG"
                or image.size != (value["image"]["width"], value["image"]["height"])
                or not isinstance(provenance, dict)
                or any(
                    provenance.get(k) != value[k]
                    for k in ("script_sha256", "spec_hash", "data_sha256_prefix")
                )
            ):
                raise ValueError("Provisional metadata differs from its actual PNG")
        return value, raw

    def poll(self, ticket: str, client: str, generation: int, *, wait: bool = True):
        record = self._lookup(ticket, client, generation)
        answer = {"ticket": ticket, "generation": generation, "verified": False}
        deadline = time.monotonic() + (0.2 if wait else 0)
        while True:
            if not self.is_current(record):
                return {**answer, "phase": "stale"}
            try:
                image = self._image(record)
            except (OSError, ValueError, KeyError, TypeError) as problem:
                return {**answer, "phase": "unavailable", "error": str(problem)}
            if image is not None:
                value, _ = image
                if not self.is_current(record):
                    return {**answer, "phase": "stale"}
                return {
                    **answer,
                    "phase": "unverified",
                    "attempt": record.identity,
                    "data_id": record.data_id,
                    "data_sha256": record.data_sha256,
                    **value,
                }
            if record.finished:
                return {**answer, "phase": "unavailable"}
            if time.monotonic() >= deadline:
                return {**answer, "phase": "pending"}
            self.closed.wait(0.005)

    def image(self, ticket: str, client: str, generation: int, identity: str) -> bytes:
        record = self._lookup(ticket, client, generation)
        if record.identity != identity or not self.is_current(record):
            raise ValueError("This provisional preview is stale")
        value = self._image(record)
        if value is None or not self.is_current(record):
            raise ValueError("This provisional preview is unavailable")
        return value[1]
