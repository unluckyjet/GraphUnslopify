"""Independent primitive PDFs establish actual point sizes, placements and policy."""

from __future__ import annotations

import hashlib
import json
import math

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
)

from graphunslopify import pdf_visual
from graphunslopify.pdf_review import review_pdf

pytest.importorskip("pypdfium2")


def primitive(
    path,
    *,
    scale=1,
    unit=1,
    rotation=0,
    image=False,
    nested=0,
    invisible=False,
    crop=False,
    image_angle=0,
):
    """A 300x240-unit page, 8pt Helvetica and optional 16px image in a 72-unit square."""
    writer = PdfWriter()
    writer.pdf_header = "%PDF-1.7"
    page = writer.add_blank_page(width=300, height=240)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    resources = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    content = f"q {scale} 0 0 {scale} 0 0 cm BT /F1 8 Tf {3 if invisible else 0} Tr 40 180 Td (Measured <script>value</script>) Tj ET "
    if image:
        stream = DecodedStreamObject()
        stream.set_data(bytes([255, 0, 0, 0, 0, 255]) * 128)
        stream.update(
            {
                NameObject("/Type"): NameObject("/XObject"),
                NameObject("/Subtype"): NameObject("/Image"),
                NameObject("/Width"): NumberObject(16),
                NameObject("/Height"): NumberObject(16),
                NameObject("/ColorSpace"): NameObject("/DeviceRGB"),
                NameObject("/BitsPerComponent"): NumberObject(8),
            }
        )
        resources[NameObject("/XObject")] = DictionaryObject(
            {NameObject("/I"): writer._add_object(stream)}
        )
        angle = math.radians(image_angle)
        a, b = 72 * math.cos(angle), 72 * math.sin(angle)
        content += (
            f"q {a} {b} {-b} {a} 100 60 cm /I Do Q "
            if image_angle
            else "q 72 0 0 72 40 40 cm /I Do Q "
        )
    content += "Q"
    for _ in range(nested):
        form = DecodedStreamObject()
        form.set_data(content.encode())
        form.update(
            {
                NameObject("/Type"): NameObject("/XObject"),
                NameObject("/Subtype"): NameObject("/Form"),
                NameObject("/BBox"): ArrayObject(
                    [NumberObject(0), NumberObject(0), NumberObject(300), NumberObject(240)]
                ),
                NameObject("/Resources"): resources,
            }
        )
        resources = DictionaryObject(
            {
                NameObject("/XObject"): DictionaryObject(
                    {NameObject("/Fm"): writer._add_object(form)}
                )
            }
        )
        content = "q .5 0 0 .5 0 0 cm /Fm Do Q"
    page[NameObject("/Resources")] = resources
    stream = DecodedStreamObject()
    stream.set_data(content.encode())
    page[NameObject("/Contents")] = writer._add_object(stream)
    page[NameObject("/UserUnit")] = FloatObject(unit)
    if rotation:
        page.rotate(rotation)
    if crop:
        page.cropbox.lower_left = (20, 20)
        page.cropbox.upper_right = (280, 220)
    writer.write(path)
    return path


def check(report, name):
    return next(c for c in report["pages"][0]["visual"]["checks"] if c["name"] == name)


@pytest.mark.parametrize(
    ("scale", "unit", "nested", "expected"),
    [(1, 1, 0, 8), (0.5, 1, 0, 4), (1, 2, 0, 16), (0.5, 2, 0, 8), (1, 1, 2, 2)],
)
def test_transformed_font_size_and_correction_preserve_source(
    tmp_path, scale, unit, nested, expected
):
    path = primitive(tmp_path / "source.pdf", scale=scale, unit=unit, nested=nested)
    original = path.read_bytes()
    report = review_pdf(path, output=tmp_path / "packet", dpi=72)
    metric = check(report, "text_size")
    assert metric["status"] == "checked" and metric["minimum_pt"] == pytest.approx(expected)
    findings = report["pages"][0]["visual"]["findings"]
    assert ("pdf_small_text" in {f["code"] for f in findings}) is (expected < 6)
    assert all(f["consequence"] and f["correction"] for f in findings)
    assert report["status"] == "incomplete" and report["exit_code"] == 2
    assert all(c["status"] == "untested" for c in report["checks"])
    assert (
        path.read_bytes() == original
        and report["source"]["sha256"] == hashlib.sha256(original).hexdigest()
    )
    assert report["pages"][0]["points"] == pytest.approx([300 * unit, 240 * unit])
    if expected < 6:
        corrected = primitive(tmp_path / "corrected.pdf")
        assert (
            check(review_pdf(corrected, output=tmp_path / "corrected packet"), "text_size")[
                "characters_below_threshold"
            ]
            == 0
        )


