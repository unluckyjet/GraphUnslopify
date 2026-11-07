"""Run a paper's strict audit and organize its current review evidence."""

from __future__ import annotations

import hashlib
import os
from collections import Counter
from pathlib import Path
from tempfile import NamedTemporaryFile

from .project import ProjectError, _config, run_project
from .project_review import project_review

_PRIORITY = {"error": 0, "evidence_gap": 1, "warning": 2}


def summarize_paper(review, *, run_event=None):
    """Index every current figure and preserve references to its recorded results."""
    native = review["native_run"]
    if run_event is not None and (not native or native["id"] != run_event):
        raise ProjectError("A different audit is current. Refresh the paper before exporting.")
    inputs_match = review["selection"]["matches_current_revision"]
    figures, issues = [], []
    for index, row in enumerate(review["figures"]):
        pdf = row["source_type"] == "pdf"
        key = row["key"] if pdf else "native:" + row["id"]
        root = f"/review/figures/{index}"

        def record(priority, code, message, path, *, figure=key, prefix=root):
            issues.append(
                {
                    "priority": priority,
                    "code": code,
                    "message": message,
                    "figure": figure,
                    "evidence_pointer": prefix + path,
                }
            )

        evidence = row["evidence_state"]
        groups = row["groups"]
        if pdf:
            record(
                "evidence_gap",
                "pdf_claims_untested",
                groups["claims"]["reason"],
                "/groups/claims",
            )
            if evidence != "saved_visual_evidence":
                record(
                    "evidence_gap",
                    "pdf_visual_evidence_unavailable",
                    "Current PDF visual evidence needs inspection.",
                    "/evidence_state",
                )
            findings = [
                (finding, f"/groups/legibility/pages/{page}/visual/findings/{item}")
                for page, inspected in enumerate(groups["legibility"].get("pages", []))
                for item, finding in enumerate((inspected.get("visual") or {}).get("findings", []))
            ]
        else:
            if evidence in ("not_run", "unavailable") or not inputs_match:
                record(
                    "evidence_gap",
                    "native_evidence_unavailable",
                    "Current figure inputs need an intact saved audit.",
                    "/evidence_state",
                )
            elif run_event is not None:
                evidence = "current_audit_run"
            for item, claim in enumerate(groups["claims"].get("items", [])):
                verdict = claim.get("verdict")
                if verdict in ("fails", "untested"):
                    record(
                        "error" if verdict == "fails" else "evidence_gap",
                        "recorded_claim_failed"
                        if verdict == "fails"
                        else "recorded_claim_untested",
                        claim.get("detail") or "A recorded numerical claim needs review.",
                        f"/groups/claims/items/{item}",
                    )
            for item, check in enumerate(groups["claims"].get("untested", [])):
                record(
                    "evidence_gap",
                    "recorded_check_untested",
                    check,
                    f"/groups/claims/untested/{item}",
                )
            findings = [
                (finding, f"/groups/legibility/findings/{item}")
                for item, finding in enumerate(groups["legibility"].get("findings", []))
            ]
        for finding, pointer in findings:
            severity = finding.get("severity")
            if severity in ("error", "warning"):
                record(severity, finding["code"], finding["message"], pointer)
        for field in ("errors", "audit_errors", "policy_errors"):
            for item, error in enumerate(row.get(field, [])):
                record("error", field, str(error), f"/{field}/{item}")
        figures.append(
            {
                "key": key,
                "name": row.get("name", row["id"]),
                "source_type": row["source_type"],
                "evidence_state": evidence,
                "recorded_outcome": row["execution_status"],
            }
        )
    issues.sort(key=lambda item: _PRIORITY[item["priority"]])
    counts = Counter(item["priority"] for item in issues)
    native_exit = native["exit_code"] if native else None
    failed = counts["error"] > 0 or (native is not None and native["status"] == "failed")
    incomplete = (
        not figures
        or counts["evidence_gap"] > 0
        or review["query_status"] != "ok"
        or native_exit == 2
    )
    return {
        "schema_version": 1,
        "kind": "graphunslopify.paper-audit",
        "status": "failed" if failed else "incomplete" if incomplete else "checked",
        "exit_code": 2 if failed or incomplete else 0,
        "evidence_revision": review["evidence_revision"],
        "execution": "fresh_native_audit" if run_event else "saved_evidence",
        "native_audit_event": native["id"] if native else None,
        "native_exit_code": native_exit,
        "figure_count": len(figures),
        "counts": {level: counts[level] for level in _PRIORITY},
        "figures": figures,
        "issues": issues,
        "scope": "Recorded strict findings and current evidence gaps. PDF numerical claims remain untested. Scientific judgment remains with the author.",
    }


