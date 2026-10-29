"""Profiling a data file so a spec can be written against what is actually there.

An agent writing a spec without this is guessing at column names, at whether a
column is a number or a label, at how many categories there are, and at whether
x repeats per series. Every one of those guesses is a spec that fails or, worse,
a figure that renders and is wrong.

Output is JSON so it can be read straight back into a spec.
"""

from __future__ import annotations

import json
import math
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .workbook import EXCEL_SUFFIXES, read_excel_table

MAX_LISTED_CATEGORIES = 25
CATEGORICAL_CEILING = 50
MAX_REPEAT_CANDIDATES = 16


def _finite_mask(series: Any) -> Any:
    import numpy as np

    return np.isfinite(series.to_numpy(dtype=float))


def _json_scalar(value: Any) -> Any:
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value if value is None or isinstance(value, (str, int, float, bool)) else str(value)


def _read(path: Path, sheet: str | None = None) -> Any:
    import pandas as pd

    suffix = path.suffix.lower()
    if suffix in EXCEL_SUFFIXES:
        return read_excel_table(path, sheet=sheet)
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix in {".json", ".jsonl"}:
        return pd.read_json(path, lines=suffix == ".jsonl")
    return pd.read_csv(path)


def _looks_like_an_index(series: Any) -> bool:
    """An epoch or a seed is a complete run of integers starting at 0 or 1.

    Measured integers are not. An accuracy column of whole percentages runs from
    something like 52 to 72, so requiring the run to start at 0 or 1 separates
    the axis a curve travels along from the quantity being measured.
    """
    values = series.dropna()
    if values.empty or not _finite_mask(values).all() or not (values % 1 == 0).all():
        return False
    low, high = int(values.min()), int(values.max())
    if low not in (0, 1):
        return False
    return values.nunique() == high - low + 1


def _role(series: Any, rows: int) -> str:
    """A guess at what the column is for, which is what a spec needs to know."""
    import pandas as pd

    distinct = series.nunique(dropna=True)
    if pd.api.types.is_numeric_dtype(series):
        if pd.api.types.is_complex_dtype(series):
            raise ValueError("Complex-valued columns need an explicit real-valued interpretation")
        if not _finite_mask(series.dropna()).all():
            return "measure"
        if distinct <= 2:
            return "flag"
        if distinct <= CATEGORICAL_CEILING and _looks_like_an_index(series):
            return "ordinal"
        return "measure"
    if distinct <= CATEGORICAL_CEILING:
        return "category"
    return "identifier"


