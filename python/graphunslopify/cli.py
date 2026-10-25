"""Command line entry points.

Two commands matter. `describe` tells an agent what is in a data file before it
writes a spec, and `run` renders a generated script and reports what is wrong
with the result. Between them they close the loop that otherwise requires a
human to open a PNG and say what they see.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import json
import os
import subprocess
import sys
from pathlib import Path

from .build import Figure, _relative_path
from .describe import profile, render
from .errors import SpecError
from .transport import local_request


def _load_spec(path: str) -> Figure:
    source = Path(path).expanduser().resolve()
    spec = json.loads(source.read_text(encoding="utf8"))
    if not isinstance(spec, dict):
        raise SpecError("spec must be a JSON object")
    data = spec.get("data", {})
    if isinstance(data, dict):
        name = data.get("path", "results.csv")
        if isinstance(name, str) and "://" not in name:
            data["path"] = str((source.parent / Path(name).expanduser()).resolve())
        spec["data"] = data
    if isinstance(spec.get("palette_lock"), str):
        spec["palette_lock"] = str((source.parent / spec["palette_lock"]).resolve())
    return Figure(spec)


def _render_spec(args: argparse.Namespace) -> int:
    try:
        figure = _load_spec(args.spec)
        with contextlib.redirect_stdout(sys.stderr):
            result = figure.render(
                cwd=args.out_dir,
                api=args.api,
                strict=args.strict,
                fail_on_warning=args.fail_on_warning,
            )
    except (SpecError, OSError, ValueError) as problem:
        report = getattr(problem, "report", None)
        if args.json:
            print(json.dumps(report or {"status": "failed", "error": str(problem)}))
        else:
            print(str(problem), file=sys.stderr)
        return int(report.get("exit_code", 2)) if report else 2
    if args.json:
        print(json.dumps(result["report"]))
    else:
        print(f"Wrote {result['script']} and {result['report_path']}")
    return 0


def _translate_spec(args: argparse.Namespace) -> int:
    try:
        figure = _load_spec(args.spec)
        if args.output:
            base = Path(args.output).expanduser().resolve().parent
            data = figure.spec.get("data", {})
            if (
                isinstance(data, dict)
                and isinstance(data.get("path"), str)
                and "://" not in data["path"]
            ):
                data["path"] = _relative_path(data["path"], base)
            if figure.spec.get("palette_lock"):
                figure.spec["palette_lock"] = _relative_path(figure.spec["palette_lock"], base)
        result = figure.translate(api=args.api)
        if args.output and result.get("ok"):
            destination = Path(args.output).expanduser().resolve()
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(result["code"], encoding="utf8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 2
    except (SpecError, OSError, ValueError) as problem:
        print(json.dumps({"ok": False, "error": str(problem)}))
        return 2


def _doctor(_: argparse.Namespace) -> int:
    from . import __version__

    try:
        info = local_request("info")
        ok = info["version"] == __version__
        print(json.dumps({"ok": ok, "python_package": __version__, "translator": info}))
        return 0 if ok else 1
    except SpecError as problem:
        print(json.dumps({"ok": False, "error": str(problem)}))
        return 1


def _notebook(args: argparse.Namespace) -> int:
    from .notebook import create_notebook

    try:
        result = create_notebook(args.output, execute=args.execute)
    except ImportError:
        print(
            json.dumps(
                {"ok": False, "error": "Install graphunslopify[notebook] to execute notebooks"}
            )
        )
        return 2
    except (OSError, ValueError, SpecError) as problem:
        print(json.dumps({"ok": False, "error": str(problem)}))
        return 2
    print(json.dumps({"ok": True, **result}))
    return 0


def _demo(args: argparse.Namespace) -> int:
    from .demo import write_demo

    try:
        args.spec = str(write_demo(args.directory))
    except (SpecError, OSError) as problem:
        print(str(problem), file=sys.stderr)
        return 1
    args.out_dir = None
    args.api = "local"
    args.strict = True
    args.fail_on_warning = False
    return _render_spec(args)


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
        encoding="utf8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
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


def _provenance(args: argparse.Namespace) -> int:
    from .provenance import read_provenance

    try:
        evidence = read_provenance(args.path)
    except (OSError, ValueError) as problem:
        print(json.dumps({"ok": False, "error": str(problem)}))
        return 1
    print(json.dumps({"ok": True, "provenance": evidence}, ensure_ascii=False, indent=2))
    return 0


def _version(_: argparse.Namespace) -> int:
    from . import __version__

    print(__version__)
    return 0


def _audit(args: argparse.Namespace) -> int:
    from .audit import audit

    try:
        result = audit(
            args.path,
            output=args.out_dir,
            baseline=args.baseline,
            fail_on_warning=args.fail_on_warning,
            fail_on_change=args.fail_on_change,
            timeout=args.timeout,
        )
    except (OSError, ValueError) as problem:
        print(json.dumps({"status": "failed", "error": str(problem)}))
        return 2
    print(json.dumps(result, indent=2))
    return int(result["exit_code"])


def _audit_init(args: argparse.Namespace) -> int:
    from .audit import discover

    try:
        manifest = discover(args.path)
        destination = Path(args.output) if args.output else Path(args.path) / "graphunslopify.json"
        with destination.open("x", encoding="utf8") as handle:
            handle.write(json.dumps(manifest, indent=2) + "\n")
    except (OSError, ValueError) as problem:
        print(json.dumps({"status": "failed", "error": str(problem)}))
        return 2
    print(json.dumps({"manifest": str(destination), "figures": len(manifest["figures"])}))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="graphunslopify", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    notebook = commands.add_parser("notebook", help="copy the public notebook example")
    notebook.add_argument("--output", default="graphunslopify-quickstart.ipynb")
    notebook.add_argument(
        "--execute", action="store_true", help="execute using the current Python environment"
    )
    notebook.set_defaults(handler=_notebook)

    audited = commands.add_parser(
        "audit", help="regenerate and verify figures from a paper manifest"
    )
    audited.add_argument(
        "path", nargs="?", default=".", help="manifest, or directory containing graphunslopify.json"
    )
    audited.add_argument("--out-dir", default=".graphunslopify-audit")
    audited.add_argument("--baseline", help="previous audit.report.json to compare")
    audited.add_argument("--fail-on-warning", action="store_true")
    audited.add_argument("--fail-on-change", action="store_true")
    audited.add_argument("--timeout", type=float, default=120, help="seconds per generated program")
    audited.set_defaults(handler=_audit)

    initialized = commands.add_parser(
        "audit-init", help="discover figure JSON specs and write a manifest"
    )
    initialized.add_argument("path", nargs="?", default=".")
    initialized.add_argument("--output")
    initialized.set_defaults(handler=_audit_init)

    converted = commands.add_parser("translate", help="translate a JSON spec locally")
    converted.add_argument("spec", help="JSON file; data paths resolve beside it")
    converted.add_argument("--output", help="also write the generated Python script")
    converted.add_argument("--api", help="explicit HTTP translator URL, or local")
    converted.set_defaults(handler=_translate_spec)

    generated = commands.add_parser("render", help="translate and render a JSON figure spec")
    generated.add_argument("spec", help="JSON file; data paths resolve beside it")
    generated.add_argument("--out-dir", help="output directory (default: beside the data)")
    generated.add_argument("--api", help="explicit HTTP translator URL, or local")
    generated.add_argument("--strict", action="store_true")
    generated.add_argument("--fail-on-warning", action="store_true")
    generated.add_argument("--json", action="store_true")
    generated.set_defaults(handler=_render_spec)

    demo = commands.add_parser("demo", help="generate and strictly verify public toy results")
    demo.add_argument("directory", nargs="?", default="graphunslopify-demo")
    demo.add_argument("--json", action="store_true")
    demo.set_defaults(handler=_demo)

    doctor = commands.add_parser("doctor", help="check the packaged local translator")
    doctor.set_defaults(handler=_doctor)

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

    provenance = commands.add_parser(
        "provenance", help="read evidence embedded in a PNG/SVG/PDF/HTML"
    )
    provenance.add_argument("path")
    provenance.set_defaults(handler=_provenance)

    versioned = commands.add_parser("version", help="print the package version")
    versioned.set_defaults(handler=_version)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
