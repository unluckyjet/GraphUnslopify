"""Offline, sourced technical checks of submitted figure bytes; never certification."""

from __future__ import annotations

import copy
import hashlib
import io
import json
import math
import re
import xml.etree.ElementTree as ET
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path

from PIL import Image
from pypdf import PdfReader
from pypdf.errors import PyPdfError

MAX_BYTES = 64 * 1024 * 1024
CHECKED = "2026-11-03"
PROFILES = {
    "plos-one-main": {
        "name": "PLOS One · accepted main-article figures",
        "stage": "After provisional editorial acceptance; supporting information excluded",
        "source_url": "https://journals.plos.org/plosone/s/figures",
        "checked_utc_date": CHECKED,
        "source_access": "Official page retrieved; technical figure requirements reviewed",
        "review_after_days": 180,
        "formats": ["tiff", "eps"],
        "width_in": [2.63, 7.5],
        "height_max_in": 8.75,
        "raster_dpi": [300, 600],
        "file_bytes_exclusive_max": 10_000_000,
        "manual_review": [
            "Check content bounds/white space: measured canvas or declared box is not an ink crop.",
            "Review all text at final size: Arial, Times or Symbol; 8-12 points.",
            "Review color mode, flattening, alpha channels and compression against the source.",
            "Match figure filename, manuscript citation and separate caption; review image integrity.",
            "Confirm every embedded image retains sufficient original resolution; no upsampling.",
        ],
    },
    "nature-final-graphs": {
        "name": "Nature · final print graphs and line art",
        "stage": "Production after acceptance in principle; photographs/Extended Data excluded",
        "source_url": "https://www.nature.com/nature/for-authors/final-submission",
        "checked_utc_date": CHECKED,
        "source_access": "Official indexed page text reviewed; direct page redirected to identity service",
        "review_after_days": 180,
        "profile_revision": "2026-11-03.2",
        "formats": ["pdf", "eps", "ps", "ai"],
        "conditional_formats": ["jpeg", "ppt", "pptx", "doc", "docx", "xls", "xlsx", "cdr"],
        "conditional_jpeg_dpi": [300, 600],
        "conditional_format_review": "Fallbacks apply when preferred formats cannot be supplied; JPEG needs 300-600 DPI, CorelDraw at most version 8. Confirm conditions with the publisher.",
        "pdf_extractable_text_min_pt": 5,
        "recommended_width_mm": [89, 183],
        "manual_review": [
            "Confirm current production instructions with the publisher; this is a dated snapshot.",
            "Standard 89/183 mm widths are guidance, not universal exact-width requirements.",
            "Review editable vector text/lines; do not rasterize or outline graph lettering.",
            "Minimum measured PDF glyph size does not establish raster/outlined text, font roles or complete legibility.",
            "Review sans-serif lettering, 5-7 point ordinary text and 8 point bold panel labels.",
            "Review 0.25-1 point final strokes, layout, embedded-image resolution and color.",
        ],
    },
}


def journal_profiles() -> list[dict]:
    """Return detached, dated policy snapshots; no network lookup or mutable catalog access."""
    return [{"id": key, **copy.deepcopy(value)} for key, value in PROFILES.items()]


def _positive(value):
    if isinstance(value, bool):
        raise TypeError("Physical measurements cannot be booleans")
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError("Physical measurements must be finite and positive")
    return value


def _length(value):
    match = re.fullmatch(r"\s*([+\-0-9.eE]+)\s*(pt|in|cm|mm)\s*", value)
    if match is None:
        raise ValueError("SVG dimensions need absolute pt/in/cm/mm units")
    return _positive(match[1]) * {"pt": 1 / 72, "in": 1, "cm": 1 / 2.54, "mm": 1 / 25.4}[match[2]]


