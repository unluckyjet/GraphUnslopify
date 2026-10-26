"""Independently associate actual panel marks with their own category identities."""

from __future__ import annotations

import importlib.util

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from graphunslopify.transport import local_request

KINDS = [
    "bar",
    "horizontal_bar",
    "box",
    "violin",
    "raincloud",
    "ridgeline",
    "forest",
    "slope",
    "dumbbell",
]
SIDEWAYS = {"horizontal_bar", "ridgeline", "forest", "dumbbell"}


def rows(kind):
    return pd.DataFrame(
        [
            {
                "category": category,
                "value": center + delta,
                "other": 2 * (center + delta),
                "site": site,
                "series": series,
            }
            for site, pairs in [
                ("first", [("B", 30), ("01", 10)]),
                ("second", [("1", 20), ("01", 11)]),
            ]
            for category, center in pairs
            for series in (["first", "second"] if kind in {"slope", "dumbbell"} else ["first"])
            for delta in [-1, 0, 1]
        ]
    )


def raw_spec(kind, shared=True, explicit=False, **extra):
    sideways = kind in SIDEWAYS
    return {
        "kind": "bar" if kind == "horizontal_bar" else kind,
        "data": {"path": "data.csv"},
        "x": {"field": "category", "label": "Category"},
        "y": {"field": "value", "label": "Original metric", "unit": "ms"},
        "facet": {
            "by": "site",
            "columns": 2 if sideways else 1,
            "share_x": shared and not sideways,
            "share_y": shared and sideways,
        },
        "legend": {"show": False},
        "output": {"stem": "shared", "formats": ["png"], "size": "double_column", "dpi": 100},
        **(
            {"orientation": "horizontal", "aggregation": "mean"} if kind == "horizontal_bar" else {}
        ),
        **({"aggregation": "mean"} if kind == "bar" else {}),
        **({"show_points": True} if kind in {"box", "violin"} else {}),
        **({"uncertainty": {"kind": "range"}} if kind == "forest" else {}),
        **({"group": "series"} if kind in {"slope", "dumbbell"} else {}),
        **({"category_order": ["1", "01", "B"]} if explicit else {}),
        **extra,
    }


def run_main(tmp_path, monkeypatch, raw, data):
    response = local_request("convert", raw)
    assert response["ok"], response
    path = tmp_path / "plot.py"
    path.write_text(response["code"], encoding="utf8")
    definition = importlib.util.spec_from_file_location("shared_reference", path)
    module = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(module)
    data.to_csv(tmp_path / "data.csv", index=False, lineterminator="\n")
    monkeypatch.chdir(tmp_path)
    captured = []
    monkeypatch.setattr(plt, "close", captured.append)
    module.main()
    return module, captured[-1]


def category_labels(ax, kind):
    axis = ax.yaxis if kind in SIDEWAYS else ax.xaxis
    return axis.get_major_formatter().format_ticks(axis.get_ticklocs())


def observed_centers(ax, kind):
    if kind in {"bar", "horizontal_bar"}:
        return [
            (p.get_y() + p.get_height() / 2, p.get_width())
            if kind == "horizontal_bar"
            else (p.get_x() + p.get_width() / 2, p.get_height())
            for p in ax.patches
            if np.isfinite(p.get_width()) and np.isfinite(p.get_height())
        ]
    if kind in {"box", "violin", "raincloud"}:
        return [
            (float(np.mean(line.get_xdata())), float(line.get_ydata()[0]))
            for line in ax.lines
            if len(line.get_ydata()) == 2
            and len(line.get_xdata()) == 2
            and np.ptp(line.get_ydata()) == 0
            and np.ptp(line.get_xdata())
            == pytest.approx({"box": 0.6, "violin": 0.14, "raincloud": 0.1}[kind])
        ]
    if kind == "ridgeline":
        return [
            (
                float(np.max(line.get_ydata()) - 0.92),
                float(line.get_xdata()[np.argmax(line.get_ydata())]),
            )
            for line in ax.lines
        ]
    if kind in {"forest", "dumbbell"}:
        return [
            (float(line.get_ydata()[0]), float(line.get_xdata()[0]))
            for line in ax.lines
            if len(line.get_xdata()) == 1 and line.get_marker() == "o"
        ]
    assert kind == "slope"
    return [
        (float(x), float(y))
        for line in ax.lines
        for x, y in zip(line.get_xdata(), line.get_ydata(), strict=True)
        if np.isfinite(y)
    ]


