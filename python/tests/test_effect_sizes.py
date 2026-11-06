"""Published normal-model effects and exact parsed-record ancestry."""

import base64
import hashlib
import json

import pytest
from test_project_changes_http import request
from test_project_changes_http import server as server  # noqa: PLC0414

from graphunslopify.cli import main
from graphunslopify.effect_sizes import compare_effects

stats = pytest.importorskip("scipy.stats")


def options(**values):
    return {
        "design": "paired",
        "group": "group",
        "outcome": "value",
        "unit": "unit",
        "confidence": 0.95,
        "contrasts": [["A", "B"]],
        "assumptions_confirmed": True,
        **values,
    }


def long_csv(left, right):
    lines = ["group,value,unit"]
    for group, values in (("A", left), ("B", right)):
        lines += [f"{group},{value},{index}" for index, value in enumerate(values)]
    return ("\n".join(lines) + "\n").encode()


def test_paired_sleep_published_interval():
    a = [0.7, -1.6, -0.2, -1.2, -0.1, 3.4, 3.7, 0.8, 0, 2]
    b = [1.9, 0.8, 1.1, 0.1, -0.1, 4.4, 5.5, 1.6, 4.6, 3.4]
    report = compare_effects(long_csv(a, b), options())
    (row,) = report["comparisons"]
    assert row["status"] == "estimated"
    d = row["standardized"]
    assert [d["estimate"], *d["interval"]] == pytest.approx([-1.28, -2.12, -0.41], abs=0.005)
    native = stats.ttest_rel(a, b).confidence_interval()
    assert row["raw"]["interval"] == pytest.approx([native.low, native.high], abs=1e-12)
    assert not d["approximate"] and not report["assumptions_verified"]


@pytest.mark.parametrize(
    ("design", "expected"),
    [("pooled", [-1.48, -2.27, -0.67]), ("welch", [-1.41, -2.26, -0.53])],
)
def test_published_mtcars_effects_and_native_raw_interval(design, expected):
    mpg = [
        21,
        21,
        22.8,
        21.4,
        18.7,
        18.1,
        14.3,
        24.4,
        22.8,
        19.2,
        17.8,
        16.4,
        17.3,
        15.2,
        10.4,
        10.4,
        14.7,
        32.4,
        30.4,
        33.9,
        21.5,
        15.5,
        15.2,
        13.3,
        19.2,
        27.3,
        26,
        30.4,
        15.8,
        19.7,
        15,
        21.4,
    ]
    manual = {0, 1, 2, 17, 18, 19, 25, 26, 27, 28, 29, 30, 31}
    a, b = (
        [v for i, v in enumerate(mpg) if i not in manual],
        [v for i, v in enumerate(mpg) if i in manual],
    )
    settings = options(design=design, unit=None, rows_are_units=True)
    (row,) = compare_effects(long_csv(a, b), settings)["comparisons"]
    d = row["standardized"]
    assert [d["estimate"], *d["interval"]] == pytest.approx(expected, abs=0.005)
    native = stats.ttest_ind(a, b, equal_var=design == "pooled").confidence_interval()
    assert row["raw"]["interval"] == pytest.approx([native.low, native.high], abs=1e-12)
    assert d["approximate"] == (design == "welch")
    (mirrored,) = compare_effects(long_csv(a, b), settings | {"contrasts": [["B", "A"]]})[
        "comparisons"
    ]
    assert mirrored["standardized"]["interval"] == pytest.approx(
        [-d["interval"][1], -d["interval"][0]]
    )
    (scaled,) = compare_effects(long_csv([v * 1e150 for v in a], [v * 1e150 for v in b]), settings)[
        "comparisons"
    ]
    assert scaled["standardized"]["interval"] == pytest.approx(d["interval"])


LINEAGE = (
    b'unit,group,value,note\n01,A,1,"first\nrecord"\n01,A,3,repeat\n1,A,5,ok\n'
    b"01,B,0,ok\n1,B,2,ok\n02,A,10,unmatched\n03,B,inf,nonfinite\n,A,2,missing id\n"
    b"11,C,0,outside\n1,,2,missing group\n08,A,,missing\n09,B,broken,invalid\n"
)


def test_quoted_records_repeats_and_pair_exclusions_account_for_every_record():
    report = compare_effects(LINEAGE, options(reduction="mean", contrasts=[["A", "B"], ["B", "A"]]))
    assert report["source"]["sha256"] == hashlib.sha256(LINEAGE).hexdigest()
    assert report["source"]["records"] == 12
    row, reverse = report["comparisons"]
    assert row["raw"]["estimate"] == pytest.approx(2.5)
    assert reverse["raw"]["estimate"] == pytest.approx(-2.5)
    assert row["provenance"] == {
        "left_units": [[1, 2], [3]],
        "right_units": [[4], [5]],
        "excluded": {
            "unmatched_pair": [6],
            "nonfinite_measurement": [7],
            "missing_unit": [8],
            "outside_selected_groups": [9],
            "missing_group": [10],
            "missing_measurement": [11],
            "invalid_measurement": [12],
        },
    }


def test_partial_intervals_do_not_invent_variability_or_drop_lineage():
    report = compare_effects(long_csv([2, 4], [1, 3]), options())
    (row,) = report["comparisons"]
    assert report["exit_code"] == 2 and row["status"] == "partial"
    assert row["raw"]["estimate"] == 1 and row["raw"]["interval"] is None
    assert row["standardized"]["estimate"] is None
    assert row["provenance"]["left_units"] == [[1], [2]]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"reduction": "refuse"}, "repeated"),
        ({"unit": None, "rows_are_units": True}, "matching unit"),
        ({"design": "welch", "reduction": "mean"}, "both independent"),
        ({"assumptions_confirmed": False}, "Confirm"),
        ({"contrasts": [["A", "A"]]}, "different groups"),
        ({"confidence": float("nan")}, "confidence"),
    ],
)
def test_unsafe_or_invalid_choices_refuse(change, message):
    with pytest.raises(ValueError, match=message):
        compare_effects(LINEAGE, options(**({"reduction": "mean"} | change)))


def test_http_profile_and_cli_use_the_same_original_bytes(server, tmp_path, capsys):
    csv = base64.b64encode(LINEAGE).decode()
    route = "/api/effect-sizes"
    request(server, route, {"csv": csv}, token=False, expected=403)
    profile = request(server, route, {"mode": "profile", "group": "group", "csv": csv})
    assert profile["levels"] == ["A", "B", "C"]
    report = request(
        server, route, {"mode": "compare", "csv": csv, "options": options(reduction="mean")}
    )
    file = tmp_path / "original.csv"
    file.write_bytes(LINEAGE)
    assert (
        main(
            [
                "effects",
                str(file),
                "--design",
                "paired",
                "--outcome",
                "value",
                "--group",
                "group",
                "--unit",
                "unit",
                "--reduction",
                "mean",
                "--contrast",
                "A",
                "B",
                "--confirm-assumptions",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out) == report
    assert file.read_bytes() == LINEAGE
