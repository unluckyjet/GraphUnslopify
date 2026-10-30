"""Visible table context, literal encodings and independent display quantities."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from pypdf import PdfReader

from graphunslopify import read_provenance
from graphunslopify.transport import local_request

SPECIAL = r"_%&#$\{}~^"


def raw_spec(folder, *, grouped=True, percent=False, interval=False, **extra):
    return {
        "kind": "table",
        "title": "Quality overview",
        "x": {"field": "dataset", "label": "Dataset"},
        "y": {
            "field": "score",
            "label": "Accuracy",
            "unit": "%" if percent else "fraction",
            "percent": percent,
        },
        **({"group": "method"} if grouped else {}),
        **({"uncertainty": {"kind": "sem"}} if interval else {}),
        "data": {"path": str(folder / "data.csv")},
        "output": {
            "stem": "table",
            "formats": ["png", "svg", "pdf"],
            "size": "double_column",
            "dpi": 150,
        },
        **extra,
    }


def source_rows(grouped=True):
    frame = pd.DataFrame(
        [
            {"dataset": dataset, "method": method, "score": value}
            for dataset, baseline in [("A", 0.6), ("B", 0.7)]
            for method, centre in [("Base", baseline), ("Ours", baseline + 0.2)]
            for value in [centre - 0.1, centre + 0.1]
        ]
    )
    return frame if grouped else frame[frame.method == "Base"].drop(columns="method")


def generated(folder, raw):
    result = local_request("convert", raw)
    assert result["ok"], result
    path = folder / "table_plot.py"
    path.write_text(result["code"], encoding="utf8")
    definition = importlib.util.spec_from_file_location("table_reference", path)
    module = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(module)
    return module


def table_texts(fig):
    return [
        cell.get_text()
        for ax in fig.axes
        for table in ax.tables
        for cell in table.get_celld().values()
    ]


@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close("all")


@pytest.mark.parametrize("grouped", [False, True])
@pytest.mark.parametrize("percent", [False, True])
@pytest.mark.parametrize("interval", [False, True])
def test_visible_context_and_numeric_strings_agree_across_all_table_exports(
    tmp_path, monkeypatch, grouped, percent, interval
):
    module = generated(
        tmp_path, raw_spec(tmp_path, grouped=grouped, percent=percent, interval=interval)
    )
    data = source_rows(grouped)
    data.to_csv(tmp_path / "data.csv", index=False, lineterminator="\n")
    original = (tmp_path / "data.csv").read_bytes()
    prepared = module.prepare(data)
    table, low, high = module.build_table(prepared)
    np.testing.assert_allclose(
        table.to_numpy(),
        [[0.6, 0.8], [0.7, 0.9]] if grouped else [[0.6], [0.7]],
        rtol=0,
        atol=1e-12,
    )
    expected = "60.00%" if percent else "0.60"
    if interval:
        expected += " [50.00%, 70.00%]" if percent else " [0.50, 0.70]"
    assert module.table_cell(table, low, high, table.index[0], table.columns[0]) == expected
    before = table.copy(deep=True)
    captured = []
    close = plt.close
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(plt, "close", captured.append)
    try:
        module.main()
        fig = captured[-1]
        texts = table_texts(fig) + list(fig.texts)
        visible = [text.get_text() for text in texts if text.get_visible()]
        assert {"Quality overview", "Dataset", module.Y_AXIS_LABEL, expected}.issubset(set(visible))
        for ax in fig.axes:
            for artist in ax.tables:
                assert artist[0, -1].get_text().get_text() == "Dataset"
                if not grouped:
                    assert artist[0, 0].get_text().get_text() == module.Y_AXIS_LABEL
                renderer = fig.canvas.get_renderer()
                body_box = artist.get_window_extent(renderer)
                for label in fig.texts:
                    assert label.get_window_extent(renderer).y0 > body_box.y1
        assert module.RUN_REPORT["inspection"]["checked"]
        assert not [f for f in module.RUN_REPORT["findings"] if f["severity"] == "error"]
    finally:
        for fig in captured:
            close(fig)
    pd.testing.assert_frame_equal(before, table)
    assert (tmp_path / "data.csv").read_bytes() == original
    markdown = (tmp_path / "table.md").read_text()
    tex = (tmp_path / "table.tex").read_text()
    for text in ["Quality overview", "Dataset", module.Y_AXIS_LABEL, expected]:
        assert text in markdown
        assert module.latex_text(text) in tex
    pdf_text = "\n".join(page.extract_text() for page in PdfReader(tmp_path / "table.pdf").pages)
    assert "Quality overview" in pdf_text and "Dataset" in pdf_text and "Accuracy" in pdf_text
    assert expected in pdf_text
    description = read_provenance(tmp_path / "table.pdf")["alt_text"]
    assert description == module.ALT_TEXT
    assert "shaded" not in description.lower() and "error bars" not in description.lower()
    assert ("60.00%" if percent else "0.60") in description


def test_optional_title_is_not_fabricated_and_metric_context_remains(tmp_path, monkeypatch):
    raw = raw_spec(tmp_path)
    raw.pop("title")
    module = generated(tmp_path, raw)
    source_rows().to_csv(tmp_path / "data.csv", index=False, lineterminator="\n")
    monkeypatch.chdir(tmp_path)
    module.main()
    markdown = (tmp_path / "table.md").read_text()
    assert "Accuracy (fraction)" in markdown and "untitled" not in markdown.lower()


def test_literal_table_context_and_labels_are_not_interpreted_as_math_or_tex(tmp_path, monkeypatch):
    raw = raw_spec(
        tmp_path,
        x={"field": "dataset", "label": "Dataset" + SPECIAL},
        y={"field": "score", "label": "Metric" + SPECIAL, "unit": "ms"},
        title="Title" + SPECIAL,
    )
    module = generated(tmp_path, raw)
    frame = pd.DataFrame(
        {"dataset": ["Row" + SPECIAL] * 2, "method": ["Method" + SPECIAL] * 2, "score": [2, 6]}
    )
    frame.to_csv(tmp_path / "data.csv", index=False, lineterminator="\n")
    captured = []
    close = plt.close
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(plt, "close", captured.append)
    try:
        module.main()
        texts = table_texts(captured[-1]) + list(captured[-1].texts)
        for text in texts:
            assert not text.get_parse_math() and not text.get_usetex()
        assert {
            "Title" + SPECIAL,
            "Dataset" + SPECIAL,
            module.Y_AXIS_LABEL,
            "Row" + SPECIAL,
            "Method" + SPECIAL,
        }.issubset({t.get_text() for t in texts})
    finally:
        for fig in captured:
            close(fig)
    tex = (tmp_path / "table.tex").read_text()
    for text in ["Title" + SPECIAL, "Dataset" + SPECIAL, module.Y_AXIS_LABEL]:
        assert module.latex_text(text) in tex
    pdf_text = "\n".join(p.extract_text() for p in PdfReader(tmp_path / "table.pdf").pages)
    assert "Title" + SPECIAL in pdf_text and "Metric" + SPECIAL in pdf_text


def test_markdown_context_and_headers_escape_literal_pipes_markup_and_html(tmp_path, monkeypatch):
    raw = raw_spec(
        tmp_path,
        title="A <b>literal</b> title",
        x={"field": "dataset", "label": "Data|set"},
        y={"field": "score", "label": "A_*[x]`$ metric", "unit": "ms"},
    )
    module = generated(tmp_path, raw)
    frame = source_rows().assign(dataset="Row|name", method="Method*name")
    frame.to_csv(tmp_path / "data.csv", index=False, lineterminator="\n")
    monkeypatch.chdir(tmp_path)
    module.main()
    markdown = (tmp_path / "table.md").read_text()
    assert "Data\\|set" in markdown and "Row\\|name" in markdown
    assert "Method\\*name" in markdown and "A\\_\\*\\[x\\]\\`\\$ metric" in markdown
    assert "&lt;b&gt;literal&lt;/b&gt;" in markdown and "<b>literal</b>" not in markdown


def test_missing_cells_stay_missing_and_singleton_intervals_stay_unavailable(tmp_path, monkeypatch):
    module = generated(tmp_path, raw_spec(tmp_path, percent=True, interval=True))
    frame = pd.DataFrame({"dataset": ["A", "B"], "method": ["Base", "Ours"], "score": [0.6, 0.9]})
    frame.to_csv(tmp_path / "data.csv", index=False, lineterminator="\n")
    table, low, high = module.build_table(module.prepare(frame))
    assert module.table_cell(table, low, high, "A", "Ours") == "-"
    assert module.table_cell(table, low, high, "A", "Base") == "60.00% [unavailable]"
    monkeypatch.chdir(tmp_path)
    module.main()
    assert "60.00% [unavailable]" in (tmp_path / "table.md").read_text()
    assert np.isnan(low.loc["A", "Base"]) and np.isnan(high.loc["A", "Base"])


@pytest.mark.parametrize(
    ("extra", "code"),
    [
        ({"x": {"field": "dataset", "label": "Dataset", "scale": "log"}}, "unsupported_table_axes"),
        (
            {"x": {"field": "dataset", "label": "Dataset", "percent": True}},
            "unsupported_table_axes",
        ),
        (
            {"x": {"field": "dataset", "label": "Dataset", "limits": [0, 10]}},
            "unsupported_table_axes",
        ),
        (
            {"x": {"field": "dataset", "label": "Dataset", "temporal": True}},
            "unsupported_table_axes",
        ),
        ({"y": {"field": "score", "label": "Score", "scale": "log"}}, "unsupported_table_axes"),
        ({"y": {"field": "score", "label": "Score", "limits": [0, 1]}}, "unsupported_table_axes"),
        ({"y": {"field": "score", "label": "Score", "temporal": True}}, "unsupported_table_axes"),
        (
            {"annotate": [{"at": "max", "series": "Ours", "text": "Peak"}]},
            "table_composition_unsupported",
        ),
        (
            {
                "reference_lines": [
                    {"axis": "y", "value": 0.5, "meaning": "other", "label": "Target"}
                ]
            },
            "table_composition_unsupported",
        ),
        ({"emphasis": {"series": "Ours"}}, "table_composition_unsupported"),
    ],
)
def test_non_table_context_options_are_refused_instead_of_described_or_ignored(
    tmp_path, extra, code
):
    result = local_request("convert", raw_spec(tmp_path, **extra))
    assert not result["ok"], result
    assert any(f["code"] == code and f["severity"] == "error" for f in result["findings"])


def test_complete_wide_context_wraps_without_hiding_headers_or_shrinking_text(tmp_path):
    title = "An intentionally oversized table title " * 12
    module = generated(tmp_path, raw_spec(tmp_path, title=title))
    source_rows().to_csv(tmp_path / "data.csv", index=False, lineterminator="\n")
    result = subprocess.run(
        [sys.executable, module.__file__, "--strict", "--json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    report = json.loads(result.stdout)
    assert result.returncode == 0 and report["status"] == "passed", result.stderr
    assert report["inspection"]["measurements"]["text_scale"] >= 0.99
    assert read_provenance(tmp_path / "table.png")["spec"]["title"] == title
    pdf_text = "\n".join(page.extract_text() for page in PdfReader(tmp_path / "table.pdf").pages)
    assert " ".join(title.split()) in " ".join(pdf_text.split())
    assert "Dataset" in pdf_text and "Base" in pdf_text and "Ours" in pdf_text
    assert (
        len(report["outputs"]) == 5 and report["inspection"]["measurements"]["basis"] == "exports"
    )


def test_percent_formatting_does_not_change_numeric_estimates_or_interval_highlights(tmp_path):
    raw = raw_spec(
        tmp_path,
        percent=True,
        interval=True,
        highlight="best_per_row",
        uncertainty={"kind": "range"},
    )
    module = generated(tmp_path, raw)
    frame = pd.DataFrame(
        {
            "dataset": ["A"] * 4,
            "method": ["Base", "Base", "Ours", "Ours"],
            "score": [0.2, 0.3, 0.8, 0.9],
        }
    )
    table, low, high = module.build_table(module.prepare(frame))
    assert module.mark_winners(table, low, high) == {("A", "Ours")}
    assert table.loc["A", "Ours"] == pytest.approx(0.85)
    assert module.table_cell(table, low, high, "A", "Ours") == "85.00% [80.00%, 90.00%]"


def test_published_table_has_committed_inputs_current_provenance_and_visible_context():
    root = Path(__file__).resolve().parents[2]
    folder = root / "examples/references"
    raw = json.loads((folder / "table.figure.json").read_text())
    translated = local_request("convert", raw)
    assert translated["ok"], translated
    payload = (folder / "table.csv").read_bytes()
    assert b"\r" not in payload
    evidence = read_provenance(root / "docs/fifth-pass-table.png")
    assert evidence["data_sha256_prefix"] == hashlib.sha256(payload).hexdigest()[:16]
    assert (
        evidence["script_sha256"] == hashlib.sha256(translated["code"].encode("utf8")).hexdigest()
    )
    assert "percentages" in evidence["alt_text"] and "shaded" not in evidence["alt_text"].lower()


@pytest.mark.parametrize(("level", "percentage"), [(0.95, "95"), (0.955, "95.5"), (0.999, "99.9")])
def test_confidence_context_preserves_the_requested_level_without_rounding_to_100(
    tmp_path, level, percentage
):
    module = generated(tmp_path, raw_spec(tmp_path, uncertainty={"kind": "ci", "level": level}))
    assert f"{percentage}% bootstrap confidence intervals" in " ".join(module.table_context())
    assert f"{percentage} percent confidence intervals" in module.ENCODING_SENTENCE
