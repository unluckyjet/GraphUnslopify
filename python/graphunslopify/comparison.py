"""Verified saved-artifact previews and explanations for source-linked audits."""

from __future__ import annotations

import hashlib
import io
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path, PureWindowsPath
from typing import Any

from PIL import Image, ImageChops

from .audit import AuditError, compare_audits

MAX_BYTES = 20 * 1024 * 1024
MAX_PIXELS = 30_000_000
PDF_DPI = 144


def artifact_roots(report: dict, source: Path, explicit=None, fallback=None) -> list[Path]:
    """An override is exclusive; copied JSON can use its recorded local locator."""
    if explicit is not None:
        return [Path(explicit).expanduser().resolve()]
    values = [source.parent]
    if isinstance(report.get("artifact_root"), str):
        values.append(Path(report["artifact_root"]))
    if fallback is not None:
        values.append(Path(fallback))
    return list(dict.fromkeys(p.expanduser().resolve() for p in values))


def _verified_bytes(item: dict, roots: list[Path]) -> bytes:
    name = item["path"]
    path = Path(name)
    if path.is_absolute() or PureWindowsPath(name).drive or "\\" in name or ".." in path.parts:
        raise ValueError("Artifact path escapes its root; use a saved audit-relative path.")
    problems = []
    for root in roots:
        candidate = (root / path).resolve()
        if not candidate.is_relative_to(root.resolve()):
            problems.append("Artifact symlink escapes its root.")
            continue
        if not candidate.is_file():
            continue
        if candidate.stat().st_size > MAX_BYTES:
            problems.append("Artifact exceeds the 20 MiB preview limit.")
            continue
        data = candidate.read_bytes()
        if len(data) != item["bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
            problems.append(
                "Saved artifact bytes changed since the audit; restore the matching file."
            )
            continue
        return data
    raise ValueError(
        problems[0]
        if problems
        else "Saved artifact is missing; restore its run directory or set the artifact root."
    )


def _store(folder: Path, name: str, data: bytes, mime: str) -> dict:
    if len(data) > MAX_BYTES:
        raise ValueError("Encoded preview exceeds the 20 MiB limit.")
    path = folder / "images" / name
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(data)
    return {
        "path": path.relative_to(folder).as_posix(),
        "mime": mime,
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }


def _png_bytes(image: Image.Image) -> bytes:
    stream = io.BytesIO()
    # Pillow can inherit ICC/ancillary metadata even without explicit pnginfo.
    # Export only the decoded channels used by the comparison measurements.
    clean = Image.frombytes(image.mode, image.size, image.tobytes())
    clean.save(stream, format="PNG")
    return stream.getvalue()


def _size(width: int, height: int) -> None:
    if width <= 0 or height <= 0 or width * height > MAX_PIXELS:
        raise ValueError("Preview exceeds the 30 million pixel limit.")


def _preview(item: dict | None, roots: list[Path], folder: Path, name: str) -> tuple[dict, Any]:
    if item is None:
        return {
            "status": "absent",
            "reason": "No supported static export exists on this side; export PNG, SVG or PDF.",
        }, None
    record = {key: item[key] for key in ("path", "format", "sha256", "bytes")}
    try:
        data = _verified_bytes(item, roots)
        if item["format"] == "svg":
            svg_text = data.decode("utf-8-sig")
            if "\x00" in svg_text:
                raise ValueError("SVG previews require UTF-8 without NUL bytes.")
            if re.search(r"<!ENTITY\s", svg_text, re.IGNORECASE):
                raise ValueError("SVG entity declarations are not supported in previews.")
            root = ET.fromstring(svg_text)
            if root.tag != "{http://www.w3.org/2000/svg}svg":
                raise ValueError("Saved SVG has no SVG root element.")
            record.update(
                status="available",
                dimensions=None,
                renderer="browser_svg_image",
                preview=_store(folder, name + ".svg", data, "image/svg+xml"),
            )
            return record, None
        if item["format"] == "pdf":
            try:
                import pypdfium2 as pdfium
            except ImportError as problem:
                raise ValueError(
                    "Install graphunslopify[pdf] for PDF previews, or export PNG/SVG."
                ) from problem
            with pdfium.PdfDocument(data) as document:
                if len(document) != 1:
                    raise ValueError(
                        "A figure PDF must have one page; use audit-pdf for manuscripts."
                    )
                page = document[0]
                try:
                    import math

                    width, height = page.get_size()
                    _size(math.ceil(width * PDF_DPI / 72), math.ceil(height * PDF_DPI / 72))
                    bitmap = page.render(scale=PDF_DPI / 72)
                    try:
                        image = bitmap.to_pil().convert("RGBA")
                    finally:
                        bitmap.close()
                finally:
                    page.close()
            record.update(renderer="pypdfium2", raster_dpi=PDF_DPI)
        else:
            with Image.open(io.BytesIO(data)) as source:
                if source.format != "PNG" or getattr(source, "n_frames", 1) != 1:
                    raise ValueError("Expected one static PNG image.")
                _size(*source.size)
                image = source.convert("RGBA")
            expected = item.get("pixels_sha256")
            actual = hashlib.sha256(str(image.size).encode() + image.tobytes()).hexdigest()
            if expected is not None and expected != actual:
                raise ValueError("Decoded PNG pixels disagree with the audit fingerprint.")
            record.update(renderer="pillow")
        record.update(
            status="available",
            dimensions=list(image.size),
            preview=_store(folder, name + ".png", _png_bytes(image), "image/png"),
        )
        return record, image
    except Exception as problem:  # noqa: BLE001 -- unavailable evidence must not erase other comparisons
        record.update(status="unavailable", reason=f"{type(problem).__name__}: {problem}")
        return record, None


def _select(before: dict | None, after: dict | None) -> tuple[dict | None, dict | None]:
    a, b = (before or {}).get("outputs", []), (after or {}).get("outputs", [])
    # Match a format first, so a renamed stem still compares the same figure ID.
    shared = next(
        (
            fmt
            for fmt in ("png", "svg", "pdf")
            if any(x["format"] == fmt for x in a) and any(x["format"] == fmt for x in b)
        ),
        None,
    )

    def pick(items):
        for fmt in [shared] if shared else ["png", "svg", "pdf"]:
            choices = sorted((x for x in items if x["format"] == fmt), key=lambda x: x["path"])
            if choices:
                return choices[0]
        return None

    return pick(a), pick(b)


def _maximum_mask(image: Image.Image) -> Image.Image:
    bands = image.split()
    mask = bands[0]
    for band in bands[1:]:
        mask = ImageChops.lighter(mask, band)
    return mask


def _metrics(before: Image.Image, after: Image.Image) -> tuple[dict, Image.Image]:
    raw = _maximum_mask(ImageChops.difference(before, after)).histogram()

    def white(image):
        return Image.alpha_composite(Image.new("RGBA", image.size, "white"), image).convert("RGB")

    difference = ImageChops.difference(white(before), white(after))
    maximum = _maximum_mask(difference)
    visible = maximum.histogram()
    pixels = before.width * before.height
    histogram = difference.histogram()
    mean = sum((i % 256) * count for i, count in enumerate(histogram)) / (pixels * 3)
    metrics = {
        "total_pixels": pixels,
        "rgba_pixels_changed": sum(raw[1:]),
        "visible_pixels_changed": sum(visible[1:]),
        "visible_changed_fraction": sum(visible[1:]) / pixels,
        "max_rgb_channel_difference": max(i for i, count in enumerate(visible) if count),
        "mean_absolute_rgb_channel_difference": mean,
        "background": "white",
        "channel_range": [0, 255],
        "resampled": False,
    }
    # A binary magenta map reveals even one-channel changes; magnitude stays in metrics.
    mask = maximum.point(lambda value: 255 if value else 0)
    heat = Image.new("RGB", before.size, "#f5f5f5")
    heat.paste(Image.new("RGB", before.size, "#c4007a"), mask=mask)
    return metrics, heat


def _leaf_changes(before: Any, after: Any, path="") -> list[dict]:
    if isinstance(before, dict) and isinstance(after, dict):
        result = []
        for key in sorted(before.keys() | after.keys()):
            address = f"{path}.{key}" if path else key
            if key not in before or key not in after:
                result.append(
                    {
                        "path": address,
                        "before_present": key in before,
                        "after_present": key in after,
                        "before": before.get(key),
                        "after": after.get(key),
                    }
                )
            else:
                result.extend(_leaf_changes(before[key], after[key], address))
        return result
    return [] if before == after else [{"path": path, "before": before, "after": after}]


def _explain(change: dict | None, before: dict | None, after: dict | None) -> list[dict]:
    if not before or not after:
        return [
            {
                "field": "membership",
                "message": "Figure added; review the new evidence."
                if after
                else "Figure removed; check manuscript references and coverage.",
            }
        ]
    a, b = before.get("report") or {}, after.get("report") or {}
    messages = {
        "status": "Validation status changed; inspect failed or incomplete checks before accepting the figure.",
        "data_bytes": "Source data bytes changed; recheck inputs, categories and cohorts. This alone does not identify which values changed.",
        "numeric_representation": "Parsed numeric-column representation changed, including possible types, columns or row order; review affected estimates and comparisons.",
        "spec": "Figure settings changed; review the listed settings for changed meaning, scales or presentation.",
        "source": "Source code/spec bytes changed; this does not by itself establish a scientific change.",
        "claims": "Claim evidence changed; review the before/after verdicts and values before repeating conclusions.",
        "significance": "Statistical comparison evidence changed; review design, effect estimates and correction assumptions.",
        "description": "Figure description changed; check that captions still describe the displayed evidence.",
        "findings": "Verification findings changed; inspect their severity, problem and recommended action.",
        "errors": "Execution/audit errors changed; a successfully produced image can still fail validation.",
        "warnings": "Audit warnings changed; check compatibility and evidence limitations.",
        "environment": "Recorded creation context changed; dependency, font or execution differences may affect results. This is not proof of the cause of a visual change.",
        "published_artifacts": "Published artifact fingerprints/checks changed; confirm the manuscript uses the intended validated exports.",
    }
    values = {
        "status": (before.get("status"), after.get("status")),
        "data_bytes": (before.get("data", {}).get("sha256"), after.get("data", {}).get("sha256")),
        "numeric_representation": (
            before.get("data", {}).get("numeric_sha256"),
            after.get("data", {}).get("numeric_sha256"),
        ),
        "spec": (before.get("semantic_spec"), after.get("semantic_spec")),
        "source": (before.get("source_sha256"), after.get("source_sha256")),
        "published_artifacts": (before.get("artifacts"), after.get("artifacts")),
    }
    entries = []
    for field, changed in (change or {}).get("fields", {}).items():
        if not changed:
            continue
        left, right = values.get(
            field, (a.get(field, before.get(field)), b.get(field, after.get(field)))
        )
        if field == "description":
            left, right = a.get("alt_text"), b.get("alt_text")
        entries.append(
            {
                "field": field,
                "message": messages[field],
                "before": left,
                "after": right,
                "details": _leaf_changes(left, right) if field in {"spec", "environment"} else [],
            }
        )
    return entries


def write_comparison(
    before: dict,
    after: dict,
    *,
    output: Path,
    before_roots: list[Path],
    after_roots: list[Path],
    audit_policy: bool = False,
) -> dict:
    """No source execution/data access; output must be a fresh evidence directory."""
    comparison = compare_audits(before, after)
    output = Path(output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise AuditError("choose an empty comparison directory; previous evidence is preserved")
    changes = {x["id"]: x for x in comparison["figures"]}
    old, new = ({x["id"]: x for x in report["figures"]} for report in (before, after))
    figures = []
    for index, name in enumerate(sorted(old.keys() | new.keys())):
        left, right = old.get(name), new.get(name)
        x, y = _select(left, right)
        a, image_a = _preview(x, before_roots, output, f"{index}-before")
        b, image_b = _preview(y, after_roots, output, f"{index}-after")
        record = {
            "id": name,
            "kind": changes.get(name, {}).get("kind", "unchanged"),
            "before_status": (left or {}).get("status"),
            "after_status": (right or {}).get("status"),
            "before": a,
            "after": b,
            "metrics": None,
            "difference": None,
            "explanations": _explain(changes.get(name), left, right),
            "output_changes": changes.get(name, {}).get("outputs", []),
            "outputs_before": (left or {}).get("outputs", []),
            "outputs_after": (right or {}).get("outputs", []),
        }
        if not left or not right:
            mode = "added" if right else "removed"
        elif a["status"] != "available" or b["status"] != "available":
            mode = "unavailable"
        elif image_a is None or image_b is None or a["format"] != b["format"]:
            mode = "preview_only"
        elif image_a.size != image_b.size:
            mode = "dimensions_changed"
        else:
            record["metrics"], heat = _metrics(image_a, image_b)
            record["difference"] = _store(
                output, f"{index}-difference.png", _png_bytes(heat), "image/png"
            )
            mode = (
                "pixels_changed" if record["metrics"]["rgba_pixels_changed"] else "pixels_unchanged"
            )
        record["visual_status"] = mode
        figures.append(record)
    report = {
        "schema_version": 1,
        "scope": "saved audit evidence and representative static exports",
        "changed": comparison["changed"],
        "before_status": before["status"],
        "after_status": after["status"],
        "before_policy": before["policy"],
        "after_policy": after["policy"],
        "before_exit_code": before["exit_code"],
        "after_exit_code": after["exit_code"],
        "preview_status": "partial"
        if any(
            x[side]["status"] != "available"
            for x in figures
            for side in ("before", "after")
            if (side == "before" and x["kind"] != "added")
            or (side == "after" and x["kind"] != "removed")
        )
        else "complete",
        "pdf_raster_dpi": PDF_DPI,
        "figures": figures,
        "limitations": [
            "Observed changes do not establish their cause or scientific validity.",
            "One representative static export is shown per figure; other formats retain separate byte evidence.",
            "PNG metrics use decoded RGBA; visible RGB differences use a white background. No resampling occurs.",
            "Channel comparisons do not apply source ICC profiles or establish perceptual/color-managed equivalence.",
            "SVG uses passive browser image preview; server-side pixel metrics are unknown.",
            "PDF previews rasterize one-page figures at the recorded DPI; this is not a vector/font/accessibility equivalence test.",
        ],
    }
    if audit_policy and report["preview_status"] == "partial":
        # The automatic packet participates in that audit's acceptance policy.
        # Saved-report comparisons instead preserve the already-recorded exit.
        report["after_exit_code"] = 2
    report["exit_code"] = (
        2
        if report["preview_status"] == "partial"
        or after["exit_code"] != 0
        or after["status"] != "passed"
        else 0
    )
    from importlib.resources import files

    from jsonschema import Draft202012Validator

    schema = json.loads(
        files("graphunslopify").joinpath("schemas/comparison.schema.json").read_text()
    )
    Draft202012Validator(schema).validate(report)
    (output / "comparison.report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf8"
    )
    from .comparison_html import render_html

    (output / "index.html").write_text(render_html(report, output), encoding="utf8")
    return report


def compare_reports(
    before: str | Path, after: str | Path, *, output: str | Path, before_root=None, after_root=None
) -> dict:
    left, right = Path(before).expanduser().resolve(), Path(after).expanduser().resolve()
    a, b = (json.loads(path.read_text(encoding="utf8")) for path in (left, right))
    return write_comparison(
        a,
        b,
        output=Path(output),
        before_roots=artifact_roots(a, left, before_root),
        after_roots=artifact_roots(b, right, after_root),
    )
