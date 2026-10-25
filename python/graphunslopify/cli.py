"""Command line entry points.

Two commands matter. `describe` tells an agent what is in a data file before it
writes a spec, and `run` renders a generated script and reports what is wrong
with the result. Between them they close the loop that otherwise requires a
human to open a PNG and say what they see.
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
from pathlib import Path

from .describe import profile, render


def _describe(args: argparse.Namespace) -> int:
    report = profile(args.path)
    print(render(report))
    return 0 if report.get("ok") else 1


def _run(args: argparse.Namespace) -> int:
    script = Path(args.script)
    if not script.exists():
        print(f"no such script: {script}", file=sys.stderr)
        return 1

    workdir = Path(args.cwd) if args.cwd else script.parent
    command = [sys.executable, str(script.resolve())]
    if args.strict:
        command.append("--strict")
    if args.fail_on_warning:
        command.append("--fail-on-warning")
    if args.report:
        command.extend(["--report", args.report])
    if args.json:
        command.append("--json")
    completed = subprocess.run(
        command,
        cwd=workdir,
        capture_output=True,
        text=True,
        check=False,
    )
    output = completed.stdout.strip()
    if output:
        print(output)
    if completed.stderr.strip():
        print(completed.stderr.strip(), file=sys.stderr)
    if completed.returncode != 0:
        return completed.returncode

    if args.thumbnail:
        # Opt in only. The whole point of emitting a script is that data stays
        # on this machine, and a thumbnail is a picture of that data.
        produced = sorted(workdir.glob("*.png"), key=lambda p: p.stat().st_mtime)
        if produced:
            payload = base64.b64encode(produced[-1].read_bytes()).decode("ascii")
            print(json.dumps({"thumbnail": produced[-1].name, "png_base64": payload}))
    return 0


def _check(args: argparse.Namespace) -> int:
    """Re-check an already rendered figure by re-running its script."""
    return _run(args)


def _version(_: argparse.Namespace) -> int:
    from . import __version__

    print(__version__)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="graphunslopify", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    described = commands.add_parser("describe", help="profile a data file as JSON")
    described.add_argument("path", help="csv, parquet or json file")
    described.set_defaults(handler=_describe)

    for name, handler in (("run", _run), ("check", _check)):
        ran = commands.add_parser(name, help="run a generated script and report on the figure")
        ran.add_argument("script", help="the .py file the translator produced")
        ran.add_argument("--cwd", help="directory to run in, so relative data paths resolve")
        ran.add_argument("--strict", action="store_true", help="fail on errors or untested checks")
        ran.add_argument("--fail-on-warning", action="store_true", help="also fail on warnings")
        ran.add_argument("--report", help="JSON report destination, relative to --cwd")
        display = ran.add_mutually_exclusive_group()
        display.add_argument("--json", action="store_true", help="only JSON on stdout")
        display.add_argument(
            "--thumbnail", action="store_true", help="also print the PNG as base64"
        )
        ran.set_defaults(handler=handler)

    versioned = commands.add_parser("version", help="print the package version")
    versioned.set_defaults(handler=_version)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
