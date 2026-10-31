"""Owned PDF visual-inspection history, separate from native scientific audits."""

from __future__ import annotations

import copy
import json
import re
import subprocess
import sys
from pathlib import Path

from .audit import _run
from .project import (
    MAX_SOURCE_BYTES,
    ProjectError,
    _bytes,
    _capture,
    _config,
    _digest,
    _event,
    _execution_source,
    _finish,
    _hash,
    _inside,
    _locator,
    _operation,
    _review_token,
    project_history,
    project_status,
)

MAX_PDF_BYTES = 50 * 1024 * 1024
SOURCE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")


def _source(path):
    if not isinstance(path, (str, Path)) or "://" in str(path):
        raise ProjectError("Choose an explicit local PDF path.")
    file = Path(path).expanduser().resolve()
    if not file.is_file() or file.stat().st_size > MAX_PDF_BYTES:
        raise ProjectError("Choose a local PDF no larger than 50 MiB.")
    with file.open("rb") as stream:
        if stream.read(5) != b"%PDF-":
            raise ProjectError("The selected file is not a PDF.")
    return file, _digest(file)


def _visual_report(report, digest):
    if (
        not isinstance(report, dict)
        or report.get("scope") != "source-free PDF visual metrics and review"
        or report.get("status") != "incomplete"
        or report.get("exit_code") != 2
        or not isinstance(report.get("source"), dict)
        or report["source"].get("sha256") != digest
        or not isinstance(report.get("checks"), list)
        or not all(
            isinstance(item, dict)
            and isinstance(item.get("name"), str)
            and isinstance(item.get("status"), str)
            for item in report["checks"]
        )
    ):
        return False
    required = {item["name"]: item["status"] for item in report["checks"]}
    return len(required) == len(report["checks"]) and all(
        required.get(name) == "untested"
        for name in ("source_data", "numerical_claims", "visual_interpretation")
    )


def project_inspections(path="."):
    """Read current PDF source hashes and separately verified saved visual assets."""
    config_path, config = _config(path)
    paper = (config_path.parent / config["manifest"]).resolve().parent
    current = project_status(path)
    history = project_history(path)
    rows = []
    seen = set()
    for event in history["events"]:
        if not event["integrity"] or event.get("action") != "inspection":
            continue
        result = event["result"]
        source = result.get("inspection_source")
        if (
            not isinstance(source, dict)
            or not isinstance(source.get("id"), str)
            or not SOURCE_ID.fullmatch(source["id"])
            or not isinstance(source.get("path"), str)
            or not isinstance(source.get("sha256"), str)
            or not re.fullmatch("[0-9a-f]{64}", source["sha256"])
            or result.get("status") not in {"failed", "incomplete"}
            or result.get("exit_code") != 2
        ):
            raise ProjectError("Saved inspection has an invalid source identity.")
        if source["id"] in seen:
            continue
        seen.add(source["id"])
        errors = copy.deepcopy(result.get("errors", []))
        if not isinstance(errors, list) or not all(isinstance(e, str) for e in errors):
            raise ProjectError("Saved inspection errors must be text records.")
        observed = None
        try:
            _, observed = _source(paper / source["path"])
        except (OSError, ValueError) as problem:
            errors.append(str(problem))
        report = result.get("inspection")
        if report is not None and not _visual_report(report, source["sha256"]):
            raise ProjectError("Saved PDF inspection is not scoped incomplete visual evidence.")
        assets = copy.deepcopy(result.get("inspection_assets", []))
        if not isinstance(assets, list):
            raise ProjectError("Saved visual-inspection assets must be an inventory.")
        verified = bool(report and assets)
        if verified:
            try:
                folder = _inside(Path(current["config"]).parent, "history/" + event["id"])
                for asset in assets:
                    file = _inside(folder, asset["path"])
                    if file.stat().st_size != asset["bytes"] or _digest(file) != asset["sha256"]:
                        raise ProjectError("Saved visual-inspection asset changed.")
            except (OSError, ValueError, KeyError, TypeError) as problem:
                errors.append(str(problem))
                verified = False
        rows.append(
            {
                "id": source["id"],
                "path": source["path"],
                "recorded_sha256": source["sha256"],
                "current_sha256": observed,
                "freshness": "unchanged"
                if observed == source["sha256"]
                else "changed"
                if observed
                else "unavailable",
                "event": event["id"],
                "operation_status": result["status"],
                "science_status": "untested",
                "assets_verified": verified,
                "evidence_state": "saved_visual_evidence"
                if report
                and verified
                and not errors
                and observed == source["sha256"]
                and history["integrity"] == "verified"
                and result["status"] == "incomplete"
                else "historical_or_needs_inspection",
                "inspection": copy.deepcopy(report),
                "assets": assets,
                "errors": errors,
                "raw_source_copied": False,
            }
        )
    after = project_status(path)
    later = project_history(path)
    if (after["revision"], [(e["id"], e["integrity"]) for e in later["events"]]) != (
        current["revision"],
        [(e["id"], e["integrity"]) for e in history["events"]],
    ):
        raise ProjectError("Project inputs/history changed while reading inspections; refresh.")
    revision = _hash(
        {
            "project_id": current["project_id"],
            "native_revision": current["revision"],
            "events": [(e["id"], e["integrity"]) for e in history["events"]],
            "sources": [
                {k: r[k] for k in ("id", "current_sha256", "event", "assets_verified", "errors")}
                for r in rows
            ],
        }
    )
    return {
        "schema_version": 1,
        "query_status": "ok" if history["integrity"] == "verified" else "partial",
        "project_id": current["project_id"],
        "revision": revision,
        "native_revision": current["revision"],
        "history_integrity": history["integrity"],
        "sources": rows,
        "scope": "Source-free PDF visual evidence only. Numerical claims/data remain untested; no native programs execute during this query.",
    }


