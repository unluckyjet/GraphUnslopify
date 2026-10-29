"""Verify native Excel in the selected installed environment without network access."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.metadata
import io
import json
import shutil
from pathlib import Path

import graphunslopify
from graphunslopify import Figure
from graphunslopify.audit import _input_data, _validate_report
from graphunslopify.describe import profile
from graphunslopify.workbook import read_excel_table


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args()
    where = args.work_dir.resolve()
    where.mkdir(parents=True, exist_ok=True)
    repository = Path(__file__).resolve().parent.parent
    assert not Path(graphunslopify.__file__).resolve().is_relative_to(repository)
    original = repository / "python/tests/fixtures/native-values.xls"
    source = where / "original experiment.xls"
    shutil.copyfile(original, source)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    result = profile(source)
    assert result["ok"] and result["sheet"] == "Measurements" and result["rows"] == 3
    frame = read_excel_table(source, sheet="Measurements")
    assert frame["subject"].tolist() == ["001", "NA", "010"]
    assert frame["score"].tolist() == [7, 11, 13]
    figure = (
        Figure.bar(source)
        .worksheet("Measurements")
        .x("subject", "Subject")
        .y("score", "Score", unit="%")
    )
    figure.spec.update(
        aggregation="none",
        legend={"show": False},
        output={"stem": "excel", "formats": ["png", "svg", "pdf"], "dpi": 100},
    )
    authored = figure.to_dict()
    with contextlib.redirect_stdout(io.StringIO()):
        rendered = figure.render(cwd=where / "verified exports")
    report = rendered["report"]
    _validate_report(report)
    assert figure.to_dict() == authored
    assert report["spec"]["data"]["sheet"] == "Measurements"
    assert report["environment"]["installed_optional_versions"][
        "python-calamine"
    ] == importlib.metadata.version("python-calamine")
    output = where / "verified exports"
    hashes = {}
    for suffix in ["png", "svg", "pdf"]:
        path = output / f"excel.{suffix}"
        assert path.is_file() and path.stat().st_size > 0
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert _input_data(source, "excel", "Measurements")["sha256"] == digest
    assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
    evidence = {
        "status": "passed",
        "source_sha256": digest,
        "rows": 3,
        "worksheet": "Measurements",
        "exports": hashes,
        "package": str(Path(graphunslopify.__file__).resolve()),
        "reader_version": importlib.metadata.version("python-calamine"),
    }
    (where / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence))


if __name__ == "__main__":
    main()
