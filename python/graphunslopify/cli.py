"""Local data profiling, figure editing/rendering, auditing and agent integration."""

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
        diagnostics = getattr(problem, "diagnostics", None)
        if args.json:
            print(
                json.dumps(
                    report
                    or {
                        "status": "failed",
                        "error": str(problem),
                        **({"diagnostics": diagnostics} if diagnostics else {}),
                    }
                )
            )
        else:
            print(str(problem), file=sys.stderr)
        return int(report.get("exit_code", 2)) if report else 2
    if args.json:
        print(json.dumps(result["report"]))
    else:
        print(f"Wrote {result['script']} and {result['report_path']}")
    return 0


def _bundle_spec(args: argparse.Namespace) -> int:
    try:
        path = _load_spec(args.spec).bundle(
            args.output, include_data=not args.no_data, api=args.api
        )
    except (SpecError, OSError, ValueError) as problem:
        print(str(problem), file=sys.stderr)
        return 2
    print(f"Wrote source archive {path}; run its strict reproduction launcher to verify the figure")
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
        diagnostics = getattr(problem, "diagnostics", None)
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": str(problem),
                    **({"diagnostics": diagnostics} if diagnostics else {}),
                }
            )
        )
        return 2


def _explain(args: argparse.Namespace) -> int:
    from .diagnostics import advice, catalog

    known = args.code in catalog()["advice"]
    item = {"code": args.code, "known": known, **advice(args.code)}
    if args.json:
        print(json.dumps(item))
    else:
        print(args.code + ("" if known else " (unrecognized code)"))
        print("Why it matters: " + item["consequence"])
        print("Recommended correction: " + item["correction"])
    return 0 if known else 2


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


def _mcp(_: argparse.Namespace) -> int:
    try:
        from .mcpserver import serve
    except ImportError:
        print(
            "Install the graphunslopify [agent] extra to start the local MCP server",
            file=sys.stderr,
        )
        return 2
    serve()
    return 0


def _preview(args: argparse.Namespace) -> int:
    from .preview import serve_preview

    try:
        serve_preview(args.port, open_browser=args.open, max_upload_mb=args.max_upload_mb)
    except (OSError, ValueError) as problem:
        print(f"Could not start the local editor: {problem}", file=sys.stderr)
        return 2
    return 0


def _project_preview(args: argparse.Namespace) -> int:
    from .project_preview import serve_project

    try:
        serve_project(args.path, args.port, open_browser=args.open)
    except (OSError, ValueError) as problem:
        print(f"Could not start the paper workspace: {problem}", file=sys.stderr)
        return 2
    return 0


def _mcp_config(args: argparse.Namespace) -> int:
    command_args = ["-m", "graphunslopify.cli", "mcp"]
    if args.client == "codex":
        print("[mcp_servers.graphunslopify]")
        print("command = " + json.dumps(sys.executable))
        print("args = " + json.dumps(command_args))
    else:
        print(
            json.dumps(
                {
                    "mcpServers": {
                        "graphunslopify": {"command": sys.executable, "args": command_args}
                    }
                },
                indent=2,
            )
        )
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
    report = profile(args.path, sheet=args.sheet)
    print(render(report))
    return 0 if report.get("ok") else 1


def _run(args: argparse.Namespace) -> int:
    script = Path(args.script)
    if not script.exists():
        print(f"no such script: {script}", file=sys.stderr)
        return 1

    workdir = Path(args.cwd) if args.cwd else script.parent
    command = [sys.executable, str(script.resolve())]
    command.append("--strict" if args.strict else "--no-strict")
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
            baseline_root=args.baseline_root,
        )
    except (OSError, ValueError) as problem:
        print(json.dumps({"status": "failed", "error": str(problem)}))
        return 2
    print(json.dumps(result, indent=2))
    return int(result["exit_code"])


def _compare(args: argparse.Namespace) -> int:
    from .comparison import compare_reports

    try:
        result = compare_reports(
            args.before,
            args.after,
            output=args.out_dir,
            before_root=args.before_root,
            after_root=args.after_root,
        )
    except (OSError, ValueError) as problem:
        print(json.dumps({"status": "failed", "error": str(problem)}))
        return 2
    print(json.dumps(result, indent=2))
    return int(result["exit_code"])


