"""One-request owned parser worker; user source is data and never executable."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

from .source_parser import Unsupported, convert
from .worker_process import MAX_REQUEST, PROTOCOL

MAX_OUTPUT = 32 * 1024 * 1024


def main():
    print(
        json.dumps(
            {
                "protocol": PROTOCOL,
                "kind": "source-import",
                "pid": os.getpid(),
                "ready": True,
                "adapter_version": 1,
            }
        ),
        flush=True,
    )
    raw = sys.stdin.buffer.readline(MAX_REQUEST + 1)
    if len(raw) > MAX_REQUEST or not raw.endswith(b"\n"):
        return 2
    request = json.loads(raw)
    if request.get("protocol") != PROTOCOL:
        return 2
    identity = request["id"]
    try:
        payload = request["payload"]
        mapped = (
            Path("bound-data.csv").read_text(encoding="utf-8-sig")
            if payload.get("mapped")
            else None
        )
        result = convert(payload["source"], mapped)
        result["report"]["reader"] = {
            "adapter": 1,
            "python": sys.version.split()[0],
            "grammar": "3.10",
            "source_execution": "never",
        }
        path = Path("analysis.json")
        size = 0
        digest = hashlib.sha256()
        with path.open("xb") as stream:
            for chunk in json.JSONEncoder(allow_nan=False, separators=(",", ":")).iterencode(
                result
            ):
                encoded = chunk.encode()
                size += len(encoded)
                if size > MAX_OUTPUT:
                    raise Unsupported("Source import exceeds its output byte budget")
                stream.write(encoded)
                digest.update(encoded)
        reply = {
            "protocol": PROTOCOL,
            "id": identity,
            "ok": True,
            "retire": True,
            "result": {"file": path.name, "bytes": size, "sha256": digest.hexdigest()},
        }
    except Unsupported as problem:
        reply = {
            "protocol": PROTOCOL,
            "id": identity,
            "ok": False,
            "retire": True,
            "error": str(problem),
        }
    except Exception as problem:  # noqa: BLE001 -- source text must not leak through parser exception messages
        reply = {
            "protocol": PROTOCOL,
            "id": identity,
            "ok": False,
            "retire": True,
            "error": "Source parser refused input: " + type(problem).__name__,
        }
    print(json.dumps(reply, allow_nan=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
