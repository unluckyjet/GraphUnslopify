"""Recover the evidence embedded in a GraphUnslopify PNG, SVG, PDF or HTML."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from PIL import Image


class _HtmlEvidence(HTMLParser):
    def __init__(self):
        super().__init__()
        self.reading = False
        self.chunks: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.reading = dict(attrs).get("id") == "graphunslopify-provenance"

    def handle_endtag(self, tag):
        if tag == "script":
            self.reading = False

    def handle_data(self, data):
        if self.reading:
            self.chunks.append(data)


class ProvenanceError(ValueError):
    """The file has missing, malformed, or unsupported embedded evidence."""


def _legacy(spec_json: str | None, stamp: str, description: str = "") -> dict[str, Any]:
    if not stamp.startswith("GraphUnslopify") or not spec_json:
        raise ProvenanceError("No GraphUnslopify provenance found")
    try:
        spec = json.loads(spec_json)
    except json.JSONDecodeError as problem:
        raise ProvenanceError("Invalid legacy figure specification") from problem
    if not isinstance(spec, dict) or "kind" not in spec:
        raise ProvenanceError("Invalid legacy figure specification")
    spec_hash = re.search(r"spec:([a-f0-9]{16})", stamp)
    data_hash = re.search(r"data:([a-f0-9]{16})", stamp)
    return {
        "schema_version": 0,
        "tool": stamp,
        "spec": spec,
        "alt_text": description,
        "spec_hash": spec_hash[1] if spec_hash else None,
        "data_sha256_prefix": data_hash[1] if data_hash else None,
        "script_sha256": None,
    }


def _envelope(payload: str) -> dict[str, Any]:
    if not isinstance(payload, str):
        raise ProvenanceError("Embedded provenance must be text")
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as problem:
        raise ProvenanceError("Invalid embedded provenance JSON") from problem
    if (
        not isinstance(value, dict)
        or type(value.get("schema_version")) is not int
        or value["schema_version"] != 1
    ):
        raise ProvenanceError("Unsupported provenance schema version")
    if (
        not isinstance(value.get("spec"), dict)
        or not isinstance(value["spec"].get("kind"), str)
        or not isinstance(value.get("alt_text"), str)
        or not isinstance(value.get("tool"), str)
        or not isinstance(value.get("spec_hash"), str)
        or not isinstance(value.get("data_sha256_prefix"), str)
    ):
        raise ProvenanceError("Incomplete embedded provenance")
    return value


def read_provenance(path: str | Path) -> dict[str, Any]:
    """Read embedded evidence; this does not authenticate it or recheck its data.

    Schema 1 carries the same payload in all supported formats. Legacy generated
    PNG/PDF files can recover their spec with schema 0 and explicit missing data.
    A legacy SVG without a spec cannot be recovered. No programs are executed.
    """
    path = Path(path)
    extension = path.suffix.lower()
    if extension == ".png":
        with Image.open(path) as image:
            info = image.info
            payload = info.get("GraphUnslopify")
            if payload is None:
                return _legacy(
                    info.get("Description"), info.get("Software", ""), info.get("Comment", "")
                )
    elif extension == ".svg":
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as problem:
            raise ProvenanceError("Invalid SVG document") from problem
        source = root.find(".//{http://purl.org/dc/elements/1.1/}source")
        payload = source.text if source is not None else None
    elif extension == ".pdf":
        from pypdf import PdfReader
        from pypdf.errors import PyPdfError

        try:
            info = PdfReader(path).metadata or {}
        except PyPdfError as problem:
            raise ProvenanceError(f"Invalid or unreadable PDF: {problem}") from problem
        payload = info.get("/Keywords")
        if not payload or not str(payload).lstrip().startswith("{"):
            return _legacy(info.get("/Subject"), info.get("/Creator", ""))
    elif extension in (".html", ".htm"):
        parsed = _HtmlEvidence()
        parsed.feed(path.read_text(encoding="utf8"))
        payload = "".join(parsed.chunks)
    else:
        raise ProvenanceError("Supported provenance formats: PNG, SVG, PDF, HTML")
    if not payload:
        raise ProvenanceError("No GraphUnslopify provenance found")
    return _envelope(payload)