def inspect_project_pdf(
    path, pdf, *, identity, expected_revision, pages=None, dpi=144, timeout=120
):
    """Prepare real bounded visual evidence; never convert it to scientific acceptance."""
    _review_token(expected_revision)
    if not isinstance(identity, str) or not SOURCE_ID.fullmatch(identity):
        raise ProjectError(
            "Choose a source ID of 1-64 letters, digits, underscores, dots or hyphens."
        )
    if type(dpi) is not int or not 72 <= dpi <= 300:
        raise ProjectError("PDF DPI must be an integer between 72 and 300.")
    if type(timeout) not in (int, float) or not 0 < timeout <= 600:
        raise ProjectError("PDF timeout must be positive and no more than 600 seconds.")
    if pages is not None and (
        not isinstance(pages, list)
        or not pages
        or len(pages) > 50
        or any(type(p) is not int or p < 1 for p in pages)
    ):
        raise ProjectError("Choose one to 50 positive one-based PDF pages.")
    source, config = _config(path)
    with _operation(source.parent):
        before = project_inspections(source)
        if before["revision"] != expected_revision:
            raise ProjectError(
                "Project/inspection evidence changed since review; refresh before inspecting."
            )
        if before["history_integrity"] != "verified":
            raise ProjectError(
                "Repair incomplete/damaged project history before adding an inspection."
            )
        snapshot, _, originals = _capture(source, config)
        if any(item["id"] == identity for item in snapshot["figures"]):
            raise ProjectError("An inspection source ID must differ from native figure IDs.")
        file, digest = _source(pdf)
        paper = (source.parent / config["manifest"]).resolve().parent
        execution_source = _execution_source()
        folder, event = _event(source.parent, "inspection")
        result = {
            "status": "failed",
            "exit_code": 2,
            "snapshot": snapshot,
            "audit": None,
            "errors": [],
            "execution_source": execution_source,
            "inspection_source": {"id": identity, "path": _locator(file, paper), "sha256": digest},
            "inspection": None,
            "inspection_assets": [],
            "raw_source_copied": False,
        }
        command = [
            sys.executable,
            "-m",
            "graphunslopify.cli",
            "audit-pdf",
            str(file),
            "--out-dir",
            str(folder / "packet"),
            "--dpi",
            str(dpi),
        ]
        if pages is not None:
            command.extend(["--pages", *map(str, pages)])
        try:
            completed = _run(command, folder, timeout)
            originals["inspection.stdout.log"] = completed.stdout.encode()
            originals["inspection.stderr.log"] = completed.stderr.encode()
            report = json.loads(completed.stdout)
            if not _visual_report(report, digest) or completed.returncode != 2:
                raise ProjectError(
                    "PDF preparation did not return strict incomplete visual evidence."
                )
            _bytes(report)
            packet = _inside(folder, "packet")
            recorded = json.loads(_inside(packet, "pdf-review.json").read_text(encoding="utf8"))
            if recorded != report:
                raise ProjectError("Saved PDF report and actual worker output disagree.")
            result["inspection"] = report
            for artifact in sorted(packet.rglob("*")):
                if artifact.is_symlink():
                    raise ProjectError("Inspection assets cannot be symlinks.")
                if artifact.is_file():
                    name = artifact.relative_to(folder).as_posix()
                    _inside(folder, name)
                    result["inspection_assets"].append(
                        {
                            "path": name,
                            "bytes": artifact.stat().st_size,
                            "sha256": _digest(artifact),
                        }
                    )
            if (
                _source(file)[1] != digest
                or _capture(source, _config(source)[1])[0]["revision"] != snapshot["revision"]
                or _execution_source() != execution_source
            ):
                raise ProjectError(
                    "PDF/project/execution sources changed during inspection; rerun."
                )
            result["status"] = "incomplete"
        except subprocess.TimeoutExpired as problem:
            for name, content in (("stdout", problem.stdout), ("stderr", problem.stderr)):
                originals[f"inspection.{name}.log"] = (
                    content.encode() if isinstance(content, str) else content or b""
                )
            result["errors"].append(
                f"PDF visual inspection exceeded {timeout:g} seconds; partial files retained."
            )
        except (OSError, ValueError, KeyError, TypeError) as problem:
            result["errors"].append(f"{type(problem).__name__}: {problem}")
        if len(_bytes(result)) > MAX_SOURCE_BYTES:
            result["inspection"] = None
            result["inspection_assets"] = []
            result["errors"].append("PDF visual metadata exceeds the 20 MiB project limit.")
            result["status"] = "failed"
        return _finish(folder, event, result, originals)
