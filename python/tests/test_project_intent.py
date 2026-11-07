"""Project-local research intent, exact acceptance, and retained history."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from graphunslopify.cli import main
from graphunslopify.project import ProjectError, initialize_project
from graphunslopify.project_intent import (
    accept_project_intent,
    project_intent,
    review_project_intent,
)

CHANGES = {
    "terminology": {"holdout": "held-out test set"},
    "model_names": {"sweep-v2": "Ablation model"},
    "units": {"latency": "µs"},
    "figure_conventions": {"legend heading": "Model variants"},
}


@pytest.fixture
def paper(tmp_path):
    return Path(initialize_project(tmp_path, review_only=True)["config"])


def test_cli_acceptance_and_later_removal_preserve_the_exact_local_history(paper, tmp_path, capsys):
    assert main(["project-intent", str(paper)]) == 0
    initial = json.loads(capsys.readouterr().out)
    assert not initial["history"] and not any(initial["entries"].values())
    proposal = tmp_path / "changes.json"
    proposal.write_text(json.dumps(CHANGES), encoding="utf8")
    flags = ["--changes", str(proposal), "--expected-revision", initial["revision"]]
    assert main(["project-review-intent", str(paper), *flags]) == 0
    reviewed = json.loads(capsys.readouterr().out)
    assert reviewed["resulting_entries"] == CHANGES
    assert all(row["before"] is None for row in reviewed["changes"])
    assert not (paper.parent / "research-intent.json").exists()
    assert (
        main(
            [
                "project-accept-intent",
                str(paper),
                *flags,
                "--review-sha256",
                reviewed["review_sha256"],
            ]
        )
        == 0
    )
    accepted = json.loads(capsys.readouterr().out)
    assert project_intent(paper.parent) == accepted
    assert accepted["history"][0]["changes"] == CHANGES

    changes = {"model_names": {"sweep-v2": None}, "units": {"latency": "ms"}}
    revision = accepted["revision"]
    reviewed = review_project_intent(paper, changes, expected_revision=revision)
    assert reviewed["changes"] == [
        {"category": "model_names", "name": "sweep-v2", "before": "Ablation model", "after": None},
        {"category": "units", "name": "latency", "before": "µs", "after": "ms"},
    ]
    edited = accept_project_intent(
        paper, changes, expected_revision=revision, review_sha256=reviewed["review_sha256"]
    )
    assert edited["entries"] == {**CHANGES, "model_names": {}, "units": {"latency": "ms"}}
    assert edited["history"][0] == accepted["history"][0]


def test_digest_scope_and_concurrent_acceptance(paper, tmp_path):
    revision = project_intent(paper)["revision"]
    reviewed = review_project_intent(paper, CHANGES, expected_revision=revision)
    with pytest.raises(ProjectError, match="exact research intent"):
        accept_project_intent(
            paper,
            {"units": {"latency": "ms"}},
            expected_revision=revision,
            review_sha256=reviewed["review_sha256"],
        )
    other = initialize_project(tmp_path, folder="other", review_only=True)["config"]
    with pytest.raises(ProjectError, match="Refresh"):
        accept_project_intent(
            other, CHANGES, expected_revision=revision, review_sha256=reviewed["review_sha256"]
        )

    def accept():
        try:
            return accept_project_intent(
                paper, CHANGES, expected_revision=revision, review_sha256=reviewed["review_sha256"]
            )
        except ProjectError as problem:
            assert "locked" in str(problem) or "Refresh" in str(problem)
            return None

    with ThreadPoolExecutor(max_workers=2) as threads:
        results = list(threads.map(lambda _: accept(), range(2)))
    assert sum(result is not None for result in results) == 1
    assert len(project_intent(paper)["history"]) == 1
    assert not project_intent(other)["history"]
    with pytest.raises(ProjectError, match="match the accepted"):
        review_project_intent(paper, CHANGES, expected_revision=project_intent(paper)["revision"])


@pytest.mark.parametrize(
    "changes",
    [
        {"aggregation": {"metric": "median"}},
        {"units": {"latency": {"factor": 1000}}},
        {"units": {"latency": "m\ns"}},
        {"units": {" latency": "ms"}},
        {"terminology": {str(i): str(i) for i in range(65)}},
    ],
)
def test_only_bounded_plain_text_changes_can_be_reviewed(paper, changes):
    state = project_intent(paper)
    with pytest.raises(ProjectError):
        review_project_intent(paper, changes, expected_revision=state["revision"])
    assert project_intent(paper) == state


def test_damaged_history_and_symlinks_refuse_to_load(paper, tmp_path):
    state = project_intent(paper)
    revision = state["revision"]
    reviewed = review_project_intent(paper, CHANGES, expected_revision=revision)
    accept_project_intent(
        paper, CHANGES, expected_revision=revision, review_sha256=reviewed["review_sha256"]
    )
    path = paper.parent / "research-intent.json"
    ledger = json.loads(path.read_bytes())
    ledger["history"][0]["changes"]["units"]["latency"] = "minutes"
    path.write_text(json.dumps(ledger), encoding="utf8")
    with pytest.raises(ProjectError, match="outside the accepted revision chain"):
        project_intent(paper)
    unrelated = tmp_path / "untouched.json"
    path.rename(unrelated)
    path.symlink_to(unrelated)
    with pytest.raises(ProjectError, match="symlink"):
        project_intent(paper)
    assert json.loads(unrelated.read_bytes()) == ledger
