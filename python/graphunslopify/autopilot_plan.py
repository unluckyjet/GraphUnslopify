"""Question-grounded, reviewable proposals over actual selected data; no inference claims."""

from __future__ import annotations

import io
import json
import re

from .describe import _read, _role
from .experiment_imports import _number

MAX_ROWS = 100_000
MAX_DATA = 20 * 1024 * 1024
INTENTS = {"comparison", "distribution", "relationship", "trend"}


def _words(value):
    return {word.rstrip("s") for word in re.findall(r"[^\W_]+", value.lower())}


def _choose(names, question, roles=None):
    if len(names) == 1:
        return names[0]
    ranked = sorted(
        (
            (len(_words(name) & _words(question)), int((roles or {}).get(name) == "measure"), name)
            for name in names
        ),
        reverse=True,
    )
    if ranked and ranked[0][:2] != ranked[1][:2]:
        return ranked[0][2]
    return None


def _intent(question):
    words = _words(question)
    for intent, terms in [
        ("trend", {"trend", "change", "time", "epoch", "step", "evolve"}),
        ("relationship", {"relation", "relationship", "association", "correlation", "tradeoff"}),
        (
            "comparison",
            {"compare", "comparison", "differ", "difference", "between", "better", "outperform"},
        ),
        ("distribution", {"distribution", "spread", "outlier", "describe", "show", "explore"}),
    ]:
        if words & terms:
            return intent
    return None


