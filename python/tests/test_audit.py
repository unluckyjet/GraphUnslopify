"""Real manifest runs, known data changes, artifact checks and process failures."""

from __future__ import annotations

import json
import os
import py_compile
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from PIL import Image, PngImagePlugin

from graphunslopify import Figure
from graphunslopify.audit import AuditError, audit, discover, load_manifest

DATA = "x,y,model\n1,1,base\n2,2,base\n1,4,ours\n2,5,ours\n"


def test_altered_pixels_keep_provenance_but_get_an_explicit_warning(tmp_path):
    manifest, _ = make_paper(tmp_path)
    output = tmp_path / "audit"
    first = audit(manifest, output=output)
    path = output / first["figures"][0]["outputs"][0]["path"]
    with Image.open(path) as source:
        info = PngImagePlugin.PngInfo()
        for key, value in source.text.items():
            info.add_text(key, value)
        image = source.convert("RGBA")
    image.putpixel((0, 0), (255, 0, 0, 255))
    image.save(path, pnginfo=info)
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "figures": [{"id": "main", "spec": "main.figure.json", "artifacts": [str(path)]}],
            }
        )
    )
    result = audit(manifest, output=output, fail_on_warning=True)
    assert result["status"] == "failed"
    record = result["figures"][0]
    assert record["artifacts"][0]["provenance_matches"]
    assert record["artifacts"][0]["pixels_match"] is False
    assert "pixels differ" in record["warnings"][0]


def test_malformed_baseline_fails_with_clear_error(tmp_path):
    manifest, _ = make_paper(tmp_path)
    baseline = tmp_path / "bad.json"
    baseline.write_text('{"schema_version":1,"figures":[{}]}')
    with pytest.raises(AuditError, match="valid version 1"):
        audit(manifest, output=tmp_path / "audit", baseline=baseline)


def test_script_audit_reads_actual_source_instead_of_a_stale_bytecode_cache(tmp_path):
    manifest, spec = make_paper(tmp_path)
    spec["alt_text"] = "Additional Context A."
    source = tmp_path / "source.py"
    code = Figure(spec).translate(api="local")["code"]
    source.write_text(code)
    py_compile.compile(str(source), doraise=True)
    previous = source.stat()
    source.write_text(code.replace("Context A", "Context B"))
    os.utime(source, ns=(previous.st_atime_ns, previous.st_mtime_ns))
    manifest.write_text(
        json.dumps({"schema_version": 1, "figures": [{"id": "source", "script": "source.py"}]})
    )
    result = audit(manifest, output=tmp_path / "audit")
    assert result["status"] == "passed", result
    assert "Context B" in result["figures"][0]["report"]["alt_text"]


def test_a_report_cannot_pass_by_omitting_a_requested_export(tmp_path):
    manifest, spec = make_paper(tmp_path)
    spec["output"]["formats"] = ["png", "pdf"]
    source = tmp_path / "source.py"
    code = Figure(spec).translate(api="local")["code"]
    source.write_text(
        code
        + "\noriginal_record = record_output\ndef record_output(path):\n    if Path(path).suffix != '.pdf': original_record(path)\n"
    )
    manifest.write_text(
        json.dumps({"schema_version": 1, "figures": [{"id": "source", "script": "source.py"}]})
    )
    result = audit(manifest, output=tmp_path / "audit")
    assert result["status"] == "failed"
    assert "requested output artifacts are missing: pdf" in result["figures"][0]["errors"][0]


def make_paper(root: Path, entries=None):
    root.mkdir(parents=True, exist_ok=True)
    (root / "results.csv").write_text(DATA)
    spec = {
        "kind": "line",
        "data": {"path": "results.csv"},
        "x": {"field": "x", "label": "X"},
        "y": {"field": "y", "label": "Y"},
        "group": "model",
        "aggregation": "mean",
        "legend": {"show": False},
        "claims": [{"kind": "beats_everywhere", "subject": "ours", "reference": "base"}],
        "output": {"stem": "figure", "formats": ["png"], "dpi": 100},
    }
    (root / "main.figure.json").write_text(json.dumps(spec))
    manifest = {
        "schema_version": 1,
        "figures": entries or [{"id": "main", "spec": "main.figure.json"}],
    }
    path = root / "graphunslopify.json"
    path.write_text(json.dumps(manifest))
    return path, spec


