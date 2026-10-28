"""Ordinary Matplotlib plus optional, separately written application assertions.

This baseline never imports GraphUnslopify. It intentionally makes no claim
that ordinary Matplotlib is a scientific verifier. The assertion-enabled arm
shows what a researcher can accomplish by writing their own validation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def run(spec: dict, destination: Path, *, validate: bool) -> dict:
    frame = pd.read_csv(spec["data"]["path"])
    x, y, group = spec["x"]["field"], spec["y"]["field"], spec["group"]
    means = frame.groupby([group, x])[y].mean().unstack(group)
    findings = []
    if validate:
        for claim in spec.get("claims", []):
            subject, reference = claim["subject"], claim["reference"]
            if subject not in means or reference not in means:
                findings.append({"status": "untested", "code": "reference_unavailable"})
            elif not (means[subject] > means[reference]).all():
                findings.append({"status": "failed", "code": "mean_comparison_false"})
        if spec.get("uncertainty") and frame.groupby([group, x])[y].count().min() < 2:
            findings.append({"status": "untested", "code": "interval_unavailable"})
    figure, axes = plt.subplots(figsize=(5, 3))
    try:
        for model in means:
            axes.plot(means.index, means[model], label=model)
        axes.set(xlabel=spec["x"]["label"], ylabel=spec["y"]["label"])
        axes.legend()
        figure.tight_layout()
        figure.savefig(destination, metadata={"Software": "research baseline"})
    finally:
        plt.close(figure)
    status = (
        "failed"
        if any(f["status"] == "failed" for f in findings)
        else "incomplete"
        if findings
        else "passed"
    )
    return {
        "status": status,
        "exit_code": 0 if status == "passed" else 2,
        "findings": findings,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("spec", type=Path)
    parser.add_argument("--assertions", action="store_true")
    args = parser.parse_args()
    try:
        report = run(
            json.loads(args.spec.read_text()),
            Path("figure.png"),
            validate=args.assertions,
        )
    except (OSError, ValueError, KeyError) as problem:
        report = {"status": "execution_error", "exit_code": 1, "error": str(problem)}
    print(json.dumps(report))
    raise SystemExit(report["exit_code"])
