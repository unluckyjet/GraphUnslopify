"""Real wrapped headings retain literal wording, source keys and scientific evidence."""

from __future__ import annotations

import contextlib
import copy
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
from matplotlib.text import Text

from graphunslopify.preview import PreviewState
from graphunslopify.transport import local_request

INPUTS = Path(__file__).resolve().parents[2] / "docs/workspace/heading-layout/inputs.json"
FIXTURE = json.loads(INPUTS.read_text())


def request(case="nested"):
    spec = copy.deepcopy(FIXTURE["spec"])
    frame = pd.read_csv(io.StringIO(FIXTURE["csv"]))
    if case == "single":
        spec.pop("facet")
        frame = frame.iloc[:2]
        spec["output"]["size"] = "single_column"
    elif case == "repeat":
        spec.pop("facet")
        frame = frame.iloc[:2].assign(loss=[3, 2])
        spec["data"]["columns"].append("loss")
        spec["repeat"] = {
            "fields": ["score", "loss"],
            "labels": [
                {
                    "field": field,
                    "text": f"{name} on the original untransformed experimental measurement scale",
                }
                for field, name in [("score", "Observed response"), ("loss", "Residual response")]
            ],
        }
    elif case == "horizontal":
        spec.update(kind="bar", orientation="horizontal")
    elif case == "math":
        spec["x"]["label"] = (
            r"Elapsed time with $a + b$ retained across the original experimental observation period"
        )
        spec["y"]["label"] = (
            r"Observed response with $r_{1} + r_{2}$ retained on the original measurement scale"
        )
    elif case == "units":
        spec["x"]["unit"] = "ms"
        spec["y"]["unit"] = "points"
    elif case == "clipped":
        spec.update(kind="bar")
        spec["y"]["limits"] = [0, 10]
    elif case == "false_claim":
        spec.pop("facet")
        frame = frame[frame.phase == "early"]
        spec["group"] = "condition"
        spec["claims"] = [{"kind": "beats_everywhere", "subject": "B", "reference": "A"}]
    elif case == "unbreakable":
        spec.pop("facet")
        frame = frame.iloc[:2]
        spec["output"]["size"] = "single_column"
        spec["title"] = "OriginalIdentifier" * 8
    return spec, frame.to_csv(index=False).encode()


def render(tmp_path, monkeypatch, case="nested"):
    spec, raw = request(case)
    (tmp_path / "data.csv").write_bytes(raw)
    result = local_request("convert", spec)
    assert result["ok"], result
    program = tmp_path / "headings.py"
    program.write_text(result["code"])
    run = subprocess.run(
        [sys.executable, str(program), "--strict", "--json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    report = json.loads(run.stdout)
    definition = importlib.util.spec_from_file_location("owned_headings", program)
    module = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(module)
    monkeypatch.chdir(tmp_path)
    with patch.object(plt, "close"), contextlib.redirect_stdout(io.StringIO()):
        module.main()
    assert (tmp_path / "data.csv").read_bytes() == raw
    return run, report, plt.gcf(), module, spec


@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close("all")


@pytest.mark.parametrize("case", ["nested", "single", "repeat", "horizontal", "math", "units"])
def test_complete_wrapped_wording_and_original_native_observations(tmp_path, monkeypatch, case):
    run, report, fig, module, spec = render(tmp_path, monkeypatch, case)
    assert run.returncode == 0 and report["status"] == "passed", report
    assert not {"labels_collide", "text_too_small"} & {f["code"] for f in report["findings"]}
    wrapped = [t for t in fig.findobj(Text) if hasattr(t, "_graphunslopify_heading_original")]
    assert wrapped
    for t in wrapped:
        assert t.get_text().split() == t._graphunslopify_heading_original.split()
        target = t._graphunslopify_text_target
        if target["role"] == "panel_title":
            assert target["source"] in [
                {"value": c, "row": p} for p in ["early", "late"] for c in ["A", "B"]
            ]
            assert t.get_text().startswith("(") and t.get_fontsize() == module.PANEL_LETTER_PT
        if target["role"] == "axis_label":
            assert target["source"] in ["epoch", "score"]
            assert t.get_fontsize() == module.RC_PARAMS["axes.labelsize"]
    expected = [[7, 11], [5, 8], [8, 13], [6, 9]]
    if case == "repeat":
        expected = [[7, 11], [3, 2]]
    elif case == "single":
        expected = expected[:1]
    for ax, ys in zip(fig.axes, expected, strict=True):
        actual = (
            [p.get_width() for p in ax.patches]
            if case == "horizontal"
            else ax.lines[0].get_ydata(orig=False)
        )
        np.testing.assert_allclose(actual, ys)
    if case == "units":
        assert any("(ms)" in t.get_text() for t in wrapped)
        assert any("(points)" in t.get_text() for t in wrapped)
        assert report["spec"]["x"]["unit"] == spec["x"]["unit"]
    if case == "math":
        assert any("$a + b$" in t.get_text() for t in wrapped)
        assert any("$r_{1} + r_{2}$" in t.get_text() for t in wrapped)
    if case == "single":
        assert fig.axes[0].bbox.height / fig.dpi >= 1.5
    assert all((tmp_path / f"panels.{fmt}").stat().st_size > 100 for fmt in ["png", "svg", "pdf"])
    before = [(t.get_text(), t.get_fontsize()) for t in wrapped]
    module.fit_headings(fig)
    assert before == [(t.get_text(), t.get_fontsize()) for t in wrapped]


@pytest.mark.parametrize("case", ["clipped", "false_claim", "unbreakable"])
def test_heading_layout_keeps_actual_strict_negatives(tmp_path, monkeypatch, case):
    run, report, fig, _, spec = render(tmp_path, monkeypatch, case)
    assert run.returncode == 2 and report["status"] == "failed", report
    if case == "clipped":
        assert any(f["code"] == "bar_mark_clipped" for f in report["findings"])
        assert all(ax.get_ylim() == (0, 10) for ax in fig.axes)
    elif case == "false_claim":
        assert report["claims"] and all(c["subject"] == "B" for c in report["claims"])
        assert any(c["verdict"] == "fails" for c in report["claims"])
    else:
        assert any(f["code"] == "text_too_small" for f in report["findings"])
        assert fig.axes[0].title.get_text() == spec["title"]


def test_wrapped_preview_targets_retain_canonical_identity_and_wording(tmp_path):
    spec, raw = request("units")
    state = PreviewState(tmp_path, 1024 * 1024)
    data = state.upload("observations.csv", raw)
    result = state.render(
        {"client": "wrapped", "generation": 1, "data_id": data["id"], "spec": spec}
    )
    assert result["report"]["status"] == "passed", result["report"]
    targets = result["edit_map"]["targets"]
    panels = [t for t in targets if t["role"] == "panel_title"]
    assert len(panels) == 4 and all("\n" in t["text"] for t in panels)
    for t in panels:
        original = next(
            x
            for x in spec["facet"]["labels"]
            if x["value"] == t["source"]["value"] and x["row"] == t["source"]["row"]
        )
        assert t["value"] == original["text"]
        assert t["path"][:2] == ["facet", "labels"] and t["editable"]
    assert any(
        t["role"] == "axis_label" and t["source"] == "epoch" and "\n" in t["text"] for t in targets
    )
