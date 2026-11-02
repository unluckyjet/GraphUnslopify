"""Actual native CI dispatch with a literal mode and optional compact qualified seal."""

from __future__ import annotations

import argparse
import json
import os
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    mode = os.environ.get("WORKSPACE_STUDY_MODE", "preseal")
    raw = os.environ.get("WORKSPACE_STUDY_SEAL", "")
    if mode not in {"preseal", "formal"} or (mode == "formal") != bool(raw):
        parser.error(
            "Use preparation without a seal or formal mode with a qualified seal"
        )
    study = runpy.run_path(str(ROOT / "benchmarks/workspace/study_runner.py"))
    candidate = None
    if raw:
        candidate = args.out.with_name(args.out.name + ".requested-seal.json")
        candidate.parent.mkdir(parents=True, exist_ok=True)
        with candidate.open("x", encoding="utf8") as stream:
            stream.write(raw)
    result = study["run"](
        "native_ci",
        args.out,
        mode=mode,
        seal_path=candidate,
        native_profile=args.profile,
        expected_revision=args.expected_sha,
    )
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "track",
                    "mode",
                    "planned_cells",
                    "retained_cells",
                    "complete",
                    "errors",
                )
            }
        )
    )
    raise SystemExit(0 if result["complete"] else 1)


if __name__ == "__main__":
    main()
