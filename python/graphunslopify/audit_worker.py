"""Execute a trusted generated script while keeping audit outputs in their own directory."""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("script", type=Path)
    parser.add_argument("cwd", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--fail-on-warning", action="store_true")
    args = parser.parse_args()
    script, source_cwd, output = args.script.resolve(), args.cwd.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    os.chdir(source_cwd)
    sys.path.insert(0, str(script.parent))
    spec = importlib.util.spec_from_file_location("audited_figure", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load generated script")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    # Read source directly: timestamp/size-based .pyc caches can be stale after
    # two same-length edits within one second, which is unacceptable in an audit.
    exec(compile(script.read_bytes(), str(script), "exec"), module.__dict__)  # noqa: S102 -- explicitly selected trusted program
    if not callable(getattr(module, "run_cli", None)):
        raise TypeError("script must implement the GraphUnslopify run_cli/report contract")
    # Definitions still come from the original program, including its source hash.
    # Resolve its input paths before changing cwd; never rewrite its source file.
    for key in ("DATA_PATH", "PALETTE_LOCK"):
        value = getattr(module, key, None)
        if isinstance(value, str) and "://" not in value:
            setattr(module, key, str((source_cwd / Path(value).expanduser()).resolve()))
    os.chdir(output)
    flags = ["--strict", "--json", "--report", "runtime.report.json"]
    if args.fail_on_warning:
        flags.append("--fail-on-warning")
    return int(module.run_cli(flags))


if __name__ == "__main__":
    raise SystemExit(main())
