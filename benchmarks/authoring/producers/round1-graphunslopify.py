"""Episode1: local semantic mean/SD generation with an explicit position adapter."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from graphunslopify import Figure

ROOT = Path(__file__).resolve().parents[3]


def labelled_position(program, dataset):
    head, separator, tail = program.rpartition('\nif __name__ == "__main__":\n')
    if not separator:
        raise ValueError("Cannot locate the generated entrypoint")
    hooks = f"""
# Presentation-only coordinate; original observations and generated estimators stay intact.
_read_original = load
def load():
    return _read_original().assign(summary_x=0.0)

_plot_original = draw_panel
def draw_panel(axis, frame):
    _plot_original(axis, frame)
    axis.set_xticks([0.0], labels=[{dataset!r}])

"""
    return head + hooks + separator + tail


def main():
    protocol = json.loads((ROOT / "benchmarks/certified/protocol.json").read_text())
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--dataset", required=True, choices=protocol["dataset_order"])
    cli.add_argument("--data", required=True, type=Path)
    cli.add_argument("--out-dir", required=True, type=Path)
    cli.add_argument("--variant", required=True, choices=protocol["variants"])
    args = cli.parse_args()
    spec = {
        "kind": "line",
        "data": {"path": str(args.data.resolve())},
        "x": {"field": "summary_x", "label": protocol["x_label"]},
        "y": {"field": "value", "label": protocol["y_labels"][args.dataset]},
        "aggregation": "mean",
        "title": protocol["title_template"].format(id=args.dataset),
        "marker": True,
        "legend": {"show": False},
        "output": {
            "stem": "figure",
            "formats": protocol["formats"],
            "dpi": protocol["dpi"],
            "size": "single_column",
        },
    }
    if args.variant == "mean_sd":
        spec["uncertainty"] = {"kind": "std", "display": "bar"}
    args.out_dir.mkdir(parents=True, exist_ok=True)
    with (args.out_dir / "spec.json").open("x", encoding="utf8") as handle:
        json.dump(spec, handle, indent=2, allow_nan=False)
        handle.write("\n")
    translated = Figure(spec).translate(api="local")
    with (args.out_dir / "translation.json").open("x", encoding="utf8") as handle:
        json.dump(
            {
                "status": translated["status"],
                "findings": translated.get("findings", []),
            },
            handle,
            indent=2,
            allow_nan=False,
        )
        handle.write("\n")
    if any(f.get("severity") == "error" for f in translated.get("findings", [])):
        raise ValueError("Translation contains errors; inspect translation.json")
    with (args.out_dir / "translated.py").open("x", encoding="utf8") as handle:
        handle.write(translated["code"])
    with (args.out_dir / "figure.py").open("x", encoding="utf8") as handle:
        handle.write(labelled_position(translated["code"], args.dataset))


if __name__ == "__main__":
    main()
