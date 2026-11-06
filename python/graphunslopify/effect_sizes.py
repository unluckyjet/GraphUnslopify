"""Compare mean differences with model-specific intervals and original CSV records."""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import math

MAX_EFFECT_CSV_BYTES = 2 * 1024 * 1024
MAX_EFFECT_REQUEST_BYTES = (MAX_EFFECT_CSV_BYTES + 2) // 3 * 4 + 16384
_MAX_ROWS = 10_000
_MODELS = {
    "paired": (
        "Cohen dz",
        "Matched independent units with normally distributed within-unit differences.",
    ),
    "pooled": ("Pooled Cohen d", "Independent normal groups with common variance."),
    "welch": ("Unpooled Cohen d", "Independent normal groups with potentially unequal variances."),
}


def _csv(raw):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_EFFECT_CSV_BYTES:
        raise ValueError("Choose a nonempty UTF-8 CSV of at most 2 MiB.")
    try:
        text = raw.decode("utf-8-sig")
        if "\x00" in text:
            raise ValueError("A CSV cannot contain NUL characters.")
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        columns = next(reader, [])
        if (
            not 1 <= len(columns) <= 128
            or len(set(columns)) != len(columns)
            or any(not field.strip() or len(field) > 200 for field in columns)
        ):
            raise ValueError("A CSV needs 1 to 128 distinct, nonempty column names.")
        rows = []
        for values in reader:
            if not values:
                continue
            if len(rows) == _MAX_ROWS or len(values) != len(columns):
                raise ValueError("A CSV needs at most 10,000 records and a consistent field count.")
            rows.append(values)
    except (UnicodeError, csv.Error) as problem:
        raise ValueError("Could not read the UTF-8 CSV snapshot.") from problem
    return (
        columns,
        rows,
        {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
            "records": len(rows),
            "record_coordinates": "One-based parsed data-record ordinals after the header, excluding empty lines.",
        },
    )


def _nct_interval(stats, optimize, t, df, level):
    if not math.isfinite(t) or abs(t) > 1e6:
        raise ValueError("The standardized interval is outside the numerical range.")
    # Use symmetry to avoid the negative-t CDF's unstable opposite tail.
    if t < 0:
        low, high = _nct_interval(stats, optimize, -t, df, level)
        return [-high, -low]
    tail = (1 - level) / 2
    width = max(2.0, t / 2)
    for _ in range(25):
        low, high = t - width, t + width
        if stats.nct.cdf(t, df, low) >= 1 - tail and stats.nct.cdf(t, df, high) <= tail:
            break
        width *= 2
    else:
        raise ValueError("Could not bracket the noncentral-t interval.")
    bounds = [
        optimize.brentq(
            lambda ncp, p=probability: stats.nct.cdf(t, df, ncp) - p, low, high, xtol=1e-10
        )
        for probability in (1 - tail, tail)
    ]
    if not all(math.isfinite(value) for value in bounds) or bounds[0] >= bounds[1]:
        raise ValueError("Could not verify the noncentral-t interval.")
    return bounds


def _mean_variance(values):
    mean = math.fsum(values) / len(values)
    return mean, math.fsum((value - mean) ** 2 for value in values) / (len(values) - 1)


def _normalized(left, right, paired):
    if paired:
        differences = [a - b for a, b in zip(left, right, strict=True)]
        if all(map(math.isfinite, differences)):
            scale = max(map(abs, differences)) or 1.0
            return [value / scale for value in differences], [], scale
    else:
        origin = right[0]
        a, b = [value - origin for value in left], [value - origin for value in right]
        if all(map(math.isfinite, a)) and all(map(math.isfinite, b)):
            scale = max(abs(value) for group in (a, b) for value in group) or 1.0
            return [value / scale for value in a], [value / scale for value in b], scale
    scale = max(abs(value) for group in (left, right) for value in group)
    a, b = [value / scale for value in left], [value / scale for value in right]
    if paired:
        return [x - y for x, y in zip(a, b, strict=True)], [], scale
    return a, b, scale


