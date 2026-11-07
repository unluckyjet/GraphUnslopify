"""Actual mixed saved packets, parent strict failures, original ancestry and guarded reads."""

import hashlib
import io
import json
import shutil
import zipfile
from pathlib import Path

import pytest

from graphunslopify import audit as auditing
from graphunslopify import project as model
from graphunslopify import project_export as packets
from graphunslopify import project_review as reviews
from graphunslopify.cli import main
from graphunslopify.project_inspections import inspect_project_pdf, project_inspections

ROOT = Path(__file__).resolve().parents[2]


def load(path):
    return json.loads(path.read_text())


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def inventory(root):
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


@pytest.fixture(scope="module")
def accepted(tmp_path_factory):
    folder = tmp_path_factory.mktemp("review-packet")
    root = folder / "paper <img src=x onerror=alert(1)>"
    shutil.copytree(ROOT / "examples/paper", root)
    pdf = root / "private original.pdf"
    pdf.write_bytes((ROOT / "python/tests/fixtures/project-review-pages.pdf").read_bytes())
    model.initialize_project(root)
    first = model.run_project(root, baseline=None)
    second = model.run_project(root, selective=True, baseline=None)
    assert first["exit_code"] == second["exit_code"] == 0
    visual = inspect_project_pdf(
        root,
        pdf,
        identity="foreign",
        expected_revision=project_inspections(root)["revision"],
        pages=[1],
        dpi=72,
        source_name="<script>foreign</script>.pdf",
    )
    assert visual["exit_code"] == 2
    backup = folder / "backup"
    shutil.copytree(root, backup)
    return root, backup, first, second, visual


@pytest.fixture
def paper(accepted):
    root, backup, first, second, visual = accepted
    shutil.rmtree(root)
    shutil.copytree(backup, root)
    return root, first, second, visual


def packet(root, event=None, token=None):
    review = reviews.project_review(root, event_id=event)
    raw = packets.create_review_packet(
        root, event_id=event, expected_revision=token or review["evidence_revision"]
    )
    z = zipfile.ZipFile(io.BytesIO(raw))
    return z, json.loads(z.read("review.json")), review


def test_review_panel_checks_real_native_and_pdf_bytes_in_separate_roles(
    paper, monkeypatch, capsys
):
    root, _, _, _ = paper
    review = reviews.project_review(root)
    before = inventory(root)

    def forbidden(*args, **kwargs):
        raise AssertionError("The deterministic panel must not run figure programs")

    monkeypatch.setattr(auditing, "_run", forbidden)
    assert (
        main(
            [
                "project-review-panel",
                str(root),
                "--journal-profile",
                "plos-one-main",
                "--expected-revision",
                review["evidence_revision"],
            ]
        )
        == 0
    )
    panel = json.loads(capsys.readouterr().out)
    assert inventory(root) == before
    assert panel["model_review"] == "not_requested"
    assert panel["journal_profile"]["id"] == "plos-one-main"
    assert panel["matches_current_native_revision"]
    assert [row["figure_key"] for row in panel["figures"]] == [
        "training",
        "results-table",
        "pdf:foreign",
    ]
    line, _, pdf = panel["figures"]
    assert line["statistical_claims"]["claims"]["items"][0]["verdict"] == "holds"
    assert line["readability"] == review["figures"][0]["groups"]["legibility"]
    exports = line["journal_formatting"]["exports"]
    assert {Path(row["name"]).suffix for row in exports} == {".png", ".svg", ".pdf"}
    png = next(row for row in exports if row["name"].endswith(".png"))
    assert any(
        row["code"] == "file_format" and row["status"] == "failed"
        for row in png["report"]["checks"]
    )
    assert pdf["statistical_claims"]["claims"]["state"] == "untested"
    assert pdf["readability"]["state"] == "visual_only"
    [measured] = pdf["journal_formatting"]["exports"]
    assert (
        measured["sha256"]
        == hashlib.sha256((root / "private original.pdf").read_bytes()).hexdigest()
    )
    assert all("path" not in result for result in exports)


def test_review_panel_keeps_changed_pdf_and_unselected_profile_explicit(paper):
    from graphunslopify.review_panel import paper_review_panel

    root, _, _, _ = paper
    first = paper_review_panel(root, figures=["pdf:foreign"])
    assert first["figures"][0]["journal_formatting"]["state"] == "profile_required"
    source = root / "private original.pdf"
    source.write_bytes(source.read_bytes() + b"\n% changed source\n")
    with pytest.raises(model.ProjectError, match="Paper evidence changed"):
        paper_review_panel(root, expected_revision=first["evidence_revision"])
    current = paper_review_panel(root, figures=["pdf:foreign"], journal_profile="plos-one-main")
    [pdf] = current["figures"]
    assert pdf["journal_formatting"] == {"state": "evidence_unavailable", "exports": []}
    assert pdf["statistical_claims"]["claims"]["state"] == "untested"
    with pytest.raises(model.ProjectError, match="distinct current figure keys"):
        paper_review_panel(root, figures=["pdf:foreign", "pdf:foreign"])
    with pytest.raises(model.ProjectError, match="supported journal profile"):
        paper_review_panel(root, journal_profile="unspecified-policy")


