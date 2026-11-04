"""Reviewable dataset/question proposals and actual strict generation of all three drafts."""

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .autopilot_plan import MAX_DATA
from .errors import SpecError
from .experiment_imports import _contained_bytes
from .owned_reader import ReaderError, run_reader
from .transport import local_request
from .workbook import EXCEL_SUFFIXES


class AutopilotError(ValueError):
    pass


@dataclass
class AutopilotPlan:
    source: Path
    data_bytes: bytes | None
    drafts: list[dict]
    report: dict


def _snapshot(report, drafts):
    return hashlib.sha256(
        json.dumps(
            {"report": {k: v for k, v in report.items() if k != "snapshot"}, "drafts": drafts},
            sort_keys=True,
            allow_nan=False,
        ).encode()
    ).hexdigest()


def propose_figures(source, question, **choices):
    """Propose three grounded canonical views without rendering or changing the input."""
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 2000:
        raise AutopilotError("Describe the research question in 1-2000 characters")
    path = Path(source).expanduser().resolve(strict=True)
    if path.suffix.lower() not in {".csv", ".json", ".parquet", *EXCEL_SUFFIXES}:
        raise AutopilotError("Choose CSV,regular JSON,Parquet or a selected Excel worksheet")
    raw = _contained_bytes(path.parent, path.name)
    if len(raw) > MAX_DATA:
        raise AutopilotError("Autopilot datasets are bounded to20MiB")
    original_sha = hashlib.sha256(raw).hexdigest()
    with tempfile.TemporaryDirectory(prefix="gu-autopilot-") as directory:
        root = Path(directory)
        name = "input" + path.suffix.lower()
        (root / name).write_bytes(raw)
        try:
            value = run_reader(
                root,
                module="graphunslopify.autopilot_worker",
                kind="figure-autopilot",
                payload={"filename": name, "question": question, "choices": choices},
                filename="proposal.json",
                max_output=32 * 1024 * 1024,
                max_rss=1024 * 1024 * 1024,
                timeout=30,
            )
        except ReaderError as problem:
            raise AutopilotError(str(problem)) from problem
    if hashlib.sha256(_contained_bytes(path.parent, path.name)).hexdigest() != original_sha:
        raise AutopilotError("Dataset changed during proposal generation; review it again")
    report = value["report"]
    report.update(
        requested_choices=copy.deepcopy(choices),
        original_name=path.name,
        original_sha256=original_sha,
        original_bytes=len(raw),
        original_format=path.suffix.lower(),
    )
    data = value["data_text"].encode() if value["data_text"] is not None else None
    for draft in value["drafts"]:
        validated = local_request("validate", draft["spec"])
        if not validated["ok"]:
            raise AutopilotError("A proposed view failed canonical static validation")
        draft["spec"] = validated["resolved"]
        draft["static_findings"] = validated["findings"]
        draft["native_status"] = "not_run"
    report["materialized_sha256"] = hashlib.sha256(data).hexdigest() if data is not None else None
    report["snapshot"] = _snapshot(report, value["drafts"])
    return AutopilotPlan(path, data, value["drafts"], report)


def generate_drafts(plan, destination, *, reviewed=False, accept_exclusions=False):
    """Render every reviewed draft strictly; preserve failures rather than select a winner."""
    from .build import Figure

    if reviewed is not True:
        raise AutopilotError("Review question,mapping,units and every draft's assumptions first")
    if not plan.report["ready"] or len(plan.drafts) != 3 or plan.data_bytes is None:
        raise AutopilotError("Resolve the proposed field/intent choices before generation")
    if (
        _snapshot(plan.report, plan.drafts) != plan.report["snapshot"]
        or hashlib.sha256(plan.data_bytes).hexdigest() != plan.report["materialized_sha256"]
    ):
        raise AutopilotError("Proposal metadata,choices or plotting values changed; review again")
    if plan.report["excluded_count"] and accept_exclusions is not True:
        raise AutopilotError("Explicitly accept the recorded joint-sample exclusions")
    if (
        hashlib.sha256(_contained_bytes(plan.source.parent, plan.source.name)).hexdigest()
        != plan.report["original_sha256"]
    ):
        raise AutopilotError("Dataset changed; review proposals again")
    root = Path(destination).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / "autopilot-data.json").write_bytes(plan.data_bytes)
    result = {
        "schema_version": 1,
        "question": plan.report["question"],
        "proposal": copy.deepcopy(plan.report),
        "drafts": [],
        "status": "incomplete",
        "exit_code": 2,
        "scientific_appropriateness_certified": False,
    }

    def save():
        (root / "autopilot.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")

    save()
    for draft in plan.drafts:
        folder = root / draft["id"]
        folder.mkdir()
        spec = copy.deepcopy(draft["spec"])
        spec["data"]["path"] = str(root / "autopilot-data.json")
        (folder / "figure.json").write_text(json.dumps(spec, indent=2) + "\n")
        record = {
            "id": draft["id"],
            "name": draft["name"],
            "why": draft["why"],
            "tradeoff": draft["tradeoff"],
            "assumptions": draft["assumptions"],
            "spec": spec,
        }
        try:
            native = Figure(spec).render(cwd=folder, strict=True, api="local")
            record.update(status=native["report"]["status"], native_report=native["report"])
        except SpecError as problem:
            record.update(
                status=(problem.report or {}).get("status", "incomplete"),
                native_report=problem.report,
                error=str(problem),
            )
        except (OSError, ValueError) as problem:
            record.update(
                status="incomplete",
                native_report=None,
                error="Draft execution failed: " + type(problem).__name__,
            )
        result["drafts"].append(record)
        save()
    same_data = (root / "autopilot-data.json").read_bytes() == plan.data_bytes
    same_source = (
        hashlib.sha256(_contained_bytes(plan.source.parent, plan.source.name)).hexdigest()
        == plan.report["original_sha256"]
    )
    result.update(
        status="passed"
        if all(d["status"] == "passed" for d in result["drafts"]) and same_data and same_source
        else "incomplete",
        source_unchanged=same_source,
        materialized_data_unchanged=same_data,
    )
    result["exit_code"] = 0 if result["status"] == "passed" else 2
    save()
    return result
