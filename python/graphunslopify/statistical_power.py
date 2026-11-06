"""Prospective power and detectable differences under declared normal models."""

from __future__ import annotations

import math
from functools import lru_cache

DESIGNS = {
    "one_sample": "Independent observations with normally distributed outcomes.",
    "paired": "Independent complete pairs with normally distributed within-pair differences.",
    "pooled": "Independent groups with normally distributed outcomes and a common variance.",
    "welch": "Independent groups with normally distributed outcomes and separately planned variances.",
}
ALTERNATIVES = ("two_sided", "greater", "less")
_FIELDS = {
    "design",
    "calculation",
    "n",
    "n_other",
    "alpha",
    "alternative",
    "sd",
    "sd_other",
    "effect",
    "target_power",
    "assumptions_confirmed",
}


def _number(payload, key):
    value = payload.get(key)
    try:
        if type(value) in (float, int) and math.isfinite(value):
            return float(value)
    except OverflowError:
        pass
    raise ValueError(f"Enter a finite numeric value for {key}.")


def _count(payload, key):
    value = payload.get(key)
    if type(value) is not int or not 2 <= value <= 1_000_000:
        raise ValueError(f"Enter 2 to 1,000,000 planned independent units for {key}.")
    return value


def _positive(payload, key):
    value = _number(payload, key)
    if value <= 0:
        raise ValueError(f"Enter a positive planning standard deviation for {key}.")
    return value


@lru_cache(maxsize=4)
def _integration_nodes(order):
    from scipy.special import roots_legendre

    nodes, weights = roots_legendre(order)
    return (nodes + 1) / 2, weights / 2


def _probabilities(stats, critical, df, noncentrality, alternative):
    if alternative == "less":
        return stats.nct.sf(critical, df, -noncentrality)
    upper = stats.nct.sf(critical, df, noncentrality)
    if alternative == "two_sided":
        return upper + stats.nct.cdf(-critical, df, noncentrality)
    return upper


def _welch_evaluator(stats, np, n, other, sd, sd_other, alpha, alternative, order):
    # Jan & Shieh (2011), Eq. 3. Integrate over the Beta share of the two
    # independent chi-square variates. The critical t df depends on that share.
    nodes, weights = _integration_nodes(order)
    df1, df2 = n - 1, other - 1
    df = df1 + df2
    first, second = sd**2 / n, sd_other**2 / other
    share = stats.beta.ppf(nodes, df1 / 2, df2 / 2)
    a, b = first * share / df1, second * (1 - share) / df2
    total = a + b
    welch_df = total**2 / (a**2 / df1 + b**2 / df2)
    tail = alpha / 2 if alternative == "two_sided" else alpha
    critical = stats.t.isf(tail, welch_df) * np.sqrt(df * total / (first + second))

    def evaluate(noncentrality):
        p = _probabilities(stats, critical, df, noncentrality, alternative)
        return float(np.dot(weights, p))

    return evaluate


def _probability(evaluate, noncentrality):
    if not math.isfinite(noncentrality) or abs(noncentrality) > 1e8:
        raise ValueError("The proposed difference is outside the supported numerical range.")
    try:
        value = float(evaluate(noncentrality))
    except (ArithmeticError, RuntimeError) as problem:
        raise ValueError("Power could not be evaluated for these planning inputs.") from problem
    if not math.isfinite(value) or not -1e-12 <= value <= 1 + 1e-12:
        raise ValueError("Power could not be evaluated for these planning inputs.")
    return min(1.0, max(0.0, value))


def _solve(evaluate, optimize, target, direction):
    def error(magnitude):
        return _probability(evaluate, direction * magnitude) - target

    bound = 1.0
    while error(bound) < 0 and bound < 2**20:
        bound *= 2
    if error(bound) < 0:
        raise ValueError("The target power is outside the supported numerical range.")
    return direction * optimize.brentq(error, 0, bound, xtol=1e-10)