@pytest.fixture(autouse=True)
def close_figures():
    close = plt.close
    yield
    close("all")


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("shared", [True, False])
@pytest.mark.parametrize("explicit", [True, False])
def test_actual_panels_preserve_category_value_associations(
    tmp_path, monkeypatch, kind, shared, explicit
):
    _, fig = run_main(tmp_path, monkeypatch, raw_spec(kind, shared, explicit), rows(kind))
    for ax, expected in zip(fig.axes, [{"B": 30, "01": 10}, {"1": 20, "01": 11}], strict=True):
        order = ["1", "01", "B"] if explicit else ["B", "01", "1"] if shared else list(expected)
        if not shared:
            order = [c for c in order if c in expected]
        if kind in {"ridgeline", "forest", "dumbbell"}:
            order = order[::-1]
        assert category_labels(ax, kind) == order
        centers = observed_centers(ax, kind)
        assert centers
        found = set()
        for position, value in centers:
            category = order[round(position)]
            assert category in expected
            assert value == pytest.approx(
                expected[category], abs=0.12 if kind == "ridgeline" else 1e-10
            )
            found.add(category)
        assert found == set(expected)
        if kind in {"box", "violin", "raincloud"}:
            clouds = [
                np.asarray(c.get_offsets()) for c in ax.collections if len(c.get_offsets()) > 1
            ]
            assert clouds
            for cloud in clouds:
                for position, value in cloud:
                    category = order[round(position)]
                    assert category in expected
                    assert abs(value - expected[category]) <= 1


@pytest.mark.parametrize("kind", KINDS)
def test_repeated_metrics_preserve_empty_levels_and_label_the_measurement_axis(
    tmp_path, monkeypatch, kind
):
    data = rows(kind)
    data.loc[data["category"] == "1", "value"] = np.nan
    data.loc[data["category"] == "B", "other"] = np.nan
    raw = raw_spec(kind)
    raw.pop("facet")
    raw["repeat"] = {
        "fields": ["value", "other"],
        "columns": 2 if kind in SIDEWAYS else 1,
        "share_x": kind not in SIDEWAYS,
        "share_y": kind in SIDEWAYS,
    }
    if kind in SIDEWAYS:
        response = local_request("convert", raw)
        assert not response["ok"]
        assert any(f["code"] == "unsupported_repeat" for f in response["findings"])
        return
    _, fig = run_main(tmp_path, monkeypatch, raw, data)
    expected_rows = [{"B": 30, "01": 10.5}, {"1": 40, "01": 21}]
    order = (
        ["B", "01", "1"][::-1] if kind in {"ridgeline", "forest", "dumbbell"} else ["B", "01", "1"]
    )
    for ax, field, expected in zip(fig.axes, ["value", "other"], expected_rows, strict=True):
        assert category_labels(ax, kind) == order
        assert (ax.get_xlabel() if kind in SIDEWAYS else ax.get_ylabel()) == field.capitalize()
        centers = observed_centers(ax, kind)
        assert centers
        assert {order[round(position)] for position, value in centers} == set(expected)
        for position, value in centers:
            assert value == pytest.approx(
                expected[order[round(position)]], abs=0.15 if kind == "ridgeline" else 1e-10
            )


@pytest.mark.parametrize("kind", ["box", "violin", "raincloud"])
def test_missing_density_groups_keep_global_positions_and_colours(tmp_path, monkeypatch, kind):
    from matplotlib.colors import to_rgba

    module, fig = run_main(
        tmp_path, monkeypatch, raw_spec(kind, category_order=["B", "01", "1", "unused"]), rows(kind)
    )
    for ax, categories in zip(fig.axes, [["B", "01"], ["01", "1"]], strict=True):
        assert category_labels(ax, kind) == ["B", "01", "1", "unused"]
        if kind == "box":
            bodies = ax.patches
        else:
            bodies = [
                c
                for c in ax.collections
                if len(c.get_paths()) == 1
                and len(c.get_paths()[0].vertices) > 10
                and len(c.get_offsets()) == 1
            ]
        assert len(bodies) == 2
        for body, category in zip(bodies, categories, strict=True):
            rgba = np.asarray(body.get_facecolor()).reshape(-1, 4)[0]
            np.testing.assert_allclose(
                rgba[:3], to_rgba(module.PALETTE[["B", "01", "1", "unused"].index(category)])[:3]
            )


def test_global_order_is_recomputed_when_the_same_module_runs_again(tmp_path, monkeypatch):
    module, _ = run_main(tmp_path, monkeypatch, raw_spec("bar"), rows("bar"))
    replacement = pd.DataFrame(
        {"category": ["new", "other"], "value": [7, 9], "site": ["first", "second"]}
    )
    replacement.to_csv(tmp_path / "data.csv", index=False, lineterminator="\n")
    module.main()
    assert module.CATEGORY_ORDER == ["new", "other"]


@pytest.mark.parametrize("kind", ["bar", "box"])
def test_shared_value_sort_uses_original_metric_on_every_main_call(tmp_path, monkeypatch, kind):
    data = rows(kind)
    data["other"] = -data["value"]
    raw = raw_spec(kind, sort={"by": "value", "direction": "desc"})
    raw.pop("facet")
    raw["repeat"] = {"fields": ["value", "other"], "share_x": True, "share_y": False}
    module, fig = run_main(tmp_path, monkeypatch, raw, data)
    assert category_labels(fig.axes[0], kind) == ["B", "1", "01"]
    module.main()
    assert module.CATEGORY_ORDER == ["B", "1", "01"]
