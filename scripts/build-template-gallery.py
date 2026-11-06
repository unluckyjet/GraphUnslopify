"""Build the packaged starter catalog and strict-rendered sample previews."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from graphunslopify import Figure
from graphunslopify.figure_templates import create_template
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]

STARTERS = [
    (
        "01-training-curve",
        "trend",
        "Change over time",
        "Training curves",
        ("Step", "Outcome"),
        "Compare methods over ordered steps. Repeated measurements at a step use their mean.",
        "Line chart showing test accuracy rising over training for four models.",
    ),
    (
        "05-latency-ranking",
        "comparison",
        "Compare categories",
        "Horizontal category comparison",
        ("Category", "Outcome"),
        "Use horizontal labels for long category names. Each bar shows the category mean.",
        "Horizontal bars comparing the mean inference latency of four models.",
    ),
    (
        "06-accuracy-vs-latency",
        "relationship",
        "Explore a relationship",
        "Grouped scatter",
        ("First measurement", "Second measurement"),
        "Compare two measurements per observation and mark the groups. Individual points are retained.",
        "Scatter plot comparing test accuracy and inference latency, marked by model.",
    ),
    (
        "11-seed-spread",
        "distribution",
        "Inspect distributions",
        "Box distributions",
        ("Group", "Outcome"),
        "Compare medians, spread and outliers across groups. Individual points are summarized in boxes.",
        "Box plots showing the distribution of test accuracy across epochs for each model.",
    ),
    (
        "12-sweep-heatmap",
        "parameter-grid",
        "Compare a parameter grid",
        "Parameter sweep heatmap",
        ("First setting", "Second setting"),
        "Compare a measured response across two settings. Each populated cell shows its mean.",
        "Annotated heatmap showing validation accuracy for learning rates and batch sizes.",
    ),
]


def main():
    examples = ROOT / "examples"
    web = ROOT / "python/graphunslopify/web"
    catalog = []
    with TemporaryDirectory(prefix="gu-template-gallery-build-") as raw:
        output = Path(raw)
        for example, key, use_case, title, labels, description, alt in STARTERS:
            spec = json.loads(
                (examples / "specs" / f"{example}.json").read_text(encoding="utf8")
            )
            for field in ("series_order", "emphasis", "filter"):
                spec.pop(field, None)
            design = {**spec, "title": title}
            for axis, label in zip(("x", "y"), labels, strict=True):
                design[axis] = {**spec[axis], "label": label}
                design[axis].pop("unit", None)
            if "value_label" in design:
                design["value_label"] = "Response"
            catalog.append(
                {
                    "id": key,
                    "use_case": use_case,
                    "description": description,
                    "preview_alt": alt,
                    "template": create_template(design, title),
                }
            )
            sample = {
                **spec,
                "data": {**spec["data"], "path": str(examples / spec["data"]["path"])},
                "output": {**spec["output"], "stem": key, "formats": ["png"]},
            }
            result = Figure(sample).render(cwd=output)
            if result["report"]["status"] != "passed":
                raise RuntimeError(f"Template preview failed verification: {key}")
            with Image.open(output / f"{key}.png") as preview:
                preview.thumbnail((680, 500), Image.Resampling.LANCZOS)
                preview.save(output / f"template-{key}.png", optimize=True)
        for entry in catalog:
            name = f"template-{entry['id']}.png"
            (web / name).write_bytes((output / name).read_bytes())
    (web / "template-gallery.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf8"
    )


if __name__ == "__main__":
    main()
