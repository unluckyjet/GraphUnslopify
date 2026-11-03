"""Real files,upstream event writers,identity/custody and actual native comparisons."""

import csv
import hashlib
import io
import json
import subprocess
from pathlib import Path

import pytest

from graphunslopify import experiment_imports as imports


@pytest.fixture
def csv_runs(tmp_path):
    root = tmp_path / "owned results"
    root.mkdir()
    (root / "a.csv").write_text("step,loss,accuracy,model\n0,3,0.5,a\n1,2,0.6,a\n2,1,0.7,a\n")
    (root / "b.csv").write_text("step,loss,accuracy,model\n0,4,0.4,b\n1,3,0.5,b\n2,2,0.6,b\n")
    return root


def _hashes(root):
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


def test_complete_catalog_selection_retains_actual_source_ids_and_values(csv_runs, monkeypatch):
    before = _hashes(csv_runs)
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: pytest.fail("A reader must not execute programs")
    )
    catalog = imports.experiment_runs(csv_runs)
    assert catalog["complete"] and not catalog["new_execution"]
    assert len(catalog["runs"]) == 2 and len({r["id"] for r in catalog["runs"]}) == 2
    assert {m["name"] for m in catalog["runs"][0]["metrics"]} == {"accuracy", "loss"}
    ids = [r["id"] for r in catalog["runs"]]
    proposal = imports.experiment_comparison(
        csv_runs, runs=ids, metric="loss", expected_snapshot=catalog["snapshot"]
    )
    rows = list(csv.DictReader(io.StringIO(proposal.csv_bytes.decode())))
    assert [(float(r["step"]), float(r["value"])) for r in rows] == [
        (0, 3),
        (1, 2),
        (2, 1),
        (0, 4),
        (1, 3),
        (2, 2),
    ]
    assert [r["run_id"] for r in rows] == [ids[0]] * 3 + [ids[1]] * 3
    assert [r["source_record"] for r in rows] == ["1", "2", "3"] * 2
    assert proposal.report["records"] == 6 and proposal.report["aggregation"] == "none"
    assert not proposal.report["applied"] and not proposal.report["verified"]
    assert "uncertainty" not in proposal.spec and "claims" not in proposal.spec
    assert _hashes(csv_runs) == before


def test_duplicate_steps_need_scatter_and_do_not_merge_or_average(csv_runs):
    with (csv_runs / "a.csv").open("a") as out:
        out.write("1,99,0.1,a\n")
    catalog = imports.experiment_runs(csv_runs)
    ids = [r["id"] for r in catalog["runs"]]
    with pytest.raises(imports.ExperimentError, match="Duplicate steps"):
        imports.experiment_comparison(
            csv_runs, runs=ids, metric="loss", expected_snapshot=catalog["snapshot"]
        )
    proposal = imports.experiment_comparison(
        csv_runs, runs=ids, metric="loss", kind="scatter", expected_snapshot=catalog["snapshot"]
    )
    rows = list(csv.DictReader(io.StringIO(proposal.csv_bytes.decode())))
    assert len(rows) == 7 and proposal.report["duplicate_steps"] == 1
    assert [float(r["value"]) for r in rows if r["run_id"] == ids[0] and float(r["step"]) == 1] == [
        2,
        99,
    ]


def test_missing_nonfinite_bad_step_exclusions_are_explicit(csv_runs):
    (csv_runs / "a.csv").write_text("step,loss\n0,3\n1,\n2,nan\nmissing,5\n3,word\n")
    catalog = imports.experiment_runs(csv_runs, metrics=["loss"])
    proposal = imports.experiment_comparison(
        csv_runs,
        metrics=["loss"],
        runs=[r["id"] for r in catalog["runs"]],
        metric="loss",
        expected_snapshot=catalog["snapshot"],
    )
    assert proposal.report["excluded_records"] == 4 and proposal.report["records"] == 4
    assert {r["issue"] for r in proposal.report["exclusions"]} == {
        "missing",
        "nonfinite",
        "step_not_numeric",
        "not_numeric",
    }
    assert len(list(csv.DictReader(io.StringIO(proposal.csv_bytes.decode())))) == 4


