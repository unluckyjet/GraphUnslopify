"""Read original fixed-track results; preparation never produces formal timing claims."""

import argparse
import hashlib
import json
import math
import runpy
import statistics
from collections import Counter, defaultdict
from pathlib import Path

if not __debug__:
    raise RuntimeError("Do not optimize analysis evidence guards")

ROOT = None
API = None
TRUTH = None


def percent(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lo, hi = math.floor(position), math.ceil(position)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (position - lo)


def describe(values):
    q1, q3 = percent(values, 0.25), percent(values, 0.75)
    return {
        "observed": len(values),
        "median": statistics.median(values) if values else None,
        "q1": q1,
        "q3": q3,
        "iqr": q3 - q1 if values else None,
    }


def terminal_metrics(row):
    origin = row.get("end_to_end_origin_ns")
    fields = {
        "first_current_unverified_png_ms": "first_png_available_ns",
        "tool_acceptance_ms": "tool_accepted_ns",
        "task_correct_strict_ms": "task_verified_ns",
        "terminal_including_independent_checks_ms": "parent_received_ns",
    }
    answer = {}
    for label, name in fields.items():
        end = row.get(name)
        if origin is None or end is None:
            answer[label] = None
        else:
            assert isinstance(origin, int) and isinstance(end, int) and end >= origin
            answer[label] = (end - origin) / 1_000_000
    return answer


def analyze(inputs, mode, seal=None):
    assert mode in {"preseal", "formal"}
    if mode == "formal":
        assert set(inputs) == set(API["TOTALS"]) and all(inputs.values())
        API["EXECUTION"]["validate_seal"](seal, ROOT)
    else:
        assert seal is None
    seal_digest = (
        API["EXECUTION"]["digest"](API["EXECUTION"]["canonical"](seal))
        if seal is not None
        else None
    )
    tracks, evidence, detailed, timings = {}, [], [], defaultdict(list)
    confusion = defaultdict(Counter)
    paper_counts, startup, timing_retained = [], defaultdict(list), Counter()
    for track, total in API["TOTALS"].items():
        counts = Counter()
        arm_counts = defaultdict(Counter)
        profiles = set()
        for filename in inputs.get(track, []):
            path = Path(filename)
            raw = path.read_bytes()
            proof = json.loads(raw)
            assert proof["track"] == track and proof["mode"] == mode
            assert proof["formal_comparison_performed"] is (mode == "formal")
            assert proof["source_sha256"] == API["RUNNER"]["source_snapshot"]()
            assert proof["package_sha256"] == API["RUNNER"]["expected_package"]()
            files = {
                p.relative_to(path.parent).as_posix(): hashlib.sha256(
                    p.read_bytes()
                ).hexdigest()
                for p in sorted(path.parent.rglob("*"))
                if p.is_file()
                and p.relative_to(path.parent).as_posix()
                not in {"study.json", "progress.json"}
            }
            assert files == proof["files_sha256"], (
                "Original evidence changed or is missing"
            )
            profile = (
                proof["plan"][0]["case"]["profile"] if track == "native_ci" else None
            )
            if profile:
                assert profile not in profiles
                profiles.add(profile)
            expected = API["plan"](track, native_profile=profile)
            assert proof["plan"] == expected and len(proof["records"]) == len(expected)
            assert (
                proof["planned_cells"]
                == proof["retained_cells"]
                == sum(len(r["cells"]) for r in expected)
            )
            evidence.append(
                {
                    "track": track,
                    "file": str(path),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "interrupted": proof["interrupted"],
                    "complete": proof["complete"],
                }
            )
            for planned, record in zip(expected, proof["records"], strict=True):
                assert all(record[k] == value for k, value in planned.items())
                case, result = planned["case"], record.get("result", {})
                context_raw = (
                    path.parent / "contexts" / (planned["id"] + ".json")
                ).read_bytes()
                context_sha = hashlib.sha256(context_raw).hexdigest()
                context = json.loads(context_raw)
                assert (
                    context["mode"] == mode
                    and context["track"] == track
                    and context["arm"] == case["arm"]
                )
                assert context["case"] == API["context_case"](track, case)
                if record["attempted"]:
                    assert record["context_sha256"] == context_sha
                if mode == "formal":
                    assert (
                        context["seal_sha256"] == seal_digest
                        and context["seal"] == seal
                    )
                else:
                    assert (
                        context.get("seal") is None
                        and context.get("seal_sha256") is None
                    )
                receipt = API["EXECUTION"]["receipt"](
                    {
                        **context,
                        "context_sha256": context_sha,
                        "formal_comparison_performed": mode == "formal",
                    }
                )
                if result:
                    assert result["execution_context"] == receipt
                rows = (
                    result.get("rows", [])
                    if track in {"single", "paper"}
                    else result.get("tasks", [])
                    if track == "gui"
                    else [result]
                )
                if rows:
                    assert len(rows) == len(planned["cells"])
                if (
                    mode == "formal"
                    and track in {"single", "paper"}
                    and result.get("startup")
                ):
                    s = result["startup"]
                    startup[
                        (track, case.get("figure", "whole-paper"), case["arm"])
                    ].append((s["ready_received_ns"] - s["launched_ns"]) / 1_000_000)
                for index, cell in enumerate(planned["cells"]):
                    row = rows[index] if rows else {}
                    if row:
                        assert row["execution_context"] == receipt
                    counts["retained"] += 1
                    completed = (
                        row.get("outcome") == "completed"
                        if track != "gui"
                        else row.get("controls_outcome") == "completed"
                    )
                    counts["completed"] += int(completed)
                    dispatched = (
                        row.get("parent_dispatched_ns") is not None
                        if track in {"single", "paper"}
                        else bool(record["attempted"])
                    )
                    counts["attempted"] += int(dispatched)
                    counts["unavailable"] += int(not completed)
                    accepted = (
                        None
                        if track == "reliability"
                        else row.get("task_verified_ns") is not None
                        if track in {"single", "paper"}
                        else row.get("task_correct_verified") is True
                        if track == "gui"
                        else row.get("evaluation", {}).get("task_correct_verified")
                        is True
                    )
                    cell_counts = {
                        "retained": 1,
                        "completed": int(completed),
                        "attempted": int(dispatched),
                        "unavailable": int(not completed),
                    }
                    if accepted is not None:
                        counts["task_correct_strict"] += int(accepted)
                        cell_counts["task_correct_strict"] = int(accepted)
                    else:
                        before = int(row.get("task_correct_before_control") is True)
                        counts["initial_task_correct_before_control"] += before
                        cell_counts["initial_task_correct_before_control"] = before
                    arm_counts[case["arm"]].update(cell_counts)
                    detail = {
                        "track": track,
                        "case": case,
                        "cell": cell,
                        "completed": completed,
                        "attempted": dispatched,
                        "task_correct_strict": accepted,
                    }
                    if track in {"single", "paper"}:
                        assert not row or row.get("formal_comparison_performed") is (
                            mode == "formal"
                        )
                        detail["tool_status"] = row.get("tool_status")
                        detail["first_png_unavailable_reason"] = row.get(
                            "first_png_unavailable_reason"
                        )
                        if mode == "formal":
                            metrics = terminal_metrics(row)
                            detail["metrics"] = metrics
                            for name, value in metrics.items():
                                key = (
                                    track,
                                    case.get("figure", "whole-paper"),
                                    str(cell),
                                    case["arm"],
                                    row.get("phase", "unavailable"),
                                    name,
                                )
                                timing_retained[key] += 1
                                observed = timings[key]
                                if value is not None:
                                    observed.append(value)
                        if track == "paper" and row.get("paper"):
                            native = row["paper"]["native"]
                            paper_counts.append(
                                {
                                    "arm": case["arm"],
                                    "session": case["session"],
                                    "step": cell,
                                    "actual": native["audit"]["execution_counts"],
                                }
                            )
                    if track == "reliability":
                        expected_class = (
                            "current_audit_needed"
                            if case["kind"] == "integrity"
                            else "clean_science"
                            if case["kind"] == "clean"
                            else "scientific_failure"
                            if TRUTH[case["control"]]["status"] == "failed"
                            else "scientific_abstention"
                        )
                        actual_class = row.get("classification", "unavailable")
                        confusion[case["arm"]][(expected_class, actual_class)] += 1
                        detail.update(
                            expected_scientific_class=expected_class,
                            actual_scientific_class=actual_class,
                            physical_task_errors=row.get("physical_task_errors"),
                            matched_expected=row.get("matched_expected"),
                        )
                    detailed.append(detail)
        tracks[track] = {
            "registered_total": total,
            "observed": dict(counts),
            "by_arm": {k: dict(v) for k, v in arm_counts.items()},
            "missing_planned_cells": total - counts["retained"],
            "all_planned_cells_retained": counts["retained"] == total,
        }
        assert 0 <= counts["retained"] <= total
        if mode == "formal":
            assert counts["retained"] == total
    matrices = {}
    for arm, values in confusion.items():
        labels = sorted(
            {
                "clean_science",
                "scientific_failure",
                "scientific_abstention",
                "current_audit_needed",
            }
            | {x for pair in values for x in pair}
        )
        matrices[arm] = {
            "scope": "Observed scientific/integrity classifications; physical-task failures remain separate",
            "labels": labels,
            "cells": [
                {"expected": e, "actual": v, "count": values[e, v]}
                for e in labels
                for v in labels
            ],
        }
    pairs = defaultdict(dict)
    for key, values in timings.items():
        if key[5] == "task_correct_strict_ms":
            pairs[(key[0], key[1], key[2], key[4])][key[3]] = {
                "retained": timing_retained[key],
                **describe(values),
            }
    paired = []
    for key, arms in pairs.items():
        eligible = set(arms) == {"matplotlib", "graphunslopify"} and all(
            v["retained"] == v["observed"] == 3 for v in arms.values()
        )
        paired.append(
            {
                "track": key[0],
                "figure": key[1],
                "step": key[2],
                "phase": key[3],
                "arms": arms,
                "all_three_sessions_task_correct_both_arms": eligible,
                "graph_minus_baseline_median_ms": arms["graphunslopify"]["median"]
                - arms["matplotlib"]["median"]
                if eligible
                else None,
            }
        )
    clean_timing = (
        mode == "formal"
        and all(not e["interrupted"] and e["complete"] for e in evidence)
        and all(t["all_planned_cells_retained"] for t in tracks.values())
    )
    return {
        "mode": mode,
        "formal_comparison_performed": mode == "formal",
        "clean_timing_interpretation_valid": clean_timing,
        "scope": "Project-run fixed operational tracks; familiar prewritten actor,not human productivity,blind quality,adoption or general model quality",
        "latencies_emitted": mode == "formal",
        "quantile_method": "Linear interpolation at (n-1)*p; missing times omitted with explicit observed count,never zero-filled",
        "tracks": tracks,
        "evidence": evidence,
        "reliability_matrices": matrices,
        "actual_paper_execution_counts": paper_counts,
        "cold_startup_ms": [
            {"track": k[0], "figure": k[1], "arm": k[2], **describe(v)}
            for k, v in startup.items()
        ],
        "per_task_metrics_ms": [
            {
                "track": k[0],
                "figure": k[1],
                "step": k[2],
                "arm": k[3],
                "phase": k[4],
                "metric": k[5],
                "retained_requests": timing_retained[k],
                "missing_times": timing_retained[k] - len(v),
                **describe(v),
            }
            for k, v in timings.items()
        ],
        "paired_task_verified_comparisons": paired,
        "raw_cell_summaries": detailed,
        "formal_inference_requires_all_tracks_and_clean_timing": True,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--inputs", type=Path, required=True)
    p.add_argument("--mode", choices=["preseal", "formal"], required=True)
    p.add_argument("--seal", type=Path)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    assert (a.mode == "formal") == (a.seal is not None)
    ROOT = a.repo.resolve()
    API = runpy.run_path(str(ROOT / "benchmarks/workspace/study_runner.py"))
    TRUTH = json.loads((ROOT / "benchmarks/workspace/ground-truth.json").read_text())
    inputs = json.loads(a.inputs.read_text())
    inputs = {
        name: [
            str((a.inputs.parent / p).resolve()) if not Path(p).is_absolute() else p
            for p in paths
        ]
        for name, paths in inputs.items()
    }
    result = analyze(inputs, a.mode, json.loads(a.seal.read_text()) if a.seal else None)
    with a.out.open("x") as f:
        json.dump(result, f, indent=2, allow_nan=False)
        f.write("\n")
    print(
        json.dumps(
            {
                "mode": result["mode"],
                "latencies_emitted": result["latencies_emitted"],
                "tracks": result["tracks"],
            }
        )
    )