def test_directory_run_verifies_outputs_and_repeat_comparison_is_stable(tmp_path):
    manifest, _ = make_paper(tmp_path / "paper with spaces")
    output = tmp_path / "audit"
    first = audit(manifest.parent, output=output)
    baseline = output / "audit.report.json"
    old_artifact = output / first["figures"][0]["outputs"][0]["path"]
    assert first["status"] == "passed"
    assert first["figures"][0]["data"]["rows"] == 4
    assert first["figures"][0]["report"]["claims"][0]["verdict"] == "holds"
    second = audit(manifest, output=output, baseline=baseline, fail_on_change=True)
    assert second["exit_code"] == 0
    assert second["comparison"] == {"changed": False, "figures": []}
    assert old_artifact.exists()  # Old evidence is retained, never deleted/reused.
    assert (output / "audit.summary.md").is_file()
    schema = json.loads(
        (Path(__file__).resolve().parents[2] / "docs/audit-report.schema.json").read_text()
    )
    Draft202012Validator(schema).validate(second)


def test_data_numeric_pixels_and_claim_changes_are_explained(tmp_path):
    manifest, _ = make_paper(tmp_path)
    output = tmp_path / "audit"
    audit(manifest, output=output)
    baseline = tmp_path / "before.json"
    baseline.write_bytes((output / "audit.report.json").read_bytes())
    (tmp_path / "results.csv").write_text(DATA.replace("2,5,ours", "2,0,ours"))
    result = audit(manifest, output=output, baseline=baseline, fail_on_change=True)
    assert result["exit_code"] == 2 and result["status"] == "failed"
    change = result["comparison"]["figures"][0]
    assert change["fields"]["data_bytes"] and change["fields"]["numeric_representation"]
    assert change["fields"]["claims"] and change["fields"]["description"]
    assert change["claims_before"][0]["verdict"] == "holds"
    assert change["claims_after"][0]["verdict"] == "fails"
    assert change["outputs"][0]["pixels_changed"] is True


def test_csv_format_only_change_is_not_labeled_numeric_or_pixel_change(tmp_path):
    manifest, _ = make_paper(tmp_path)
    output = tmp_path / "audit"
    audit(manifest, output=output)
    baseline = tmp_path / "before.json"
    baseline.write_bytes((output / "audit.report.json").read_bytes())
    (tmp_path / "results.csv").write_text(DATA.replace("base", '"base"'))
    result = audit(manifest, output=output, baseline=baseline)
    change = result["comparison"]["figures"][0]
    assert change["fields"]["data_bytes"]
    assert not change["fields"]["numeric_representation"]
    assert change["outputs"][0]["pixels_changed"] is False


def test_failed_and_untested_figures_do_not_stop_the_rest(tmp_path):
    entries = [
        {"id": "pass", "spec": "main.figure.json"},
        {
            "id": "fail",
            "spec": "main.figure.json",
            "claims": [{"kind": "beats_everywhere", "subject": "base", "reference": "ours"}],
        },
        {
            "id": "unknown",
            "spec": "main.figure.json",
            "claims": [{"kind": "beats_everywhere", "subject": "ours", "reference": "missing"}],
        },
        {"id": "missing", "spec": "missing.json"},
    ]
    manifest, _ = make_paper(tmp_path, entries)
    result = audit(manifest, output=tmp_path / "audit")
    assert result["counts"] == {"passed": 1, "failed": 2, "incomplete": 1}
    assert result["exit_code"] == 2
    assert result["figures"][-1]["errors"]