def test_changed_snapshot_options_and_foreign_ids_refused(csv_runs):
    catalog = imports.experiment_runs(csv_runs)
    ids = [r["id"] for r in catalog["runs"]]
    with pytest.raises(imports.ExperimentError, match="source/reader/options changed"):
        imports.experiment_comparison(
            csv_runs,
            runs=ids,
            metric="loss",
            metrics=["loss"],
            expected_snapshot=catalog["snapshot"],
        )
    with pytest.raises(imports.ExperimentError, match="distinct run IDs"):
        imports.experiment_comparison(
            csv_runs, runs=["another-source"], metric="loss", expected_snapshot=catalog["snapshot"]
        )
    with (csv_runs / "a.csv").open("a") as out:
        out.write("3,0,0.8,a\n")
    with pytest.raises(imports.ExperimentError, match="source/reader/options changed"):
        imports.experiment_comparison(
            csv_runs, runs=ids, metric="loss", expected_snapshot=catalog["snapshot"]
        )


def test_race_during_collection_refused(csv_runs, monkeypatch):
    original = imports._csv_points

    def change(config, contents):
        result = original(config, contents)
        (csv_runs / "a.csv").write_text("step,loss\n0,99\n")
        return result

    monkeypatch.setattr(imports, "_csv_points", change)
    with pytest.raises(imports.ExperimentError, match="source changed"):
        imports.experiment_runs(csv_runs)


@pytest.mark.parametrize(
    "bound,value",
    [("MAX_FILES", 1), ("MAX_FILE_BYTES", 8), ("MAX_SOURCE_BYTES", 8), ("MAX_POINTS", 2)],
)
def test_limits_refuse_instead_of_silent_sampling(csv_runs, monkeypatch, bound, value):
    before = _hashes(csv_runs)
    monkeypatch.setattr(imports, bound, value)
    with pytest.raises(imports.ExperimentError):
        imports.experiment_runs(csv_runs)
    assert _hashes(csv_runs) == before


def test_csv_ragged_duplicate_header_and_source_escape_refused(tmp_path):
    root = tmp_path / "input"
    root.mkdir()
    p = root / "a.csv"
    p.write_text("step,loss\n0,1,extra\n")
    with pytest.raises(imports.ExperimentError, match="number of fields"):
        imports.experiment_runs(root)
    p.write_text("step,loss,loss\n0,1,2\n")
    with pytest.raises(imports.ExperimentError, match="unique column"):
        imports.experiment_runs(root)
    outside = tmp_path / "external.csv"
    outside.write_text("step,loss\n0,9\n")
    p.unlink()
    try:
        p.symlink_to(outside)
    except OSError:
        pytest.skip("This host does not permit file symlinks")
    with pytest.raises(imports.ExperimentError, match="contained regular files"):
        imports.experiment_runs(root)


@pytest.fixture
def tensorboard_runs(tmp_path):
    pytest.importorskip("tensorboard")
    from tensorboard.compat.proto import event_pb2, summary_pb2, tensor_pb2, types_pb2
    from tensorboard.summary.writer.event_file_writer import EventFileWriter

    root = tmp_path / "events"
    for index in range(2):
        folder = root / str(index) / "same name"
        writer = EventFileWriter(str(folder))
        for step in range(3):
            writer.add_event(
                event_pb2.Event(
                    wall_time=step + 1,
                    step=step,
                    summary=summary_pb2.Summary(
                        value=[summary_pb2.Summary.Value(tag="loss", simple_value=3 - step + index)]
                    ),
                )
            )
            writer.add_event(
                event_pb2.Event(
                    wall_time=step + 1,
                    step=step,
                    summary=summary_pb2.Summary(
                        value=[
                            summary_pb2.Summary.Value(
                                tag="accuracy",
                                tensor=tensor_pb2.TensorProto(
                                    dtype=types_pb2.DT_FLOAT, float_val=[step + index]
                                ),
                                metadata=summary_pb2.SummaryMetadata(
                                    plugin_data=summary_pb2.SummaryMetadata.PluginData(
                                        plugin_name="scalars"
                                    )
                                ),
                            )
                        ]
                    ),
                )
            )
        writer.close()
        writer = EventFileWriter(str(folder))
        writer.add_event(
            event_pb2.Event(
                wall_time=10,
                step=1,
                session_log=event_pb2.SessionLog(status=event_pb2.SessionLog.START),
            )
        )
        writer.add_event(
            event_pb2.Event(
                wall_time=11,
                step=1,
                summary=summary_pb2.Summary(
                    value=[summary_pb2.Summary.Value(tag="loss", simple_value=99 + index)]
                ),
            )
        )
        writer.close()
    return root


