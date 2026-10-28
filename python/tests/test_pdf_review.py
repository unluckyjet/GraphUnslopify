"""Real PDF review packets never turn missing numerical evidence into a pass."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter

from graphunslopify.pdf_review import review_pdf

BASELINE = Path(__file__).resolve().parents[2] / "examples/baseline/01-training-curve.pdf"


@pytest.fixture
def paper(tmp_path):
    pytest.importorskip("pypdfium2")
    destination = tmp_path / "paper.pdf"
    writer = PdfWriter()
    writer.add_page(PdfReader(BASELINE).pages[0])
    writer.add_blank_page(width=72, height=144)
    with destination.open("wb") as handle:
        writer.write(handle)
    return destination


@pytest.mark.parametrize("prepare_only", [False, True])
def test_pdf_cli_preparation_policy_and_retained_evidence(paper, tmp_path, prepare_only):
    original = paper.read_bytes()
    folder = tmp_path / "packet"
    command = [
        sys.executable,
        "-m",
        "graphunslopify.cli",
        "audit-pdf",
        str(paper),
        "--pages",
        "2",
        "--out-dir",
        str(folder),
        "--dpi",
        "72",
    ]
    result = subprocess.run(
        command + (["--prepare-only"] if prepare_only else []),
        capture_output=True,
        text=True,
        check=False,
    )
    report = json.loads(result.stdout)
    assert report["status"] == "incomplete"
    assert result.returncode == report["exit_code"] == (0 if prepare_only else 2)
    assert report["policy"] == {"prepare_only": prepare_only, "passed": prepare_only}
    assert all(check["status"] == "untested" for check in report["checks"])
    assert report == json.loads((folder / "pdf-review.json").read_text())
    assert report["source"]["sha256"] == hashlib.sha256(original).hexdigest()
    assert paper.read_bytes() == original
    assert len(report["pages"]) == 1 and report["pages"][0]["page"] == 2
    assert report["pages"][0]["text"]["status"] == "unavailable"
    with Image.open(folder / "page-2.png") as image:
        assert image.size == (72, 144)
    assert (folder / "pdf-review.html").is_file()


def test_pdf_regions_are_actual_normalized_crops_with_hashes(paper, tmp_path):
    region = {"id": "figure-1", "page": 1, "box": [0.1, 0.2, 0.8, 0.7]}
    folder = tmp_path / "packet"
    report = review_pdf(paper, output=folder, pages=[1], regions=[region])
    selected = report["regions"][0]
    with (
        Image.open(folder / "page-1.png") as page,
        Image.open(folder / "region-figure-1.png") as crop,
    ):
        expected = [
            math.floor(0.1 * page.width),
            math.floor(0.2 * page.height),
            math.ceil(0.8 * page.width),
            math.ceil(0.7 * page.height),
        ]
        assert selected["pixel_box"] == expected
        with page.crop(expected) as oracle:
            assert crop.size == oracle.size and crop.tobytes() == oracle.tobytes()
    assert (
        selected["image"]["sha256"]
        == hashlib.sha256((folder / "region-figure-1.png").read_bytes()).hexdigest()
    )
    assert report["pages"][0]["text"]["status"] == "extracted"


@pytest.mark.parametrize("pages", [[], [0], [-1], [3], [1, 1], [True]])
def test_pdf_invalid_page_selection_is_explicit(paper, tmp_path, pages):
    with pytest.raises(ValueError, match="pages"):
        review_pdf(paper, output=tmp_path / "packet", pages=pages)


@pytest.mark.parametrize("dpi", [0, 71, 301, True, 144.5])
def test_pdf_invalid_resolution_is_explicit(paper, tmp_path, dpi):
    with pytest.raises(ValueError, match="dpi"):
        review_pdf(paper, output=tmp_path / "packet", dpi=dpi)


@pytest.mark.parametrize(
    "change",
    [
        {"id": "../escape"},
        {"id": ""},
        {"page": 0},
        {"page": 2},
        {"box": [0, 0, 2, 1]},
        {"box": [0.8, 0.2, 0.1, 0.9]},
        {"box": [0, 0, float("nan"), 1]},
        {"box": [False, 0, 1, 1]},
        {"box": [0, 0, 0, 1]},
        {"unexpected": True},
    ],
)
def test_pdf_invalid_regions_refuse_without_outputs(paper, tmp_path, change):
    folder = tmp_path / "packet"
    region = {"id": "figure", "page": 1, "box": [0, 0, 1, 1], **change}
    with pytest.raises(ValueError):
        review_pdf(paper, output=folder, pages=[1], regions=[region])
    assert not folder.exists()


def test_pdf_duplicate_regions_and_previous_outputs_are_preserved(paper, tmp_path):
    folder = tmp_path / "packet"
    region = {"id": "figure", "page": 1, "box": [0, 0, 1, 1]}
    with pytest.raises(ValueError, match="unique"):
        review_pdf(paper, output=folder, pages=[1], regions=[region, region])
    folder.mkdir()
    marker = folder / "pdf-review.json"
    marker.write_text("existing evidence")
    with pytest.raises(ValueError, match="empty"):
        review_pdf(paper, output=folder)
    assert marker.read_text() == "existing evidence"


def test_pdf_casefold_collisions_are_rejected_on_every_platform(paper, tmp_path):
    folder = tmp_path / "packet"
    regions = [
        {"id": "Figure", "page": 1, "box": [0, 0, 0.5, 0.5]},
        {"id": "figure", "page": 1, "box": [0.5, 0.5, 1, 1]},
    ]
    with pytest.raises(ValueError, match="unique ignoring case"):
        review_pdf(paper, output=folder, pages=[1], regions=regions, prepare_only=True)
    assert not folder.exists()


def test_pdf_embedded_metadata_does_not_validate_original_data(tmp_path):
    pytest.importorskip("pypdfium2")
    report = review_pdf(BASELINE, output=tmp_path / "packet", pages=[1], prepare_only=True)
    assert report["embedded_provenance"]["available"]
    assert not report["embedded_provenance"]["authenticated"]
    assert report["status"] == "incomplete"


def test_pdf_missing_optional_dependency_is_actionable(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "pypdfium2", None)
    with pytest.raises(ValueError, match=r"graphunslopify\[pdf\]"):
        review_pdf(BASELINE, output=tmp_path / "packet")


def test_pdf_malformed_file_returns_nonzero_json(tmp_path):
    pytest.importorskip("pypdfium2")
    source = tmp_path / "broken.pdf"
    source.write_text("not a PDF")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "graphunslopify.cli",
            "audit-pdf",
            str(source),
            "--out-dir",
            str(tmp_path / "packet"),
            "--prepare-only",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["status"] == "failed"


def test_pdf_source_name_is_escaped_in_offline_html(paper, tmp_path):
    source = tmp_path / "<untrusted&>.pdf"
    source.write_bytes(paper.read_bytes())
    folder = tmp_path / "packet"
    review_pdf(source, output=folder, pages=[1])
    page = (folder / "pdf-review.html").read_text()
    assert "&lt;untrusted&amp;&gt;.pdf" in page
    assert "<untrusted&>.pdf" not in page
