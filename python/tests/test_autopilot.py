"""Actual owned planning and all-three native drafts with explicit scientific review."""

import hashlib
import json
from pathlib import Path

import pytest

from graphunslopify.autopilot import AutopilotError, generate_drafts, propose_figures


@pytest.fixture
def source(tmp_path):
    p = tmp_path / "results.csv"
    p.write_text("model,loss,step\nA,1.1,0\nA,2.2,1\nA,3.3,2\nB,2.4,0\nB,3.5,1\nB,4.6,2\n")
    return p


@pytest.mark.parametrize(
    "question,kinds",
    [
        ("How does loss differ between models?", ["box", "ecdf", "bar"]),
        ("How does loss change with step?", ["scatter", "line", "ecdf"]),
        ("Show the distribution of loss", ["ecdf", "box", "scatter"]),
    ],
)
def test_question_grounded_three_actual_strict_native_views(source, tmp_path, question, kinds):
    original = source.read_bytes()
    plan = propose_figures(source, question)
    assert plan.report["ready"] and plan.report["choices"]["target"] == "loss"
    assert plan.report["question"] == question and plan.report["choices"]["units"] == {}
    assert [d["spec"]["kind"] for d in plan.drafts] == kinds
    assert all(d["native_status"] == "not_run" for d in plan.drafts)
    assert all(d["why"] and d["tradeoff"] and d["assumptions"] for d in plan.drafts)
    assert not plan.report["scientific_appropriateness_certified"]
    result = generate_drafts(plan, tmp_path / "drafts", reviewed=True)
    assert result["status"] == "passed" and result["exit_code"] == 0
    assert len(result["drafts"]) == 3 and all(d["status"] == "passed" for d in result["drafts"])
    assert all(d["native_report"]["policy"]["strict"] for d in result["drafts"])
    assert all(d["native_report"]["data"]["counts"]["prepared"] == 6 for d in result["drafts"])
    assert (
        source.read_bytes() == original
        and plan.report["original_sha256"] == hashlib.sha256(original).hexdigest()
    )


def test_review_exclusions_and_source_identity_are_required(source, tmp_path):
    with source.open("a") as out:
        out.write("A,,3\n")
    plan = propose_figures(source, "Compare loss between models")
    assert plan.report["excluded_count"] == 1
    assert plan.report["excluded_records"][0]["source_record"] == 6
    with pytest.raises(AutopilotError, match="Review"):
        generate_drafts(plan, tmp_path / "unreviewed")
    with pytest.raises(AutopilotError, match="exclusions"):
        generate_drafts(plan, tmp_path / "unaccepted", reviewed=True)
    with source.open("a") as out:
        out.write("B,7,3\n")
    with pytest.raises(AutopilotError, match="Dataset changed"):
        generate_drafts(plan, tmp_path / "stale", reviewed=True, accept_exclusions=True)
    assert not (tmp_path / "stale").exists()


@pytest.mark.parametrize("change", ["question", "choices", "data", "draft", "exclusions"])
def test_proposal_snapshot_fences_every_reviewed_component(source, tmp_path, change):
    plan = propose_figures(source, "Compare loss between models")
    if change == "question":
        plan.report["question"] = "Another question"
    elif change == "choices":
        plan.report["choices"]["units"] = {"loss": "%"}
    elif change == "data":
        plan.data_bytes = plan.data_bytes.replace(b"1.1", b"9.9")
    elif change == "draft":
        plan.drafts[0]["spec"]["y"]["unit"] = "%"
    else:
        plan.report["excluded_count"] = 7
    with pytest.raises(AutopilotError, match="changed; review"):
        generate_drafts(plan, tmp_path / "tampered", reviewed=True)
    assert not (tmp_path / "tampered").exists()


def test_ambiguous_question_needs_mapping_instead_of_fake_three(source):
    plan = propose_figures(source, "What can be learned?")
    assert not plan.report["ready"] and not plan.drafts and plan.data_bytes is None
    selected = propose_figures(
        source,
        "What can be learned?",
        intent="comparison",
        target="loss",
        group="model",
        units={"loss": "score"},
    )
    assert selected.report["ready"] and len(selected.drafts) == 3
    assert selected.report["choices"]["units"] == {"loss": "score"}
    assert selected.drafts[0]["spec"]["y"]["unit"] == "score"
    assert not selected.report["data_sent_to_model"]


def test_univariate_data_has_three_distinct_descriptive_views(tmp_path):
    source = tmp_path / "one.csv"
    source.write_text("loss\n1.5\n2.5\n3.5\n")
    plan = propose_figures(source, "Describe the distribution of loss")
    assert plan.report["ready"] and [d["spec"]["kind"] for d in plan.drafts] == [
        "ecdf",
        "box",
        "scatter",
    ]
    rows = json.loads(plan.data_bytes)
    assert [r["source_record"] for r in rows] == [0, 1, 2]
    assert [r["measure"] for r in rows] == [1.5, 2.5, 3.5]
    assert "not time" in plan.drafts[2]["spec"]["x"]["label"]


