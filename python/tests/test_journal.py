"""Journal checks use actual files, explicit policy scope and missing-evidence refusals."""

import hashlib
import json
from datetime import date

import pytest
from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import FloatObject, NameObject, NumberObject, RectangleObject

from graphunslopify.cli import main
from graphunslopify.journal import check_journal, journal_profiles

DAY = date(2026, 11, 3)


def tiff(tmp_path, *, size=(1000, 600), dpi=(300, 300), name="Fig1.tif"):
    path = tmp_path / name
    image = Image.new("RGB", size, "white")
    image.save(path, **({"dpi": dpi} if dpi is not None else {}))
    return path


def pdf(tmp_path, *, width=252, height=144, unit=1, rotation=0, pages=1):
    path = tmp_path / "figure.pdf"
    writer = PdfWriter()
    for _ in range(pages):
        page = writer.add_blank_page(width=width, height=height)
        page[NameObject("/UserUnit")] = FloatObject(unit)
        page[NameObject("/Rotate")] = NumberObject(rotation)
    writer.write(path)
    return path


def checks(report):
    return {item["code"]: item for item in report["checks"]}


def test_actual_tiff_passes_technical_subset_without_certifying_text_or_science(tmp_path):
    path = tiff(tmp_path)
    raw = path.read_bytes()
    report = check_journal(path, profile="plos-one-main", as_of=DAY)
    assert report["status"] == "passed" and report["exit_code"] == 0
    assert report["submission_ready"] is None
    assert report["scientific_verification"] == "not_performed"
    assert any("8-12" in item for item in report["manual_review"])
    assert report["source"]["sha256"] == hashlib.sha256(raw).hexdigest()
    measure = checks(report)["physical_measurement"]["actual"]
    assert measure["width_in"] == pytest.approx(1000 / 300)
    assert measure["height_in"] == 2
    assert path.read_bytes() == raw


@pytest.mark.parametrize("dpi", [(150, 300), (300, 150), (601, 300)])
def test_both_resolution_axes_must_meet_requirements(tmp_path, dpi):
    report = check_journal(tiff(tmp_path, dpi=dpi), profile="plos-one-main", as_of=DAY)
    assert report["status"] == "failed"
    assert checks(report)["raster_resolution"]["status"] == "failed"


def test_missing_tiff_physical_units_do_not_become_default_dpi(tmp_path):
    report = check_journal(tiff(tmp_path, dpi=None), profile="plos-one-main", as_of=DAY)
    assert report["status"] == "incomplete"
    for code in ["physical_measurement", "physical_width", "physical_height", "raster_resolution"]:
        assert checks(report)[code]["status"] == "unavailable"


@pytest.mark.parametrize(
    "size,code",
    [
        ((700, 600), "physical_width"),
        ((2400, 600), "physical_width"),
        ((1000, 2700), "physical_height"),
    ],
)
def test_actual_dimensions_reject_real_small_wide_or_tall_tiffs(tmp_path, size, code):
    report = check_journal(tiff(tmp_path, size=size), profile="plos-one-main", as_of=DAY)
    assert report["status"] == "failed" and checks(report)[code]["status"] == "failed"


def test_png_is_not_silently_accepted_as_a_plos_submission(tmp_path):
    path = tmp_path / "Fig1.png"
    Image.new("RGB", (1000, 600)).save(path, dpi=(300, 300))
    report = check_journal(path, profile="plos-one-main", as_of=DAY)
    assert checks(report)["file_format"]["status"] == "failed"


def test_extension_spoofing_is_unavailable_not_accepted(tmp_path):
    path = tmp_path / "Fig1.tif"
    Image.new("RGB", (1000, 600)).save(path, format="PNG", dpi=(300, 300))
    report = check_journal(path, profile="plos-one-main", as_of=DAY)
    assert report["status"] == "incomplete"
    assert "disagree" in checks(report)["physical_measurement"]["message"]


