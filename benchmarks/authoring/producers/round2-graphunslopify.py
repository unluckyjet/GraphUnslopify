"""Fresh fourth episode: compile complete-data mean/SD and label its summary position."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from graphunslopify import Figure

ROOT = Path(__file__).resolve().parents[3]


def main():
    rules = json.loads((ROOT / "benchmarks/certified/protocol.json").read_text())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, choices=rules["dataset_order"])
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--variant", required=True, choices=rules["variants"])
    options = parser.parse_args()
    request = {
        "kind": "line",
        "title": rules["title_template"].format(id=options.dataset),
        "data": {"path": str(options.data.resolve())},
        "x": {"field": "plot_position", "label": rules["x_label"]},
        "y": {"field": "value", "label": rules["y_labels"][options.dataset]},
        "aggregation": "mean",
        "marker": True,
        "legend": {"show": False},
        "output": {
            "stem": "figure",
            "formats": rules["formats"],
            "dpi": rules["dpi"],
            "size": "single_column",
        },
    }
    if options.variant == "mean_sd":
        request["uncertainty"] = {"kind": "std", "display": "bar"}
    options.out_dir.mkdir(parents=True, exist_ok=True)
    result = Figure(request).translate(api="local")
    for name, data in {
        "spec.json": request,
        "translation.json": {
            "status": result["status"],
            "findings": result.get("findings", []),
        },
    }.items():
        with (options.out_dir / name).open("x", encoding="utf8") as stream:
            stream.write(json.dumps(data, indent=2, allow_nan=False) + "\n")
    if any(item.get("severity") == "error" for item in result.get("findings", [])):
        raise ValueError("Static translation rejected this request")
    original = result["code"]
    boundary = '\nif __name__ == "__main__":\n'
    prefix, found, entry = original.rpartition(boundary)
    if not found:
        raise ValueError(
            "Generated entrypoint is unavailable for a presentation adapter"
        )
    presentation = f"""
# Add a plotting coordinate only; keep every source row/value and generated statistic.
_source_loader = load
def load():
    observations = _source_loader()
    observations["plot_position"] = 0.0
    return observations

_summary_renderer = draw_panel
def draw_panel(axis, observations):
    _summary_renderer(axis, observations)
    axis.set_xticks([0], [{options.dataset!r}])

"""
    for name, code in {
        "translated.py": original,
        "figure.py": prefix + presentation + boundary + entry,
    }.items():
        with (options.out_dir / name).open("x", encoding="utf8") as stream:
            stream.write(code)


if __name__ == "__main__":
    main()
