"""Read actual exported pixels/vectors and verify reproducible provenance."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from PIL import Image, PngImagePlugin
from pypdf import PdfReader, PdfWriter

from graphunslopify import read_provenance
from graphunslopify.cli import main

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    if shutil.which("node") is None:
        pytest.skip("Node is needed for the real emitter")
    directory = tmp_path_factory.mktemp("provenance")
    spec = {
        "kind": "line",
        "x": {"field": "epoch", "label": "Epoch"},
        "y": {"field": "score", "label": "Score Δ & rate", "unit": "%"},
        "title": "Scores Δ & uncertainty",
        "alt_text": 'Author context: "quoted" <tag> & µ.\nSecond line. ',
        "group": "model",
        "aggregation": "mean",
        "legend": {"show": False},
        "uncertainty": {"kind": "sem", "over": "seed"},
        "claims": [{"kind": "beats_everywhere", "subject": "ours", "reference": "base"}],
        "output": {"stem": "figure", "dpi": 100},
    }
    generated = subprocess.run(
        [
            "node",
            "--experimental-strip-types",
            "--input-type=module",
            "-e",
            (
                "import {translate} from './src/translate.ts'; import fs from 'node:fs';"
                "process.stdout.write(translate(JSON.parse(fs.readFileSync(0,'utf8'))).code);"
            ),
        ],
        input=json.dumps(spec),
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    (directory / "figure.py").write_text(generated.stdout)
    (directory / "results.csv").write_text(
        "epoch,score,model,seed\n1,1,base,0\n1,2,base,1\n1,3,ours,0\n1,4,ours,1\n"
        "2,2,base,0\n2,3,base,1\n2,5,ours,0\n2,6,ours,1\n"
    )
    subprocess.run(
        [sys.executable, "figure.py", "--strict"], cwd=directory, capture_output=True, check=True
    )
    return directory


@pytest.mark.parametrize("extension", ["png", "svg", "pdf"])
def test_each_export_carries_the_same_spec_description_and_fingerprints(rendered, extension):
    evidence = read_provenance(rendered / f"figure.{extension}")
    report = json.loads((rendered / "figure.report.json").read_text())
    assert evidence["schema_version"] == 1
    assert evidence["spec"] == report["spec"]
    assert evidence["spec_hash"] == report["spec_hash"]
    assert evidence["alt_text"] == report["alt_text"]
    assert '"quoted" <tag> & µ' in evidence["alt_text"]
    assert (
        evidence["data_sha256_prefix"]
        == hashlib.sha256((rendered / "results.csv").read_bytes()).hexdigest()[:16]
    )
    assert (
        evidence["script_sha256"]
        == hashlib.sha256((rendered / "figure.py").read_bytes()).hexdigest()
    )
    assert evidence["script_sha256"] == report["script"]["sha256"]
    if extension == "png":
        with Image.open(rendered / "figure.png") as image:
            assert json.loads(image.info["Description"]) == evidence["spec"]
            assert image.info["Comment"] == evidence["alt_text"]
    elif extension == "svg":
        root = ET.parse(rendered / "figure.svg").getroot()
        assert (
            root.find(".//{http://purl.org/dc/elements/1.1/}description").text
            == evidence["alt_text"]
        )
        assert root.find(".//{http://purl.org/dc/elements/1.1/}date") is None
        desc = root.find("{http://www.w3.org/2000/svg}desc")
        assert desc.text == evidence["alt_text"]
        assert root.get("role") == "img"
        assert root.get("aria-describedby") == desc.get("id")
        assert root.get("aria-labelledby") == root.find("{http://www.w3.org/2000/svg}title").get(
            "id"
        )
    else:
        info = PdfReader(rendered / "figure.pdf").metadata
        assert json.loads(info["/Subject"]) == evidence["spec"]
        assert "/CreationDate" not in info and "/ModDate" not in info


def test_rerendering_identical_inputs_produces_identical_png_svg_and_pdf_bytes(rendered):
    before = {
        extension: (rendered / f"figure.{extension}").read_bytes()
        for extension in ("png", "svg", "pdf")
    }
    subprocess.run(
        [sys.executable, "figure.py", "--strict"], cwd=rendered, capture_output=True, check=True
    )
    for extension, original in before.items():
        assert (rendered / f"figure.{extension}").read_bytes() == original, extension


def test_legacy_png_recovers_only_the_evidence_it_really_contains(tmp_path):
    info = PngImagePlugin.PngInfo()
    info.add_text("Software", "GraphUnslopify 0.6.0 spec:0123456789abcdef data:abcdef0123456789")
    info.add_text("Description", '{"kind":"line"}')
    info.add_text("Comment", "")
    path = tmp_path / "legacy.png"
    Image.new("RGB", (2, 2)).save(path, pnginfo=info)
    evidence = read_provenance(path)
    assert evidence["schema_version"] == 0
    assert evidence["data_sha256_prefix"] == "abcdef0123456789"
    assert evidence["script_sha256"] is None
    assert evidence["alt_text"] == ""


def test_legacy_pdf_recovers_spec_without_inventing_description(tmp_path):
    path = tmp_path / "legacy.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.add_metadata({"/Creator": "GraphUnslopify 0.6.0", "/Subject": '{"kind":"line"}'})
    writer.write(path)
    evidence = read_provenance(path)
    assert evidence["schema_version"] == 0
    assert evidence["spec_hash"] is None
    assert evidence["alt_text"] == ""


def test_missing_and_corrupt_metadata_are_rejected(tmp_path):
    path = tmp_path / "plain.svg"
    path.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    with pytest.raises(ValueError, match="No GraphUnslopify"):
        read_provenance(path)
    info = PngImagePlugin.PngInfo()
    info.add_text("GraphUnslopify", "{")
    path = tmp_path / "corrupt.png"
    Image.new("RGB", (2, 2)).save(path, pnginfo=info)
    with pytest.raises(ValueError, match="Invalid embedded"):
        read_provenance(path)


def test_cli_reads_embedded_evidence_without_running_the_program(rendered, capsys):
    assert main(["provenance", str(rendered / "figure.svg")]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is True
    assert result["provenance"]["script_sha256"]


@pytest.mark.parametrize(
    "payload",
    ["[]", '{"schema_version":2}', '{"schema_version":true}', '{"schema_version":1,"spec":{}}'],
)
def test_unsupported_or_incomplete_envelopes_fail_explicitly(tmp_path, payload):
    info = PngImagePlugin.PngInfo()
    info.add_text("GraphUnslopify", payload)
    path = tmp_path / "invalid.png"
    Image.new("RGB", (2, 2)).save(path, pnginfo=info)
    with pytest.raises(ValueError):
        read_provenance(path)
