"""Portable saved review evidence, with explicit files and no scientific re-execution."""

from __future__ import annotations

import copy
import hashlib
import html
import io
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .project import (
    MAX_SOURCE_BYTES,
    ProjectError,
    _bytes,
    _config,
    _digest,
    _execution_source,
    _inside,
    _operation,
    _review_token,
    project_history,
)
from .project_review import _groups, project_review

MAX_PACKET_BYTES = 128 * 1024 * 1024
MAX_PACKET_FILES = 4096


class _Packet:
    def __init__(self):
        self.entries = {}
        self.assets = []
        self.pinned = {}
        self.size = 0

    def add(self, name, data):
        if name in self.entries:
            raise ProjectError("Review packet contains a duplicate member.")
        if self.size + len(data) > MAX_PACKET_BYTES or len(self.entries) >= MAX_PACKET_FILES:
            raise ProjectError("Review packet exceeds the 128 MiB/4096 file limit.")
        self.entries[name] = data
        self.size += len(data)

    def saved(self, root, item, destination, **context):
        record = {
            **context,
            "original_path": item["path"],
            "expected_bytes": item["bytes"],
            "expected_sha256": item["sha256"],
            "state": "unavailable",
            "packet_path": None,
        }
        try:
            file = _inside(root, item["path"])
            expected = item["bytes"]
            if type(expected) is not int or expected < 0:
                raise ProjectError("Saved asset has an invalid recorded size.")
            if expected > MAX_PACKET_BYTES - self.size:
                raise ProjectError("Review packet exceeds the 128 MiB size limit.")
            if file.stat().st_size != expected:
                raise ProjectError("Saved asset size differs from its recorded evidence.")
            with file.open("rb") as stream:
                data = stream.read(expected + 1)
            if len(data) != expected or hashlib.sha256(data).hexdigest() != item["sha256"]:
                raise ProjectError("Saved asset bytes differ from their recorded evidence.")
            self.add(destination, data)
            self.pinned[file] = (root, item["path"], expected, item["sha256"])
            record.update(state="included", packet_path=destination)
        except (OSError, ValueError) as error:
            record["error"] = str(error)
        self.assets.append(record)
        return record

    def recheck(self):
        for path, (root, name, size, digest) in self.pinned.items():
            if (
                _inside(root, name) != path
                or path.stat().st_size != size
                or _digest(path) != digest
            ):
                raise ProjectError("Saved packet evidence changed while exporting; refresh.")


def _group_html(groups):
    escape = lambda value: html.escape(str(value), quote=True)
    cards = []
    for key, label in [
        ("claims", "Claims"),
        ("uncertainty", "Uncertainty"),
        ("legibility", "Legibility"),
        ("reproduction", "Reproduction"),
    ]:
        value = (groups or {}).get(key) or {"state": "unavailable"}
        text = value.get("reason") or value.get("scope") or "Read the recorded evidence below."
        items = "".join(
            f"<p>{escape(item.get('kind', 'Claim')).replace('_', ' ')}: <strong>{escape(item.get('verdict', 'untested'))}</strong> — {escape(item.get('detail', ''))}</p>"
            for item in value.get("items", [])
        )
        execution = value.get("execution", {})
        ancestry = (
            f"<p>Figure execution: {escape(execution['mode'])}. Original execution: {escape(execution.get('origin_event', 'this recorded run'))}.</p>"
            if execution
            else ""
        )
        cards.append(
            f"<article><h3>{label}</h3><p>{escape(value.get('state', 'unavailable')).replace('_', ' ')}</p><p>{escape(text)}</p>{items}{ancestry}</article>"
        )
    return '<div class="groups">' + "".join(cards) + "</div>"


def _scorecard_html(value):
    if not value:
        return ""
    escape = lambda item: html.escape(str(item), quote=True)
    rows = "".join(
        f"<li><strong>{escape(c['label'])}: {escape(c['state'])}</strong> — {escape(c['summary'])}</li>"
        for c in value["components"]
    )
    return (
        "<h3>Reproducibility scorecard</h3>"
        "<p>Component availability in the local project at export time. "
        "This does not mean raw data or programs are included in this packet, "
        "and does not change the recorded scientific outcome.</p><ul>" + rows + "</ul>"
    )


