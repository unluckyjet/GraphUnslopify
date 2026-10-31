"""Compare accepted inline scripts, bound canonical helpers and current emission."""

from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import io
import json
import os
import runpy
import shutil
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def invoke(namespace, folder, archive):
    """Run genuine CLI policy and inspect its actual written artifacts."""
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = namespace["run_cli"](["--json"])
    return inspect_artifacts(
        namespace,
        folder,
        archive,
        json.loads(stdout.getvalue()),
        exit_code,
        stderr.getvalue(),
    )


def inspect_artifacts(namespace, folder, archive, report, exit_code, stderr):
    """Validate actual report/source/provenance/export bytes; never execute replacements."""
    from graphunslopify.provenance import read_provenance
    from PIL import Image
    from pypdf import PdfReader

    assert report == json.loads((folder / "figure.report.json").read_text())
    assert report["exit_code"] == exit_code and report["policy"]["strict"]
    script_sha = sha((folder / "figure.py").read_bytes())
    assert report["script"]["sha256"] == script_sha
    binding = namespace.get("RUNTIME_BINDING")
    if binding is not None:
        from graphunslopify import figure_runtime

        assert binding["abi"] == figure_runtime.RUNTIME_ABI
        assert (
            binding["source_sha256"] == figure_runtime.runtime_info()["source_sha256"]
        )
        assert binding["functions"] == list(figure_runtime.FUNCTION_NAMES)
        assert binding["components"] == {
            name: sha(Path(figure_runtime.__file__).parent.joinpath(name).read_bytes())
            for name in figure_runtime.SOURCE_COMPONENTS
        }
        assert report["script"]["runtime"] == binding
    outputs = {}
    for item in report["outputs"]:
        path = folder / item["path"]
        raw = path.read_bytes()
        assert sha(raw) == item["sha256"] and len(raw) == item["bytes"]
        fmt = item["format"]
        if fmt in {"png", "svg", "pdf"}:
            evidence = read_provenance(path)
            assert evidence["script_sha256"] == script_sha
            assert evidence["spec_hash"] == report["spec_hash"]
            assert evidence["spec"] == report["spec"]
            assert evidence["data_sha256_prefix"] == namespace["DATA_HASH"]
            if binding is not None:
                assert evidence["runtime"] == binding
        if fmt == "png":
            with Image.open(io.BytesIO(raw)) as image:
                pixels = image.convert("RGBA")
                visible = {
                    "size": list(pixels.size),
                    "rgba_sha256": sha(pixels.tobytes()),
                }
        elif fmt == "svg":
            tree = ET.fromstring(raw)
            for child in list(tree):
                if child.tag.rsplit("}", 1)[-1] == "metadata":
                    tree.remove(child)
            visible = {"drawing_xml_sha256": sha(ET.tostring(tree))}
        elif fmt == "pdf":
            reader = PdfReader(io.BytesIO(raw))
            visible = {
                "pages": [
                    {
                        "mediabox": [float(value) for value in page.mediabox],
                        "drawing_stream_sha256": sha(page.get_contents().get_data()),
                    }
                    for page in reader.pages
                ]
            }
        else:
            visible = {"literal_sha256": sha(raw)}
        outputs[item["path"]] = {"format": fmt, "visible": visible}
    # Reuse the existing all-kind report projection; add environment and output
    # coverage. Artifact SHA/bytes are verified above, not compared across code.
    fields = runpy.run_path(str(ROOT / "scripts/check-render-worker.py"))["FIELDS"]
    semantic = {
        key: report.get(key) for key in [*fields, "environment", "skipped_outputs"]
    }
    archive.mkdir(parents=True)
    retained = {"figure.py", "figure.report.json", namespace["DATA_PATH"]}
    retained.update(item["path"] for item in report["outputs"])
    artifact_files = {}
    for name in sorted(retained):
        if Path(name).name != name:
            raise ValueError("Frozen conformance artifacts must remain plain filenames")
        shutil.copyfile(folder / name, archive / name)
        artifact_files[name] = sha((archive / name).read_bytes())
    return {
        "exit_code": exit_code,
        "status": report["status"],
        "scientific_report": semantic,
        "outputs": outputs,
        "script_sha256": script_sha,
        "stderr_sha256": sha(stderr.encode()),
        "artifact_files": artifact_files,
    }


def load_program(path):
    loaded = runpy.run_path(str(path), run_name="__runtime_foundation_probe__")
    # runpy returns a copy; match PreviewRender's actual original context.
    namespace = loaded["run_cli"].__globals__
    assert namespace["__file__"] == str(path)
    return namespace


