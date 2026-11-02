"""Actual independent custody/science controls; formal execution awaits the full seal."""

from __future__ import annotations

import copy
import hashlib
import json
import runpy
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUNNER = runpy.run_path(str(HERE / "session_runner.py"))


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def classify_science(kind, status):
    if kind == "clean":
        return "clean_science" if status == "passed" else "clean_science_false_alarm"
    if status == "failed":
        return "scientific_failure"
    if status == "incomplete":
        return "scientific_abstention"
    return "missed_scientific_fault"


def schedule():
    protocol = json.loads((HERE / "protocol.json").read_text())
    controls = protocol["reliability"]
    cases = [("clean", name) for name in controls["clean"]]
    cases += [("science", row["id"]) for row in controls["science_faults"]]
    cases += [("integrity", name) for name in controls["integrity_faults"]]
    return [
        {"arm": arm, "kind": kind, "control": name, "repeat": repeat}
        for repeat in range(controls["repeats_per_arm_case"])
        for index, (kind, name) in enumerate(cases)
        for arm in (
            ["matplotlib", "graphunslopify"]
            if (index + repeat) % 2 == 0
            else ["graphunslopify", "matplotlib"]
        )
    ]


def relevant_science(arm, control, result, folder):
    if arm == "matplotlib":
        codes = {f["code"] for f in result["scientific_findings"]}
        expected = (
            "descriptive_claim_false"
            if control.endswith("false-claim")
            else "claim_reference_unavailable"
            if control == "penguins-absent-reference"
            else "sample_sd_unavailable"
        )
        return expected in codes, sorted(codes)
    if result.get("preflight_rejected"):
        codes = {
            f["code"] for f in result["preflight_findings"] if f["severity"] == "error"
        }
        return (
            control == "penguins-absent-reference"
            and codes == {"claim_series_unknown"}
            and result["native_exit_code"] is None,
            sorted(codes),
        )
    native = json.loads((folder / result["native_report_file"]).read_text())
    if control.endswith("false-claim"):
        claims = native["claims"]
        expected = result["spec"]["claims"][0]
        matches = [
            row
            for row in claims
            if row.get("kind") == expected["kind"]
            and row.get("subject") == expected["subject"]
            and row.get("reference") == expected["reference"]
            and row.get("verdict") == "fails"
        ]
        return bool(matches), claims
    findings = native.get("findings", [])
    codes = {f["code"] for f in findings}
    return "uncertainty_unavailable" in codes, findings


def mutation(arm, control, folder, result, live, data):
    if control == "change-saved-png-bytes":
        path = folder / "figure.png"
        reason = (
            "file_changed:figure.png"
            if arm == "graphunslopify"
            else "output_changed:figure.png"
        )
    elif control == "change-saved-report-bytes":
        path = folder / (
            result["native_report_file"] if arm == "graphunslopify" else "report.json"
        )
        reason = (
            "file_changed:" + path.name if arm == "graphunslopify" else "report_changed"
        )
    elif control == "reencode-data-after-acceptance":
        path, reason = data, "input_changed"
    else:
        if control != "append-comment-to-owned-recorded-producer-after-acceptance":
            raise ValueError("Unknown registered integrity control")
        path = (
            folder / "figure.py"
            if arm == "graphunslopify"
            else live.folder / "producer/code/producer.py"
        )
        reason = (
            "file_changed:figure.py"
            if arm == "graphunslopify"
            else "producer_changed:code/producer.py"
        )
    original = path.read_bytes()
    if path == data:
        normalized = original.replace(b"\r\n", b"\n")
        changed = (
            normalized if normalized != original else normalized.replace(b"\n", b"\r\n")
        )
    else:
        changed = (
            original + b"\n"
            if path == folder / "figure.png" or path.suffix == ".json"
            else original + b"\n# owned recorded producer changed after acceptance\n"
        )
    if changed == original:
        raise ValueError("Actual registered mutation did not change bytes")
    return path, original, changed, reason


