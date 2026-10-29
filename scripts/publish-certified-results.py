"""Publish retained benchmark metadata and verify/copy actual outputs without rerunning plots."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
from decimal import Decimal
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def median(values):
    return statistics.median(values) if values else None


def publish(report_path, output, sessions):
    report = json.loads(report_path.read_text())
    if report.get("phase") != "benchmark":
        raise ValueError(
            "publish a formal benchmark report, keeping development attempts separate"
        )
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError(
            "choose a fresh publication directory; prior evidence is retained"
        )
    records = report["records"]
    checked, rgba_checked, missing = 0, 0, []
    for row in records:
        folder = (
            report_path.parent
            / "runs"
            / str(row["repeat"])
            / row["dataset"]
            / row["arm"]
            / row["variant"]
        )
        for fmt in report["protocol"]["formats"]:
            path = folder / ("figure." + fmt)
            recorded = row.get("final_exports", {}).get("files", {}).get(fmt, {})
            if not path.exists() or not recorded:
                missing.append(str(path))
                continue
            if sha(path) != recorded["sha256"]:
                raise ValueError(f"changed final artifact: {path}")
            checked += 1
            if fmt == "png":
                with Image.open(path) as image:
                    rgba = image.convert("RGBA")
                    digest = hashlib.sha256(
                        str(rgba.size).encode() + rgba.tobytes()
                    ).hexdigest()
                    if digest != recorded["rgba_sha256"]:
                        raise ValueError(f"changed decoded PNG: {path}")
                rgba_checked += 1
    if report["passed"] and missing:
        raise ValueError("a passed report has missing final outputs")
    ends = [
        e
        for e in (json.loads(line) for line in sessions.read_text().splitlines())
        if e["event"] == "end"
    ]
    summary = {
        "schema_version": 1,
        "protocol_id": report["protocol"]["id"],
        "protocol_sha256": report["protocol_sha256"],
        "full_report_sha256": sha(report_path),
        "source_git_head": report["environment"]["git_head"],
        "source_git_dirty": report["environment"]["git_dirty"],
        "completed_at": report["completed_at"],
        "passed": report["passed"],
        "runs": report["runs"],
        "expected_runs": report["expected_runs"],
        "datasets": len(report["protocol"]["dataset_order"]),
        "repetition_pairs": len(report["repetition_pairs"]),
        "identical_pixel_pairs": sum(
            p["identical"] for p in report["repetition_pairs"]
        ),
        "outcome_agreement_pairs": sum(
            p["outcome_agreement"] for p in report["repetition_pairs"]
        ),
        "independently_rechecked_final_files": checked,
        "independently_rechecked_png_rgba": rgba_checked,
        "missing_outputs": missing,
        "arms": {},
        "per_dataset": {},
        "shared_runtime_helpers": report["environment"]["common_source"],
        "development_sessions": ends,
        "paired_development_timing_valid": len(ends) == 2
        and all(e.get("timing_comparison_valid", True) for e in ends),
        "timing_scope": "Clean-condition fresh-process medians with warm caches and measurement overhead; no human productivity inference",
        "shared_preparation_scope": "Prior shared design/preparation time is unmeasured and excluded; listed helper sizes are selected runtime code, not total project cost",
        "study_scope": "Project-run mean/sample-SD plots against external NIST facts; not an independent researcher-run study or whole StRD certification",
    }
    summary["development_source_matches"] = {
        event["arm"]: all(
            row["producer_sha256"] == event["producer_sha256"]
            for row in records
            if row["arm"] == event["arm"]
        )
        for event in ends
    }
    summary["paired_development_timing_valid"] = summary[
        "paired_development_timing_valid"
    ] and all(summary["development_source_matches"].values())
    for arm in report["protocol"]["arms"]:
        rows = [r for r in records if r["arm"] == arm and r["variant"] == "mean_sd"]
        measurements = [r["measurement"] for r in rows if r.get("measurement")]
        fonts = [
            m["exports"]["minimum_text_pt_at_target"]
            for m in measurements
            if m["exports"].get("minimum_text_pt_at_target") is not None
        ]
        snapshots = [s for m in measurements for s in m["snapshots"]]
        example = next((r for r in rows if r.get("generated_script")), None)
        source = (
            report_path.parent
            / "runs"
            / str(example["repeat"])
            / example["dataset"]
            / arm
            / "mean_sd/producer-source.py"
            if example
            else None
        )
        size = None
        if source and source.exists():
            if sha(source) != example["producer_sha256"]:
                raise ValueError("producer snapshot differs from its measured source")
            size = {
                "sha256": sha(source),
                "bytes": source.stat().st_size,
                "nonblank_lines": sum(
                    bool(s.strip()) for s in source.read_text().splitlines()
                ),
            }
        summary["arms"][arm] = {
            **report["arms"][arm],
            "clean_timing_medians": {
                "producer_build_seconds": median([r["build"]["seconds"] for r in rows]),
                "process_wall_seconds": median(
                    [r["execution"]["seconds"] for r in rows if r.get("execution")]
                ),
                "instrumented_script_seconds": median(
                    [m["instrumented_execution_seconds"] for m in measurements]
                ),
                "save_seconds": median([m["save_seconds"] for m in measurements]),
            },
            "clean_timing_measurements": len(measurements),
            "minimum_clean_text_pt_at_target": min(fonts) if fonts else None,
            "overlap_observed_snapshots": len(snapshots),
            "maximum_clean_overlap_candidates": max(
                (len(s["measurement"]["text_overlap_candidates"]) for s in snapshots),
                default=None,
            ),
            "authored_producer": size,
            "median_clean_generated_nonblank_lines": median(
                [
                    r["generated_script"]["nonblank_lines"]
                    for r in rows
                    if r.get("generated_script")
                ]
            ),
            "median_clean_payload_bytes": median(
                [
                    r["declarative_payload"]["bytes"]
                    for r in rows
                    if r.get("declarative_payload")
                ]
            ),
        }
    for name in report["protocol"]["dataset_order"]:
        summary["per_dataset"][name] = {}
        for arm in report["protocol"]["arms"]:
            rows = [
                r
                for r in records
                if r["dataset"] == name
                and r["arm"] == arm
                and r["variant"] == "mean_sd"
            ]
            values = {}
            for key in ("mean", "low", "high", "half_span"):
                errors = [
                    Decimal(n["quantities"][key]["absolute_error"])
                    for r in rows
                    for n in r["numeric"]
                    if "absolute_error" in n["quantities"][key]
                ]
                values[key] = str(max(errors)) if errors else None
            summary["per_dataset"][name][arm] = values
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_bytes(report_path.read_bytes())
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n"
    )
    with (output / "runs.csv").open("x", newline="") as handle:
        fields = [
            "dataset",
            "arm",
            "variant",
            "repeat",
            "task_accepted",
            "matches_expected",
            "numeric_passed",
            "quality_passed",
            "labels_passed",
            "artifacts_retained",
            "script_exit_code",
            "native_status",
            "build_seconds",
            "process_seconds",
            "instrumented_seconds",
            "save_seconds",
            "minimum_text_pt",
            "png_rgba_sha256",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for r in records:
            m = r.get("measurement") or {}
            row = {key: r[key] for key in fields if key in r}
            row.update(
                script_exit_code=m.get("script_exit_code"),
                native_status=(r.get("built_in_report") or {}).get("status", "absent"),
                build_seconds=r["build"]["seconds"],
                process_seconds=(r.get("execution") or {}).get("seconds"),
                instrumented_seconds=m.get("instrumented_execution_seconds"),
                save_seconds=m.get("save_seconds"),
                minimum_text_pt=m.get("exports", {}).get("minimum_text_pt_at_target"),
                png_rgba_sha256=r.get("final_exports", {})
                .get("files", {})
                .get("png", {})
                .get("rgba_sha256"),
            )
            writer.writerow(row)
    figures = output / "figures"
    figures.mkdir()
    for row in records:
        if (
            row["dataset"] not in {"Mavro", "NumAcc4"}
            or row["variant"] != "mean_sd"
            or row["repeat"] != 0
        ):
            continue
        source = (
            report_path.parent
            / "runs/0"
            / row["dataset"]
            / row["arm"]
            / "mean_sd/figure.png"
        )
        if source.exists():
            (figures / f"{row['dataset']}-{row['arm']}.png").write_bytes(
                source.read_bytes()
            )
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--sessions",
        type=Path,
        default=ROOT / "benchmarks/certified/development-sessions.jsonl",
    )
    args = parser.parse_args()
    try:
        summary = publish(
            args.report.resolve(), args.out_dir.resolve(), args.sessions.resolve()
        )
    except (OSError, ValueError, KeyError) as problem:
        print(json.dumps({"status": "failed", "error": str(problem)}))
        return 2
    print(
        json.dumps(
            {
                k: summary[k]
                for k in [
                    "passed",
                    "runs",
                    "independently_rechecked_final_files",
                    "independently_rechecked_png_rgba",
                ]
            },
            indent=2,
        )
    )
    return 0 if summary["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
