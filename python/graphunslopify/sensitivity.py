"""Compare author-justified statistical choices on an unchanged source snapshot."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import subprocess
from pathlib import Path

from .audit import AuditError, _outputs, _run, _validate_report
from .audit_geometry import native_command
from .build import Figure, SpecError
from .observation_provenance import _load_observation_selection

_KINDS = {"bar", "line", "forest"}
_VARIANT_FIELDS = {"aggregation", "filter", "uncertainty"}
_INCOMPATIBLE = {"animate", "facet", "inset", "layers", "repeat", "smooth", "stacked", "y2"}
_FORMAT_SUFFIX = {"csv": ".csv", "excel": ".xlsx", "json": ".json", "parquet": ".parquet"}
_MAX_INPUT_BYTES = 16 * 1024**2
_MAX_GROUPS = 512


def _digest(content):
    return hashlib.sha256(content).hexdigest()


def _identity(value):
    return json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":"))


def _label(value, limit, purpose):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{purpose} requires nonempty text up to {limit} characters")
    return value.strip()


def _choice_identity(spec):
    uncertainty = spec.get("uncertainty")
    if uncertainty:
        kind = uncertainty.get("kind")
        uncertainty = {
            "kind": kind,
            "over": uncertainty.get("over"),
            "level": uncertainty.get("level", 0.95) if kind == "ci" else None,
        }
    return _identity([spec.get("aggregation"), spec.get("filter"), uncertainty])


def sensitivity_plan(spec, alternatives):
    """Build an immutable baseline and explicit alternatives for author review."""
    if (
        not isinstance(spec, dict)
        or not isinstance(spec.get("kind"), str)
        or spec["kind"] not in _KINDS
    ):
        raise ValueError("Sensitivity currently supports bar, line and forest summary figures")
    if not isinstance(spec.get("data"), dict):
        raise TypeError("Select the original figure dataset")
    if "output" in spec and not isinstance(spec["output"], dict):
        raise TypeError("Figure output must be an object")
    unsupported = sorted(name for name in _INCOMPATIBLE if spec.get(name))
    if unsupported:
        raise ValueError(
            "Sensitivity requires one ordinary summary panel. Unsupported: "
            + ", ".join(unsupported)
        )
    if spec.get("uncertainty") is not None and not isinstance(spec["uncertainty"], dict):
        raise ValueError("The baseline uncertainty must be an object")
    if spec.get("aggregation", "mean" if spec["kind"] == "forest" else None) not in (
        "mean",
        "median",
    ):
        raise ValueError("Choose an explicit mean or median summary for the baseline")
    if not isinstance(alternatives, list) or not 1 <= len(alternatives) <= 4:
        raise ValueError("Provide one to four justified alternatives")
    if len(_identity(spec)) > 64 * 1024 or len(_identity(alternatives)) > 64 * 1024:
        raise ValueError("Sensitivity specifications exceed the supported size")

    baseline = copy.deepcopy(spec)
    baseline["aggregation"] = spec.get("aggregation", "mean")
    plan = [{"label": "Baseline", "justification": None, "changes": {}, "spec": baseline}]
    choices = {_choice_identity(baseline)}
    names = {"baseline"}
    for item in alternatives:
        if not isinstance(item, dict) or set(item) != {"label", "justification", "changes"}:
            raise ValueError("Each alternative needs a label, justification and changes")
        label = _label(item["label"], 80, "Alternative label")
        reason = _label(item["justification"], 600, "Statistical justification")
        if label.casefold() in names:
            raise ValueError("Alternative labels must be distinct")
        changes = item["changes"]
        if not isinstance(changes, dict) or not changes or not changes.keys() <= _VARIANT_FIELDS:
            raise ValueError("Alternatives may change aggregation, filter or uncertainty")
        if "aggregation" in changes and changes["aggregation"] not in ("mean", "median"):
            raise ValueError("Alternative aggregation must be mean or median")
        if "uncertainty" in changes and changes["uncertainty"] is not None:
            uncertainty = changes["uncertainty"]
            if not isinstance(uncertainty, dict) or not uncertainty.keys() <= {
                "kind",
                "level",
                "over",
            }:
                raise ValueError("Only the uncertainty method, level and independent unit may vary")

        variant = copy.deepcopy(baseline)
        for key, value in changes.items():
            if value is None:
                variant.pop(key, None)
            elif key == "uncertainty":
                variant[key] = {**(baseline.get(key) or {}), **copy.deepcopy(value)}
                if variant[key].get("over") is None:
                    variant[key].pop("over", None)
            else:
                variant[key] = copy.deepcopy(value)
        if spec["kind"] == "forest" and not variant.get("uncertainty"):
            raise ValueError("Forest alternatives must retain uncertainty")
        choice = _choice_identity(variant)
        if choice in choices:
            raise ValueError("Every alternative must change a distinct statistical choice")
        choices.add(choice)
        names.add(label.casefold())
        plan.append(
            {
                "label": label,
                "justification": reason,
                "changes": copy.deepcopy(changes),
                "spec": variant,
            }
        )
    return plan


def _measurements(folder, report, program_sha, source_sha):
    selection = report["observation_selection"]
    _, graph = _load_observation_selection(
        folder,
        report,
        run_id=selection["run_id"],
        program_sha256=program_sha,
        require_contained_png=True,
    )
    if graph._source["snapshot_sha256"] != source_sha:
        raise ValueError("The calculation ledger used a different source snapshot")
    root = graph._nodes[selection["summary_node_id"]]
    values = {}
    intervals = {}
    for panel_id in root["inputs"]:
        for node_id in graph._nodes[panel_id]["inputs"]:
            node = graph._nodes[node_id]
            metadata = node["metadata"]
            key = _identity([metadata["field"], metadata["keys"]])
            if node["operation"] == "summary_estimate":
                if key in values:
                    raise ValueError("Several estimates share one comparison key")
                support = graph._nodes[node["inputs"][0]]
                values[key] = {
                    "field": metadata["field"],
                    "keys": metadata["keys"],
                    "estimate": node["value"],
                    "estimator": metadata["estimator"],
                    "units": support["value"],
                    "unit_field": support["metadata"]["unit_field"],
                    "node_id": node_id,
                }
            elif node["operation"] == "summary_interval":
                if key in intervals:
                    raise ValueError("Several intervals share one comparison key")
                intervals[key] = {
                    "bounds": node["value"],
                    "method": metadata["estimator"],
                    "bootstrap": metadata.get("bootstrap"),
                    "node_id": node_id,
                }
    if not 0 < len(values) <= _MAX_GROUPS:
        raise ValueError("The render requires one to 512 recorded group estimates")
    for key, estimate in values.items():
        estimate["interval"] = intervals.get(key)
    return values


def _compare(baseline, alternative):
    rows = []
    for key in sorted(baseline.keys() | alternative.keys()):
        before, after = baseline.get(key), alternative.get(key)
        delta = None
        if before and after and before["estimate"] is not None and after["estimate"] is not None:
            difference = after["estimate"] - before["estimate"]
            if math.isfinite(difference):
                delta = difference
        rows.append({"before": before, "after": after, "difference": delta})
    return rows


def _compare_claims(baseline, alternative):
    # Claim order only identifies results when each authored claim was evaluated
    # on both sides. A partial run can omit some claim results entirely.
    identities = ("kind", "subject", "reference", "panel", "metric")
    if len(baseline) != len(alternative):
        return None
    pairs = list(zip(baseline, alternative, strict=True))
    if any(before.get(key) != after.get(key) for before, after in pairs for key in identities):
        return None
    return [
        {"before": before, "after": after, "changed": before["verdict"] != after["verdict"]}
        for before, after in pairs
    ]


def _render(variant, output, folder, source, source_sha, palette, timeout):
    folder.mkdir()
    spec = copy.deepcopy(variant["spec"])
    spec["data"]["path"] = "../" + source.name
    if palette is not None:
        spec["palette_lock"] = "../" + palette.name
    output_spec = spec.get("output") or {}
    spec["output"] = {
        **output_spec,
        "stem": "figure",
        "formats": ["png"],
        "interactive": False,
        "latex": False,
    }
    (folder / "intent.json").write_text(_identity(spec) + "\n", encoding="utf8")
    result = {key: value for key, value in variant.items() if key != "spec"}
    result.update(status="failed", findings=[], claims=[], errors=[], estimates={}, preview=None)
    try:
        translation = Figure(spec).translate(api="local", trace_observations=True)
        result["findings"] = translation["findings"]
        if not translation["ok"]:
            raise ValueError("Static figure checks refused this choice")
        script = folder / "figure.py"
        code = translation["code"].encode("utf8")
        script.write_bytes(code)
        completed = _run(
            [
                *native_command(script, translation["filename"]),
                "--strict",
                "--json",
                "--report",
                "figure.report.json",
            ],
            folder,
            timeout,
        )
        report = json.loads(completed.stdout)
        _validate_report(report)
        if (
            report["script"]["sha256"] != _digest(code)
            or report["data"]["sha256_prefix"] != source_sha[:16]
        ):
            raise ValueError("Runtime report does not bind this generated program and source")
        result.update(
            findings=report["findings"],
            claims=report["claims"],
            counts=report["data"]["counts"],
            runtime_status=report["status"],
            runtime_exit_code=completed.returncode,
        )
        if report["outputs"]:
            (png,) = _outputs(report, folder, output)
            result["preview"] = png
        result["estimates"] = _measurements(folder, report, _digest(code), source_sha)
        result["status"] = (
            "checked"
            if completed.returncode == 0 and report["status"] == "passed"
            else "checked_with_failures"
        )
    except SpecError as problem:
        result["findings"] = problem.diagnostics or []
        result["errors"].append("The local figure compiler rejected this choice")
    except subprocess.TimeoutExpired:
        result["errors"].append("Native rendering timed out")
    except (AuditError, OSError, ValueError, KeyError, TypeError) as problem:
        result["errors"].append(str(problem))
    return result


def run_sensitivity(spec, alternatives, *, data, destination, reviewed, palette=None, timeout=60):
    """Run each choice through the native renderer and keep its evidence in a new folder."""
    plan = sensitivity_plan(spec, alternatives)
    if reviewed is not True:
        raise ValueError("Explicitly review the statistical assumptions and justified alternatives")
    if type(data) is not bytes or not 0 < len(data) <= _MAX_INPUT_BYTES:
        raise ValueError("Select a nonempty data snapshot up to 16 MiB")
    if type(timeout) not in (int, float) or not 0 < timeout <= 120:
        raise ValueError("Choose a per-figure timeout between 0 and 120 seconds")
    data_format = spec["data"].get("format", "csv")
    if not isinstance(data_format, str) or data_format not in _FORMAT_SUFFIX:
        raise ValueError("Use a supported CSV, JSON, parquet or Excel snapshot")
    if palette is None and spec.get("palette_lock"):
        raise ValueError("Select the palette snapshot used by the original figure")
    if palette is not None and (type(palette) is not bytes or not 0 < len(palette) <= 1024**2):
        raise ValueError("Select a nonempty palette snapshot up to 1 MiB")

    output = Path(destination).resolve()
    output.mkdir(mode=0o700)
    source = output / ("input" + _FORMAT_SUFFIX[data_format])
    source_sha = _digest(data)
    palette_path = output / "palette.json" if palette is not None else None
    try:
        source.write_bytes(data)
        if palette_path is not None:
            palette_path.write_bytes(palette)
        variants = [
            _render(
                variant,
                output,
                output / f"choice-{index}",
                source,
                source_sha,
                palette_path,
                timeout,
            )
            for index, variant in enumerate(plan)
        ]
        original = variants[0]
        for choice in variants[1:]:
            choice["comparison"] = (
                _compare(original["estimates"], choice["estimates"])
                if original["estimates"] and choice["estimates"]
                else None
            )
            choice["claim_comparison"] = (
                _compare_claims(original["claims"], choice["claims"])
                if "runtime_status" in original and "runtime_status" in choice
                else None
            )
        for choice in variants:
            choice["estimates"] = list(choice["estimates"].values())
        status = "checked" if all(item["status"] == "checked" for item in variants) else "partial"
        report = {
            "schema_version": 1,
            "kind": "graphunslopify.sensitivity",
            "status": status,
            "exit_code": 0 if status == "checked" else 2,
            "source": {
                "sha256": source_sha,
                "bytes": len(data),
                "format": data_format,
                "sheet": spec["data"].get("sheet"),
                "palette_sha256": _digest(palette) if palette_path is not None else None,
            },
            "choices": variants,
            "scope": "Author-justified alternatives, unchanged data snapshot, and descriptive differences between checked computations. No joint inference or selection of a preferred result.",
        }
        (output / "sensitivity.json").write_text(_identity(report) + "\n", encoding="utf8")
        return report
    finally:
        source.unlink(missing_ok=True)
        if palette_path is not None:
            palette_path.unlink(missing_ok=True)
