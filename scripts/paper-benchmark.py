"""Reproduce descriptive plots and check seeded faults on two public paper datasets."""

from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import importlib.metadata
import io
import json
import math
import os
import runpy
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples/published-papers"
REFERENCE = runpy.run_path(str(ROOT / "benchmarks/papers/reference.py"))


def close(actual: float | None, expected: float | None) -> bool:
    return (
        actual is None
        and expected is None
        or (
            actual is not None
            and expected is not None
            and math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-10)
        )
    )


def compare(actual: list[dict], expected: list[dict]) -> dict:
    if len(actual) != len(expected):
        raise AssertionError(f"artist count differs: {len(actual)} vs {len(expected)}")
    compared, error = 0, 0.0
    for drawn, oracle in zip(actual, expected, strict=True):
        if drawn["x"] != oracle["x"] or drawn["group"] != oracle["group"]:
            raise AssertionError(f"artist identity differs: {drawn} vs {oracle}")
        for key in ("mean", "low", "high") if "mean" in oracle else ("x", "y"):
            if not close(drawn[key], oracle[key]):
                raise AssertionError(
                    f"artist quantity differs for {key}: {drawn} vs {oracle}"
                )
            if oracle[key] is not None:
                error = max(error, abs(drawn[key] - oracle[key]))
                compared += 1
    return {
        "artists": len(actual),
        "numeric_values": compared,
        "max_absolute_error": error,
    }


def probe(script: Path, kind: str) -> list[dict]:
    before = Path.cwd()
    try:
        os.chdir(script.parent)
        with contextlib.redirect_stdout(io.StringIO()):
            module = runpy.run_path(str(script))
            frame = module["prepare"](module["load"]())
            figure, axes = module["plt"].subplots()
            try:
                module["draw_panel"](axes, frame)
                if kind == "bar":
                    return REFERENCE["artists"](axes, module["category_order"](frame))
                return REFERENCE["scatter_artists"](axes)
            finally:
                module["plt"].close(figure)
    finally:
        os.chdir(before)


def pixels(path: Path) -> str:
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        return hashlib.sha256(str(rgba.size).encode() + rgba.tobytes()).hexdigest()


