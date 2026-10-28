"""Separate stdlib numerical reference and ordinary Matplotlib comparison.

No GraphUnslopify or pandas imports. These are author-written descriptive
calculations on published data, not independent researcher validation.
"""

from __future__ import annotations

import csv
import math
import statistics
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.container import BarContainer, ErrorbarContainer


def observations(spec: dict, base: Path) -> list[tuple]:
    rows = []
    with (base / spec["data"]["path"]).open(newline="", encoding="utf8") as handle:
        for row in csv.DictReader(handle):
            if any(
                row[rule["field"]] not in rule["value"]
                for rule in spec.get("filter", [])
            ):
                continue
            group = row[spec["group"]]
            try:
                x = row[spec["x"]["field"]]
                if spec["kind"] == "scatter":
                    x = float(x)
                y = float(row[spec["y"]["field"]])
            except ValueError:
                continue
            if math.isfinite(y) and (not isinstance(x, float) or math.isfinite(x)):
                rows.append((x, group, y))
    return rows


def summaries(rows: list[tuple]) -> list[dict]:
    grouped = defaultdict(list)
    for x, group, y in rows:
        grouped[x, group].append(y)
    result = []
    for (x, group), values in sorted(grouped.items()):
        mean = statistics.mean(values)
        sd = statistics.stdev(values) if len(values) > 1 else None
        result.append(
            {
                "x": x,
                "group": group,
                "n": len(values),
                "mean": mean,
                "low": mean - sd if sd is not None else None,
                "high": mean + sd if sd is not None else None,
            }
        )
    return result


def verdict(spec: dict, summary: list[dict]) -> str:
    status = "passed"
    for claim in spec.get("claims", []):
        mine = {
            row["x"]: row["mean"] for row in summary if row["group"] == claim["subject"]
        }
        theirs = {
            row["x"]: row["mean"]
            for row in summary
            if row["group"] == claim["reference"]
        }
        if not mine or mine.keys() != theirs.keys():
            if status != "failed":
                status = "incomplete"
        elif any(mine[x] <= theirs[x] for x in mine):
            status = "failed"
    if (
        spec.get("uncertainty")
        and any(row["n"] < 2 for row in summary)
        and status != "failed"
    ):
        status = "incomplete"
    return status


def artists(axes, categories: list) -> list[dict]:
    """Measure actual containers, including category/group identity and SD endpoints."""
    intervals = {}
    for container in axes.containers:
        if isinstance(container, ErrorbarContainer):
            for collection in container.lines[2]:
                for segment in collection.get_segments():
                    if len(segment) == 2 and all(
                        math.isfinite(float(v)) for v in segment.flat
                    ):
                        intervals[round(float(segment[0, 0]), 10)] = [
                            float(segment[0, 1]),
                            float(segment[1, 1]),
                        ]
    result = []
    for container in axes.containers:
        if not isinstance(container, BarContainer):
            continue
        for bar in container.patches:
            centre = bar.get_x() + bar.get_width() / 2
            bounds = intervals.get(round(centre, 10), [None, None])
            result.append(
                {
                    "x": categories[round(centre)],
                    "group": container.get_label(),
                    "mean": float(bar.get_height()),
                    "low": bounds[0],
                    "high": bounds[1],
                }
            )
    return sorted(result, key=lambda row: (row["x"], row["group"]))


def scatter_artists(axes) -> list[dict]:
    result = []
    for collection in axes.collections:
        for x, y in collection.get_offsets():
            # Matplotlib retains masked source rows in offsets but draws no point.
            if getattr(x, "mask", False) or getattr(y, "mask", False):
                continue
            if math.isfinite(float(x)) and math.isfinite(float(y)):
                result.append(
                    {"x": float(x), "y": float(y), "group": collection.get_label()}
                )
    return sorted(result, key=lambda row: (row["group"], row["x"], row["y"]))


def baseline(spec: dict, base: Path, output: Path) -> dict:
    rows = observations(spec, base)
    summary = summaries(rows) if spec["kind"] == "bar" else []
    figure, axes = plt.subplots(figsize=(7.4, 3.8))
    try:
        groups = spec.get("series_order") or sorted({row[1] for row in rows})
        if spec["kind"] == "bar":
            categories = list(dict.fromkeys(row[0] for row in rows))
            for index, group in enumerate(groups):
                values = [
                    {row["x"]: row for row in summary if row["group"] == group}[x]
                    for x in categories
                ]
                width = 0.8 / len(groups)
                positions = [
                    i + (index - (len(groups) - 1) / 2) * width
                    for i in range(len(categories))
                ]
                spread = [
                    v["high"] - v["mean"] if v["high"] is not None else float("nan")
                    for v in values
                ]
                axes.bar(
                    positions,
                    [v["mean"] for v in values],
                    width,
                    label=group,
                    yerr=spread if any(math.isfinite(v) for v in spread) else None,
                )
            axes.set_xticks(range(len(categories)), categories)
            measured = artists(axes, categories)
        else:
            for group in groups:
                points = [row for row in rows if row[1] == group]
                axes.scatter(
                    [p[0] for p in points], [p[2] for p in points], label=group, s=10
                )
            measured = scatter_artists(axes)
        axes.set(
            xlabel=spec["x"]["label"],
            ylabel=spec["y"]["label"],
            title=spec.get("title"),
        )
        axes.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=len(groups))
        figure.tight_layout()
        figure.savefig(output, dpi=150)
    finally:
        plt.close(figure)
    status = verdict(spec, summary)
    return {
        "status": status,
        "exit_code": 0 if status == "passed" else 2,
        "rows": len(rows),
        "reference": summary,
        "artists": measured,
    }
