"""Known pixel answers, preserved audit policies, real exports and portable archives."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image, PngImagePlugin

from graphunslopify.audit import AuditError, _pixel_hash, audit
from graphunslopify.comparison import compare_reports, write_comparison


def saved(root, *, color="white", size=(2, 2), metadata=None, name="figure.png"):
    root.mkdir(parents=True, exist_ok=True)
    path = root / name
    image = Image.new("RGBA", size, color)
    info = PngImagePlugin.PngInfo()
    if metadata:
        info.add_text("note", metadata)
    image.save(path, pnginfo=info)
    return output(path, root, "png", pixels=_pixel_hash(path))


def output(path, root, format, pixels=None):
    return {
        "path": path.relative_to(root).as_posix(),
        "format": format,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
        "pixels_sha256": pixels,
    }


def report(item=None, *, name="main", status="passed"):
    return {
        "schema_version": 1,
        "manifest": "graphunslopify.json",
        "status": status,
        "figures": [
            {
                "id": name,
                "status": status,
                "errors": [],
                "warnings": [],
                "report": {"claims": [], "environment": None},
                "outputs": [] if item is None else [item],
                "artifacts": [],
            }
        ],
        "counts": {x: int(x == status) for x in ("passed", "failed", "incomplete")},
        "comparison": None,
        "policy": {"strict": True, "fail_on_warning": False, "fail_on_change": False},
        "exit_code": 0 if status == "passed" else 2,
    }


def compare(tmp_path, a, b):
    return write_comparison(
        a,
        b,
        output=tmp_path / "comparison",
        before_roots=[tmp_path / "before"],
        after_roots=[tmp_path / "after"],
    )


def test_one_changed_pixel_has_exact_channel_counts_and_difference_location(tmp_path):
    a = saved(tmp_path / "before")
    path = tmp_path / "after" / "figure.png"
    saved(path.parent)
    with Image.open(path) as opened:
        image = opened.convert("RGBA")
    image.putpixel((1, 0), (255, 0, 0, 255))
    image.save(path)
    b = output(path, path.parent, "png", pixels=_pixel_hash(path))
    result = compare(tmp_path, report(a), report(b))
    f = result["figures"][0]
    assert result["changed"] and result["exit_code"] == 0
    assert f["visual_status"] == "pixels_changed"
    assert f["metrics"] == {
        "total_pixels": 4,
        "rgba_pixels_changed": 1,
        "visible_pixels_changed": 1,
        "visible_changed_fraction": 0.25,
        "max_rgb_channel_difference": 255,
        "mean_absolute_rgb_channel_difference": 42.5,
        "background": "white",
        "channel_range": [0, 255],
        "resampled": False,
    }
    with Image.open(tmp_path / "comparison" / f["difference"]["path"]) as heat:
        assert heat.getpixel((1, 0)) == (196, 0, 122)
        assert heat.getpixel((0, 0)) == (245, 245, 245)


@pytest.mark.parametrize(
    "before,after,visible,mean",
    [
        ((0, 0, 0, 0), (255, 0, 0, 0), 0, 0),
        ((255, 0, 0, 0), (255, 0, 0, 255), 1, 170),
    ],
)
def test_transparency_is_counted_separately_from_white_visible_pixels(
    tmp_path, before, after, visible, mean
):
    a = saved(tmp_path / "before", color=before, size=(1, 1))
    b = saved(tmp_path / "after", color=after, size=(1, 1))
    f = compare(tmp_path, report(a), report(b))["figures"][0]
    assert f["metrics"]["rgba_pixels_changed"] == 1
    assert f["metrics"]["visible_pixels_changed"] == visible
    assert f["metrics"]["mean_absolute_rgb_channel_difference"] == mean


def test_metadata_only_change_has_zero_pixel_metrics(tmp_path):
    a = saved(tmp_path / "before", metadata="before")
    b = saved(tmp_path / "after", metadata="after")
    result = compare(tmp_path, report(a), report(b))
    assert result["changed"]
    f = result["figures"][0]
    assert f["visual_status"] == "pixels_unchanged"
    assert f["output_changes"] == [
        {"file": "figure.png", "bytes_changed": True, "pixels_changed": False}
    ]
    assert f["metrics"]["visible_pixels_changed"] == 0
    with Image.open(tmp_path / "comparison" / f["before"]["preview"]["path"]) as image:
        assert "note" not in image.info


def test_different_dimensions_are_not_resampled_or_given_a_score(tmp_path):
    a = saved(tmp_path / "before", size=(2, 2))
    b = saved(tmp_path / "after", size=(3, 2))
    f = compare(tmp_path, report(a), report(b))["figures"][0]
    assert f["visual_status"] == "dimensions_changed"
    assert f["metrics"] is None and f["difference"] is None
    assert f["before"]["dimensions"] == [2, 2] and f["after"]["dimensions"] == [3, 2]


@pytest.mark.parametrize(
    "failure", ["missing", "tampered", "wrong_pixels", "corrupt", "escaped", "windows", "symlink"]
)
def test_invalid_saved_evidence_is_unavailable_never_unchanged(tmp_path, failure):
    a = saved(tmp_path / "before")
    b = saved(tmp_path / "after")
    path = tmp_path / "before" / a["path"]
    if failure == "missing":
        path.unlink()
    elif failure == "tampered":
        path.write_bytes(b"changed")
    elif failure == "wrong_pixels":
        a["pixels_sha256"] = "0" * 64
    elif failure == "corrupt":
        path.write_bytes(b"not a PNG")
        a = output(path, path.parent, "png")
    elif failure == "escaped":
        a["path"] = "../after/figure.png"
    elif failure == "windows":
        a["path"] = "C:\\outside\\image.png"
    else:
        outside = tmp_path / "outside.png"
        shutil.move(path, outside)
        try:
            path.symlink_to(outside)
        except OSError:
            pytest.skip("symlink creation unavailable on this host")
    result = compare(tmp_path, report(a), report(b))
    assert result["preview_status"] == "partial" and result["exit_code"] == 2
    f = result["figures"][0]
    assert f["before"]["status"] == "unavailable"
    assert f["visual_status"] == "unavailable" and f["metrics"] is None


def test_added_removed_and_unchanged_figures_keep_their_own_context(tmp_path):
    a = saved(tmp_path / "before")
    b = saved(tmp_path / "after")
    before = report(a, name="removed")
    before["figures"] += report(a, name="same")["figures"]
    after = report(b, name="added")
    after["figures"] += report(b, name="same")["figures"]
    result = compare(tmp_path, before, after)
    assert result["preview_status"] == "complete"
    assert [(f["id"], f["kind"], f["visual_status"]) for f in result["figures"]] == [
        ("added", "added", "added"),
        ("removed", "removed", "removed"),
        ("same", "unchanged", "pixels_unchanged"),
    ]


def test_unsupported_only_exports_are_explicitly_unavailable(tmp_path):
    a = report()
    b = report()
    result = compare(tmp_path, a, b)
    assert result["preview_status"] == "partial" and result["exit_code"] == 2
    assert "export PNG" in result["figures"][0]["before"]["reason"]


def test_source_settings_claims_environment_and_failed_status_are_explained(tmp_path):
    a = report(saved(tmp_path / "before"))
    b = report(saved(tmp_path / "after"), status="failed")
    a["figures"][0]["semantic_spec"] = {"y": {"limits": [0, 10]}}
    b["figures"][0]["semantic_spec"] = {"y": {"limits": [5, 10]}}
    a["figures"][0]["report"]["claims"] = [{"verdict": "holds"}]
    b["figures"][0]["report"]["claims"] = [{"verdict": "fails"}]
    a["figures"][0]["report"]["environment"] = {"backend": "old"}
    b["figures"][0]["report"]["environment"] = {"backend": "new"}
    result = compare(tmp_path, a, b)
    assert (
        result["after_status"] == "failed"
        and result["after_exit_code"] == 2
        and result["exit_code"] == 2
    )
    f = result["figures"][0]
    assert (
        f["visual_status"] == "pixels_unchanged"
    )  # No false scientific pass from identical images.
    explanations = {x["field"]: x for x in f["explanations"]}
    assert explanations["spec"]["details"] == [
        {"path": "y.limits", "before": [0, 10], "after": [5, 10]}
    ]
    assert explanations["claims"]["before"] == [{"verdict": "holds"}]
    assert explanations["claims"]["after"] == [{"verdict": "fails"}]
    assert "not proof" in explanations["environment"]["message"]


def test_renamed_stems_compare_same_figure_by_format(tmp_path):
    a = saved(tmp_path / "before", name="old.png")
    b = saved(tmp_path / "after", name="new.png")
    result = compare(tmp_path, report(a), report(b))
    assert result["figures"][0]["visual_status"] == "pixels_unchanged"


def test_portable_archives_explicit_roots_and_source_files_are_not_executed(tmp_path):
    a = saved(tmp_path / "before")
    b = saved(tmp_path / "after")
    left, right = report(a), report(b)
    left["artifact_root"] = str(tmp_path / "nonexistent-original-location")
    right["artifact_root"] = str(tmp_path / "after")
    left["figures"][0]["source"] = 'raise RuntimeError("must not execute")'
    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    before, after = snapshots / "before.json", snapshots / "after.json"
    before.write_text(json.dumps(left))
    after.write_text(json.dumps(right))
    result = compare_reports(
        before, after, output=tmp_path / "packet", before_root=tmp_path / "before"
    )
    assert result["preview_status"] == "complete" and result["exit_code"] == 0
    # Explicit roots are exclusive, never quietly bypassed by a stored locator.
    wrong = compare_reports(
        before, after, output=tmp_path / "wrong-root", before_root=tmp_path / "missing"
    )
    assert wrong["preview_status"] == "partial"
    with pytest.raises(AuditError, match="empty"):
        compare_reports(before, after, output=tmp_path / "packet", before_root=tmp_path / "before")


@pytest.mark.parametrize("kind", ["duplicate", "missing_field", "nan"])
def test_both_saved_reports_are_validated_before_writing_outputs(tmp_path, kind):
    before, after = report(), report()
    if kind == "duplicate":
        after["figures"] *= 2
    elif kind == "missing_field":
        after.pop("figures")
    else:
        after["extra"] = float("nan")
    with pytest.raises(AuditError):
        compare(tmp_path, before, after)
    assert not (tmp_path / "comparison").exists()


def svg(root, text='<path d="M0 0h10v10z" fill="red"/>'):
    root.mkdir(exist_ok=True)
    path = root / "figure.svg"
    path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">{text}</svg>')
    return output(path, root, "svg")


def test_svg_preview_remains_passive_and_has_unknown_pixel_metrics(tmp_path):
    a = svg(tmp_path / "before")
    b = svg(tmp_path / "after", "<text>After</text>")
    left, right = report(a), report(b)
    left["figures"][0]["report"]["alt_text"] = "<img onerror=alert(1)>"
    right["figures"][0]["report"]["alt_text"] = "updated description"
    result = compare(tmp_path, left, right)
    f = result["figures"][0]
    assert f["visual_status"] == "preview_only" and f["metrics"] is None
    assert f["before"]["renderer"] == "browser_svg_image"
    html = (tmp_path / "comparison/index.html").read_text()
    assert "&lt;img onerror=alert(1)&gt;" in html and "<img onerror=" not in html
    assert "data:image/svg+xml;base64," in html and "<svg " not in html
    assert "default-src &#x27;none&#x27;" in html


def test_saved_pdf_previews_have_actual_raster_metrics(tmp_path):
    pytest.importorskip("pypdfium2")
    records = []
    for name, color in [("before", "white"), ("after", "red")]:
        root = tmp_path / name
        root.mkdir()
        path = root / "figure.pdf"
        Image.new("RGB", (10, 10), color).save(path, "PDF", resolution=72)
        records.append(report(output(path, root, "pdf")))
    result = compare(tmp_path, *records)
    f = result["figures"][0]
    assert f["before"]["dimensions"] == [20, 20]
    assert f["before"]["raster_dpi"] == 144
    assert f["metrics"]["visible_pixels_changed"] == 400
    assert f["visual_status"] == "pixels_changed"


def test_missing_optional_pdf_renderer_has_actionable_fallback(tmp_path, monkeypatch):
    a = saved(tmp_path / "before")
    b = saved(tmp_path / "after")
    a["format"] = b["format"] = "pdf"  # Import fails before any bytes are decoded as PDF.
    monkeypatch.setitem(sys.modules, "pypdfium2", None)
    result = compare(tmp_path, report(a), report(b))
    assert "graphunslopify[pdf]" in result["figures"][0]["before"]["reason"]
    assert result["preview_status"] == "partial"


@pytest.fixture(scope="module")
def real_audits(tmp_path_factory):
    root = tmp_path_factory.mktemp("visual audit with spaces")
    (root / "results.csv").write_text("x,y,model\n1,1,base\n2,2,base\n1,4,ours\n2,5,ours\n")
    spec = {
        "kind": "line",
        "data": {"path": "results.csv"},
        "x": {"field": "x", "label": "X"},
        "y": {"field": "y", "label": "Y"},
        "group": "model",
        "legend": {"show": False},
        "claims": [{"kind": "beats_everywhere", "subject": "ours", "reference": "base"}],
        "output": {"stem": "figure", "formats": ["png", "svg", "pdf"], "dpi": 100},
    }
    manifest = root / "graphunslopify.json"
    manifest.write_text(
        json.dumps({"schema_version": 1, "figures": [{"id": "main", "spec": spec}]})
    )
    folder = root / "audit"
    first = audit(manifest, output=folder)
    snapshot = root / "before.json"
    snapshot.write_bytes((folder / "audit.report.json").read_bytes())
    (root / "results.csv").write_text("x,y,model\n1,1,base\n2,2,base\n1,4,ours\n2,0,ours\n")
    second = audit(manifest, output=folder, baseline=snapshot, fail_on_change=True)
    return root, folder, snapshot, first, second


def test_real_audit_automatically_saves_changed_failed_claim_preview_and_policy(real_audits):
    _root, folder, snapshot, first, second = real_audits
    packet = json.loads((folder / second["visual_comparison"]["report"]).read_text())
    assert first["status"] == "passed" and second["status"] == "failed"
    assert packet["after_exit_code"] == 2 and packet["after_status"] == "failed"
    assert packet["preview_status"] == "complete"
    f = packet["figures"][0]
    assert f["metrics"]["visible_pixels_changed"] > 0
    explanation = {x["field"]: x for x in f["explanations"]}
    assert {x["format"] for x in f["outputs_before"]} == {"png", "svg", "pdf"}
    assert explanation["claims"]["before"][0]["verdict"] == "holds"
    assert explanation["claims"]["after"][0]["verdict"] == "fails"
    assert (
        explanation["numeric_representation"]["before"]
        != explanation["numeric_representation"]["after"]
    )
    assert (folder / second["visual_comparison"]["html"]).is_file()
    assert second["visual_comparison"]["html"] in (folder / "audit.summary.md").read_text()
    assert snapshot.is_file()  # Copied JSON resolves its original saved artifacts.


def test_installed_style_cli_compare_preserves_failed_source_status(real_audits, tmp_path):
    _, folder, snapshot, _, _ = real_audits
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "graphunslopify.cli",
            "compare",
            str(snapshot),
            str(folder / "audit.report.json"),
            "--out-dir",
            str(tmp_path / "packet"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 2, run.stderr
    result = json.loads(run.stdout)
    assert result["preview_status"] == "complete" and result["after_status"] == "failed"


def test_packaged_comparison_schema_matches_canonical_source():
    root = Path(__file__).resolve().parents[2]
    assert json.loads((root / "docs/comparison.schema.json").read_text()) == json.loads(
        (root / "python/graphunslopify/schemas/comparison.schema.json").read_text()
    )


def test_artifact_byte_and_decoded_size_limits_are_enforced(tmp_path, monkeypatch):
    import graphunslopify.comparison as module

    a = saved(tmp_path / "before")
    b = saved(tmp_path / "after")
    monkeypatch.setattr(module, "MAX_PIXELS", 3)
    result = compare(tmp_path, report(a), report(b))
    assert result["preview_status"] == "partial"
    assert "pixel limit" in result["figures"][0]["before"]["reason"]
    monkeypatch.setattr(module, "MAX_PIXELS", 30_000_000)
    monkeypatch.setattr(module, "MAX_BYTES", 1)
    result = module.write_comparison(
        report(a),
        report(b),
        output=tmp_path / "small-limit",
        before_roots=[tmp_path / "before"],
        after_roots=[tmp_path / "after"],
    )
    assert "MiB" in result["figures"][0]["before"]["reason"]


@pytest.mark.parametrize(
    "content",
    [
        '<!DOCTYPE svg [<!ENTITY a "unsafe">]><svg xmlns="http://www.w3.org/2000/svg">&a;</svg>',
        "<not-svg/>",
    ],
)
def test_malformed_or_entity_declaring_svg_is_not_embedded(tmp_path, content):
    a = svg(tmp_path / "before")
    path = tmp_path / "before/figure.svg"
    path.write_text(content)
    a = output(path, path.parent, "svg")
    b = svg(tmp_path / "after")
    result = compare(tmp_path, report(a), report(b))
    assert result["preview_status"] == "partial"
    assert result["figures"][0]["before"]["status"] == "unavailable"


def test_multipage_pdf_does_not_silently_compare_only_the_first_page(tmp_path):
    pytest.importorskip("pypdfium2")
    records = []
    for name in ["before", "after"]:
        root = tmp_path / name
        root.mkdir()
        path = root / "figure.pdf"
        image = Image.new("RGB", (5, 5), "white")
        image.save(path, "PDF", save_all=True, append_images=[image])
        records.append(report(output(path, root, "pdf")))
    result = compare(tmp_path, *records)
    assert result["preview_status"] == "partial"
    assert "one page" in result["figures"][0]["before"]["reason"]


def test_saved_report_comparison_survives_moved_archive_and_missing_original_data(
    real_audits, tmp_path
):
    root, folder, snapshot, _, _ = real_audits
    archive = tmp_path / "moved archive"
    shutil.copytree(folder, archive)
    before = tmp_path / "before.json"
    before.write_bytes(snapshot.read_bytes())
    for script in archive.rglob("*.py"):
        script.write_text('raise RuntimeError("saved comparison must not execute source")')
    data = root / "results.csv"
    parked = root / "results.saved"
    data.rename(parked)
    try:
        result = compare_reports(
            before,
            archive / "audit.report.json",
            output=tmp_path / "packet",
            before_root=archive,
            after_root=archive,
        )
    finally:
        parked.rename(data)
    assert result["preview_status"] == "complete"
    assert result["figures"][0]["metrics"]["visible_pixels_changed"] > 0


@pytest.mark.parametrize("encoding", ["utf-16", "utf-16-le", "utf-32-le"])
def test_utf16_entity_declaration_cannot_bypass_svg_preview_refusal(tmp_path, encoding):
    a = svg(tmp_path / "before")
    path = tmp_path / "before/figure.svg"
    path.write_bytes(
        '<!DOCTYPE svg [<!ENTITY a "expanded">]><svg xmlns="http://www.w3.org/2000/svg">&a;</svg>'.encode(
            "utf-16"
        )
    )
    a = output(path, path.parent, "svg")
    b = svg(tmp_path / "after")
    result = compare(tmp_path, report(a), report(b))
    assert result["preview_status"] == "partial"
    assert result["figures"][0]["before"]["status"] == "unavailable"


def test_actual_matplotlib_svg_with_external_doctype_is_a_passive_preview(real_audits, tmp_path):
    _, folder, _, first, second = real_audits
    a, b = copy.deepcopy(first), copy.deepcopy(second)
    for record in [a, b]:
        record["figures"][0]["outputs"] = [
            x for x in record["figures"][0]["outputs"] if x["format"] == "svg"
        ]
    result = write_comparison(
        a, b, output=tmp_path / "svg-packet", before_roots=[folder], after_roots=[folder]
    )
    assert result["preview_status"] == "complete"
    assert result["figures"][0]["visual_status"] == "preview_only"
    assert result["figures"][0]["metrics"] is None


def test_automatic_audit_rejects_unavailable_baseline_without_relabeling_source_checks(
    real_audits, tmp_path
):
    root, _folder, snapshot, _first, _second = real_audits
    manifest = json.loads((root / "graphunslopify.json").read_text())
    manifest["figures"][0]["spec"].pop("claims")
    manifest["figures"][0]["spec"]["data"]["path"] = str(root / "results.csv")
    source = tmp_path / "manifest.json"
    source.write_text(json.dumps(manifest))
    result = audit(
        source,
        output=tmp_path / "audit",
        baseline=snapshot,
        baseline_root=tmp_path / "missing-root",
    )
    assert result["status"] == "passed"  # Current figure's numerical checks really passed.
    assert result["exit_code"] == 2 and result["policy"]["require_visual_comparison"]
    assert result["visual_comparison"]["preview_status"] == "partial"
    assert result["visual_comparison"]["exit_code"] == 2
    packet = json.loads((tmp_path / "audit" / result["visual_comparison"]["report"]).read_text())
    assert packet["after_exit_code"] == result["exit_code"] == 2
    assert packet["after_policy"] == result["policy"]
    assert "unavailable evidence rejects" in (tmp_path / "audit/audit.summary.md").read_text()


def test_png_previews_do_not_inherit_original_color_profile_metadata(tmp_path):
    a = saved(tmp_path / "before")
    path = tmp_path / "before/figure.png"
    Image.new("RGBA", (2, 2), "white").save(path, icc_profile=b"synthetic-original-profile")
    a = output(path, path.parent, "png", pixels=_pixel_hash(path))
    b = saved(tmp_path / "after")
    with Image.open(path) as original:
        assert "icc_profile" in original.info
    result = compare(tmp_path, report(a), report(b))
    f = result["figures"][0]
    assert f["metrics"]["visible_pixels_changed"] == 0
    for side in ["before", "after"]:
        with Image.open(tmp_path / "comparison" / f[side]["preview"]["path"]) as preview:
            assert not preview.info
    # Original evidence is still byte-identical and retains its original metadata.
    assert hashlib.sha256(path.read_bytes()).hexdigest() == a["sha256"]