def test_review_panel_preserves_failed_native_claim_when_journal_checks_are_available(paper):
    from graphunslopify.review_panel import paper_review_panel

    root, _, _, _ = paper
    file = root / "training.figure.json"
    spec = load(file)
    spec["claims"][0].update(subject="base", reference="ours")
    save(file, spec)
    assert model.run_project(root, baseline=None)["exit_code"] == 2
    panel = paper_review_panel(root, figures=["training"], journal_profile="nature-final-graphs")
    [figure] = panel["figures"]
    assert panel["matches_current_native_revision"]
    assert figure["recorded_outcome"] == "failed"
    assert figure["statistical_claims"]["claims"]["items"][0]["verdict"] == "fails"
    assert figure["journal_formatting"]["state"] == "recorded"


def test_actual_mixed_packet_preserves_files_groups_parent_counts_and_original_executions(
    paper, monkeypatch
):
    root, first, second, _ = paper
    before = inventory(root)

    def forbidden(*args, **kwargs):
        raise AssertionError("Export must not execute a figure or context probe")

    monkeypatch.setattr(auditing, "_run", forbidden)
    z, result, review = packet(root)
    assert inventory(root) == before
    assert result["review"] == review
    assert not result["science_reexecuted"] and not result["source_data_included"]
    assert not result["source_programs_included"] and not result["original_pdfs_included"]
    assert review["native_run"]["id"] == second["id"]
    assert review["native_run"]["execution_counts"] == {"executed": 0, "reused": 2, "not_run": 0}
    assert len(result["figures"]) == 3
    assert all(
        set(f["groups"]) == {"claims", "uncertainty", "legibility", "reproduction"}
        for f in result["figures"]
    )
    assert all(a["state"] == "included" for a in result["assets"])
    assert "receipts/" + first["id"] + ".json" in z.namelist()
    assert "reports/ancestry/" + first["id"] + ".json" in z.namelist()
    assert json.loads(z.read("reports/native-audit.json")) == second["audit"]
    assert all(
        not name.endswith((".py", ".csv")) and "private original.pdf" not in name
        for name in z.namelist()
    )
    assert all(
        raw != (root / "private original.pdf").read_bytes()
        for raw in (z.read(n) for n in z.namelist())
    )
    manifest = json.loads(z.read("manifest.json"))
    assert {m["path"] for m in manifest["files"]} == set(z.namelist()) - {"manifest.json"}
    for item in manifest["files"]:
        raw = z.read(item["path"])
        assert len(raw) == item["bytes"] and hashlib.sha256(raw).hexdigest() == item["sha256"]
    html = z.read("index.html").decode()
    assert "<script>" not in html and "<img src=x" not in html
    assert "&lt;img src=x" in html and "&lt;script&gt;foreign" in html
    assert all(name.isascii() for name in z.namelist())
    assert "numerical claims/data untested" in html


def test_explicit_native_history_excludes_later_pdf_and_retains_removed_figures(paper):
    root, first, _, _ = paper
    model.set_project_entry(
        root,
        "results-table",
        None,
        expected_revision=model.project_status(root)["revision"],
        mode="remove",
    )
    z, result, _ = packet(root, first["id"])
    assert len(result["figures"]) == 2 and not any(
        f["key"].startswith("pdf:") for f in result["figures"]
    )
    removed = next(f for f in result["figures"] if f["id"] == "results-table")
    assert removed["state"] == "historical_removed_figure"
    assert removed["groups"]["claims"]["state"] != "unavailable"
    assert not any(name.startswith("figures/pdf/") for name in z.namelist())


def test_explicit_pdf_history_excludes_unrelated_native_paper(paper):
    root, _, _, visual = paper
    z, result, _ = packet(root, visual["id"])
    assert result["review"]["native_run"] is None and len(result["figures"]) == 1
    assert result["figures"][0]["groups"]["claims"]["state"] == "untested"
    assert not any(name.startswith("figures/native/") for name in z.namelist())


