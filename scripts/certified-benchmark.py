"""Run the frozen complete NIST comparison or record live producer-implementation sessions."""

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
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument(
        "--journal",
        type=Path,
        default=ROOT / "benchmarks/certified/development-sessions.jsonl",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--begin-development", choices=["matplotlib", "graphunslopify"])
    mode.add_argument("--development", choices=["matplotlib", "graphunslopify"])
    args = parser.parse_args()
    runner = runpy.run_path(str(ROOT / "benchmarks/certified/runner.py"))
    try:
        if args.begin_development:
            runner["load_inputs"](
                ROOT, args.source_dir.resolve(), args.prepared_dir.resolve()
            )
            result = runner["begin_session"](
                ROOT, args.begin_development, args.journal.resolve()
            )
        else:
            if args.out_dir is None:
                parser.error("--out-dir is required for verification or benchmark runs")
            report = runner["run"](
                ROOT,
                args.source_dir.resolve(),
                args.prepared_dir.resolve(),
                args.out_dir.resolve(),
                development_arm=args.development,
                journal=args.journal.resolve(),
            )
            result = {
                k: report[k]
                for k in ["phase", "passed", "runs", "expected_runs", "completed_at"]
            }
            print(json.dumps(result, indent=2))
            return 0 if report["passed"] else 2
    except (OSError, ValueError, KeyError) as problem:
        print(json.dumps({"status": "failed", "error": str(problem)}))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
