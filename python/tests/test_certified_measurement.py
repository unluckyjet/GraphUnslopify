"""Independent synthetic controls for the frozen evaluator; no NIST product evaluations."""

from __future__ import annotations

import copy
import hashlib
import json
import runpy
import subprocess
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
M = runpy.run_path(str(ROOT / "benchmarks/certified/measurement.py"))
PROTOCOL = json.loads((ROOT / "benchmarks/certified/protocol.json").read_text())


def reference(mean="2", sd="1", tokens=None):
    return M["numeric_reference"](
        {
            "certified": {
                "mean": {"value": mean, "exact": True},
                "sample_sd": {"value": sd, "exact": True},
            }
        },
        tokens or ["1", "2", "3"],
    )


def primitive():
    figure, axis = plt.subplots(figsize=(3.4, 2.6))
    artist = axis.errorbar([0], [2], yerr=[1], fmt="o", capsize=3)
    axis.set(
        xlabel="Synthetic group", ylabel="Synthetic value", title="Synthetic measurement control"
    )
    figure.tight_layout()
    return figure, axis, artist


def test_numeric_gates_resolve_large_offsets_without_a_relative_error_shortcut():
    mean, sd = 10000000.2, 0.1
    r = reference(str(mean), str(sd), ["10000000.1", "10000000.2", "10000000.3"])
    actual = {
        "mean": mean,
        "low": mean - sd,
        "high": mean + sd,
        "half_span": ((mean + sd) - (mean - sd)) / 2,
    }
    assert M["compare_numeric"](actual, r)["passed"]
    wrong = {**actual, "mean": mean + 0.0001}
    assert not M["compare_numeric"](wrong, r)["passed"]
    # Plotted-coordinate cancellation is disclosed rather than called an SD algorithm defect.
    assert float(r["absolute_allowances"]["half_span"]) > 0


@pytest.mark.parametrize("bad", [None, float("nan"), float("inf"), True])
def test_absent_nonfinite_and_boolean_measurements_fail(bad):
    assert not M["compare_numeric"](
        {"mean": bad, "low": 1, "high": 3, "half_span": 1}, reference()
    )["passed"]


def test_unrepresentable_reference_observations_are_not_infinite_allowances():
    with pytest.raises(ValueError, match="finite floats"):
        reference(tokens=["1e1000"])


def test_actual_artists_change_the_score_and_missing_intervals_fail():
    fig, _axis, artist = primitive()
    try:
        before = M["figure_measurements"](fig)
        assert M["compare_numeric"](before["actual"], reference())["passed"]
        artist.lines[0].set_ydata([2.1])
        assert not M["compare_numeric"](M["figure_measurements"](fig)["actual"], reference())[
            "passed"
        ]
        artist.lines[0].set_ydata([2])
        artist.lines[2][0].set_visible(False)
        after = M["figure_measurements"](fig)
        assert after["actual"] == {"mean": 2}
        assert not M["compare_numeric"](after["actual"], reference())["passed"]
    finally:
        plt.close(fig)


@pytest.mark.parametrize(
    "hidden", ["transparent-marker", "zero-interval-width", "clipped-point", "duplicate-point"]
)
def test_artist_visibility_and_membership_are_observed(hidden):
    fig, axis, artist = primitive()
    try:
        if hidden == "transparent-marker":
            artist.lines[0].set_markerfacecolor("none")
            artist.lines[0].set_markeredgewidth(0)
        elif hidden == "zero-interval-width":
            artist.lines[2][0].set_linewidth(0)
        elif hidden == "clipped-point":
            axis.set_xlim(5, 6)
        else:
            axis.plot([0], [2], marker="o")
        result = M["figure_measurements"](fig)
        if hidden == "clipped-point":
            assert result["point_visibility"] == [False]
        else:
            assert not M["compare_numeric"](result["actual"], reference())["passed"]
    finally:
        plt.close(fig)


def test_missing_outputs_never_count_as_reproducible():
    assert M["reproduction"]({}, {}) == {"comparable": False, "identical": False}
    first = {"files": {"png": {"rgba_sha256": "one"}}}
    assert M["reproduction"](first, first) == {"comparable": True, "identical": True}
    assert not M["reproduction"](first, {"files": {"png": {"rgba_sha256": "two"}}})["identical"]


