"""Real CLI review/replay,strict native outcomes and unchanged-source review fences."""

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from graphunslopify.autopilot import AutopilotError, propose_figures
from graphunslopify.autopilot_review import (
    MAX_REVIEW,
    generate_reviewed,
    read_review,
    review_document,
    write_review,
)


@pytest.fixture
def reviewed(tmp_path):
    source = tmp_path / "observations.csv"
    source.write_text("model,loss\nA,1\nA,3\nB,2\nB,4\nA,\n")
    return source, review_document(propose_figures(source, "Compare loss between models"))


def cli(tmp_path, *args):
    env = dict(os.environ)
    # Keep the selected source/installed environment when changing working directory.
    if "PYTHONPATH" in env:
        env["PYTHONPATH"] = os.pathsep.join(
            str(Path(p or ".").resolve()) for p in env["PYTHONPATH"].split(os.pathsep)
        )
    run = subprocess.run(
        [sys.executable, "-m", "graphunslopify.cli", *map(str, args)],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert run.stdout, run.stderr
    return run, json.loads(run.stdout)


def test_actual_cli_reviews_then_generates_all_three_with_explicit_exclusions(tmp_path, reviewed):
    source, _ = reviewed
    original = source.read_bytes()
    review = tmp_path / "review.json"
    run, document = cli(
        tmp_path,
        "autopilot-propose",
        source,
        "--question",
        "Compare loss between models",
        "--out",
        review,
        "--units",
        '{"loss":"score"}',
    )
    assert run.returncode == 0 and document == read_review(review)
    assert document["report"]["excluded_count"] == 1
    assert document["report"]["choices"]["units"] == {"loss": "score"}
    for flags, name in [([], "unreviewed"), (["--reviewed"], "unaccepted-exclusions")]:
        folder = tmp_path / name
        run, refused = cli(tmp_path, "autopilot-generate", review, "--out-dir", folder, *flags)
        assert run.returncode == refused["exit_code"] == 2 and not folder.exists()
    folder = tmp_path / "native"
    run, result = cli(
        tmp_path,
        "autopilot-generate",
        review,
        "--out-dir",
        folder,
        "--reviewed",
        "--accept-exclusions",
    )
    assert run.returncode == result["exit_code"] == 0 and result["status"] == "passed"
    assert len(result["drafts"]) == 3 and all(d["status"] == "passed" for d in result["drafts"])
    assert all(d["native_report"]["policy"]["strict"] for d in result["drafts"])
    assert json.loads((folder / "autopilot.json").read_text()) == result
    assert read_review(folder / "reviewed-proposal.json") == document
    assert result["review"]["fingerprint"] == document["fingerprint"]
    assert result["review"]["acknowledged"] and result["review"]["exclusions_acknowledged"]
    assert source.read_bytes() == original


@pytest.mark.parametrize("component", ["question", "choices", "report", "draft"])
def test_review_document_changes_refuse_before_any_output(tmp_path, reviewed, component):
    source, original = reviewed
    document = copy.deepcopy(original)
    if component == "question":
        document["request"]["question"] = "A different research question"
    elif component == "choices":
        document["request"]["choices"]["units"] = {"loss": "%"}
    elif component == "report":
        document["report"]["excluded_count"] = 0
    else:
        document["drafts"][0]["spec"]["y"]["label"] = "Changed interpretation"
    review = tmp_path / "tampered.json"
    review.write_text(json.dumps(document))
    with pytest.raises(AutopilotError, match="changed"):
        generate_reviewed(
            read_review(review), tmp_path / "refused", reviewed=True, accept_exclusions=True
        )
    assert not (tmp_path / "refused").exists() and source.exists()


def test_actual_source_change_invalidates_an_unchanged_saved_review(tmp_path, reviewed):
    source, document = reviewed
    review = tmp_path / "review.json"
    write_review(document, review)
    with source.open("a") as stream:
        stream.write("B,9\n")
    run, result = cli(
        tmp_path,
        "autopilot-generate",
        review,
        "--out-dir",
        tmp_path / "stale",
        "--reviewed",
        "--accept-exclusions",
    )
    assert run.returncode == result["exit_code"] == 2 and "changed" in result["error"]
    assert not (tmp_path / "stale").exists()


def test_review_export_never_overwrites_the_source(tmp_path, reviewed):
    source, document = reviewed
    before = source.read_bytes()
    with pytest.raises(FileExistsError):
        write_review(document, source)
    assert source.read_bytes() == before


def test_review_input_is_bounded_without_reading_a_sparse_oversized_file(tmp_path):
    path = tmp_path / "oversized.json"
    with path.open("wb") as stream:
        stream.truncate(MAX_REVIEW + 1)
    with pytest.raises(ValueError, match="bounded"):
        read_review(path)


def test_cli_unresolved_question_shape_stays_exportable_and_cannot_generate(tmp_path):
    source = tmp_path / "one-group.csv"
    source.write_text("model,loss\nA,1\nA,2\n")
    review = tmp_path / "unresolved.json"
    run, document = cli(
        tmp_path,
        "autopilot-propose",
        source,
        "--question",
        "Compare loss between models",
        "--out",
        review,
    )
    assert run.returncode == 2 and not document["report"]["ready"]
    assert review.exists() and document["drafts"] == []
    run, result = cli(
        tmp_path,
        "autopilot-generate",
        review,
        "--out-dir",
        tmp_path / "unsupported",
        "--reviewed",
        "--accept-exclusions",
    )
    assert run.returncode == result["exit_code"] == 2 and not (tmp_path / "unsupported").exists()


def test_actual_cli_binds_the_selected_worksheet_and_author_units(tmp_path):
    import pandas as pd

    source = tmp_path / "two-sheets.xlsx"
    frame = pd.DataFrame({"model": ["A", "A", "B", "B"], "loss": [1, 3, 2, 4]})
    with pd.ExcelWriter(source, engine="openpyxl") as workbook:
        pd.DataFrame({"irrelevant": [99]}).to_excel(workbook, sheet_name="Ignore", index=False)
        frame.to_excel(workbook, sheet_name="Measured", index=False)
    run, document = cli(
        tmp_path,
        "autopilot-propose",
        source,
        "--question",
        "Compare loss between models",
        "--sheet",
        "Measured",
        "--target",
        "loss",
        "--group",
        "model",
        "--intent",
        "comparison",
        "--units",
        '{"loss":"score"}',
        "--out",
        tmp_path / "worksheet-review.json",
    )
    assert run.returncode == 0 and document["report"]["ready"]
    assert document["report"]["choices"]["sheet"] == "Measured"
    assert document["request"]["choices"]["sheet"] == "Measured"
    assert document["report"]["selected_rows"] == 4 and len(document["drafts"]) == 3