def test_no_run_packet_stays_not_run_and_source_data_is_not_copied(tmp_path):
    shutil.copytree(ROOT / "examples/paper", tmp_path, dirs_exist_ok=True)
    model.initialize_project(tmp_path)
    z, result, _ = packet(tmp_path)
    assert result["review"]["native_run"] is None
    assert all(f["state"] == "not_run" for f in result["figures"])
    assert not result["assets"] and not any(name.startswith("figures/") for name in z.namelist())


@pytest.mark.parametrize("damage", ["delete", "append"])
def test_unavailable_saved_output_is_reported_without_copying_changed_bytes(paper, damage):
    root, _, second, _ = paper
    item = next(o for o in second["audit"]["figures"][0]["outputs"] if o["format"] == "png")
    file = Path(second["directory"]) / "audit" / item["path"]
    if damage == "delete":
        file.unlink()
    else:
        file.write_bytes(file.read_bytes() + b"changed")
    z, result, _ = packet(root)
    missing = [a for a in result["assets"] if a["original_path"] == item["path"]]
    assert (
        len(missing) == 1 and missing[0]["state"] == "unavailable" and not missing[0]["packet_path"]
    )
    assert (
        next(f for f in result["figures"] if f["id"] == second["audit"]["figures"][0]["id"])[
            "state"
        ]
        != "current_inputs"
    )
    assert "Unavailable:" in z.read("index.html").decode()


def test_parent_baseline_rejection_is_retained_even_when_native_science_passes(paper):
    root, _, second, _ = paper
    item = next(o for o in second["audit"]["figures"][0]["outputs"] if o["format"] == "png")
    file = Path(second["directory"]) / "audit" / item["path"]
    file.write_bytes(file.read_bytes() + b"changed")
    failed = model.run_project(root, selective=True)
    assert failed["exit_code"] == 2 and all(
        f["status"] == "passed" for f in failed["audit"]["figures"]
    )
    z, result, _ = packet(root)
    assert result["review"]["native_run"]["exit_code"] == 2
    assert result["review"]["native_run"]["visual_comparison"]["preview_status"] == "partial"
    assert json.loads(z.read("reports/native-audit.json"))["exit_code"] == 2
    assert "exit 2" in z.read("index.html").decode()


def test_old_review_token_refuses_changed_actual_input_without_new_history(paper):
    root, _, _, _ = paper
    review = reviews.project_review(root)
    data = root / "results.csv"
    data.write_bytes(data.read_bytes() + b"\n")
    before = model.project_history(root)
    with pytest.raises(model.ProjectError, match="changed since selection"):
        packet(root, token=review["evidence_revision"])
    assert model.project_history(root) == before


def test_actual_receipt_byte_change_is_bound_even_when_review_fields_are_identical(paper):
    root, first, _, _ = paper
    before = reviews.project_review(root)
    path = Path(first["directory"]) / "receipt.json"
    value = load(path)
    value["export_test_metadata"] = "new external receipt annotation"
    save(path, value)
    after = reviews.project_review(root)
    assert before["evidence_revision"] != after["evidence_revision"]
    assert {k: v for k, v in before.items() if k != "evidence_revision"} == {
        k: v for k, v in after.items() if k != "evidence_revision"
    }
    with pytest.raises(model.ProjectError, match="changed since selection"):
        packet(root, token=before["evidence_revision"])


@pytest.mark.parametrize("kind", ["data", "copied_asset", "receipt"])
def test_actual_external_change_during_copy_rejects_packet(paper, monkeypatch, kind):
    root, _, second, _ = paper
    original = packets._Packet.saved
    changed = False

    def race(self, folder, item, destination, **context):
        nonlocal changed
        result = original(self, folder, item, destination, **context)
        if not changed and context.get("role") == "native_export":
            changed = True
            path = (
                root / "results.csv"
                if kind == "data"
                else folder / item["path"]
                if kind == "copied_asset"
                else Path(second["directory"]) / "receipt.json"
            )
            path.write_bytes(path.read_bytes() + b"\nchanged")
        return result

    monkeypatch.setattr(packets._Packet, "saved", race)
    with pytest.raises((model.ProjectError, OSError), match=r"changed|receipt|evidence"):
        packet(root)


def test_bounded_packet_and_busy_operation_refuse_without_figure_execution(paper, monkeypatch):
    root, _, _, _ = paper
    with (
        model._operation(root / "graphunslopify-project"),
        pytest.raises(model.ProjectError, match="locked"),
    ):
        packet(root)
    monkeypatch.setattr(packets, "MAX_PACKET_BYTES", 8)
    with pytest.raises(model.ProjectError, match="limit"):
        packet(root)


