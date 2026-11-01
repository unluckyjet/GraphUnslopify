"""Independent final task gates shared by the two operational producer arms."""

from __future__ import annotations

import io
import math
import re
import runpy
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image
from pypdf import PdfReader

HERE = Path(__file__).resolve().parent
MEASUREMENT = runpy.run_path(str(HERE / "measurement.py"))
CORPUS = runpy.run_path(str(HERE / "corpus.py"))


def quantity_errors(actual, expected):
    errors = []
    if len(actual) != len(expected):
        return ["actual_artist_count"]
    for left, right in zip(actual, expected, strict=True):
        if set(left) != set(right) - {"n"}:
            errors.append("actual_artist_fields")
            continue
        for key, value in left.items():
            target = right[key]
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if (
                    target is None
                    or not math.isfinite(value)
                    or not math.isclose(value, target, rel_tol=1e-10, abs_tol=1e-10)
                ):
                    errors.append("actual_quantity:" + key)
            elif value != target:
                errors.append("actual_identity_or_interval:" + key)
    return errors


def intent_errors(actual, requested, path="spec"):
    """Typed defaults may be added; requested scientific/presentation intent remains."""
    errors = []
    if isinstance(requested, dict):
        if not isinstance(actual, dict):
            return [path]
        for key, value in requested.items():
            if path == "spec" and key == "data":
                continue  # Actual full data bytes are checked separately.
            if key not in actual:
                errors.append(path + "." + key)
            else:
                errors += intent_errors(actual[key], value, path + "." + key)
    elif actual != requested:
        errors.append(path)
    return errors


def evaluate(result, folder, spec, base, oracle):
    """Return real failures without dropping a denominator or counting decline as verified."""
    folder, base = Path(folder), Path(base)
    errors = []
    checks = []
    if result.get("preflight_rejected"):
        # An absent-reference control may be refused by the compiler rather
        # than rendered with an incomplete report. This is not a saved figure.
        findings = result.get("preflight_findings", [])
        relevant = any(
            f.get("code") == "claim_series_unknown" and f.get("severity") == "error"
            for f in findings
        )
        error_codes = {f.get("code") for f in findings if f.get("severity") == "error"}
        valid = (
            oracle["status"] == "incomplete"
            and result["status"] == "incomplete"
            and relevant
            and error_codes == {"claim_series_unknown"}
            and result["strict"] is True
            and result["fail_on_warning"] is False
            and result["compiler_response"]["ok"] is False
            and not intent_errors(result["spec"], spec)
            and not result["outputs"]
            and result["native_exit_code"] is None
            and result["native_report_present"] is False
            and not result["save_observations"]
            and result["data_sha256"]
            == MEASUREMENT["digest"]((base / spec["data"]["path"]).read_bytes())
            and (folder / "data.csv").read_bytes()
            == (base / spec["data"]["path"]).read_bytes()
        )
        return {
            "conformant": valid,
            "task_correct_verified": False,
            "expected_status": oracle["status"],
            "actual_status": result["status"],
            "errors": [] if valid else ["unsupported_or_unmatched_preflight_refusal"],
            "exports": [],
            "correct_refusal_without_native_report": valid,
            "scope": "Actual relevant preflight abstention; no numerical/export measurement or native process exit is claimed.",
            "formal_comparison_performed": False,
        }
    if (
        result["status"] != oracle["status"]
        or result["exit_code"] != oracle["exit_code"]
    ):
        errors.append("tool_scientific_outcome")
    if result["strict"] is not True or result["fail_on_warning"] is not False:
        errors.append("strict_policy")
    if result["retained_observations"] != oracle["retained_observations"]:
        errors.append("retained_observations")
    errors += intent_errors(result["spec"], spec)
    source = (base / spec["data"]["path"]).read_bytes()
    if (
        MEASUREMENT["digest"](source) != result["data_sha256"]
        or (folder / "data.csv").read_bytes() != source
    ):
        errors.append("current_data_bytes")
    formats = spec["output"]["formats"]
    stem = spec["output"]["stem"]
    width = {"single_column": 3.4, "double_column": 7.0}[spec["output"]["size"]]
    if set(result["outputs"]) != {stem + "." + fmt for fmt in formats}:
        errors.append("required_export_set")
    rows = CORPUS["observations"](spec, base)
    groups = list(spec.get("series_order") or sorted({row[1] for row in rows}))
    groups = [g for g in groups if any(row[1] == g for row in rows)]
    categories = (
        list(dict.fromkeys(row[0] for row in rows)) if spec["kind"] == "bar" else []
    )
    expected_labels = {"title": spec.get("title", "")}
    for axis in ("x", "y"):
        expected_labels[axis] = spec[axis]["label"] + (
            " (" + spec[axis]["unit"] + ")" if spec[axis].get("unit") else ""
        )
    clean_text = lambda value: " ".join(value.split())
    for fmt in formats:
        filename = stem + "." + fmt
        path = folder / filename
        events = [
            event for event in result["save_observations"] if event["file"] == filename
        ]
        if not path.is_file() or not events:
            errors.append("missing_original_save:" + fmt)
            continue
        event = events[-1]
        errors += quantity_errors(event["artists"], oracle["artists"])
        raw = path.read_bytes()
        if MEASUREMENT["digest"](raw) != result["outputs"].get(filename):
            errors.append("final_export_bytes:" + fmt)
        identity = MEASUREMENT["graphic_identity"](raw, fmt)
        if event["sha256"] != MEASUREMENT["digest"](raw) and not (
            event["graphic_identity"] is not None
            and event["graphic_identity"] == identity
        ):
            errors.append("original_save_binding:" + fmt)
        if {key: clean_text(value) for key, value in event["labels"].items()} != {
            key: clean_text(value) for key, value in expected_labels.items()
        }:
            errors.append("required_labels_or_units:" + fmt)
        if event["series_order"] != groups or event["categories"] != categories:
            errors.append("group_or_category_order:" + fmt)
        if fmt == "png":
            with Image.open(io.BytesIO(raw)) as image:
                dpi = image.info["dpi"]
                if any(abs(d - spec["output"]["dpi"]) >= 1 for d in dpi):
                    errors.append("actual_dpi")
                actual_width = image.width / dpi[0]
        elif fmt == "svg":
            token = ET.fromstring(raw).attrib["width"]
            if not re.fullmatch(r"[0-9.]+pt", token):
                errors.append("actual_svg_width_unit")
                continue
            actual_width = float(token[:-2]) / 72
        else:
            actual_width = (
                float(PdfReader(io.BytesIO(raw)).pages[0].mediabox.width) / 72
            )
        if abs(actual_width - width) > 0.02:
            errors.append("actual_width:" + fmt)
        font = event["minimum_visible_font_pt"]
        if font is None or font * width / actual_width < 6 - 1e-6:
            errors.append("actual_effective_font:" + fmt)
        checks.append(
            {
                "format": fmt,
                "actual_artists": len(event["artists"]),
                "actual_width_in": actual_width,
                "minimum_visible_font_pt": font,
                "save_bytes_equal_final": event["sha256"] == MEASUREMENT["digest"](raw),
                "graphic_identity_matches": identity is not None
                and identity == event["graphic_identity"],
            }
        )
    return {
        "conformant": not errors,
        "task_correct_verified": not errors and oracle["status"] == "passed",
        "expected_status": oracle["status"],
        "actual_status": result["status"],
        "errors": sorted(set(errors)),
        "exports": checks,
        "formal_comparison_performed": False,
    }
