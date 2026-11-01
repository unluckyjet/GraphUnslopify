"""Owned native worker observer; preserve program bytes and the actual render."""

from __future__ import annotations

import argparse
import hashlib
import json
import runpy
import sys
import time
from pathlib import Path

from graphunslopify import preview_render
from matplotlib.figure import Figure


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--timings", type=Path, required=True)
    parser.add_argument("--profile-script", type=Path, required=True)
    args, native = parser.parse_known_args()
    script = args.profile_script.resolve()
    original_program = script.read_bytes()
    measurement_path = Path(__file__).with_name("measurement.py")
    measured = runpy.run_path(str(measurement_path))
    original_save, previous_argv = Figure.savefig, sys.argv
    events = []
    kind, stem = None, None

    def observe(event, context):
        nonlocal kind, stem
        if event == "before_module":
            if Path(context["__file__"]).resolve() != script:
                raise ValueError("Observed a different native program")
        elif event == "ready":
            spec = json.loads(context["SPEC_JSON"])
            kind, stem = spec["kind"], spec["output"]["stem"]
            # Install after preview_render installs its owned geometry wrapper.
            downstream = Figure.savefig

            def save(figure, filename, *positional, **options):
                answer = downstream(figure, filename, *positional, **options)
                available = time.perf_counter_ns()
                if isinstance(filename, (str, Path)):
                    path = Path(filename).resolve()
                    if path.parent == script.parent and path.name in {
                        stem + "." + fmt for fmt in ("png", "svg", "pdf")
                    }:
                        event = measured["saved_figure"](
                            figure, path, kind, available_ns=available
                        )
                        events.append(event)
                        (script.parent / "workspace-save-events.json").write_text(
                            json.dumps(events, ensure_ascii=False, allow_nan=False)
                            + "\n",
                            encoding="utf8",
                        )
                return answer

            Figure.savefig = save

    token = preview_render.NAMESPACE_OBSERVER.set(observe)
    sys.argv = ["workspace-save-observer", *native]
    try:
        preview_render.main()
    finally:
        preview_render.NAMESPACE_OBSERVER.reset(token)
        Figure.savefig = original_save
        sys.argv = previous_argv
        if script.read_bytes() != original_program:
            raise RuntimeError("Native program changed while being observed")
        args.timings.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "scope": "Actual original native saves. Event timestamps are observation only; no formal latency inference before the complete implementation seal.",
                    "program_sha256": hashlib.sha256(original_program).hexdigest(),
                    "measurement_source_sha256": hashlib.sha256(
                        measurement_path.read_bytes()
                    ).hexdigest(),
                    "events": events,
                    "formal_comparison_performed": False,
                },
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n",
            encoding="utf8",
        )


if __name__ == "__main__":
    main()