def expected_artists(spec: dict, base: Path) -> list[dict]:
    rows = REFERENCE["observations"](spec, base)
    if spec["kind"] == "bar":
        return REFERENCE["summaries"](rows)
    return sorted(
        [{"x": x, "group": group, "y": y} for x, group, y in rows],
        key=lambda row: (row["group"], row["x"], row["y"]),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.out_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        parser.error("choose an empty output directory; previous evidence is retained")
    runpy.run_path(str(ROOT / "scripts/prepare-paper-data.py"))["prepare"]()
    fingerprint = runpy.run_path(str(ROOT / "scripts/research-benchmark.py"))[
        "installed_source"
    ]
    installed = fingerprint()
    if not installed["is_checkout_package"]:
        raise ValueError("install this checkout with python -m pip install -e ./python")
    cases = []
    for name in (
        "penguins-mass",
        "iris-measurements",
        "penguins-scatter",
        "iris-scatter",
    ):
        spec = json.loads((EXAMPLES / f"{name}.json").read_text())
        spec["data"]["path"] = str((EXAMPLES / spec["data"]["path"]).resolve())
        cases.append((name, "passed", spec))
    for name, subject, reference in (
        ("penguins-mass", "female", "male"),
        ("iris-measurements", "Iris-virginica", "Iris-setosa"),
    ):
        spec = json.loads(
            json.dumps(next(spec for stem, _, spec in cases if stem == name))
        )
        spec["claims"] = [
            {"kind": "beats_everywhere", "subject": subject, "reference": reference}
        ]
        cases.append((name + "-false-claim", "failed", spec))
    absent = json.loads(json.dumps(cases[0][2]))
    absent["claims"][0]["reference"] = "absent"
    absent.pop("series_order", None)
    cases.append(("penguins-missing-reference", "incomplete", absent))
    single = json.loads(json.dumps(cases[0][2]))
    # Each cell has one real observation, selected without changing its value.
    with Path(single["data"]["path"]).open(newline="", encoding="utf8") as handle:
        source_rows = list(csv.DictReader(handle))
    selected = {}
    for row in source_rows:
        if row["sex"] in {"female", "male"} and row["body_mass_g"] != "NA":
            selected.setdefault((row["species"], row["sex"]), row)
    single_data = output / "singleton-penguins.csv"
    with single_data.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(source_rows[0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(selected.values())
    single["data"]["path"] = str(single_data)
    single.pop("claims", None)
    cases.append(("penguins-singleton-sd", "incomplete", single))
    records = []
    for name, expected_status, spec in cases:
        record = {"id": name, "expected_status": expected_status, "attempts": []}
        for repeat in range(2):
            folder = output / name / str(repeat)
            folder.mkdir(parents=True)
            spec_path = folder / "input.json"
            spec_path.write_text(json.dumps(spec, indent=2) + "\n")
            baseline = REFERENCE["baseline"](spec, folder, folder / "matplotlib.png")
            command = [
                sys.executable,
                "-m",
                "graphunslopify.cli",
                "render",
                str(spec_path),
                "--out-dir",
                str(folder),
                "--api",
                "local",
                "--json",
            ]
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=120, check=False
            )
            (folder / "stdout.log").write_text(result.stdout)
            (folder / "stderr.log").write_text(result.stderr)
            report = json.loads(result.stdout)
            expected_exit = 0 if expected_status == "passed" else 2
            if (
                result.returncode != expected_exit
                or report["status"] != expected_status
                or baseline["status"] != expected_status
                or baseline["exit_code"] != expected_exit
            ):
                raise AssertionError(
                    f"{name}: expected {expected_status}/{expected_exit}, got CLI {result.returncode}/{report.get('status')} baseline {baseline['status']}; inspect {folder}"
                )
            expected = expected_artists(spec, folder)
            baseline_check = compare(baseline["artists"], expected)
            product_check = compare(probe(folder / "figure.py", spec["kind"]), expected)
            record["attempts"].append(
                {
                    "status": report["status"],
                    "exit_code": result.returncode,
                    "baseline_status": baseline["status"],
                    "baseline_exit": baseline["exit_code"],
                    "reference_rows": baseline["rows"],
                    "reference_summaries": baseline["reference"],
                    "baseline_quantities": baseline_check,
                    "graphunslopify_quantities": product_check,
                    "pixels": {
                        arm: pixels(folder / filename)
                        for arm, filename in (
                            ("matplotlib", "matplotlib.png"),
                            ("graphunslopify", "figure.png"),
                        )
                    },
                    "claim_verdicts": [claim["verdict"] for claim in report["claims"]],
                }
            )
        record["pixels_reproduce"] = all(
            record["attempts"][0]["pixels"][arm] == record["attempts"][1]["pixels"][arm]
            for arm in ("matplotlib", "graphunslopify")
        )
        if not record["pixels_reproduce"]:
            raise AssertionError(f"{name}: same-environment pixel reproduction failed")
        records.append(record)
        print(
            name,
            expected_status,
            "numeric quantities match; both arms reproduce PNG pixels",
        )
    tracked = [
        Path(__file__).resolve(),
        ROOT / "scripts/prepare-paper-data.py",
        ROOT / "scripts/research-benchmark.py",
        ROOT / "benchmarks/papers/reference.py",
        ROOT / "benchmarks/papers/sources.json",
        *sorted((ROOT / "benchmarks/papers/sources").iterdir()),
        *sorted(EXAMPLES.glob("*.json")),
        *sorted((EXAMPLES / "data").glob("*.csv")),
    ]
    if fingerprint() != installed:
        raise ValueError("installed implementation changed during the benchmark")
    evidence = {
        "schema_version": 1,
        "scope": "author-run published-data descriptive reproduction and seeded faults; not full paper replication or independent external validation",
        "base_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "source_sha256": {
            p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in tracked
        },
        "installed_implementation": installed,
        "environment": {
            "python": sys.version.split()[0],
            **{
                name: importlib.metadata.version(name)
                for name in ("graphunslopify", "matplotlib", "numpy", "pandas")
            },
        },
        "executions": len(records) * 2 * 2,
        "cases": records,
    }
    (output / "paper-benchmark.json").write_text(json.dumps(evidence, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
