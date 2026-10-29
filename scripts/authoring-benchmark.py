"""Run a preflight or prospectively record a familiarized authoring episode."""

from __future__ import annotations

import argparse
import json
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir", type=Path, default=ROOT / "benchmarks/certified/.cache/sources"
    )
    parser.add_argument(
        "--prepared-dir",
        type=Path,
        default=ROOT / "benchmarks/certified/.cache/prepared",
    )
    parser.add_argument(
        "--journal", type=Path, default=ROOT / "benchmarks/authoring/sessions.jsonl"
    )
    parser.add_argument("--out-dir", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--begin", action="store_true")
    mode.add_argument("--attempt", action="store_true")
    mode.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    session = runpy.run_path(str(ROOT / "benchmarks/authoring/session.py"))
    try:
        if args.begin:
            result = session["begin"](
                ROOT,
                args.journal.resolve(),
                args.source_dir.resolve(),
                args.prepared_dir.resolve(),
            )
        else:
            if not args.out_dir:
                parser.error("--out-dir is required for an attempt or preflight")
            common = (
                ROOT,
                args.out_dir.resolve(),
                args.source_dir.resolve(),
                args.prepared_dir.resolve(),
            )
            result = (
                session["attempt"](ROOT, args.journal.resolve(), *common[1:])
                if args.attempt
                else session["preflight"](*common)
            )
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0 if result.get("passed", True) else 2
    except (OSError, ValueError, KeyError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
