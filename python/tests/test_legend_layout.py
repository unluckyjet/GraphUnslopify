"""Complete outside legends retain original marks, statistics and source bindings."""

from __future__ import annotations

import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from test_heading_literal_context import exported_glyph_count

from graphunslopify import read_provenance
from graphunslopify.preview import PreviewState
from graphunslopify.transport import local_request

INPUTS = Path(__file__).resolve().parents[2] / "docs/workspace/outside-legend-layout/inputs.json"
FIXTURE = json.loads(INPUTS.read_text())
KINDS = [case["kind"] for case in FIXTURE["grouped"]]


def request(kind="line", position="outside_bottom"):
    source = next(case for case in FIXTURE["grouped"] if case["kind"] == kind)
    spec = copy.deepcopy(source["spec"])
    spec["legend"]["position"] = position
    return spec, source["csv"]


def data_signature(fig):
    def values(array):
        return np.ma.asarray(array, dtype=float).filled(np.nan).tolist()

    records = []
    for ax in fig.axes:
        if not ax.get_visible():
            continue
        records.append(
            {
                "limits": [list(ax.get_xlim()), list(ax.get_ylim())],
                "scales": [ax.get_xscale(), ax.get_yscale()],
                "lines": [values(line.get_xydata()) for line in ax.lines],
                "collections": [
                    [
                        values(item.get_offsets()),
                        [values(path.vertices) for path in item.get_paths()],
                    ]
                    for item in ax.collections
                ],
                "patches": [
                    [
                        values(item.get_path().vertices),
                        [
                            float(item.get_x()),
                            float(item.get_y()),
                            float(item.get_width()),
                            float(item.get_height()),
                        ]
                        if all(
                            hasattr(item, name)
                            for name in ["get_x", "get_y", "get_width", "get_height"]
                        )
                        else None,
                    ]
                    for item in ax.patches
                ],
            }
        )
    return json.dumps(records, allow_nan=True, sort_keys=True)


