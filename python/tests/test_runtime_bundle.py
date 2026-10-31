"""Actual source archive reproduction, integrity refusals and input consent."""

import ast
import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

from graphunslopify import Figure, read_provenance

ROOT = Path(__file__).resolve().parents[2]


def frozen_figure(folder, *, negative=False):
    protocol = json.loads((ROOT / "benchmarks/runtime/protocol.json").read_text())
    case = next(case for case in protocol["cases"] if bool(case["expected_exit_code"]) == negative)
    with ZipFile(ROOT / "benchmarks/runtime" / protocol["baseline_archive"]) as archive:
        prefix = "cases/" + case["id"] + "/"
        spec = json.loads(archive.read(prefix + "spec.json"))
        data = folder / case["data"]
        data.write_bytes(archive.read(prefix + case["data"]))
    spec["data"]["path"] = str(data)
    spec["output"]["stem"] = "reproduce"
    return Figure(spec), data


@pytest.fixture(scope="module")
def source_bundle(tmp_path_factory):
    folder = tmp_path_factory.mktemp("actual-source-bundle")
    figure, data = frozen_figure(folder)
    before = copy.deepcopy(figure.to_dict())
    bundle = figure.bundle(folder / "figure.zip")
    assert figure.to_dict() == before
    return bundle, data


def unpack(bundle, folder):
    with ZipFile(bundle) as archive:
        archive.extractall(folder)
    return json.loads((folder / "_graphunslopify/manifest.json").read_text())


def launch(folder, manifest):
    return subprocess.run(
        [sys.executable, str(folder / manifest["launcher"]), "--json"],
        cwd=folder,
        env={**os.environ, "GRAPHUNSLOPIFY_NODE": "/not/a/node/executable"},
        capture_output=True,
        text=True,
        check=False,
    )


def test_actual_archive_reproduces_twice_with_runtime_report_and_embedded_identity(
    source_bundle, tmp_path
):
    bundle, data = source_bundle
    manifest = unpack(bundle, tmp_path)
    assert manifest["launcher"] == "_reproduce.py"  # preserve the author's script name
    for name, item in manifest["files"].items():
        raw = (tmp_path / name).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == item["sha256"] and len(raw) == item["bytes"]
    runtime = tmp_path / "_graphunslopify/runtime/graphunslopify"
    assert (runtime / "LICENSE.txt").read_bytes() == (ROOT / "LICENSE").read_bytes()
    assert (runtime / "ZOD-LICENSE.txt").is_file()
    assert (runtime / "figure_runtime.py").is_file()
    assert b"graphunslopify" not in (tmp_path / "_graphunslopify/requirements.txt").read_bytes()
    for _ in range(2):
        result = launch(tmp_path, manifest)
        assert result.returncode == 0, result.stderr
        report = json.loads(result.stdout)
        assert report["status"] == "passed" and report["policy"]["strict"]
        binding = report["script"]["runtime"]
        assert binding["components"] == manifest["runtime"]["components"]
        assert binding["source_sha256"] == manifest["runtime"]["source_sha256"]
        assert read_provenance(tmp_path / "reproduce.png")["runtime"] == binding
        assert (tmp_path / "data" / data.name).read_bytes() == data.read_bytes()


@pytest.mark.parametrize(
    "member", ["reproduce.py", "_graphunslopify/runtime/graphunslopify/inspect.py", "data"]
)
def test_modified_source_runtime_and_inputs_refuse_before_render(source_bundle, tmp_path, member):
    bundle, data = source_bundle
    manifest = unpack(bundle, tmp_path)
    name = "data/" + data.name if member == "data" else member
    path = tmp_path / name
    path.write_bytes(path.read_bytes() + b"\n# Modified\n")
    result = launch(tmp_path, manifest)
    assert result.returncode != 0 and "Missing or modified archived file" in result.stderr
    assert not (tmp_path / "reproduce.report.json").exists()


def test_omitted_data_is_not_in_archive_and_requires_exact_original(tmp_path):
    figure, data = frozen_figure(tmp_path)
    bundle = figure.bundle(tmp_path / "without-data.zip", include_data=False)
    target = tmp_path / "extracted"
    manifest = unpack(bundle, target)
    name = "data/" + data.name
    assert not (target / name).exists()
    assert manifest["inputs"][0]["included"] is False
    result = launch(target, manifest)
    assert result.returncode != 0 and "Supply the original unchanged input" in result.stderr
    (target / "data").mkdir()
    (target / name).write_bytes(data.read_bytes())
    result = launch(target, manifest)
    assert result.returncode == 0, result.stderr


def test_bundle_preserves_original_strict_negative(tmp_path):
    figure, _ = frozen_figure(tmp_path, negative=True)
    bundle = figure.bundle(tmp_path / "negative.zip")
    target = tmp_path / "extracted"
    manifest = unpack(bundle, target)
    result = launch(target, manifest)
    assert result.returncode == 2, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "failed" and report["policy"]["strict"]
    assert not report["policy"]["passed"]


def test_cli_bundle_resolves_data_beside_spec_and_preserves_canonical_spec(tmp_path, capsys):
    from graphunslopify.cli import main

    figure, data = frozen_figure(tmp_path)
    spec = figure.to_dict()
    spec["data"]["path"] = data.name
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec))
    bundle = tmp_path / "cli.zip"
    assert main(["bundle", str(path), "--output", str(bundle), "--no-data"]) == 0
    assert "source archive" in capsys.readouterr().out.lower()
    with ZipFile(bundle) as archive:
        manifest = json.loads(archive.read("_graphunslopify/manifest.json"))
        assert manifest["inputs"][0]["included"] is False
        assert manifest["inputs"][0]["sha256"] == hashlib.sha256(data.read_bytes()).hexdigest()
        assert "data/" + data.name not in archive.namelist()
        canonical = json.loads(archive.read("reproduce.figure.json"))
        assert canonical["data"]["path"] == "data/" + data.name
        tree = ast.parse(archive.read("reproduce.py"))
        actual = next(
            node.value
            for node in tree.body
            if isinstance(node, ast.Assign)
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "SPEC_JSON"
        )
        assert canonical == json.loads(ast.literal_eval(actual))


def test_archive_destination_cannot_overwrite_original_input(tmp_path):
    from graphunslopify import SpecError

    figure, data = frozen_figure(tmp_path)
    before = data.read_bytes()
    with pytest.raises(SpecError, match="must differ from the original input"):
        figure.bundle(data)
    assert data.read_bytes() == before
