"""Run one complete fixed operational track; preparation is the default."""

from __future__ import annotations

import argparse
import json
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--track",
        required=True,
        choices=("single", "paper", "reliability", "local", "native_ci", "gui"),
    )
    parser.add_argument("--mode", choices=("preseal", "formal"), default="preseal")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--seal", type=Path)
    parser.add_argument("--profiles-file", type=Path)
    parser.add_argument("--native-profile")
    parser.add_argument("--expected-sha")
    args = parser.parse_args()
    if (args.mode == "formal") != (args.seal is not None):
        parser.error(
            "Formal mode requires a qualified seal; preparation cannot borrow one"
        )
    result = runpy.run_path(str(ROOT / "benchmarks/workspace/study_runner.py"))["run"](
        args.track,
        args.out,
        mode=args.mode,
        seal_path=args.seal,
        profiles=json.loads(args.profiles_file.read_text(encoding="utf8"))
        if args.profiles_file
        else None,
        native_profile=args.native_profile,
        expected_revision=args.expected_sha,
    )
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "track",
                    "mode",
                    "planned_cells",
                    "retained_cells",
                    "complete",
                    "interrupted",
                    "errors",
                )
            }
        )
    )
    raise SystemExit(0 if result["complete"] else 1)


if __name__ == "__main__":
    main()
