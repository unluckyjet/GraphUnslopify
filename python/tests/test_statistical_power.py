"""Published and numerical checks for declared prospective study designs."""

import json

import pytest
from test_project_changes_http import request
from test_project_changes_http import server as server  # noqa: PLC0414

from graphunslopify.cli import main
from graphunslopify.statistical_power import plan_power

pytest.importorskip("scipy")


def planning(**changes):
    return {
        "design": "paired",
        "calculation": "power",
        "n": 24,
        "alpha": 0.05,
        "alternative": "greater",
        "sd": 0.25,
        "effect": 0.08,
        "assumptions_confirmed": True,
        **changes,
    }


@pytest.mark.parametrize(
    ("settings", "published"),
    [
        ({"design": "paired"}, 0.4508691),
        (
            {
                "design": "pooled",
                "n": 30,
                "n_other": 30,
                "effect": 0.5,
                "sd": None,
                "alternative": "two_sided",
            },
            0.4778965,
        ),
        (
            {
                "design": "pooled",
                "n": 28,
                "n_other": 35,
                "effect": 0.5,
                "sd": None,
                "alternative": "two_sided",
            },
            0.4924588,
        ),
    ],
)
def test_published_r_pwr_examples(settings, published):
    result = plan_power(planning(**settings))
    assert result["result"]["power"] == pytest.approx(published, abs=5e-8)
    assert result["assumptions_verified"] is False


def test_one_sample_power_brackets_published_r_sample_size():
    inputs = planning(design="one_sample", sd=2.25, effect=0.5)
    low = plan_power(inputs | {"n": 174})["result"]["power"]
    high = plan_power(inputs | {"n": 175})["result"]["power"]
    assert low < 0.9 < high


@pytest.mark.parametrize(
    ("n", "other", "sd", "expected"),
    [
        (14, 14, 1 / 3, 0.9137),
        (15, 15, 0.5, 0.9088),
        (23, 23, 1, 0.9121),
        (54, 54, 2, 0.9007),
        (107, 107, 3, 0.9009),
        (8, 16, 1 / 3, 0.9300),
        (9, 18, 0.5, 0.9131),
        (17, 34, 1, 0.9033),
        (49, 98, 2, 0.9009),
        (102, 204, 3, 0.9012),
        (6, 18, 1 / 3, 0.9379),
        (7, 21, 0.5, 0.9075),
        (16, 48, 1, 0.9143),
        (48, 144, 2, 0.9048),
        (100, 300, 3, 0.9004),
    ],
)
def test_jan_shieh_table_one(n, other, sd, expected):
    result = plan_power(
        planning(
            design="welch", n=n, n_other=other, sd=sd, sd_other=1, effect=1, alternative="two_sided"
        )
    )
    assert result["result"]["power"] == pytest.approx(expected, abs=5.01e-5)
    assert result["method"]["fixed_degrees_of_freedom"] is None


@pytest.mark.parametrize("design", ["one_sample", "paired", "pooled", "welch"])
@pytest.mark.parametrize("alternative", ["less", "greater", "two_sided"])
def test_detectable_difference_round_trips_and_sign_is_explicit(design, alternative):
    inputs = planning(
        design=design,
        calculation="detectable_effect",
        effect=None,
        target_power=0.8,
        alternative=alternative,
        n_other=40 if design in {"pooled", "welch"} else None,
        sd_other=0.8 if design == "welch" else None,
    )
    answer = plan_power(inputs)["result"]
    effect = answer["difference"]
    assert (effect < 0) == (alternative == "less")
    replay = plan_power(inputs | {"calculation": "power", "target_power": None, "effect": effect})
    assert replay["result"]["power"] == pytest.approx(0.8, abs=1e-8)
    if alternative != "two_sided":
        opposing = plan_power(
            inputs | {"calculation": "power", "target_power": None, "effect": -effect}
        )
        assert opposing["result"]["power"] < opposing["result"]["null_rejection_probability"]


def test_null_probability_and_unit_rescaling():
    assert plan_power(planning(effect=0, alternative="two_sided"))["result"][
        "power"
    ] == pytest.approx(0.05)
    inputs = planning(
        design="welch", n=8, n_other=16, sd=1 / 3, sd_other=1, effect=1, alternative="two_sided"
    )
    reference = plan_power(inputs)["result"]
    assert reference["null_rejection_probability"] == pytest.approx(0.04959597, abs=1e-6)
    for factor in (1e-150, 1e150):
        scaled = plan_power(inputs | {"effect": factor, "sd": factor / 3, "sd_other": factor})
        assert scaled["result"]["power"] == pytest.approx(reference["power"], abs=1e-12)


@pytest.mark.parametrize(
    "inputs",
    [
        {"assumptions_confirmed": False},
        {"design": "clustered"},
        {"n": True},
        {"n_other": 20},
        {"sd_other": 0.1},
        {"alpha": float("nan")},
        {"effect": float("inf")},
        {"calculation": "detectable_effect", "effect": None, "target_power": 0.04},
        {"design": "welch", "n_other": 24},
        {"dataset": "observed.csv"},
    ],
)
def test_out_of_scope_or_incomplete_requests_refuse(inputs):
    with pytest.raises(ValueError):
        plan_power(planning(**inputs))


def test_real_paper_http_and_cli_share_calculation(server, capsys):
    _, paper = server
    before = {p.relative_to(paper): p.read_bytes() for p in paper.rglob("*") if p.is_file()}
    endpoint = "/api/statistical-power"
    request(server, endpoint, planning(), expected=403, token=False)
    request(
        server, endpoint, planning(), expected=403, headers={"Origin": "https://outside.invalid"}
    )
    request(server, endpoint, planning(assumptions_confirmed=False), expected=400)
    data = request(server, endpoint, planning())
    args = [
        "power",
        "--design",
        "paired",
        "--n",
        "24",
        "--alpha",
        "0.05",
        "--alternative",
        "greater",
        "--sd",
        "0.25",
        "--effect",
        "0.08",
    ]
    assert main(args) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "failed"
    assert main([*args, "--confirm-assumptions"]) == 0
    assert json.loads(capsys.readouterr().out) == data
    assert {p.relative_to(paper): p.read_bytes() for p in paper.rglob("*") if p.is_file()} == before
