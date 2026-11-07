"""Collect separate deterministic evidence for three paper review roles."""

from __future__ import annotations

from pathlib import Path

from .journal import journal_profiles
from .journal_workspace import inspect_export
from .project import ProjectError, _config, _hash, _inside, project_history
from .project_review import project_review

_FORMATS = {".png", ".pdf", ".svg", ".jpg", ".jpeg", ".tif", ".tiff", ".eps", ".gif"}


def _selected(review, figures):
    rows = review["figures"]
    if figures is None:
        return rows
    if (
        not isinstance(figures, (list, tuple))
        or not figures
        or not all(isinstance(key, str) for key in figures)
        or len(set(figures)) != len(figures)
    ):
        raise ProjectError("Choose distinct current figure keys for the review panel.")
    by_key = {row["key"]: row for row in rows}
    if set(figures) - by_key.keys():
        raise ProjectError("Choose only figure keys in the current paper review.")
    return [by_key[key] for key in figures]


def _native_exports(source, review):
    selection = review["native_run"]
    if selection is None:
        return {}
    event = next(
        (row for row in project_history(source)["events"] if row["id"] == selection["id"]),
        None,
    )
    if not event or not event["integrity"] or event["action"] != "run":
        raise ProjectError("Saved audit evidence changed during panel review. Refresh and retry.")
    root = _inside(source.parent, f"history/{event['id']}/audit")
    return {
        row["id"]: [
            (root, item)
            for item in row.get("outputs", [])
            if Path(item["path"]).suffix.lower() in _FORMATS
        ]
        for row in (event["result"].get("audit") or {}).get("figures", [])
    }


def _pdf_export(source, row):
    inspection = row["inspection"]
    if inspection["freshness"] != "unchanged" or not inspection["recorded_sha256"]:
        return []
    path = (source.parent.parent / inspection["path"]).resolve()
    return [
        (
            None,
            {
                "path": str(path),
                "sha256": inspection["recorded_sha256"],
                "bytes": path.stat().st_size,
            },
        )
    ]


def _formatting(source, row, exports, profile):
    if profile is None:
        return {"state": "profile_required", "exports": []}
    try:
        candidates = (
            _pdf_export(source, row) if row["source_type"] == "pdf" else exports.get(row["id"], [])
        )
    except OSError:
        candidates = []
    results = []
    for root, expected in candidates:
        name = Path(expected["path"]).name
        try:
            path = _inside(root, expected["path"]) if root is not None else Path(expected["path"])
            report = inspect_export(path, expected, {"profile": profile})
        except (OSError, ValueError) as problem:
            results.append({"name": name, "state": "unavailable", "reason": str(problem)})
        else:
            results.append(
                {
                    "name": name,
                    "state": "checked",
                    "sha256": expected["sha256"],
                    "report": {
                        key: report[key]
                        for key in ("status", "checks", "manual_review", "profile_sha256", "as_of")
                    },
                }
            )
    checked = any(row["state"] == "checked" for row in results)
    return {"state": "recorded" if checked else "evidence_unavailable", "exports": results}


def paper_review_panel(path=".", *, journal_profile=None, figures=None, expected_revision=None):
    """Read figure evidence and check saved export bytes under the selected profile."""
    profile = next((row for row in journal_profiles() if row["id"] == journal_profile), None)
    if journal_profile is not None and profile is None:
        raise ProjectError("Choose a supported journal profile for the formatting role.")
    source, _ = _config(path)
    review = project_review(source)
    evidence_revision = review["evidence_revision"]
    if expected_revision is not None and expected_revision != evidence_revision:
        raise ProjectError("Paper evidence changed. Refresh before collecting the panel.")
    selected = _selected(review, figures)
    exports = _native_exports(source, review) if journal_profile is not None else {}
    rows = []
    for row in selected:
        groups = row["groups"]
        rows.append(
            {
                "figure_key": row["key"],
                "source_type": row["source_type"],
                "evidence_state": row["evidence_state"],
                "recorded_outcome": row["execution_status"],
                "readability": groups["legibility"],
                "statistical_claims": {
                    "claims": groups["claims"],
                    "uncertainty": groups["uncertainty"],
                },
                "journal_formatting": _formatting(source, row, exports, journal_profile),
            }
        )
    if project_review(source)["evidence_revision"] != evidence_revision:
        raise ProjectError("Paper evidence changed while collecting the panel. Refresh and retry.")
    result = {
        "schema_version": 1,
        "kind": "graphunslopify.paper-review-panel",
        "project_id": review["project_id"],
        "evidence_revision": evidence_revision,
        "matches_current_native_revision": review["selection"]["matches_current_revision"],
        "journal_profile": profile,
        "figures": rows,
        "model_review": "not_requested",
        "scope": "Recorded figure checks and technical journal measurements. Scientific interpretation remains with the author.",
    }
    return {**result, "panel_revision": _hash(result)}