def test_actual_upstream_files_scalars_tensors_restarts_and_custody(tensorboard_runs):
    before = _hashes(tensorboard_runs)
    catalog = imports.experiment_runs(tensorboard_runs, provider="tensorboard")
    assert len(catalog["runs"]) == 2 and len(catalog["files"]) == 4
    proposal = imports.experiment_comparison(
        tensorboard_runs,
        provider="tensorboard",
        runs=[r["id"] for r in catalog["runs"]],
        metric="loss",
        kind="scatter",
        expected_snapshot=catalog["snapshot"],
    )
    rows = list(csv.DictReader(io.StringIO(proposal.csv_bytes.decode())))
    assert len(rows) == 8 and proposal.report["duplicate_steps"] == 2
    assert [float(r["value"]) for r in rows] == [3, 2, 1, 99, 4, 3, 2, 100]
    assert {r["session"] for r in rows} == {"0", "1"}
    assert all(r["source_offset"] for r in rows)
    assert _hashes(tensorboard_runs) == before
    assert imports._crc32c(b"123456789") == 0xE3069283


@pytest.mark.parametrize("mutation", ["length_crc", "payload_crc", "truncated", "trailing"])
def test_corrupt_or_partial_event_file_cannot_be_complete(tensorboard_runs, mutation):
    path = next(tensorboard_runs.rglob("events.out.tfevents.*"))
    content = bytearray(path.read_bytes())
    if mutation == "length_crc":
        content[8] ^= 1
    elif mutation == "payload_crc":
        content[-1] ^= 1
    elif mutation == "truncated":
        content = content[:-1]
    else:
        content += b"partial"
    path.write_bytes(content)
    with pytest.raises(imports.ExperimentError, match=r"CRC mismatch|Truncated"):
        imports.experiment_runs(tensorboard_runs, provider="tensorboard")


def test_huge_non_scalar_tensor_is_not_allocated(tensorboard_runs, monkeypatch):
    from tensorboard.compat.proto import (
        event_pb2,
        summary_pb2,
        tensor_pb2,
        tensor_shape_pb2,
        types_pb2,
    )
    from tensorboard.summary.writer.event_file_writer import EventFileWriter
    from tensorboard.util import tensor_util

    folder = tensorboard_runs / "0" / "same name"
    writer = EventFileWriter(str(folder))
    writer.add_event(
        event_pb2.Event(
            step=0,
            summary=summary_pb2.Summary(
                value=[
                    summary_pb2.Summary.Value(
                        tag="huge",
                        tensor=tensor_pb2.TensorProto(
                            dtype=types_pb2.DT_FLOAT,
                            tensor_shape=tensor_shape_pb2.TensorShapeProto(
                                dim=[tensor_shape_pb2.TensorShapeProto.Dim(size=2**50)]
                            ),
                        ),
                    )
                ]
            ),
        )
    )
    writer.close()
    original = tensor_util.make_ndarray

    def bounded(tensor):
        assert not tensor.tensor_shape.dim, "Refuse non-scalar shape before allocating"
        return original(tensor)

    monkeypatch.setattr(tensor_util, "make_ndarray", bounded)
    catalog = imports.experiment_runs(tensorboard_runs, provider="tensorboard")
    assert any(r["metric"] == "huge" for r in catalog["ignored"])
    with pytest.raises(imports.ExperimentError, match="unsupported scalar"):
        imports.experiment_comparison(
            tensorboard_runs,
            provider="tensorboard",
            runs=[catalog["runs"][0]["id"]],
            metric="huge",
            kind="scatter",
            expected_snapshot=catalog["snapshot"],
        )


