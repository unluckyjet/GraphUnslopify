"""Owned PDF visual-inspection history, separate from native scientific audits."""

from __future__ import annotations

import contextlib
import copy
import hashlib
import json
import re
import subprocess
import sys
import uuid
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


def _inspection_source(event):
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
        or not isinstance(source.get("name", ""), str)
        or len(source.get("name", "")) > 255
        or source.get("origin", "local_reference") not in {"local_reference", "uploaded_local_copy"}
    ):
        raise ProjectError("Saved inspection has an invalid source identity.")
    return source


def _inspection_row(event, paper, folder_root, history_integrity, *, historical=False):
    result = event["result"]
    source = _inspection_source(event)
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
            folder = _inside(folder_root, "history/" + event["id"])
            for asset in assets:
                file = _inside(folder, asset["path"])
                if file.stat().st_size != asset["bytes"] or _digest(file) != asset["sha256"]:
                    raise ProjectError("Saved visual-inspection asset changed.")
        except (OSError, ValueError, KeyError, TypeError) as problem:
            errors.append(str(problem))
            verified = False
    return {
        "id": source["id"],
        "path": source["path"],
        "name": source.get("name", Path(source["path"]).name),
        "origin": source.get("origin", "local_reference"),
        "explicit_history_selection": historical,
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
        if not historical
        and report
        and verified
        and not errors
        and observed == source["sha256"]
        and history_integrity == "verified"
        and result["status"] == "incomplete"
        else "historical_or_needs_inspection",
        "inspection": copy.deepcopy(report),
        "assets": assets,
        "errors": errors,
        "raw_source_copied": False,
    }


def project_inspections(path=".", *, event_id=None):
    """Read current sources or an explicitly historical inspection; never execute plots."""
    config_path, _ = _config(path)
    paper = config_path.parent.parent
    current = project_status(path)
    history = project_history(path)
    rows = []
    seen = set()
    for event in history["events"]:
        if not event["integrity"] or event.get("action") != "inspection":
            continue
        source = _inspection_source(event)
        if source["id"] in seen:
            continue
        seen.add(source["id"])
        rows.append(_inspection_row(event, paper, config_path.parent, history["integrity"]))
    selected = None
    if event_id is not None:
        selected = next((event for event in history["events"] if event["id"] == event_id), None)
        if not selected or not selected["integrity"] or selected.get("action") != "inspection":
            raise ProjectError("Choose an intact completed PDF inspection event.")
        selected_rows = [
            _inspection_row(
                selected, paper, config_path.parent, history["integrity"], historical=True
            )
        ]
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
        "sources": selected_rows if selected else rows,
        "selection": {"event": event_id, "explicit_history_selection": event_id is not None},
        "scope": "Source-free PDF visual evidence only. Numerical claims/data remain untested; no native programs execute during this query.",
    }


def _inspection_options(identity, expected_revision, pages, dpi, timeout):
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


def inspect_project_pdf(
    path,
    pdf,
    *,
    identity,
    expected_revision,
    pages=None,
    dpi=144,
    timeout=120,
    source_name=None,
    source_origin="local_reference",
):
    """Prepare real bounded visual evidence; never convert it to scientific acceptance."""
    _inspection_options(identity, expected_revision, pages, dpi, timeout)
    if source_name is not None and (
        not isinstance(source_name, str)
        or not source_name
        or len(source_name) > 255
        or any(ord(char) < 32 for char in source_name)
    ):
        raise ProjectError("Choose a source display name of 1-255 printable characters.")
    if source_origin not in {"local_reference", "uploaded_local_copy"}:
        raise ProjectError("Unknown PDF source origin.")
    source, config = _config(path)
    with _operation(source.parent):
        return _inspect_locked(
            source,
            config,
            pdf,
            identity=identity,
            expected_revision=expected_revision,
            pages=pages,
            dpi=dpi,
            timeout=timeout,
            source_name=source_name,
            source_origin=source_origin,
        )


