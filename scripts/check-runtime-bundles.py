"""Reproduce every frozen kind outside the checkout with no GraphUnslopify installation."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import runpy
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def refusal_controls(executable, out, environment, program, data_name, raw):
    from graphunslopify import figure_runtime

    results = []
    for mode in ["missing", "wrong_source", "wrong_abi", "missing_components"]:
        folder = out / ("entry-refusal-" + mode)
        folder.mkdir()
        (folder / "figure.py").write_bytes(program)
        (folder / data_name).write_bytes(raw)
        env = dict(environment)
        if mode != "missing":
            package = folder / "incompatible installed source" / "graphunslopify"
            package.mkdir(parents=True)
            (package / "__init__.py").write_text("")
            runtime = Path(figure_runtime.__file__).read_bytes()
            if mode == "wrong_source":
                runtime += b"\n# Changed source; same nominal ABI\n"
            elif mode == "wrong_abi":
                runtime = runtime.replace(b"RUNTIME_ABI = 1", b"RUNTIME_ABI = 999")
            (package / "figure_runtime.py").write_bytes(runtime)
            env["PYTHONPATH"] = str(package.parent)
        completed = subprocess.run(
            [str(executable), str(folder / "figure.py"), "--json"],
            cwd=folder,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        assert completed.returncode != 0 and "RuntimeError" in completed.stderr
        assert "runtime" in completed.stderr and "bundle" in completed.stderr
        assert not list(folder.glob("*.report.json")) and not list(folder.glob("*.png"))
        (folder / "stdout.txt").write_text(completed.stdout)
        (folder / "stderr.txt").write_text(completed.stderr)
        results.append(
            {
                "mode": mode,
                "exit_code": completed.returncode,
                "no_report_or_png": True,
                "stderr_sha256": sha(completed.stderr.encode()),
            }
        )
    return results


def main():
    if not __debug__:
        raise RuntimeError("Run this verifier without Python optimization")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--foundation", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    executable = (
        args.python.expanduser().absolute()
    )  # preserve the venv executable symlink
    out = args.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    if out.is_relative_to(ROOT):
        raise ValueError("Standalone acceptance must run outside the checkout")
    environment = {
        key: value for key, value in os.environ.items() if key != "PYTHONPATH"
    }
    environment["GRAPHUNSLOPIFY_NODE"] = "/deliberately/not/a/node/executable"
    probe = subprocess.run(
        [
            str(executable),
            "-c",
            """
import importlib.metadata, importlib.util, json, sys
try: version = importlib.metadata.version('graphunslopify')
except importlib.metadata.PackageNotFoundError: version = None
assert version is None and importlib.util.find_spec('graphunslopify') is None
print(json.dumps({'interpreter':sys.executable,'prefix':sys.prefix,'version':sys.version,
                 'distribution_absent':True,'import_absent':True}))