def _review_paper(source, review, requests, *, consent, api_key):
    from .review_agent import read_document, restore_plan

    if consent is not True:
        raise ProjectError("Review each exact provider request and explicitly consent to send it.")
    expected = {row["key"] for row in review["figures"]}
    covered = set()
    batches = []
    for request_path, digest in requests:
        document = read_document(request_path)
        disclosure, selection = document["disclosure"], document["selection"]
        if (
            selection["event_id"] is not None
            or disclosure.get("binding") != review["evidence_revision"]
            or disclosure.get("consent_sha256") != digest
        ):
            raise ProjectError(
                "Review the exact current paper request and its consent digest again."
            )
        plan = restore_plan(document, source, api_key=api_key)
        keys = set(selection["figures"])
        if covered & keys:
            raise ProjectError(
                "Each current figure must be covered by exactly one reviewed request."
            )
        covered.update(keys)
        batches.append((selection["figures"], plan, digest))
    if not expected or covered != expected:
        raise ProjectError("The reviewed requests must cover every current figure before sending.")

    results = []
    for figures, plan, digest in batches:
        record = {"figures": figures, "request_sha256": plan.disclosure()["request_sha256"]}
        try:
            record.update(
                status="completed", review=plan.request(consent=True, consent_sha256=digest)
            )
        except (OSError, ValueError) as problem:
            if project_review(source)["evidence_revision"] != review["evidence_revision"]:
                raise ProjectError("Paper evidence changed during qualitative review.") from problem
            record.update(status="unavailable", error=str(problem))
        results.append(record)
    return results


def audit_paper(
    path,
    output,
    *,
    saved_evidence=False,
    expected_revision=None,
    timeout=120,
    reviewed_requests=(),
    consent=False,
    api_key="",
):
    """Save a portable report over the whole paper and keep failed outcomes visible."""
    from .project_export import create_review_packet

    source, config = _config(path)
    destination = Path(output).expanduser().absolute()
    if destination.is_symlink() or destination.resolve().is_relative_to(source.parent):
        raise ProjectError("Choose a new output outside the owned project evidence folder.")
    if destination.exists() or not destination.parent.is_dir():
        raise ProjectError("Choose a new output file in an existing directory.")
    if reviewed_requests and not saved_evidence:
        raise ProjectError("Use saved evidence when sending reviewed model requests.")
    run_event = None
    if not saved_evidence and config.get("mode") != "review_only":
        run = run_project(source, expected_revision=expected_revision, timeout=timeout)
        run_event = run["id"]
    review = project_review(source)
    if (
        run_event is None
        and expected_revision is not None
        and review["current_revision"] != expected_revision
    ):
        raise ProjectError("Project inputs changed. Refresh before collecting the audit.")
    summary = summarize_paper(review, run_event=run_event)
    qualitative = (
        _review_paper(source, review, reviewed_requests, consent=consent, api_key=api_key)
        if reviewed_requests
        else []
    )
    data = create_review_packet(
        source,
        expected_revision=summary["evidence_revision"],
        paper_audit=True,
        run_event=run_event,
        qualitative=qualitative,
    )
    with NamedTemporaryFile(dir=destination.parent, prefix=".paper-audit-", delete=False) as file:
        temporary = Path(file.name)
        try:
            file.write(data)
            file.close()
            os.link(temporary, destination)
        finally:
            temporary.unlink()
    partial = any(row["status"] != "completed" for row in qualitative)
    return {
        **summary,
        "output": str(destination),
        "sha256": hashlib.sha256(data).hexdigest(),
        "qualitative_status": "partial"
        if partial
        else "completed"
        if qualitative
        else "not_requested",
        "exit_code": 2 if partial else summary["exit_code"],
    }
