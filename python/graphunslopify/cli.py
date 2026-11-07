"""Local data profiling, figure editing/rendering, auditing and agent integration."""

from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
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
    trace_observations = getattr(args, "trace_observations", False)
    try:
        figure = _load_spec(args.spec)
        with contextlib.redirect_stdout(sys.stderr):
            result = figure.render(
                cwd=args.out_dir,
                api=args.api,
                strict=args.strict,
                fail_on_warning=args.fail_on_warning,
                trace_observations=trace_observations,
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
        if trace_observations:
            print(f"Wrote observation selection {result['observation_path']}")
    return 0


def _comparison_file(name, limit):
    from .experiment_imports import _contained_bytes

    if not isinstance(name, str) or "://" in name:
        raise ValueError("Comparison requires local figure inputs")
    path = Path(name).resolve(strict=True)
    data = _contained_bytes(path.parent, path.name, limit=limit)
    if not 0 < len(data) <= limit:
        raise ValueError("Comparison requires a nonempty bounded local file")
    return data


def _sensitivity(args: argparse.Namespace) -> int:
    from .sensitivity import run_sensitivity, sensitivity_plan

    try:
        spec = _load_spec(args.spec).spec
        alternatives = json.loads(_comparison_file(args.alternatives, 64 * 1024))
        plan = sensitivity_plan(spec, alternatives)
        if not args.reviewed:
            print(
                json.dumps(
                    {
                        "status": "review_required",
                        "choices": [
                            {key: value for key, value in item.items() if key != "spec"}
                            for item in plan
                        ],
                        "next": "Confirm the declared analysis assumptions and run again with --reviewed.",
                    }
                )
            )
            return 2
        data = _comparison_file(spec.get("data", {}).get("path"), 16 * 1024**2)
        palette_name = spec.get("palette_lock")
        palette = _comparison_file(palette_name, 1024**2) if palette_name else None
        result = run_sensitivity(
            spec,
            alternatives,
            data=data,
            palette=palette,
            destination=args.out_dir,
            reviewed=True,
            timeout=args.timeout,
        )
    except (OSError, SpecError, TypeError, ValueError) as problem:
        print(json.dumps({"status": "failed", "error": str(problem)}))
        return 2
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return result["exit_code"]


def _robustness(args: argparse.Namespace) -> int:
    from .visual_robustness import robustness_plan, run_robustness

    try:
        spec = _load_spec(args.spec).spec
        requested = json.loads(_comparison_file(args.plan, 64 * 1024))
        if not isinstance(requested, dict) or set(requested) != {"alternatives", "thresholds"}:
            raise ValueError("The plan needs alternatives and thresholds")
        alternatives, thresholds = requested["alternatives"], requested["thresholds"]
        plan = robustness_plan(spec, alternatives, thresholds)
        if not args.reviewed:
            print(
                json.dumps(
                    {
                        "status": "review_required",
                        "thresholds": thresholds,
                        "choices": [
                            {key: value for key, value in item.items() if key != "spec"}
                            for item in plan
                        ],
                        "next": "Confirm the alternatives and materiality thresholds with --reviewed.",
                    }
                )
            )
            return 2
        data = _comparison_file(spec["data"].get("path"), 16 * 1024**2)
        palette_name = spec.get("palette_lock")
        palette = _comparison_file(palette_name, 1024**2) if palette_name else None
        result = run_robustness(
            spec,
            alternatives,
            thresholds,
            data=data,
            palette=palette,
            destination=args.out_dir,
            reviewed=True,
            timeout=args.timeout,
        )
    except (OSError, SpecError, TypeError, ValueError) as problem:
        print(json.dumps({"status": "failed", "error": str(problem)}))
        return 2
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return result["exit_code"]


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


def _explain_observation(args: argparse.Namespace) -> int:
    from .observation_provenance import (
        explain_saved_estimate,
        explain_saved_interval,
        explain_saved_matrix_cell,
    )

    handlers = {
        "explain-cell": explain_saved_matrix_cell,
        "explain-interval": explain_saved_interval,
        "explain-estimate": explain_saved_estimate,
    }
    try:
        explain = handlers[args.observation_command]
        options = {"run_directory": args.run_dir}
        if args.observation_command == "explain-estimate":
            options["curve"] = args.curve
        result = explain(args.report, args.x, args.y, **options)
    except (AttributeError, OSError, KeyError, TypeError, ValueError) as problem:
        print(str(problem), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
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


def _project_claim_links(args: argparse.Namespace) -> int:
    from .experiment_imports import _contained_bytes
    from .project_claim_links import (
        project_claim_links,
        remove_claim_link,
        review_claim_link,
        save_claim_link,
    )

    try:
        if args.confirm is not None and args.draft is None:
            raise ValueError("--confirm requires --draft")
        if args.links_revision is not None and args.remove is None:
            raise ValueError("--links-revision requires --remove")
        if args.draft is not None:
            draft_path = Path(args.draft).expanduser().resolve(strict=True)
            raw = _contained_bytes(draft_path.parent, draft_path.name, limit=16 * 1024)
            if len(raw) > 16 * 1024:
                raise ValueError("Claim-link drafts must fit within 16 KiB")
            draft = json.loads(raw)
            result = (
                review_claim_link(args.path, draft)
                if args.confirm is None
                else save_claim_link(args.path, draft, review_sha256=args.confirm, confirmed=True)
            )
        elif args.remove is not None:
            result = remove_claim_link(args.path, args.remove, links_revision=args.links_revision)
        else:
            result = project_claim_links(args.path)
    except (KeyError, OSError, TypeError, ValueError) as problem:
        print(json.dumps({"status": "failed", "error": str(problem)}))
        return 2
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return result.get("exit_code", 0)


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
            result = initialize_project(args.path, folder=args.folder, review_only=args.review_only)
        elif args.command == "project-status":
            result = project_status(args.path)
        elif args.command == "project-history":
            result = project_history(args.path)
        elif args.command == "project-intent":
            from .project_intent import project_intent

            result = project_intent(args.path)
        elif args.command in ("project-review-intent", "project-accept-intent"):
            from .experiment_imports import _contained_bytes
            from .project_intent import accept_project_intent, review_project_intent

            proposal = Path(args.changes).expanduser().absolute()
            raw = _contained_bytes(proposal.parent, proposal.name, limit=256 * 1024)
            if len(raw) > 256 * 1024:
                raise ValueError("Research intent changes must fit within 256 KiB.")
            changes = json.loads(raw)
            result = (
                review_project_intent(args.path, changes, expected_revision=args.expected_revision)
                if args.command == "project-review-intent"
                else accept_project_intent(
                    args.path,
                    changes,
                    expected_revision=args.expected_revision,
                    review_sha256=args.review_sha256,
                )
            )
        elif args.command == "project-review":
            from .project_review import project_review

            result = project_review(args.path, event_id=args.event)
        elif args.command == "project-review-panel":
            from .review_panel import paper_review_panel

            result = paper_review_panel(
                args.path,
                figures=args.figure,
                journal_profile=args.journal_profile,
                expected_revision=args.expected_revision,
            )
        elif args.command == "project-audit":
            from .paper_audit import audit_paper

            if len(args.review_plan) != len(args.consent_sha256) or (
                args.consent and not args.review_plan
            ):
                raise ValueError("Supply one consent digest per reviewed model request.")
            result = audit_paper(
                args.path,
                args.output,
                saved_evidence=args.saved_evidence,
                expected_revision=args.expected_revision,
                timeout=args.timeout,
                reviewed_requests=list(zip(args.review_plan, args.consent_sha256, strict=True)),
                consent=args.consent,
                api_key=os.environ.get("GRAPHUNSLOPIFY_DRAFT_API_KEY", ""),
            )
        elif args.command == "project-scorecard":
            from .project_scorecard import project_scorecard

            result = project_scorecard(args.path, event_id=args.event)
        elif args.command == "project-export":
            from .project import _config
            from .project_export import create_review_packet
            from .project_review import project_review

            review = project_review(args.path, event_id=args.event)
            source, _ = _config(args.path)
            destination = Path(args.output).expanduser().absolute()
            if destination.is_symlink() or destination.resolve().is_relative_to(
                source.parent.resolve()
            ):
                raise ValueError("Choose a new output outside the owned project evidence folder.")
            if destination.exists():
                raise FileExistsError("Choose a new output; the existing file is preserved.")
            raw = create_review_packet(
                args.path,
                event_id=args.event,
                expected_revision=args.expected_revision or review["evidence_revision"],
            )
            with destination.open("xb") as stream:
                stream.write(raw)
            result = {
                "status": "exported",
                "exit_code": 0,
                "path": str(destination),
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "evidence_revision": review["evidence_revision"],
                "native_audit_exit": (review.get("native_run") or {}).get("exit_code"),
                "science_reexecuted": False,
                "scope": "Saved review packet creation, not new scientific acceptance. Original datasets, PDFs and programs are excluded.",
            }
        elif args.command == "project-inspections":
            from .project_inspections import project_inspections

            result = project_inspections(args.path, event_id=args.event)
        elif args.command == "project-inspect-pdf":
            from .project_inspections import inspect_project_pdf

            result = inspect_project_pdf(
                args.path,
                args.pdf,
                identity=args.id,
                expected_revision=args.expected_revision,
                pages=args.pages,
                dpi=args.dpi,
                timeout=args.timeout,
            )
        elif args.command in ("project-review-shared", "project-apply-shared"):
            from .project_changes import apply_project_shared, review_project_shared

            operation = (
                review_project_shared
                if args.command == "project-review-shared"
                else apply_project_shared
            )
            result = operation(
                args.path,
                json.loads(Path(args.settings).read_text(encoding="utf8"))
                if args.settings
                else None,
                expected_revision=args.expected_revision,
                undo_event=args.undo,
                **(
                    {"proposal_token": args.proposal_token}
                    if args.command == "project-apply-shared"
                    else {}
                ),
            )
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
                selective=args.selective,
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


def _journal_profiles(args: argparse.Namespace) -> int:
    from .journal import journal_profiles

    print(json.dumps(journal_profiles(), ensure_ascii=False, indent=2))
    return 0


def _journal_check(args: argparse.Namespace) -> int:
    from .journal import check_journal

    try:
        source = Path(args.path).expanduser().resolve()
        output = Path(args.output).expanduser().resolve() if args.output else None
        if output is not None and (
            output == source or (output.exists() and output.samefile(source))
        ):
            raise ValueError("The journal report cannot overwrite its inspected figure")
        report = check_journal(
            source,
            profile=args.profile,
            target_width_mm=args.target_width_mm,
            width_tolerance_mm=args.width_tolerance_mm,
        )
        encoded = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(encoded + "\n", encoding="utf8")
        if args.json:
            print(encoded)
        else:
            print(f"Technical checks: {report['status']} · {report['profile']['name']}")
            for check in report["checks"]:
                if check["status"] != "passed":
                    print(f"  {check['status']}: {check['code']} — {check['message']}")
            print(
                f"{len(report['manual_review'])} manual review items remain; scientific verification was not performed."
            )
        return report["exit_code"]
    except (OSError, ValueError) as problem:
        if args.json:
            print(
                json.dumps(
                    {
                        "kind": "graphunslopify.journal-check",
                        "status": "failed",
                        "error": str(problem),
                        "exit_code": 2,
                    }
                )
            )
        else:
            print(str(problem), file=sys.stderr)
        return 2


def _experiments(args: argparse.Namespace) -> int:
    import contextlib
    import io

    from .experiment_imports import (
        experiment_comparison,
        experiment_runs,
        render_experiment_comparison,
    )

    options = {"provider": args.provider, "step_field": args.step_field, "metrics": args.metrics}
    if args.provider in {"mlflow", "wandb"}:
        options["tracker"] = {
            "endpoint": args.tracker_endpoint,
            "experiment_ids": args.experiments,
            "allow_remote": args.allow_remote,
            "api_key": os.environ.get(args.api_key_env) if args.api_key_env else None,
        }
    try:
        if args.command == "experiment-runs":
            result = experiment_runs(args.source, **options)
        else:
            proposal = experiment_comparison(
                args.source,
                **options,
                runs=args.runs,
                metric=args.metric,
                kind=args.kind,
                expected_snapshot=args.snapshot,
            )
            with contextlib.redirect_stdout(io.StringIO()):
                result = render_experiment_comparison(
                    proposal, args.out_dir, accept_exclusions=args.accept_exclusions
                )
        print(json.dumps(result, indent=2, allow_nan=False))
        return int(result.get("exit_code", 0))
    except (OSError, ValueError, TypeError) as problem:
        print(json.dumps({"error": str(problem), "exit_code": 2}))
        return 2


def _review_agent(args: argparse.Namespace) -> int:
    from .drafts import DraftProvider
    from .review_agent import (
        FigureReviewPlan,
        read_document,
        restore_plan,
        review_document,
        write_document,
    )

    try:
        destination = Path(args.out).expanduser()
        if destination.exists() or destination.is_symlink():
            raise ValueError("Choose a new output file; existing files stay intact")
        if args.command == "review-agent-plan":
            plan = FigureReviewPlan(
                DraftProvider(args.endpoint, args.model, args.protocol),
                args.path,
                question=args.question,
                figures=args.figure,
                event_id=args.event,
                author_context=args.author_context,
                structured_output=not args.json_mode,
            )
            result = review_document(plan)
            write_document(result, destination)
        else:
            plan = restore_plan(
                read_document(args.review),
                args.path,
                api_key=os.environ.get("GRAPHUNSLOPIFY_DRAFT_API_KEY", ""),
            )
            result = plan.request(consent=args.consent, consent_sha256=args.consent_sha256)
            with destination.open("x", encoding="utf8") as stream:
                json.dump(result, stream, indent=2, allow_nan=False)
                stream.write("\n")
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except (OSError, ValueError, TypeError) as problem:
        print(json.dumps({"error": str(problem), "exit_code": 2}))
        return 2


def _autopilot(args: argparse.Namespace) -> int:
    import io

    from .autopilot import propose_figures
    from .autopilot_review import generate_reviewed, read_review, review_document, write_review

    try:
        if args.command == "autopilot-propose":
            choices = {
                name: getattr(args, name)
                for name in ["target", "group", "predictor", "intent", "sheet"]
                if getattr(args, name) is not None
            }
            if args.no_group:
                choices["group"] = ""
            if args.temporal_predictor:
                choices["predictor_temporal"] = True
            if args.units is not None:
                choices["units"] = json.loads(args.units)
            document = review_document(propose_figures(args.source, args.question, **choices))
            write_review(document, args.out)
            print(json.dumps(document, indent=2, allow_nan=False))
            return 0 if document["report"]["ready"] else 2
        with contextlib.redirect_stdout(io.StringIO()):
            result = generate_reviewed(
                read_review(args.review),
                args.out_dir,
                reviewed=args.reviewed,
                accept_exclusions=args.accept_exclusions,
            )
        print(json.dumps(result, indent=2, allow_nan=False))
        return result["exit_code"]
    except (OSError, ValueError, TypeError) as problem:
        print(json.dumps({"error": str(problem), "exit_code": 2}))
        return 2


def _source_import(args: argparse.Namespace) -> int:
    import io

    from .experiment_imports import _contained_bytes
    from .source_imports import import_source, save_source_import

    try:
        source = Path(args.source).expanduser().resolve(strict=True)
        original = _contained_bytes(source.parent, source.name)
        data = None
        if args.data:
            mapped = Path(args.data).expanduser().resolve(strict=True)
            data = _contained_bytes(mapped.parent, mapped.name)
        proposal = import_source(original, data=data, name=source.name)
        with contextlib.redirect_stdout(io.StringIO()):
            result = save_source_import(
                proposal,
                args.out_dir,
                accept_partial=args.accept_partial,
                render=not args.no_render,
            )
        print(json.dumps(result, indent=2, allow_nan=False))
        return result["exit_code"]
    except (OSError, ValueError) as problem:
        print(json.dumps({"error": str(problem), "exit_code": 2}))
        return 2


def _statistical_power(args: argparse.Namespace) -> int:
    from .statistical_power import plan_power

    try:
        result = plan_power(
            {
                "design": args.design,
                "calculation": "power" if args.target_power is None else "detectable_effect",
                "n": args.n,
                "n_other": args.n_other,
                "alpha": args.alpha,
                "alternative": args.alternative,
                "effect": args.effect,
                "target_power": args.target_power,
                "sd": args.sd,
                "sd_other": args.sd_other,
                "assumptions_confirmed": args.confirm_assumptions,
            }
        )
    except ValueError as problem:
        print(json.dumps({"status": "failed", "error": str(problem), "exit_code": 2}))
        return 2
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0


def _effect_sizes(args: argparse.Namespace) -> int:
    from .effect_sizes import MAX_EFFECT_CSV_BYTES, compare_effects

    try:
        with Path(args.path).expanduser().open("rb") as source:
            raw = source.read(MAX_EFFECT_CSV_BYTES + 1)
        result = compare_effects(
            raw,
            {
                "outcome": args.outcome,
                "group": args.group,
                "unit": args.unit,
                "rows_are_units": args.rows_are_units,
                "design": args.design,
                "reduction": args.reduction,
                "contrasts": args.contrast,
                "confidence": args.confidence,
                "assumptions_confirmed": args.confirm_assumptions,
            },
        )
    except (OSError, ValueError) as problem:
        print(json.dumps({"status": "failed", "error": str(problem), "exit_code": 2}))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return result["exit_code"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="graphunslopify", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    journals = commands.add_parser(
        "journal-profiles", help="list dated, sourced journal requirement snapshots"
    )
    journals.set_defaults(handler=_journal_profiles)
    journal = commands.add_parser(
        "journal-check", help="inspect actual figure bytes against a journal profile"
    )
    journal.add_argument("path", help="local exported figure; no program or PostScript execution")
    journal.add_argument("--profile", required=True, help="ID from journal-profiles")
    journal.add_argument(
        "--target-width-mm",
        type=float,
        help="explicit author target, not inferred from venue styling",
    )
    journal.add_argument("--width-tolerance-mm", type=float, default=0.5)
    journal.add_argument("--output", help="also write the technical report as JSON")
    journal.add_argument("--json", action="store_true")
    journal.set_defaults(handler=_journal_check)

    power = commands.add_parser("power", help="calculate prospective mean-difference power")
    power.add_argument(
        "--design", required=True, choices=("one_sample", "paired", "pooled", "welch")
    )
    power.add_argument(
        "--n", required=True, type=int, help="planned observations, pairs or first-group units"
    )
    power.add_argument("--n-other", type=int, help="planned second-group units")
    power.add_argument("--alpha", required=True, type=float)
    power.add_argument("--alternative", required=True, choices=("two_sided", "greater", "less"))
    power.add_argument(
        "--sd", type=float, help="planning SD in outcome units, or first-group SD for Welch"
    )
    power.add_argument("--sd-other", type=float, help="second-group planning SD for Welch")
    goal = power.add_mutually_exclusive_group(required=True)
    goal.add_argument(
        "--effect",
        type=float,
        help="signed planning difference in outcome units with SD, or in SD units",
    )
    goal.add_argument(
        "--target-power", type=float, help="solve for a difference that attains this power"
    )
    power.add_argument(
        "--confirm-assumptions",
        action="store_true",
        help="confirm the declared normal-model design",
    )
    power.set_defaults(handler=_statistical_power)

    effects = commands.add_parser("effects", help="compare observed mean differences and intervals")
    effects.add_argument("path", help="UTF-8 CSV of original observations")
    effects.add_argument("--design", required=True, choices=("paired", "pooled", "welch"))
    effects.add_argument("--outcome", required=True, help="measurement column")
    effects.add_argument("--group", required=True, help="condition or group column")
    unit = effects.add_mutually_exclusive_group(required=True)
    unit.add_argument("--unit", help="independent or paired unit column")
    unit.add_argument(
        "--rows-are-units", action="store_true", help="declare separate independent units per row"
    )
    effects.add_argument("--reduction", choices=("refuse", "mean"), default="refuse")
    effects.add_argument(
        "--contrast", nargs=2, action="append", required=True, metavar=("LEFT", "RIGHT")
    )
    effects.add_argument("--confidence", type=float, default=0.95)
    effects.add_argument("--confirm-assumptions", action="store_true")
    effects.set_defaults(handler=_effect_sizes)

    sensitivity = commands.add_parser(
        "sensitivity", help="compare justified statistical alternatives for a summary figure"
    )
    sensitivity.add_argument("spec", help="baseline FigureSpec JSON file")
    sensitivity.add_argument("--alternatives", required=True, help="JSON file of justified choices")
    sensitivity.add_argument("--out-dir", required=True, help="new comparison evidence directory")
    sensitivity.add_argument(
        "--reviewed", action="store_true", help="confirm the stated statistical choices"
    )
    sensitivity.add_argument(
        "--timeout", type=float, default=60, help="per-figure timeout in seconds"
    )
    sensitivity.set_defaults(handler=_sensitivity)

    robustness = commands.add_parser(
        "robustness", help="measure how display choices change checked native figures"
    )
    robustness.add_argument("spec", help="baseline FigureSpec JSON file")
    robustness.add_argument(
        "--plan", required=True, help="JSON alternatives and materiality thresholds"
    )
    robustness.add_argument("--out-dir", required=True, help="new robustness evidence directory")
    robustness.add_argument(
        "--reviewed", action="store_true", help="confirm the choices and thresholds"
    )
    robustness.add_argument(
        "--timeout", type=float, default=60, help="per-figure timeout in seconds"
    )
    robustness.set_defaults(handler=_robustness)

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

    claim_links = commands.add_parser(
        "project-claim-links", help="check exact manuscript passages against saved figure evidence"
    )
    claim_links.add_argument("path", nargs="?", default=".")
    action = claim_links.add_mutually_exclusive_group()
    action.add_argument("--draft", help="review a local JSON link draft")
    action.add_argument("--remove", help="remove a saved claim link by its ID")
    claim_links.add_argument("--confirm", help="confirm the exact excerpt and the reviewed SHA-256")
    claim_links.add_argument("--links-revision", help="current links revision for removal")
    claim_links.set_defaults(handler=_project_claim_links)

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

    reviewer = commands.add_parser(
        "review-agent-plan", help="disclose a reviewer question grounded in saved paper checks"
    )
    reviewer.add_argument("path", nargs="?", default=".", help="initialized paper project")
    reviewer.add_argument("--endpoint", required=True, help="HTTPS or loopback model endpoint")
    reviewer.add_argument("--model", required=True)
    reviewer.add_argument("--protocol", choices=["responses", "chat"], default="responses")
    reviewer.add_argument(
        "--question", default="What would a skeptical reviewer criticize about these figures?"
    )
    reviewer.add_argument("--figure", action="append", help="repeat actual review figure keys")
    reviewer.add_argument("--event", help="explicit historical evidence selection")
    reviewer.add_argument("--author-context", default="", help="author-supplied study context")
    reviewer.add_argument(
        "--json-mode",
        action="store_true",
        help="explicit JSON-only mode for providers without schema-constrained output",
    )
    reviewer.add_argument("--out", required=True, help="new JSON disclosure file")
    reviewer.set_defaults(handler=_review_agent)
    reviewed = commands.add_parser(
        "review-agent-run", help="send an explicitly consented, unchanged reviewer disclosure"
    )
    reviewed.add_argument("review", help="saved JSON from review-agent-plan")
    reviewed.add_argument("--path", default=".", help="same initialized paper project")
    reviewed.add_argument("--consent", action="store_true")
    reviewed.add_argument("--consent-sha256", help="destination/request digest in the disclosure")
    reviewed.add_argument("--out", required=True, help="new JSON result file")
    reviewed.set_defaults(handler=_review_agent)

    propose = commands.add_parser(
        "autopilot-propose", help="review three data/question proposals without rendering"
    )
    propose.add_argument("source", help="CSV,regular JSON,Parquet or Excel dataset")
    propose.add_argument("--question", required=True)
    propose.add_argument(
        "--out", required=True, help="new JSON review file;existing files stay intact"
    )
    for option in ["target", "predictor", "sheet"]:
        propose.add_argument("--" + option)
    grouping = propose.add_mutually_exclusive_group()
    grouping.add_argument("--group", help="explicit grouping field")
    grouping.add_argument(
        "--no-group", action="store_true", help="keep all observations in one sample"
    )
    propose.add_argument(
        "--intent", choices=["comparison", "distribution", "relationship", "trend"]
    )
    propose.add_argument("--units", help='author unit labels as JSON,for example {"loss":"score"}')
    propose.add_argument("--temporal-predictor", action="store_true")
    propose.set_defaults(handler=_autopilot)
    generate = commands.add_parser(
        "autopilot-generate", help="strictly generate all three drafts from an unchanged review"
    )
    generate.add_argument("review", help="saved JSON from autopilot-propose")
    generate.add_argument(
        "--out-dir", required=True, help="new folder for all three native results"
    )
    generate.add_argument(
        "--reviewed", action="store_true", help="acknowledge reviewed mappings and assumptions"
    )
    generate.add_argument("--accept-exclusions", action="store_true")
    generate.set_defaults(handler=_autopilot)

    source_import = commands.add_parser(
        "import-source",
        help="review supported Python plotting patterns without executing the original",
    )
    source_import.add_argument("source", help="UTF8 Matplotlib/Seaborn Python source")
    source_import.add_argument(
        "--data",
        help="explicit local CSV mapping; source references are never opened automatically",
    )
    source_import.add_argument(
        "--out-dir", required=True, help="new original/report/spec/native output folder"
    )
    source_import.add_argument(
        "--accept-partial",
        action="store_true",
        help="explicitly review all unsupported source/presentation behavior",
    )
    source_import.add_argument(
        "--no-render",
        action="store_true",
        help="save an unverified draft instead of running strict native checks",
    )
    source_import.set_defaults(handler=_source_import)

    for name in ("experiment-runs", "experiment-compare"):
        experiment = commands.add_parser(
            name,
            help="read bounded local/MLflow/W&B histories"
            if name == "experiment-runs"
            else "strictly render selected raw experiment histories",
        )
        experiment.add_argument(
            "source", help="local files,MLflow SQLite/server,or W&B entity/project"
        )
        experiment.add_argument(
            "--provider", choices=["csv", "tensorboard", "mlflow", "wandb"], default="csv"
        )
        experiment.add_argument("--experiments", nargs="+", help="explicit MLflow experiment IDs")
        experiment.add_argument(
            "--tracker-endpoint", help="W&B endpoint;shown/configured explicitly"
        )
        experiment.add_argument(
            "--api-key-env",
            help="environment variable holding a provider key;never pass the key as an argument",
        )
        experiment.add_argument(
            "--allow-remote",
            action="store_true",
            help="authorize this explicit tracker endpoint/network read",
        )
        experiment.add_argument("--step-field", default="step", help="CSV step column")
        experiment.add_argument(
            "--metrics", nargs="+", help="optional CSV columns/TensorBoard tags to read"
        )
        if name == "experiment-compare":
            experiment.add_argument(
                "--snapshot", required=True, help="snapshot from experiment-runs"
            )
            experiment.add_argument(
                "--runs", nargs="+", required=True, help="run IDs from that snapshot"
            )
            experiment.add_argument("--metric", required=True)
            experiment.add_argument("--kind", choices=["line", "scatter"], default="line")
            experiment.add_argument(
                "--out-dir", required=True, help="new comparison folder outside the source"
            )
            experiment.add_argument(
                "--accept-exclusions",
                action="store_true",
                help="explicitly use valid observations with recorded exclusions",
            )
        experiment.set_defaults(handler=_experiments)

    for name, help_text in [
        ("project-init", "initialize durable paper figure management beside its manifest"),
        ("project-status", "inspect every figure's last result and declared input freshness"),
        ("project-history", "verify saved project run and settings history"),
        ("project-intent", "read accepted terminology, model names, units and figure conventions"),
        ("project-review-intent", "review exact proposed changes to project memory"),
        ("project-accept-intent", "accept a reviewed change to project memory"),
        ("project-review", "read grouped scientific evidence without executing figures"),
        ("project-review-panel", "assemble readability, statistical and journal review evidence"),
        (
            "project-audit",
            "strictly audit all paper figures and export prioritized review evidence",
        ),
        ("project-scorecard", "report available and missing reproduction evidence by component"),
        ("project-export", "save figure files and an auditable review packet without re-execution"),
        ("project-inspections", "read saved source-free PDF visual evidence and freshness"),
        (
            "project-inspect-pdf",
            "retain bounded PDF visual inspection without numerical acceptance",
        ),
        ("project-shared", "save shared semantic settings with an expected revision"),
        ("project-review-shared", "review affected figures or a guarded shared-settings undo"),
        ("project-apply-shared", "apply a content-bound shared review or undo"),
        ("project-run", "audit the paper and preserve an independent versioned run"),
    ]:
        project = commands.add_parser(name, help=help_text)
        project.add_argument("path", nargs="?", default=".")
        project.set_defaults(handler=_project)
        if name == "project-review-panel":
            project.add_argument("--journal-profile", help="technical journal profile ID")
            project.add_argument(
                "--figure", action="append", help="current figure key; repeat to select several"
            )
            project.add_argument(
                "--expected-revision", help="current project-review evidence revision"
            )
        if name in ("project-review-intent", "project-accept-intent"):
            project.add_argument("--changes", required=True, help="JSON patch of wording changes")
            project.add_argument(
                "--expected-revision", required=True, help="project-intent revision"
            )
        if name == "project-accept-intent":
            project.add_argument(
                "--review-sha256", required=True, help="exact reviewed change digest"
            )
        if name == "project-init":
            project.add_argument("--folder", default="graphunslopify-project")
            project.add_argument(
                "--review-only",
                action="store_true",
                help="create a PDF review project without a native plotting manifest",
            )
        if name in ("project-review-shared", "project-apply-shared"):
            choice = project.add_mutually_exclusive_group(required=True)
            choice.add_argument("--settings", help="proposed shared settings JSON file")
            choice.add_argument("--undo", help="intact saved settings event to undo")
            project.add_argument("--expected-revision", required=True)
            if name == "project-apply-shared":
                project.add_argument("--proposal-token", required=True)
        if name == "project-shared":
            project.add_argument(
                "--settings",
                required=True,
                help="JSON object containing style/output/palette settings",
            )
            project.add_argument("--expected-revision", required=True)
        if name in ("project-review", "project-scorecard", "project-inspections", "project-export"):
            project.add_argument(
                "--event",
                help="completed native audit or PDF inspection ID"
                if name in ("project-review", "project-scorecard", "project-export")
                else "completed PDF inspection ID",
            )
        if name == "project-export":
            project.add_argument("--output", required=True, help="new review ZIP destination")
            project.add_argument(
                "--expected-revision",
                help="evidence_revision from project-review; omitted selects current saved evidence",
            )
        if name == "project-audit":
            project.add_argument("--output", required=True, help="new paper audit ZIP destination")
            project.add_argument(
                "--saved-evidence",
                action="store_true",
                help="use current saved evidence without executing figures",
            )
            project.add_argument("--expected-revision", help="current project-status revision")
            project.add_argument(
                "--timeout", type=float, default=120, help="native figure timeout in seconds"
            )
            project.add_argument(
                "--review-plan",
                action="append",
                default=[],
                help="reviewed request document for current saved evidence",
            )
            project.add_argument(
                "--consent-sha256",
                action="append",
                default=[],
                help="exact consent digest for each request, in the same order",
            )
            project.add_argument(
                "--consent",
                action="store_true",
                help="authorize sending all reviewed requests to their configured providers",
            )
        if name == "project-inspect-pdf":
            project.add_argument("--pdf", required=True)
            project.add_argument("--id", required=True)
            project.add_argument("--expected-revision", required=True)
            project.add_argument("--pages", nargs="+", type=int)
            project.add_argument("--dpi", type=int, default=144)
            project.add_argument("--timeout", type=float, default=120)
        if name == "project-run":
            project.add_argument(
                "--selective",
                action="store_true",
                help="reuse intact accepted native figures when inputs/runtime/environment match",
            )
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
    generated.add_argument(
        "--trace-observations",
        action="store_true",
        help="record observation dependencies through filters, preparation and supported calculations (local translator)",
    )
    _verification_options(generated)
    generated.add_argument("--json", action="store_true")
    generated.set_defaults(handler=_render_spec)

    for name, target in (
        ("explain-cell", "a matrix cell"),
        ("explain-interval", "a summary interval"),
        ("explain-estimate", "a summary estimate"),
    ):
        explain = commands.add_parser(name, help=f"inspect {target} in an observation-traced PNG")
        explain.add_argument(
            "report", help="saved <stem>.report.json beside its generated Python file"
        )
        explain.add_argument(
            "x", type=float, help="horizontal pixel coordinate from the PNG's left edge"
        )
        explain.add_argument(
            "y", type=float, help="vertical pixel coordinate from the PNG's top edge"
        )
        explain.add_argument(
            "--run-dir", help="original render directory (default: beside the report)"
        )
        if name == "explain-estimate":
            explain.add_argument(
                "--curve", choices=("raw", "smoothed"), help="choose a displayed curve"
            )
        explain.set_defaults(handler=_explain_observation, observation_command=name)

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
