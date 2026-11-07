"""Compare native visual measurements for author-declared display alternatives."""

from __future__ import annotations

import copy

from .sensitivity import _compare_claims, _identity, _label, _run_variants

_KINDS = {"line", "scatter", "calibration"}
_FORBIDDEN = {
    "animate",
    "axis_break",
    "facet",
    "frontier",
    "inset",
    "layers",
    "repeat",
    "smooth",
    "y2",
}
_AXIS_SCALES = ("linear", "log", "symlog")
_LEGEND_POSITIONS = (
    "best",
    "upper_left",
    "upper_right",
    "lower_left",
    "lower_right",
    "outside_right",
    "outside_bottom",
)
_OPTIONS = {
    "x.scale": _AXIS_SCALES,
    "y.scale": _AXIS_SCALES,
    "legend.position": _LEGEND_POSITIONS,
    "uncertainty.display": ("bar", "band"),
}
_BOOLEAN = {"legend.show", "style.grid", "marker"}
_LIMITS = {"x.limits", "y.limits"}
_FIELDS = set(_OPTIONS) | _BOOLEAN | _LIMITS | {"bins"}
_DEFAULTS = {
    "x.scale": "linear",
    "y.scale": "linear",
    "legend.show": True,
    "legend.position": "best",
    "style.grid": False,
    "marker": False,
    "uncertainty.display": "band",
    "bins": 10,
}
_THRESHOLD_KEYS = {"axis_fraction", "ece_delta"}


def _number(value):
    return type(value) in (int, float) and -float("inf") < value < float("inf")


def _value(spec, key):
    group, dot, field = key.partition(".")
    return (
        (spec.get(group) or {}).get(field, _DEFAULTS.get(key))
        if dot
        else spec.get(group, _DEFAULTS.get(key))
    )


def _check_option(spec, key, value, thresholds):
    kind = spec["kind"]
    if key == "bins":
        if kind != "calibration" or type(value) is not int or not 3 <= value <= 50:
            raise ValueError("Only calibration supports bin counts from 3 through 50")
        if "ece_delta" not in thresholds:
            raise ValueError("Declare a material ECE difference before comparing bins")
    elif key in _OPTIONS:
        if value not in _OPTIONS[key]:
            raise ValueError(f"Unsupported {key} setting")
        if key == "uncertainty.display" and not (kind == "line" and spec.get("uncertainty")):
            raise ValueError("Interval display requires a line with declared uncertainty")
    elif key in _BOOLEAN:
        if type(value) is not bool or (key == "marker" and kind != "line"):
            raise ValueError(f"{key} requires a supported boolean setting")
    elif key in _LIMITS and value is not None:
        if (
            not isinstance(value, list)
            or len(value) != 2
            or not all(map(_number, value))
            or value[0] >= value[1]
        ):
            raise ValueError("Enter two increasing finite axis limits or null for automatic limits")
    if key.split(".")[0] in ("x", "y"):
        if kind == "calibration":
            raise ValueError("Calibration alternatives use the fixed probability axes")
        if "axis_fraction" not in thresholds:
            raise ValueError(
                "Declare a material axes-fraction shift before comparing scales or limits"
            )


