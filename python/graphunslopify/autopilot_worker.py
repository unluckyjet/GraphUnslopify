"""One owned reader request for question-grounded figure proposals."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

from .autopilot_plan import make_plan
from .worker_process import MAX_REQUEST, PROTOCOL


def main():
    print(
        json.dumps(
            {
                "protocol": PROTOCOL,
                "kind": "figure-autopilot",
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
    try:
        payload = request["payload"]
        name = payload["filename"]
        if Path(name).name != name:
            raise ValueError("Invalid owned dataset filename")
        result = make_plan(Path(name), payload["question"], payload["choices"])
        import pandas as pd

        result["report"]["reader"] = {
            "python": sys.version.split()[0],
            "pandas": pd.__version__,
            "adapter": 1,
        }
        encoded = json.dumps(result, ensure_ascii=False, allow_nan=False).encode()
        if len(encoded) > 32 * 1024 * 1024:
            raise ValueError("Autopilot proposal exceeds32MiB")
        Path("proposal.json").write_bytes(encoded)
        reply = {
            "ok": True,
            "result": {
                "file": "proposal.json",
                "bytes": len(encoded),
                "sha256": hashlib.sha256(encoded).hexdigest(),
            },
        }
    except ValueError as problem:
        # These are explicit adapter refusals; generic parser exceptions disclose only their type.
        reply = {"ok": False, "error": "Autopilot data/choice refusal: " + str(problem)}
    except Exception as problem:  # noqa: BLE001 -- do not disclose private table contents
        reply = {"ok": False, "error": "Autopilot reader refused input: " + type(problem).__name__}
    print(
        json.dumps({"protocol": PROTOCOL, "id": request["id"], "retire": True, **reply}), flush=True
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