def _measure(raw: bytes, format_: str) -> dict:
    if format_ in {"png", "tiff", "jpeg"}:
        with Image.open(io.BytesIO(raw)) as image:
            if image.format != {"png": "PNG", "tiff": "TIFF", "jpeg": "JPEG"}[format_]:
                raise ValueError("File extension and actual image format disagree")
            if getattr(image, "n_frames", 1) != 1:
                raise ValueError("Only single-image figure files are supported")
            if image.width * image.height > 50_000_000:
                raise ValueError("Figure inspection is limited to 50 million pixels")
            # Decode pixels too: a valid-looking header is not a readable submitted image.
            image.load()
            dpi = image.info.get("dpi")
            if format_ == "tiff":
                tags = image.tag_v2
                if tags.get(296) not in {2, 3} or 282 not in tags or 283 not in tags:
                    raise ValueError("TIFF needs explicit horizontal/vertical resolution and units")
                multiplier = 2.54 if tags[296] == 3 else 1
                dpi = (_positive(tags[282]) * multiplier, _positive(tags[283]) * multiplier)
            if dpi is None or len(dpi) != 2:
                raise ValueError("Image has no physical horizontal/vertical DPI")
            x, y = _positive(dpi[0]), _positive(dpi[1])
            return {
                "basis": "decoded raster canvas and recorded physical resolution",
                "width_in": image.width / x,
                "height_in": image.height / y,
                "pixels": [image.width, image.height],
                "dpi": [x, y],
                "pages": 1,
            }
    if format_ == "pdf":
        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted or len(reader.pages) != 1:
            raise ValueError("Only unencrypted single-page figure PDFs are supported")
        page = reader.pages[0]
        unit = _positive(page.get("/UserUnit", 1))
        raw_rotation = float(page.get("/Rotate", 0))
        if not math.isfinite(raw_rotation) or raw_rotation != int(raw_rotation):
            raise ValueError("PDF rotation must be an integer number of degrees")
        rotation = int(raw_rotation) % 360
        if rotation not in {0, 90, 180, 270}:
            raise ValueError("PDF rotation is not an orthogonal page rotation")
        # The visible page is the intersection, not a CropBox extending outside its media.
        box, media = page.cropbox, page.mediabox
        width = _positive((min(box.right, media.right) - max(box.left, media.left)) * unit / 72)
        height = _positive((min(box.top, media.top) - max(box.bottom, media.bottom)) * unit / 72)
        if rotation in {90, 270}:
            width, height = height, width
        return {
            "basis": "PDF visible page box, UserUnit and rotation; not rendered ink",
            "width_in": width,
            "height_in": height,
            "pages": 1,
            "dpi": None,
            "pdf_user_unit": unit,
        }
    if format_ == "svg":
        root = ET.fromstring(raw)
        if root.tag not in {"svg", "{http://www.w3.org/2000/svg}svg"}:
            raise ValueError("SVG root element is missing")
        return {
            "basis": "SVG declared absolute viewport; not rendered ink",
            "width_in": _length(root.get("width", "")),
            "height_in": _length(root.get("height", "")),
            "pages": 1,
            "dpi": None,
        }
    if format_ == "eps":
        lines = []
        for line in raw[:65536].decode("latin1").splitlines():
            if line.startswith("%%EndComments") or (line.strip() and not line.startswith("%")):
                break
            lines.append(line)
        header = "\n".join(lines)
        if not re.match(r"%!PS-Adobe-[^\r\n]* EPSF-", header):
            raise ValueError("File is not an EPS with an Adobe DSC header")
        boxes = re.findall(r"^%%(HiResBoundingBox|BoundingBox):\s*([^\r\n]+)", header, re.MULTILINE)
        numeric = {}
        for kind, box in boxes:
            try:
                values = [float(v) for v in box.split()]
            except ValueError:
                continue
            if len(values) == 4 and all(math.isfinite(v) for v in values):
                numeric[kind] = values
        if not numeric:
            raise ValueError("EPS has no numeric bounding box in its header")
        left, bottom, right, top = numeric.get("HiResBoundingBox", numeric.get("BoundingBox"))
        return {
            "basis": "EPS declared DSC box only; PostScript is never executed",
            "width_in": _positive(right - left) / 72,
            "height_in": _positive(top - bottom) / 72,
            "pages": None,
            "dpi": None,
        }
    raise ValueError("This file format has no supported local physical inspector")