def test_source_and_evaluator_changes_require_an_explicit_new_freeze(tmp_path):
    protocol = M["read_protocol"](ROOT)
    for name in [
        "benchmarks/certified/protocol.json",
        "benchmarks/certified/sources.json",
        *protocol["implementation_sha256"],
    ]:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / name).read_bytes())
    changed = tmp_path / "benchmarks/certified/measurement.py"
    changed.write_bytes(changed.read_bytes() + b"\n# changed\n")
    with pytest.raises(ValueError, match="implementation"):
        M["read_protocol"](tmp_path)
    changed.write_bytes((ROOT / "benchmarks/certified/measurement.py").read_bytes())
    source = tmp_path / "benchmarks/certified/sources.json"
    source.write_text(source.read_text() + "\n")
    with pytest.raises(ValueError, match="source selection"):
        M["read_protocol"](tmp_path)


def test_written_exports_and_physical_font_size_are_checked(tmp_path):
    fig, _, _ = primitive()
    snapshots = []
    try:
        for suffix in PROTOCOL["formats"]:
            measurement = M["figure_measurements"](fig)
            path = tmp_path / f"figure.{suffix}"
            fig.savefig(path, dpi=PROTOCOL["dpi"], bbox_inches="tight")
            snapshots.append(
                {
                    "format": suffix,
                    "measurement": measurement,
                    "export_dpi": PROTOCOL["dpi"],
                    "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
        result = M["export_measurements"](tmp_path, snapshots, PROTOCOL)
        assert result["quality_passed"] and result["minimum_text_pt_at_target"] >= 6
        png = tmp_path / "figure.png"
        original_png = png.read_bytes()
        with Image.open(png) as image:
            image.save(tmp_path / "replacement.png")
        png.write_bytes((tmp_path / "replacement.png").read_bytes())
        assert png.read_bytes() != original_png
        assert not M["export_measurements"](tmp_path, snapshots, PROTOCOL)["quality_checks"][
            "one_measured_export_each"
        ]
        png.write_bytes(original_png)
        reduced = copy.deepcopy(PROTOCOL)
        reduced["width_in"] = 0.5
        assert not M["export_measurements"](tmp_path, snapshots, reduced)["quality_passed"]
        (tmp_path / "figure.pdf").write_bytes(b"bad PDF")
        assert not M["export_measurements"](tmp_path, snapshots, PROTOCOL)["quality_passed"]
        (tmp_path / "figure.png").unlink()
        missing = M["export_measurements"](tmp_path, snapshots, PROTOCOL)
        assert not missing["quality_passed"] and "png" not in missing["files"]
    finally:
        plt.close(fig)


@pytest.mark.parametrize("exit_code", [0, 5])
def test_actual_worker_preserves_exports_and_nonzero_process_exit(tmp_path, exit_code):
    script = tmp_path / "primitive.py"
    script.write_text(
        """import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(3.4, 2.6))
ax.errorbar([0], [2], yerr=[1], fmt="o")
ax.set(xlabel="Synthetic", ylabel="Value", title="Synthetic worker control")
fig.tight_layout()
for suffix in ("png", "svg", "pdf"):
    fig.savefig("figure."+suffix, dpi=150, bbox_inches="tight")
plt.close(fig)
"""
        + f"raise SystemExit({exit_code})\n"
    )
    command = [
        sys.executable,
        str(ROOT / "scripts/measure-certified-figure.py"),
        "--script",
        str(script),
        "--out-dir",
        str(tmp_path),
    ]
    run = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    assert run.returncode == exit_code, run.stderr
    record = json.loads((tmp_path / "measurement.json").read_text())
    assert record["script_exit_code"] == exit_code
    assert record["exports"]["quality_passed"]
    assert len(record["snapshots"]) == 3
    assert all(
        M["compare_numeric"](s["measurement"]["actual"], reference())["passed"]
        for s in record["snapshots"]
    )
    retained = (tmp_path / "measurement.json").read_bytes()
    repeat = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    assert repeat.returncode == 2 and (tmp_path / "measurement.json").read_bytes() == retained
