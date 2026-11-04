"""Reviewable static source import with byte-bound original/data provenance."""

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .owned_reader import ReaderError, run_reader
from .source_parser import MAX_SOURCE
from .worker_process import JsonWorker

MAX_DATA = 20 * 1024 * 1024
MAX_RSS = 512 * 1024 * 1024


class SourceImportError(ValueError):
    pass


@dataclass
class SourceImport:
    original: bytes
    csv_bytes: bytes | None
    spec: dict | None
    report: dict


def import_source(source, *, data=None, name="original.py"):
    """Analyze UTF8 source and explicitly supplied CSV bytes in an owned worker."""
    if isinstance(source, str):
        source = source.encode()
    if not isinstance(source, bytes) or not source or len(source) > MAX_SOURCE:
        raise SourceImportError("Choose nonempty Python source of at most256KiB")
    if (
        not isinstance(name, str)
        or len(name) > 128
        or Path(name).name != name
        or not name.endswith((".py", ".pyw"))
    ):
        raise SourceImportError("Source name must be a simple Python filename")
    try:
        text = source.decode("utf-8-sig")
    except UnicodeDecodeError as problem:
        raise SourceImportError("Source import supports UTF8 Python files") from problem
    if data is not None and (not isinstance(data, bytes) or not data or len(data) > MAX_DATA):
        raise SourceImportError("Mapped CSV must be nonempty and at most20MiB")
    with tempfile.TemporaryDirectory(prefix="gu-source-import-") as directory:
        root = Path(directory)
        if data is not None:
            (root / "bound-data.csv").write_bytes(data)
        try:
            result = run_reader(
                root,
                module="graphunslopify.source_worker",
                kind="source-import",
                payload={"source": text, "mapped": data is not None},
                filename="analysis.json",
                max_output=32 * 1024 * 1024,
                max_rss=MAX_RSS,
                timeout=20,
                worker_factory=JsonWorker,
            )
        except ReaderError as problem:
            raise SourceImportError(str(problem)) from problem
    report = result["report"]
    report.update(
        original_name=name,
        original_bytes=len(source),
        original_sha256=hashlib.sha256(source).hexdigest(),
        mapped_data_sha256=hashlib.sha256(data).hexdigest() if data is not None else None,
        mapped_data_identity_is_author_supplied=data is not None,
    )
    report["snapshot"] = hashlib.sha256(
        json.dumps(
            {
                "source": report["original_sha256"],
                "data": report["mapped_data_sha256"],
                "reader": report["reader"],
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    return SourceImport(
        source,
        result["csv_text"].encode() if result.get("csv_text") is not None else None,
        result["spec"],
        report,
    )


def save_source_import(proposal, destination, *, accept_partial=False, render=False):
    """Keep the unexecuted original/report even when the proposed conversion refuses."""
    from .build import Figure
    from .errors import SpecError

    root = Path(destination).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / "original-source.py").write_bytes(proposal.original)
    report = copy.deepcopy(proposal.report)
    report["original_saved_as"] = "original-source.py"
    if not report["convertible"]:
        result = {"exit_code": 1, "import": report, "native_status": "not_run"}
    elif report["requires_partial_review"] and not accept_partial:
        result = {
            "exit_code": 1,
            "import": {
                **report,
                "reason": "Explicitly review unsupported behavior before accepting partial extraction",
            },
            "native_status": "not_run",
        }
    else:
        (root / "imported-source.csv").write_bytes(proposal.csv_bytes)
        spec = copy.deepcopy(proposal.spec)
        (root / "imported-source.figure.json").write_text(json.dumps(spec, indent=2) + "\n")
        result = {"exit_code": 0, "import": report, "native_status": "not_run"}
        if render:
            spec["data"]["path"] = str(root / "imported-source.csv")
            try:
                native = Figure(spec).render(cwd=root, strict=True)["report"]
                result.update(
                    exit_code=0 if native["status"] == "passed" else 2,
                    native_status=native["status"],
                )
            except SpecError as problem:
                native = problem.report
                result.update(
                    exit_code=2 if native else 1,
                    native_status=native.get("status", "incomplete") if native else "incomplete",
                    error=str(problem),
                )
            result["native_report"] = native
        report["materialized_csv_sha256"] = hashlib.sha256(proposal.csv_bytes).hexdigest()
        if (root / "imported-source.csv").read_bytes() != proposal.csv_bytes:
            result.update(exit_code=2, error="Materialized source data changed during rendering")
    (root / "source-import.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