def make_plan(path, question, choices):
    import numpy as np
    import pandas as pd

    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 2000:
        raise ValueError("Describe the research question in 1-2000 characters")
    if set(choices) - {
        "target",
        "group",
        "predictor",
        "intent",
        "units",
        "sheet",
        "predictor_temporal",
    }:
        raise ValueError("Unknown autopilot choices")
    frame = _read(path, choices.get("sheet"))
    identity_names = None
    if path.suffix.lower() == ".json":
        identity_names = pd.DataFrame(json.loads(path.read_bytes()), dtype=object)
        if len(identity_names) != len(frame) or len(identity_names.columns) != len(frame.columns):
            raise ValueError("Identifier and measurement rows do not align")
        frame.columns = identity_names.columns
    if not 1 <= len(frame) <= MAX_ROWS or not 1 <= len(frame.columns) <= 128:
        raise ValueError("Choose a dataset with 1-100000 rows and at most128 columns")
    if (
        any(not isinstance(c, str) or not 1 <= len(c) <= 128 for c in frame.columns)
        or not frame.columns.is_unique
    ):
        raise ValueError("Use unique text column names of at most128 characters")
    roles = {c: _role(frame[c], len(frame)) for c in frame.columns}
    numeric = [c for c in frame.columns if pd.api.types.is_numeric_dtype(frame[c])]
    categorical = [
        c
        for c in frame.columns
        if not pd.api.types.is_numeric_dtype(frame[c]) and frame[c].nunique(dropna=True) <= 32
    ]
    target = choices.get("target") or _choose(numeric, question, roles)
    intent = choices.get("intent") or _intent(question)
    group = choices.get("group")
    if group is None and intent in {"comparison", "trend", "relationship"}:
        group = _choose(
            [c for c in categorical if c not in {target, choices.get("predictor")}], question
        )
    if group == "":
        group = None
    predictor = choices.get("predictor")
    if predictor is None and intent in {"trend", "relationship"}:
        predictor = _choose([c for c in numeric if c != target], question)
    if predictor == "":
        predictor = None
    fields = [
        {
            "name": c,
            "dtype": str(frame[c].dtype),
            "role": roles[c],
            "role_inference": "heuristic",
            "missing": int(frame[c].isna().sum()),
            "distinct": int(frame[c].nunique(dropna=True)),
        }
        for c in frame.columns
    ]
    report = {
        "schema_version": 1,
        "engine": "question-grounded deterministic proposals v1",
        "question": question,
        "input_rows": len(frame),
        "fields": fields,
        "choices": {
            "target": target,
            "group": group,
            "predictor": predictor,
            "intent": intent,
            "units": choices.get("units") or {},
            "sheet": frame.attrs.get("_graphunslopify_excel_sheet", choices.get("sheet")),
            "predictor_temporal": choices.get("predictor_temporal", False),
        },
        "mapping_requires_author_review": True,
        "scientific_appropriateness_certified": False,
        "native_verification": "not_run",
        "data_sent_to_model": False,
    }

    def unresolved(reason):
        return {
            "report": {**report, "ready": False, "reason": reason},
            "drafts": [],
            "data_text": None,
        }

    if intent not in INTENTS:
        return unresolved(
            "Choose whether the question concerns comparison,distribution,relationship or trend"
        )
    if target not in frame.columns:
        return unresolved(
            "Select the measured outcome; question/role heuristics did not identify it unambiguously"
        )
    if group is not None and (group not in frame.columns or group == target):
        return unresolved("Choose a different existing grouping column")
    if intent == "comparison" and group is None:
        return unresolved("Select the column defining the comparison groups")
    if intent in {"trend", "relationship"} and (
        predictor not in frame.columns or predictor in {target, group}
    ):
        return unresolved("Select a different existing predictor or ordered x column")
    if intent not in {"trend", "relationship"}:
        predictor = None
        report["choices"]["predictor"] = None
    temporal = choices.get("predictor_temporal", False)
    if type(temporal) is not bool or (temporal and predictor is None):
        return unresolved("Temporal x requires an explicitly selected predictor")
    units = choices.get("units") or {}
    if not isinstance(units, dict) or any(
        c not in ({target} | ({predictor} if predictor is not None else set()))
        or not isinstance(v, str)
        or not 1 <= len(v) <= 32
        for c, v in units.items()
    ):
        return unresolved("Supply units only for selected numeric fields,using 1-32 characters")

    group_values = None
    if group:
        if path.suffix.lower() == ".csv":
            group_values = pd.read_csv(path, dtype={group: "string"}, usecols=[group])[
                group
            ].tolist()
        elif identity_names is not None:
            group_values = identity_names[group].tolist()
        else:
            group_values = frame[group].tolist()
        if len(group_values) != len(frame):
            return unresolved("Identifier and measurement rows do not align")
    records, excluded = [], []
    groups = []
    for position, row in enumerate(frame.to_dict(orient="records")):
        reasons = []

        def number(field, row, reasons):
            value = row[field]
            if hasattr(value, "item"):
                value = value.item()
            value, issue = _number(value)
            if issue:
                reasons.append({"field": field, "reason": issue})
            return value

        value = number(target, row, reasons)
        x = position
        if predictor:
            if temporal:
                try:
                    stamp = pd.Timestamp(row[predictor])
                    if pd.isna(stamp):
                        raise ValueError("Missing date")
                    x = stamp.isoformat()
                except (ValueError, TypeError, OverflowError):
                    reasons.append({"field": predictor, "reason": "invalid_or_missing_date"})
            else:
                x = number(predictor, row, reasons)
        label = "All observations"
        if group:
            raw = group_values[position]
            if not pd.api.types.is_scalar(raw) or pd.isna(raw):
                reasons.append({"field": group, "reason": "missing_or_nonscalar_group"})
            else:
                label = str(raw)
                if not label or len(label) > 256:
                    reasons.append({"field": group, "reason": "empty_or_oversized_group"})
        if reasons:
            excluded.append({"source_record": position, "reasons": reasons})
            continue
        if label not in groups:
            groups.append(label)
            if len(groups) > 32:
                return unresolved("Select at most32 groups for reviewed figure drafts")
        records.append(
            {"measure": value, "predictor": x, "group": label, "source_record": position}
        )
    if not records:
        return unresolved("No joint valid observations remain for the selected fields")
    data_text = json.dumps(records, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    if len(data_text.encode()) > MAX_DATA:
        return unresolved("Normalized plotting data exceeds20MiB")
    # Check the same JSON reader used by native figures before calling a proposal ready.
    normalized = pd.read_json(io.StringIO(data_text))
    for key in ["measure", *([] if temporal else ["predictor"])]:
        actual = normalized[key].to_numpy(dtype=float)
        expected = np.asarray([r[key] for r in records], dtype=float)
        if not np.isfinite(actual).all() or not np.allclose(actual, expected, rtol=1e-14, atol=0):
            return unresolved(
                "The native JSON reader cannot preserve the selected numeric representation"
            )
    # The canonical JSON loader restores category/series identities from these
    # same raw bytes, independently of pandas' numeric inference (e.g. 001).
    names = pd.DataFrame(json.loads(data_text), dtype=object)
    if list(names["group"]) != [r["group"] for r in records]:
        return unresolved("Normalized source identities changed")

    def axis(field, label, original=None):
        result = {"field": field, "label": label}
        if original in units:
            result["unit"] = units[original]
        return result

    def spec(kind, x, y, **settings):
        if settings.get("group"):
            settings["series_order"] = groups
        return {
            "kind": kind,
            "data": {"path": "autopilot-data.json", "format": "json", "columns": list(records[0])},
            "x": x,
            "y": y,
            "output": {"stem": "autopilot-" + kind, "formats": ["png", "svg", "pdf"]},
            **settings,
        }

    measure = axis("measure", target, target)
    empirical = {
        "id": "empirical",
        "name": "Empirical distribution",
        "why": f"Shows the observed distribution of {target} without bin widths or density smoothing.",
        "tradeoff": "Preserves each observed value; it does not show association with an ordered predictor or establish population uncertainty.",
        "assumptions": [
            "Empirical proportions describe this reviewed sample; no independence or population inference is asserted."
        ],
        "spec": spec(
            "ecdf",
            measure,
            axis("proportion", "Empirical cumulative proportion"),
            **(
                {"group": "group", "legend": {"show": True, "title": group}}
                if group
                else {"legend": {"show": False}}
            ),
        ),
    }
    points = {
        "id": "observations",
        "name": "Raw observations",
        "why": f"Keeps every reviewed {target} observation visible against {predictor or 'its source record position'}.",
        "tradeoff": "Points can overlap. A source record position is an index,not time or an independent experimental unit.",
        "assumptions": [
            "No aggregation,uncertainty estimator or optimization direction is inferred."
        ],
        "spec": spec(
            "scatter",
            {
                **axis("predictor", predictor or "Source record index (not time)", predictor),
                **({"temporal": True} if temporal else {}),
            },
            measure,
            **(
                {"group": "group", "legend": {"show": True, "title": group}}
                if group
                else {"legend": {"show": False}}
            ),
        ),
    }
    box = {
        "id": "quartiles",
        "name": "Quartiles and raw points",
        "why": f"Compares the observed median and spread of {target}"
        + (f" across {group}." if group else "."),
        "tradeoff": "Quartiles summarize the sample; points remain visible. A box is not an uncertainty interval for a population parameter.",
        "assumptions": [
            "Default native quartiles and1.5-IQR whiskers are descriptive summaries; no notch or hypothesis test."
        ],
        "spec": spec(
            "box",
            axis("group", group or "Reviewed sample"),
            measure,
            show_points=True,
            notch=False,
            category_order=groups,
            legend={"show": False},
        ),
    }
    if intent == "comparison":
        third = {
            "id": "means",
            "name": "Descriptive group means",
            "why": f"Places each observed group mean of {target} on a shared baseline for the comparison question.",
            "tradeoff": "Means hide variation; consult the empirical and raw-point views. No uncertainty or significance is established.",
            "assumptions": [
                "Arithmetic mean of reviewed rows,not a justified experimental-unit or population estimator.",
                "No intervals,independence assumptions or significance tests are added.",
            ],
            "spec": spec(
                "bar",
                axis("group", group),
                measure,
                aggregation="mean",
                order=groups,
                legend={"show": False},
            ),
        }
        drafts = [box, empirical, third]
    elif intent in {"trend", "relationship"}:
        duplicate = len(records) - len({(r["predictor"], r["group"]) for r in records})
        third = {
            "id": "ordered",
            "name": "Ordered descriptive profile",
            "why": f"Shows how reviewed {target} values vary along {predictor} for the {intent} question.",
            "tradeoff": "Connecting values suggests continuity. Repeated x/group cells use descriptive row means; a line is not a causal or fitted model.",
            "assumptions": [
                "Order by the selected x field,not source row order.",
                f"{duplicate} repeated x/group rows;"
                + (
                    "arithmetic row means require explicit author review."
                    if duplicate
                    else "no aggregation is required."
                ),
            ],
            "spec": spec(
                "line",
                {
                    **axis("predictor", predictor, predictor),
                    **({"temporal": True} if temporal else {}),
                },
                measure,
                aggregation="mean" if duplicate else "none",
                marker=True,
                **(
                    {"group": "group", "legend": {"show": True, "title": group}}
                    if group
                    else {"legend": {"show": False}}
                ),
            ),
        }
        drafts = [points, third, empirical]
    else:
        drafts = [empirical, box, points]
    report.update(
        ready=True,
        selected_rows=len(records),
        excluded_records=excluded,
        excluded_count=len(excluded),
        groups=groups,
        exclusion_policy="All three use the same reviewed joint-valid sample across selected fields.",
        normalization="Materialize selected plotting values,group display identities and zero-based source record positions in an owned JSON table; original input stays unchanged. Reader float64 agreement is checked at rtol1e-14/atol0.",
        units_policy="Units are author labels,no automatic conversion or percentage scaling.",
        review_required=[
            "question and field mapping",
            "units or their absence",
            "each draft's assumptions/trade-offs",
            "joint-sample exclusions",
        ],
        finite_observations=len(records),
    )
    return {"report": report, "drafts": drafts, "data_text": data_text}