""",
        ],
        cwd=out,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    sys.path.insert(0, str(ROOT / "python"))
    from graphunslopify.runtime_bundle import create_bundle
    from graphunslopify.transport import local_request

    inspect = runpy.run_path(str(ROOT / "scripts/check-runtime-foundation.py"))[
        "inspect_artifacts"
    ]
    protocol_raw = (ROOT / "benchmarks/runtime/protocol.json").read_bytes()
    protocol = json.loads(protocol_raw)
    archive = ROOT / "benchmarks/runtime" / protocol["baseline_archive"]
    assert sha(archive.read_bytes()) == protocol["baseline_archive_sha256"]
    foundation = json.loads((args.foundation / "results.json").read_text())
    assert foundation["complete"] and foundation["passed"]
    assert foundation["protocol_sha256"] == sha(protocol_raw)
    for name, digest in foundation["package_files"].items():
        assert sha((ROOT / "python/graphunslopify" / name).read_bytes()) == digest
    originals = {record["id"]: record for record in foundation["records"]}
    result = {
        "scope": "Actual all-kind conformance, not a performance measurement or human study.",
        "protocol_sha256": sha(protocol_raw),
        "probe": json.loads(probe.stdout),
        "records": [],
        "entry_refusals": [],
        "complete": False,
        "passed": False,
    }
    try:
        with ZipFile(archive) as baseline:
            for case in protocol["cases"]:
                folder = out / case["id"]
                folder.mkdir()
                prefix = "cases/" + case["id"] + "/"
                raw = baseline.read(prefix + case["data"])
                assert sha(raw) == case["data_sha256"]
                spec_raw = baseline.read(prefix + "spec.json")
                # The frozen producer stores literal SPEC_JSON plus one newline;
                # its declared digest covers SPEC_JSON itself, not that newline.
                assert (
                    spec_raw.endswith(b"\n")
                    and sha(spec_raw[:-1]) == case["spec_sha256"]
                )
                assert (
                    sha(baseline.read(prefix + "figure.py")) == case["program_sha256"]
                )
                spec = json.loads(spec_raw)
                translated = local_request("convert", spec)
                assert translated["status"] == "translated" and translated["ok"]
                program = translated["code"].encode()
                if not result["records"]:
                    result["entry_refusals"] = refusal_controls(
                        executable, out, environment, program, case["data"], raw
                    )
                bundled = create_bundle(
                    {"figure.py": program},
                    script="figure.py",
                    inputs={case["data"]: raw},
                )
                bundle_path = folder / "figure.zip"
                bundle_path.write_bytes(bundled)
                target = folder / "outside checkout"
                with ZipFile(bundle_path) as zipped:
                    assert all(
                        not Path(n).is_absolute() and ".." not in Path(n).parts
                        for n in zipped.namelist()
                    )
                    zipped.extractall(target)
                    manifest = json.loads(zipped.read("_graphunslopify/manifest.json"))
                assert (target / "figure.py").read_bytes() == program
                assert (target / case["data"]).read_bytes() == raw
                for name, item in manifest["files"].items():
                    actual = (target / name).read_bytes()
                    assert (
                        sha(actual) == item["sha256"] and len(actual) == item["bytes"]
                    )
                completed = subprocess.run(
                    [str(executable), str(target / manifest["launcher"]), "--json"],
                    cwd=target,
                    env=environment,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=120,
                )
                (folder / "stdout.json").write_text(completed.stdout)
                (folder / "stderr.txt").write_text(completed.stderr)
                assert completed.returncode == case["expected_exit_code"], (
                    completed.stderr
                )
                report = json.loads(completed.stdout)
                assert report["status"] == case["expected_status"]
                assert (
                    report["environment"]["installed_optional_versions"][
                        "graphunslopify"
                    ]
                    is None
                )
                signature = inspect(
                    {
                        "DATA_PATH": case["data"],
                        "DATA_HASH": sha(raw)[:16],
                        "RUNTIME_BINDING": report["script"]["runtime"],
                    },
                    target,
                    folder / "retained actual exports",
                    report,
                    completed.returncode,
                    completed.stderr,
                )
                expected = copy.deepcopy(originals[case["id"]]["current_shared"])
                actual = copy.deepcopy(signature)
                # The source and no-package controls truthfully differ only in
                # installed GraphUnslopify distribution metadata. Validate absence
                # above; all other environment fields must still match exactly.
                expected["scientific_report"]["environment"][
                    "installed_optional_versions"
                ]["graphunslopify"] = None
                for value in [actual, expected]:
                    value.pop("artifact_files")
                    value.pop(
                        "stderr_sha256"
                    )  # complete raw streams retained; launcher paths differ
                assert actual == expected, case["id"]
                record = {
                    "id": case["id"],
                    "kind": case["kind"],
                    "exit_code": completed.returncode,
                    "status": report["status"],
                    "bundle_sha256": sha(bundled),
                    "bundle_bytes": len(bundled),
                    "runtime_files": sum(
                        n.startswith("_graphunslopify/runtime/")
                        for n in manifest["files"]
                    ),
                    "signature": signature,
                    "passed": True,
                }
                result["records"].append(record)
                print(
                    f"PASS {case['id']} actual no-package standalone strict{completed.returncode}",
                    flush=True,
                )
        assert len(result["records"]) == len(protocol["cases"]) == 30
        assert len({record["kind"] for record in result["records"]}) == 21
        result["complete"] = result["passed"] = True
    finally:
        (out / "results.json").write_text(
            json.dumps(result, indent=2, allow_nan=False) + "\n"
        )


if __name__ == "__main__":
    main()
