"""Actual SVG glyphs must retain literal/math interpretation after heading wrapping."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import xml.etree.ElementTree as ET

import matplotlib.pyplot as plt
import pytest

from graphunslopify.transport import local_request


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    folder = tmp_path_factory.mktemp("heading-context")
    result = local_request(
        "convert",
        {
            "kind": "line",
            "x": {"field": "epoch", "label": "Epoch"},
            "y": {"field": "score", "label": "Score"},
            "legend": {"show": False},
        },
    )
    assert result["ok"], result
    path = folder / "context.py"
    path.write_text(result["code"])
    definition = importlib.util.spec_from_file_location("heading_context", path)
    module = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(module)
    return module


def svg_text(fig):
    with plt.rc_context({"svg.fonttype": "none"}):
        output = io.BytesIO()
        fig.savefig(output, format="svg", bbox_inches="tight")
    root = ET.fromstring(output.getvalue())
    return "".join(
        "".join(t.itertext()) for t in root.findall(".//{http://www.w3.org/2000/svg}text")
    )


def exported_glyph_count(svg, character, rc_params):
    text = "".join(
        "".join(t.itertext()) for t in svg.findall(".//{http://www.w3.org/2000/svg}text")
    )
    # Font IDs use codepoints in3.10 and glyph indices in newer Matplotlib.
    # Independently render the expected glyph with the same publication fonts.
    with plt.rc_context({**rc_params, "svg.fonttype": "path"}):
        fig, ax = plt.subplots()
        try:
            ax.axis("off")
            greek = character == "\N{GREEK SMALL LETTER ALPHA}"
            ax.text(0.1, 0.1, r"$\alpha$" if greek else character, parse_math=greek)
            buffer = io.BytesIO()
            fig.savefig(buffer, format="svg")
            reference = ET.fromstring(buffer.getvalue())
        finally:
            plt.close(fig)
    glyph_ids = {
        use.get("{http://www.w3.org/1999/xlink}href", use.get("href", ""))
        for use in reference.findall(".//{http://www.w3.org/2000/svg}use")
    }
    assert len(glyph_ids) == 1
    outlined = sum(
        use.get("{http://www.w3.org/1999/xlink}href", use.get("href", "")) in glyph_ids
        for use in svg.findall(".//{http://www.w3.org/2000/svg}use")
    )
    return text.count(character) + outlined


CASES = [
    ("Measured prices at $5 and $10 and $15 in the original measurement currency", True, 3, 0),
    ("Prices $1 and $2 and $3 and $4 and $5 with all original observations retained", True, 5, 0),
    (
        r"Measured response $\alpha + \beta$" + "\nNominal price $15 in the original currency",
        True,
        1,
        1,
    ),
    (r"Measured prices at \$5 and \$10 and \$15 in the original measurement currency", True, 3, 0),
    (r"Measured prices at \$5 and \$10 and \$15 in the original measurement currency", False, 3, 0),
    ("Measured prices at $5 and $10 and $15 in the original measurement currency", False, 3, 0),
    (r"Measured response $\alpha + \beta$ and comparison $x + y$ retained", True, 0, 1),
    ("Prices($5,$10) with $15 applied to the original observations", True, 3, 0),
    (r"Measured response $\alpha + \beta$" + "\n\nOriginal price $15\n", True, 1, 1),
]


@pytest.mark.parametrize("width", [35, 70, 100, 140, 180])
@pytest.mark.parametrize(("original", "parse_math", "dollars", "alpha"), CASES)
def test_actual_svg_keeps_currency_formula_and_original_wording(
    generated, width, original, parse_math, dollars, alpha
):
    fig, ax = plt.subplots(figsize=(4, 3))
    try:
        ax.axis("off")
        artist = ax.text(0.01, 0.95, original, va="top", fontsize=12, parse_math=parse_math)
        fig.canvas.draw()
        before = svg_text(fig)
        wrapped = generated.wrap_heading(original, artist, fig.canvas.get_renderer(), width)
        assert wrapped.split() == original.split()
        artist.set_text(wrapped)
        after = svg_text(fig)
        assert before.count("$") == after.count("$") == dollars
        assert (
            before.count("\N{GREEK SMALL LETTER ALPHA}")
            == after.count("\N{GREEK SMALL LETTER ALPHA}")
            == alpha
        )
        assert artist.get_fontsize() == 12 and artist.get_parse_math() == parse_math
        # Raw escaped currency remains literal under an explicitly disabled parser.
        if not parse_math:
            assert before.count("\\") == after.count("\\")
    finally:
        plt.close(fig)


@pytest.mark.parametrize("title", [CASES[0][0], CASES[2][0]])
def test_strict_generated_export_preserves_glyphs_data_and_canonical_title(
    generated, tmp_path, title
):
    raw = b"epoch,score\n1,1\n2,2\n3,3\n"
    (tmp_path / "data.csv").write_bytes(raw)
    spec = {
        "kind": "line",
        "title": title,
        "x": {"field": "epoch", "label": "Epoch"},
        "y": {"field": "score", "label": "Score"},
        "legend": {"show": False},
        "data": {"path": "data.csv"},
        "output": {"stem": "literal", "formats": ["png", "svg", "pdf"]},
    }
    result = local_request("convert", spec)
    assert result["ok"], result
    (tmp_path / "literal.py").write_text(result["code"])
    run = subprocess.run(
        [sys.executable, "literal.py", "--strict", "--json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    report = json.loads(run.stdout)
    assert run.returncode == 0 and report["status"] == "passed", report
    assert report["spec"]["title"] == title
    assert report["data"]["counts"]["read"] == 3
    assert report["data"]["sha256_prefix"] == hashlib.sha256(raw).hexdigest()[:16]
    assert (tmp_path / "data.csv").read_bytes() == raw
    svg = ET.parse(tmp_path / "literal.svg").getroot()
    assert exported_glyph_count(svg, "$", generated.RC_PARAMS) == (1 if "alpha" in title else 3)
    if "alpha" in title:
        assert exported_glyph_count(svg, "\N{GREEK SMALL LETTER ALPHA}", generated.RC_PARAMS) == 1
    assert all((tmp_path / f"literal.{fmt}").stat().st_size > 100 for fmt in ["png", "svg", "pdf"])


def test_malformed_authored_math_still_fails_actual_render(tmp_path):
    (tmp_path / "data.csv").write_text("epoch,score\n1,1\n2,2\n")
    result = local_request(
        "convert",
        {
            "kind": "line",
            "title": r"Invalid authored expression $\frac{a}$",
            "x": {"field": "epoch", "label": "Epoch"},
            "y": {"field": "score", "label": "Score"},
            "data": {"path": "data.csv"},
            "legend": {"show": False},
        },
    )
    assert result["ok"]
    (tmp_path / "invalid.py").write_text(result["code"])
    run = subprocess.run(
        [sys.executable, "invalid.py", "--strict", "--json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    report = json.loads(run.stdout)
    assert run.returncode == 1 and report["status"] == "failed"
    assert any(f["code"] == "runtime_error" for f in report["findings"])
