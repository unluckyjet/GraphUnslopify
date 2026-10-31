"""Observe original native module read/compile/exec in the extra untimed sample."""

from __future__ import annotations

import argparse
import builtins
import hashlib
import io
import json
import sys
import time
from pathlib import Path

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--timings", type=Path, required=True)
parser.add_argument("--profile-script", type=Path, required=True)
options, native = parser.parse_known_args()
expected = options.profile_script.resolve()
original_bytes = expected.read_bytes()
assert not options.timings.exists()
old_compile, old_open, old_profile = builtins.compile, io.open_code, sys.getprofile()
phases = {"source_read_seconds": 0.0, "compile_seconds": 0.0, "exec_seconds": 0.0}
counts = {"source_reads": 0, "compile_calls": 0, "exec_calls": 0}
exec_started = None
module_started = None
restored = False


class SourceFile:
    def __init__(self, source):
        self.source = source

    def __enter__(self):
        self.source.__enter__()
        return self

    def __exit__(self, *args):
        return self.source.__exit__(*args)

    def __getattr__(self, name):
        return getattr(self.source, name)

    def read(self, *args):
        began = time.perf_counter()
        try:
            return self.source.read(*args)
        finally:
            phases["source_read_seconds"] += time.perf_counter() - began
            counts["source_reads"] += 1


def open_code(path):
    source = old_open(path)
    return SourceFile(source) if Path(path).resolve() == expected else source


def compile_code(source, filename, *args, **kwargs):
    if str(filename) != str(expected):
        return old_compile(source, filename, *args, **kwargs)
    raw = source.encode() if isinstance(source, str) else source
    assert raw == original_bytes
    began = time.perf_counter()
    try:
        return old_compile(source, filename, *args, **kwargs)
    finally:
        phases["compile_seconds"] += time.perf_counter() - began
        counts["compile_calls"] += 1


def profile(frame, event, function):
    global exec_started
    # runpy passes its original compiled code explicitly to the real C exec.
    # Never replace exec or change implicit caller-global behavior.
    if function is not builtins.exec or event not in {
        "c_call",
        "c_return",
        "c_exception",
    }:
        return
    code = frame.f_locals.get("code")
    if getattr(code, "co_filename", None) != str(expected):
        return
    if event == "c_call":
        assert exec_started is None
        exec_started = time.perf_counter()
        counts["exec_calls"] += 1
    else:
        assert exec_started is not None
        phases["exec_seconds"] += time.perf_counter() - exec_started
        exec_started = None


def restore():
    global restored
    builtins.compile, io.open_code = old_compile, old_open
    sys.setprofile(old_profile)
    restored = True


def observe(event, namespace):
    global module_started
    if event == "before_module":
        assert Path(namespace["__file__"]).resolve() == expected
        module_started = time.perf_counter()
        builtins.compile, io.open_code = compile_code, open_code
        sys.setprofile(profile)
    elif event == "after_module":
        phases["module_load_seconds_instrumented"] = (
            time.perf_counter() - module_started
        )
        restore()


sys.argv = ["runtime-phase-observer", *native]
from graphunslopify import preview_render

token = preview_render.NAMESPACE_OBSERVER.set(observe)
began = time.perf_counter()
try:
    preview_render.main()
finally:
    restore()
    preview_render.NAMESPACE_OBSERVER.reset(token)
    phases["complete_native_seconds_instrumented"] = time.perf_counter() - began
    assert expected.read_bytes() == original_bytes
    options.timings.write_text(
        json.dumps(
            {
                "scope": "Extra untimed original-program sample. Hooks active only during module load; compile and real C exec retain original code. Timings include observer overhead and are not ordinary latency samples.",
                "program_sha256": hashlib.sha256(original_bytes).hexdigest(),
                "counts": counts,
                "seconds": phases,
                "hooks_restored": restored,
                "observer_source_sha256": hashlib.sha256(
                    Path(__file__).read_bytes()
                ).hexdigest(),
            },
            indent=2,
        )
        + "\n"
    )