def _audit_html(report):
    audit = report.get("paper_audit")
    if audit is None:
        return ""
    positions = {row["key"]: index for index, row in enumerate(report["figures"])}
    names = {row["key"]: row["name"] for row in audit["figures"]}
    items = "".join(
        f"<li><strong>{html.escape(issue['priority'].replace('_', ' '))}</strong> · "
        f'<a href="#figure-{positions[issue["figure"]]}">{html.escape(names[issue["figure"]])}</a> '
        f"· {html.escape(issue['message'])}</li>"
        for issue in audit["issues"]
    )
    counts = audit["counts"]
    return (
        '<section aria-labelledby="paper-audit-title"><h2 id="paper-audit-title">Paper audit priorities</h2>'
        f"<p>{audit['figure_count']} figures reviewed · {counts['error']} recorded errors · "
        f"{counts['evidence_gap']} evidence gaps · {counts['warning']} warnings.</p>"
        '<p><a href="reports/paper-audit.json">Paper audit JSON and evidence references</a></p>'
        + (f"<ol>{items}</ol>" if items else "<p>No review priorities were recorded.</p>")
        + "</section>"
    )


def _qualitative_html(batches):
    if not batches:
        return ""
    groups = []
    for number, batch in enumerate(batches, start=1):
        details = batch.get("review", {}).get("qualitative", {}).get("content")
        if details is None:
            groups.append(f"<p>Batch {number} unavailable · {html.escape(batch['error'])}</p>")
            continue
        suggestions = "".join(
            f"<li><strong>{html.escape(item['figure_key'])}</strong> · "
            f"{html.escape(item['suggestion'])} · {html.escape(item['why'])} "
            f"({html.escape(', '.join(item['evidence_ids']))})</li>"
            for item in details["suggestions"]
        )
        questions = "".join(f"<li>{html.escape(item)}</li>" for item in details["author_questions"])
        groups.append(
            f"<h3>Batch {number}</h3><p>{html.escape(details['summary'])}</p><ul>{suggestions}</ul>"
            + (f"<p>Questions for the author</p><ul>{questions}</ul>" if questions else "")
        )
    return (
        '<section aria-labelledby="paper-qualitative-title"><h2 id="paper-qualitative-title">'
        "Unverified model suggestions</h2><p>Review the wording and evidence references. "
        "The recorded audit verdicts remain separate.</p>"
        '<p><a href="reports/qualitative-review.json">Batch evidence and references</a></p>'
        + "".join(groups)
        + "</section>"
    )


def _index(report):
    escape = lambda value: html.escape(str(value), quote=True)
    audit = report.get("paper_audit")
    audit_figures = {row["key"]: row for row in audit["figures"]} if audit else {}
    rows = []
    for number, figure in enumerate(report["figures"]):
        assets = [item for item in report["assets"] if item.get("figure") == figure["key"]]
        links = []
        for item in assets:
            label = escape(Path(item["original_path"]).name)
            links.append(
                f'<a download href="{escape(item["packet_path"])}">{label}</a>'
                if item["state"] == "included"
                else f"<span>Unavailable: {label} — {escape(item.get('error', ''))}</span>"
            )
        image = next(
            (
                item["packet_path"]
                for item in assets
                if item["state"] == "included" and item["packet_path"].endswith(".png")
            ),
            None,
        )
        preview = f'<img src="{escape(image)}" alt="Saved {escape(figure["id"])}">' if image else ""
        anchor = f' id="figure-{number}"' if audit else ""
        audit_row = audit_figures.get(figure["key"])
        evidence = (
            f"<p>Paper audit evidence: {escape(audit_row['evidence_state']).replace('_', ' ')}.</p>"
            if audit_row
            else ""
        )
        rows.append(
            f"<section{anchor}><h2>{escape(figure.get('display_name', figure['id']))}</h2>"
            f"<p>{escape(figure['scope'])} · {escape(figure['state']).replace('_', ' ')}</p>{preview}"
            f"<p>Recorded outcome: {escape(figure.get('execution_status', 'unavailable'))}.</p>"
            + evidence
            + '<div class="links">'
            + "".join(links)
            + "</div>"
            + _group_html(figure.get("groups"))
            + _scorecard_html(figure.get("scorecard"))
            + "<details><summary>Recorded evidence</summary><pre>"
            + escape(json.dumps(figure, indent=2, ensure_ascii=False))
            + "</pre></details></section>"
        )
    native = report["review"].get("native_run")
    status = (
        f"Saved source-backed paper audit: {escape(native['status'])} · exit {escape(native['exit_code'])}."
        if native
        else "No intact native paper audit in this selection."
    )
    execution = (
        "This is saved evidence, not a new execution or continuing scientific acceptance. "
        "PDF numerical claims and original data remain untested."
    )
    if audit:
        basis = (
            "This report ran the native figures with strict checks."
            if audit["execution"] == "fresh_native_audit"
            else "This report uses saved evidence."
        )
        execution = basis + " PDF numerical claims remain untested."
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>GraphUnslopify · Saved paper review</title><style>"
        "body{font:16px/1.5 system-ui,sans-serif;color:#193344;background:#f2f6f8;"
        "max-width:1100px;margin:0 auto;padding:24px}header,section{background:white;"
        "padding:24px;border:1px solid #dce5eb;border-radius:12px;margin-bottom:20px}"
        "h1,h2{line-height:1.2}img{max-width:100%;height:auto}pre{white-space:pre-wrap;"
        "overflow-wrap:anywhere;font-size:13px}.links{display:flex;flex-wrap:wrap;gap:12px}"
        "a{color:#126f91}details{margin-top:16px}p{overflow-wrap:anywhere}"
        ".groups{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px}"
        ".groups article{padding:12px;background:#f2f6f8;border-radius:8px}</style>"
        f"<header><p>GRAPHUNSLOPIFY · SAVED REVIEW PACKET</p><h1>{escape(report['project_name'])} — figure review</h1>"
        f"<p>{status}</p><p>{escape(report['created_at'])}</p>"
        f"<p>{execution}</p>"
        "<p>Raw datasets, original PDFs and source programs are excluded. "
        "The recorded reports contain results, labels and source metadata.</p>"
        '<p><a download href="review.json">Full review JSON</a> · '
        '<a download href="manifest.json">File integrity manifest</a></p>'
        '<p><a download href="reports/scorecard.json">Reproducibility scorecard JSON</a></p>'
        + (
            '<p><a download href="reports/native-audit.json">Saved native audit report</a></p>'
            if any(
                x["role"] == "native_audit" and x["state"] == "included" for x in report["assets"]
            )
            else ""
        )
        + "<details><summary>Whole-paper checks and policy</summary><pre>"
        + escape(json.dumps(native, indent=2, ensure_ascii=False))
        + "</pre></details></header>"
        + _audit_html(report)
        + _qualitative_html(report.get("qualitative_reviews"))
        + "".join(rows)
        + "</html>"
    ).encode("utf8")


