"""Record package source bytes before importing the scientific/compiler modules."""

from __future__ import annotations

import hashlib
import json
from importlib.resources import files


def current() -> dict:
    sources = {}

    def scan(root, prefix=""):
        for child in sorted(root.iterdir(), key=lambda item: item.name):
            name = prefix + child.name
            if getattr(child, "is_symlink", lambda: False)():
                raise ValueError("Package source symlinks cannot establish execution identity.")
            if child.is_dir() and child.name != "__pycache__":
                scan(child, name + "/")
            elif child.is_file() and child.name.rsplit(".", 1)[-1] in {"py", "mjs", "json"}:
                sources[name] = hashlib.sha256(child.read_bytes()).hexdigest()

    scan(files("graphunslopify"))
    raw = json.dumps(sources, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return {"schema_version": 1, "sha256": hashlib.sha256(raw).hexdigest(), "files": sources}


IMPORTED_SOURCES = current()
