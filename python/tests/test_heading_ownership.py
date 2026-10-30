"""Owned figure headings retain their place, canonical identity and observations."""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
from unittest.mock import patch

import matplotlib.pyplot as plt
import numpy as np
import pytest
from matplotlib.text import Text

from graphunslopify import read_provenance
from graphunslopify.preview import PreviewState
from graphunslopify.transport import local_request

SHORT = "Observed responses"
LONG = "Observed responses across the complete original experimental measurement period"
MIXED = r"Measured response $\alpha + \beta$" + "\nNominal price $15 per original observation"
PANEL = "Original treatment cohort followed across the complete observation period"
CSV = b"epoch,value,condition\n1,1,A\n2,2,A\n3,3,A\n4,70,A\n5,80,A\n6,90,A\n"


def request(context, title=LONG, letters=True):
    spec = {
        "kind": "line",
        "x": {"field": "epoch", "label": "Epoch"},
        "y": {"field": "value", "label": "Response"},
        "legend": {"show": False},
        "data": {"path": "data.csv"},
        "output": {
            "size": "single_column",
            "formats": ["png", "svg", "pdf"],
            "dpi": 150,
            "stem": "context",
        },
    }
    if title is not None:
        spec["title"] = title
    if context == "facet":
        spec["facet"] = {
            "by": "condition",
            "panel_letters": letters,
            "labels": [{"value": "A", "text": PANEL}],
        }
    else:
        spec["axis_break"] = {"axis": "y", "from": 20, "to": 60}
    return spec


