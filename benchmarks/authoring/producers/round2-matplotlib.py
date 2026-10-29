"""Fresh reverse-pair implementation: CSV, sample statistics, and three exports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

DRAW = """import csv
import json
import statistics
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

config = json.loads(Path(__file__).with_name("spec.json").read_text())
with open(config["data"], encoding="utf8", newline="") as source:
    samples = [float(r["value"]) for r in csv.DictReader(source)]
average = statistics.mean(samples)
deviation = statistics.stdev(samples)
plt.rcParams.update({"font.size": 9, "text.parse_math": False,
                     "svg.fonttype": "none", "pdf.fonttype": 42})
fig, ax = plt.subplots(figsize=config["dimensions"])
ax.errorbar([0], [average], yerr=[deviation] if config["interval"] else None,
            fmt="o", capsize=3)
ax.set_xticks([0], [config["dataset"]])
ax.set(title=config["title"], xlabel=config["xlabel"], ylabel=config["ylabel"])
fig.tight_layout()
for extension in config["formats"]:
    fig.savefig("figure." + extension, dpi=config["dpi"], bbox_inches="tight")
plt.close(fig)
"""


def main():
    rules = json.loads((ROOT / "benchmarks/certified/protocol.json").read_text())
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--dataset", required=True, choices=rules["dataset_order"])
    cli.add_argument("--data", required=True, type=Path)
    cli.add_argument("--out-dir", required=True, type=Path)
    cli.add_argument("--variant", required=True, choices=rules["variants"])
    args = cli.parse_args()
    config = {
        "data": str(args.data.resolve()),
        "dataset": args.dataset,
        "interval": args.variant == "mean_sd",
        "title": rules["title_template"].format(id=args.dataset),
        "xlabel": rules["x_label"],
        "ylabel": rules["y_labels"][args.dataset],
        "dimensions": [rules["width_in"], rules["height_in"]],
        "dpi": rules["dpi"],
        "formats": rules["formats"],
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    with (args.out_dir / "spec.json").open("x", encoding="utf8") as output:
        output.write(json.dumps(config, indent=2, allow_nan=False) + "\n")
    with (args.out_dir / "figure.py").open("x", encoding="utf8") as output:
        output.write(DRAW)


if __name__ == "__main__":
    main()