def create_review_packet(
    path=".", *, expected_revision, event_id=None, paper_audit=False, run_event=None, qualitative=()
):
    """Collect explicit saved files for the reviewed revision, including failed/partial scope."""
    _review_token(expected_revision)
    source, _ = _config(path)
    with _operation(source.parent):
        review = project_review(source, event_id=event_id)
        if review["evidence_revision"] != expected_revision:
            raise ProjectError("Review evidence changed since selection; refresh before exporting.")
        history = project_history(source)
        events = {item["id"]: item for item in history["events"] if item["integrity"]}
        packet = _Packet()
        figures, receipt_ids = [], set()
        selected = review.get("native_run")
        if selected:
            event = events[selected["id"]]
            receipt_ids.add(event["id"])
            folder = _inside(source.parent, "history/" + event["id"])
            audit_root = _inside(folder, "audit")
            packet.add("reports/selected-native-run.json", _bytes(selected))
            aggregate = next(
                (item for item in event["files"] if item["path"] == "audit/audit.report.json"), None
            )
            if aggregate:
                packet.saved(folder, aggregate, "reports/native-audit.json", role="native_audit")
            current_rows = {
                row["id"]: row for row in review["figures"] if row["source_type"] != "pdf"
            }
            for number, row in enumerate((event["result"].get("audit") or {}).get("figures", [])):
                identity = row["id"]
                current = current_rows.get(identity)
                groups = (
                    copy.deepcopy(current["groups"])
                    if current
                    else _groups(
                        row.get("report"),
                        {
                            "id": identity,
                            "input_coverage": "not_current_removed_binding",
                        },
                        event,
                        exports_verified=False,
                        execution_source=_execution_source(),
                    )
                )
                if not current:
                    groups["reproduction"]["execution"] = copy.deepcopy(
                        row.get("execution", {"mode": "not_recorded"})
                    )
                figures.append(
                    {
                        "key": "native:" + identity,
                        "id": identity,
                        "scope": "Saved source-backed scientific evidence",
                        "state": current["evidence_state"]
                        if current
                        else "historical_removed_figure",
                        "execution_status": row["status"],
                        "execution": copy.deepcopy(row.get("execution", {"mode": "not_recorded"})),
                        "groups": groups,
                        "scorecard": copy.deepcopy(current.get("scorecard")) if current else None,
                        "errors": copy.deepcopy(row.get("errors", [])),
                    }
                )
                for key in ("origin_event", "source_event"):
                    if row.get("execution", {}).get(key) in events:
                        receipt_ids.add(row["execution"][key])
                for index, output in enumerate(row["outputs"]):
                    suffix = (
                        output["format"]
                        if re.fullmatch(r"[a-z0-9]{1,8}", output["format"])
                        else "bin"
                    )
                    packet.saved(
                        audit_root,
                        output,
                        f"figures/native/{number:04d}/{index:04d}.{suffix}",
                        role="native_export",
                        figure="native:" + identity,
                        event=event["id"],
                    )
                if not current:
                    groups["reproduction"]["saved_exports_verified"] = bool(row["outputs"]) and all(
                        asset["state"] == "included"
                        for asset in packet.assets
                        if asset.get("figure") == "native:" + identity
                    )
        for number, row in enumerate(review["figures"]):
            if row["source_type"] != "pdf":
                if not any(figure["key"] == "native:" + row["id"] for figure in figures):
                    figures.append(
                        {
                            "key": "native:" + row["id"],
                            "id": row["id"],
                            "scope": "Native evidence unavailable",
                            "state": row["evidence_state"],
                            "groups": copy.deepcopy(row["groups"]),
                            "scorecard": copy.deepcopy(row["scorecard"]),
                            "errors": copy.deepcopy(row["errors"]),
                        }
                    )
                continue
            figures.append(
                {
                    "key": row["key"],
                    "id": row["id"],
                    "scope": "PDF visual-only; numerical claims/data untested",
                    "display_name": row["name"],
                    "execution_status": row["execution_status"],
                    "state": row["evidence_state"],
                    "groups": copy.deepcopy(row["groups"]),
                    "scorecard": copy.deepcopy(row["scorecard"]),
                    "errors": copy.deepcopy(row["errors"]),
                }
            )
            identity = row["inspection"]["event"]
            if identity not in events:
                continue
            receipt_ids.add(identity)
            root = _inside(source.parent, "history/" + identity)
            for index, asset in enumerate(row["inspection"]["assets"]):
                suffix = Path(asset["path"]).suffix.lower()
                if suffix not in {".png", ".txt", ".json"}:
                    continue
                packet.saved(
                    root,
                    asset,
                    f"figures/pdf/{number:04d}/{index:04d}{suffix}",
                    role="pdf_visual_asset",
                    figure=row["key"],
                    event=identity,
                )
        for identity in sorted(receipt_ids):
            root = _inside(source.parent, "history/" + identity)
            ancestor = events[identity]
            aggregate = next(
                (item for item in ancestor["files"] if item["path"] == "audit/audit.report.json"),
                None,
            )
            if aggregate and (not selected or identity != selected["id"]):
                packet.saved(
                    root,
                    aggregate,
                    "reports/ancestry/" + identity + ".json",
                    role="execution_ancestry",
                    event=identity,
                )
            receipt = _inside(root, "receipt.json")
            if receipt.stat().st_size > MAX_SOURCE_BYTES:
                raise ProjectError("Saved receipt exceeds the 20 MiB metadata limit.")
            with receipt.open("rb") as stream:
                raw = stream.read(MAX_SOURCE_BYTES + 1)
            if len(raw) > MAX_SOURCE_BYTES:
                raise ProjectError("Saved receipt changed while exporting.")
            packet.add("receipts/" + identity + ".json", raw)
            packet.pinned[_inside(root, "receipt.json")] = (
                root,
                "receipt.json",
                len(raw),
                hashlib.sha256(raw).hexdigest(),
            )
        report = {
            "schema_version": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "operation": "saved_review_export",
            "project_name": source.parent.parent.name,
            "science_reexecuted": False,
            "source_data_included": False,
            "source_programs_included": False,
            "original_pdfs_included": False,
            "review": review,
            "figures": figures,
            "assets": packet.assets,
            "scope": "Read-only saved native and source-free visual evidence. Integrity hashes do not authenticate authorship. Export success is not scientific acceptance or a new reproduction.",
        }
        if paper_audit:
            from .paper_audit import summarize_paper

            report["paper_audit"] = summarize_paper(review, run_event=run_event)
            packet.add("reports/paper-audit.json", _bytes(report["paper_audit"]))
            if qualitative:
                report["qualitative_reviews"] = qualitative
                packet.add("reports/qualitative-review.json", _bytes(qualitative))
        packet.add(
            "reports/scorecard.json",
            _bytes(
                {
                    **copy.deepcopy(review["scorecard"]),
                    "evidence_revision": expected_revision,
                    "packet_inclusion": {
                        "raw_datasets": False,
                        "source_programs": False,
                        "original_pdfs": False,
                        "saved_exports": "See the packet asset inventory.",
                    },
                }
            ),
        )
        packet.add("review.json", _bytes(report))
        packet.add("index.html", _index(report))
        packet.recheck()
        if project_review(source, event_id=event_id)["evidence_revision"] != expected_revision:
            raise ProjectError("Project evidence changed during export; refresh.")
        inventory = [
            {"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
            for name, raw in sorted(packet.entries.items())
        ]
        packet.add(
            "manifest.json",
            _bytes(
                {
                    "schema_version": 1,
                    "project_id": review["project_id"],
                    "evidence_revision": expected_revision,
                    "files": inventory,
                    "scope": "Explicit included bytes only; hashes are integrity evidence, not author authentication.",
                }
            ),
        )
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, raw in sorted(packet.entries.items()):
                archive.writestr(name, raw)
        return stream.getvalue()