@pytest.mark.parametrize(
    ("scale", "unit", "nested", "expected_dpi"),
    [(1, 1, 0, 16), (0.5, 1, 0, 32), (1, 2, 0, 8), (1, 1, 2, 64)],
)
def test_embedded_pixel_density_uses_source_pixels_and_all_form_transforms(
    tmp_path, scale, unit, nested, expected_dpi
):
    source = primitive(tmp_path / "image.pdf", scale=scale, unit=unit, nested=nested, image=True)
    for dpi in [72, 144]:
        report = review_pdf(source, output=tmp_path / str(dpi), dpi=dpi)
        metric = check(report, "raster_resolution")
        assert metric["status"] == "checked" and metric["placements_measured"] == 1
        actual = report["pages"][0]["visual"]["image_samples"][0]
        assert actual["pixels"] == [16, 16] and actual["dpi"] == pytest.approx([expected_dpi] * 2)
        assert any(
            f["code"] == "pdf_low_raster_resolution"
            for f in report["pages"][0]["visual"]["findings"]
        )


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_selected_region_membership_survives_rotation_crop_and_user_units(tmp_path, rotation):
    source = primitive(tmp_path / "rotated.pdf", image=True, rotation=rotation, crop=True, unit=2)
    # Locate the actual rendered red/blue pixels independently of PDF-object metrics.
    first = review_pdf(source, output=tmp_path / "full", dpi=144)
    page = first["pages"][0]
    w, h = page["preview"]["width"], page["preview"]["height"]
    import numpy as np
    from PIL import Image

    with Image.open(tmp_path / "full" / page["preview"]["path"]) as image:
        pixels = np.asarray(image.convert("RGB"))
    rows, columns = np.where(
        (pixels[:, :, 1] < 50) & ((pixels[:, :, 0] > 200) | (pixels[:, :, 2] > 200))
    )
    l, t, r, b = (
        float(columns.min()),
        float(rows.min()),
        float(columns.max() + 1),
        float(rows.max() + 1),
    )
    assert page["visual"]["image_samples"][0]["pixel_box"] == pytest.approx([l, t, r, b], abs=1)
    box = [(l + 2) / w, (t + 2) / h, (l + r) / (2 * w), (t + b) / (2 * h)]
    report = review_pdf(
        source,
        output=tmp_path / "selected",
        dpi=144,
        regions=[
            {"id": "image", "page": 1, "box": box},
            {"id": "empty", "page": 1, "box": [0.9, 0.9, 1, 1]},
        ],
    )
    selected, empty = report["regions"]
    assert selected["visual"]["checks"][1]["placements_measured"] == 1
    assert empty["visual"]["checks"][1]["placements_measured"] == 0
    assert selected["visual"]["checks"][0]["characters_measured"] == 0


def test_invisible_text_and_raster_only_labels_do_not_become_passed_text_checks(tmp_path):
    source = primitive(tmp_path / "hidden.pdf", image=True, invisible=True)
    report = review_pdf(source, output=tmp_path / "packet")
    assert check(report, "text_size")["status"] == "untested"
    assert check(report, "raster_resolution")["status"] == "checked"


def test_scan_caps_and_missing_capabilities_are_explicit(tmp_path, monkeypatch):
    source = primitive(tmp_path / "bounded.pdf", image=True)
    monkeypatch.setattr(pdf_visual, "MAX_CHARACTERS", 2)
    monkeypatch.setattr(pdf_visual, "MAX_OBJECTS", 1)
    report = review_pdf(source, output=tmp_path / "capped", prepare_only=True)
    visual = report["pages"][0]["visual"]
    assert all(c["status"] == "partial" for c in visual["checks"])
    assert visual["coverage"]["page_characters_examined"] == 2
    assert report["status"] == "incomplete" and report["exit_code"] == 0
    assert any(f["code"] == "pdf_visual_checks_partial" for f in visual["findings"])
    import pypdfium2

    monkeypatch.delattr(pypdfium2.raw, "FPDFText_GetMatrix")
    report = review_pdf(source, output=tmp_path / "unavailable")
    assert check(report, "text_size")["status"] == "partial"


