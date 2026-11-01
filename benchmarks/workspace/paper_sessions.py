"""Isolated actual paper sessions; formal measurement is not enabled yet."""

from __future__ import annotations

import json
import runpy
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNNER = runpy.run_path(str(HERE / "session_runner.py"))
write, LiveSession = RUNNER["write"], RUNNER["LiveSession"]
ROOT = HERE.parents[1]


def schedule():
    """Six complete sessions in the original alternating arm order."""
    protocol = json.loads((HERE / "protocol.json").read_text(encoding="utf8"))
    return [
        {"session": repeat, "arm": arm}
        for repeat in range(protocol["paper"]["sessions_per_arm"])
        for arm in (
            ["graphunslopify", "matplotlib"]
            if repeat % 2
            else ["matplotlib", "graphunslopify"]
        )
    ]


def run_sequence(arm, folder, *, python=sys.executable, installed=False, timeout=240):
    """Preserve all nine planned cells after real startup/request/closure failures."""
    folder = Path(folder).resolve()
    if folder.is_relative_to(ROOT) and not folder.is_relative_to(HERE / "results"):
        raise ValueError(
            "Keep owned paper outputs outside source or under workspace/results"
        )
    folder.mkdir(parents=True, exist_ok=False)
    plan = json.loads((HERE / "protocol.json").read_text(encoding="utf8"))["paper"][
        "steps"
    ]
    rows = [
        {
            "arm": arm,
            "step": p["id"],
            "phase": "cold" if i == 0 else "warm",
            "outcome": "not_run",
            "formal_comparison_performed": False,
        }
        for i, p in enumerate(plan)
    ]
    result = {
        "arm": arm,
        "rows": rows,
        "formal_comparison_performed": False,
        "scope": "Pre-seal isolated paper integrity only; not formal54 requests",
        "session_error": None,
        "closure_error": None,
    }
    live = None
    try:
        live = LiveSession(
            arm,
            folder / "live",
            python=python,
            installed=installed,
            timeout=timeout,
            track="paper",
        )
        result["startup"] = {
            "launched_ns": live.launched_ns,
            "ready_received_ns": live.ready_received_ns,
            "pid": live.ready["pid"],
            "python": live.ready["python"],
            "package_root": live.ready["package_root"],
            "producer_preparing_ns": live.ready["producer_preparing_ns"],
            "producer_prepared_ns": live.ready["producer_prepared_ns"],
        }
        if (
            not live.launched_ns
            <= live.ready["producer_preparing_ns"]
            <= live.ready["producer_prepared_ns"]
            <= live.ready_received_ns
        ):
            raise ValueError("Paper setup counters are outside the actual startup")
        for index, expected in enumerate(plan):
            answer = live.request(
                {
                    "operation": "step",
                    "step": expected["id"],
                    "case": "paper/" + expected["id"],
                }
            )
            row = rows[index]
            row.update(answer)
            origin = live.launched_ns if index == 0 else answer["parent_dispatched_ns"]
            row["end_to_end_origin_ns"] = origin
            row["timing_envelope_valid"] = False
            if answer["outcome"] != "completed":
                raise RuntimeError(
                    "Actual paper worker request failed; no replacement worker"
                )
            if (
                not origin
                <= answer["worker_started_ns"]
                <= answer["tool_end_ns"]
                <= answer["checked_ns"]
                <= answer["parent_received_ns"]
            ):
                raise ValueError(
                    "Paper request counters do not share the actual parent envelope"
                )
            first = answer["first_png_available_ns"]
            if (
                first is not None
                and not answer["worker_started_ns"] <= first <= answer["tool_end_ns"]
            ):
                raise ValueError(
                    "Current-request PNG event is outside the actual request"
                )
            row["timing_envelope_valid"] = True
            write(folder / "sequence-progress.json", result)
    except Exception as error:  # noqa: BLE001 - keep the failed attempt and entire fixed sequence
        result["session_error"] = {
            "type": type(error).__name__,
            "error": str(error),
            "traceback": traceback.format_exc(),
        }
        for row in rows:
            if row["outcome"] == "not_run":
                dispatch = getattr(live, "last_dispatch", None)
                if dispatch and dispatch["case"] == "paper/" + row["step"]:
                    row.update(
                        dispatch,
                        outcome="response_unavailable",
                        unavailable_reason="Actual dispatch retained; worker response unavailable, no replacement",
                    )
                else:
                    row["unavailable_reason"] = (
                        "Paper session interrupted; no substitute worker/request"
                    )
    finally:
        if live is not None:
            try:
                live.close()
                result["closure"] = live.closed
            except Exception as error:  # noqa: BLE001 - failed cleanup cannot establish clean-session evidence
                result["closure_error"] = {
                    "type": type(error).__name__,
                    "error": str(error),
                    "traceback": traceback.format_exc(),
                }
        write(folder / "sequence.json", result)
    return result
