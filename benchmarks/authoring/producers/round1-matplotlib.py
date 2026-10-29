"""Episode2: reusable standard-library statistics and Matplotlib plotting program."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

PLOT_PROGRAM = """import csv
import json
import statistics
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

def main():
    settings = json.loads(Path(__file__).with_name("spec.json").read_text())
    with open(settings["data"], newline="", encoding="utf8") as stream:
        measurements = [float(record["value"]) for record in csv.DictReader(stream)]
    center = statistics.mean(measurements)
    interval = [statistics.stdev(measurements)] if settings["variant"] == "mean_sd" else None
    plt.rcParams.update({"font.size": 9, "pdf.fonttype": 42,
                         "svg.fonttype": "none", "text.parse_math": False})
    figure, axis = plt.subplots(figsize=settings["size_inches"])
    axis.errorbar([0.0], [center], yerr=interval, fmt="o", capsize=3)
    axis.set_xticks([0.0], labels=[settings["dataset"]])
    axis.set_title(settings["title"])
    axis.set_xlabel(settings["x_label"])
    axis.set_ylabel(settings["y_label"])
    figure.tight_layout()
    for extension in settings["formats"]:
        figure.savefig("figure." + extension, bbox_inches="tight", dpi=settings["dpi"])
    plt.close(figure)

if __name__ == "__main__":
    main()
"""


def main():
    metadata = json.loads((ROOT / "benchmarks/certified/protocol.json").read_text())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, choices=metadata["dataset_order"])
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--variant", required=True, choices=metadata["variants"])
    options = parser.parse_args()
    payload = {
        "dataset": options.dataset,
        "data": str(options.data.resolve()),
        "variant": options.variant,
        "title": metadata["title_template"].format(id=options.dataset),
        "x_label": metadata["x_label"],
        "y_label": metadata["y_labels"][options.dataset],
        "size_inches": [metadata["width_in"], metadata["height_in"]],
        "dpi": metadata["dpi"],
        "formats": metadata["formats"],
    }
    options.out_dir.mkdir(parents=True, exist_ok=True)
    for filename, contents in {
        "spec.json": json.dumps(payload, indent=2, allow_nan=False) + "\n",
        "figure.py": PLOT_PROGRAM,
    }.items():
        with (options.out_dir / filename).open("x", encoding="utf8") as stream:
            stream.write(contents)


if __name__ == "__main__":
    main()
