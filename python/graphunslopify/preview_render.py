"""Run one owned generated script with an observational PNG geometry capture."""

from __future__ import annotations

import argparse
import json
import runpy
import sys
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from .numerical_cache import ACTIVE
from .preview_diagnostics import DiagnosticSnapshot
from .preview_geometry import capture_png_geometry

NAMESPACE_OBSERVER: ContextVar = ContextVar("graphunslopify_namespace_observer", default=None)


def _execute(script):
    cache, observer = ACTIVE.get(), NAMESPACE_OBSERVER.get()
    if cache is None and observer is None:
        return runpy.run_path(str(script), run_name="__main__")
    if observer is not None:
        observer("before_module", {"__file__": str(script)})
    namespace = runpy.run_path(str(script), run_name="__preview_runtime__")
    context = namespace["run_cli"].__globals__
    if observer is not None:
        observer("after_module", context)
    if cache is not None:
        cache.install(context)
    if observer is not None:
        observer("ready", context)
    raise SystemExit(context["run_cli"](sys.argv[1:]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--geometry", type=Path, required=True)
    parser.add_argument("--png", type=Path, required=True)
    parser.add_argument("--diagnostics", type=Path)
    parser.add_argument("--provisional", action="store_true")
    parser.add_argument("script", type=Path)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    from matplotlib.figure import Figure

    import graphunslopify

    original = Figure.savefig
    original_inspect = graphunslopify.inspect_figure
    snapshot = DiagnosticSnapshot() if args.diagnostics is not None else None
    diagnostic_map = {
        "schema_version": 1,
        "available": False,
        "error": "No actual figure inspection was observed",
        "findings": [],
    }
    expected = args.png.resolve()

    def save(figure: Any, filename: Any, *positional: Any, **options: Any):
        if isinstance(filename, (str, Path)) and Path(filename).resolve() == expected:
            with capture_png_geometry(figure, expected, args.geometry, diagnostics=snapshot):
                result = original(figure, filename, *positional, **options)
            if args.provisional:
                from .preview_staging import publish_png

                try:
                    publish_png(expected, args.script)
                except (OSError, ValueError, TypeError, KeyError) as problem:
                    print(f"Provisional preview unavailable: {problem}", file=sys.stderr)
            return result
        return original(figure, filename, *positional, **options)

    def inspect(figure: Any, *positional: Any, **options: Any):
        report = original_inspect(figure, *positional, **options)
        if snapshot is not None:
            nonlocal diagnostic_map
            try:
                diagnostic_map = snapshot.project(figure, report)
            except (AttributeError, TypeError, ValueError, RuntimeError) as problem:
                diagnostic_map = {
                    "schema_version": 1,
                    "available": False,
                    "error": str(problem),
                    "findings": [],
                }
        return report

    previous = sys.argv
    Figure.savefig = save
    if snapshot is not None:
        graphunslopify.inspect_figure = inspect
    sys.argv = [str(args.script), *args.arguments]
    try:
        _execute(args.script)
    finally:
        Figure.savefig = original
        graphunslopify.inspect_figure = original_inspect
        sys.argv = previous
        if args.diagnostics is not None:
            try:
                args.diagnostics.write_text(
                    json.dumps(diagnostic_map, ensure_ascii=False, allow_nan=False), encoding="utf8"
                )
            except (OSError, ValueError, TypeError) as problem:
                print(f"Preview diagnostic geometry unavailable: {problem}", file=sys.stderr)


if __name__ == "__main__":
    main()
