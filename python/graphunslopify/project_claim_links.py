"""Bind author-selected text to a current deterministic paper figure check."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from .experiment_imports import _contained_bytes
from .project import (
    ProjectError,
    _atomic,
    _capture,
    _config,
    _execution_source,
    _hash,
    _inside,
    _native,
    _operation,
    _read,
    _review_token,
    project_history,
    project_status,
)

_LEDGER = "claim-links.json"
_MAX_LINKS = 128
_MAX_TEXT = 2_000
_MAX_MANUSCRIPT = 2 * 1024**2
_TEXT_SUFFIXES = {".md", ".markdown", ".tex", ".txt"}
_TARGET_FIELDS = {"kind", "subject", "reference", "tolerance", "metric", "panel_name"}
_SCOPE = (
    "The author attests that the exact excerpt expresses the selected figure check. "
    "Results apply to that check and its recorded inputs. Free-form text interpretation remains manual."
)


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _anchor(value):
    if not isinstance(value, dict) or value.get("kind") not in ("caption", "manuscript"):
        raise ProjectError("Choose an exact caption or manuscript excerpt.")
    fields = {"kind", "text"} | ({"path"} if value["kind"] == "manuscript" else set())
    if set(value) != fields:
        raise ProjectError("A text anchor requires kind, excerpt and a path for manuscript text.")
    text = value["text"]
    if not isinstance(text, str) or not text.strip() or len(text) > _MAX_TEXT or "\x00" in text:
        raise ProjectError("Choose a nonempty excerpt of at most 2,000 characters.")
    if value["kind"] == "manuscript":
        name = value["path"]
        if (
            not isinstance(name, str)
            or not 0 < len(name) <= 512
            or Path(name).suffix.lower() not in _TEXT_SUFFIXES
            or "\x00" in name
        ):
            raise ProjectError(
                "Choose a project-relative Markdown, LaTeX or plain text manuscript."
            )
    return value


def _ledger(source, project_id):
    path = _inside(source.parent, _LEDGER)
    state = (
        _read(path)
        if path.exists()
        else {"schema_version": 1, "project_id": project_id, "links": []}
    )
    if (
        not isinstance(state, dict)
        or set(state) != {"schema_version", "project_id", "links"}
        or state["schema_version"] != 1
        or state["project_id"] != project_id
        or not isinstance(state["links"], list)
        or len(state["links"]) > _MAX_LINKS
    ):
        raise ProjectError("The claim-link ledger is invalid or belongs to another project.")
    seen = set()
    for link in state["links"]:
        if (
            not isinstance(link, dict)
            or set(link) != {"id", "figure", "check", "anchor", "confirmed_at", "reviewed_run"}
            or not isinstance(link["figure"], str)
            or not isinstance(link["check"], dict)
            or set(link["check"]) != _TARGET_FIELDS
            or not isinstance(link["confirmed_at"], str)
            or not isinstance(link["reviewed_run"], str)
            or link["id"] != _hash([link["figure"], link["check"], _anchor(link["anchor"])])
            or link["id"] in seen
        ):
            raise ProjectError("The claim-link ledger contains an invalid or duplicate link.")
        seen.add(link["id"])
    return state


def _selected(history):
    # A newer incomplete/damaged operation blocks silent fallback to an older audit.
    return next(
        (
            item
            for item in history["events"]
            if item.get("action") == "run" or not item["integrity"]
        ),
        None,
    )


def _checks(report):
    panels = {panel["index"]: panel for panel in report["panels"]}
    keys = [(panel["name"], panel["metric"]) for panel in panels.values()]
    checks = {}
    duplicates = set()
    for result in report["claims"]:
        panel = panels.get(result["panel"])
        if panel is None or panel["metric"] != result["metric"]:
            continue
        panel_key = panel["name"], panel["metric"]
        if keys.count(panel_key) != 1:
            continue
        check = {key: result.get(key) for key in _TARGET_FIELDS - {"panel_name"}}
        check["panel_name"] = panel["name"]
        identity = _hash(check)
        if identity in checks:
            duplicates.add(identity)
        checks[identity] = {"id": identity, "target": check, "result": result}
    return {identity: item for identity, item in checks.items() if identity not in duplicates}


def _current_figures(status, event, execution_source):
    figures = {}
    result = event["result"] if event and event["integrity"] else {}
    audited = {row["id"]: row for row in (result.get("audit") or {}).get("figures", [])}
    for row in status["figures"]:
        identity = row["id"]
        record = audited.get(identity) or {}
        report = record.get("report") or {}
        data = next((item["sha256"] for item in row["files"] if item["role"] == "data"), None)
        reason = None
        if row["source_type"] != "spec":
            reason = "Claim links require a source-backed JSON figure."
        elif row["freshness"] == "changed":
            reason = "Figure inputs changed since the selected audit."
        elif (
            not event
            or not event["integrity"]
            or row["last_run"] != event["id"]
            or row["freshness"] != "unchanged"
            or not row.get("artifacts_verified")
            or result.get("errors")
            or (result.get("policy_errors") or {}).get(identity)
            or result.get("execution_source") != execution_source
            or (report.get("policy") or {}).get("strict") is not True
            or not data
            or (record.get("data") or {}).get("sha256") != data
            or report.get("data", {}).get("sha256_prefix") != data[:16]
        ):
            reason = "Run a current strict audit with intact native figure evidence."
        checks = _checks(report) if reason is None else {}
        figures[identity] = {
            "reason": reason
            or (None if checks else "This audit has no unambiguous supported claim checks."),
            "checks": checks,
            "evidence": (
                {
                    "event": event["id"],
                    "data_sha256": data,
                    "program_sha256": report["script"]["sha256"],
                    "report_sha256": _hash(report),
                    "exports": [
                        {"format": artifact["format"], "sha256": artifact["sha256"]}
                        for artifact in record["outputs"]
                    ],
                }
                if checks
                else None
            ),
        }
    return figures


def _context(path):
    source, config = _config(path)
    _native(config)
    status = project_status(source)
    snapshot, effective, _ = _capture(source, config)
    history = project_history(source)
    if (
        status["revision"] != snapshot["revision"]
        or history["integrity"] != status["history_integrity"]
        or len(history["events"]) != status["history_count"]
    ):
        raise ProjectError("Project inputs or audit history changed; refresh.")
    event = _selected(history)
    return {
        "source": source,
        "project_revision": snapshot["revision"],
        "project_id": snapshot["project_id"],
        "event": event["id"] if event and event["integrity"] else None,
        "figures": _current_figures(status, event, _execution_source()),
        "captions": {
            row["id"]: row["spec"].get("caption")
            for row in effective["figures"]
            if isinstance(row.get("spec"), dict)
        },
    }


def _locate(context, figure, anchor):
    if anchor["kind"] == "caption":
        text = context["captions"].get(figure)
        if not isinstance(text, str):
            raise ProjectError("The figure no longer has a current caption.")
        raw = text.encode()
    else:
        source = context["source"]
        paper = source.parent.parent
        name = anchor["path"]
        path = _inside(paper, name)
        if path.is_relative_to(source.parent):
            raise ProjectError("Choose a manuscript outside owned project evidence.")
        raw = _contained_bytes(paper, name, limit=_MAX_MANUSCRIPT)
        if len(raw) > _MAX_MANUSCRIPT:
            raise ProjectError("Choose a manuscript of at most 2 MiB.")
        text = raw.decode("utf-8-sig")
    snippet = anchor["text"]
    start = text.find(snippet)
    if start < 0 or text.find(snippet, start + 1) >= 0:
        raise ProjectError("The exact excerpt is absent or occurs more than once.")
    return {
        "source_sha256": _sha(raw),
        "excerpt_sha256": _sha(snippet.encode()),
        "first_line": text.count("\n", 0, start) + 1,
        "last_line": text.count("\n", 0, start + len(snippet.rstrip("\n"))) + 1,
    }


def _evaluate(context, link):
    entry = {**link, "status": "stale_text", "reason": None, "location": None, "check_result": None}
    try:
        entry["location"] = _locate(context, link["figure"], link["anchor"])
    except (OSError, ValueError) as problem:
        entry["reason"] = str(problem)
        return entry
    figure = context["figures"].get(link["figure"])
    check = figure["checks"].get(_hash(link["check"])) if figure else None
    if check is None:
        entry.update(
            status="stale_figure",
            reason=(figure["reason"] if figure else None)
            or "The selected check is absent or ambiguous in the latest figure audit.",
        )
        return entry
    verdict = check["result"]["verdict"]
    entry.update(
        status={"holds": "supported", "fails": "contradiction", "untested": "untested"}[verdict],
        check_result=check["result"],
        evidence=figure["evidence"],
    )
    return entry


def _review(context, ledger, draft):
    if not isinstance(draft, dict) or set(draft) != {"figure", "check", "anchor"}:
        raise ProjectError("Choose a figure, recorded check and exact text anchor.")
    if not isinstance(draft["figure"], str) or not isinstance(draft["check"], str):
        raise ProjectError("Choose a figure and recorded check ID.")
    figure = context["figures"].get(draft["figure"])
    check = figure["checks"].get(draft["check"]) if figure else None
    if check is None:
        raise ProjectError("Choose an unambiguous check from a current strict figure audit.")
    anchor = _anchor(draft["anchor"])
    link = {"figure": draft["figure"], "check": check["target"], "anchor": anchor}
    link["id"] = _hash([link["figure"], link["check"], anchor])
    if any(existing["id"] == link["id"] for existing in ledger["links"]):
        raise ProjectError("This excerpt already links to the selected check.")
    if len(ledger["links"]) >= _MAX_LINKS:
        raise ProjectError("This project already has 128 claim links.")
    location = _locate(context, link["figure"], anchor)
    review = {
        "status": "review_required",
        "link": link,
        "location": location,
        "check_result": check["result"],
        "evidence": figure["evidence"],
        "project_revision": context["project_revision"],
        "links_revision": _hash(ledger),
        "scope": _SCOPE,
    }
    return {**review, "review_sha256": _hash(review)}


def project_claim_links(path="."):
    context = _context(path)
    ledger = _ledger(context["source"], context["project_id"])
    links = [_evaluate(context, item) for item in ledger["links"]]
    return {
        "schema_version": 1,
        "kind": "graphunslopify.claim-links",
        "project_revision": context["project_revision"],
        "links_revision": _hash(ledger),
        "audit": context["event"],
        "figures": [
            {"id": identity, "reason": row["reason"], "checks": list(row["checks"].values())}
            for identity, row in context["figures"].items()
        ],
        "links": links,
        "exit_code": 2 if any(item["status"] != "supported" for item in links) else 0,
        "scope": _SCOPE,
    }


def review_claim_link(path, draft):
    context = _context(path)
    return _review(context, _ledger(context["source"], context["project_id"]), draft)


def save_claim_link(path, draft, *, review_sha256, confirmed):
    if confirmed is not True:
        raise ProjectError("Confirm that the exact excerpt expresses the selected numerical check.")
    _review_token(review_sha256)
    source, config = _config(path)
    with _operation(source.parent):
        context = _context(source)
        if context["project_id"] != config["project_id"]:
            raise ProjectError("Project ownership changed; reopen the intended project.")
        ledger = _ledger(source, context["project_id"])
        review = _review(context, ledger, draft)
        if review["review_sha256"] != review_sha256:
            raise ProjectError("The text, audit or links changed since review; review again.")
        link = {
            **review["link"],
            "confirmed_at": datetime.now(timezone.utc).isoformat(),
            "reviewed_run": review["evidence"]["event"],
        }
        ledger["links"].append(link)
        _atomic(source.parent, _LEDGER, ledger)
        return {
            "status": "linked",
            "link": _evaluate(context, link),
            "links_revision": _hash(ledger),
        }


def remove_claim_link(path, identity, *, links_revision):
    _review_token(links_revision)
    _review_token(identity)
    source, config = _config(path)
    _native(config)
    with _operation(source.parent):
        ledger = _ledger(source, config["project_id"])
        if links_revision != _hash(ledger):
            raise ProjectError("Claim links changed; refresh before removing one.")
        remaining = [link for link in ledger["links"] if link["id"] != identity]
        if len(remaining) == len(ledger["links"]):
            raise ProjectError("Choose an existing claim link.")
        ledger["links"] = remaining
        _atomic(source.parent, _LEDGER, ledger)
        return {"status": "removed", "id": identity, "links_revision": _hash(ledger)}