def robustness_plan(spec, alternatives, thresholds):
    """Allow presentation changes while preserving the data and scientific settings."""
    if (
        not isinstance(spec, dict)
        or not isinstance(spec.get("kind"), str)
        or spec["kind"] not in _KINDS
    ):
        raise ValueError("Choose a line, scatter or calibration figure")
    if not isinstance(spec.get("data"), dict) or not all(
        isinstance(spec.get(axis), dict) for axis in ("x", "y")
    ):
        raise ValueError("Choose a dataset and both figure axes")
    if any(spec.get(name) for name in _FORBIDDEN):
        raise ValueError("Use a single ordinary figure without nested axes, layers or smoothing")
    if any(
        name in spec and not isinstance(spec[name], dict)
        for name in ("legend", "style", "uncertainty", "output")
    ):
        raise ValueError("Use objects for figure display settings")
    if spec.get("legend", {}).get("style") == "direct":
        raise ValueError("Use a box legend for the supported legend evidence")
    if (
        not isinstance(thresholds, dict)
        or not thresholds.keys() <= _THRESHOLD_KEYS
        or any(not _number(value) or not 0 < value <= 1 for value in thresholds.values())
    ):
        raise ValueError(
            "Set axis_fraction and ece_delta thresholds between zero and one when applicable"
        )
    if not isinstance(alternatives, list) or not 1 <= len(alternatives) <= 4:
        raise ValueError("Choose one to four display alternatives")
    if len(_identity(spec)) > 64 * 1024 or len(_identity(alternatives)) > 64 * 1024:
        raise ValueError("The figure or alternatives exceed the supported size")
    baseline = copy.deepcopy(spec)
    plan = [{"label": "Baseline", "justification": None, "changes": {}, "spec": baseline}]
    names = {"baseline"}
    seen = {_identity({key: _value(baseline, key) for key in _FIELDS})}
    for item in alternatives:
        if not isinstance(item, dict) or set(item) != {"label", "justification", "changes"}:
            raise ValueError(
                "Each alternative needs a label, justification and explicit display changes"
            )
        label = _label(item["label"], 80, "Alternative label")
        reason = _label(item["justification"], 600, "Display justification")
        changes = item["changes"]
        if (
            label.casefold() in names
            or not isinstance(changes, dict)
            or not changes
            or not changes.keys() <= _FIELDS
        ):
            raise ValueError("Use distinct labels and supported display changes")
        variant = copy.deepcopy(baseline)
        for key, value in changes.items():
            _check_option(baseline, key, value, thresholds)
            group, dot, field = key.partition(".")
            target = variant.setdefault(group, {}) if dot else variant
            name = field if dot else group
            if value is None:
                target.pop(name, None)
            else:
                target[name] = copy.deepcopy(value)
        signature = _identity({key: _value(variant, key) for key in _FIELDS})
        if signature in seen:
            raise ValueError("Each alternative must change a distinct visual setting")
        seen.add(signature)
        names.add(label.casefold())
        plan.append({"label": label, "justification": reason, "changes": changes, "spec": variant})
    return plan


def _projections(before, after, threshold):
    old = {item["series"]: item for item in before["series"]}
    new = {item["series"]: item for item in after["series"]}
    result = []
    for label in dict.fromkeys([*old, *new]):
        left, right = old.get(label), new.get(label)
        if not left or not right or left["data_sha256"] != right["data_sha256"]:
            result.append({"series": label, "status": "different_plotted_quantities"})
            continue
        visible = list(zip(left["inside"], right["inside"], strict=True))
        shift = None
        for (a, b), (was_visible, is_visible) in zip(
            zip(left["projected"], right["projected"], strict=True), visible, strict=True
        ):
            if was_visible and is_visible:
                current = max(abs(a[0] - b[0]), abs(a[1] - b[1]))
                shift = current if shift is None else max(shift, current)
        result.append(
            {
                "series": label,
                "status": "compared",
                "centers_lost": sum(a and not b for a, b in visible),
                "centers_gained": sum(b and not a for a, b in visible),
                "outside_scale_domain_before": left["outside_scale_domain"],
                "outside_scale_domain_after": right["outside_scale_domain"],
                "max_common_center_axis_shift": shift,
                "shift_exceeds_threshold": shift is not None
                and threshold is not None
                and shift >= threshold,
            }
        )
    return result