def _estimates(stats, optimize, left, right, design, level):
    a, b, scale = _normalized(left, right, design == "paired")
    mean, first = _mean_variance(a)
    if design == "paired":
        df = len(a) - 1
        standardizer = math.sqrt(first)
        se = standardizer / math.sqrt(len(a))
    else:
        second_mean, second = _mean_variance(b)
        mean -= second_mean
        if design == "pooled":
            df = len(a) + len(b) - 2
            standardizer = math.sqrt(((len(a) - 1) * first + (len(b) - 1) * second) / df)
            se = standardizer * math.sqrt(1 / len(a) + 1 / len(b))
        else:
            standardizer = math.sqrt((first + second) / 2)
            x, y = first / len(a), second / len(b)
            se = math.sqrt(x + y)
            if se:
                w, z = x / (x + y), y / (x + y)
                df = 1 / (w * w / (len(a) - 1) + z * z / (len(b) - 1))
            else:
                df = None
    value = mean * scale
    if not math.isfinite(value):
        raise ValueError("The mean difference cannot be represented in outcome units.")
    result = {
        "raw": {
            "label": "Mean difference",
            "estimate": value,
            "interval": None,
            "method": "Welch-Satterthwaite t" if design == "welch" else "Student t",
            "approximate": design == "welch",
        },
        "standardized": {
            "label": _MODELS[design][0],
            "estimate": None,
            "interval": None,
            "method": "Noncentral t inversion with an estimated Welch scale"
            if design == "welch"
            else "Noncentral t inversion",
            "approximate": design == "welch",
        },
        "degrees_of_freedom": df,
        "notes": [],
    }
    if not (se > 0 and standardizer > 0):
        result["notes"].append(
            "Zero or unrepresentable variability leaves the intervals unavailable."
        )
        return result
    half = float(stats.t.isf((1 - level) / 2, df)) * se
    raw = [(mean - half) * scale, (mean + half) * scale]
    if all(map(math.isfinite, raw)) and raw[0] < raw[1]:
        result["raw"]["interval"] = raw
    else:
        result["notes"].append("The raw interval cannot be represented in outcome units.")
    d = mean / standardizer
    if math.isfinite(d):
        result["standardized"]["estimate"] = d
    try:
        interval = [
            bound * (se / standardizer)
            for bound in _nct_interval(stats, optimize, mean / se, df, level)
        ]
        if not all(map(math.isfinite, interval)) or interval[0] >= interval[1]:
            raise ValueError("The standardized interval cannot be represented.")
        result["standardized"]["interval"] = interval
    except (ValueError, RuntimeError, ArithmeticError) as problem:
        result["notes"].append(str(problem))
    return result


def _average(values):
    if len(values) == 1:
        return values[0]
    scale = max(map(abs, values)) or 1.0
    return math.fsum(value / scale for value in values) / len(values) * scale


def _contrast(stats, optimize, rows, fields, design, reduction, level, left, right):
    group, outcome, unit = fields
    sides = {left: {}, right: {}}
    excluded = {}

    def omit(reason, *records):
        excluded.setdefault(reason, []).extend(records)

    for ordinal, row in enumerate(rows, 1):
        key = row[group]
        if key not in sides:
            omit("outside_selected_groups" if key.strip() else "missing_group", ordinal)
            continue
        identity = row[unit] if unit is not None else ordinal
        if isinstance(identity, str) and not identity.strip():
            omit("missing_unit", ordinal)
            continue
        try:
            value = float(row[outcome])
        except ValueError:
            omit("invalid_measurement" if row[outcome].strip() else "missing_measurement", ordinal)
            continue
        if not math.isfinite(value):
            omit("nonfinite_measurement", ordinal)
            continue
        sides[key].setdefault(identity, []).append((ordinal, value))
    a, b = sides[left], sides[right]
    if reduction == "refuse" and any(
        len(values) > 1 for side in (a, b) for values in side.values()
    ):
        raise ValueError(
            "A selected unit has repeated values. Choose an explicit within-unit mean or supply one value per unit."
        )
    overlap = a.keys() & b.keys()
    if design == "paired":
        for side in (a, b):
            for key in list(side):
                if key not in overlap:
                    omit("unmatched_pair", *(record for record, _ in side.pop(key)))
        ordered = list(a)
        b = {key: b[key] for key in ordered}
    elif unit is not None and overlap:
        raise ValueError(
            "A unit identifier occurs in both independent groups. Use distinct units or declare a paired design."
        )
    provenance = {
        "left_units": [[record for record, _ in records] for records in a.values()],
        "right_units": [[record for record, _ in records] for records in b.values()],
        "excluded": {reason: sorted(ordinals) for reason, ordinals in excluded.items()},
    }
    response = {
        "left": left,
        "right": right,
        "n_left": len(a),
        "n_right": len(b),
        "provenance": provenance,
    }
    if min(len(a), len(b)) < 2:
        return {
            **response,
            "status": "unavailable",
            "notes": ["At least two units per group or two complete pairs are required."],
        }
    left_values = [_average([value for _, value in records]) for records in a.values()]
    right_values = [_average([value for _, value in records]) for records in b.values()]
    try:
        result = _estimates(stats, optimize, left_values, right_values, design, level)
    except ValueError as problem:
        return {**response, "status": "unavailable", "notes": [str(problem)]}
    return {**response, **result, "status": "partial" if result["notes"] else "estimated"}


