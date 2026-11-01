"""Source-preserving public inputs and an independent decimal descriptive oracle.

These are benchmark fixtures, not new observations or reproduction of the papers'
inferential models. Performance measurements are deliberately absent here.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import math
from collections import defaultdict
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
FIGURES = ("penguins-mass", "iris-measurements", "penguins-scatter", "iris-scatter")
FORMATS = ["png", "svg", "pdf"]


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    ).encode("utf8")


def csv_bytes(rows, fields):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf8")


def records(path):
    with Path(path).open(encoding="utf8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader), reader.fieldnames


def views():
    penguins, fields = records(ROOT / "benchmarks/papers/sources/penguins.csv")
    filtered = [r for r in penguins if r["sex"] in ("female", "male")]
    assert len(penguins) == 344 and len(filtered) == 333
    singleton = {}
    for row in filtered:
        if row["body_mass_g"] != "NA":
            singleton.setdefault((row["species"], row["sex"]), row)
    assert len(singleton) == 6
    iris, iris_fields = records(ROOT / "examples/published-papers/data/iris.csv")
    assert len(iris) == 150
    millimetres = []
    for row in iris:
        changed = {
            name + "_mm": str(Decimal(row[name]) * 10)
            for name in iris_fields
            if name != "species"
        }
        changed["species"] = row["species"]
        millimetres.append(changed)
    return {
        "penguins-sex-complete.csv": csv_bytes(filtered, fields),
        "penguins-singleton-sd.csv": csv_bytes(list(singleton.values()), fields),
        "iris-mm.csv": csv_bytes(
            millimetres,
            [name + "_mm" if name != "species" else name for name in iris_fields],
        ),
    }


def observations(spec, base):
    rows, _ = records(base / spec["data"]["path"])
    result = []
    for row in rows:
        if any(row[f["field"]] not in f["value"] for f in spec.get("filter", [])):
            continue
        try:
            y = Decimal(row[spec["y"]["field"]])
            x = (
                Decimal(row[spec["x"]["field"]])
                if spec["kind"] == "scatter"
                else row[spec["x"]["field"]]
            )
        except InvalidOperation:
            continue
        if not y.is_finite() or isinstance(x, Decimal) and not x.is_finite():
            continue
        result.append((x, row[spec["group"]], y))
    return result


def oracle(spec, base):
    rows = observations(spec, base)
    status = "passed"
    if spec["kind"] == "scatter":
        artists = sorted(
            [{"x": float(x), "group": group, "y": float(y)} for x, group, y in rows],
            key=lambda r: (r["group"], r["x"], r["y"]),
        )
    else:
        grouped = defaultdict(list)
        for x, group, y in rows:
            grouped[x, group].append(y)
        artists = []
        with localcontext() as context:
            context.prec = 50
            for (x, group), values in sorted(grouped.items()):
                mean = sum(values) / len(values)
                sd = (
                    (sum((v - mean) ** 2 for v in values) / (len(values) - 1)).sqrt()
                    if len(values) > 1
                    else None
                )
                artists.append(
                    {
                        "x": x,
                        "group": group,
                        "n": len(values),
                        "mean": float(mean),
                        "low": float(mean - sd) if sd is not None else None,
                        "high": float(mean + sd) if sd is not None else None,
                    }
                )
        for claim in spec.get("claims", []):
            mine = {
                r["x"]: r["mean"] for r in artists if r["group"] == claim["subject"]
            }
            theirs = {
                r["x"]: r["mean"] for r in artists if r["group"] == claim["reference"]
            }
            if not mine or mine.keys() != theirs.keys():
                if status != "failed":
                    status = "incomplete"
            elif any(mine[x] <= theirs[x] for x in mine):
                status = "failed"
        if (
            status != "failed"
            and spec.get("uncertainty")
            and any(r["n"] < 2 for r in artists)
        ):
            status = "incomplete"
    return {
        "status": status,
        "exit_code": 0 if status == "passed" else 2,
        "retained_observations": len(rows),
        "artists": artists,
    }


def requests(spec, base):
    """The fixed one-cold/seven-warm sequence; no timing or outcome-dependent choice."""
    current = copy.deepcopy(spec)
    result = [("first", copy.deepcopy(current))]
    current["title"] += " — review"
    result.append(("title", copy.deepcopy(current)))
    current["y"]["label"] += " — descriptive"
    result.append(("y-label", copy.deepcopy(current)))
    current["output"].update(size="single_column", dpi=600, formats=FORMATS[:])
    result.append(("single-column", copy.deepcopy(current)))
    current["output"].update(
        size="single_column", dpi=144, formats=["png"], interactive=False, latex=False
    )
    result.append(("review-png", copy.deepcopy(current)))
    current["output"].update(size="double_column", dpi=600, formats=FORMATS[:])
    result.append(("paper-double", copy.deepcopy(current)))
    field = current["x"]["field"] if current["kind"] == "bar" else current["group"]
    raw, _ = records(base / current["data"]["path"])
    candidates = sorted({r[field] for r in raw})
    current.setdefault("filter", []).append(
        {"field": field, "op": "in", "value": [candidates[0]]}
    )
    result.append(("filter", copy.deepcopy(current)))
    result.append(("restore", copy.deepcopy(spec)))
    return result


def independent_check(spec, base, expected, reference):
    """Compare decimal truth to the earlier separately written csv/statistics path."""
    rows = reference["observations"](spec, base)
    if spec["kind"] == "bar":
        actual = reference["summaries"](rows)
    else:
        actual = sorted(
            [{"x": x, "group": group, "y": y} for x, group, y in rows],
            key=lambda r: (r["group"], r["x"], r["y"]),
        )
    assert (
        len(actual) == len(expected["artists"])
        and len(rows) == expected["retained_observations"]
    )
    for left, right in zip(actual, expected["artists"], strict=True):
        assert left.keys() == right.keys()
        for key in left:
            if isinstance(left[key], float):
                assert math.isclose(left[key], right[key], rel_tol=1e-10, abs_tol=1e-10)
            else:
                assert left[key] == right[key]