def run_case(case, output, *, python=sys.executable, installed=False):
    output = Path(output).resolve()
    if output.is_relative_to(ROOT) and not output.is_relative_to(HERE / "results"):
        raise ValueError(
            "Keep owned controls outside source or under workspace/results"
        )
    output.mkdir(parents=True, exist_ok=False)
    row = {
        **case,
        "formal_comparison_performed": False,
        "outcome": "not_run",
        "session_error": None,
        "closure_error": None,
    }
    live = None
    try:
        figure = "penguins-mass" if case["kind"] == "integrity" else case["control"]
        spec = copy.deepcopy(
            json.loads((HERE / "figures" / (figure + ".json")).read_text())
        )
        original_input = (HERE / "figures" / spec["data"]["path"]).read_bytes()
        data = output / "owned-input.csv"
        data.write_bytes(original_input)
        spec["data"]["path"] = str(data)
        actual_case = figure + "/first" if case["kind"] != "science" else figure
        live = RUNNER["LiveSession"](
            case["arm"], output / "live", python=python, installed=installed
        )
        request = {"name": "accepted-origin", "case": actual_case}
        initial = live.request(
            {**request, "operation": "render", "spec": spec, "base": str(output)}
        )
        row.update(startup=live.ready, initial=initial)
        if (
            initial["outcome"] != "completed"
            or not initial["current_evidence"]["current"]
        ):
            raise RuntimeError("No original intact producer result")
        folder = Path(initial["folder"])
        result = json.loads(Path(initial["report_file"]).read_text())
        row["task_correct_before_control"] = initial["evaluation"][
            "task_correct_verified"
        ]
        row["geometry_and_other_task_errors"] = initial["evaluation"]["errors"]
        row["physical_task_errors"] = [
            error
            for error in initial["evaluation"]["errors"]
            if error.startswith(("actual_width:", "actual_effective_font:"))
        ]
        row["independent_contract_errors"] = [
            error
            for error in initial["evaluation"]["errors"]
            if error not in row["physical_task_errors"]
        ]
        if case["kind"] == "integrity":
            if result["status"] != "passed" or result["exit_code"] != 0:
                raise RuntimeError(
                    "Integrity control needs actual native acceptance, not fabricated task acceptance"
                )
            path, before, after, reason = mutation(
                case["arm"], case["control"], folder, result, live, data
            )
            (output / "original-mutated-file.bin").write_bytes(before)
            path.write_bytes(after)
            row["mutation"] = {
                "path": str(path),
                "before_sha256": sha(before),
                "after_sha256": sha(after),
                "expected_reason": reason,
            }
            guard = live.request({**request, "operation": "validate"})
            row["guard"] = guard
            if guard["outcome"] != "completed":
                raise RuntimeError("Actual producer guard did not return")
            current = guard["current_evidence"]
            row["matched_expected"] = (
                not current["current"]
                and not current["strict_accepted"]
                and reason in current["reasons"]
                and not row["independent_contract_errors"]
            )
            row["classification"] = (
                "current_audit_needed"
                if not current["current"]
                else "borrowed_acceptance"
            )
        else:
            truth = json.loads((HERE / "ground-truth.json").read_text())[actual_case]
            matches = (
                result["status"] == truth["status"]
                and result["exit_code"] == truth["exit_code"]
            )
            if case["kind"] == "science":
                relevant, signal = relevant_science(
                    case["arm"], case["control"], result, folder
                )
                row["relevant_signal"] = signal
                matches = matches and relevant
            row["matched_expected"] = matches and not row["independent_contract_errors"]
            row["classification"] = classify_science(case["kind"], result["status"])
        row["outcome"] = "completed"
    except Exception as error:  # noqa: BLE001 - preserve every actual planned control
        row.update(
            outcome="execution_error",
            session_error={
                "type": type(error).__name__,
                "message": str(error),
                "traceback": traceback.format_exc(),
            },
        )
    finally:
        if live is not None:
            row["last_dispatch"] = copy.deepcopy(getattr(live, "last_dispatch", None))
            try:
                live.close()
                row["closure"] = live.closed
            except Exception as error:  # noqa: BLE001 - retain real teardown failures
                row["closure_error"] = {
                    "type": type(error).__name__,
                    "message": str(error),
                }
        RUNNER["write"](output / "control.json", row)
    return row