def profile(path: str | Path, *, sheet: str | None = None) -> dict[str, Any]:
    import numpy as np
    import pandas as pd

    path = Path(path)
    if not path.exists():
        return {"ok": False, "error": f"no such file: {path}"}

    if sheet is not None and path.suffix.lower() not in EXCEL_SUFFIXES:
        return {"ok": False, "error": "Worksheet selection applies only to Excel input"}
    try:
        frame = _read(path, sheet)
    except ValueError as error:
        if path.suffix.lower() not in EXCEL_SUFFIXES:
            raise
        return {
            "ok": False,
            "path": str(path),
            "error": str(error),
            "sheets": getattr(error, "sheets", []),
        }
    rows = len(frame)
    columns: list[dict[str, Any]] = []

    for name in frame.columns:
        series = frame[name]
        entry: dict[str, Any] = {
            "name": str(name),
            "dtype": str(series.dtype),
            "role": _role(series, rows),
            "distinct": int(series.nunique(dropna=True)),
            "missing": int(series.isna().sum()),
            "non_missing": int(series.notna().sum()),
            "role_inference": "heuristic",
        }
        if pd.api.types.is_numeric_dtype(series):
            values = series.dropna()
            finite = values[_finite_mask(values)]
            entry["finite"] = len(finite)
            entry["nonfinite"] = len(values) - len(finite)
            entry["numeric_summary_scope"] = "finite values only"
            if len(finite):
                entry["min"] = _json_scalar(float(finite.min()))
                entry["max"] = _json_scalar(float(finite.max()))
                with np.errstate(over="ignore", invalid="ignore"):
                    numeric = finite.to_numpy(dtype=float)
                    mean = float(np.mean(numeric))
                    if not math.isfinite(mean):
                        mean = float(np.sum(numeric / len(finite)))
                    entry["mean"] = _json_scalar(mean)
        if (
            entry["role"] in {"category", "flag", "ordinal"}
            and entry["distinct"] <= MAX_LISTED_CATEGORIES
        ):
            entry["values"] = [_json_scalar(v) for v in series.dropna().unique().tolist()]
        columns.append(entry)

    measures = [c["name"] for c in columns if c["role"] == "measure" and c.get("finite", 0)]
    categories = [c["name"] for c in columns if c["role"] == "category"]
    # The ordinal a curve runs along has many steps. A replicate index has few,
    # so ranking by distinct count picks epoch over seed.
    ordinals = [
        c["name"] for c in sorted(columns, key=lambda c: -c["distinct"]) if c["role"] == "ordinal"
    ]

    report: dict[str, Any] = {
        "ok": True,
        "path": str(path),
        "rows": rows,
        "columns": columns,
        "column_names": [c["name"] for c in columns],
    }

    # Whether x repeats per series decides whether aggregation is needed, and it
    # is the single thing a spec most often gets wrong.
    repeats: list[dict[str, Any]] = []
    x_candidates = (ordinals + categories)[:MAX_REPEAT_CANDIDATES]
    group_candidates = categories[:MAX_REPEAT_CANDIDATES]
    for x_name in x_candidates:
        for group in group_candidates:
            if group == x_name:
                continue
            duplicated = int(frame.duplicated(subset=[x_name, group]).sum())
            if duplicated:
                repeats.append({"x": x_name, "group": group, "repeated_rows": duplicated})
    report["repeats"] = repeats[:10]
    report["repeat_scan"] = {
        "x_columns_checked": len(x_candidates),
        "group_columns_checked": len(group_candidates),
        "truncated": len(x_candidates) < len(ordinals + categories)
        or len(group_candidates) < len(categories)
        or len(repeats) > 10,
    }
    report["inference_note"] = (
        "Column roles and figure suggestions are heuristics. Row/non-missing counts are not "
        "independent experimental sample counts; review units and uncertainty before rendering."
    )

    hint: dict[str, Any] = {}
    if ordinals and measures:
        hint = {"kind": "line", "x": ordinals[0], "y": measures[0]}
    elif categories and measures:
        hint = {"kind": "bar", "x": categories[0], "y": measures[0]}
    elif len(measures) >= 2:
        hint = {"kind": "scatter", "x": measures[0], "y": measures[1]}
    if categories and hint:
        candidates = [c for c in categories if c != hint.get("x")]
        if candidates:
            hint["group"] = candidates[0]
    matching = [r for r in repeats if r["x"] == hint.get("x") and r["group"] == hint.get("group")]
    if hint and matching:
        hint["aggregation"] = "mean"
        replicate = [
            c["name"]
            for c in columns
            if c["role"] == "ordinal" and c["name"] not in {hint.get("x"), hint.get("y")}
        ]
        hint["uncertainty"] = {"kind": "ci", "over": replicate[0]} if replicate else {"kind": "std"}
        hint["note"] = (
            f"{matching[0]['repeated_rows']} rows repeat on "
            f"({hint['x']}, {hint['group']}), so aggregation is needed"
        )
    report["suggested"] = hint
    if path.suffix.lower() in EXCEL_SUFFIXES:
        report["format"] = "excel"
        report["sheet"] = frame.attrs["_graphunslopify_excel_sheet"]
        report["reader_note"] = (
            "Excel stored/cached cell values; formulas and macros are not executed."
        )

    return report


def render(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, default=str, allow_nan=False)
