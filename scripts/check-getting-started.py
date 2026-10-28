"""Execute the getting-started tour against an installed package outside the checkout."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="interpreter with graphunslopify installed",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        help="new or empty directory for public example evidence",
    )
    args = parser.parse_args()
    python = str(Path(args.python).resolve())
    where = (
        args.work_dir or Path(tempfile.mkdtemp(prefix="gu-getting-started-"))
    ).resolve()
    if where.exists() and any(where.iterdir()):
        parser.error(
            "choose a new or empty work directory; existing inputs are never replaced"
        )
    where.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "GRAPHUNSLOPIFY_API": "local",
        "MPLBACKEND": "Agg",
        "PYTHONIOENCODING": "utf-8",
    }
    started = time.perf_counter()

    def command(*words: str, expected: int = 0):
        result = subprocess.run(
            [python, "-m", "graphunslopify.cli", *words],
            cwd=where,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf8",
            timeout=120,
            check=False,
        )
        if result.returncode != expected:
            raise RuntimeError(
                f"{words}: expected exit{expected}, got{result.returncode}\n{result.stdout}\n{result.stderr}"
            )
        return result.stdout

    def evidence(report, folder):
        assert report["inspection"]["checked"]
        assert {item["format"] for item in report["outputs"]} == {"png", "svg", "pdf"}
        for item in report["outputs"]:
            path = folder / item["path"]
            assert path.stat().st_size == item["bytes"] > 0
            assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
            embedded = json.loads(command("provenance", str(path)))["provenance"]
            assert embedded["spec_hash"] == report["spec_hash"]
            assert embedded["data_sha256_prefix"] == report["data"]["sha256_prefix"]
            assert embedded["script_sha256"] == report["script"]["sha256"]

    doctor = json.loads(command("doctor"))
    assert doctor["ok"]
    first = where / "first-figure"
    passed = json.loads(command("demo", "first-figure", "--json"))
    assert passed["status"] == "passed" and passed["policy"]["strict"]
    assert passed["claims"][0]["verdict"] == "holds"
    assert passed["data"]["counts"]["sample_sizes"] == [4] * 6
    assert len((first / "results.csv").read_text().splitlines()) == 25
    evidence(passed, first)
    rerun = json.loads(command("run", "first-figure/figure.py", "--json"))
    assert rerun["status"] == "passed" and rerun["policy"]["strict"]
    evidence(rerun, first)
    profile = command("describe", "first-figure/results.csv")
    assert all(field in profile for field in ("epoch", "score", "model", "seed"))

    original = first / "figure.json"
    original_bytes = original.read_bytes()
    spec = json.loads(original_bytes)
    review = first / "review.json"
    spec["claims"][0].update(subject="base", reference="ours")
    review.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf8")
    failed = json.loads(
        command(
            "render",
            "first-figure/review.json",
            "--out-dir",
            "first-figure/claim-check",
            "--api",
            "local",
            "--json",
            expected=2,
        )
    )
    assert failed["status"] == "failed" and failed["claims"][0]["verdict"] == "fails"
    assert failed["policy"]["strict"] and not failed["policy"]["passed"]
    evidence(failed, first / "claim-check")
    spec["claims"][0].update(subject="ours", reference="base")
    review.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf8")
    recovered = json.loads(
        command(
            "render",
            "first-figure/review.json",
            "--out-dir",
            "first-figure/claim-check",
            "--api",
            "local",
            "--json",
        )
    )
    assert (
        recovered["status"] == "passed" and recovered["claims"][0]["verdict"] == "holds"
    )
    assert recovered["policy"]["strict"]
    evidence(recovered, first / "claim-check")
    assert original.read_bytes() == original_bytes
    assert (
        passed["data"]["sha256_prefix"]
        == failed["data"]["sha256_prefix"]
        == recovered["data"]["sha256_prefix"]
    )
    result = {
        "status": "passed",
        "python_package": doctor["python_package"],
        "steps": {
            "demo": passed["status"],
            "rerun": rerun["status"],
            "false_claim": failed["status"],
            "recovered": recovered["status"],
        },
        "exit_codes": [
            passed["exit_code"],
            failed["exit_code"],
            recovered["exit_code"],
        ],
        "data_sha256_prefix": passed["data"]["sha256_prefix"],
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "timing_scope": "automated walkthrough after installation, not novice completion time",
        "work_dir": str(where),
    }
    (where / "walkthrough-evidence.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf8"
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
