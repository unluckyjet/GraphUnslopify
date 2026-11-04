"""Actual static worker and strict native imports; original fixture execution is trusted and separate."""

import csv
import hashlib
import io
import json
import subprocess
import sys

import pytest

from graphunslopify import source_imports as imports
from graphunslopify.source_parser import convert


@pytest.mark.parametrize(
    "method,kind,x",
    [
        ("plot", "line", "[0,1,2]"),
        ("scatter", "scatter", "[0,1,2]"),
        ("bar", "bar", "['A','B','C']"),
    ],
)
def test_actual_worker_keeps_values_and_original_with_strict_native(tmp_path, method, kind, x):
    source = f"import matplotlib.pyplot as plt\nfig, ax = plt.subplots()\nax.{method}({x}, [3,2,1], label='Model')\nax.set_xlabel('Step')\nax.set_ylabel('Loss')\nax.legend()\n".encode()
    proposal = imports.import_source(source, name="owned.py")
    assert proposal.report["convertible"] and proposal.report["all_statements_supported"]
    assert (
        not proposal.report["source_executed"] and not proposal.report["pixel_equivalence_claimed"]
    )
    assert proposal.spec["kind"] == kind
    rows = list(csv.DictReader(io.StringIO(proposal.csv_bytes.decode())))
    assert [float(r["y"]) for r in rows] == [3, 2, 1]
    result = imports.save_source_import(proposal, tmp_path / "native", render=True)
    assert result["exit_code"] == 0 and result["native_status"] == "passed"
    assert (tmp_path / "native/original-source.py").read_bytes() == source
    assert proposal.report["original_sha256"] == hashlib.sha256(source).hexdigest()
    assert (
        json.loads((tmp_path / "native/source-import.json").read_text())["native_report"]["status"]
        == "passed"
    )


def test_side_effects_are_not_executed_and_unsupported_original_is_retained(tmp_path):
    marker = tmp_path / "must-not-exist"
    source = f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n".encode()
    proposal = imports.import_source(source)
    assert not marker.exists() and not proposal.report["convertible"]
    assert proposal.report["unsupported_count"] == 2
    result = imports.save_source_import(proposal, tmp_path / "refused", render=True)
    assert result["exit_code"] == 1 and result["native_status"] == "not_run"
    assert (tmp_path / "refused/original-source.py").read_bytes() == source and not marker.exists()


def test_unsupported_presentation_requires_explicit_partial_review(tmp_path):
    source = "import matplotlib.pyplot as plt\nfig,ax=plt.subplots(figsize=(6,4))\nax.plot([0,1],[3,2])\n"
    proposal = imports.import_source(source)
    assert proposal.report["requires_partial_review"]
    refused = imports.save_source_import(proposal, tmp_path / "needs-review", render=True)
    assert (
        refused["exit_code"] == 1 and not (tmp_path / "needs-review/imported-source.csv").exists()
    )
    accepted = imports.save_source_import(
        proposal, tmp_path / "reviewed", accept_partial=True, render=True
    )
    assert accepted["exit_code"] == 0


def test_explicit_csv_binding_and_raw_seaborn_semantics():
    source = "import pandas as pd\nimport seaborn as sns\ndf=pd.read_csv('original-private.csv')\nsns.lineplot(data=df,x='step',y='loss',hue='model',estimator=None,errorbar=None)\n"
    missing = imports.import_source(source)
    assert not missing.report["convertible"]
    proposal = imports.import_source(source, data=b"step,loss,model\n0,3,A\n1,2,A\n0,4,B\n1,3,B\n")
    assert proposal.report["convertible"] and proposal.report["rows"] == 4
    assert proposal.report["dataset_references"] == ["original-private.csv"]
    assert proposal.report["mapped_data_identity_is_author_supplied"]
    aggregate = imports.import_source(
        source.replace(",estimator=None,errorbar=None", ""), data=b"step,loss,model\n0,3,A\n1,2,A\n"
    )
    assert (
        not aggregate.report["convertible"]
        and "aggregation" in aggregate.report["unsupported"][0]["reason"]
    )


@pytest.mark.parametrize(
    "statement",
    [
        "plt.plot([1,0],[3,2])",
        "plt.plot([0,0],[3,2])",
        "plt.bar([1,5],[3,2])",
        "plt.plot([0,1],[3,None])",
        "plt.plot([0,1],[3,2],color='red')",
    ],
)
def test_unrepresentable_semantics_refuse_or_report(statement):
    proposal = imports.import_source("import matplotlib.pyplot as plt\n" + statement)
    assert not proposal.report["convertible"] or proposal.report["requires_partial_review"]


def test_mutated_import_alias_is_not_treated_as_matplotlib():
    result = convert("import matplotlib.pyplot as plt\nplt=[1,2]\nplt.plot([0,1],[3,2])\n")
    assert not result["report"]["convertible"]


def test_source_and_ast_limits_are_refusals():
    with pytest.raises(imports.SourceImportError, match="256KiB"):
        imports.import_source("x" * (256 * 1024 + 1))
    result = imports.import_source("def broken(:\n")
    assert (
        not result.report["convertible"] and result.report["unsupported"][0]["category"] == "syntax"
    )