def render(folder, monkeypatch, spec):
    (folder / "data.csv").write_bytes(CSV)
    converted = local_request("convert", spec)
    assert converted["ok"], converted
    path = folder / "plot.py"
    path.write_text(converted["code"])
    completed = subprocess.run(
        [sys.executable, str(path), "--strict", "--json"],
        cwd=folder,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    report = json.loads(completed.stdout)
    definition = importlib.util.spec_from_file_location("heading_ownership", path)
    module = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(module)
    monkeypatch.chdir(folder)
    with patch.object(plt, "close"), contextlib.redirect_stdout(io.StringIO()):
        module.main()
    fig = plt.gcf()
    fig.canvas.draw()
    assert (folder / "data.csv").read_bytes() == CSV
    assert report["data"]["sha256_prefix"] == hashlib.sha256(CSV).hexdigest()[:16]
    assert report["data"]["counts"]["read"] == 6
    for fmt in ["png", "svg", "pdf"]:
        output = folder / f"context.{fmt}"
        assert output.stat().st_size > 100
        assert read_provenance(output)["spec"].get("title") == spec.get("title")
    return completed, report, fig, module


def owned(fig, role):
    return [
        text
        for text in fig.findobj(Text)
        if text.get_visible()
        and text.get_text()
        and getattr(text, "_graphunslopify_text_target", {}).get("role") == role
    ]


@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close("all")


@pytest.mark.parametrize("title", [SHORT, LONG, MIXED])
@pytest.mark.parametrize("letters", [False, True])
def test_single_facet_keeps_global_and_panel_headings_separate(
    tmp_path, monkeypatch, title, letters
):
    spec = request("facet", title, letters)
    completed, report, fig, _ = render(tmp_path, monkeypatch, spec)
    assert completed.returncode == 0 and report["status"] == "passed", report
    headings, panels = owned(fig, "title"), owned(fig, "panel_title")
    assert len(headings) == len(panels) == 1
    heading, panel = headings[0], panels[0]
    assert heading in fig.texts
    assert heading.get_text().split() == title.split()
    assert heading._graphunslopify_text_target["path"] == ["title"]
    assert panel._graphunslopify_text_target["source"] == {"value": "A"}
    assert panel._graphunslopify_text_target["value"] == PANEL
    expected = "(a) " + PANEL if letters else PANEL
    assert panel.get_text().split() == expected.split()
    renderer = fig.canvas.get_renderer()
    assert not heading.get_window_extent(renderer).overlaps(panel.get_window_extent(renderer))
    np.testing.assert_array_equal(fig.axes[0].lines[0].get_ydata(), [1, 2, 3, 70, 80, 90])
    assert fig.axes[0].bbox.height / fig.dpi >= 1.5


@pytest.mark.parametrize("title", [None, SHORT, LONG, MIXED])
def test_broken_axis_keeps_title_gap_and_original_data_area(tmp_path, monkeypatch, title):
    spec = request("break", title)
    completed, report, fig, module = render(tmp_path, monkeypatch, spec)
    assert completed.returncode == 0 and report["status"] == "passed", report
    headings = owned(fig, "title")
    assert len(headings) == (0 if title is None else 1)
    if title is not None:
        assert headings[0].get_text().split() == title.split()
        assert headings[0]._graphunslopify_text_target["path"] == ["title"]
    upper, lower = fig.axes
    assert lower.get_ylim()[1] == 20 and upper.get_ylim()[0] == 60
    assert upper.get_label() == lower.get_label() == "<axis-break>"
    for ax in fig.axes:
        np.testing.assert_array_equal(ax.lines[0].get_xdata(), [1, 2, 3, 4, 5, 6])
        np.testing.assert_array_equal(ax.lines[0].get_ydata(), [1, 2, 3, 70, 80, 90])
        assert ax.bbox.height >= ax._graphunslopify_heading_height - 1
    renderer = fig.canvas.get_renderer()
    boxes = []
    for ax in fig.axes:
        low, high = sorted(ax.get_ylim())
        boxes.append(
            [
                label.get_window_extent(renderer)
                for value, label in zip(ax.get_yticks(), ax.get_yticklabels(), strict=True)
                if low <= value <= high and label.get_visible() and label.get_text()
            ]
        )
    assert all(not a.overlaps(b) for a in boxes[0] for b in boxes[1])
    assert report["inspection"]["measurements"]["text_scale"] >= 0.99
    before = [ax.bbox.bounds for ax in fig.axes]
    with plt.rc_context(module.RC_PARAMS):
        module.fit_break_layout(fig, upper, lower)
    after = [ax.bbox.bounds for ax in fig.axes]
    np.testing.assert_allclose(np.array(after), np.array(before), rtol=0, atol=1)


@pytest.mark.parametrize("context", ["facet", "break"])
def test_unbreakable_owned_titles_still_fail_strictly(tmp_path, monkeypatch, context):
    title = "OriginalSourceIdentifier" * 12
    completed, report, fig, _ = render(tmp_path, monkeypatch, request(context, title))
    assert completed.returncode == 2 and report["status"] == "failed", report
    assert any(f["code"] == "text_too_small" for f in report["findings"])
    assert owned(fig, "title")[0].get_text() == title


@pytest.mark.parametrize("context", ["facet", "break"])
def test_preview_title_target_keeps_canonical_path_and_source_identity(tmp_path, context):
    state = PreviewState(tmp_path, 1024 * 1024)
    upload = state.upload("observations.csv", CSV)
    spec = request(context)
    result = state.render(
        {"client": "heading-ownership", "generation": 1, "data_id": upload["id"], "spec": spec}
    )
    assert result["report"]["status"] == "passed", result["report"]
    titles = [target for target in result["edit_map"]["targets"] if target["role"] == "title"]
    assert len(titles) == 1 and titles[0]["editable"]
    assert titles[0]["path"] == ["title"] and titles[0]["text"].split() == LONG.split()
    assert result["report"]["spec"]["title"] == LONG
    assert result["report"]["data"]["counts"]["read"] == 6
    if context == "facet":
        panels = [t for t in result["edit_map"]["targets"] if t["role"] == "panel_title"]
        assert len(panels) == 1 and panels[0]["source"] == {"value": "A"}
        assert panels[0]["value"] == PANEL and panels[0]["text"].startswith("(a)")