def test_real_review_only_packet_has_no_dummy_native_acceptance(tmp_path):
    model.initialize_project(tmp_path, review_only=True)
    visual = inspect_project_pdf(
        tmp_path,
        ROOT / "python/tests/fixtures/project-review-pages.pdf",
        identity="only-pdf",
        expected_revision=project_inspections(tmp_path)["revision"],
        pages=[1],
        dpi=72,
    )
    assert visual["exit_code"] == 2
    z, result, _ = packet(tmp_path)
    assert len(result["figures"]) == 1 and result["review"]["native_run"] is None
    assert result["figures"][0]["groups"]["claims"]["state"] == "untested"
    assert not any(name.startswith("figures/native/") for name in z.namelist())
    assert "reports/native-audit.json" not in z.namelist()


def test_actual_failed_claim_and_scientific_exit_remain_failed_in_packet(paper):
    root, _, _, _ = paper
    file = root / "training.figure.json"
    spec = load(file)
    spec["claims"][0].update(subject="base", reference="ours")
    save(file, spec)
    failed = model.run_project(root, baseline=None)
    assert failed["exit_code"] == 2
    z, result, _ = packet(root)
    row = next(f for f in result["figures"] if f["id"] == "training")
    assert row["execution_status"] == "failed"
    assert any(c["verdict"] == "fails" for c in row["groups"]["claims"]["items"])
    assert json.loads(z.read("reports/native-audit.json"))["exit_code"] == 2
    assert "Recorded outcome: failed" in z.read("index.html").decode()


def test_paper_audit_runs_all_native_figures_and_flags_pdf_evidence(paper, tmp_path, capsys):
    root, _, previous, _ = paper
    file = root / "training.figure.json"
    spec = load(file)
    spec["claims"][0].update(subject="base", reference="ours")
    save(file, spec)
    original = file.read_bytes()
    destination = tmp_path / "review.zip"
    assert main(["project-audit", str(root), "--output", str(destination)]) == 2
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "failed" and output["execution"] == "fresh_native_audit"
    assert output["native_audit_event"] != previous["id"] and output["native_exit_code"] == 2
    assert output["figure_count"] == 3 and file.read_bytes() == original
    assert hashlib.sha256(destination.read_bytes()).hexdigest() == output["sha256"]
    with zipfile.ZipFile(destination) as z:
        report = json.loads(z.read("review.json"))
        audit = json.loads(z.read("reports/paper-audit.json"))
        assert report["paper_audit"] == audit
        assert report["review"]["native_run"]["execution_counts"]["executed"] == 2
        assert [(row["evidence_state"], row["recorded_outcome"]) for row in audit["figures"]] == [
            ("current_audit_run", "failed"),
            ("current_audit_run", "passed"),
            ("saved_visual_evidence", "incomplete"),
        ]
        failed = next(item for item in audit["issues"] if item["code"] == "recorded_claim_failed")
        assert failed["figure"] == "native:training" and failed["priority"] == "error"
        gap = next(item for item in audit["issues"] if item["code"] == "pdf_claims_untested")
        assert gap["figure"] == "pdf:foreign" and gap["priority"] == "evidence_gap"
        for item in (failed, gap):
            value = report
            for key in item["evidence_pointer"].strip("/").split("/"):
                value = value[int(key)] if isinstance(value, list) else value[key]
            assert value.get("verdict", value.get("state")) in ("fails", "untested")
        assert audit["issues"].index(failed) < audit["issues"].index(gap)
        html = z.read("index.html").decode()
        assert "Paper audit priorities" in html and "#figure-" in html
        assert "This report ran the native figures with strict checks." in html
        assert html.count("Paper audit evidence: current audit run.") == 2
        assert "<script>foreign" not in html


def test_saved_paper_audit_discloses_stale_inputs_without_execution(paper, tmp_path, monkeypatch):
    from graphunslopify.paper_audit import audit_paper

    root, _, previous, _ = paper
    file = root / "training.figure.json"
    save(file, {**load(file), "title": "Changed after the previous run"})
    before = inventory(root)

    def forbidden(*args, **kwargs):
        raise AssertionError("Saved evidence must not execute a figure")

    monkeypatch.setattr(auditing, "_run", forbidden)
    result = audit_paper(root, tmp_path / "review.zip", saved_evidence=True)
    assert result["status"] == "incomplete" and result["exit_code"] == 2
    assert result["execution"] == "saved_evidence"
    assert result["native_audit_event"] == previous["id"]
    assert any(item["code"] == "native_evidence_unavailable" for item in result["issues"])
    assert not any(row["evidence_state"] == "current_audit_run" for row in result["figures"])
    assert inventory(root) == before
