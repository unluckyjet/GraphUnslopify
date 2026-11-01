"""Verify actual selective execution/copy outcomes on the unchanged frozen all-kind corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sha = lambda raw: hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--installed", action="store_true")
    args = parser.parse_args()
    out = args.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    if not args.installed:
        sys.path.insert(0, str(ROOT / "python"))
    import graphunslopify
    from graphunslopify.project import initialize_project, project_history, run_project

    package = Path(graphunslopify.__file__).resolve()
    if args.installed:
        assert package.is_relative_to(Path(sys.prefix).resolve())
    protocol_raw = (ROOT / "benchmarks/runtime/protocol.json").read_bytes()
    protocol = json.loads(protocol_raw)
    archive = ROOT / "benchmarks/runtime" / protocol["baseline_archive"]
    assert sha(archive.read_bytes()) == protocol["baseline_archive_sha256"]
    cases = protocol["cases"]
    positives = [c for c in cases if c["expected_exit_code"] == 0]
    negatives = [c for c in cases if c["expected_exit_code"] != 0]
    assert len(cases) == 30 and len(positives) == 29 and len(negatives) == 1
    assert len({c["kind"] for c in positives}) == 21
    records = []
    with zipfile.ZipFile(archive) as z:
        for label, group in [
            ("accepted-all-kinds", positives),
            ("original-negative", negatives),
        ]:
            paper = out / label
            paper.mkdir()
            entries = []
            for case in group:
                folder = paper / case["id"]
                folder.mkdir()
                assert Path(case["data"]).name == case["data"]
                prefix = "cases/" + case["id"] + "/"
                data = z.read(prefix + case["data"])
                assert sha(data) == case["data_sha256"]
                (folder / case["data"]).write_bytes(data)
                (folder / "figure.json").write_bytes(z.read(prefix + "spec.json"))
                entries.append({"id": case["id"], "spec": case["id"] + "/figure.json"})
            (paper / "graphunslopify.json").write_text(
                json.dumps({"schema_version": 1, "figures": entries})
            )
            initialize_project(paper)
            before = run_project(paper, baseline=None)
            after = run_project(paper, selective=True, baseline=None)
            assert (
                before["exit_code"]
                == after["exit_code"]
                == (0 if label == "accepted-all-kinds" else 2)
            )
            assert before["audit"]["execution_counts"] == {
                "executed": len(group),
                "reused": 0,
                "not_run": 0,
            }
            assert after["audit"]["execution_counts"] == {
                "executed": 0 if label == "accepted-all-kinds" else len(group),
                "reused": len(group) if label == "accepted-all-kinds" else 0,
                "not_run": 0,
            }
            old = {f["id"]: f for f in before["audit"]["figures"]}
            new = {f["id"]: f for f in after["audit"]["figures"]}
            for case in group:
                first, last = old[case["id"]], new[case["id"]]
                assert first["status"] == last["status"] == case["expected_status"]
                assert (
                    first["data"]["sha256"]
                    == last["data"]["sha256"]
                    == case["data_sha256"]
                )
                assert set(case["formats"]) <= {f["format"] for f in last["outputs"]}
                if case["expected_exit_code"] == 0:
                    assert first["report"] == last["report"]
                    assert last["execution"]["mode"] == "reused"
                    assert last["execution"]["origin_event"] == before["id"]
                    for a, b in zip(first["outputs"], last["outputs"], strict=True):
                        one = Path(before["directory"]) / "audit" / a["path"]
                        two = Path(after["directory"]) / "audit" / b["path"]
                        assert one.read_bytes() == two.read_bytes()
                        assert sha(two.read_bytes()) == b["sha256"]
                else:
                    assert last["execution"]["mode"] == "executed"
                records.append(
                    {
                        "id": case["id"],
                        "kind": case["kind"],
                        "status": last["status"],
                        "expected_exit": case["expected_exit_code"],
                        "execution": last["execution"],
                        "outputs": last["outputs"],
                        "data_sha256": last["data"]["sha256"],
                    }
                )
            assert project_history(paper)["integrity"] == "verified"
    result = {
        "status": "passed",
        "scope": "Functional all-kind conformance, not performance/human evidence. Original frozen data/specs/statuses/formats retained. Actual accepted reports/exports are copied without scientific re-execution; the original strict negative reruns and stays rejected.",
        "protocol_sha256": sha(protocol_raw),
        "baseline_archive_sha256": sha(archive.read_bytes()),
        "cases": len(records),
        "kinds": 21,
        "accepted_reused": 29,
        "original_strict_negative_rerun": 1,
        "python": sys.version,
        "executable": sys.executable,
        "package": str(package),
        "installed": args.installed,
        "records": records,
    }
    (out / "checks.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: result[k]
                for k in [
                    "status",
                    "cases",
                    "kinds",
                    "accepted_reused",
                    "original_strict_negative_rerun",
                    "installed",
                ]
            }
        )
    )


if __name__ == "__main__":
    main()