def test_requested_width_uses_pdf_crop_units_and_rotation(tmp_path):
    path = pdf(tmp_path, width=252, height=144, unit=2, rotation=90)
    report = check_journal(path, profile="nature-final-graphs", target_width_mm=101.6, as_of=DAY)
    assert report["status"] == "incomplete"  # The blank PDF has no measurable glyphs.
    assert checks(report)["requested_width"]["status"] == "passed"
    assert checks(report)["requested_width"]["actual"] == pytest.approx(101.6)
    writer = PdfWriter(clone_from=path)
    writer.pages[0].cropbox = RectangleObject([0, 0, 252, 72])
    writer.write(path)
    second = check_journal(path, profile="nature-final-graphs", target_width_mm=101.6, as_of=DAY)
    assert checks(second)["requested_width"]["status"] == "failed"
    assert checks(second)["requested_width"]["actual"] == pytest.approx(50.8)


def test_tight_native_export_cannot_pass_nominal_target(tmp_path):
    import matplotlib.pyplot as plt

    path = tmp_path / "figure.pdf"
    fig, ax = plt.subplots(figsize=(7, 3))
    ax.plot([0, 1], [0, 1])
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    report = check_journal(path, profile="nature-final-graphs", target_width_mm=177.8, as_of=DAY)
    assert checks(report)["requested_width"]["status"] == "failed"
    assert report["status"] == "failed"


def test_nature_guidance_is_not_an_unstated_exact_width_rule(tmp_path):
    report = check_journal(pdf(tmp_path, width=288), profile="nature-final-graphs", as_of=DAY)
    assert report["status"] == "incomplete"
    assert checks(report)["physical_measurement"]["status"] == "passed"
    assert checks(report)["pdf_text_minimum"]["status"] == "unavailable"
    assert "requested_width" not in checks(report)
    assert any("guidance" in item for item in report["manual_review"])


@pytest.mark.parametrize("days", [date(2027, 5, 3), date(2026, 11, 2)])
def test_stale_or_future_snapshot_requires_recheck(tmp_path, days):
    report = check_journal(tiff(tmp_path), profile="plos-one-main", as_of=days)
    assert report["status"] == "incomplete"
    assert checks(report)["profile_freshness"]["status"] == "unavailable"


def test_multiframe_and_multipage_are_not_silently_reduced_to_first(tmp_path):
    path = tmp_path / "Fig1.tif"
    first = Image.new("RGB", (1000, 600))
    first.save(path, save_all=True, append_images=[first], dpi=(300, 300))
    assert check_journal(path, profile="plos-one-main", as_of=DAY)["status"] == "incomplete"
    report = check_journal(pdf(tmp_path, pages=2), profile="nature-final-graphs", as_of=DAY)
    assert report["status"] == "incomplete"


def test_eps_header_is_measured_without_executing_postscript(tmp_path):
    path = tmp_path / "Fig1.eps"
    marker = tmp_path / "must-not-exist"
    path.write_text(
        f"%!PS-Adobe-3.0 EPSF-3.0\n%%HiResBoundingBox: 0 0 240.12 144\n%%BoundingBox: 0 0 241 144\n%%EndComments\n({marker}) (w) file closefile\n"
    )
    report = check_journal(path, profile="plos-one-main", as_of=DAY)
    assert not marker.exists()
    assert checks(report)["physical_width"]["actual"] == pytest.approx(240.12 / 72)
    assert checks(report)["raster_resolution"]["status"] == "unavailable"
    assert report["status"] == "incomplete"


def test_eps_executable_body_cannot_supply_a_missing_header_box(tmp_path):
    path = tmp_path / "figure.eps"
    path.write_text("%!PS-Adobe-3.0 EPSF-3.0\n0 0 moveto\n%%BoundingBox: 0 0 252 144\n")
    report = check_journal(path, profile="nature-final-graphs", as_of=DAY)
    assert report["status"] == "incomplete"