def _workflow_init(args: argparse.Namespace) -> int:
    from .workflow import initialize_workflow

    try:
        result = initialize_workflow(args.path, folder=args.folder)
    except (OSError, ValueError) as problem:
        print(json.dumps({"status": "failed", "error": str(problem)}))
        return 2
    print(json.dumps(result, indent=2))
    return 0


def _workflow_run(args: argparse.Namespace) -> int:
    from .workflow import run_workflow

    try:
        result = run_workflow(
            args.config,
            latex=args.latex,
            baseline=args.baseline,
            baseline_root=args.baseline_root,
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


def _track_mlflow(args: argparse.Namespace) -> int:
    from .tracking import log_mlflow

    try:
        result = log_mlflow(
            args.report,
            tracking_uri=args.tracking_uri,
            experiment_id=args.experiment_id,
            run_id=args.run_id,
            artifact_root=args.artifact_root,
        )
    except (OSError, ValueError) as problem:
        print(json.dumps({"status": "failed", "exit_code": 2, "error": str(problem)}))
        return 2
    print(json.dumps(result, indent=2))
    return int(result["exit_code"])


def _project(args: argparse.Namespace) -> int:
    from .project import (
        initialize_project,
        project_history,
        project_status,
        run_project,
        set_project_shared,
    )

    try:
        if args.command == "project-init":
            result = initialize_project(args.path, folder=args.folder)
        elif args.command == "project-status":
            result = project_status(args.path)
        elif args.command == "project-history":
            result = project_history(args.path)
        elif args.command == "project-review":
            from .project_review import project_review

            result = project_review(args.path, event_id=args.event)
        elif args.command == "project-shared":
            result = set_project_shared(
                args.path,
                json.loads(Path(args.settings).read_text(encoding="utf8")),
                expected_revision=args.expected_revision,
            )
        else:
            result = run_project(
                args.path,
                expected_revision=args.expected_revision,
                baseline=None if args.no_baseline else args.baseline,
                fail_on_warning=args.fail_on_warning,
                fail_on_change=args.fail_on_change,
                timeout=args.timeout,
            )
    except (OSError, ValueError) as problem:
        print(json.dumps({"status": "failed", "exit_code": 2, "error": str(problem)}))
        return 2
    print(json.dumps(result, indent=2))
    return int(result.get("exit_code", 0))


def _audit_pdf(args: argparse.Namespace) -> int:
    from .pdf_review import review_pdf

    try:
        regions = (
            json.loads(Path(args.regions).read_text(encoding="utf8")) if args.regions else None
        )
        result = review_pdf(
            args.path,
            output=args.out_dir,
            pages=args.pages,
            regions=regions,
            dpi=args.dpi,
            prepare_only=args.prepare_only,
            min_text_pt=args.min_text_pt,
            min_image_dpi=args.min_image_dpi,
        )
    except (OSError, ValueError) as problem:
        print(json.dumps({"status": "failed", "error": str(problem)}))
        return 2
    print(json.dumps(result, indent=2))
    return int(result["exit_code"])


def _verification_options(parser: argparse.ArgumentParser) -> None:
    policy = parser.add_mutually_exclusive_group()
    policy.add_argument(
        "--strict",
        action="store_true",
        default=True,
        help="reject failed or incomplete verification (default)",
    )
    policy.add_argument(
        "--no-strict",
        dest="strict",
        action="store_false",
        help="explicit legacy opt-out; reports still retain failed/incomplete checks",
    )
    parser.add_argument(
        "--fail-on-warning", action="store_true", help="strict mode, also rejecting warnings"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="graphunslopify", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    bundle = commands.add_parser("bundle", help="archive a figure with its actual source runtime")
    bundle.add_argument("spec", help="FigureSpec JSON file")
    bundle.add_argument("--output", required=True, help="standalone ZIP destination")
    bundle.add_argument(
        "--no-data", action="store_true", help="require the original input separately"
    )
    bundle.add_argument("--api", default=None)
    bundle.set_defaults(handler=_bundle_spec)

    preview = commands.add_parser("preview", help="open a local live figure editor")
    preview.add_argument("--port", type=int, default=8787)
    preview.add_argument("--open", action="store_true", help="open the browser")
    preview.add_argument("--max-upload-mb", type=int, default=100)
    preview.set_defaults(handler=_preview)

    paper = commands.add_parser(
        "project-preview",
        help="manage a paper's figures and audit history in one local browser workspace",
    )
    paper.add_argument("path", nargs="?", default=".")
    paper.add_argument("--port", type=int, default=8788)
    paper.add_argument("--open", action="store_true", help="open the browser")
    paper.set_defaults(handler=_project_preview)

    mcp = commands.add_parser("mcp", help="serve the local compiler over MCP stdio (agent extra)")
    mcp.set_defaults(handler=_mcp)
    mcp_config = commands.add_parser(
        "mcp-config", help="print client configuration without changing settings"
    )
    mcp_config.add_argument("--client", choices=["generic", "codex"], default="generic")
    mcp_config.set_defaults(handler=_mcp_config)

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
    audited.add_argument("--baseline-root", help="artifact root for a moved baseline archive")
    audited.add_argument("--fail-on-warning", action="store_true")
    audited.add_argument("--fail-on-change", action="store_true")
    audited.add_argument("--timeout", type=float, default=120, help="seconds per generated program")
    audited.set_defaults(handler=_audit)

    compared = commands.add_parser(
        "compare", help="compare two saved audits without executing sources"
    )
    compared.add_argument("before")
    compared.add_argument("after")
    compared.add_argument("--out-dir", default="figure-comparison")
    compared.add_argument("--before-root", help="override the before artifact root")
    compared.add_argument("--after-root", help="override the after artifact root")
    compared.set_defaults(handler=_compare)

    workflow = commands.add_parser(
        "workflow-init", help="connect a paper manifest to notebooks, VS Code and LaTeX"
    )
    workflow.add_argument("path", nargs="?", default=".")
    workflow.add_argument(
        "--folder",
        default="graphunslopify-workflow",
        help="new portable child folder beside the manifest",
    )
    workflow.set_defaults(handler=_workflow_init)
    workflow_run = commands.add_parser(
        "workflow-run", help="run one strict manifest workflow from any working directory"
    )
    workflow_run.add_argument("config", nargs="?", default=".")
    workflow_run.add_argument(
        "--latex",
        action="store_true",
        help="stage accepted PNG/PDFs and a checked-width manuscript include",
    )
    workflow_run.add_argument("--baseline")
    workflow_run.add_argument("--baseline-root")
    workflow_run.add_argument("--fail-on-warning", action="store_true")
    workflow_run.add_argument("--fail-on-change", action="store_true")
    workflow_run.add_argument("--timeout", type=float, default=120)
    workflow_run.set_defaults(handler=_workflow_run)

    tracked = commands.add_parser(
        "track-mlflow", help="log saved audit/workflow evidence to an explicit MLflow run"
    )
    tracked.add_argument("report", help="saved audit.report.json or workflow.report.json")
    tracked.add_argument("--tracking-uri", required=True)
    destination = tracked.add_mutually_exclusive_group(required=True)
    destination.add_argument("--experiment-id", help="existing experiment for a new owned run")
    destination.add_argument("--run-id", help="existing running run; caller keeps its lifecycle")
    tracked.add_argument(
        "--artifact-root", help="exclusive root override for a moved audit archive"
    )
    tracked.set_defaults(handler=_track_mlflow)

    for name, help_text in [
        ("project-init", "initialize durable paper figure management beside its manifest"),
        ("project-status", "inspect every figure's last result and declared input freshness"),
        ("project-history", "verify saved project run and settings history"),
        ("project-review", "read grouped scientific evidence without executing figures"),
        ("project-shared", "save shared semantic settings with an expected revision"),
        ("project-run", "audit the paper and preserve an independent versioned run"),
    ]:
        project = commands.add_parser(name, help=help_text)
        project.add_argument("path", nargs="?", default=".")
        project.set_defaults(handler=_project)
        if name == "project-init":
            project.add_argument("--folder", default="graphunslopify-project")
        if name == "project-shared":
            project.add_argument(
                "--settings",
                required=True,
                help="JSON object containing style/output/palette settings",
            )
            project.add_argument("--expected-revision", required=True)
        if name == "project-review":
            project.add_argument("--event", help="intact completed historical audit run ID")
        if name == "project-run":
            project.add_argument("--expected-revision")
            project.add_argument(
                "--baseline", default="latest", help="completed run ID; default latest intact run"
            )
            project.add_argument("--no-baseline", action="store_true")
            project.add_argument("--fail-on-warning", action="store_true")
            project.add_argument("--fail-on-change", action="store_true")
            project.add_argument("--timeout", type=float, default=120)

    initialized = commands.add_parser(
        "audit-init", help="discover figure JSON specs and write a manifest"
    )
    initialized.add_argument("path", nargs="?", default=".")
    initialized.add_argument("--output")
    initialized.set_defaults(handler=_audit_init)

    pdf_review = commands.add_parser(
        "audit-pdf", help="prepare a visual review packet from an ordinary PDF"
    )
    pdf_review.add_argument(
        "path", help="local PDF; prepare review without original figure source data"
    )
    pdf_review.add_argument("--out-dir", default="pdf-review")
    pdf_review.add_argument(
        "--pages", nargs="+", type=int, help="one-based pages, at most50; default all"
    )
    pdf_review.add_argument(
        "--regions", help="JSON list of manually selected normalized page rectangles"
    )
    pdf_review.add_argument("--dpi", type=int, default=144)
    pdf_review.add_argument(
        "--min-text-pt",
        type=float,
        default=6.0,
        help="review transformed PDF text below this physical point size",
    )
    pdf_review.add_argument(
        "--min-image-dpi",
        type=float,
        default=150.0,
        help="review embedded raster placements below this source pixel density",
    )
    pdf_review.add_argument(
        "--prepare-only",
        action="store_true",
        help="exit0 when preparation succeeds; scientific verification stays incomplete",
    )
    pdf_review.set_defaults(handler=_audit_pdf)

    converted = commands.add_parser("translate", help="translate a JSON spec locally")
    converted.add_argument("spec", help="JSON file; data paths resolve beside it")
    converted.add_argument("--output", help="also write the generated Python script")
    converted.add_argument("--api", help="explicit HTTP translator URL, or local")
    converted.set_defaults(handler=_translate_spec)

    generated = commands.add_parser("render", help="translate and render a JSON figure spec")
    generated.add_argument("spec", help="JSON file; data paths resolve beside it")
    generated.add_argument("--out-dir", help="output directory (default: beside the data)")
    generated.add_argument("--api", help="explicit HTTP translator URL, or local")
    _verification_options(generated)
    generated.add_argument("--json", action="store_true")
    generated.set_defaults(handler=_render_spec)

    demo = commands.add_parser("demo", help="generate and strictly verify public toy results")
    demo.add_argument("directory", nargs="?", default="graphunslopify-demo")
    demo.add_argument("--json", action="store_true")
    demo.set_defaults(handler=_demo)

    doctor = commands.add_parser("doctor", help="check the packaged local translator")
    doctor.set_defaults(handler=_doctor)

    described = commands.add_parser("describe", help="profile a data file as JSON")
    described.add_argument("path", help="csv, parquet, json or Excel file")
    described.add_argument("--sheet", help="Excel worksheet name; required for multiple worksheets")
    described.set_defaults(handler=_describe)

    for name, handler in (("run", _run), ("check", _check)):
        ran = commands.add_parser(name, help="run a generated script and report on the figure")
        ran.add_argument("script", help="the .py file the translator produced")
        ran.add_argument("--cwd", help="directory to run in, so relative data paths resolve")
        _verification_options(ran)
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

    explain = commands.add_parser("explain", help="explain a finding's consequence and correction")
    explain.add_argument("code", help="stable finding code, e.g. truncated_bar_axis")
    explain.add_argument("--json", action="store_true")
    explain.set_defaults(handler=_explain)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
