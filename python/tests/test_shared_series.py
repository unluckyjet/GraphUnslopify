"""Actual artist identities must survive missing groups and shared legends."""

from __future__ import annotations

import importlib.util

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import pandas as pd
import pytest

from graphunslopify.transport import local_request

KINDS = [
    "line",
    "scatter",
    "bar",
    "ecdf",
    "slope",
    "qq",
    "scaling_fit",
    "kaplan_meier",
    "calibration",
    "dumbbell",
    "sparkline_grid",
]


def spec(kind, explicit=False, **extra):
    raw = {
        "kind": kind,
        "data": {"path": "data.csv"},
        "x": {"field": "step", "label": "Step"},
        "y": {"field": "value", "label": "Value"},
        "group": "method",
        "facet": {"by": "site", "columns": 2},
        "legend": {"position": "outside_bottom"},
        "output": {"stem": "series", "formats": ["png"], "size": "double_column", "dpi": 100},
        **({"series_order": ["1", "01"]} if explicit else {}),
        **extra,
    }
    if kind == "bar":
        raw["aggregation"] = "mean"
    if kind == "scaling_fit":
        raw["x"]["scale"] = "log"
        raw["y"]["scale"] = "log"
        raw["interval"] = "none"
    if kind == "kaplan_meier":
        raw["event"] = "event"
    if kind == "calibration":
        raw["x"]["field"] = "prob"
        raw["y"]["field"] = "observed"
        raw["outcome"] = "event"
    return raw


def rows(explicit=False):
    first = "01" if explicit else "1"
    return pd.DataFrame(
        [
            {
                "step": step,
                "value": value,
                "other": value * 2,
                "prob": prob,
                "event": event,
                "method": name,
                "site": site,
            }
            for site, names in [("first", [first]), ("second", ["01", "1"])]
            for name in names
            for step, value, prob, event in [
                (1, 1 if name == "01" else 3, 0.25, 0),
                (2, 2 if name == "01" else 4, 0.75, 1),
            ]
        ]
    )


def run_main(tmp_path, monkeypatch, raw, data):
    r = local_request("convert", raw)
    assert r["ok"], r
    path = tmp_path / "series.py"
    path.write_text(r["code"], encoding="utf8")
    d = importlib.util.spec_from_file_location("series_reference", path)
    m = importlib.util.module_from_spec(d)
    d.loader.exec_module(m)
    data.to_csv(tmp_path / "data.csv", index=False, lineterminator="\n")
    monkeypatch.chdir(tmp_path)
    captured = []
    monkeypatch.setattr(plt, "close", captured.append)
    m.main()
    return m, captured[-1]


def name_of(label):
    name = str(label).split()[0]
    return name if name in {"01", "1"} else None


def artist_styles(ax, kind):
    if kind == "sparkline_grid":
        return {
            child.get_title(): (
                mcolors.to_hex(child.lines[0].get_color()),
                child.lines[0].get_linestyle(),
            )
            for child in ax.child_axes
        }
    handles, labels = ax.get_legend_handles_labels()
    result = {}
    for handle, label in zip(handles, labels, strict=True):
        name = name_of(label)
        if not name:
            continue
        if hasattr(handle, "patches"):
            patch = handle.patches[0]
            result[name] = (mcolors.to_hex(patch.get_facecolor()), patch.get_hatch())
        elif hasattr(handle, "get_facecolor"):
            result[name] = (
                mcolors.to_hex(handle.get_facecolor()[0]),
                str(handle.get_paths()[0].vertices.tolist()),
            )
        else:
            result[name] = (mcolors.to_hex(handle.get_color()), handle.get_linestyle())
    return result


def legend_names(ax):
    legend = ax.get_legend()
    return (
        [name_of(t.get_text()) for t in legend.get_texts() if name_of(t.get_text())]
        if legend
        else []
    )


@pytest.fixture(autouse=True)
def close_figures():
    close = plt.close
    yield
    close("all")


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("explicit", [True, False])
def test_sparse_facets_keep_actual_series_styles_and_identifiable_legends(
    tmp_path, monkeypatch, kind, explicit
):
    m, fig = run_main(tmp_path, monkeypatch, spec(kind, explicit), rows(explicit))
    first, second = fig.axes[:2]
    first_name = "01" if explicit else "1"
    a, b = artist_styles(first, kind), artist_styles(second, kind)
    assert a[first_name] == b[first_name]
    assert b["01"][0] != b["1"][0]
    assert not any(
        f["code"] == "series_colour_drifts_between_panels" for f in m.RUN_REPORT["findings"]
    )
    if kind == "calibration":
        assert legend_names(first) == [first_name]
        assert set(legend_names(second)) == {"01", "1"}
    elif kind != "sparkline_grid":
        assert legend_names(first) == (["1", "01"] if explicit else ["01", "1"])
        assert not legend_names(second)