def main():
    if not __debug__:
        raise RuntimeError("Run conformance without Python -O/PYTHONOPTIMIZE")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--installed", action="store_true")
    args = parser.parse_args()
    out = args.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    if not args.installed:
        sys.path.insert(0, str(ROOT / "python"))
    import graphunslopify
    from graphunslopify import figure_runtime
    from graphunslopify.transport import local_request

    package = Path(graphunslopify.__file__).resolve().parent
    source = ROOT / "python/graphunslopify"
    if args.installed and package == source.resolve():
        raise ValueError("Installed control resolved to the source checkout")
    assets = {
        str(p.relative_to(package)): sha(p.read_bytes())
        for p in package.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    }
    assert all(
        sha((source / name).read_bytes()) == digest for name, digest in assets.items()
    )
    assert figure_runtime.runtime_info()["source_sha256"] == assets["figure_runtime.py"]
    protocol_bytes = (ROOT / "benchmarks/runtime/protocol.json").read_bytes()
    protocol = json.loads(protocol_bytes)
    archive = ROOT / "benchmarks/runtime" / protocol["baseline_archive"]
    assert sha(archive.read_bytes()) == protocol["baseline_archive_sha256"]
    result = {
        "scope": "Actual accepted-inline/bound/default-shared conformance; no performance claim.",
        "protocol_sha256": sha(protocol_bytes),
        "baseline_archive_sha256": protocol["baseline_archive_sha256"],
        "package_root": str(package),
        "package_files": assets,
        "runtime": figure_runtime.runtime_info(),
        "python": sys.version,
        "expected_cases": len(protocol["cases"]),
        "records": [],
        "complete": False,
        "passed": False,
    }
    previous = Path.cwd()
    try:
        with zipfile.ZipFile(archive) as z:
            manifest = json.loads(z.read("source-manifest.json"))
            assert all(
                sha(z.read(name)) == digest
                for name, digest in manifest["members"].items()
            )
            for case in protocol["cases"]:
                folder = out / case["id"]
                folder.mkdir()
                prefix = "cases/" + case["id"] + "/"
                data = z.read(prefix + case["data"])
                assert sha(data) == case["data_sha256"]
                (folder / case["data"]).write_bytes(data)
                program = z.read(prefix + "figure.py")
                assert sha(program) == case["program_sha256"]
                spec = json.loads(z.read(prefix + "spec.json"))
                script = folder / "figure.py"
                script.write_bytes(program)
                os.chdir(folder)
                record = {"id": case["id"], "kind": case["kind"], "passed": False}
                result["records"].append(record)
                original = load_program(script)
                artifacts = out / "artifacts" / case["id"]
                record["accepted_inline"] = invoke(
                    original, folder, artifacts / "accepted-inline"
                )
                assert (
                    record["accepted_inline"]["exit_code"] == case["expected_exit_code"]
                )
                assert record["accepted_inline"]["status"] == case["expected_status"]
                original["RUNTIME_OPTIONAL_PACKAGES"] = [
                    "graphunslopify",
                    "plotly",
                    "scipy",
                    "pypdf",
                ] + (["python-calamine"] if spec["data"]["format"] == "excel" else [])
                figure_runtime.bind(
                    original,
                    abi=figure_runtime.RUNTIME_ABI,
                    source_sha256=figure_runtime.runtime_info()["source_sha256"],
                    required=figure_runtime.FUNCTION_NAMES,
                )
                assert all(
                    original[name].__globals__ is original
                    for name in figure_runtime.FUNCTION_NAMES
                )
                record["bound_canonical"] = invoke(
                    original, folder, artifacts / "bound-canonical"
                )
                assert record["accepted_inline"] == record["bound_canonical"]
                translated = local_request("convert", spec)
                assert translated["status"] == "translated" and translated["ok"]
                script.write_text(translated["code"])
                current = load_program(script)
                record["current_shared"] = invoke(
                    current, folder, artifacts / "current-shared"
                )
                before, after = (
                    copy.deepcopy(record["accepted_inline"]),
                    copy.deepcopy(record["current_shared"]),
                )
                # Each actual script and embedded static-export provenance was
                # checked above. Compare the actual drawing/science separately.
                before.pop("script_sha256")
                after.pop("script_sha256")
                before.pop("artifact_files")
                after.pop("artifact_files")
                before["scientific_report"]["script"]["sha256"] = (
                    "validated actual script"
                )
                after["scientific_report"]["script"]["sha256"] = (
                    "validated actual script"
                )
                # Actual bound source/capabilities and all embedded descriptors
                # were validated above; older inline artifacts had no binding.
                assert (
                    after["scientific_report"]["script"].pop("runtime")
                    == current["RUNTIME_BINDING"]
                )
                assert before == after
                record["passed"] = True
                print(
                    f"PASS {case['id']} original/bound/current strict{case['expected_exit_code']}",
                    flush=True,
                )
                os.chdir(previous)
        assert len(result["records"]) == 30
        assert len({record["kind"] for record in result["records"]}) == 21
        result["complete"] = True
        result["passed"] = all(record["passed"] for record in result["records"])
    finally:
        os.chdir(previous)
        (out / "results.json").write_text(
            json.dumps(result, indent=2, allow_nan=False) + "\n"
        )


if __name__ == "__main__":
    main()
