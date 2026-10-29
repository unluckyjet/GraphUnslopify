"""Compile complete-data mean/sample-SD specifications with the real local translator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from graphunslopify import Figure

ROOT = Path(__file__).resolve().parents[3]


def main():
    protocol = json.loads((ROOT / "benchmarks/certified/protocol.json").read_text())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=protocol["dataset_order"], required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--variant", choices=protocol["variants"], required=True)
    args = parser.parse_args()
    spec = {
        "kind": "line",
        "data": {"path": str(args.data.resolve())},
        "x": {"field": "dataset", "label": protocol["x_label"]},
        "y": {"field": "value", "label": protocol["y_labels"][args.dataset]},
        "title": protocol["title_template"].format(id=args.dataset),
        "aggregation": "mean",
        "marker": True,
        "legend": {"show": False},
        "output": {
            "stem": "figure",
            "formats": protocol["formats"],
            "size": "single_column",
            "dpi": protocol["dpi"],
        },
    }
    if args.variant == "mean_sd":
        spec["uncertainty"] = {"kind": "std", "display": "bar"}
    args.out_dir.mkdir(parents=True, exist_ok=True)
    with (args.out_dir / "spec.json").open("x", encoding="utf8") as handle:
        json.dump(spec, handle, indent=2, allow_nan=False)
        handle.write("\n")
    result = Figure(spec).translate(api="local")
    with (args.out_dir / "translation.json").open("x", encoding="utf8") as handle:
        json.dump(
            {"status": result["status"], "findings": result.get("findings", [])},
            handle,
            indent=2,
            allow_nan=False,
        )
        handle.write("\n")
    if any(f.get("severity") == "error" for f in result.get("findings", [])):
        raise ValueError(
            "Strict translation rejected static errors; inspect translation.json"
        )
    with (args.out_dir / "figure.py").open("x", encoding="utf8") as handle:
        handle.write(result["code"])


if __name__ == "__main__":
    main()