@pytest.mark.parametrize("kind", ["line", "scatter"])
@pytest.mark.parametrize("scope", ["facet", "repeat"])
def test_direct_labels_belong_to_each_panel_with_its_actual_groups(
    tmp_path, monkeypatch, kind, scope
):
    raw = spec(kind, legend={"style": "direct", "position": "best"})
    data = rows()
    if scope == "repeat":
        raw.pop("facet")
        raw["repeat"] = {"fields": ["value", "other"], "columns": 2}
        data = data[data["site"] == "second"].copy()
        data.loc[data["method"] == "01", "value"] = float("nan")
    _, fig = run_main(tmp_path, monkeypatch, raw, data)
    assert "1" in [t.get_text() for t in fig.axes[0].texts]
    assert {"01", "1"} <= {t.get_text() for t in fig.axes[1].texts}


def test_dumbbell_later_only_group_still_has_an_actual_legend_handle(tmp_path, monkeypatch):
    raw = spec("dumbbell")
    raw.pop("facet")
    data = pd.DataFrame({"step": ["A", "B", "B"], "value": [3, 1, 3], "method": ["1", "01", "1"]})
    _, fig = run_main(tmp_path, monkeypatch, raw, data)
    assert set(legend_names(fig.axes[0])) == {"01", "1"}


def test_shared_legend_keeps_overlay_labels_after_the_ordered_series(tmp_path, monkeypatch):
    raw = spec("line", True, layers=[{"mark": "rule", "value": 2, "label": "Guide"}])
    _, fig = run_main(tmp_path, monkeypatch, raw, rows(True))
    assert [t.get_text() for t in fig.axes[0].get_legend().get_texts()] == ["1", "01", "Guide"]


def test_late_dumbbell_labels_respect_declared_order(tmp_path, monkeypatch):
    raw = spec("dumbbell", series_order=["01", "1"])
    raw.pop("facet")
    data = pd.DataFrame({"step": ["A", "B", "B"], "value": [3, 1, 3], "method": ["1", "01", "1"]})
    _, fig = run_main(tmp_path, monkeypatch, raw, data)
    assert legend_names(fig.axes[0]) == ["01", "1"]


def test_locked_secondary_channels_remain_stable_with_sparse_groups(tmp_path, monkeypatch):
    m, fig = run_main(
        tmp_path, monkeypatch, spec("line", palette_lock=str(tmp_path / "appearance.json")), rows()
    )
    a, b = [artist_styles(ax, "line") for ax in fig.axes]
    assert a["1"] == b["1"]
    assert a["1"][0] == mcolors.to_hex(m.LOCKED["1"]["colour"])
    assert a["1"][1] == m.LOCKED["1"]["linestyle"]


def test_series_mapping_is_recomputed_on_module_reuse(tmp_path, monkeypatch):
    m, _ = run_main(tmp_path, monkeypatch, spec("line"), rows())
    data = rows()
    data = data[data["method"] == "1"]
    data.to_csv(tmp_path / "data.csv", index=False, lineterminator="\n")
    m.main()
    fig = plt.gcf()
    assert artist_styles(fig.axes[0], "line")["1"] == (mcolors.to_hex(m.PALETTE[0]), "-")
    assert legend_names(fig.axes[0]) == ["1"]


def test_actual_sparse_export_passes_strict_with_complete_identity(tmp_path):
    import json
    import subprocess
    import sys

    raw = spec("line")
    raw["output"].update(formats=["png", "svg"], dpi=150)
    r = local_request("convert", raw)
    assert r["ok"]
    path = tmp_path / "series.py"
    path.write_text(r["code"], encoding="utf8")
    rows().to_csv(tmp_path / "data.csv", index=False, lineterminator="\n")
    result = subprocess.run(
        [sys.executable, str(path), "--strict", "--json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    report = json.loads(result.stdout)
    assert result.returncode == 0 and report["status"] == "passed", report
    assert len(report["outputs"]) == 2 and report["inspection"]["checked"]