def test_generated_script_executes_original_source_with_separate_outputs(tmp_path):
    manifest, spec = make_paper(tmp_path)
    script = tmp_path / "original.py"
    script.write_text(Figure(spec).translate(api="local")["code"])
    (tmp_path / "figure.png").write_bytes(b"original output must survive")
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "figures": [{"id": "script", "script": "original.py", "data": "results.csv"}],
            }
        )
    )
    result = audit(manifest, output=tmp_path / "audit")
    assert result["status"] == "passed", result
    assert (tmp_path / "figure.png").read_bytes() == b"original output must survive"
    assert (
        result["figures"][0]["report"]["script"]["sha256"] == result["figures"][0]["source_sha256"]
    )


@pytest.mark.parametrize("suffix", ["png", "svg", "pdf", "html"])
def test_published_artifact_is_checked_and_stale_data_rejected(tmp_path, suffix):
    if suffix == "html":
        pytest.importorskip("plotly")
    manifest, spec = make_paper(tmp_path)
    spec["output"]["formats"] = ["png", "svg", "pdf"]
    spec["output"]["interactive"] = suffix == "html"
    (tmp_path / "main.figure.json").write_text(json.dumps(spec))
    first = audit(manifest, output=tmp_path / "audit")
    image = (
        tmp_path
        / "audit"
        / next(item["path"] for item in first["figures"][0]["outputs"] if item["format"] == suffix)
    )
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "figures": [{"id": "main", "spec": "main.figure.json", "artifacts": [str(image)]}],
            }
        )
    )
    assert audit(manifest, output=tmp_path / "audit")["status"] == "passed"
    (tmp_path / "results.csv").write_text(DATA.replace("2,5,ours", "2,6,ours"))
    stale = audit(manifest, output=tmp_path / "audit")
    assert stale["status"] == "failed"
    assert "stale" in stale["figures"][0]["errors"][0]
    assert image.exists()


@pytest.mark.parametrize(
    "figures",
    [
        [{"id": "../escape", "spec": {}}],
        [{"id": "same", "spec": {}}, {"id": "same", "spec": {}}],
        [{"id": "both", "spec": {}, "script": "x.py"}],
    ],
)
def test_invalid_manifest_is_rejected_before_execution(tmp_path, figures):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"schema_version": 1, "figures": figures}))
    with pytest.raises(AuditError):
        load_manifest(path)


def test_script_without_report_and_timeout_are_failures_not_passes(tmp_path):
    manifest, _ = make_paper(tmp_path)
    (tmp_path / "legacy.py").write_text("print('no structured checks')\n")
    manifest.write_text(
        json.dumps({"schema_version": 1, "figures": [{"id": "legacy", "script": "legacy.py"}]})
    )
    result = audit(manifest, output=tmp_path / "audit")
    assert result["exit_code"] == 2
    assert "valid runtime report" in result["figures"][0]["errors"][0]
    (tmp_path / "slow.py").write_text("import time\ntime.sleep(30)\n")
    manifest.write_text(
        json.dumps({"schema_version": 1, "figures": [{"id": "slow", "script": "slow.py"}]})
    )
    result = audit(manifest, output=tmp_path / "audit", timeout=0.1)
    assert "exceeded" in result["figures"][0]["errors"][0]


def test_cli_discovery_and_added_removed_figures(tmp_path):
    manifest, _ = make_paper(tmp_path)
    assert discover(tmp_path)["figures"] == [{"id": "main.figure", "spec": "main.figure.json"}]
    output = tmp_path / "audit"
    audit(manifest, output=output)
    baseline = tmp_path / "before.json"
    baseline.write_bytes((output / "audit.report.json").read_bytes())
    manifest.write_text(
        json.dumps(
            {"schema_version": 1, "figures": [{"id": "replacement", "spec": "main.figure.json"}]}
        )
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "graphunslopify.cli",
            "audit",
            str(manifest),
            "--out-dir",
            str(output),
            "--baseline",
            str(baseline),
            "--fail-on-change",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2, completed.stderr
    report = json.loads(completed.stdout)
    assert report["status"] == "passed"
    assert report["comparison"]["figures"] == [
        {"id": "main", "kind": "removed"},
        {"id": "replacement", "kind": "added"},
    ]