def plan_power(payload: dict) -> dict:
    """Calculate power or a detectable difference without reading observed data."""
    if not isinstance(payload, dict) or payload.keys() - _FIELDS:
        raise ValueError("Supply only explicit statistical power planning inputs.")
    design = payload.get("design")
    if not isinstance(design, str) or design not in DESIGNS:
        raise ValueError("Choose a supported normal-model design.")
    if payload.get("assumptions_confirmed") is not True:
        raise ValueError("Confirm the stated study-design assumptions before calculating.")
    alternative = payload.get("alternative")
    if alternative not in ALTERNATIVES:
        raise ValueError("Choose a two-sided, greater, or less alternative.")
    n = _count(payload, "n")
    independent_groups = design in {"pooled", "welch"}
    other = _count(payload, "n_other") if independent_groups else None
    if not independent_groups and payload.get("n_other") is not None:
        raise ValueError("One-sample and paired designs use a single planned unit count.")
    alpha = _number(payload, "alpha")
    if not 1e-8 <= alpha <= 0.5:
        raise ValueError("Enter alpha from 0.00000001 to 0.5.")
    sd = _positive(payload, "sd") if design == "welch" or payload.get("sd") is not None else None
    sd_other = _positive(payload, "sd_other") if design == "welch" else None
    if design != "welch" and payload.get("sd_other") is not None:
        raise ValueError("A second planning standard deviation applies only to Welch designs.")
    calculation = payload.get("calculation")
    if calculation == "power" and payload.get("target_power") is None:
        effect, target = _number(payload, "effect"), None
    elif calculation == "detectable_effect" and payload.get("effect") is None:
        effect, target = None, _number(payload, "target_power")
        if not 0 < target < 1:
            raise ValueError("Enter a target power between 0 and 1.")
    else:
        raise ValueError(
            "Choose either power with an effect or detectable effect with target power."
        )
    try:
        import numpy as np
        from scipy import optimize, stats
    except ImportError as problem:
        raise ValueError(
            "Install graphunslopify[statistics] to calculate planning power."
        ) from problem

    direction = -1 if alternative == "less" else 1
    df = n + other - 2 if other is not None else n - 1
    common_scale = max(sd, sd_other) if design == "welch" else (sd if sd is not None else 1.0)
    if design == "welch":
        if min(sd, sd_other) / common_scale < 1e-8:
            raise ValueError(
                "Welch planning supports a standard deviation ratio up to 100,000,000."
            )
        first, second = sd / common_scale, sd_other / common_scale
        se = math.hypot(first / math.sqrt(n), second / math.sqrt(other))
        orders = (128, 256, 512, 1024)
    else:
        se = math.sqrt(1 / n + (1 / other if other is not None else 0))
        critical = stats.t.isf(alpha / 2 if alternative == "two_sided" else alpha, df)
        orders = (None,)

    previous = None
    for order in orders:
        if order is None:

            def evaluate(value):
                return _probabilities(stats, critical, df, value, alternative)
        else:
            evaluate = _welch_evaluator(
                stats, np, n, other, first, second, alpha, alternative, order
            )
        null_power = alpha if order is None else _probability(evaluate, 0)
        if target is not None and target <= null_power:
            raise ValueError("Target power must exceed the rejection probability at zero effect.")
        noncentrality = (
            effect / common_scale / se
            if target is None
            else _solve(evaluate, optimize, target, direction)
        )
        power = null_power if noncentrality == 0 else _probability(evaluate, noncentrality)
        if order is None or (
            previous is not None
            and abs(_probability(previous, noncentrality) - power) <= 1e-6
            and abs(_probability(previous, 0) - null_power) <= 1e-6
        ):
            break
        previous = evaluate
    else:
        raise ValueError("Welch integration did not converge for these planning inputs.")
    difference = effect if effect is not None else (noncentrality * se) * common_scale
    if not math.isfinite(difference) or (difference == 0 and target is not None):
        raise ValueError("The detectable difference is outside the representable outcome range.")
    if target is not None:
        power = _probability(evaluate, difference / common_scale / se)
        if abs(power - target) > 1e-6:
            raise ValueError(
                "The detectable difference is outside the representable outcome range."
            )
    return {
        "schema_version": 1,
        "kind": "graphunslopify.statistical-power",
        "status": "calculated",
        "inputs": {
            "design": design,
            "calculation": calculation,
            "alternative": alternative,
            "n": n,
            "n_other": other,
            "alpha": alpha,
            "sd": sd,
            "sd_other": sd_other,
            "effect": effect,
            "target_power": target,
            "assumptions_confirmed": True,
        },
        "result": {
            "power": power,
            "null_rejection_probability": null_power,
            "difference": difference,
            "difference_scale": "outcome_units" if sd is not None else "standardized",
            "standardized_difference": difference / common_scale if design != "welch" else None,
        },
        "method": {
            "name": "Normal-model Welch power by beta-mixture integration"
            if design == "welch"
            else "Noncentral t rejection probability",
            "fixed_degrees_of_freedom": df if design != "welch" else None,
            "integration_order": order,
            "reference": "https://doi.org/10.3758/s13428-011-0095-7"
            if design == "welch"
            else "https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.nct.html",
        },
        "assumptions": [
            DESIGNS[design],
            "Fixed sample sizes, one declared test, and pre-specified direction and planning inputs.",
        ],
        "assumptions_verified": False,
        "scope": "Prospective planning for mean differences. No observed data or figure verdict is used. Clustered, sequential, equivalence and multiple-testing designs require a different model.",
    }
