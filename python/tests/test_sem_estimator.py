"""Standard error of a mean cannot silently label the uncertainty of a median."""

from __future__ import annotations

import importlib.util
import json
import math
import subprocess
import sys

import pandas as pd
import pytest

from graphunslopify.transport import local_request

KINDS = ["line", "bar", "forest", "table"]


def spec(kind, aggregation="median", uncertainty="sem", named=False):
    return {
        "kind": kind,
        "data": {"path": "data.csv"},
        "x": {"field": "category", "label": "Category"},
        "y": {"field": "value", "label": "Value"},
        "aggregation": aggregation,
        "uncertainty": {"kind": uncertainty, **({"over": "seed"} if named else {})},
        "legend": {"show": False},
        "output": {"stem": "estimate", "formats": ["png"], "size": "double_column"},
    }


def rows(named=False):
    if not named:
        return pd.DataFrame({"category": [1] * 3, "value": [1, 2, 9]})
    return pd.DataFrame(
        {
            "category": [1] * 6,
            "value": [0, 2, 1, 3, 8, 10],
            "seed": ["r1", "r1", "r2", "r2", "r3", "r3"],
        }
    )


def generated(tmp_path, raw, allow_errors=False):
    r = local_request("convert", raw)
    assert r["ok"] or allow_errors, r
    path = tmp_path / "estimate.py"
    path.write_text(r["code"], encoding="utf8")
    definition = importlib.util.spec_from_file_location("sem_reference", path)
    m = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(m)
    return m


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("named", [True, False])
def test_median_sem_is_an_explicit_estimator_error(kind, named):
    r = local_request("convert", spec(kind, named=named))
    assert not r["ok"]
    assert any(
        f["code"] == "median_sem_unsupported" and f["severity"] == "error" for f in r["findings"]
    )


@pytest.mark.parametrize("kind", KINDS)
def test_refused_generated_summary_cannot_compute_mean_sem_for_a_median(tmp_path, kind):
    m = generated(tmp_path, spec(kind), allow_errors=True)
    with pytest.raises(ValueError, match=r"SEM.*mean"):
        m.summarise(rows())


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("named", [True, False])
def test_mean_sem_retains_known_units_and_quantities(tmp_path, kind, named):
    m = generated(tmp_path, spec(kind, aggregation="mean", named=named))
    df = rows(named)
    original = df.copy(deep=True)
    row = m.summarise(df).iloc[0]
    assert row["value"] == 4
    assert row["_low"] == pytest.approx(4 - math.sqrt(19 / 3))
    assert row["_high"] == pytest.approx(4 + math.sqrt(19 / 3))
    pd.testing.assert_frame_equal(df, original)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("named", [True, False])
def test_median_bootstrap_retains_the_requested_estimator(tmp_path, kind, named):
    m = generated(tmp_path, spec(kind, uncertainty="ci", named=named))
    row = m.summarise(rows(named)).iloc[0]
    # Exact n=3 empirical bootstrap medians are1/2/9; both tails exceed2.5%.
    assert row["value"] == 2 and row["_low"] == 1 and row["_high"] == 9


@pytest.mark.parametrize("kind", KINDS)
def test_direct_strict_execution_cannot_certify_the_refused_interval(tmp_path, kind):
    m = generated(tmp_path, spec(kind), allow_errors=True)
    rows().to_csv(tmp_path / "data.csv", index=False, lineterminator="\n")
    result = subprocess.run(
        [sys.executable, m.__file__, "--strict", "--json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    r = json.loads(result.stdout)
    assert result.returncode != 0 and r["status"] == "failed"
    assert any(f["code"] == "median_sem_unsupported" for f in r["findings"])
    assert not r["outputs"]


def test_missing_aggregation_sem_guidance_does_not_recommend_a_median():
    r = local_request("convert", spec("line", aggregation="none"))
    message = next(
        f["message"] for f in r["findings"] if f["code"] == "uncertainty_without_aggregation"
    )
    assert "mean" in message and "median" not in message
