"""Pinned external reference inputs; no product imports or computed answer keys."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import urllib.request
from decimal import Decimal, InvalidOperation
from pathlib import Path

MAX_SOURCE_BYTES = 512 * 1024
NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _one(header, pattern, name):
    matches = re.findall(pattern, header, re.MULTILINE)
    if len(matches) != 1:
        raise ValueError(f"expected exactly one {name} in the reference header")
    return matches[0]


def _finite(token):
    try:
        value = Decimal(token)
    except InvalidOperation as problem:
        raise ValueError(
            f"invalid decimal observation/reference: {token!r}"
        ) from problem
    if not re.fullmatch(NUMBER, token) or not value.is_finite():
        raise ValueError(
            "observations and certified values must be finite numeric tokens"
        )
    return value


def parse_source(data: bytes, expected: dict) -> dict:
    """Verify transport, header answers and row count before producing any view."""
    if len(data) != expected["bytes"] or digest(data) != expected["sha256"]:
        raise ValueError(
            f"source bytes/hash differ for {expected['id']}; preserve and investigate"
        )
    try:
        lines = data.decode("ascii").splitlines()
    except UnicodeDecodeError as problem:
        raise ValueError("StRD reference input must be ASCII") from problem
    if len(lines) < 61:
        raise ValueError(
            "StRD input requires a 60-line header followed by observations"
        )
    header = "\n".join(lines[:60])
    name = _one(header, r"^Dataset Name:\s*([A-Za-z0-9]+)", "dataset name")
    if name != expected["id"]:
        raise ValueError("dataset identity differs from the frozen manifest")
    count = int(
        _one(header, r"^Number of Observations:\s*(\d+)\s*$", "observation count")
    )
    if count <= 0 or count != expected["observations"]:
        raise ValueError("declared observation count differs from the frozen manifest")
    if len(re.findall(r"^Data:\s*Y\s*$", header, re.MULTILINE)) != 1:
        raise ValueError("expected the univariate Data: Y declaration in the header")
    certified = {}
    for key, label in [
        ("mean", r"Sample Mean"),
        ("sample_sd", r"Sample Standard Deviation \(denom\. = n-1\)"),
        ("lag1_autocorrelation", r"Sample Autocorrelation Coefficient \(lag 1\)"),
    ]:
        token, exact = _one(
            header, rf"^{label}[^:\n]*:\s*({NUMBER})\s*(\(exact\))?\s*$", key
        )
        number = _finite(token)
        if (
            key == "sample_sd"
            and number < 0
            or key == "lag1_autocorrelation"
            and abs(number) > 1
        ):
            raise ValueError(f"invalid certified {key}")
        certified[key] = {"value": token, "exact": bool(exact)}
    if certified != expected["certified"]:
        raise ValueError(
            "certified values differ from the frozen publisher transcription"
        )
    values = [line.strip() for line in lines[60:] if line.strip()]
    if len(values) != count:
        raise ValueError("actual observation count differs from the reference header")
    for token in values:
        _finite(token)
    return {"id": name, "observations": count, "certified": certified, "values": values}


def read_manifest(path: Path) -> dict:
    manifest = json.loads(path.read_text(encoding="utf8"))
    if manifest.get("schema_version") != 1 or not manifest.get("sources"):
        raise ValueError("invalid reference corpus manifest")
    identifiers = [row["id"] for row in manifest["sources"]]
    if identifiers != manifest["dataset_order"] or len(
        {s.casefold() for s in identifiers}
    ) != len(identifiers):
        raise ValueError("corpus membership/order must match the frozen selection")
    for row in manifest["sources"]:
        if (
            not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", row["id"])
            or row["file"] != row["id"] + ".dat"
        ):
            raise ValueError("unsafe or inconsistent reference filename")
        if (
            not re.fullmatch(r"[0-9a-f]{64}", row["sha256"])
            or not 0 < row["bytes"] <= MAX_SOURCE_BYTES
        ):
            raise ValueError("invalid source size/hash")
        if row["difficulty"] not in {"lower", "average", "higher"} or row[
            "nist_source_class"
        ] not in {"observed", "generated"}:
            raise ValueError("invalid reference stratum")
    return manifest


def _source(row, source_dir, *, download, user_agent):
    path = source_dir / row["file"]
    if path.is_symlink():
        raise ValueError("source cache entries must be regular files, not symlinks")
    if path.exists():
        if not path.is_file():
            raise ValueError("source cache entries must be regular files")
        with path.open("rb") as handle:
            data = handle.read(MAX_SOURCE_BYTES + 1)
        parse_source(data, row)
        return data
    if not download:
        raise ValueError(
            f"missing pinned source {row['file']}; use --download once, then rerun offline"
        )
    request = urllib.request.Request(
        row["url"], headers={"User-Agent": user_agent, "Accept": "text/plain"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(MAX_SOURCE_BYTES + 1)
    if len(data) > MAX_SOURCE_BYTES:
        raise ValueError("reference response exceeds the bounded download size")
    parse_source(data, row)  # Never publish a bad response into the source cache.
    source_dir.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(data)
    except FileExistsError:
        if path.read_bytes() != data:
            raise ValueError(
                "source cache changed concurrently; no file was overwritten"
            ) from None
    return data


def prepare(
    *, manifest_path: Path, source_dir: Path, output: Path, download: bool = False
) -> dict:
    """Prepare deterministic decimal-preserving views; this is not a tool benchmark."""
    manifest_path, source_dir, output = (
        manifest_path.resolve(),
        source_dir.resolve(),
        output.resolve(),
    )
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("choose an empty output directory; prior evidence is retained")
    manifest = read_manifest(manifest_path)
    inputs = []
    for row in manifest["sources"]:
        data = _source(
            row,
            source_dir,
            download=download,
            user_agent=manifest["transport_user_agent"],
        )
        inputs.append((row, data, parse_source(data, row)))
    # Validate every source before creating derived output, retaining the download cache on failure.
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for row, data, parsed in inputs:
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(["observation", "dataset", "value"])
        writer.writerows(
            (i, row["id"], value) for i, value in enumerate(parsed["values"], 1)
        )
        body = buffer.getvalue().encode("ascii")
        destination = output / (row["id"] + ".csv")
        with destination.open("xb") as handle:
            handle.write(body)
        records.append(
            {
                "id": row["id"],
                "source_url": row["url"],
                "source_sha256": digest(data),
                "source_bytes": len(data),
                "csv": destination.name,
                "csv_sha256": digest(body),
                "observations": parsed["observations"],
                "certified": parsed["certified"],
                "nist_source_class": row["nist_source_class"],
                "difficulty": row["difficulty"],
            }
        )
    result = {
        "schema_version": 1,
        "status": "prepared",
        "collection": manifest["collection"],
        "manifest_sha256": digest(manifest_path.read_bytes()),
        "datasets": len(records),
        "observations": sum(r["observations"] for r in records),
        "sources": records,
        "scope": "Pinned source preparation only; no GraphUnslopify/Matplotlib accuracy, timing, figure-quality or user-study result was measured",
    }
    with (output / "preparation.json").open("x", encoding="utf8") as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
        handle.write("\n")
    return result
