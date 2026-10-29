"""Capture actual save-time artists and exports for the frozen certified-reference protocol."""

from __future__ import annotations

import argparse
import hashlib
import os
import runpy
import sys
import time
import traceback
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
from matplotlib.figure import Figure

ROOT = Path(__file__).resolve().parents[1]
MEASURE = runpy.run_path(str(ROOT / "benchmarks/certified/measurement.py"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--script", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    script, output = args.script.resolve(), args.out_dir.resolve()
    record_path = output / "measurement.json"
    if record_path.exists():
        parser.error("previous measurements are never overwritten")
    protocol_path = ROOT / "benchmarks/certified/protocol.json"
    protocol = MEASURE["read_protocol"](ROOT)
    snapshots, exit_code, error = [], 0, None
    original_save = Figure.savefig

    def save(figure, filename, *positional, **options):
        path = (
            Path(filename).resolve()
            if isinstance(filename, (str, os.PathLike))
            else None
        )
        capture = (
            path is not None
            and path.parent == output
            and path.stem == "figure"
            and path.suffix[1:] in protocol["formats"]
        )
        measurement = MEASURE["figure_measurements"](figure) if capture else None
        dpi = options.get("dpi", matplotlib.rcParams["savefig.dpi"])
        dpi = float(figure.dpi if dpi == "figure" else dpi)
        start = time.perf_counter()
        result = original_save(figure, filename, *positional, **options)
        elapsed = time.perf_counter() - start
        if capture:
            snapshots.append(
                {
                    "format": path.suffix[1:],
                    "measurement": measurement,
                    "export_dpi": dpi,
                    "save_seconds": elapsed,
                    "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "svg_graphic_sha256": MEASURE["svg_graphic_digest"](
                        path.read_bytes()
                    )
                    if path.suffix == ".svg"
                    else None,
                }
            )
        return result

    before = Path.cwd()
    argv = sys.argv
    start = time.perf_counter()
    try:
        Figure.savefig = save
        os.chdir(output)
        sys.argv = [str(script)]
        runpy.run_path(str(script), run_name="__main__")
    except SystemExit as problem:
        exit_code = (
            problem.code
            if isinstance(problem.code, int)
            else 0
            if problem.code is None
            else 1
        )
        if isinstance(problem.code, str):
            error = problem.code
    except Exception as problem:  # noqa: BLE001 - retain arbitrary subject-script failures as evidence
        exit_code, error = 1, str(problem)
        traceback.print_exc()
    finally:
        Figure.savefig = original_save
        os.chdir(before)
        sys.argv = argv
    elapsed = time.perf_counter() - start
    exports = MEASURE["export_measurements"](output, snapshots, protocol)
    MEASURE["write_json"](
        record_path,
        {
            "schema_version": 1,
            "script_exit_code": exit_code,
            "error": error,
            "script_sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
            "protocol_sha256": hashlib.sha256(protocol_path.read_bytes()).hexdigest(),
            "instrumented_execution_seconds": elapsed,
            "save_seconds": sum(s["save_seconds"] for s in snapshots),
            "snapshots": snapshots,
            "exports": exports,
            "scope": "Instrumented execution includes measurement overhead; not human development time",
        },
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
