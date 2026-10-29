"""Actual native workbook values, explicit selection and standalone figure evidence."""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pytest

openpyxl = pytest.importorskip("openpyxl")
pytest.importorskip("python_calamine")

from graphunslopify import Figure
from graphunslopify.audit import _input_data, _validate_report
from graphunslopify.cli import main
from graphunslopify.describe import profile
from graphunslopify.errors import SpecError
from graphunslopify.transport import local_request
from graphunslopify.workbook import WorksheetSelectionError, read_excel_table, workbook_sheets


@pytest.fixture
def workbook(tmp_path):
    path = tmp_path / "native.xlsx"
    book = openpyxl.Workbook()
    wrong = book.active
    wrong.title = "Other experiment"
    wrong.append(["subject", "score"])
    wrong.append(["001", 900])
    sheet = book.create_sheet("Selected results")
    sheet.append(["subject", "score", "note"])
    for row in [("001", 7, "a"), ("NA", 11, "b"), ("010", 13, "c")]:
        sheet.append(row)
    book.save(path)
    return path


def specification(path, *, selected=True):
    return {
        "kind": "bar",
        "data": {
            "path": str(path),
            "format": "excel",
            **({"sheet": "Selected results"} if selected else {}),
        },
        "x": {"field": "subject", "label": "Subject"},
        "y": {"field": "score", "label": "Score", "unit": "%"},
        "aggregation": "none",
        "legend": {"show": False},
        "output": {"stem": "native", "formats": ["png", "svg", "pdf"], "dpi": 100},
    }


def test_native_text_numeric_missing_and_dates_are_preserved(tmp_path):
    from datetime import datetime

    path = tmp_path / "typed.xlsx"
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append(["subject", "score", "date"])
    for row in [
        ("001", 7, datetime(2026, 1, 1)),
        ("NA", None, None),
        ("010", 13, None),
        ("formula", "=1+1", None),
    ]:
        sheet.append(row)
    book.save(path)
    raw = path.read_bytes()
    frame = read_excel_table(path)
    assert frame["subject"].tolist() == ["001", "NA", "010", "formula"]
    assert frame["score"].isna().sum() == 2
    result = profile(path)
    assert result["ok"] and result["sheet"] == "Sheet" and result["format"] == "excel"
    score = next(c for c in result["columns"] if c["name"] == "score")
    assert score["mean"] == 10 and score["missing"] == 2 and score["finite"] == 2
    assert next(c for c in result["columns"] if c["name"] == "date")["values"] == [
        "2026-01-01T00:00:00"
    ]
    assert path.read_bytes() == raw
    json.dumps(result, allow_nan=False)


