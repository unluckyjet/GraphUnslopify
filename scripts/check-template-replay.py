"""Replay portable canonical intent through every frozen native figure kind.

This checks conformance, not speed, independent execution or user productivity.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

from graphunslopify.figure_templates import create_template, review_reuse
from graphunslopify.transport import local_request


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    protocol_raw = (root / "benchmarks/runtime/protocol.json").read_bytes()
    protocol = json.loads(protocol_raw)
    archive = root / "benchmarks/runtime" / protocol["baseline_archive"]
    assert sha(archive.read_bytes()) == protocol["baseline_archive_sha256"]
    summary = {
        "scope": "Actual portable-file replay, canonical/program identity and strict native execution. No speed or human productivity claim.",
        "protocol_sha256": sha(protocol_raw),
        "baseline_archive_sha256": sha(archive.read_bytes()),
        "python": sys.version,
        "records": [],
        "passed": False,
    }
    previous = Path.cwd()
    try:
        with ZipFile(archive) as z:
            for case in protocol["cases"]:
                folder = out / case["id"]
                folder.mkdir()
                prefix = "cases/" + case["id"] + "/"
                raw = z.read(prefix + "spec.json")
                assert raw.endswith(b"\n") and sha(raw[:-1]) == case["spec_sha256"]
                original = json.loads(raw)
                data = z.read(prefix + case["data"])
                assert sha(data) == case["data_sha256"]
                (folder / case["data"]).write_bytes(data)
                os.chdir(folder)
                template = create_template(original, case["kind"] + " portable design")
                template_file = folder / "saved.gu-template.json"
                template_file.write_text(
                    json.dumps(template, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf8",
                )
                active = copy.deepcopy(original)
                active["title"] = "Active draft before portable replay"
                plan = review_reuse(
                    active,
                    template=json.loads(template_file.read_text(encoding="utf8")),
                )
                assert plan["can_apply"] and plan["execution"] == "not_run"
                for key in ("data", "palette_lock", "claims"):
                    assert (key in plan["spec"], plan["spec"].get(key)) == (
                        key in original,
                        original.get(key),
                    )
                before = local_request("convert", original)
                after = local_request("convert", plan["spec"])
                canonical_before = local_request("validate", original)["resolved"]
                canonical_after = local_request("validate", plan["spec"])["resolved"]
                assert (
                    canonical_before == canonical_after
                    and before["code"] == after["code"]
                )
                # Rename every physical CSV column, including unused columns.
                # A missed source reference must fail actual native execution,
                # rather than passing because this test repeats the collector.
                mapped_fields = {}
                actual_data = data
                if original.get("data", {}).get("format", "csv") == "csv":
                    rows = list(csv.reader(io.StringIO(data.decode("utf8"))))
                    source_columns = rows[0]
                    target_columns = ["replayed_" + name for name in source_columns]
                    rows[0] = target_columns
                    stream = io.StringIO(newline="")
                    csv.writer(stream).writerows(rows)
                    actual_data = stream.getvalue().encode("utf8")
                    target_data = folder / "remapped-data.csv"
                    target_data.write_bytes(actual_data)
                    current = copy.deepcopy(active)
                    current["data"] = {
                        **current.get("data", {}),
                        "path": target_data.name,
                        "columns": target_columns,
                    }
                    fields = set(plan["fields"])
                    mapped_fields = {
                        name: "replayed_" + name
                        for name in source_columns
                        if name in fields
                    }
                    plan = review_reuse(
                        current,
                        template=template,
                        mapping=mapped_fields,
                        replace_claims=True,
                    )
                    assert plan["can_apply"]
                    after = local_request("convert", plan["spec"])
                    canonical_after = local_request("validate", plan["spec"])[
                        "resolved"
                    ]
                (folder / "proposal.json").write_text(
                    json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf8",
                )
                script = folder / "figure.py"
                script.write_text(after["code"], encoding="utf8")
                run = subprocess.run(
                    [sys.executable, str(script), "--strict"],
                    cwd=folder,
                    capture_output=True,
                    text=True,
                    encoding="utf8",
                    timeout=180,
                    check=False,
                )
                (folder / "stdout.log").write_text(run.stdout, encoding="utf8")
                (folder / "stderr.log").write_text(run.stderr, encoding="utf8")
                report_path = folder / (
                    canonical_after["output"]["stem"] + ".report.json"
                )
                report = json.loads(report_path.read_text(encoding="utf8"))
                record = {
                    "id": case["id"],
                    "kind": case["kind"],
                    "template_sha256": sha(template_file.read_bytes()),
                    "original_roundtrip_canonical_equal": True,
                    "original_roundtrip_program_equal": True,
                    "original_roundtrip_program_sha256": sha(before["code"].encode()),
                    "executed_program_sha256": sha(script.read_bytes()),
                    "field_mapping": mapped_fields,
                    "actual_data_sha256": sha(actual_data),
                    "exit_code": run.returncode,
                    "expected_exit_code": case["expected_exit_code"],
                    "status": report["status"],
                    "expected_status": case["expected_status"],
                    "report_sha256": sha(report_path.read_bytes()),
                    "passed": False,
                }
                summary["records"].append(record)
                assert run.returncode == case["expected_exit_code"], run.stderr
                assert (
                    report["status"] == case["expected_status"]
                    and report["data"]["sha256_prefix"] == sha(actual_data)[:16]
                )
                assert (folder / case["data"]).read_bytes() == data
                record["passed"] = True
        summary["kinds"] = sorted({r["kind"] for r in summary["records"]})
        assert len(summary["kinds"]) == 21
        summary["remapped_kinds"] = sorted(
            {r["kind"] for r in summary["records"] if r["field_mapping"]}
        )
        assert len(summary["remapped_kinds"]) == 21
        summary["passed"] = True
    finally:
        os.chdir(previous)
        (out / "verification.json").write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf8"
        )
    print(
        json.dumps(
            {
                "passed": True,
                "cases": len(summary["records"]),
                "kinds": len(summary["kinds"]),
                "strict_exits": [r["exit_code"] for r in summary["records"]],
                "evidence": str(out),
            }
        )
    )


if __name__ == "__main__":
    main()