def render(folder, monkeypatch, spec, csv):
    raw = csv.encode()
    (folder / "data.csv").write_bytes(raw)
    result = local_request("convert", spec)
    assert result["ok"], result
    path = folder / "legend.py"
    path.write_text(result["code"])
    run = subprocess.run(
        [sys.executable, str(path), "--strict", "--json"],
        cwd=folder,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    report = json.loads(run.stdout)
    definition = importlib.util.spec_from_file_location("owned_legend", path)
    module = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(module)
    original = module.fit_outside_legends
    checked = []

    def text_state(fig):
        return [
            (
                index,
                copy.deepcopy(text._graphunslopify_text_target),
                text.get_fontproperties().copy(),
                text.get_parse_math(),
                text.get_usetex(),
            )
            for index, ax in enumerate(fig.axes)
            if ax.get_legend() is not None
            for text in [*ax.get_legend().get_texts(), ax.get_legend().get_title()]
        ]

    def unchanged(fig, *args, **kwargs):
        fig.canvas.draw()
        before = data_signature(fig)
        presentation = text_state(fig)
        heights = {ax: ax.bbox.height for ax in fig.axes if ax.get_visible()}
        original(fig, *args, **kwargs)
        fig.canvas.draw()
        assert data_signature(fig) == before
        assert text_state(fig) == presentation
        assert all(ax.bbox.height >= height - 1 for ax, height in heights.items())
        if module.RUN_REPORT["spec"]["kind"] == "calibration":
            assert all(ax.bbox.height <= height * 1.3 for ax, height in heights.items())
        checked.append(True)

    module.fit_outside_legends = unchanged
    monkeypatch.chdir(folder)
    with patch.object(plt, "close"), contextlib.redirect_stdout(io.StringIO()):
        module.main()
    assert checked
    assert (folder / "data.csv").read_bytes() == raw
    assert report["data"]["sha256_prefix"] == hashlib.sha256(raw).hexdigest()[:16]
    assert report["data"]["counts"]["read"] == len(pd.read_csv(io.StringIO(csv)))
    stem = spec["output"]["stem"]
    for fmt in spec["output"]["formats"]:
        output = folder / f"{stem}.{fmt}"
        assert output.stat().st_size > 100
        assert read_provenance(output)["spec"]["legend"].get("labels", []) == spec["legend"].get(
            "labels", []
        )
    return run, report, plt.gcf(), module


def legends(fig):
    return [ax.get_legend() for ax in fig.axes if ax.get_legend() is not None]


@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close("all")


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("position", ["outside_right", "outside_bottom"])
def test_complete_native_legend_names_preserve_original_marks_and_sparse_source_ids(
    tmp_path, monkeypatch, kind, position
):
    spec, csv = request(kind, position)
    run, report, fig, _ = render(tmp_path, monkeypatch, spec, csv)
    assert run.returncode == 0 and report["status"] == "passed", report
    actual = legends(fig)
    assert all(ax.bbox.width / fig.dpi >= 0.75 for ax in fig.axes if ax.get_visible())
    assert len(actual) == (2 if kind == "calibration" else 1)
    expected = set(spec["series_order"])
    entries = [text for legend in actual for text in legend.get_texts()]
    assert {text._graphunslopify_text_target["source"] for text in entries} == expected
    for text in entries:
        target = text._graphunslopify_text_target
        assert target["role"] == "legend_entry" and target["path"][:2] == ["legend", "labels"]
        displayed = " ".join(text.get_text().split())
        assert displayed == target["source"] or displayed.startswith(target["source"] + " (ECE ")
        assert text.get_fontsize() * report["inspection"]["measurements"]["text_scale"] >= 5
    assert any("\n" in text.get_text() for text in entries)
    if kind != "calibration":
        renderer = fig.canvas.get_renderer()
        box = actual[0].get_window_extent(renderer)
        if position == "outside_right":
            assert box.x0 > max(ax.bbox.x1 for ax in fig.axes if ax.get_visible())
        else:
            assert box.y1 < min(ax.bbox.y0 for ax in fig.axes if ax.get_visible())


@pytest.mark.parametrize("position", ["outside_right", "outside_bottom"])
def test_original_single_column_six_row_legend_reproduction(tmp_path, monkeypatch, position):
    source = next(case for case in FIXTURE["single_column"] if case["position"] == position)
    spec = copy.deepcopy(source["spec"])
    spec["output"]["formats"] = ["png", "svg", "pdf"]
    run, report, _, _ = render(tmp_path, monkeypatch, spec, source["csv"])
    assert run.returncode == 0 and report["status"] == "passed", report
    assert report["inspection"]["measurements"]["text_scale"] > 0.65


def test_short_bottom_legend_retains_actual_native_horizontal_strip(tmp_path, monkeypatch):
    spec, csv = request()
    spec["legend"]["labels"] = [
        {"series": source, "text": alias}
        for source, alias in zip(spec["series_order"], ["Control", "Treatment"], strict=True)
    ]
    run, report, fig, _ = render(tmp_path, monkeypatch, spec, csv)
    assert run.returncode == 0 and report["status"] == "passed", report
    renderer = fig.canvas.get_renderer()
    left, right = [text.get_window_extent(renderer) for text in legends(fig)[0].get_texts()]
    assert abs(left.y0 - right.y0) < 1 and left.x1 < right.x0


def test_four_short_entries_choose_measured_compact_columns(tmp_path, monkeypatch):
    spec, csv = request()
    frame = pd.read_csv(io.StringIO(csv))
    extra = frame.copy()
    mapping = {name: name + " second preparation" for name in spec["series_order"]}
    extra["method"] = extra.method.map(mapping)
    spec["series_order"] += [mapping[name] for name in spec["series_order"]]
    spec["output"]["size"] = "single_column"
    spec["legend"]["labels"] = [
        {"series": source, "text": alias}
        for source, alias in zip(
            spec["series_order"], ["Baseline", "Augmented", "Distilled", "Proposed"], strict=True
        )
    ]
    raw = pd.concat([frame, extra], ignore_index=True).to_csv(index=False, lineterminator="\n")
    run, report, fig, _ = render(tmp_path, monkeypatch, spec, raw)
    assert run.returncode == 0 and report["status"] == "passed", report
    actual = legends(fig)[0]
    renderer = fig.canvas.get_renderer()
    boxes = [text.get_window_extent(renderer) for text in actual.get_texts()]
    assert len({round(box.y0, 3) for box in boxes}) == 2
    assert len({round(box.x0, 3) for box in boxes}) == 2
    assert all(
        not left.overlaps(right) for index, left in enumerate(boxes) for right in boxes[index + 1 :]
    )
    assert actual.get_window_extent(renderer).width <= fig.bbox.width * 0.92


def test_calibration_legends_keep_each_panels_independent_error_value(tmp_path, monkeypatch):
    spec, csv = request("calibration")
    frame = pd.read_csv(io.StringIO(csv))
    frame.loc[frame.site == "first", "prob"] = [0.1, 0.9]
    raw = frame.to_csv(index=False, lineterminator="\n")
    run, report, fig, _ = render(tmp_path, monkeypatch, spec, raw)
    assert run.returncode == 0 and report["status"] == "passed", report
    first, second = legends(fig)
    assert len(first.get_texts()) == 1 and len(second.get_texts()) == 2
    assert " ".join(first.get_texts()[0].get_text().split()).endswith("(ECE 0.1)")
    assert all(
        " ".join(text.get_text().split()).endswith("(ECE 0.25)") for text in second.get_texts()
    )


@pytest.mark.parametrize("context", ["nested", "repeat", "break", "layer", "dates"])
def test_outside_legend_contexts_keep_numeric_marks_bounds_and_ownership(
    tmp_path, monkeypatch, context
):
    spec, csv = request("line")
    frame = pd.read_csv(io.StringIO(csv))
    if context == "nested":
        frame["phase"] = frame.step.map({1: "early", 2: "late"})
        spec["facet"]["rows"] = "phase"
    elif context in {"repeat", "break"}:
        frame = frame[frame.site == "second"]
        spec.pop("facet")
        if context == "repeat":
            spec["repeat"] = {"fields": ["value", "other"]}
        else:
            spec["axis_break"] = {"axis": "y", "from": 2.1, "to": 2.9}
    elif context == "layer":
        spec["layers"] = [
            {
                "mark": "rule",
                "value": 2.5,
                "label": "Independent preregistered reference threshold retained across the full observation period",
            }
        ]
    elif context == "dates":
        frame["step"] = frame.step.map({1: "2026-10-01T00:00:00", 2: "2026-10-01T12:00:00"})
        spec["x"]["temporal"] = True
    run, report, fig, _ = render(
        tmp_path, monkeypatch, spec, frame.to_csv(index=False, lineterminator="\n")
    )
    assert run.returncode == 0 and report["status"] == "passed", report
    if context == "layer":
        entries = [text for legend in legends(fig) for text in legend.get_texts()]
        assert any(
            text._graphunslopify_text_target["path"] == ["layers", 0, "label"] for text in entries
        )
    if context == "break":
        assert fig.axes[0].get_ylim()[0] == 2.9 and fig.axes[1].get_ylim()[1] == 2.1


def test_grouped_secondary_axes_remain_explicitly_unsupported():
    spec, _ = request()
    spec["y2"] = {
        "field": "other",
        "label": "Other measured quantity",
        "justification": "The second measured quantity shares only the observation axis.",
    }
    result = local_request("convert", spec)
    assert not result["ok"]
    assert any(item["code"] == "dual_axis_with_group" for item in result["findings"])


def test_long_legend_title_fits_without_changing_canonical_text(tmp_path, monkeypatch):
    spec, csv = request(position="outside_right")
    title = "Complete treatment identities across the original experimental preparation and follow-up schedule"
    spec["legend"]["title"] = title
    run, report, fig, _ = render(tmp_path, monkeypatch, spec, csv)
    assert run.returncode == 0 and report["status"] == "passed", report
    actual = legends(fig)[0].get_title()
    assert actual.get_text().split() == title.split()
    assert "\n" in actual.get_text()
    assert actual._graphunslopify_text_target["path"] == ["legend", "title"]
    assert report["spec"]["legend"]["title"] == title


def test_actual_legend_svg_retains_currency_and_formula_glyphs(tmp_path, monkeypatch):
    spec, csv = request()
    names = spec["series_order"]
    spec["legend"]["labels"] = [
        {
            "series": names[0],
            "text": r"Measured response $\alpha + \beta$ across the complete period",
        },
        {
            "series": names[1],
            "text": "Measured prices at $5 and $10 and $15 in the original currency",
        },
    ]
    run, report, _, module = render(tmp_path, monkeypatch, spec, csv)
    assert run.returncode == 0 and report["status"] == "passed", report
    import xml.etree.ElementTree as ET

    svg = ET.parse(tmp_path / "series.svg").getroot()
    assert exported_glyph_count(svg, "$", module.RC_PARAMS) == 3
    assert exported_glyph_count(svg, "\N{GREEK SMALL LETTER ALPHA}", module.RC_PARAMS) == 1


@pytest.mark.parametrize("case", ["unbreakable", "clipped", "false_claim"])
def test_legend_fitting_keeps_strict_negative_evidence(tmp_path, monkeypatch, case):
    spec, csv = request("bar" if case == "clipped" else "line")
    if case == "unbreakable":
        spec["legend"]["labels"] = [
            {"series": spec["series_order"][0], "text": "OriginalIdentifier" * 15}
        ]
    elif case == "clipped":
        spec["y"]["limits"] = [0, 2]
    else:
        spec["claims"] = [
            {
                "kind": "beats_everywhere",
                "subject": spec["series_order"][1],
                "reference": spec["series_order"][0],
            }
        ]
    run, report, fig, _ = render(tmp_path, monkeypatch, spec, csv)
    assert run.returncode == 2 and report["status"] == "failed", report
    if case == "unbreakable":
        assert any(item["code"] == "text_too_small" for item in report["findings"])
    elif case == "clipped":
        assert any(item["code"] == "bar_mark_clipped" for item in report["findings"])
        assert all(ax.get_ylim() == (0, 2) for ax in fig.axes)
    else:
        assert any(item["verdict"] == "fails" for item in report["claims"])
        assert all(item["subject"] == spec["series_order"][1] for item in report["claims"])


def test_preview_wrapped_entries_retain_original_canonical_append_identity(tmp_path):
    spec, csv = request()
    state = PreviewState(tmp_path, 1024 * 1024)
    data = state.upload("original.csv", csv.encode())
    result = state.render(
        {"client": "long-legends", "generation": 1, "data_id": data["id"], "spec": spec}
    )
    assert result["report"]["status"] == "passed", result["report"]
    targets = [item for item in result["edit_map"]["targets"] if item["role"] == "legend_entry"]
    assert {item["source"] for item in targets} == set(spec["series_order"])
    assert all("\n" in item["text"] and item["editable"] for item in targets)
    assert all(item["path"] == ["legend", "labels", 0, "text"] for item in targets)
    assert result["report"]["spec"]["legend"].get("labels", []) == []