@pytest.mark.parametrize("kind", ["line", "scatter", "bar", "seaborn-line", "seaborn-scatter"])
def test_trusted_original_artists_match_extracted_observations(tmp_path, monkeypatch, kind):
    # Only these repository-owned fixture strings are executed to establish an oracle.
    # The importer itself never runs Python supplied by a user.
    import matplotlib.pyplot as plt
    import numpy as np

    monkeypatch.chdir(tmp_path)
    if kind.startswith("seaborn"):
        source = "import pandas as pd\nimport seaborn as sns\ndf=pd.read_csv('results.csv')\n"
        method = "lineplot" if kind.endswith("line") else "scatterplot"
        source += (
            f"sns.{method}(data=df,x='step',y='loss',hue='model'"
            + (",estimator=None,errorbar=None" if method == "lineplot" else "")
            + ")\n"
        )
        raw = b"step,loss,model\n0,3,A\n1,2,A\n0,4,B\n1,3,B\n"
        (tmp_path / "results.csv").write_bytes(raw)
    else:
        x = "['A','B','C']" if kind == "bar" else "[0,1,2]"
        method = "plot" if kind == "line" else kind
        source = f"import matplotlib.pyplot as plt\nplt.{method}({x},[3,2,1])\n"
        raw = None
    figure = plt.figure()
    try:
        exec(compile(source, "trusted-fixture.py", "exec"), {})  # noqa: S102
        axes = figure.axes[0]
        if kind.endswith("line"):
            artists = [
                np.column_stack(line.get_data()).astype(float)
                for line in axes.lines
                if len(line.get_xdata())
            ]
        elif kind.endswith("scatter"):
            artists = [
                np.asarray(item.get_offsets(), dtype=float)
                for item in axes.collections
                if len(item.get_offsets())
            ]
        else:
            artists = [np.array([[i, bar.get_height()] for i, bar in enumerate(axes.patches)])]
        proposal = imports.import_source(source, data=raw)
        assert proposal.report["convertible"] and proposal.report["all_statements_supported"]
        if kind.startswith("seaborn"):
            assert proposal.spec["x"]["label"] == axes.get_xlabel() == "step"
            assert proposal.spec["y"]["label"] == axes.get_ylabel() == "loss"
            assert (
                proposal.spec["legend"]["title"]
                == axes.get_legend().get_title().get_text()
                == "model"
            )
        rows = list(csv.DictReader(io.StringIO(proposal.csv_bytes.decode())))
        if kind == "bar":
            assert [row["x"] for row in rows] == ["A", "B", "C"]
            expected = np.array([[i, float(row["y"])] for i, row in enumerate(rows)])
        else:
            expected = np.array([[float(row["x"]), float(row["y"])] for row in rows])
        np.testing.assert_array_equal(np.concatenate(artists), expected)
        assert (
            imports.save_source_import(proposal, tmp_path / "native", render=True)["native_status"]
            == "passed"
        )
    finally:
        plt.close(figure)


@pytest.mark.parametrize(
    "source",
    [
        "matplotlib.pyplot.plot([0,1],[2,3])",
        "import matplotlib.pyplot as plt\nimport pandas as pd\nplt=pd.read_csv('a.csv')\nplt.plot([0,1],[2,3])",
        "import matplotlib.pyplot as plt\nplt.plot(x=[0,1],y=[2,3])",
        "import seaborn as sns\nsns.scatterplot(x=[0,1],y=[2,3],estimator=None)",
        "import matplotlib.pyplot as plt\nx=[0,1]\ny=[2,3]\nx.append(2)\nplt.plot(x,y)",
        "import matplotlib.pyplot as plt\nplt.plot([0,1],[2,3],label='a',label='b')",
    ],
)
def test_invalid_or_changed_bindings_do_not_claim_conversion(source):
    assert not imports.import_source(source).report["convertible"]


def test_native_failure_is_nonzero_and_preserves_report_and_original(tmp_path):
    source = b"import matplotlib.pyplot as plt\nplt.plot([0,1],[-2,-1])\nplt.yscale('log')\n"
    result = imports.save_source_import(
        imports.import_source(source), tmp_path / "failed", render=True
    )
    assert result["exit_code"] != 0 and result["native_status"] != "passed"
    assert (tmp_path / "failed/original-source.py").read_bytes() == source
    assert json.loads((tmp_path / "failed/source-import.json").read_text())["exit_code"] != 0


def test_real_cli_runs_strictly_and_never_opens_source_references(tmp_path):
    source = tmp_path / "trusted.py"
    source.write_text(
        "import pandas as pd\nimport matplotlib.pyplot as plt\ndf=pd.read_csv('missing.csv')\nplt.plot(df['x'],df['y'])\n"
    )
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "graphunslopify.cli",
            "import-source",
            str(source),
            "--out-dir",
            str(tmp_path / "refused"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 1 and not json.loads(run.stdout)["import"]["convertible"]
    data = tmp_path / "bound.csv"
    data.write_text("x,y\n0,3\n1,2\n")
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "graphunslopify.cli",
            "import-source",
            str(source),
            "--data",
            str(data),
            "--out-dir",
            str(tmp_path / "native"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0 and json.loads(run.stdout)["native_status"] == "passed", (
        run.stdout + run.stderr
    )