def test_exact_ten_megabyte_file_obeys_published_strict_summary_bound(tmp_path):
    path = tiff(tmp_path)
    with path.open("ab") as f:
        f.truncate(10_000_000)
    report = check_journal(path, profile="plos-one-main", as_of=DAY)
    assert checks(report)["physical_measurement"]["status"] == "passed"
    assert checks(report)["file_size"]["status"] == "failed"


def test_changed_source_during_inspection_cannot_borrow_snapshot_acceptance(tmp_path, monkeypatch):
    from graphunslopify import journal

    path = tiff(tmp_path)
    original = journal._measure

    def change(raw, format_):
        result = original(raw, format_)
        path.write_bytes(b"changed after snapshot")
        return result

    monkeypatch.setattr(journal, "_measure", change)
    report = check_journal(path, profile="plos-one-main", as_of=DAY)
    assert report["status"] == "failed"
    assert checks(report)["source_current"]["status"] == "failed"


def test_catalog_detaches_and_cli_does_not_overwrite_source(tmp_path, capsys):
    items = journal_profiles()
    items[0]["formats"].append("png")
    assert "png" not in journal_profiles()[0]["formats"]
    path = tiff(tmp_path)
    raw = path.read_bytes()
    assert (
        main(
            [
                "journal-check",
                str(path),
                "--profile",
                "plos-one-main",
                "--output",
                str(path),
                "--json",
            ]
        )
        == 2
    )
    assert "overwrite" in json.loads(capsys.readouterr().out)["error"]
    assert path.read_bytes() == raw
    assert main(["journal-profiles"]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 2


def test_cli_json_and_saved_report_match_actual_artifact(tmp_path, capsys):
    path = tiff(tmp_path)
    output = tmp_path / "report.json"
    assert (
        main(
            [
                "journal-check",
                str(path),
                "--profile",
                "plos-one-main",
                "--output",
                str(output),
                "--json",
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report == json.loads(output.read_text())
    assert report["source"]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("value", [True, 0, -1, float("nan"), float("inf")])
def test_invalid_author_target_is_refused(tmp_path, value):
    with pytest.raises((ValueError, TypeError)):
        check_journal(tiff(tmp_path), profile="plos-one-main", target_width_mm=value, as_of=DAY)


@pytest.mark.parametrize(
    ("points", "unit", "rotation", "expected"),
    [(4, 1, 0, "failed"), (6, 1, 0, "passed"), (4, 2, 0, "passed"), (6, 1, 90, "passed")],
)
def test_actual_pdf_glyph_minimum_uses_transformed_physical_size(
    tmp_path, points, unit, rotation, expected
):
    import matplotlib.pyplot as plt

    source = tmp_path / "text.pdf"
    with plt.rc_context({"pdf.fonttype": 42}):
        fig = plt.figure(figsize=(3, 2))
        fig.text(0.1, 0.5, "Measured label", fontsize=points)
        fig.savefig(source)
        plt.close(fig)
    if unit != 1 or rotation:
        writer = PdfWriter(clone_from=source)
        writer.pages[0][NameObject("/UserUnit")] = FloatObject(unit)
        if rotation:
            writer.pages[0].rotate(rotation)
        writer.write(source)
    report = check_journal(source, profile="nature-final-graphs", as_of=DAY)
    metric = checks(report)["pdf_text_minimum"]
    assert metric["status"] == expected
    assert metric["actual"]["minimum_pt"] == pytest.approx(points * unit)
    assert metric["actual"]["characters_measured"] == len("Measuredlabel")
    assert metric["actual"]["limits"]
    assert report["submission_ready"] is None
    assert report["scientific_verification"] == "not_performed"


def test_raster_only_pdf_does_not_claim_extractable_text_or_legibility(tmp_path):
    import matplotlib.pyplot as plt

    source = tmp_path / "raster.pdf"
    fig = plt.figure(figsize=(3, 2))
    ax = fig.add_axes((0, 0, 1, 1))
    ax.imshow([[0, 1], [1, 0]])
    ax.set_axis_off()
    fig.savefig(source)
    plt.close(fig)
    report = check_journal(source, profile="nature-final-graphs", as_of=DAY)
    assert report["status"] == "incomplete"
    assert checks(report)["pdf_text_minimum"]["status"] == "unavailable"
    assert checks(report)["pdf_text_minimum"]["actual"]["characters_measured"] == 0


def test_missing_optional_pdfium_retains_unavailable_text_evidence(tmp_path, monkeypatch):
    import builtins

    original = builtins.__import__

    def without_pdfium(name, *args, **kwargs):
        if name == "pypdfium2":
            raise ImportError("Optional PDFium unavailable")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_pdfium)
    report = check_journal(pdf(tmp_path), profile="nature-final-graphs", as_of=DAY)
    assert checks(report)["pdf_text_minimum"]["status"] == "unavailable"
    assert "[pdf]" in checks(report)["pdf_text_minimum"]["message"]
    assert report["status"] == "incomplete"


def test_conditional_nature_jpeg_is_manual_instead_of_universally_prohibited(tmp_path):
    source = tmp_path / "fallback.jpg"
    Image.new("RGB", (1000, 600), "white").save(source, dpi=(300, 300))
    report = check_journal(source, profile="nature-final-graphs", as_of=DAY)
    assert checks(report)["file_format"]["status"] == "unavailable"
    assert "Fallbacks" in checks(report)["file_format"]["message"]
    assert report["status"] == "incomplete"
    assert "jpeg" in report["profile"]["conditional_formats"]
    assert "version 8" in report["profile"]["conditional_format_review"]


def test_partial_pdf_glyph_scan_cannot_pass_missing_coverage(tmp_path, monkeypatch):
    from graphunslopify import pdf_visual

    original = pdf_visual.scan_page

    def partial(*args, **kwargs):
        model = original(*args, **kwargs)
        model["text_reasons"].append("Bounded extraction coverage is partial")
        return model

    monkeypatch.setattr(pdf_visual, "scan_page", partial)
    report = check_journal(pdf(tmp_path), profile="nature-final-graphs", as_of=DAY)
    check = checks(report)["pdf_text_minimum"]
    assert check["status"] == "unavailable"
    assert check["actual"]["status"] == "partial"
    assert report["status"] == "incomplete"


def test_source_change_after_actual_text_scan_is_rejected(tmp_path, monkeypatch):
    import matplotlib.pyplot as plt

    from graphunslopify import journal

    path = tmp_path / "text.pdf"
    fig = plt.figure(figsize=(3, 2))
    fig.text(0.1, 0.5, "Real text", fontsize=6)
    fig.savefig(path)
    plt.close(fig)
    original = journal._pdf_text

    def inspect_then_change(*args, **kwargs):
        result = original(*args, **kwargs)
        path.write_bytes(b"changed after actual glyph inspection")
        return result

    monkeypatch.setattr(journal, "_pdf_text", inspect_then_change)
    report = check_journal(path, profile="nature-final-graphs", as_of=DAY)
    assert checks(report)["source_current"]["status"] == "failed"
    assert report["status"] == "failed"


def test_enormous_pdf_text_viewport_stays_unavailable_without_allocation(tmp_path):
    report = check_journal(
        pdf(tmp_path, width=20000, height=20000), profile="nature-final-graphs", as_of=DAY
    )
    metric = checks(report)["pdf_text_minimum"]
    assert metric["status"] == "unavailable"
    assert "bounded" in metric["message"]
    assert report["status"] == "incomplete"


def test_conditional_jpeg_still_checks_actual_resolution(tmp_path):
    source = tmp_path / "low-fallback.jpg"
    Image.new("RGB", (1000, 600), "white").save(source, dpi=(150, 150))
    report = check_journal(source, profile="nature-final-graphs", as_of=DAY)
    assert checks(report)["file_format"]["status"] == "unavailable"
    assert checks(report)["raster_resolution"]["status"] == "failed"
    assert report["status"] == "failed"