def test_actual_strict_native_comparison_matches_selected_numeric_artists(
    csv_runs, tmp_path, monkeypatch
):
    import runpy
    import sys

    import matplotlib.pyplot as plt

    from graphunslopify import Figure

    catalog = imports.experiment_runs(csv_runs)
    proposal = imports.experiment_comparison(
        csv_runs,
        runs=[r["id"] for r in catalog["runs"]],
        metric="loss",
        expected_snapshot=catalog["snapshot"],
    )
    out = tmp_path / "native"
    out.mkdir()
    data = out / "experiment-history.csv"
    data.write_bytes(proposal.csv_bytes)
    spec = json.loads(json.dumps(proposal.spec))
    spec["data"]["path"] = str(data)
    result = Figure(spec).render(cwd=out, api="local")
    assert result["report"]["status"] == "passed"
    plt.close("all")
    original_close = plt.close
    with monkeypatch.context() as m:
        m.setattr(plt, "close", lambda *a, **k: None)
        m.setattr(sys, "argv", [str(result["script"]), "--strict"])
        m.chdir(out)
        with pytest.raises(SystemExit) as completed:
            runpy.run_path(str(result["script"]), run_name="__main__")
        assert completed.value.code == 0
        lines = [line for line in plt.gcf().axes[0].lines if not line.get_label().startswith("_")]
        assert [list(line.get_xdata()) for line in lines] == [[0, 1, 2], [0, 1, 2]]
        assert [list(line.get_ydata()) for line in lines] == [[3, 2, 1], [4, 3, 2]]
    original_close("all")
    assert data.read_bytes() == proposal.csv_bytes


