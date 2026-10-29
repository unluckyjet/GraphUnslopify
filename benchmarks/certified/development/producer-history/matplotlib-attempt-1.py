"""Build a conventional reusable CSV/statistics/Matplotlib summary program."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROGRAM = '''"""Complete-data mean and descriptive sample SD; external validation is separate."""
import csv
import json
import statistics
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

config = json.loads(Path(__file__).with_name("spec.json").read_text())
with open(config["data"], newline="", encoding="utf8") as handle:
    values = [float(row["value"]) for row in csv.DictReader(handle)]
mean = statistics.mean(values)
sd = statistics.stdev(values)
plt.rcParams.update({"font.size": 9, "pdf.fonttype": 42,
                     "svg.fonttype": "none", "text.parse_math": False})
figure, axis = plt.subplots(figsize=config["size_inches"])
axis.errorbar([config["dataset"]], [mean],
              yerr=[sd] if config["variant"] == "mean_sd" else None,
              fmt="o", capsize=3)
axis.set(title=config["title"], xlabel=config["x_label"], ylabel=config["y_label"])
figure.tight_layout()
for fmt in config["formats"]:
    figure.savefig("figure."+fmt, bbox_inches="tight",
                   **({"dpi": config["dpi"]} if fmt == "png" else {}))
plt.close(figure)
'''


def main():
    protocol = json.loads((ROOT / "benchmarks/certified/protocol.json").read_text())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=protocol["dataset_order"], required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--variant", choices=protocol["variants"], required=True)
    args = parser.parse_args()
    config = {
        "workflow": "Conventional Matplotlib with external frozen evaluator",
        "data": str(args.data.resolve()),
        "dataset": args.dataset,
        "variant": args.variant,
        "title": protocol["title_template"].format(id=args.dataset),
        "x_label": protocol["x_label"],
        "y_label": protocol["y_labels"][args.dataset],
        "size_inches": [protocol["width_in"], protocol["height_in"]],
        "dpi": protocol["dpi"],
        "formats": protocol["formats"],
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    with (args.out_dir / "spec.json").open("x", encoding="utf8") as handle:
        json.dump(config, handle, indent=2, allow_nan=False)
        handle.write("\n")
    with (args.out_dir / "figure.py").open("x", encoding="utf8") as handle:
        handle.write(PROGRAM)


if __name__ == "__main__":
    main()
