"""Exact manuscript passages bound to actual deterministic audit results."""

from __future__ import annotations

import hashlib
import json
import shutil

import pytest

from graphunslopify.cli import main
from graphunslopify.project import ProjectError, initialize_project, run_project
from graphunslopify.project_claim_links import (
    project_claim_links,
    remove_claim_link,
    review_claim_link,
    save_claim_link,
)

TEXT = "Arm A has a higher mean than Arm B at every recorded visit."
INPUT = b"visit,arm,value\n1,A,8\n1,A,6\n1,B,3\n1,B,5\n2,A,10\n2,A,8\n2,B,5\n2,B,7\n"
CONTRADICTORY = INPUT.replace(b"2,A,10\n2,A,8", b"2,A,2\n2,A,4")
FIGURE = {
    "kind": "line",
    "title": "Two arms over time",
    "aggregation": "mean",
    "marker": True,
    "data": {"path": "input.csv", "format": "csv"},
    "x": {"field": "visit", "label": "Visit"},
    "y": {"field": "value", "label": "Response"},
    "group": "arm",
    "caption": TEXT,
    "output": {"stem": "response", "formats": ["png"], "dpi": 144},
    "claims": [{"kind": "beats_everywhere", "subject": "A", "reference": "B"}],
}


@pytest.fixture(scope="module")
def audited(tmp_path_factory):
    paper = tmp_path_factory.mktemp("claim-link-paper")
    (paper / "input.csv").write_bytes(INPUT)
    (paper / "paper.tex").write_text("Results\n" + TEXT + "\nDiscussion\n", encoding="utf8")
    (paper / "response.figure.json").write_text(json.dumps(FIGURE))
    (paper / "graphunslopify.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "figures": [{"id": "response", "spec": "response.figure.json"}],
            }
        )
    )
    initialize_project(paper)
    run = run_project(paper)
    assert run["exit_code"] == 0, run
    return paper


@pytest.fixture
def paper(audited, tmp_path):
    return shutil.copytree(audited, tmp_path / "moved paper")


def draft(paper, anchor=None):
    (row,) = project_claim_links(paper)["figures"]
    (check,) = row["checks"]
    return {
        "figure": row["id"],
        "check": check["id"],
        "anchor": anchor
        or {
            "kind": "manuscript",
            "path": "paper.tex",
            "text": TEXT,
        },
    }


def confirm(paper, proposal):
    review = review_claim_link(paper, proposal)
    return save_claim_link(paper, proposal, review_sha256=review["review_sha256"], confirmed=True)


def test_link_tracks_real_current_claim_change_and_export_integrity(paper):
    proposal = draft(paper)
    review = review_claim_link(paper, proposal)
    assert review["location"]["first_line"] == review["location"]["last_line"] == 2
    assert review["check_result"]["verdict"] == "holds"
    assert review["evidence"]["data_sha256"] == hashlib.sha256(INPUT).hexdigest()
    links_path = paper / "graphunslopify-project/claim-links.json"
    assert not links_path.exists()
    with pytest.raises(ProjectError, match="Confirm"):
        save_claim_link(paper, proposal, review_sha256=review["review_sha256"], confirmed=False)
    assert not links_path.exists()
    saved = confirm(paper, proposal)
    assert saved["link"]["status"] == "supported"
    old = saved["link"]["evidence"]["event"]
    original = links_path.read_bytes()
    (paper / "input.csv").write_bytes(CONTRADICTORY)
    before = project_claim_links(paper)
    assert before["links"][0]["status"] == "stale_figure"
    assert before["links"][0]["check_result"] is None
    failed = run_project(paper)
    assert failed["exit_code"] == 2
    report = project_claim_links(paper)
    (current,) = report["links"]
    assert report["exit_code"] == 2 and current["status"] == "contradiction"
    assert current["evidence"]["event"] == failed["id"] != old
    assert current["check_result"]["verdict"] == "fails"
    assert current["evidence"]["data_sha256"] == hashlib.sha256(CONTRADICTORY).hexdigest()
    assert original == links_path.read_bytes()
    (artifact,) = (
        row for row in failed["audit"]["figures"][0]["outputs"] if row["format"] == "png"
    )
    export = paper / "graphunslopify-project/history" / failed["id"] / "audit" / artifact["path"]
    export.write_bytes(b"replaced")
    (damaged,) = project_claim_links(paper)["links"]
    assert damaged["status"] == "stale_figure" and damaged["check_result"] is None


def test_text_change_relocation_ambiguity_and_guarded_removal(paper):
    proposal = draft(paper)
    review = review_claim_link(paper, proposal)
    manuscript = paper / "paper.tex"
    manuscript.write_text("Introduction\nResults\n" + TEXT + "\n", encoding="utf8")
    with pytest.raises(ProjectError, match="changed since review"):
        save_claim_link(paper, proposal, review_sha256=review["review_sha256"], confirmed=True)
    saved = confirm(paper, proposal)
    assert saved["link"]["location"]["first_line"] == 3
    with pytest.raises(ProjectError, match="already links"):
        review_claim_link(paper, proposal)
    manuscript.write_text("New introduction\n" + TEXT, encoding="utf8")
    (moved,) = project_claim_links(paper)["links"]
    assert moved["status"] == "supported" and moved["location"]["first_line"] == 2
    manuscript.write_text(TEXT + "\n" + TEXT, encoding="utf8")
    (stale,) = project_claim_links(paper)["links"]
    assert stale["status"] == "stale_text" and stale["check_result"] is None
    with pytest.raises(ProjectError, match="changed"):
        remove_claim_link(paper, stale["id"], links_revision=review["links_revision"])
    assert (
        remove_claim_link(paper, stale["id"], links_revision=saved["links_revision"])["status"]
        == "removed"
    )
    assert project_claim_links(paper)["links"] == []


def test_caption_and_cli_do_not_change_manuscript_or_definition(paper, tmp_path, capsys):
    proposal = draft(paper, {"kind": "caption", "text": TEXT})
    file = tmp_path / "proposal.json"
    file.write_text(json.dumps(proposal))
    figure = (paper / "response.figure.json").read_bytes()
    manuscript = (paper / "paper.tex").read_bytes()
    args = ["project-claim-links", str(paper), "--draft", str(file)]
    assert main(args) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["status"] == "review_required"
    assert main([*args, "--confirm", plan["review_sha256"]]) == 0
    assert json.loads(capsys.readouterr().out)["link"]["status"] == "supported"
    assert (paper / "response.figure.json").read_bytes() == figure
    assert (paper / "paper.tex").read_bytes() == manuscript
    changed = {**FIGURE, "caption": "A different caption without the linked statement."}
    (paper / "response.figure.json").write_text(json.dumps(changed))
    assert main(["project-claim-links", str(paper)]) == 2
    assert json.loads(capsys.readouterr().out)["links"][0]["status"] == "stale_text"


def test_path_escape_and_indeterminate_claim_are_distinct(paper):
    invalid = draft(paper, {"kind": "manuscript", "path": "../paper.tex", "text": TEXT})
    with pytest.raises(ProjectError, match="inside"):
        review_claim_link(paper, invalid)
    saved = confirm(paper, draft(paper))
    (paper / "input.csv").write_bytes(
        b"\n".join(line for line in INPUT.splitlines() if b",B," not in line) + b"\n"
    )
    result = run_project(paper)
    assert result["exit_code"] == 2
    (current,) = project_claim_links(paper)["links"]
    assert current["id"] == saved["link"]["id"] and current["status"] == "untested"
    assert current["check_result"]["verdict"] == "untested"
