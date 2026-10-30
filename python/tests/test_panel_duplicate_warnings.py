"""Duplicate warnings use prepared source identities within actual panels."""

from __future__ import annotations

import csv
import io
import json
import subprocess
import sys

import pytest

from graphunslopify.transport import local_request


def fixture(kind="line", *, nested=False, duplicate=False, grouped=False):
    rows = []
    for phase in ["early", "late"] if nested else ["early"]:
        for condition in ["A", "B"]:
            for series in ["first", "second"] if grouped else ["first"]:
                for x in [1, 2]:
                    rows.append(
                        {
                            "x": x,
                            "value": x + 1,
                            "condition": condition,
                            "phase": phase,
                            "series": series,
                        }
                    )
    if duplicate:
        rows.append({**rows[0], "value": 2.5})
    spec = {
        "kind": "line" if kind == "line" else "bar",
        "data": {"path": "data.csv"},
        "x": {"field": "x", "label": "Time"},
        "y": {"field": "value", "label": "Value"},
        "aggregation": "none",
        "facet": {"by": "condition", "columns": 2},
        "legend": {"show": False},
        "output": {"stem": "panels", "formats": ["png"], "size": "double_column"},
    }
    if kind == "bar-horizontal":
        spec["orientation"] = "horizontal"
    if nested:
        spec["facet"]["rows"] = "phase"
    # Aliases change visible wording while original panel identities stay stable.
    spec["facet"]["labels"] = (
        [
            {"value": value, "row": phase, "text": f"{phase} {value}"}
            for phase in ["early", "late"]
            for value in ["A", "B"]
        ]
        if nested
        else [{"value": value, "text": f"Condition {value}"} for value in ["A", "B"]]
    )
    if grouped:
        spec["group"] = "series"
    return spec, rows


def rendered(tmp_path, spec, rows, *, ambiguous_bar=False):
    translated = local_request("convert", spec)
    assert translated["ok"], translated
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    original = stream.getvalue().encode()
    data = tmp_path / "data.csv"
    data.write_bytes(original)
    script = tmp_path / "panels.py"
    script.write_text(translated["code"], encoding="utf8")
    run = subprocess.run(
        [sys.executable, str(script), "--strict", "--json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    report = json.loads(run.stdout)
    if ambiguous_bar:
        assert run.returncode == 1 and report["status"] == "failed", report
        assert "runtime_error" in {item["code"] for item in report["findings"]}
    else:
        assert run.returncode == 0 and report["status"] == "passed", report
    assert data.read_bytes() == original
    assert (tmp_path / "panels.png").is_file() != ambiguous_bar
    # Retain the existing advisory log contract, independently of machine findings.
    assert not any(item["code"] == "repeated_x_values" for item in report["findings"])
    return run.stderr, report


@pytest.mark.parametrize("kind", ["line", "bar-vertical", "bar-horizontal"])
@pytest.mark.parametrize("nested", [False, True])
@pytest.mark.parametrize("duplicate", [False, True])
def test_panel_identity_separates_cross_panel_repetition_and_real_duplicates(
    tmp_path, kind, nested, duplicate
):
    spec, rows = fixture(kind, nested=nested, duplicate=duplicate)
    ambiguous_bar = duplicate and kind != "line"
    output, report = rendered(tmp_path, spec, rows, ambiguous_bar=ambiguous_bar)
    assert ("[repeated_x_values]" in output) == duplicate
    if not ambiguous_bar:
        assert len(report["panels"]) == (4 if nested else 2)
    if duplicate:
        assert "correct independent units" in output


@pytest.mark.parametrize("kind", ["line", "bar-vertical", "bar-horizontal"])
@pytest.mark.parametrize("duplicate", [False, True])
def test_series_identity_preserves_real_within_series_duplicates(tmp_path, kind, duplicate):
    spec, rows = fixture(kind, nested=True, grouped=True, duplicate=duplicate)
    ambiguous_bar = duplicate and kind != "line"
    output, report = rendered(tmp_path, spec, rows, ambiguous_bar=ambiguous_bar)
    assert ("[repeated_x_values]" in output) == duplicate
    if not ambiguous_bar:
        assert len(report["panels"]) == 4


@pytest.mark.parametrize("selected", ["A", "B"])
def test_raw_filter_controls_which_duplicates_reach_prepared_panels(tmp_path, selected):
    spec, rows = fixture(duplicate=True)
    spec["filter"] = [{"field": "condition", "op": "eq", "value": selected}]
    spec["facet"]["labels"] = [
        label for label in spec["facet"]["labels"] if label["value"] == selected
    ]
    output, report = rendered(tmp_path, spec, rows)
    assert ("[repeated_x_values]" in output) == (selected == "A")
    assert len(report["panels"]) == 1
    assert report["panels"][0]["name"] == selected


def test_faceting_by_the_series_group_remains_rejected():
    spec, _ = fixture()
    spec["group"] = "condition"
    translated = local_request("convert", spec)
    assert not translated["ok"]
    assert "facet_by_the_group" in {item["code"] for item in translated["findings"]}