def _calibration(before, after, threshold):
    if before is None or after is None:
        return []
    old = {item["series"]: item for item in before["series"]}
    new = {item["series"]: item for item in after["series"]}
    result = []
    for label in dict.fromkeys([*old, *new]):
        left, right = old.get(label), new.get(label)
        if not left or not right or left["observations"] != right["observations"]:
            result.append({"series": label, "status": "different_prediction_counts"})
            continue
        delta = right["ece"] - left["ece"]
        result.append(
            {
                "series": label,
                "status": "compared",
                "ece_before": left["ece"],
                "ece_after": right["ece"],
                "ece_delta": delta,
                "occupied_bins_before": len(left["points"]),
                "occupied_bins_after": len(right["points"]),
                "ece_exceeds_threshold": threshold is not None and abs(delta) >= threshold,
            }
        )
    return result


def _compare_visuals(baseline, variant, thresholds):
    before, after = baseline.get("visual"), variant.get("visual")
    if before is None or after is None:
        return {
            "status": "unavailable",
            "review_reasons": ["One native visualization could not be measured."],
        }
    projections = _projections(before, after, thresholds.get("axis_fraction"))
    calibration = _calibration(
        before["calibration"], after["calibration"], thresholds.get("ece_delta")
    )
    claims = _compare_claims(baseline["claims"], variant["claims"])
    reasons = []
    if any(row.get("shift_exceeds_threshold") for row in projections):
        reasons.append("The matching visible centers reach the declared axes-fraction threshold.")
    if any(row.get("centers_lost") or row.get("centers_gained") for row in projections):
        reasons.append("The axes or scale domain show a different set of plotted data centers.")
    if before["calibration"] is None and any(row["status"] != "compared" for row in projections):
        reasons.append("Some plotted quantities could not be matched across choices.")
    if any(row.get("ece_exceeds_threshold") for row in calibration):
        reasons.append("Binned calibration error reaches the declared ECE threshold.")
    if any(row["status"] != "compared" for row in calibration):
        reasons.append("Calibration predictions could not be aligned across choices.")
    if claims is None:
        reasons.append("The authored claim results could not be aligned.")
    elif any(item["changed"] for item in claims):
        reasons.append("A recorded claim verdict changed.")
    if before["legend_labels"] and not after["legend_labels"]:
        reasons.append("The rendered legend labels were removed.")
    if variant["status"] != "checked" or baseline["status"] != "checked":
        reasons.append("A strict figure verification was incomplete or failed.")
    return {
        "status": "review" if reasons else "checked",
        "review_reasons": reasons,
        "projected_centers": projections,
        "calibration": calibration,
        "claim_comparison": claims,
    }


def run_robustness(
    spec, alternatives, thresholds, *, data, destination, reviewed, palette=None, timeout=60
):
    plan = robustness_plan(spec, alternatives, thresholds)
    if reviewed is not True:
        raise ValueError("Explicitly review the display alternatives and materiality thresholds")
    output, snapshot, choices = _run_variants(
        spec,
        plan,
        data=data,
        destination=destination,
        palette=palette,
        timeout=timeout,
        visual=True,
    )
    for choice in choices[1:]:
        choice["comparison"] = _compare_visuals(choices[0], choice, thresholds)
    for choice in choices:
        choice.pop("estimates", None)
        if "visual" in choice:
            for item in choice["visual"]["series"]:
                item.pop("projected")
                item.pop("inside")
    status = (
        "partial"
        if any(item["status"] != "checked" for item in choices)
        else (
            "review"
            if any(item["comparison"]["status"] == "review" for item in choices[1:])
            else "checked"
        )
    )
    report = {
        "schema_version": 1,
        "kind": "graphunslopify.visual-robustness",
        "status": status,
        "exit_code": 0 if status == "checked" else 2,
        "source": snapshot,
        "thresholds": thresholds,
        "choices": choices,
        "scope": "Native visual signals and recorded claim verdicts for the declared alternatives. "
        "Center visibility does not measure mark overlap or complete line segments. "
        "Materiality reflects declared thresholds and explicit review flags.",
    }
    (output / "robustness.json").write_text(_identity(report) + "\n", encoding="utf8")
    return report
