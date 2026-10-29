"""Local visual review packets for PDFs without requiring figure source data."""

from __future__ import annotations

import hashlib
import html
import importlib.metadata
import json
import math
import re
from contextlib import closing
from pathlib import Path
from typing import Any

from .pdf_visual import inspect_region, scan_page
from .provenance import read_provenance


def _digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            result.update(block)
    return result.hexdigest()


def _regions(value: Any, selected: list[int]) -> list[dict]:
    if not isinstance(value, list) or len(value) > 200:
        raise ValueError("regions must be a JSON list with at most 200 selections")
    names = set()
    for region in value:
        if not isinstance(region, dict) or set(region) != {"id", "page", "box"}:
            raise ValueError("each region requires exactly id, page and box")
        name = region["id"]
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", name):
            raise ValueError("region id must be 1-64 letters/digits/underscores/hyphens")
        if name.casefold() in names:
            raise ValueError("region IDs must be unique ignoring case")
        names.add(name.casefold())
        if type(region["page"]) is not int or region["page"] not in selected:
            raise ValueError("region page must be one of the selected one-based pages")
        box = region["box"]
        if (
            not isinstance(box, list)
            or len(box) != 4
            or any(
                type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in box
            )
            or not box[0] < box[2]
            or not box[1] < box[3]
        ):
            raise ValueError("region box must be normalized [left, top, right, bottom] within 0..1")
    return value


def _artifact(path: Path, image) -> dict:
    return {
        "path": path.name,
        "sha256": _digest(path),
        "bytes": path.stat().st_size,
        "width": image.width,
        "height": image.height,
    }


def _visual_html(visual):
    parts = ['<section aria-label="Visual measurements"><p>']
    for check in visual["checks"]:
        parts.append(html.escape(f"{check['name']}: {check['status']}. "))
        if check["name"] == "text_size" and check["minimum_pt"] is not None:
            parts.append(
                html.escape(
                    f"{check['characters_measured']} extracted characters, minimum {check['minimum_pt']:.3g}pt; review threshold {check['threshold_pt']:g}pt. "
                )
            )
        if check["name"] == "raster_resolution" and check["minimum_dpi"] is not None:
            parts.append(
                html.escape(
                    f"{check['placements_measured']} image placements, minimum {check['minimum_dpi']:.3g} source dpi; review threshold {check['threshold_dpi']:g}dpi. "
                )
            )
        for reason in check["reasons"]:
            parts.append(html.escape(reason + ". "))
    parts.append("</p>")
    for finding in visual["findings"]:
        parts.append(
            '<div class="notice"><strong>'
            + html.escape(finding["code"])
            + "</strong><p>"
            + html.escape(finding["message"])
            + "</p><p><strong>Why it matters:</strong> "
            + html.escape(finding["consequence"])
            + "</p><p><strong>Recommended correction:</strong> "
            + html.escape(finding["correction"])
            + "</p></div>"
        )
    for sample in visual["text_samples"]:
        l, t, r, b = visual["selection_pixel_box"]
        sl, st, sr, sb = sample["pixel_box"]
        x, y = (
            max(0, min(100, 100 * ((sl + sr) / 2 - l) / (r - l))),
            max(0, min(100, 100 * ((st + sb) / 2 - t) / (b - t))),
        )
        parts.append(
            "<p>Small-text sample: "
            + html.escape(sample["text"])
            + html.escape(
                f" ({sample['minimum_pt']:.3g}pt, near {x:.0f}% across / {y:.0f}% down this selection)"
            )
            + "</p>"
        )
    parts.append("</section>")
    return "\n".join(parts)


