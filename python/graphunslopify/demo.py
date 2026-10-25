"""Public synthetic data for an offline installation check."""

from __future__ import annotations

import json
from pathlib import Path

from .errors import SpecError


def write_demo(directory: str | Path) -> Path:
    where = Path(directory)
    where.mkdir(parents=True, exist_ok=True)
    rows = ["epoch,score,model,seed"]
    for epoch in range(1, 4):
        for model, gain in (("base", 0), ("ours", 2)):
            for seed in range(4):
                rows.append(f"{epoch},{50 + epoch + seed + gain},{model},{seed}")
    spec = {
        "kind": "line",
        "data": {"path": "results.csv"},
        "x": {"field": "epoch", "label": "Epoch"},
        "y": {"field": "score", "label": "Score"},
        "group": "model",
        "series_order": ["base", "ours"],
        "aggregation": "mean",
        "uncertainty": {"kind": "ci", "over": "seed", "display": "band"},
        "legend": {"position": "outside_bottom"},
        "claims": [{"kind": "beats_everywhere", "subject": "ours", "reference": "base"}],
        "output": {"stem": "figure", "formats": ["png", "svg", "pdf"]},
    }
    for name, text in (
        ("results.csv", "\n".join(rows) + "\n"),
        ("figure.json", json.dumps(spec, indent=2) + "\n"),
    ):
        destination = where / name
        if destination.exists() and destination.read_text(encoding="utf8") != text:
            raise SpecError(f"demo would overwrite {destination}; choose another directory")
        destination.write_text(text, encoding="utf8")
    return where / "figure.json"
