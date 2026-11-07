"""Arrange recorded findings and role recommendations for author review."""

from __future__ import annotations

DISPOSITIONS = ("request_change", "needs_evidence", "no_change_proposed")
_PRIORITY = {"recorded_failure": 0, "evidence_gap": 1, "recorded_warning": 2}


def _flag(role, priority, code, pointer):
    return {"role": role, "priority": priority, "code": code, "evidence_pointer": pointer}


def _recorded_flags(row, root):
    if row["recorded_outcome"] == "failed":
        yield _flag(
            "recorded_audit", "recorded_failure", "execution_failed", root + "/recorded_outcome"
        )
    if row["evidence_state"] in (
        "historical_or_needs_audit",
        "historical_or_needs_inspection",
        "current_inputs_rerun_recommended",
    ):
        yield _flag(
            "recorded_audit", "evidence_gap", "recheck_saved_evidence", root + "/evidence_state"
        )
    readability = row["readability"]
    if readability["state"] == "unavailable":
        yield _flag("readability", "evidence_gap", "inspection_unavailable", root + "/readability")
    for index, finding in enumerate(readability.get("findings", [])):
        severity = finding.get("severity")
        if severity in ("error", "warning"):
            priority = "recorded_failure" if severity == "error" else "recorded_warning"
            yield _flag(
                "readability", priority, finding["code"], f"{root}/readability/findings/{index}"
            )

    claims = row["statistical_claims"]["claims"]
    claims_path = root + "/statistical_claims/claims"
    if claims["state"] in ("untested", "unavailable"):
        yield _flag("statistical_claims", "evidence_gap", claims["state"], claims_path)
    for index, claim in enumerate(claims.get("items", [])):
        verdict = claim.get("verdict")
        if verdict in ("fails", "untested"):
            priority = "recorded_failure" if verdict == "fails" else "evidence_gap"
            yield _flag("statistical_claims", priority, verdict, f"{claims_path}/items/{index}")
    for index, _ in enumerate(claims.get("untested", [])):
        yield _flag(
            "statistical_claims",
            "evidence_gap",
            "check_untested",
            f"{claims_path}/untested/{index}",
        )

    formatting = row["journal_formatting"]
    formatting_path = root + "/journal_formatting"
    if formatting["state"] != "recorded":
        yield _flag("journal_formatting", "evidence_gap", formatting["state"], formatting_path)
    for index, export in enumerate(formatting["exports"]):
        export_path = f"{formatting_path}/exports/{index}"
        if export["state"] == "unavailable":
            yield _flag("journal_formatting", "evidence_gap", "export_unavailable", export_path)
        for number, check in enumerate(export.get("report", {}).get("checks", [])):
            if check["status"] in ("failed", "unavailable"):
                priority = "recorded_failure" if check["status"] == "failed" else "evidence_gap"
                yield _flag(
                    "journal_formatting",
                    priority,
                    check["code"],
                    f"{export_path}/report/checks/{number}",
                )


def _next_step(flags, dispositions, mixed, current):
    if not current:
        return "refresh_current_evidence"
    if any(row["priority"] == "recorded_failure" for row in flags):
        return "resolve_recorded_failures"
    if any(row["priority"] == "evidence_gap" for row in flags) or "needs_evidence" in dispositions:
        return "gather_missing_evidence"
    if mixed:
        return "compare_role_recommendations"
    if "request_change" in dispositions:
        return "consider_requested_changes"
    return "author_review"


def summarize_roles(panel, results, *, current):
    by_figure = {row["figure_key"]: [] for row in panel["figures"]}
    for role, result in results.items():
        for index, assessment in enumerate(
            result.get("qualitative", {}).get("content", {}).get("figure_assessments", [])
        ):
            by_figure[assessment["figure_key"]].append(
                {
                    "role": role,
                    "disposition": assessment["disposition"],
                    "assessment_pointer": f"/role_reviews/{role}/qualitative/content/figure_assessments/{index}",
                }
            )
    figures = []
    for index, row in enumerate(panel["figures"]):
        key = row["figure_key"]
        root = f"/deterministic_evidence/figures/{index}"
        flags = sorted(_recorded_flags(row, root), key=lambda item: _PRIORITY[item["priority"]])
        assessments = by_figure[key]
        dispositions = {item["disposition"] for item in assessments}
        mixed = len(dispositions) > 1
        figures.append(
            {
                "figure_key": key,
                "recorded_priorities": flags,
                "role_assessments": assessments,
                "different_role_recommendations": mixed,
                "next_author_step": _next_step(flags, dispositions, mixed, current),
            }
        )
    return {
        "figures": figures,
        "unavailable_roles": [
            role for role, result in results.items() if result["status"] != "completed"
        ],
        "scope": "Compare recommendations within their roles and inspect the recorded evidence before making changes.",
    }