def test_actual_cli_catalog_comparison_and_portable_source_report(csv_runs, tmp_path):
    import os
    import sys

    env = {**os.environ, "PYTHONPATH": str(Path(__file__).parents[1])}
    before = _hashes(csv_runs)
    catalog_process = subprocess.run(
        [sys.executable, "-m", "graphunslopify.cli", "experiment-runs", str(csv_runs)],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    catalog = json.loads(catalog_process.stdout)
    output = tmp_path / "comparison"
    command = [
        sys.executable,
        "-m",
        "graphunslopify.cli",
        "experiment-compare",
        str(csv_runs),
        "--snapshot",
        catalog["snapshot"],
        "--runs",
        *[r["id"] for r in catalog["runs"]],
        "--metric",
        "loss",
        "--out-dir",
        str(output),
    ]
    rendered = subprocess.run(command, env=env, capture_output=True, text=True, check=True)
    report = json.loads(rendered.stdout)
    assert report["exit_code"] == 0 and report["scientific_status"] == "passed"
    assert report["import"]["records"] == 6 and not report["import"]["verified"]
    assert (
        json.loads((output / "experiment.figure.json").read_text())["data"]["path"]
        == "experiment-history.csv"
    )
    assert json.loads((output / "experiment-import.json").read_text()) == report
    assert (output / "experiment-comparison.png").is_file()
    repeated = subprocess.run(command, env=env, capture_output=True, text=True, check=False)
    assert repeated.returncode == 2
    assert _hashes(csv_runs) == before


def test_explicit_exclusions_and_source_output_boundaries(csv_runs, tmp_path):
    with (csv_runs / "a.csv").open("a") as out:
        out.write("3,,0.8,a\n")
    catalog = imports.experiment_runs(csv_runs)
    proposal = imports.experiment_comparison(
        csv_runs,
        runs=[r["id"] for r in catalog["runs"]],
        metric="loss",
        expected_snapshot=catalog["snapshot"],
    )
    with pytest.raises(imports.ExperimentError, match="explicitly accept"):
        imports.render_experiment_comparison(proposal, tmp_path / "not-created")
    assert not (tmp_path / "not-created").exists()
    with pytest.raises(imports.ExperimentError, match="outside"):
        imports.render_experiment_comparison(proposal, csv_runs / "output", accept_exclusions=True)
    result = imports.render_experiment_comparison(
        proposal, tmp_path / "accepted-exclusions", accept_exclusions=True
    )
    assert result["exit_code"] == 0 and result["import"]["excluded_records"] == 1


def test_materialized_data_race_keeps_actual_native_verdict_but_refuses_import(
    csv_runs, tmp_path, monkeypatch
):
    from graphunslopify import Figure

    catalog = imports.experiment_runs(csv_runs)
    proposal = imports.experiment_comparison(
        csv_runs,
        runs=[r["id"] for r in catalog["runs"]],
        metric="loss",
        expected_snapshot=catalog["snapshot"],
    )
    original = Figure.render

    def mutate(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        Path(self.spec["data"]["path"]).write_text("step,value\n0,999\n")
        return result

    monkeypatch.setattr(Figure, "render", mutate)
    result = imports.render_experiment_comparison(proposal, tmp_path / "raced")
    assert result["exit_code"] == 2 and result["scientific_status"] == "passed"
    assert "Materialized history changed" in result["error"]


def test_normalized_output_has_a_separate_byte_budget(csv_runs, monkeypatch):
    catalog = imports.experiment_runs(csv_runs)
    monkeypatch.setattr(imports, "MAX_NORMALIZED_BYTES", 120)
    with pytest.raises(imports.ExperimentError, match="Normalized history"):
        imports.experiment_comparison(
            csv_runs,
            runs=[r["id"] for r in catalog["runs"]],
            metric="loss",
            expected_snapshot=catalog["snapshot"],
        )


def test_csv_integer_steps_and_values_above_float_mantissa_remain_exact(tmp_path):
    source = tmp_path / "large.csv"
    source.write_text(
        "step,loss\n9007199254740992,9007199254740992\n9007199254740993,9007199254740993\n2,9223372036854775808\n"
    )
    catalog = imports.experiment_runs(source)
    proposal = imports.experiment_comparison(
        source,
        runs=[catalog["runs"][0]["id"]],
        metric="loss",
        expected_snapshot=catalog["snapshot"],
    )
    rows = list(csv.DictReader(io.StringIO(proposal.csv_bytes.decode())))
    assert [r["step"] for r in rows] == ["9007199254740992", "9007199254740993"]
    assert [r["value"] for r in rows] == ["9007199254740992", "9007199254740993"]
    assert proposal.report["duplicate_steps"] == 0 and proposal.report["excluded_records"] == 1
    assert proposal.report["exclusions"][0]["issue"] == "integer_out_of_range"


def test_actual_tensorboard_integer_scalars_remain_exact(tmp_path):
    pytest.importorskip("tensorboard")
    from tensorboard.compat.proto.event_pb2 import Event
    from tensorboard.compat.proto.summary_pb2 import Summary
    from tensorboard.compat.proto.tensor_pb2 import TensorProto
    from tensorboard.compat.proto.types_pb2 import DT_INT64
    from tensorboard.summary.writer.event_file_writer import EventFileWriter

    source = tmp_path / "events"
    writer = EventFileWriter(str(source))
    for step, value in enumerate([9007199254740992, 9007199254740993]):
        writer.add_event(
            Event(
                step=step,
                summary=Summary(
                    value=[
                        Summary.Value(
                            tag="loss", tensor=TensorProto(dtype=DT_INT64, int64_val=[value])
                        )
                    ]
                ),
            )
        )
    writer.close()
    catalog = imports.experiment_runs(source, provider="tensorboard")
    proposal = imports.experiment_comparison(
        source,
        provider="tensorboard",
        runs=[catalog["runs"][0]["id"]],
        metric="loss",
        expected_snapshot=catalog["snapshot"],
    )
    rows = list(csv.DictReader(io.StringIO(proposal.csv_bytes.decode())))
    assert [r["value"] for r in rows] == ["9007199254740992", "9007199254740993"]


@pytest.mark.parametrize("parent", [False, True])
def test_symlink_swap_between_discovery_and_open_is_refused(
    csv_runs, tmp_path, monkeypatch, parent
):
    import os

    if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
        pytest.skip("Descriptor-based containment is a POSIX control")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "a.csv").write_text("step,loss\n0,999\n")
    if parent:
        nested = csv_runs / "nested"
        nested.mkdir()
        (nested / "a.csv").write_text("step,loss\n0,1\n")
    discover = imports._discover

    def swapped(config):
        paths = discover(config)
        if parent:
            nested.rename(csv_runs / "nested-held")
            nested.symlink_to(outside, target_is_directory=True)
        else:
            (csv_runs / "a.csv").rename(csv_runs / "a-held")
            (csv_runs / "a.csv").symlink_to(outside / "a.csv")
        return paths

    monkeypatch.setattr(imports, "_discover", swapped)
    with pytest.raises(OSError):
        imports.experiment_runs(csv_runs)
