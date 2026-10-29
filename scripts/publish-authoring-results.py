"""Audit original outputs and publish the complete four-episode authoring observations."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import runpy
import statistics
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def publish(output):
    s = runpy.run_path(str(ROOT / "benchmarks/authoring/session.py"))
    p = s["read_protocol"](ROOT)
    journal = ROOT / "benchmarks/authoring/sessions.jsonl"
    events = s["R"]["journal_events"](journal)
    current, ended = s["active"](events, p["sessions"])
    if current or ended != [slot["id"] for slot in p["sessions"]]:
        raise ValueError("all four declared episodes must be complete")
    if output.exists():
        raise ValueError("choose a fresh publication directory")
    inputs = s["R"]["load_inputs"](
        ROOT,
        ROOT / "benchmarks/certified/.cache/sources",
        ROOT / "benchmarks/certified/.cache/prepared",
    )
    lookup = {i["source"]["id"]: i for i in inputs}
    measure = s["R"]["M"]["read_protocol"](ROOT)
    episodes, rows, pixels, per_dataset = [], [], {}, {}
    sources = None
    files_checked = pngs_checked = 0
    for end in (e for e in events if e["event"] == "end"):
        start = next(
            e
            for e in events
            if e["event"] == "begin" and e["session"] == end["session"]
        )
        if end["seconds"] != (
            end["monotonic_ns"] - start["monotonic_ns"]
        ) / 1e9 or start["protocol_sha256"] != s["sha"](
            ROOT / "benchmarks/authoring/protocol.json"
        ):
            raise ValueError("original clock/protocol identity differs")
        wall = (
            datetime.fromisoformat(end["utc"]) - datetime.fromisoformat(start["utc"])
        ).total_seconds()
        if abs(wall - end["seconds"]) >= 0.01:
            raise ValueError("UTC/monotonic intervals disagree")
        report_path = ROOT / end["report"]
        if s["sha"](report_path) != end["report_sha256"]:
            raise ValueError("a retained original report changed")
        report = json.loads(report_path.read_text())
        slot = next(v for v in p["sessions"] if v["id"] == end["slot"])
        producer = s["producer_path"](ROOT, slot)
        if s["sha"](producer) != end["producer_sha256"]:
            raise ValueError("an authored producer changed after its episode")
        context = s["sources"](start["environment"])
        sources = context if sources is None else sources
        if (
            sources != context
            or context != s["sources"](report["environment"])
            or context != s["sources"](s["R"]["environment"](ROOT))
        ):
            raise ValueError("interpreter/runtime differs between episodes or now")
        plan = s["R"]["schedule"](measure, end["arm"])
        identity = lambda r: tuple(
            r[k] for k in ["dataset", "arm", "variant", "repeat"]
        )
        if not report["passed"] or [identity(r) for r in report["records"]] != [
            identity(r) for r in plan
        ]:
            raise ValueError("the complete nine-case episode is not proven")
        fonts, generated, payloads = [], [], []
        overlaps = 0
        for record in report["records"]:
            folder = Path(end["output"]) / "runs" / record["dataset"]
            s["R"]["retain_case"](
                ROOT,
                folder,
                record,
                lookup[record["dataset"]],
                measure,
                producer=producer,
            )
            if (
                not record["task_accepted"]
                or not record["matches_expected"]
                or record["producer_sha256"] != end["producer_sha256"]
                or s["sha"](folder / "producer-source.py") != end["producer_sha256"]
            ):
                raise ValueError("original case/source/final artifact retention failed")
            for fmt, meta in record["final_exports"]["files"].items():
                actual = folder / ("figure." + fmt)
                if s["sha"](actual) != meta["sha256"]:
                    raise ValueError("final file identity differs")
                files_checked += 1
                if fmt == "png":
                    with Image.open(actual) as image:
                        rgba = image.convert("RGBA")
                        digest = hashlib.sha256(
                            str(rgba.size).encode() + rgba.tobytes()
                        ).hexdigest()
                        if digest != meta["rgba_sha256"]:
                            raise ValueError("decoded PNG identity differs")
                    pixels[(end["arm"], end["round"], record["dataset"])] = digest
                    pngs_checked += 1
            fonts.append(record["measurement"]["exports"]["minimum_text_pt_at_target"])
            overlaps = max(
                overlaps,
                *(
                    len(v["measurement"]["text_overlap_candidates"])
                    for v in record["measurement"]["snapshots"]
                ),
            )
            generated.append(record["generated_script"]["nonblank_lines"])
            payloads.append(record["declarative_payload"]["bytes"])
            for quantity in ["mean", "low", "high", "half_span"]:
                key = record["dataset"]
                values = per_dataset.setdefault(key, {}).setdefault(end["arm"], {})
                error = max(
                    Decimal(v["quantities"][quantity]["absolute_error"])
                    for v in record["numeric"]
                )
                values[quantity] = str(max(error, Decimal(values.get(quantity, "0"))))
            rows.append(
                {
                    "slot": end["slot"],
                    "round": end["round"],
                    "arm": end["arm"],
                    "dataset": record["dataset"],
                    "task_accepted": record["task_accepted"],
                    "numeric_passed": record["numeric_passed"],
                    "quality_passed": record["quality_passed"],
                    "producer_sha256": end["producer_sha256"],
                    "png_rgba_sha256": digest,
                }
            )
        episodes.append(
            {
                "slot": end["slot"],
                "round": end["round"],
                "arm": end["arm"],
                "seconds": end["seconds"],
                "utc_elapsed_seconds": wall,
                "begin_utc": start["utc"],
                "end_utc": end["utc"],
                "attempts": sum(
                    e["event"] == "attempt" and e["session"] == end["session"]
                    for e in events
                ),
                "accepted_cases": len(report["records"]),
                "producer_sha256": end["producer_sha256"],
                "report": end["report"],
                "report_sha256": end["report_sha256"],
                "authored_bytes": producer.stat().st_size,
                "authored_nonblank_lines": sum(
                    bool(t.strip()) for t in producer.read_text().splitlines()
                ),
                "median_generated_nonblank_lines": statistics.median(generated),
                "median_parameter_payload_bytes": statistics.median(payloads),
                "minimum_text_pt_at_target": min(fonts),
                "maximum_overlap_candidates": overlaps,
            }
        )
    pairs = [
        {
            "arm": arm,
            "dataset": name,
            "identical": pixels[(arm, 1, name)] == pixels[(arm, 2, name)],
        }
        for arm in measure["arms"]
        for name in measure["dataset_order"]
    ]
    summary = {
        "phase": "complete-familiarized-authoring-study",
        "study_complete": True,
        "planned_episodes": 4,
        "completed_episodes": len(episodes),
        "accepted_cases": len(rows),
        "protocol_sha256": s["sha"](ROOT / "benchmarks/authoring/protocol.json"),
        "journal_sha256": s["sha"](journal),
        "publisher_sha256": s["sha"](Path(__file__)),
        "measurement_protocol_sha256": s["sha"](
            ROOT / "benchmarks/certified/protocol.json"
        ),
        "episodes": episodes,
        "verified_original_final_files": files_checked,
        "verified_original_png_decodes": pngs_checked,
        "per_dataset_absolute_errors": per_dataset,
        "reimplementation_pixel_pairs": pairs,
        "episode_median_seconds": {
            arm: statistics.median(e["seconds"] for e in episodes if e["arm"] == arm)
            for arm in measure["arms"]
        },
        "shared_runtime_context": sources,
        "shared_study_implementation": {
            name: {
                "sha256": digest,
                "bytes": (ROOT / name).stat().st_size,
                "nonblank_lines": sum(
                    bool(line.strip())
                    for line in (ROOT / name).read_text().splitlines()
                ),
            }
            for name, digest in p["implementation_sha256"].items()
        },
        "scope": "Four unamended familiarized episodes by one coding assistant, all9 cases each; not first-use/human/causal productivity or independent researcher benefit. Earlier invalid42s/3171s clocks retained. Shared preparation/familiarity/CI outside clocks is unmeasured/excluded. Errors retain each dataset's units; generated code size is not authored effort.",
    }
    output.mkdir(parents=True)
    s["R"]["M"]["write_json"](output / "summary.json", summary)
    with (output / "runs.csv").open("x", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return {
        k: summary[k]
        for k in [
            "study_complete",
            "completed_episodes",
            "accepted_cases",
            "verified_original_final_files",
            "verified_original_png_decodes",
            "episode_median_seconds",
        ]
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(publish(args.out_dir.resolve()), indent=2, allow_nan=False))
        return 0
    except (OSError, ValueError, KeyError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
