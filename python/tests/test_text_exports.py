"""Literal author text must survive real TeX, and disclosure cannot certify data origin."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from graphunslopify.transport import local_request

SPECIAL = r"_&%#${}\^~"
CAPTION = "Caption literal " + SPECIAL + r" \input{sentinel}"
ESCAPED = r"\_\&\%\#\$\{\}\textbackslash{}\textasciicircum{}\textasciitilde{}"


def load_module(path):
    definition = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def exports(tmp_path_factory):
    configured = os.environ.get("GRAPHUNSLOPIFY_LATEX_EVIDENCE")
    if configured:
        folder = Path(configured)
        folder.mkdir(parents=True, exist_ok=False)
    else:
        folder = tmp_path_factory.mktemp("text-exports")
    dataset = folder / "data.csv"
    original = b"x,score\n1,2\n2,6\n"
    dataset.write_bytes(original)
    spec = {
        "kind": "line",
        "data": {"path": str(dataset)},
        "x": {"field": "x", "label": "Step"},
        "y": {"field": "score", "label": "Score"},
        "caption": CAPTION,
        "alt_text": "Author literal " + SPECIAL,
        "output": {"stem": "figure_1", "formats": ["pdf"], "latex": True},
    }
    result = local_request("convert", spec)
    assert result["ok"], result
    script = folder / "figure_1.py"
    script.write_text(result["code"], encoding="utf8")
    completed = subprocess.run(
        [sys.executable, str(script), "--strict", "--json", "--report", "report.json"],
        cwd=folder,
        capture_output=True,
        text=True,
        check=True,
    )
    report = json.loads(completed.stdout)
    assert report["status"] == "passed"
    assert dataset.read_bytes() == original
    table_spec = {
        **spec,
        "kind": "table",
        "title": "Table title" + SPECIAL,
        "data": {"path": str(folder / "table.csv")},
        "group": "method",
        "highlight": "best_per_row",
        "aggregation": "mean",
        "x": {"field": "dataset", "label": "Dataset" + SPECIAL},
        "y": {"field": "score", "label": "Metric" + SPECIAL, "unit": "ms"},
        "uncertainty": {"kind": "range"},
        "output": {"stem": "table_1", "formats": ["pdf"]},
    }
    table = local_request("convert", table_spec)
    assert table["ok"], table
    table_script = folder / "table_1.py"
    table_script.write_text(table["code"], encoding="utf8")
    module = load_module(table_script)
    frame = pd.DataFrame(
        {"dataset": ["Row" + SPECIAL] * 2, "method": ["Method" + SPECIAL] * 2, "score": [2, 6]}
    )
    frame.to_csv(folder / "table.csv", index=False)
    table_input = (folder / "table.csv").read_bytes()
    previous = Path.cwd()
    try:
        os.chdir(folder)
        module.write_table(*module.build_table(module.prepare(module.load())))
    finally:
        os.chdir(previous)
    assert (folder / "table.csv").read_bytes() == table_input
    percent_spec = {
        **table_spec,
        "title": "Percentages" + SPECIAL,
        "data": {"path": str(folder / "percent.csv")},
        "y": {"field": "score", "label": "Accuracy", "unit": "%", "percent": True},
        "output": {"stem": "table_percent", "formats": ["pdf"]},
    }
    converted = local_request("convert", percent_spec)
    assert converted["ok"], converted
    percent_script = folder / "table_percent.py"
    percent_script.write_text(converted["code"], encoding="utf8")
    percent_module = load_module(percent_script)
    frame.assign(score=[0.2, 0.6]).to_csv(folder / "percent.csv", index=False, lineterminator="\n")
    try:
        os.chdir(folder)
        percent_module.write_table(
            *percent_module.build_table(percent_module.prepare(percent_module.load()))
        )
    finally:
        os.chdir(previous)
    return folder, script, report


def test_figure_caption_description_and_metadata_keep_literal_author_text(exports):
    folder, _, report = exports
    text = (folder / "figure_1.tex").read_text()
    assert "Caption literal " + ESCAPED in text
    assert "Author literal " + ESCAPED in text
    assert report["spec"]["caption"] == CAPTION
    assert "Author literal " + SPECIAL in report["alt_text"]


def test_table_headers_rows_and_highlighted_numeric_intervals_are_valid_tex(exports):
    folder, _, _ = exports
    text = (folder / "table_1.tex").read_text()
    assert "Dataset" + ESCAPED in text
    assert "Method" + ESCAPED in text
    assert "Row" + ESCAPED in text
    assert "Table title" + ESCAPED in text and "Metric" + ESCAPED in text
    assert r"\textbf{4.00 [2.00, 6.00]}" in text


def test_disclosure_does_not_certify_where_the_input_data_came_from(exports):
    _, script, _ = exports
    disclosure = load_module(script).DISCLOSURE
    assert "plotting code was generated" in disclosure
    assert "does not establish the origin" in disclosure
    assert "underlying data were not" not in disclosure


def test_real_latex_compilation_preserves_special_characters_and_table_values(exports):
    folder, _, _ = exports
    compiler = shutil.which("pdflatex")
    if compiler is None:
        if os.environ.get("GRAPHUNSLOPIFY_REQUIRE_LATEX"):
            pytest.fail("Required pdflatex executable is missing")
        pytest.skip("Run the render CI TeX gate, or install pdflatex and booktabs")
    (folder / "sentinel.tex").write_text("INJECTED_MARKER", encoding="utf8")
    (folder / "main.tex").write_text(
        r"""\documentclass{article}
\usepackage[T1]{fontenc}
\usepackage{graphicx}
\usepackage{booktabs}
\newcommand{\Description}[1]{\par\noindent #1}
\begin{document}
\input{figure_1.tex}
\clearpage
\input{table_1.tex}
\clearpage
\input{table_percent.tex}
\end{document}
""",
        encoding="utf8",
    )
    completed = subprocess.run(
        [compiler, "-no-shell-escape", "-interaction=nonstopmode", "-halt-on-error", "main.tex"],
        cwd=folder,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout[-5000:]
    from pypdf import PdfReader

    text = "".join(page.extract_text() for page in PdfReader(folder / "main.pdf").pages)
    compact = re.sub(r"\s+", "", text)
    for prefix in (
        "Captionliteral",
        "Authorliteral",
        "Dataset",
        "Method",
        "Row",
        "Tabletitle",
        "Metric",
        "Percentages",
    ):
        assert prefix + SPECIAL in compact, text
    assert "4.00[2.00,6.00]" in compact
    assert "40.00%[20.00%,60.00%]" in compact and "Accuracy(%)" in compact
    assert r"\input{sentinel}" in compact
    assert "INJECTED_MARKER" not in text
    print("Compiled literal-text proof:", folder / "main.pdf")
