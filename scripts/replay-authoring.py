"""Replay every completed authoring producer; historical clocks are never rerun."""

from __future__ import annotations

import argparse
import json
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replay(output, source_dir, prepared_dir):
    study = runpy.run_path(str(ROOT / "benchmarks/authoring/session.py"))
    protocol = study["read_protocol"](ROOT)
    events = study["R"]["journal_events"](ROOT / "benchmarks/authoring/sessions.jsonl")
    current, completed = study["active"](events, protocol["sessions"])
    if current or not completed:
        raise ValueError("replay completed episodes after all current live clocks end")
    if output.exists():
        raise ValueError("use a fresh replay directory")
    results = []
    measurement = study["R"]["M"]["read_protocol"](ROOT)
    for end in (e for e in events if e["event"] == "end"):
        start = next(
            e
            for e in events
            if e["event"] == "begin" and e["session"] == end["session"]
        )
        protocol_hash = study["sha"](ROOT / "benchmarks/authoring/protocol.json")
        if (
            start["protocol_sha256"] != protocol_hash
            or end["seconds"] != (end["monotonic_ns"] - start["monotonic_ns"]) / 1e9
        ):
            raise ValueError("historical clock/protocol identity changed")
        slot = next(s for s in protocol["sessions"] if s["id"] == end["slot"])
        producer = study["producer_path"](ROOT, slot)
        original_path = ROOT / end["report"]
        if (
            study["sha"](original_path) != end["report_sha256"]
            or study["sha"](producer) != end["producer_sha256"]
        ):
            raise ValueError("historical report/producer identity changed")
        original = json.loads(original_path.read_text())
        plan = study["R"]["schedule"](measurement, slot["arm"])
        identity = lambda r: tuple(
            r[k] for k in ["dataset", "arm", "variant", "repeat"]
        )
        if (
            not original["passed"]
            or [identity(r) for r in original["records"]] != [identity(r) for r in plan]
            or not all(
                r["task_accepted"]
                and r["matches_expected"]
                and r["producer_sha256"] == end["producer_sha256"]
                for r in original["records"]
            )
        ):
            raise ValueError(
                "historical episode lacks all nine source-bound clean cases"
            )
        actual = study["verify"](
            ROOT, producer, slot["arm"], output / slot["id"], source_dir, prepared_dir
        )
        results.append(
            {
                "slot": slot["id"],
                "arm": slot["arm"],
                "passed": actual["passed"],
                "runs": actual["runs"],
                "producer_sha256": actual["producer_sha256"],
                "historical_authoring_seconds": end["seconds"],
                "replay_report_sha256": study["sha"](
                    output / slot["id"] / "results.json"
                ),
            }
        )
    report = {
        "phase": "authoring-producer-replay",
        "protocol_sha256": protocol_hash,
        "recorded_episodes": len(completed),
        "planned_episodes": len(protocol["sessions"]),
        "study_complete": len(completed) == len(protocol["sessions"]),
        "runs": sum(r["runs"] for r in results),
        "passed": all(r["passed"] for r in results),
        "replay_source_sha256": study["sha"](Path(__file__)),
        "results": results,
        "scope": "Reexecution checks outputs; historical authoring times are retained observations, not measured or reconstructed by replay. Partial completed prefixes do not complete the four-episode study.",
    }
    study["R"]["M"]["write_json"](output / "replay.json", report)
    return {k: v for k, v in report.items() if k != "results"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--source-dir", type=Path, default=ROOT / "benchmarks/certified/.cache/sources"
    )
    parser.add_argument(
        "--prepared-dir",
        type=Path,
        default=ROOT / "benchmarks/certified/.cache/prepared",
    )
    args = parser.parse_args()
    try:
        result = replay(
            args.out_dir.resolve(),
            args.source_dir.resolve(),
            args.prepared_dir.resolve(),
        )
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0 if result["passed"] else 2
    except (OSError, ValueError, KeyError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
