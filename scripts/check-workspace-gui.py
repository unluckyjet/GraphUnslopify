"""Independently inspect original real-GUI saves and retain every public-task failure."""

from __future__ import annotations

import argparse
import hashlib
import json
import runpy
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "benchmarks/workspace"


def check(browser_file, output, *, execution_context=None):
    if not __debug__:
        raise RuntimeError("Do not optimize independent GUI guards")
    output = Path(output)
    if output.exists():
        raise ValueError("Refuse to replace previous GUI evidence")
    execution_api = runpy.run_path(str(HERE / "execution_context.py"))
    context = execution_api["load"](
        execution_context, repo=ROOT, track="gui", arm="graphunslopify"
    )
    execution = execution_api["receipt"](context)
    root = Path(browser_file).resolve().parent
    browser = json.loads(Path(browser_file).read_text(encoding="utf8"))
    protocol = json.loads((HERE / "protocol.json").read_text(encoding="utf8"))
    runner = runpy.run_path(str(HERE / "session_runner.py"))
    evaluate = runpy.run_path(str(HERE / "evaluation.py"))["evaluate"]
    truth = json.loads((HERE / "ground-truth.json").read_text(encoding="utf8"))
    digest = lambda raw: hashlib.sha256(raw).hexdigest()
    startup = json.loads((root / "server/startup.json").read_text(encoding="utf8"))
    closure = json.loads((root / "server/closure.json").read_text(encoding="utf8"))
    errors = []
    if any(
        v.get("execution_context") != execution for v in (browser, startup, closure)
    ):
        errors.append("actual_gui_execution_context_differs")
    if context.get("case", {}).get("profile", browser["profile"]) != browser["profile"]:
        errors.append("actual_gui_execution_profile_differs")
    if (
        startup["source_sha256"] != runner["source_snapshot"]()
        or startup["package_sha256"] != runner["expected_package"]()
        or closure["errors"]
        or closure["pid"] != startup["pid"]
        or browser["server_exit_code"] != 0
    ):
        errors.append("source_package_or_lifecycle_binding")
    if [row["task"] for row in browser["rows"]] != protocol["gui"]["tasks"]:
        errors.append("planned_seven_tasks_changed_or_missing")
    if browser["page_errors"] or browser["external_requests"]:
        errors.append("browser_page_errors_or_external_requests")
    receipts = [
        json.loads(path.read_text(encoding="utf8"))
        for path in sorted((root / "server/receipts").glob("*.json"))
    ]
    if len(receipts) != closure["responses"]:
        errors.append("recorded_response_count")
    observed = {}
    for receipt in receipts:
        identity = receipt["response"].get("run_id")
        if identity:
            if identity in observed:
                errors.append("duplicate_native_run")
            observed[identity] = receipt
        if receipt["observation_error"]:
            errors.append("actual_save_observation_failed")
    results = []
    seen = set()
    phases = [
        ["first"],
        ["first"],
        ["first"],
        ["first"],
        ["setup", "direct-Title", "direct-Axis label"],
        ["setup", "paper-single", "paper-double", "review-png"],
        ["setup", "mapped-before-unit-correction", "corrected-units"],
    ]
    for index, row in enumerate(browser["rows"]):
        task = {
            "task": row["task"],
            "profile": browser["profile"],
            "attempted": row["attempted"],
            "controls_outcome": row["outcome"],
            "controls_error": row["error"],
            "required_json_edits": row["required_json_edits"],
            "evaluations": [],
            "task_correct_verified": False,
            "formal_comparison_performed": context["formal_comparison_performed"],
            "execution_context": execution,
        }
        if not row["attempted"]:
            errors.append("unattempted_gui_task")
        if row.get("module_network_failures"):
            errors.append("gui_module_network_failure:" + row["task"])
        if (
            row["outcome"] != "completed"
            or [r["phase"] for r in row["responses"]] != phases[index]
        ):
            errors.append("gui_controls_or_actual_responses_incomplete:" + row["task"])
        if (
            row.get("screenshot_error")
            or len(row.get("viewports", [])) != 2
            or any(
                not viewport["no_horizontal_overflow"]
                for viewport in row.get("viewports", [])
            )
        ):
            errors.append("gui_viewport_evidence_failed:" + row["task"])
        for request in row["responses"]:
            answer = request["answer"]
            identity = answer.get("run_id")
            if not identity:
                task["evaluations"].append(
                    {"phase": request["phase"], "unavailable": True}
                )
                continue
            receipt = observed.get(identity)
            if receipt is None or receipt["response"] != answer or identity in seen:
                errors.append("browser_original_reply_binding")
                continue
            seen.add(identity)
            result = receipt["result"]
            if result is None:
                errors.append("original_save_result_unavailable")
                continue
            folder = Path(result["owned_folder"]).resolve()
            if folder != root / "server/editor/runs" / identity:
                raise ValueError("GUI native output escapes its owned run")
            expected = request["expected"]
            data_source = Path(request["data_source"]).resolve()
            name = row["task"].removesuffix("-first") if index < 4 else "iris-scatter"
            if index == 6 and request["phase"] != "setup":
                name = "iris-scatter-mm"
            frozen = json.loads((HERE / "figures" / (name + ".json")).read_text())
            declared = (HERE / "figures" / frozen["data"]["path"]).resolve()
            if data_source != declared:
                raise ValueError("GUI input differs from the registered public task")
            source = declared.read_bytes()
            source_key = declared.relative_to(ROOT).as_posix()
            if digest(source) != protocol["frozen_assets"][source_key]:
                raise ValueError("Frozen GUI source data changed")
            if (folder / "data.csv").read_bytes() != source:
                raise ValueError("GUI rendered different observations")
            stem = result["spec"]["output"]["stem"]
            if (
                digest((folder / (stem + ".py")).read_bytes())
                != result["producer_sha256"]
            ):
                raise ValueError("GUI original generated program changed")
            for filename, signature in result["outputs"].items():
                if (
                    Path(filename).name != filename
                    or digest((folder / filename).read_bytes()) != signature
                ):
                    raise ValueError("GUI original export changed")
            oracle = truth[name if name == "iris-scatter-mm" else name + "/first"]
            evaluated = evaluate(
                result,
                folder,
                expected,
                data_source.parent,
                oracle,
                execution_context=execution_context,
            )
            task["evaluations"].append(
                {"phase": request["phase"], "run_id": identity, "evaluation": evaluated}
            )
        for download in row["downloads"]:
            path = Path(download["path"]).resolve()
            if path.parent != root or digest(path.read_bytes()) != download["sha256"]:
                raise ValueError("Actual GUI download changed")
            if download["kind"] == "bundle":
                with zipfile.ZipFile(path) as archive:
                    for name in archive.namelist():
                        if Path(name).is_absolute() or ".." in Path(name).parts:
                            raise ValueError("GUI bundle has an unsafe member")
                        archive.read(name)
                    original = observed[download["run_id"]]["result"]
                    exports = {
                        name
                        for name in archive.namelist()
                        if name.endswith((".png", ".svg", ".pdf"))
                    }
                    if exports != set(original["outputs"]) or any(
                        digest(archive.read(name)) != signature
                        for name, signature in original["outputs"].items()
                    ):
                        raise ValueError(
                            "Downloaded GUI bundle does not contain the current original exports"
                        )
            elif download["kind"] == "template":
                template = json.loads(path.read_text(encoding="utf8"))
                if (
                    "data" in template["intent"]
                    or "palette_lock" in template["intent"]
                    or "stem" in template["intent"].get("output", {})
                ):
                    raise ValueError(
                        "Portable GUI template leaks source/output ownership"
                    )
        finals = [
            e
            for e in task["evaluations"]
            if e["phase"] not in {"setup", "mapped-before-unit-correction"}
        ]
        task["task_correct_verified"] = bool(
            row["outcome"] == "completed"
            and not row["required_json_edits"]
            and finals
            and all(
                e.get("evaluation", {}).get("task_correct_verified") for e in finals
            )
        )
        results.append(task)
    proof = {
        "profile": browser["profile"],
        "scope": "Seven real GUI preparation tasks; actual original saves, controls, failures and downloads. No formal14 or human authoring claim.",
        "formal_comparison_performed": context["formal_comparison_performed"],
        "execution_context": execution,
        "source_sha256": startup["source_sha256"],
        "package_sha256": startup["package_sha256"],
        "tasks": results,
        "actual_native_responses_verified": len(seen),
        "errors": errors,
        "passed": not errors,
    }
    runner["write"](output, proof)
    return proof


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser-results", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--execution-context", type=Path)
    args = parser.parse_args()
    proof = check(
        args.browser_results, args.out, execution_context=args.execution_context
    )
    print(
        json.dumps(
            {
                "passed": proof["passed"],
                "tasks": len(proof["tasks"]),
                "errors": proof["errors"],
            }
        )
    )
    raise SystemExit(0 if proof["passed"] else 1)
