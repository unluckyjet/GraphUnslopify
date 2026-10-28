"""Create headered/long Iris views from the pinned corrected UCI source, offline."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def prepare() -> None:
    sources = ROOT / "benchmarks/papers/sources"
    metadata = json.loads((sources.parent / "sources.json").read_text())
    for source in metadata["sources"]:
        path = sources / source["file"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError(f"source hash mismatch: {path.name}")
        if source["id"] == "penguins":
            counts = Counter(
                row["species"] for row in csv.DictReader(path.read_text().splitlines())
            )
        else:
            counts = Counter(
                row[-1] for row in csv.reader(path.read_text().splitlines()) if row
            )
        if counts != source["published_counts"]:
            raise ValueError(f"published class counts differ: {path.name}")
        if "comparison_file" in source:
            path = sources / source["comparison_file"]
            if (
                hashlib.sha256(path.read_bytes()).hexdigest()
                != source["comparison_sha256"]
            ):
                raise ValueError(f"comparison source hash mismatch: {path.name}")
    folder = ROOT / "examples/published-papers/data"
    folder.mkdir(exist_ok=True)
    measurements = ["sepal_length", "sepal_width", "petal_length", "petal_width"]
    wide, long = io.StringIO(newline=""), io.StringIO(newline="")
    writer, melted = (
        csv.writer(wide, lineterminator="\n"),
        csv.writer(long, lineterminator="\n"),
    )
    writer.writerow([*measurements, "species"])
    melted.writerow(["measurement", "value", "species"])
    for row in csv.reader((sources / "bezdekIris.data").read_text().splitlines()):
        if not row:
            continue
        writer.writerow(row)
        for name, value in zip(measurements, row[:4], strict=True):
            melted.writerow([name.replace("_", " "), value, row[4]])
    for name, content in (
        ("iris.csv", wide.getvalue()),
        ("iris-long.csv", long.getvalue()),
    ):
        path = folder / name
        # Derived committed views are deterministic. Refuse to silently replace an edited view.
        if path.exists() and path.read_text() != content:
            raise ValueError(
                f"derived view differs: {path}; inspect/remove it explicitly to rebuild"
            )
        path.write_text(content, encoding="utf8")


if __name__ == "__main__":
    prepare()
