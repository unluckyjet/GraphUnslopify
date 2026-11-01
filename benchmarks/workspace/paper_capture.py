"""Observe original saves in a real direct audit subprocess; preserve program bytes."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import runpy
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--script", type=Path, required=True)
    args, native = parser.parse_known_args()
    script = args.script.resolve()
    original = script.read_bytes()
    constants = {
        n.targets[0].id: ast.literal_eval(n.value)
        for n in ast.parse(original).body
        if isinstance(n, ast.Assign)
        and len(n.targets) == 1
        and isinstance(n.targets[0], ast.Name)
        and n.targets[0].id == "SPEC_JSON"
    }
    spec = json.loads(constants["SPEC_JSON"])
    measured = runpy.run_path(str(Path(__file__).with_name("measurement.py")))
    from matplotlib.figure import Figure

    downstream = Figure.savefig
    events = []

    def save(figure, filename, *positional, **options):
        answer = downstream(figure, filename, *positional, **options)
        available = time.perf_counter_ns()
        if isinstance(filename, (str, Path)):
            path = Path(filename).resolve()
            if path.parent == script.parent and path.name in {
                spec["output"]["stem"] + "." + fmt for fmt in spec["output"]["formats"]
            }:
                events.append(
                    measured["saved_figure"](
                        figure, path, spec["kind"], available_ns=available
                    )
                )
        return answer

    previous = sys.argv
    Figure.savefig = save
    sys.argv = [str(script), *native]
    try:
        runpy.run_path(str(script), run_name="__main__")
    finally:
        sys.argv = previous
        Figure.savefig = downstream
        if script.read_bytes() != original:
            raise RuntimeError("Observed native program changed")
        # Keep this copy inside the subprocess, before the real audit inventories
        # and receipts the directory. Never mutate completed SDK history later.
        actual_input = Path(spec["data"]["path"])
        if not actual_input.is_absolute():
            actual_input = script.parent / actual_input
        (script.parent / "data.csv").write_bytes(actual_input.read_bytes())
        args.observations.write_text(
            json.dumps(
                {
                    "program_sha256": hashlib.sha256(original).hexdigest(),
                    "pid": os.getpid(),
                    "events": events,
                    "formal_comparison_performed": False,
                    "scope": "Direct native subprocess, runpy bootstrap observer; original program/arguments and terminal status preserved. Requires a plain/observed control before formal clocks.",
                },
                allow_nan=False,
            )
            + "\n",
            encoding="utf8",
        )


if __name__ == "__main__":
    main()
