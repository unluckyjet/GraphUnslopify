"""Right-censored survival must match independent product-limit reference values."""

from __future__ import annotations

import importlib.util
import itertools
import json
import subprocess
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from graphunslopify import read_provenance
from graphunslopify.transport import local_request

stats = pytest.importorskip(
    "scipy.stats", reason="Install the statistics extra for reference tests"
)

BASE = {
    "kind": "kaplan_meier",
    "x": {"field": "time", "label": "Follow-up"},
    "y": {"field": "survival", "label": "Surviving fraction"},
    "event": "event",
    "legend": {"show": False},
    "output": {"stem": "survival", "formats": ["png", "svg"], "dpi": 100},
}


def generated(folder, **extra):
    spec = {**BASE, "data": {"path": str(folder / "data.csv")}, **extra}
    if extra.get("group") and "legend" not in extra:
        spec["legend"] = {"position": "outside_bottom"}
    result = local_request("convert", spec)
    assert result.get("ok"), result
    path = folder / "survival.py"
    path.write_text(result["code"], encoding="utf8")
    definition = importlib.util.spec_from_file_location("survival_reference", path)
    module = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(module)
    return module, path


@pytest.fixture(scope="module")
def emitted(tmp_path_factory):
    return generated(tmp_path_factory.mktemp("survival-reference"))[0]


def sample(observed, censored):
    return pd.DataFrame(
        {"time": [*observed, *censored], "event": [1] * len(observed) + [0] * len(censored)}
    )


def plotted(module, frame):
    fig, ax = plt.subplots()
    try:
        module.draw_panel(ax, frame)
        lines = [
            tuple(np.asarray(data, dtype=float) for data in line.get_data()) for line in ax.lines
        ]
        markers = [np.asarray(collection.get_offsets()) for collection in ax.collections]
        return lines, markers
    finally:
        plt.close(fig)


def at(line, points):
    times, survival = line
    return survival[np.searchsorted(times, points, side="right") - 1]


def test_tied_event_and_censor_are_invariant_to_every_row_order(emitted):
    frame = sample([1, 2], [1])
    for permutation in itertools.permutations(range(3)):
        lines, _ = plotted(emitted, frame.iloc[list(permutation)])
        assert at(lines[0], [1])[0] == pytest.approx(2 / 3), permutation


@pytest.mark.parametrize(
    ("observed", "censored"),
    [
        ([1, 2], [1]),
        ([2, 2, 4], [2, 3, 6]),
        ([], [1, 2, 4]),
        ([1, 2, 2], []),
        ([0, 1], [0, 2]),
        ([77, 47, 81, 56, 80], [62, 60, 43, 71, 37]),
    ],
)
def test_real_artists_and_censor_marks_match_scipy_product_limit(emitted, observed, censored):
    frame = sample(observed, censored)
    reference = stats.ecdf(stats.CensoredData(uncensored=observed, right=censored)).sf
    lines, markers = plotted(emitted, frame)
    assert len(lines) == 1
    assert lines[0][0][0] == 0
    assert lines[0][0][-1] == max(observed + censored)
    np.testing.assert_allclose(
        at(lines[0], reference.quantiles), reference.probabilities, atol=1e-12
    )
    assert np.all(np.diff(lines[0][1]) <= 0)
    assert np.all((lines[0][1] >= 0) & (lines[0][1] <= 1))
    if censored:
        points = np.concatenate(markers)
        assert sorted(points[:, 0]) == sorted(censored)
        np.testing.assert_allclose(points[:, 1], reference.evaluate(points[:, 0]), atol=1e-12)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("time", -1),
        ("time", np.nan),
        ("time", np.inf),
        ("time", "invalid"),
        ("event", -1),
        ("event", 0.5),
        ("event", 2),
        ("event", np.nan),
        ("event", np.inf),
    ],
)
def test_invalid_domains_fail_before_plotting_or_silently_omitting_records(emitted, field, value):
    frame = sample([1, 2], [1]).astype(object)
    frame.loc[0, field] = value
    with pytest.raises(ValueError, match="Kaplan-Meier"):
        emitted.prepare(frame)
    with pytest.raises(ValueError, match="Kaplan-Meier"):
        plotted(emitted, frame)


def test_empty_cohort_cannot_produce_a_successful_empty_curve(emitted):
    with pytest.raises(ValueError, match="Kaplan-Meier"):
        emitted.prepare(sample([], []))


def test_description_uses_survival_and_censoring_without_needing_a_raw_y_column(emitted):
    description = emitted.alt_text(sample([1, 2], [1]))
    assert "3 observations" in description and "2 events" in description
    assert "1 right-censored" in description
    assert "survival is 0" in description and "follow-up 2" in description
    assert "median survival is 2" in description.lower()
    assert "mean is" not in description
    unseen = emitted.alt_text(sample([], [1, 2, 4]))
    assert "median survival is not reached" in unseen.lower() and "survival is 1" in unseen


def rendered(folder, rows, **extra):
    module, path = generated(folder, **extra)
    rows.to_csv(folder / "data.csv", index=False)
    process = subprocess.run(
        [sys.executable, str(path), "--strict", "--json"],
        cwd=folder,
        capture_output=True,
        text=True,
        check=False,
    )
    report = json.loads(process.stdout)
    assert report["exit_code"] == process.returncode, process.stderr
    return module, process, report