def compare_effects(raw: bytes, options: dict) -> dict:
    """Estimate an explicitly selected set of signed left-minus-right contrasts."""
    allowed = {
        "outcome",
        "group",
        "unit",
        "rows_are_units",
        "design",
        "reduction",
        "contrasts",
        "confidence",
        "assumptions_confirmed",
    }
    if not isinstance(options, dict) or options.keys() - allowed:
        raise ValueError("Supply only explicit effect comparison inputs.")
    design = options.get("design")
    if not isinstance(design, str) or design not in _MODELS:
        raise ValueError("Choose a supported study design.")
    if options.get("assumptions_confirmed") is not True:
        raise ValueError("Confirm the selected design and independent units before comparing.")
    columns, rows, source = _csv(raw)
    outcome, group, unit = (options.get(key) for key in ("outcome", "group", "unit"))
    chosen = [outcome, group, *([unit] if unit is not None else [])]
    if any(not isinstance(field, str) or field not in columns for field in chosen) or len(
        set(chosen)
    ) != len(chosen):
        raise ValueError("Choose distinct outcome, group and unit columns from this CSV.")
    if unit is None and (design == "paired" or options.get("rows_are_units") is not True):
        raise ValueError(
            "Choose a matching unit column for pairs or explicitly declare independent rows."
        )
    reduction = options.get("reduction", "refuse")
    if reduction not in ("refuse", "mean") or (unit is None and reduction != "refuse"):
        raise ValueError("Choose a supported unit reduction; the mean requires a unit column.")
    level = options.get("confidence")
    if type(level) not in (int, float) or not 0.5 <= level <= 0.999:
        raise ValueError("Choose a confidence level from 0.5 through 0.999.")
    levels = {row[columns.index(group)] for row in rows}
    contrasts = options.get("contrasts")
    if not isinstance(contrasts, list) or not 1 <= len(contrasts) <= 12:
        raise ValueError("Choose one to twelve contrasts.")
    pairs = []
    for contrast in contrasts:
        if (
            not isinstance(contrast, list)
            or len(contrast) != 2
            or any(
                not isinstance(value, str) or not value.strip() or value not in levels
                for value in contrast
            )
            or contrast[0] == contrast[1]
        ):
            raise ValueError("Each contrast requires two different groups present in this CSV.")
        pairs.append(tuple(contrast))
    if len(set(pairs)) != len(pairs):
        raise ValueError("Each signed contrast must be unique.")
    try:
        from scipy import optimize, stats
    except ImportError as problem:
        raise ValueError("Install graphunslopify[statistics] to compare effect sizes.") from problem
    fields = (
        columns.index(group),
        columns.index(outcome),
        columns.index(unit) if unit is not None else None,
    )
    results = [
        _contrast(stats, optimize, rows, fields, design, reduction, level, *pair) for pair in pairs
    ]
    status = "estimated" if all(row["status"] == "estimated" for row in results) else "partial"
    return {
        "schema_version": 1,
        "kind": "graphunslopify.effect-sizes",
        "status": status,
        "exit_code": 0 if status == "estimated" else 2,
        "source": source,
        "inputs": {
            "design": design,
            "outcome": outcome,
            "group": group,
            "unit": unit,
            "rows_are_units": unit is None,
            "confidence": level,
            "reduction": reduction,
        },
        "assumptions": _MODELS[design][1],
        "assumptions_verified": False,
        "comparisons": results,
        "scope": "Signed left-minus-right estimates and per-contrast intervals. No simultaneous coverage or study-design validation is claimed.",
    }


def effect_request(payload):
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("csv"), str)
        or len(payload["csv"]) > MAX_EFFECT_REQUEST_BYTES
    ):
        raise ValueError("Supply an encoded CSV snapshot.")
    try:
        raw = base64.b64decode(payload["csv"], validate=True)
    except ValueError as problem:
        raise ValueError("Could not decode the CSV snapshot.") from problem
    if payload.get("mode") == "profile":
        columns, rows, source = _csv(raw)
        group = payload.get("group")
        levels = []
        if group is not None:
            if group not in columns:
                raise ValueError("Choose a group column from this CSV.")
            index = columns.index(group)
            levels = list(dict.fromkeys(row[index] for row in rows if row[index].strip()))
        return {
            "source": source,
            "columns": columns,
            "levels": levels[:100],
            "level_count": len(levels),
        }
    if payload.get("mode") != "compare":
        raise ValueError("Choose a profile or effect comparison.")
    return compare_effects(raw, payload.get("options"))
