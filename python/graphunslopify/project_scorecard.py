"""Read component availability without executing or certifying a research result."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from importlib.resources import files
from pathlib import Path

from .project import MAX_SOURCE_BYTES, ProjectError, _inside

SCOPE = (
    "Availability in the local project at query time. Components are not scientific grades. "
    "Reading this report performs no new execution or cross-machine reproduction. "
    "Portable review packets have a separate included-file inventory."
)


def _component(identity, label, state, summary, **evidence):
    return {
        "id": identity,
        "label": label,
        "state": state,
        "summary": summary,
        "evidence": evidence,
    }


def _program_bytes(root, relative):
    try:
        path = _inside(root, relative)
        if path.stat().st_size > MAX_SOURCE_BYTES:
            raise ValueError("Saved program exceeds the 20 MiB source limit.")
        with path.open("rb") as stream:
            raw = stream.read(MAX_SOURCE_BYTES + 1)
        if len(raw) > MAX_SOURCE_BYTES:
            raise ValueError("Saved program exceeds the 20 MiB source limit.")
        return {"readable": True, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    except FileNotFoundError:
        return {"readable": False, "reason": "Saved execution program is missing."}
    except (OSError, ValueError) as error:
        return {"readable": False, "reason": str(error)}


class ScorecardCollector:
    """One query owns its observations; recheck program bytes at collection end."""

    def __init__(self):
        self.programs = []

    def recheck(self):
        for root, relative, observed in self.programs:
            if _program_bytes(root, relative) != observed:
                raise ProjectError("Saved program availability changed during review; refresh.")

    def native(self, root, current, event, figure, groups, history_integrity):
        snapshot = ((event or {}).get("result") or {}).get("snapshot") or {}
        previous = snapshot.get("figures", [])
        index = next((i for i, item in enumerate(previous) if item["id"] == current["id"]), None)
        recorded = previous[index] if index is not None else {}
        report = figure.get("report") or {}
        reproduction = groups["reproduction"]
        source_type = current["source_type"]
        data = [copy.deepcopy(f) for f in current["files"] if f["role"] == "data"]
        old_data = [copy.deepcopy(f) for f in recorded.get("files", []) if f["role"] == "data"]
        readable = sum(bool(f.get("sha256")) for f in data)
        same_data = (
            sorted(f["sha256"] for f in data) == sorted(f.get("sha256") or "" for f in old_data)
            if data
            and old_data
            and readable == len(data)
            and all(f.get("sha256") for f in old_data)
            else None
        )
        same_locations = (
            sorted(f["path"] for f in data) == sorted(f["path"] for f in old_data)
            if old_data
            else None
        )
        unknown_comparison = event is not None and same_data is None
        data_state = (
            "missing"
            if not readable
            else "partial"
            if readable != len(data)
            or same_data is False
            or same_locations is False
            or unknown_comparison
            or source_type == "script"
            else "available"
        )
        data_summary = (
            "No readable declared data files are available."
            if not readable
            else "Some declared data files are missing or unreadable."
            if readable != len(data)
            else "Current data bytes differ from the selected run."
            if same_data is False
            else "Matching data bytes are readable at different declared locations."
            if same_data is True and same_locations is False
            else "Selected audit has no complete data fingerprint for comparison; current files are readable."
            if unknown_comparison
            else "Declared data files are readable; other Python inputs are not fully known."
            if source_type == "script"
            else "Declared data bytes match the selected run."
            if same_data is True
            else "Declared data files are readable; no selected audit records them yet."
        )
        components = [
            _component(
                "data",
                "Declared data",
                data_state,
                data_summary,
                current_files=data,
                recorded_files=old_data,
                matches_recorded_bytes=same_data,
                matches_recorded_locations=same_locations,
                input_coverage=current["input_coverage"],
                historical_raw_copy_claimed=False,
            )
        ]
        source_files = [f for f in current["files"] if f["role"] in {"spec", "script"}]
        current_source = bool(
            all(f.get("sha256") for f in source_files)
            if source_files
            else source_type == "spec" and current.get("kind")
        )
        saved_name = None
        if index is not None:
            saved_name = (
                f"source/{index:04d}.py"
                if recorded.get("source_type") == "script"
                else f"source/{index:04d}.json"
                if any(f["role"] == "spec" for f in recorded.get("files", []))
                else "source/manifest.json"
            )
        saved_source = next(
            (f for f in (event or {}).get("files", []) if f["path"] == saved_name), None
        )
        components.append(
            _component(
                "definitions",
                "Source definitions",
                "available" if current_source else "partial" if saved_source else "missing",
                "Current source definition is readable."
                if current_source
                else "A saved definition exists, but the current source is unavailable."
                if saved_source
                else "No readable current or saved source definition is available.",
                source_type=source_type,
                current_files=copy.deepcopy(source_files),
                inline_manifest_definition=source_type == "spec" and not source_files,
                saved_source=copy.deepcopy(saved_source),
            )
        )
        expected = (report.get("script") or {}).get("sha256")
        program = {"readable": False, "reason": "No anchored execution program is recorded."}
        relative = None
        if event and isinstance(expected, str) and re.fullmatch("[a-f0-9]{64}", expected):
            try:
                audit = _inside(Path(root), "history/" + event["id"] + "/audit")
                directory = event["result"]["audit"]["run_directory"]
                name = "source.py" if recorded.get("source_type") == "script" else "figure.py"
                relative = directory + "/figures/" + current["id"] + "/" + name
                program = _program_bytes(audit, relative)
                self.programs.append((audit, relative, program))
            except (OSError, ValueError, TypeError, KeyError) as error:
                program = {"readable": False, "reason": str(error)}
        matches = program.get("readable") is True and program.get("sha256") == expected
        components.append(
            _component(
                "programs",
                "Execution programs",
                "available" if matches else "partial" if program.get("readable") else "missing",
                "Saved program bytes match the recorded execution."
                if matches
                else "Saved program bytes differ from the recorded execution."
                if program.get("readable")
                else program["reason"],
                relative_path=relative,
                expected_sha256=expected,
                observed=program,
                matches_executed_program=matches,
                recorded_source_type=recorded.get("source_type"),
            )
        )
        environment = reproduction.get("environment", {})
        has_environment = environment.get("state") not in {None, "not_recorded", "unavailable"}
        components.append(
            _component(
                "environment",
                "Environment",
                "partial" if has_environment else "missing",
                "Runtime and dependency context is recorded; a complete environment lock is not supplied."
                if has_environment
                else "No execution environment context is recorded.",
                versions=copy.deepcopy(environment),
                runtime=copy.deepcopy(reproduction.get("runtime")),
                compiler=copy.deepcopy(reproduction.get("audit_compiler_source")),
                complete_environment_lock_claimed=False,
            )
        )
        status = report.get("status", "not_available")
        components.append(
            _component(
                "checks",
                "Recorded checks",
                "available" if report else "missing",
                f"Recorded scientific outcome: {status}. Availability does not change this outcome."
                if report
                else "No intact executed scientific report is available.",
                scientific_status=status,
                policy=copy.deepcopy(report.get("policy")),
                claims=copy.deepcopy(report.get("claims", [])),
                untested=copy.deepcopy(report.get("untested", [])),
                inspection_available=bool((report.get("inspection") or {}).get("available")),
            )
        )
        outputs = figure.get("outputs", [])
        verified = reproduction.get("saved_exports_verified") is True
        components.append(
            _component(
                "exports",
                "Figure exports",
                "available" if verified else "partial" if outputs else "missing",
                "Saved export bytes match their recorded hashes."
                if verified
                else "Recorded exports are missing, changed or unverified."
                if outputs
                else "No saved figure exports are recorded.",
                verified=verified,
                inventory=copy.deepcopy(outputs),
            )
        )
        components.append(
            _component(
                "history",
                "Run history",
                "available"
                if event and history_integrity == "verified"
                else "partial"
                if event
                else "missing",
                "Selected run history is intact; execution ancestry remains explicit."
                if event and history_integrity == "verified"
                else "Selected evidence exists, but project history is not fully intact."
                if event
                else "No intact selected run is available.",
                event=(event or {}).get("id"),
                history_integrity=history_integrity,
                execution=copy.deepcopy(figure.get("execution", {"mode": "not_run"})),
            )
        )
        return {
            "scientific_status": status,
            "paper_status": ((event or {}).get("result") or {}).get("status"),
            "components": components,
        }


def pdf_scorecard(row):
    reproduction = row["groups"]["reproduction"]
    available = reproduction["assets_verified"] is True
    context = row["groups"]["legibility"].get("renderer")
    components = [
        _component("data", "Declared data", "missing", "A PDF does not supply the original data."),
        _component(
            "definitions",
            "Source definitions",
            "missing",
            "Original plotting definitions were not supplied.",
        ),
        _component(
            "programs",
            "Execution programs",
            "missing",
            "Original plotting programs were not supplied.",
        ),
        _component(
            "environment",
            "Environment",
            "partial" if context else "missing",
            "Figure creation environment is unknown; any recorded context describes PDF inspection only.",
            inspection_renderer=copy.deepcopy(context),
        ),
        _component(
            "checks",
            "Recorded checks",
            "partial" if context else "missing",
            "PDF visual checks do not establish numerical or scientific verification.",
            scientific_status="untested",
            visual_status=row["execution_status"],
        ),
        _component(
            "exports",
            "Figure exports",
            "available" if available else "missing",
            "Saved PDF inspection assets match recorded hashes."
            if available
            else "No verified saved PDF inspection assets are available.",
            assets_verified=available,
            current_pdf_sha256=reproduction["current_sha256"],
            recorded_pdf_sha256=reproduction["recorded_sha256"],
        ),
        _component(
            "history",
            "Run history",
            "available"
            if available
            else "partial"
            if row["inspection"].get("event")
            else "missing",
            "PDF inspection history is separate from original figure execution.",
            inspection_event=row["inspection"].get("event"),
        ),
    ]
    return {"scientific_status": "untested", "paper_status": None, "components": components}


def collection_scorecard(review):
    value = {
        "schema_version": 1,
        "project_id": review["project_id"],
        "current_revision": review["current_revision"],
        "selection": copy.deepcopy(review["selection"]),
        "availability_scope": "local_project_at_query",
        "new_execution": False,
        "scope": SCOPE,
        "figures": [
            {
                "id": row["id"],
                "key": row["key"],
                "source_type": row["source_type"],
                **copy.deepcopy(row["scorecard"]),
            }
            for row in review["figures"]
        ],
    }
    from jsonschema import Draft202012Validator

    schema = json.loads(
        files("graphunslopify").joinpath("schemas/scorecard.schema.json").read_text()
    )
    Draft202012Validator(schema).validate(value)
    return value


def project_scorecard(path=".", *, event_id=None):
    """Read the same revision-bound component report used by scientific review."""
    from .project_review import project_review

    review = project_review(path, event_id=event_id)
    return {**copy.deepcopy(review["scorecard"]), "evidence_revision": review["evidence_revision"]}