def test_grouped_claims_evaluate_plotted_survival_with_exported_provenance(tmp_path):
    rows = pd.concat(
        [
            sample([1, 2], [1]).assign(cohort="baseline"),
            sample([], [1, 1, 2]).assign(cohort="treated"),
        ]
    )
    _, process, report = rendered(
        tmp_path,
        rows,
        group="cohort",
        legend={"position": "outside_bottom"},
        claims=[{"kind": "beats_at_end", "subject": "treated", "reference": "baseline"}],
    )
    assert process.returncode == 0, process.stderr
    assert report["status"] == "passed" and report["claims"][0]["verdict"] == "holds"
    assert "baseline" in report["alt_text"] and "treated" in report["alt_text"]
    assert report["data"]["counts"]["read"] == 6
    for suffix in ["png", "svg"]:
        provenance = read_provenance(tmp_path / ("survival." + suffix))
        assert provenance["alt_text"] == report["alt_text"]
        assert provenance["spec_hash"] == report["spec_hash"]


def test_claim_does_not_extrapolate_a_censored_cohort_beyond_its_followup(tmp_path):
    rows = pd.concat(
        [sample([1, 2], [1]).assign(cohort="baseline"), sample([], [1]).assign(cohort="treated")]
    )
    _, process, report = rendered(
        tmp_path,
        rows,
        group="cohort",
        claims=[{"kind": "beats_at_end", "subject": "treated", "reference": "baseline"}],
    )
    assert process.returncode == 2
    assert report["claims"][0]["verdict"] == "untested"
    assert len(report["outputs"]) == 2
    assert not any(item["code"] == "runtime_error" for item in report["findings"])


def test_invalid_event_produces_failed_runtime_evidence_and_no_artifacts(tmp_path):
    _, process, report = rendered(tmp_path, pd.DataFrame({"time": [1, 2], "event": [1, 0.6]}))
    assert process.returncode == 1 and report["status"] == "failed"
    assert not report["outputs"]
    assert any("Kaplan-Meier" in item["message"] for item in report["findings"])


def test_claim_cannot_certify_raw_event_values_in_place_of_the_plotted_curve(tmp_path):
    rows = pd.concat(
        [
            sample([1, 2], [1]).assign(cohort="baseline"),
            sample([], [1, 1, 2]).assign(cohort="treated"),
        ]
    )
    _, process, report = rendered(
        tmp_path,
        rows,
        group="cohort",
        y={"field": "event", "label": "Surviving fraction"},
        claims=[{"kind": "beats_at_end", "subject": "baseline", "reference": "treated"}],
    )
    assert process.returncode == 2 and report["claims"][0]["verdict"] == "fails"
    assert "-1" in report["claims"][0]["detail"]
    assert report["outputs"]


def test_faceted_survival_claims_and_counts_remain_panel_scoped(tmp_path):
    first = pd.concat(
        [
            sample([1, 2], [1]).assign(cohort="baseline"),
            sample([], [1, 1, 2]).assign(cohort="treated"),
        ]
    )
    second = first.copy()
    second["time"] *= 2
    rows = pd.concat([first.assign(site="first"), second.assign(site="second")])
    _, process, report = rendered(
        tmp_path,
        rows,
        group="cohort",
        facet={"by": "site", "columns": 2},
        claims=[{"kind": "beats_at_end", "subject": "treated", "reference": "baseline"}],
        output={"stem": "survival", "formats": ["png"], "size": "double_column", "dpi": 100},
    )
    assert process.returncode == 0, process.stderr
    assert len(report["claims"]) == 2
    assert {claim["panel"] for claim in report["claims"]} == {0, 1}
    assert all(claim["verdict"] == "holds" for claim in report["claims"])
    assert report["data"]["counts"]["read"] == 12
    assert "follow-up 2" in report["alt_text"] and "follow-up 4" in report["alt_text"]


def test_missing_cohort_label_is_not_silently_removed_from_the_risk_set(tmp_path):
    module, _ = generated(tmp_path, group="cohort")
    frame = sample([1, 2], [1]).assign(cohort=["A", None, "A"])
    with pytest.raises(ValueError, match="nonmissing cohort"):
        module.prepare(frame)


def test_domain_validation_uses_the_rows_intentionally_retained_by_filter(tmp_path):
    module, _ = generated(tmp_path, filter=[{"field": "keep", "op": "eq", "value": 1}])
    retained = module.prepare(pd.DataFrame({"time": [-1, 2], "event": [0.7, 1], "keep": [0, 1]}))
    assert len(retained) == 1
    assert module.survival_estimate(retained)["events"] == 1


@pytest.mark.parametrize(
    "extra",
    [
        {"transform": {"kind": "cumulative"}},
        {
            "y": {"field": "time", "label": "Survival"},
            "group": "cohort",
            "claims": [{"kind": "monotone_decreasing", "subject": "A"}],
        },
    ],
)
def test_undefined_transforms_and_ambiguous_claim_roles_fail_static_validation(extra):
    result = local_request("convert", {**BASE, **extra})
    assert result["status"] == "translated" and not result["ok"]
    assert any(item["code"] == "unsupported_survival_semantics" for item in result["findings"])


@pytest.mark.parametrize("count", [2, 6, 10, 24, 100, 1000])
def test_even_uncensored_sample_median_is_the_first_half_survival_time(emitted, count):
    curve = emitted.survival_estimate(sample(list(range(1, count + 1)), []))
    assert curve["median"] == count / 2


def test_median_boundary_remains_stable_after_early_censoring(emitted):
    curve = emitted.survival_estimate(sample(list(range(2, 26)), [1, 1]))
    assert curve["median"] == 13
