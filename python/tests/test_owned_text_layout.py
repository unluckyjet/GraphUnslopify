"""Complete native child/table text must fit without rewriting scientific data."""

import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from pypdf import PdfReader
from test_heading_literal_context import exported_glyph_count
from test_table_context import raw_spec, source_rows

from graphunslopify import read_provenance
from graphunslopify.preview import PreviewState
from graphunslopify.transport import local_request

ROOT = Path(__file__).resolve().parents[2]
INPUTS = json.loads((ROOT / "docs/workspace/owned-text-layout/inputs.json").read_text())
TITLE = "Observed responses across the complete original experimental measurement period"


def signature(axes):
    return [
        (
            ax.get_xscale(),
            ax.get_yscale(),
            tuple(ax.get_xlim()),
            tuple(ax.get_ylim()),
            [
                (np.asarray(line.get_xdata()).tolist(), np.asarray(line.get_ydata()).tolist())
                for line in ax.lines
            ],
        )
        for ax in axes
    ]


def render(folder, monkeypatch, raw, csv):
    original = csv.encode()
    (folder / "data.csv").write_bytes(original)
    raw = copy.deepcopy(raw)
    raw["data"]["path"] = "data.csv"
    raw["output"].update(stem="owned", formats=["png", "svg", "pdf"], dpi=150)
    converted = local_request("convert", raw)
    assert converted["ok"], converted
    path = folder / "plot.py"
    path.write_text(converted["code"])
    done = subprocess.run(
        [sys.executable, str(path), "--strict", "--json"],
        cwd=folder,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    report = json.loads(done.stdout)
    definition = importlib.util.spec_from_file_location("owned_text", path)
    module = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(module)
    observation = {}
    if raw["kind"] == "sparkline_grid":
        original_fit = module.fit_sparkline_layout

        def observe(fig, axes):
            fig.canvas.draw()
            children = [
                child
                for ax in axes
                for child in ax.child_axes
                if hasattr(child, "_graphunslopify_sparkline_cell")
            ]
            before = signature(children)
            heights = [child.bbox.height / fig.dpi for child in children]
            texts = [
                (
                    child.title.get_text(),
                    copy.deepcopy(child.title._graphunslopify_text_target),
                    child.title.get_fontproperties().copy(),
                    child.title.get_parse_math(),
                    child.title.get_usetex(),
                )
                for child in children
            ]
            result = original_fit(fig, axes)
            fig.canvas.draw()
            assert signature(children) == before
            for child, minimum, (text, target, font, parse, tex) in zip(
                children, heights, texts, strict=True
            ):
                assert child.bbox.height / fig.dpi >= minimum - 1 / fig.dpi
                assert child.title.get_text().split() == text.split()
                assert child.title._graphunslopify_text_target == target
                assert child.title.get_fontproperties() == font
                assert child.title.get_parse_math() == parse and child.title.get_usetex() == tex
            observation["children"] = children
            return result

        module.fit_sparkline_layout = observe
    else:
        original_fit = module.fit_table_layout

        def observe(fig, ax, drawn, context):
            before = {
                key: (cell.get_text().get_text(), cell.get_text().get_fontproperties().copy())
                for key, cell in drawn.get_celld().items()
            }
            captions = [text.get_text() for text in context]
            result = original_fit(fig, ax, drawn, context)
            for key, cell in drawn.get_celld().items():
                original_text, font = before[key]
                assert cell.get_text().get_fontproperties() == font
                assert not cell.get_text().get_parse_math() and not cell.get_text().get_usetex()
                if key[0] > 0 and key[1] >= 0:
                    assert cell.get_text().get_text() == original_text
                else:
                    assert cell.get_text().get_text().split() == original_text.split()
            assert [text.get_text().split() for text in context] == [
                text.split() for text in captions
            ]
            observation["table"] = drawn
            return result

        module.fit_table_layout = observe
    monkeypatch.chdir(folder)
    with patch.object(plt, "close"), contextlib.redirect_stdout(io.StringIO()):
        module.main()
    fig = plt.gcf()
    fig.canvas.draw()
    assert (folder / "data.csv").read_bytes() == original
    assert report["data"]["sha256_prefix"] == hashlib.sha256(original).hexdigest()[:16]
    for fmt in ["png", "svg", "pdf"]:
        provenance = read_provenance(folder / f"owned.{fmt}")
        assert provenance["spec"].get("title") == raw.get("title")
        assert provenance["spec"]["y"]["label"] == raw["y"]["label"]
    return done, report, fig, module, observation


@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close("all")


@pytest.mark.parametrize(
    "context", ["original", "single", "one-column", "direct", "nested", "headings"]
)
def test_complete_original_sparkline_words_have_native_space_and_unchanged_marks(
    tmp_path, monkeypatch, context
):
    raw = copy.deepcopy(INPUTS["sparkline"]["spec"])
    csv = INPUTS["sparkline"]["csv"]
    if context == "single":
        raw.pop("facet")
        data = pd.read_csv(io.StringIO(csv), dtype={"method": str, "site": str})
        csv = data[data.site == "second"].to_csv(index=False, lineterminator="\n")
        raw["output"]["size"] = "single_column"
    elif context == "one-column":
        raw["columns"] = 1
    elif context == "direct":
        raw["legend"]["style"] = "direct"
    elif context == "nested":
        data = pd.read_csv(io.StringIO(csv), dtype={"method": str, "site": str})
        data = pd.concat([data.assign(batch="A"), data.assign(batch="B")], ignore_index=True)
        csv = data.to_csv(index=False, lineterminator="\n")
        raw["facet"]["rows"] = "batch"
    elif context == "headings":
        raw["title"] = TITLE
        raw["facet"]["labels"] = [
            {
                "value": value,
                "text": "Original treatment cohort followed across the complete observation period "
                + value,
            }
            for value in ["first", "second"]
        ]
    done, report, fig, module, observation = render(tmp_path, monkeypatch, raw, csv)
    assert done.returncode == 0 and report["status"] == "passed", report
    renderer = fig.canvas.get_renderer()
    titles = [child.title.get_window_extent(renderer) for child in observation["children"]]
    assert all(not a.overlaps(b) for i, a in enumerate(titles) for b in titles[i + 1 :])
    assert report["inspection"]["measurements"]["text_scale"] >= 0.99
    before = [child.bbox.bounds for child in observation["children"]]
    with plt.rc_context(module.RC_PARAMS):
        module.fit_sparkline_layout(fig, fig.axes)
    np.testing.assert_allclose(
        [child.bbox.bounds for child in observation["children"]], before, rtol=0, atol=1
    )


@pytest.mark.parametrize("grouped", [False, True])
def test_original_long_table_context_headers_and_quantities_fit(tmp_path, monkeypatch, grouped):
    source = next(
        item
        for item in INPUTS["tables"]
        if item["name"] == ("grouped-table" if grouped else "ungrouped-table")
    )
    done, report, fig, module, observation = render(
        tmp_path, monkeypatch, source["spec"], source["csv"]
    )
    assert done.returncode == 0 and report["status"] == "passed", report
    assert report["inspection"]["measurements"]["text_scale"] >= 0.99
    table = observation["table"]
    assert table[1, 0].get_text().get_text() == "0.60"
    assert table[2, 0].get_text().get_text() == "0.70"
    assert source["spec"]["title"] in (tmp_path / "owned.md").read_text()
    assert (
        module.latex_text(source["spec"]["y"]["label"] + " (fraction)")
        in (tmp_path / "owned.tex").read_text()
    )
    renderer = fig.canvas.get_renderer()
    assert all(
        text.get_window_extent(renderer).y0 > table.get_window_extent(renderer).y1
        for text in fig.texts
    )


@pytest.mark.parametrize("grouped", [False, True])
@pytest.mark.parametrize("percent", [False, True])
@pytest.mark.parametrize("interval", [False, True])
def test_long_table_names_keep_independent_mean_units_and_intervals(
    tmp_path, monkeypatch, grouped, percent, interval
):
    raw = raw_spec(tmp_path, grouped=grouped, percent=percent, interval=interval, title=TITLE)
    raw["y"]["label"] = (
        "Observed response across the complete original experimental measurement period"
    )
    raw["output"]["size"] = "single_column"
    data = source_rows(grouped)
    data["dataset"] = data.dataset.map(
        {
            "A": "Original experimental cohort observed across the complete first follow-up",
            "B": "Independent experimental cohort observed across the complete second follow-up",
        }
    )
    if grouped:
        data["method"] = data.method.map(
            {
                "Base": "Original reference treatment condition",
                "Ours": "Modified alternative treatment condition",
            }
        )
    done, report, _, module, observation = render(
        tmp_path, monkeypatch, raw, data.to_csv(index=False, lineterminator="\n")
    )
    assert done.returncode == 0 and report["status"] == "passed", report
    expected = "60.00%" if percent else "0.60"
    if interval:
        expected += " [50.00%, 70.00%]" if percent else " [0.50, 0.70]"
    # Group ordering can differ, but the original reference quantity remains exact.
    body = [
        cell.get_text().get_text()
        for (row, column), cell in observation["table"].get_celld().items()
        if row > 0 and column >= 0
    ]
    assert expected in body
    assert expected in (tmp_path / "owned.md").read_text()
    assert module.latex_text(expected) in (tmp_path / "owned.tex").read_text()


@pytest.mark.parametrize("kind", ["sparkline_grid", "table"])
def test_unbreakable_original_words_remain_failed_and_complete(tmp_path, monkeypatch, kind):
    if kind == "table":
        source = INPUTS["tables"][0]
        raw, csv = copy.deepcopy(source["spec"]), source["csv"]
        raw["title"] = "OriginalSourceIdentifier" * 30
    else:
        source = INPUTS["sparkline"]
        raw, csv = copy.deepcopy(source["spec"]), source["csv"]
        raw["legend"]["labels"] = [
            {"series": raw["series_order"][0], "text": "OriginalSourceIdentifier" * 30}
        ]
    done, report, _, _, _ = render(tmp_path, monkeypatch, raw, csv)
    assert done.returncode == 2 and report["status"] == "failed"
    assert any(f["code"] == "text_too_small" for f in report["findings"])


def test_wrapped_child_preview_keeps_raw_identity_and_full_canonical_wording(tmp_path):
    source = INPUTS["sparkline"]
    state = PreviewState(tmp_path, 1024 * 1024)
    csv = source["csv"].encode()
    upload = state.upload("original.csv", csv)
    result = state.render(
        {
            "client": "child-heading",
            "generation": 1,
            "data_id": upload["id"],
            "spec": source["spec"],
        }
    )
    assert result["report"]["status"] == "passed", result["report"]
    entries = [
        target for target in result["edit_map"]["targets"] if target["role"] == "legend_entry"
    ]
    assert len(entries) == 3 and all(entry["editable"] for entry in entries)
    assert all(entry["text"].split() == entry["source"].split() for entry in entries)
    assert all(entry["path"] == ["legend", "labels", 0, "text"] for entry in entries)
    assert result["report"]["data"]["sha256_prefix"] == hashlib.sha256(csv).hexdigest()[:16]


@pytest.mark.parametrize("kind", ["sparkline_grid", "table"])
def test_complete_currency_context_keeps_actual_exported_dollar_glyphs(tmp_path, monkeypatch, kind):
    words = "Observed costs of $1 and $2 with $3 retained across the original measurement period"
    formula = r"Original coefficient $\alpha$ remains explicit"
    if kind == "table":
        source = INPUTS["tables"][0]
        raw, csv = copy.deepcopy(source["spec"]), source["csv"]
        raw["title"] = words + "\n" + formula
        expected = 5
    else:
        source = INPUTS["sparkline"]
        raw, csv = copy.deepcopy(source["spec"]), source["csv"]
        raw["legend"]["labels"] = [
            {"series": raw["series_order"][0], "text": words + "\n" + formula}
        ]
        expected = 3
    done, report, _, module, _ = render(tmp_path, monkeypatch, raw, csv)
    assert done.returncode == 0 and report["status"] == "passed", report
    svg = ET.parse(tmp_path / "owned.svg").getroot()
    assert exported_glyph_count(svg, "$", module.RC_PARAMS) == expected
    if kind == "sparkline_grid":
        assert exported_glyph_count(svg, "\N{GREEK SMALL LETTER ALPHA}", module.RC_PARAMS) == 1
    else:
        text = " ".join(
            " ".join(
                page.extract_text() for page in PdfReader(tmp_path / "owned.pdf").pages
            ).split()
        )
        assert formula in text


@pytest.mark.parametrize("kind", ["sparkline_grid", "table"])
def test_fitting_preserves_false_comparison_claim_failures(tmp_path, monkeypatch, kind):
    if kind == "table":
        source = next(item for item in INPUTS["tables"] if item["name"] == "grouped-table")
        raw, csv = copy.deepcopy(source["spec"]), source["csv"]
        subject, reference = "Base", "Ours"
    else:
        source = INPUTS["sparkline"]
        raw = copy.deepcopy(source["spec"])
        data = pd.read_csv(io.StringIO(source["csv"]))
        csv = data[data.site == "second"].to_csv(index=False, lineterminator="\n")
        raw.pop("facet")
        subject, reference = raw["series_order"][1], raw["series_order"][0]
    raw["claims"] = [{"kind": "beats_everywhere", "subject": subject, "reference": reference}]
    done, report, _, _, _ = render(tmp_path, monkeypatch, raw, csv)
    assert done.returncode == 2 and report["status"] == "failed"
    assert any(claim["verdict"] == "fails" for claim in report["claims"])


def test_constrained_many_column_table_keeps_all_values_and_fails_font_floor(tmp_path, monkeypatch):
    raw = raw_spec(tmp_path, interval=True, title=TITLE)
    raw["output"]["size"] = "single_column"
    data = pd.DataFrame(
        [
            {"dataset": dataset, "method": f"M{method}", "score": value}
            for dataset in ["A", "B"]
            for method in range(12)
            for value in [0.4, 0.6]
        ]
    )
    done, report, _, _, observation = render(
        tmp_path, monkeypatch, raw, data.to_csv(index=False, lineterminator="\n")
    )
    assert done.returncode == 2 and report["status"] == "failed"
    assert any(f["code"] == "text_too_small" for f in report["findings"])
    cells = observation["table"].get_celld()
    assert {
        cell.get_text().get_text()
        for (row, column), cell in cells.items()
        if row == 0 and column >= 0
    } == {f"M{method}" for method in range(12)}
    assert (
        sum(
            cell.get_text().get_text() == "0.50 [0.40, 0.60]"
            for (row, column), cell in cells.items()
            if row > 0 and column >= 0
        )
        == 24
    )


def test_other_inset_axes_are_not_mistaken_for_owned_sparkline_cells(tmp_path, monkeypatch):
    raw = copy.deepcopy(INPUTS["sparkline"]["spec"])
    raw["inset"] = {"x": [1.2, 1.8], "y": [1.2, 2.8], "corner": "upper_right", "size": 0.35}
    done, report, fig, _, observation = render(
        tmp_path, monkeypatch, raw, INPUTS["sparkline"]["csv"]
    )
    assert done.returncode in (0, 2), report
    assert not any(f["code"] == "runtime_error" for f in report["findings"])
    foreign = [
        child
        for ax in fig.axes
        for child in ax.child_axes
        if not hasattr(child, "_graphunslopify_sparkline_cell")
    ]
    assert len(foreign) == 2
    assert all(child.child_axes for child in foreign)
    assert len(observation["children"]) == 3