def test_multiple_worksheets_require_explicit_selection(workbook, capsys):
    assert workbook_sheets(workbook) == ["Other experiment", "Selected results"]
    with pytest.raises(WorksheetSelectionError, match="Choose a worksheet"):
        read_excel_table(workbook)
    assert main(["describe", str(workbook)]) == 1
    error = json.loads(capsys.readouterr().out)
    assert not error["ok"] and error["sheets"] == workbook_sheets(workbook)
    assert main(["describe", str(workbook), "--sheet", "Selected results"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["rows"] == 3 and result["sheet"] == "Selected results"
    with pytest.raises(WorksheetSelectionError, match="Unknown worksheet"):
        read_excel_table(workbook, sheet="../../other.xlsx")


def test_sdk_and_ranked_suggestions_retain_the_selected_worksheet(workbook):
    figure = (
        Figure.bar(workbook)
        .worksheet("Selected results")
        .x("subject", "Subject")
        .y("score", "Score")
    )
    assert figure.spec["data"]["format"] == "excel"
    suggested = Figure.from_profile(workbook, sheet="Selected results")
    assert suggested.spec["data"]["sheet"] == "Selected results"
    assert suggested.spec["data"]["format"] == "excel"
    with pytest.raises(SpecError, match="Worksheet selection"):
        Figure.bar("data.csv").worksheet("Sheet")


def test_actual_generated_marks_use_the_chosen_sheet_and_original_identifiers(workbook, tmp_path):
    converted = local_request("convert", specification(workbook))
    assert converted["ok"], converted
    path = tmp_path / "figure.py"
    path.write_text(converted["code"])
    definition = importlib.util.spec_from_file_location("native_workbook_figure", path)
    module = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(module)
    frame = module.prepare(module.load())
    assert frame["subject"].tolist() == ["001", "NA", "010"]
    fig, ax = plt.subplots()
    try:
        module.draw_panel(ax, frame)
        assert [bar.get_height() for bar in ax.patches] == [7, 11, 13]
        assert [tick.get_text() for tick in ax.get_xticklabels()] == ["001", "NA", "010"]
    finally:
        plt.close(fig)
    recorded = _input_data(workbook, "excel", "Selected results")
    assert recorded["rows"] == 3 and recorded["numeric_columns"] == 1
    assert recorded["sha256"] == hashlib.sha256(workbook.read_bytes()).hexdigest()
    assert (
        recorded["numeric_sha256"]
        != _input_data(workbook, "excel", "Other experiment")["numeric_sha256"]
    )


@pytest.mark.parametrize("selected", [True, False])
def test_standalone_runtime_and_strict_missing_sheet_failure(workbook, tmp_path, selected):
    where = tmp_path / "standalone"
    where.mkdir()
    shutil.copyfile(workbook, where / "native.xlsx")
    original = workbook.read_bytes()
    result = local_request("convert", specification("native.xlsx", selected=selected))
    assert result["ok"], result
    path = where / "figure.py"
    path.write_text(result["code"])
    completed = subprocess.run(
        [sys.executable, str(path), "--json", "--report", "report.json"],
        cwd=where,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    report = json.loads((where / "report.json").read_text())
    _validate_report(report)
    if selected:
        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert report["spec"]["data"]["sheet"] == "Selected results"
        assert report["environment"]["installed_optional_versions"][
            "python-calamine"
        ] == importlib.metadata.version("python-calamine")
        assert all((where / f"native.{suffix}").is_file() for suffix in ["png", "svg", "pdf"])
    else:
        assert completed.returncode != 0
        assert "Choose a worksheet" in completed.stdout + completed.stderr
        assert not (where / "native.png").exists()
    assert (where / "native.xlsx").read_bytes() == original


def test_sheet_is_rejected_for_other_formats():
    result = local_request(
        "convert", {**specification("data.csv"), "data": {"path": "data.csv", "sheet": "Results"}}
    )
    assert result["status"] == "invalid_spec"
    assert result["issues"][0]["path"] == "data.sheet"


def test_missing_reader_dependency_has_an_actionable_error(workbook, monkeypatch):
    monkeypatch.setitem(sys.modules, "python_calamine", None)
    result = profile(workbook, sheet="Selected results")
    assert not result["ok"] and "python-calamine" in result["error"]


def test_colliding_native_header_names_are_not_silently_merged(tmp_path):
    path = tmp_path / "collision.xlsx"
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append([1, "1"])
    sheet.append([7, 11])
    book.save(path)
    with pytest.raises(ValueError, match="collide"):
        read_excel_table(path)


def test_genuine_legacy_xls_values_and_generator_parity(tmp_path):
    path = Path(__file__).parent / "fixtures" / "native-values.xls"
    original = path.read_bytes()
    frame = read_excel_table(path)
    assert frame["subject"].tolist() == ["001", "NA", "010"]
    assert frame["score"].tolist() == [7, 11, 13]
    result = profile(path)
    assert result["sheet"] == "Measurements" and result["rows"] == 3
    assert Figure.bar(path).spec["data"]["format"] == "excel"
    spec = specification(path)
    spec["data"]["sheet"] = "Measurements"
    converted = local_request("convert", spec)
    assert converted["ok"], converted
    program = tmp_path / "legacy.py"
    program.write_text(converted["code"], encoding="utf8")
    definition = importlib.util.spec_from_file_location("legacy_excel_reference", program)
    module = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(module)
    actual = module.prepare(module.load())
    assert actual["subject"].tolist() == ["001", "NA", "010"]
    assert actual["score"].tolist() == [7, 11, 13]
    assert path.read_bytes() == original