@pytest.mark.parametrize(
    "name,value", [("min_text_pt", 0), ("min_image_dpi", float("nan")), ("min_text_pt", True)]
)
def test_invalid_review_thresholds_reject_before_writing(tmp_path, name, value):
    source = primitive(tmp_path / "source.pdf")
    with pytest.raises(ValueError, match="finite positive"):
        review_pdf(source, output=tmp_path / "absent", **{name: value})
    assert not (tmp_path / "absent").exists()


def test_html_escapes_pdf_content_and_reports_visual_scope(tmp_path):
    source = primitive(tmp_path / "literal.pdf", scale=0.5)
    folder = tmp_path / "packet"
    report = review_pdf(source, output=folder)
    text = (folder / "pdf-review.html").read_text()
    assert "&lt;script&gt;value&lt;/script&gt;" in text and "<script>value</script>" not in text
    assert "Why it matters:" in text and "Recommended correction:" in text
    assert json.loads((folder / "pdf-review.json").read_text()) == report


def test_rotated_image_bounding_box_corner_does_not_enter_a_selection(tmp_path):
    import numpy as np
    from PIL import Image

    source = primitive(tmp_path / "diamond.pdf", image=True, image_angle=45)
    folder = tmp_path / "full"
    review_pdf(source, output=folder, dpi=144)
    with Image.open(folder / "page-1.png") as image:
        pixels = np.asarray(image.convert("RGB"))
    mask = (pixels[:, :, 1] < 50) & ((pixels[:, :, 0] > 200) | (pixels[:, :, 2] > 200))
    rows, cols = np.where(mask)
    left, top = int(cols.min() + 3), int(rows.min() + 3)
    assert not mask[top : top + 3, left : left + 3].any()
    height, width = mask.shape
    selected = review_pdf(
        source,
        output=tmp_path / "corner",
        dpi=144,
        regions=[
            {
                "id": "corner",
                "page": 1,
                "box": [left / width, top / height, (left + 3) / width, (top + 3) / height],
            }
        ],
    )
    assert selected["regions"][0]["visual"]["checks"][1]["placements_measured"] == 0


@pytest.mark.parametrize("unit", [0, -1, 1e300])
def test_invalid_or_unrenderable_user_unit_fails_cleanly(tmp_path, unit):
    source = primitive(tmp_path / "units.pdf", unit=unit)
    with pytest.raises(ValueError, match=r"UserUnit|megapixel|physical-unit metadata"):
        review_pdf(source, output=tmp_path / "packet")


def test_cli_records_custom_thresholds_without_certifying_the_pdf(tmp_path, capsys):
    from graphunslopify.cli import main

    source = primitive(tmp_path / "source.pdf")
    assert (
        main(
            [
                "audit-pdf",
                str(source),
                "--out-dir",
                str(tmp_path / "packet"),
                "--min-text-pt",
                "9",
                "--min-image-dpi",
                "300",
                "--prepare-only",
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["visual_policy"] == {"minimum_text_pt": 9, "minimum_image_dpi": 300}
    assert (
        report["status"] == "incomplete"
        and check(report, "text_size")["characters_below_threshold"] > 0
    )


def test_indirect_numeric_user_unit_is_resolved_before_physical_measurement(tmp_path):
    source = primitive(tmp_path / "direct.pdf")
    writer = PdfWriter()
    writer.append_pages_from_reader(PdfReader(source))
    writer.pages[0][NameObject("/UserUnit")] = writer._add_object(FloatObject(2))
    indirect = tmp_path / "indirect.pdf"
    writer.write(indirect)
    report = review_pdf(indirect, output=tmp_path / "packet", dpi=72)
    assert check(report, "text_size")["minimum_pt"] == 16
    assert report["pages"][0]["points"] == [600, 480]