def _inspect_locked(
    source,
    config,
    pdf,
    *,
    identity,
    expected_revision,
    pages,
    dpi,
    timeout,
    source_name,
    source_origin,
):
    before = project_inspections(source)
    if before["revision"] != expected_revision:
        raise ProjectError(
            "Project/inspection evidence changed since review; refresh before inspecting."
        )
    if before["history_integrity"] != "verified":
        raise ProjectError("Repair incomplete/damaged project history before adding an inspection.")
    snapshot, _, originals = _capture(source, config)
    if any(item["id"] == identity for item in snapshot["figures"]):
        raise ProjectError("An inspection source ID must differ from native figure IDs.")
    file, digest = _source(pdf)
    if (
        snapshot["revision"] != before["native_revision"]
        or project_inspections(source)["revision"] != expected_revision
    ):
        raise ProjectError(
            "Project/inspection evidence changed during capture; refresh before inspecting."
        )
    paper = source.parent.parent
    execution_source = _execution_source()
    folder, event = _event(source.parent, "inspection")
    result = {
        "status": "failed",
        "exit_code": 2,
        "snapshot": snapshot,
        "audit": None,
        "errors": [],
        "execution_source": execution_source,
        "inspection_source": {
            "id": identity,
            "path": _locator(file, paper),
            "sha256": digest,
            "name": source_name or file.name,
            "origin": source_origin,
        },
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
        if isinstance(report, dict) and isinstance(report.get("error"), str):
            raise ProjectError("PDF preparation failed: " + report["error"][:4000])
        if not _visual_report(report, digest) or completed.returncode != 2:
            raise ProjectError("PDF preparation did not return strict incomplete visual evidence.")
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
            raise ProjectError("PDF/project/execution sources changed during inspection; rerun.")
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


def inspect_uploaded_pdf(
    path, data, *, identity, expected_revision, name, pages=None, dpi=144, timeout=120
):
    """Retain an explicitly uploaded local source copy; only derived assets enter history."""
    _inspection_options(identity, expected_revision, pages, dpi, timeout)
    if (
        not isinstance(data, bytes)
        or not 0 < len(data) <= MAX_PDF_BYTES
        or not data.startswith(b"%PDF-")
    ):
        raise ProjectError("Upload a PDF no larger than 50 MiB.")
    if not isinstance(name, str) or not name or len(name) > 255 or any(ord(c) < 32 for c in name):
        raise ProjectError("Choose a source display name of 1-255 printable characters.")
    source, config = _config(path)
    with _operation(source.parent):
        before = project_inspections(source)
        if before["revision"] != expected_revision or before["history_integrity"] != "verified":
            raise ProjectError(
                "Project/inspection evidence changed since review; refresh before uploading."
            )
        # An exclusive nested ignore file also protects uploads in older projects.
        # No existing ignore/configuration file is rewritten.
        parent = _inside(source.parent, "sources")
        parent.mkdir(exist_ok=True)
        folder = _inside(source.parent, "sources/" + uuid.uuid4().hex)
        folder.mkdir()
        ignored = _inside(folder, ".gitignore")
        file = _inside(folder, "source.pdf")
        try:
            with ignored.open("xb") as stream:
                stream.write(b"*\n")
            with file.open("xb") as stream:
                stream.write(data)
            return _inspect_locked(
                source,
                config,
                file,
                identity=identity,
                expected_revision=expected_revision,
                pages=pages,
                dpi=dpi,
                timeout=timeout,
                source_name=name,
                source_origin="uploaded_local_copy",
            )
        except (OSError, ValueError, KeyError, TypeError):
            # Only our exclusive two files are eligible for cleanup; never recurse
            # through a changed folder or remove another writer's additions.
            for item in (file, ignored):
                with contextlib.suppress(OSError, ValueError):
                    _inside(source.parent, item.relative_to(source.parent).as_posix()).unlink(
                        missing_ok=True
                    )
            with contextlib.suppress(OSError):
                folder.rmdir()
            raise


def inspection_asset(path, event_id, index):
    """Return an actual inventoried saved asset, with an independent read-byte guard."""
    result = project_inspections(path, event_id=event_id)
    row = result["sources"][0]
    if not row["assets_verified"] or type(index) is not int or not 0 <= index < len(row["assets"]):
        raise ProjectError("Choose an asset from an intact saved PDF visual packet.")
    entry = row["assets"][index]
    source, _ = _config(path)
    file = _inside(source.parent, "history/" + event_id + "/" + entry["path"])
    data = file.read_bytes()
    if len(data) != entry["bytes"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
        raise ProjectError("Saved PDF visual asset changed while being read.")
    return data, file.name