def _pdf_text(raw: bytes, *, unit: float, minimum: float) -> dict:
    """Measure a bounded subset of visible extractable glyphs, without rendering."""
    try:
        import pypdfium2 as pdfium
    except ImportError as problem:
        raise ValueError(
            "Install the optional [pdf] extra for supported PDF text metrics"
        ) from problem
    from .pdf_visual import inspect_region, scan_page

    try:
        with closing(pdfium.PdfDocument(raw)) as document:
            if len(document) != 1:
                raise ValueError("PDF text inspection requires one readable page")
            with closing(document[0]) as page:
                size = tuple(math.ceil(_positive(value) * 2) for value in page.get_size())
                if max(size) > 32768 or math.prod(size) > 50_000_000:
                    raise ValueError("PDF text coordinates exceed the bounded inspection viewport")
                model = scan_page(page, unit=unit, size=size)
                result = inspect_region(model, [0, 0, *size], min_text_pt=minimum)
    except (pdfium.PdfiumError, IndexError) as problem:
        raise ValueError("PDF text could not be inspected") from problem
    check = next(check for check in result["checks"] if check["name"] == "text_size")
    return {**check, "coverage": result["coverage"], "limits": result["limits"]}


def check_journal(
    path: str | Path,
    *,
    profile: str,
    target_width_mm: float | None = None,
    width_tolerance_mm: float = 0.5,
    as_of: date | None = None,
) -> dict:
    """Check a frozen file snapshot. Passed technical checks never certify submission readiness."""
    if profile not in PROFILES:
        raise ValueError("Unknown journal profile; list journal-profiles for supported IDs")
    if target_width_mm is not None:
        target_width_mm = _positive(target_width_mm)
    width_tolerance_mm = _positive(width_tolerance_mm)
    today = datetime.now(timezone.utc).date() if as_of is None else as_of
    if type(today) is not date:
        raise ValueError("as_of must be a calendar date")
    source = Path(path).expanduser().resolve()
    with source.open("rb") as f:
        raw = f.read(MAX_BYTES + 1)
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("Choose a nonempty figure of at most 64 MiB")
    rules = copy.deepcopy(PROFILES[profile])
    format_ = {"tif": "tiff", "jpg": "jpeg"}.get(
        source.suffix[1:].lower(), source.suffix[1:].lower()
    )
    raster_range = rules.get("raster_dpi") or (
        rules.get("conditional_jpeg_dpi") if format_ == "jpeg" else None
    )
    checks = []

    def add(code, status, actual, requirement, message):
        checks.append(
            {
                "code": code,
                "status": status,
                "actual": actual,
                "requirement": requirement,
                "message": message,
            }
        )

    age = (today - date.fromisoformat(rules["checked_utc_date"])).days
    fresh = 0 <= age <= rules["review_after_days"]
    add(
        "profile_freshness",
        "passed" if fresh else "unavailable",
        age,
        {"maximum_age_days": rules["review_after_days"]},
        "Dated snapshot; confirm current publisher instructions before submission.",
    )
    add(
        "file_format",
        "passed"
        if format_ in rules["formats"]
        else "unavailable"
        if format_ in rules.get("conditional_formats", [])
        else "failed",
        format_,
        {"preferred": rules["formats"], "conditional": rules["conditional_formats"]}
        if "conditional_formats" in rules
        else rules["formats"],
        rules["conditional_format_review"]
        if format_ in rules.get("conditional_formats", [])
        else "Formats apply only to the selected journal/stage/artwork scope.",
    )
    if "file_bytes_exclusive_max" in rules:
        bound = rules["file_bytes_exclusive_max"]
        add(
            "file_size",
            "passed" if len(raw) < bound else "failed",
            len(raw),
            {"less_than_bytes": bound},
            "Uses the strict <10 MB summary requirement.",
        )
    try:
        measurement = _measure(raw, format_)
    except (
        OSError,
        ValueError,
        TypeError,
        OverflowError,
        ZeroDivisionError,
        ET.ParseError,
        PyPdfError,
        Image.DecompressionBombError,
    ) as problem:
        measurement = None
        add(
            "physical_measurement",
            "unavailable",
            None,
            "readable supported figure bytes",
            str(problem),
        )
    if measurement is not None:
        add(
            "physical_measurement",
            "passed",
            measurement,
            "readable supported figure bytes",
            "Physical metadata is measured from this exact snapshot, not nominal figsize.",
        )
        if "width_in" in rules:
            lo, hi = rules["width_in"]
            width = measurement["width_in"]
            add(
                "physical_width",
                "passed" if lo <= width <= hi else "failed",
                width,
                {"minimum_in": lo, "maximum_in": hi},
                "Review white space/content bounds separately.",
            )
        if "height_max_in" in rules:
            height = measurement["height_in"]
            add(
                "physical_height",
                "passed" if height <= rules["height_max_in"] else "failed",
                height,
                {"maximum_in": rules["height_max_in"]},
                "Uses actual recorded vertical dimensions.",
            )
        if raster_range is not None:
            dpi = measurement["dpi"]
            lo, hi = raster_range
            status = (
                "unavailable"
                if dpi is None
                else "passed"
                if all(lo <= d <= hi for d in dpi)
                else "failed"
            )
            add(
                "raster_resolution",
                status,
                dpi,
                {"minimum_dpi": lo, "maximum_dpi": hi},
                "Both axes required; vector metadata cannot establish embedded-image resolution.",
            )
        if target_width_mm is not None:
            width = measurement["width_in"] * 25.4
            add(
                "requested_width",
                "passed" if abs(width - target_width_mm) <= width_tolerance_mm else "failed",
                width,
                {"target_mm": target_width_mm, "tolerance_mm": width_tolerance_mm},
                "Explicit author target; this is not an inferred publisher requirement.",
            )
    else:
        for code, needed in (
            ("physical_width", "width_in" in rules),
            ("physical_height", "height_max_in" in rules),
            ("raster_resolution", raster_range is not None),
            ("requested_width", target_width_mm is not None),
        ):
            if needed:
                add(
                    code,
                    "unavailable",
                    None,
                    "readable physical measurements",
                    "Required measurement could not be established from these bytes.",
                )
    if format_ == "pdf" and "pdf_extractable_text_min_pt" in rules:
        minimum = rules["pdf_extractable_text_min_pt"]
        try:
            if measurement is None:
                raise ValueError("Physical PDF measurement is unavailable")
            text = _pdf_text(raw, unit=measurement["pdf_user_unit"], minimum=minimum)
            text_status = (
                "failed"
                if text["characters_below_threshold"]
                else "passed"
                if text["status"] == "checked" and text["characters_measured"]
                else "unavailable"
            )
            add(
                "pdf_text_minimum",
                text_status,
                text,
                {"minimum_extractable_glyph_pt": minimum},
                "Supported non-invisible extractable glyphs only; font roles, outlined/raster text and full legibility remain manual.",
            )
        except (OSError, ValueError, TypeError, OverflowError) as problem:
            add(
                "pdf_text_minimum",
                "unavailable",
                None,
                {"minimum_extractable_glyph_pt": minimum},
                str(problem),
            )
    digest = hashlib.sha256(raw).hexdigest()
    try:
        with source.open("rb") as f:
            current = hashlib.sha256(f.read(MAX_BYTES + 1)).hexdigest() == digest
        add(
            "source_current",
            "passed" if current else "failed",
            current,
            "source bytes unchanged during inspection",
            "The report retains the inspected snapshot hash.",
        )
    except OSError as problem:
        add("source_current", "unavailable", None, "readable unchanged source", str(problem))
    status = (
        "failed"
        if any(c["status"] == "failed" for c in checks)
        else "incomplete"
        if any(c["status"] == "unavailable" for c in checks)
        else "passed"
    )
    return {
        "kind": "graphunslopify.journal-check",
        "schema_version": 1,
        "as_of": today.isoformat(),
        "profile": {"id": profile, **rules},
        "profile_sha256": hashlib.sha256(
            json.dumps(rules, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest(),
        "source": {"path": str(source), "sha256": digest, "bytes": len(raw), "format": format_},
        "scope": "Sourced technical snapshot checks; not complete journal or scientific compliance",
        "status": status,
        "exit_code": 0 if status == "passed" else 2,
        "checks": checks,
        "manual_review": rules["manual_review"],
        "submission_ready": None,
        "scientific_verification": "not_performed",
    }