@pytest.mark.parametrize("suffix", [".csv", ".json", ".parquet", ".xlsx"])
def test_actual_readers_preserve_leading_zero_group_identities(tmp_path, suffix):
    import pandas as pd

    frame = pd.DataFrame({"id": ["001", "001", "002", "002"], "loss": [1.1, 2.2, 3.3, 4.4]})
    source = tmp_path / ("identities" + suffix)
    choices = {"target": "loss", "group": "id", "intent": "comparison"}
    if suffix == ".csv":
        frame.to_csv(source, index=False)
    elif suffix == ".json":
        source.write_text(frame.to_json(orient="records"))
    elif suffix == ".parquet":
        frame.to_parquet(source, index=False)
    else:
        frame.to_excel(source, sheet_name="Results", index=False)
        choices["sheet"] = "Results"
    plan = propose_figures(source, "Compare loss between id groups", **choices)
    assert plan.report["ready"] and plan.report["groups"] == ["001", "002"]
    assert [r["group"] for r in json.loads(plan.data_bytes)] == ["001", "001", "002", "002"]
    result = generate_drafts(plan, tmp_path / "native", reviewed=True)
    assert result["status"] == "passed" and len(result["drafts"]) == 3
    assert all(d["native_report"]["data"]["counts"]["prepared"] == 4 for d in result["drafts"])


def test_public_penguins_question_keeps_reviewed_actual_observations(tmp_path):
    import numpy as np
    import pandas as pd

    source = Path(__file__).resolve().parents[2] / "benchmarks/papers/sources/penguins.csv"
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    frame = pd.read_csv(source)
    plan = propose_figures(source, "Compare body mass between species")
    assert plan.report["choices"]["target"] == "body_mass_g"
    assert plan.report["choices"]["group"] == "species"
    valid = np.isfinite(frame["body_mass_g"]) & frame["species"].notna()
    assert plan.report["selected_rows"] == int(valid.sum())
    assert plan.report["excluded_count"] == int((~valid).sum())
    rows = json.loads(plan.data_bytes)
    assert [r["measure"] for r in rows] == frame.loc[valid, "body_mass_g"].tolist()
    assert [r["group"] for r in rows] == frame.loc[valid, "species"].tolist()
    assert [r["source_record"] for r in rows] == list(frame.index[valid])
    result = generate_drafts(
        plan, tmp_path / "public-native", reviewed=True, accept_exclusions=True
    )
    assert result["status"] == "passed" and len(result["drafts"]) == 3
    assert all(
        d["native_report"]["data"]["counts"]["prepared"] == int(valid.sum())
        for d in result["drafts"]
    )
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


def test_strict_layout_failure_keeps_all_three_actual_verdicts(tmp_path):
    source = tmp_path / "long.csv"
    source.write_text(
        "model,loss\n"
        + "\n".join(
            f"{label},{value}"
            for label, value in [("A" * 250, 1), ("A" * 250, 2), ("B" * 250, 3), ("B" * 250, 4)]
        )
        + "\n"
    )
    plan = propose_figures(source, "Compare loss between models")
    result = generate_drafts(plan, tmp_path / "failed-native", reviewed=True)
    assert result["exit_code"] == 2 and result["status"] == "incomplete"
    assert len(result["drafts"]) == 3 and any(d["status"] != "passed" for d in result["drafts"])
    saved = json.loads((tmp_path / "failed-native/autopilot.json").read_text())
    assert [d["status"] for d in saved["drafts"]] == [d["status"] for d in result["drafts"]]
    assert all(d["native_report"] is not None for d in result["drafts"])


def test_explicit_temporal_predictor_is_not_inferred_as_a_group(tmp_path):
    source = tmp_path / "dates.csv"
    source.write_text(
        "date,model,loss\n2026-01-01,A,4\n2026-01-02,A,3\n2026-01-01,B,5\n2026-01-02,B,4\n"
    )
    plan = propose_figures(
        source, "How does loss change with date?", predictor="date", predictor_temporal=True
    )
    assert plan.report["ready"] and plan.report["choices"]["group"] == "model"
    assert plan.drafts[0]["spec"]["x"]["temporal"] and plan.drafts[1]["spec"]["x"]["temporal"]
    result = generate_drafts(plan, tmp_path / "temporal-native", reviewed=True)
    assert result["status"] == "passed" and len(result["drafts"]) == 3
