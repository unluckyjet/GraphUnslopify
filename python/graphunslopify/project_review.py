"""Read intact paper evidence without rendering, repairing or accepting new science."""

from __future__ import annotations

import copy
import hashlib
import platform
from importlib.metadata import PackageNotFoundError, version
from importlib.resources import files
from pathlib import Path

from .diagnostics import explain
from .project import (
    ProjectError,
    _digest,
    _execution_source,
    _inside,
    project_history,
    project_status,
)


def _version(name):
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def _runtime(recorded):
    if not recorded:
        return {"state": "not_recorded", "matches_current_source": None}
    from .figure_runtime import FUNCTION_NAMES, RUNTIME_ABI, SOURCE_COMPONENTS, runtime_info

    try:
        components = {
            name: hashlib.sha256(files("graphunslopify").joinpath(name).read_bytes()).hexdigest()
            for name in SOURCE_COMPONENTS
        }
        expected = {
            "abi": RUNTIME_ABI,
            "source_sha256": components["figure_runtime.py"],
            "functions": list(FUNCTION_NAMES),
            "components": components,
        }
        loaded_source_matches = runtime_info()["source_sha256"] == expected["source_sha256"]
        match = recorded == expected and loaded_source_matches
        return {
            "state": "matches" if match else "changed",
            "matches_current_source": match,
            "recorded": copy.deepcopy(recorded),
            "scope": "Actual scientific source/ABI/capabilities; not author authentication or a new execution.",
        }
    except (OSError, ValueError) as error:
        return {"state": "unavailable", "matches_current_source": None, "error": str(error)}


def _environment(recorded):
    if not recorded:
        return {"state": "not_recorded", "versions_match": None}
    observed = {"python": platform.python_version()}
    expected = {"python": recorded.get("python", {}).get("version")}
    for name, value in recorded.get("loaded_core_versions", {}).items():
        if name == "freetype":
            from matplotlib.ft2font import __freetype_version__

            observed[name] = __freetype_version__
        else:
            observed[name] = _version(name)
        expected[name] = value
    for name, value in recorded.get("installed_optional_versions", {}).items():
        key = "optional:" + name
        observed[key], expected[key] = _version(name), value
    match = observed == expected and all(
        expected.get(n) for n in ("python", "numpy", "pandas", "matplotlib", "Pillow")
    )
    return {
        "state": "versions_match" if match else "versions_changed_or_incomplete",
        "versions_match": match,
        "recorded": expected,
        "observed": observed,
        "scope": "Version comparison only; system fonts, external tools and complete dependency bytes are not reverified.",
    }


def _groups(report, current, event, exports_verified=False, execution_source=None):
    if report is None:
        return {
            name: {"state": "unavailable", "reason": "No intact executed report in this selection."}
            for name in ("claims", "uncertainty", "legibility", "reproduction")
        }
    claims = copy.deepcopy(report.get("claims", []))
    spec = report.get("spec", {})
    findings = [explain(item) for item in report.get("findings", [])]
    inspection = copy.deepcopy(report.get("inspection", {}))
    recorded_execution = event["result"].get("execution_source")
    recorded_execution = recorded_execution if isinstance(recorded_execution, dict) else {}
    return {
        "claims": {
            "state": "recorded_results" if claims else "not_declared",
            "items": claims,
            "untested": copy.deepcopy(report.get("untested", [])),
            "scope": "Only the declared supported comparisons from this saved execution.",
        },
        "uncertainty": {
            "state": "declared" if spec.get("uncertainty") else "not_declared",
            "settings": copy.deepcopy(spec.get("uncertainty")),
            "aggregation": spec.get("aggregation"),
            "sample_evidence": copy.deepcopy(report.get("data", {}).get("counts", {})),
            "random_constants": copy.deepcopy(
                report.get("environment", {}).get("random_constants", {})
            ),
            "execution_status": report.get("status"),
            "scope": "Declared method and recorded sample evidence; appropriateness is not established by displaying an interval.",
        },
        "legibility": {
            "state": "recorded_inspection" if inspection.get("available") else "unavailable",
            "inspection": inspection,
            "findings": findings,
            "scope": "All actual findings are retained; categories may overlap. No new inspection is performed by this query.",
        },
        "reproduction": {
            "state": "recorded_evidence",
            "event": event["id"],
            "script": copy.deepcopy(report.get("script")),
            "data": copy.deepcopy(report.get("data")),
            "declared_input_coverage": current["input_coverage"],
            "source_input_scope": "canonical_spec_inputs"
            if current["source_type"] == "spec"
            else "declared_script_inputs_only",
            "saved_exports_verified": exports_verified,
            "runtime": _runtime(report.get("script", {}).get("runtime")),
            "environment": _environment(report.get("environment")),
            "audit_compiler_source": {
                "state": "not_recorded"
                if not recorded_execution
                else "matches"
                if recorded_execution == execution_source
                else "changed",
                "recorded_sha256": recorded_execution.get("sha256"),
                "observed_sha256": (execution_source or {}).get("sha256"),
                "scope": "Actual recorded package Python/compiler/schema sources; external dependency versions are checked separately.",
            },
            "scope": "Saved fingerprints and environment evidence, not a new reproduction or proof of all authored-script inputs.",
        },
    }


