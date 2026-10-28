"""Run the public, project-authored pilot; not an independent scientific benchmark."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import graphunslopify
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "benchmarks/research"
ARMS = ("matplotlib", "matplotlib_assertions", "graphunslopify")


def pixel_hash(path: Path) -> str | None:
    if not path.exists():
        return None
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        return hashlib.sha256(str(rgba.size).encode() + rgba.tobytes()).hexdigest()


def summarize(rows: list[dict], arm: str) -> dict:
    selected = [row for row in rows if row["arm"] == arm]
    counts = {}
    for truth in (
        "valid",
        "invalid",
        "unavailable",
        "execution_error",
        "outside_scope",
    ):
        group = [row for row in selected if row["truth"] == truth]
        counts[truth] = {
            "cases": len(group),
            "blocked": sum(
                any(code != 0 for code in row["exit_codes"]) for row in group
            ),
            "confirmed_failed": sum("failed" in row["statuses"] for row in group),
            "incomplete": sum("incomplete" in row["statuses"] for row in group),
        }
    counts["repeat_consistency"] = {
        "cases": len(selected),
        "disagreements": sum(
            len(set(zip(row["exit_codes"], row["statuses"], strict=True))) != 1
            for row in selected
        ),
    }
    counts["pixel_reproductions"] = {
        "comparable": sum(all(row["pixel_hashes"]) for row in selected),
        "identical": sum(
            all(row["pixel_hashes"]) and len(set(row["pixel_hashes"])) == 1
            for row in selected
        ),
    }
    return counts


def installed_source() -> dict:
    package = Path(graphunslopify.__file__).resolve().parent
    paths = sorted(
        [
            *package.glob("*.py"),
            package / "_translator.mjs",
            *package.glob("schemas/*.json"),
        ]
    )
    return {
        "is_checkout_package": package == (ROOT / "python/graphunslopify").resolve(),
        "sha256": {
            path.relative_to(package).as_posix(): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in paths
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.out_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        parser.error(
            "choose an empty output directory; previous evidence is never overwritten"
        )
    cases = json.loads((FIXTURES / "cases.json").read_text())
    data = (FIXTURES / "results.csv").read_text()
    installed = installed_source()
    rows = []
    for case in cases:
        for arm in ARMS:
            row = {
                "id": case["id"],
                "truth": case["truth"],
                "arm": arm,
                "exit_codes": [],
                "statuses": [],
                "seconds": [],
                "pixel_hashes": [],
            }
            for repeat in range(2):
                folder = output / case["id"] / arm / str(repeat)
                folder.mkdir(parents=True)
                lines = data.splitlines()
                if case.get("singleton"):
                    lines = [
                        lines[0],
                        *[line for line in lines[1:] if line.endswith(",0")],
                    ]
                (folder / "results.csv").write_text("\n".join(lines) + "\n")
                spec = {
                    "kind": "line",
                    "data": {"path": "results.csv"},
                    "x": {"field": "epoch", "label": "Epoch"},
                    "y": {
                        "field": case.get("field", "score"),
                        "label": case.get("label", "Score"),
                    },
                    "group": "model",
                    "aggregation": "mean",
                    "legend": {"position": "outside_bottom"},
                    "output": {"stem": "figure", "formats": ["png"], "dpi": 100},
                }
                if "claim" in case:
                    spec["claims"] = [case["claim"]]
                if case.get("interval"):
                    spec["uncertainty"] = {
                        "kind": "ci",
                        "over": "seed",
                        "display": "band",
                    }
                (folder / "figure.json").write_text(json.dumps(spec, indent=2) + "\n")
                if arm == "graphunslopify":
                    command = [
                        sys.executable,
                        "-m",
                        "graphunslopify.cli",
                        "render",
                        "figure.json",
                        "--api",
                        "local",
                        "--json",
                    ]
                else:
                    command = [
                        sys.executable,
                        str(FIXTURES / "matplotlib_baseline.py"),
                        "figure.json",
                    ]
                    if arm == "matplotlib_assertions":
                        command.append("--assertions")
                start = time.perf_counter()
                result = subprocess.run(
                    command,
                    cwd=folder,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    env={**os.environ, "MPLBACKEND": "Agg"},
                    check=False,
                )
                row["seconds"].append(round(time.perf_counter() - start, 6))
                (folder / "stdout.log").write_text(result.stdout)
                (folder / "stderr.log").write_text(result.stderr)
                try:
                    report = json.loads(result.stdout)
                except ValueError as problem:
                    raise RuntimeError(
                        f"{case['id']}/{arm}: no structured result; inspect {folder}"
                    ) from problem
                if report.get("exit_code", result.returncode) != result.returncode:
                    raise RuntimeError(f"{case['id']}/{arm}: report/exit disagreement")
                row["statuses"].append(report.get("status", "command_error"))
                row["exit_codes"].append(result.returncode)
                row["pixel_hashes"].append(pixel_hash(folder / "figure.png"))
            rows.append(row)
    if installed_source() != installed:
        raise RuntimeError("installed implementation changed during the benchmark")
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    tracked_changes = subprocess.check_output(
        [
            "git",
            "diff",
            "HEAD",
            "--",
            "scripts/research-benchmark.py",
            "benchmarks/research",
        ],
        cwd=ROOT,
    )
    fixture_files = [
        Path(__file__).resolve(),
        FIXTURES / "results.csv",
        FIXTURES / "matplotlib_baseline.py",
        FIXTURES / "cases.json",
    ]
    evidence = {
        "schema_version": 1,
        "study": "project-authored synthetic pilot; no external participants",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "base_revision": revision,
        "tracked_diff_sha256": hashlib.sha256(tracked_changes).hexdigest(),
        "installed_implementation": installed,
        "source_sha256": {
            path.relative_to(ROOT).as_posix(): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in fixture_files
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            **{
                name: importlib.metadata.version(name)
                for name in ("graphunslopify", "matplotlib", "pandas", "numpy")
            },
        },
        "summary": {arm: summarize(rows, arm) for arm in ARMS},
        "cases": rows,
        "limits": [
            "Fixed synthetic cases, selected by project authors; not independent or representative.",
            "Render-only baseline has no semantic verification; assertion-enabled arm is a stronger comparator.",
            "Unavailable checks are abstentions, not confirmed scientific errors.",
            "Missing-column failures are execution checks, counted separately.",
            "Wrong units and causal interpretation cannot be verified from supplied evidence.",
            "Timings include process startup; no human time, quality, power or adoption claims.",
            "Same-environment repeated PNG pixel hashes; not cross-platform or cross-tool visual equality.",
        ],
    }
    (output / "benchmark.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(
        json.dumps(
            {"report": str(output / "benchmark.json"), "summary": evidence["summary"]},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
