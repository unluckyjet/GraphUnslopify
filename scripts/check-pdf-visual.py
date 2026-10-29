"""Exercise actual installed source-free PDF metrics and strict preparation policy."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    from graphunslopify import Figure
    from graphunslopify.pdf_review import review_pdf
    from pypdf import PdfReader, PdfWriter, Transformation

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path)
    args = parser.parse_args()
    where = (args.work_dir or Path(tempfile.mkdtemp(prefix="gu-pdf-visual-"))).resolve()
    if where.exists() and any(where.iterdir()):
        parser.error("choose a new/empty evidence directory")
    where.mkdir(parents=True, exist_ok=True)
    data = where / "observations.csv"
    data.write_bytes(b"x,y\n1,1\n2,3\n3,4\n")
    figure = (
        Figure.line(data)
        .x("x", "X")
        .y("y", "Y")
        .set(legend={"show": False})
        .output(formats=["pdf"])
    )
    with contextlib.redirect_stdout(sys.stderr):
        figure.render(cwd=where / "native")
    original = where / "native/figure.pdf"
    before = original.read_bytes()
    native = review_pdf(original, output=where / "native review", dpi=72)
    normal = native["pages"][0]["visual"]["checks"][0]
    assert normal["status"] == "checked" and normal["minimum_pt"] >= 6
    writer = PdfWriter()
    page = PdfReader(original).pages[0]
    page.add_transformation(Transformation().scale(0.5))
    writer.add_page(page)
    reduced = where / "reduced.pdf"
    writer.write(reduced)
    reduced_bytes = reduced.read_bytes()
    command = [
        sys.executable,
        "-m",
        "graphunslopify.cli",
        "audit-pdf",
        str(reduced),
        "--dpi",
        "72",
    ]
    failed = subprocess.run(
        [*command, "--out-dir", str(where / "reduced review")],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    report = json.loads(failed.stdout)
    assert (
        failed.returncode == report["exit_code"] == 2
        and report["status"] == "incomplete"
    )
    visual = report["pages"][0]["visual"]
    measured = visual["checks"][0]
    assert abs(measured["minimum_pt"] - normal["minimum_pt"] * 0.5) < 1e-5
    assert any(
        f["code"] == "pdf_small_text" and f["consequence"] and f["correction"]
        for f in visual["findings"]
    )
    prepared = subprocess.run(
        [*command, "--out-dir", str(where / "prepare only"), "--prepare-only"],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    assert json.loads(prepared.stdout)["status"] == "incomplete"
    assert original.read_bytes() == before and reduced.read_bytes() == reduced_bytes
    assert report["source"]["sha256"] == hashlib.sha256(reduced_bytes).hexdigest()
    html = (where / "reduced review/pdf-review.html").read_text()
    assert "Why it matters:" in html and "Recommended correction:" in html
    print(
        json.dumps(
            {
                "status": "passed",
                "native_pt": normal["minimum_pt"],
                "reduced_pt": measured["minimum_pt"],
                "strict_default_exit": failed.returncode,
                "prepare_only_exit": prepared.returncode,
                "scientific_status": "incomplete",
                "source_bytes_unchanged": True,
                "where": str(where),
            }
        )
    )


if __name__ == "__main__":
    main()
