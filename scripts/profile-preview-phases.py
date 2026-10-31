"""Native CLI phase timers; original program bytes are retained, guard invoked explicitly."""

from __future__ import annotations

import argparse
import functools
import json
import sys
import time
from pathlib import Path

start = time.perf_counter()
parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--timings", type=Path, required=True)
parser.add_argument("--profile-script", type=Path, required=True)
options, native_args = parser.parse_known_args()
expected = options.profile_script.resolve()
assert not options.timings.exists()
exclusive, inclusive, calls, stack = {}, {}, {}, []
last = start


def timed(label, function):
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        global last
        began = time.perf_counter()
        if stack:
            exclusive[stack[-1]] = exclusive.get(stack[-1], 0) + began - last
        stack.append(label)
        last = began
        try:
            return function(*args, **kwargs)
        finally:
            ended = time.perf_counter()
            exclusive[stack[-1]] = exclusive.get(stack[-1], 0) + ended - last
            stack.pop()
            last = ended
            inclusive[label] = inclusive.get(label, 0) + ended - began
            calls[label] = calls.get(label, 0) + 1

    return wrapped


module_start = None
old_save = old_inspect = None


def observe(event, context):
    global module_start, old_save, old_inspect
    if event == "before_module":
        if Path(context["__file__"]).resolve() != expected:
            raise ValueError(
                "Observed script differs from the declared profiling input"
            )
        exclusive["initialization_before_script"] = time.perf_counter() - start
        module_start = time.perf_counter()
        return
    if event == "after_module":
        exclusive["script_module_initialization"] = time.perf_counter() - module_start
        return
    groups = {
        "main": "draw_and_other_main",
        "load": "data_read",
        "prepare": "data_prepare",
        "summarise": "statistics",
        "build_table": "statistics",
        "summary_input": "statistics",
        "fit_headings": "owned_layout",
        "fit_sparkline_layout": "owned_layout",
        "fit_table_layout": "owned_layout",
        "fit_outside_legends": "owned_layout",
        "fit_date_labels": "owned_layout",
        "describe_panels": "description_and_claims",
    }
    for name, label in groups.items():
        if callable(context.get(name)):
            context[name] = timed(label, context[name])
    import graphunslopify
    from matplotlib.figure import Figure

    old_save, old_inspect = Figure.savefig, graphunslopify.inspect_figure
    Figure.savefig = timed("export_and_geometry", old_save)
    graphunslopify.inspect_figure = timed("inspection_and_projection", old_inspect)


sys.argv = ["preview-phase-probe", *native_args]
from graphunslopify import preview_render

observer_token = preview_render.NAMESPACE_OBSERVER.set(observe)
try:
    preview_render.main()
finally:
    preview_render.NAMESPACE_OBSERVER.reset(observer_token)
    if old_save is not None:
        import graphunslopify
        from matplotlib.figure import Figure

        Figure.savefig, graphunslopify.inspect_figure = old_save, old_inspect
    total = time.perf_counter() - start
    result = {
        "scope": "Instrumented native preview_render namespace observer. Invokes original run_cli after inert module load and optional numerical hooks; byte/PNG/spec/data controls required. Exclusive phases avoid nested double counting; inclusive phases overlap. No worker or speed claim.",
        "total_instrumented_child_seconds": total,
        "exclusive_seconds": exclusive,
        "inclusive_seconds": inclusive,
        "calls": calls,
        "unattributed_seconds": total - sum(exclusive.values()),
    }
    options.timings.write_text(json.dumps(result, indent=2) + "\n")