def project_review(path=".", *, event_id: str | None = None):
    """Group actual saved evidence and keep current inputs/history distinct."""
    current = project_status(path)
    history = project_history(path)
    events = history["events"]
    if event_id is not None:
        event = next((e for e in events if e["id"] == event_id), None)
        if event is None or not event["integrity"] or event.get("action") != "run":
            raise ProjectError("Choose an intact completed audit run for scientific review.")
    else:
        # A newer incomplete/damaged event blocks automatic fallback to older science.
        event = next((e for e in events if e.get("action") == "run" or not e["integrity"]), None)
    usable = bool(event and event["integrity"] and event.get("action") == "run")
    result = event.get("result", {}) if usable else {}
    snapshot_revision = (result.get("snapshot") or {}).get("revision")
    audited = {f["id"]: f for f in (result.get("audit") or {}).get("figures", [])}
    execution_source = _execution_source()
    rows = []
    for item in current["figures"]:
        figure = audited.get(item["id"], {})
        report = figure.get("report")
        export_errors = []
        exports_verified = bool(usable and figure.get("outputs"))
        if exports_verified:
            try:
                audit_root = _inside(
                    Path(current["config"]).parent, "history/" + event["id"] + "/audit"
                )
                for output in figure["outputs"]:
                    target = _inside(audit_root, output["path"])
                    if (
                        target.stat().st_size != output["bytes"]
                        or _digest(target) != output["sha256"]
                    ):
                        raise ProjectError("Selected saved export changed since its audit.")
            except (OSError, ValueError) as error:
                exports_verified = False
                export_errors.append(str(error))
        same_inputs = snapshot_revision == current["revision"]
        latest_figure_run = bool(event and item["last_run"] == event["id"])
        inputs_accepted = bool(
            report
            and same_inputs
            and latest_figure_run
            and item["last_accepted"]
            and item["freshness"] == "unchanged"
            and item.get("artifacts_verified")
            and history["integrity"] == "verified"
            and report.get("policy", {}).get("strict")
            and exports_verified
        )
        groups = (
            _groups(report, item, event, exports_verified, execution_source)
            if usable
            else _groups(None, item, event)
        )
        current_versions = bool(
            report
            and groups["reproduction"].get("runtime", {}).get("matches_current_source") is True
            and groups["reproduction"].get("environment", {}).get("versions_match") is True
            and groups["reproduction"].get("audit_compiler_source", {}).get("state") == "matches"
        )
        state = (
            "not_run"
            if event is None
            else "unavailable"
            if not usable or report is None
            else "current_inputs"
            if inputs_accepted and current_versions
            else "current_inputs_rerun_recommended"
            if inputs_accepted
            else "historical_or_needs_audit"
        )
        rows.append(
            {
                "id": item["id"],
                "source_type": item["source_type"],
                "freshness": item["freshness"],
                "evidence_state": state,
                "matches_latest_accepted_inputs": inputs_accepted,
                "rerun_recommended": not (inputs_accepted and current_versions)
                or item["source_type"] == "script",
                "execution_status": report.get("status") if report else "not_available",
                "policy": copy.deepcopy(report.get("policy")) if report else None,
                "groups": groups,
                "errors": [*copy.deepcopy(item["errors"]), *export_errors],
                "audit_errors": copy.deepcopy(figure.get("errors", [])),
                "policy_errors": copy.deepcopy(result.get("policy_errors", {}).get(item["id"], [])),
            }
        )
    after = project_status(path)
    if execution_source != _execution_source():
        raise ProjectError("Audit/compiler sources changed while reading review evidence; refresh.")
    if (
        after["project_id"],
        after["revision"],
        after["history_count"],
        after["history_integrity"],
    ) != (
        current["project_id"],
        current["revision"],
        current["history_count"],
        current["history_integrity"],
    ):
        raise ProjectError("Project inputs/history changed while reading review evidence; refresh.")
    return {
        "schema_version": 1,
        "query_status": "ok",
        "project_id": current["project_id"],
        "current_revision": current["revision"],
        "current_input_status": current["status"],
        "history_integrity": history["integrity"],
        "selection": {
            "event": event["id"] if event else None,
            "state": "intact_run" if usable else "unavailable" if event else "not_run",
            "snapshot_revision": snapshot_revision,
            "matches_current_revision": usable and snapshot_revision == current["revision"],
            "explicit_history_selection": event_id is not None,
        },
        "figures": rows,
        "scope": "Read-only saved scientific evidence. Current-input matching is not a new execution, cross-machine reproduction or universal scientific acceptance.",
    }