def review_pdf(
    path: str | Path,
    *,
    output: str | Path,
    pages: list[int] | None = None,
    regions: list[dict] | None = None,
    dpi: int = 144,
    prepare_only: bool = False,
    min_text_pt: float = 6.0,
    min_image_dpi: float = 150.0,
) -> dict:
    """Inspect page/crop visual metrics; scientific verification remains incomplete.

    No original programs are executed and no OCR, caption inference, arbitrary
    chart reconstruction or numerical claim validation is performed.
    """
    try:
        import pypdfium2 as pdfium
    except ImportError as problem:
        raise ValueError("Install graphunslopify[pdf] to render PDF review packets") from problem
    source = Path(path).expanduser().resolve()
    for name, value in (("min_text_pt", min_text_pt), ("min_image_dpi", min_image_dpi)):
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be a finite positive number")
    if type(dpi) is not int or not 72 <= dpi <= 300:
        raise ValueError("dpi must be an integer between 72 and 300")
    original_hash = _digest(source)
    try:
        document = pdfium.PdfDocument(source)
    except pdfium.PdfiumError as problem:
        raise ValueError(
            f"Cannot open PDF (including protected/unreadable files): {problem}"
        ) from problem
    with document:
        selected = list(range(1, len(document) + 1)) if pages is None else pages
        if (
            not selected
            or len(selected) > 50
            or len(set(selected)) != len(selected)
            or any(type(n) is not int or not 1 <= n <= len(document) for n in selected)
        ):
            raise ValueError("select 1-50 distinct one-based pages within this PDF")
        selections = _regions([] if regions is None else regions, selected)
        from pypdf import PdfReader
        from pypdf.errors import PyPdfError

        units = {}
        try:
            reader = PdfReader(source)
            for number in selected:
                unit = reader.pages[number - 1].get("/UserUnit", 1)
                if hasattr(unit, "get_object"):
                    unit = unit.get_object()
                if (
                    isinstance(unit, bool)
                    or not isinstance(unit, (int, float))
                    or not math.isfinite(unit)
                    or unit <= 0
                ):
                    raise ValueError(f"page {number} UserUnit must be a finite positive number")
                units[number] = float(unit)
        except (PyPdfError, IndexError, TypeError) as problem:
            raise ValueError(
                f"PDF physical-unit metadata could not be parsed: {problem}"
            ) from problem
        destination = Path(output).expanduser().resolve()
        destination.mkdir(parents=True, exist_ok=True)
        if any(destination.iterdir()):
            raise ValueError(
                "choose an empty output directory; existing review evidence is preserved"
            )
        report: dict[str, Any] = {
            "schema_version": 1,
            "scope": "source-free PDF visual metrics and review",
            "status": "incomplete",
            "exit_code": 0 if prepare_only else 2,
            "policy": {"prepare_only": prepare_only, "passed": prepare_only},
            "source": {"name": source.name, "sha256": original_hash, "pages": len(document)},
            "renderer": {
                "name": "pypdfium2",
                "version": importlib.metadata.version("pypdfium2"),
                "dpi": dpi,
            },
            "visual_policy": {"minimum_text_pt": min_text_pt, "minimum_image_dpi": min_image_dpi},
            "checks": [
                {
                    "name": "source_data",
                    "status": "untested",
                    "reason": "Original data/spec are not supplied; use a source-linked manifest audit for numerical checks.",
                },
                {
                    "name": "numerical_claims",
                    "status": "untested",
                    "reason": "Rendered PDF content does not establish the underlying quantities, uncertainty or claims.",
                },
                {
                    "name": "visual_interpretation",
                    "status": "untested",
                    "reason": "Text-size/image-resolution candidates do not establish chart meaning, complex clipping/layer visibility or scientific claims; no OCR is performed.",
                },
            ],
            "pages": [],
            "regions": [],
        }
        try:
            evidence = read_provenance(source)
            report["embedded_provenance"] = {
                "available": True,
                "authenticated": False,
                "schema_version": evidence["schema_version"],
                "spec_hash": evidence["spec_hash"],
            }
        except ValueError:
            report["embedded_provenance"] = {"available": False, "authenticated": False}
        try:
            for number in selected:
                with closing(document[number - 1]) as page:
                    width, height = page.get_size()
                    unit = units[number]
                    scale = dpi / 72 * unit
                    scaled = (width * scale, height * scale)
                    if (
                        not all(math.isfinite(v) and v > 0 for v in (width, height, *scaled))
                        or math.ceil(scaled[0]) * math.ceil(scaled[1]) > 30_000_000
                    ):
                        raise ValueError(
                            f"page {number} exceeds the 30-megapixel render limit; lower dpi"
                        )
                    with closing(page.render(scale=scale)) as bitmap:
                        image = bitmap.to_pil().copy()
                    try:
                        model = scan_page(page, unit=unit, size=image.size)
                        preview = destination / f"page-{number}.png"
                        image.save(preview)
                        text_path = destination / f"page-{number}.txt"
                        with closing(page.get_textpage()) as text_page:
                            count = text_page.count_chars()
                            text = (
                                text_page.get_text_range(count=min(count, 200000)) if count else ""
                            )
                        text_path.write_text(text, encoding="utf8")
                        report["pages"].append(
                            {
                                "page": number,
                                "points": [width * unit, height * unit],
                                "canvas_units": [width, height],
                                "unit_points": unit,
                                "visual": inspect_region(
                                    model,
                                    [0, 0, image.width, image.height],
                                    min_text_pt=min_text_pt,
                                    min_image_dpi=min_image_dpi,
                                ),
                                "preview": _artifact(preview, image),
                                "text": {
                                    "path": text_path.name,
                                    "sha256": _digest(text_path),
                                    "characters": count,
                                    "truncated": count > 200000,
                                    "status": "extracted" if text else "unavailable",
                                },
                            }
                        )
                        for region in (r for r in selections if r["page"] == number):
                            left, top, right, bottom = region["box"]
                            box = [
                                math.floor(left * image.width),
                                math.floor(top * image.height),
                                math.ceil(right * image.width),
                                math.ceil(bottom * image.height),
                            ]
                            with image.crop(box) as crop:
                                crop_path = destination / f"region-{region['id']}.png"
                                crop.save(crop_path)
                                report["regions"].append(
                                    {
                                        **region,
                                        "pixel_box": box,
                                        "image": _artifact(crop_path, crop),
                                        "visual": inspect_region(
                                            model,
                                            box,
                                            min_text_pt=min_text_pt,
                                            min_image_dpi=min_image_dpi,
                                        ),
                                    }
                                )
                    finally:
                        image.close()
        except pdfium.PdfiumError as problem:
            raise ValueError(
                f"PDF review preparation failed; partial files retained: {problem}"
            ) from problem
        if _digest(source) != original_hash:
            raise ValueError("source PDF changed during review preparation")
    title = html.escape(source.name)
    parts = [
        f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PDF review: {title}</title>',
        "<style>body{font:16px/1.6 system-ui;max-width:1000px;margin:auto;padding:24px;overflow-wrap:anywhere}img{max-width:100%;height:auto}figure{margin:24px 0;border:1px solid #bbb;padding:12px}a{color:#075e54}.notice{background:#fff1d8;padding:16px}</style>",
        f'<h1>PDF review: {title}</h1><p class="notice"><strong>Verification incomplete.</strong> This packet inspects extractable text size and embedded-image pixel density in pages/selected crops. Original data, numerical claims and general visual interpretation remain untested.</p>',
        '<p><a href="pdf-review.json">Machine-readable evidence</a>. Select an image to inspect its full resolution. Text extraction is not OCR; missing text is not proof of a missing label.</p><h2>Selected regions</h2>',
    ]
    for region in report["regions"]:
        name, filename = html.escape(region["id"]), region["image"]["path"]
        parts.append(
            f'<figure><figcaption>{name} — page {region["page"]}, manually selected</figcaption><a href="{filename}"><img src="{filename}" alt="Selected region {name}"></a></figure>'
        )
        parts.append(_visual_html(region["visual"]))
    if not report["regions"]:
        parts.append(
            "<p>No figure regions were selected. Review the pages below or supply a regions JSON file; page rendering does not locate figures automatically.</p>"
        )
    parts.append("<h2>Pages</h2>")
    for entry in report["pages"]:
        filename = entry["preview"]["path"]
        parts.append(
            f'<details><summary>Page {entry["page"]} — text {entry["text"]["status"]}</summary><a href="{entry["text"]["path"]}">Extracted text</a><a href="{filename}"><img loading="lazy" src="{filename}" alt="Page {entry["page"]}"></a></details>'
        )
        parts.append(_visual_html(entry["visual"]))
    parts.append("</html>")
    (destination / "pdf-review.html").write_text("\n".join(parts), encoding="utf8")
    (destination / "pdf-review.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf8"
    )
    return report
