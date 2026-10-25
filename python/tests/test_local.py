"""Exercise the real bundled emitter and its path/error contracts."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from graphunslopify import Figure, SpecError
from graphunslopify.demo import write_demo
from graphunslopify.transport import local_request


def test_default_translate_never_uses_the_http_transport(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("HTTP transport used")

    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    monkeypatch.delenv("GRAPHUNSLOPIFY_API", raising=False)
    result = Figure.line().x("epoch", "Epoch").y("score", "Score").translate()
    assert result["status"] == "translated" and result["ok"]
    assert "def main()" in result["code"]


def test_profile_preserves_the_actual_source_and_rank_validation(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHUNSLOPIFY_API", "local")
    spec_path = write_demo(tmp_path)
    path = spec_path.parent / "results.csv"
    figure = Figure.from_profile(path)
    assert Path(figure.spec["data"]["path"]) == path
    assert figure.translate()["status"] == "translated"
    with pytest.raises(SpecError, match="rank"):
        Figure.from_profile(path, rank=99)


def test_local_translator_rejects_unknown_operations():
    with pytest.raises(SpecError, match="Unknown local operation"):
        local_request("does-not-exist")


def test_cli_render_resolves_relative_data_and_reports_static_errors(tmp_path):
    spec_path = write_demo(tmp_path / "project data")
    output = tmp_path / "outputs"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "graphunslopify.cli",
            "render",
            str(spec_path),
            "--out-dir",
            str(output),
            "--strict",
            "--json",
            "--api",
            "local",
        ],
        capture_output=True,
        text=True,
        encoding="utf8",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "passed"
    assert report["data"]["counts"]["read"] == 24
    assert (output / "figure.png").is_file()
    bad = tmp_path / "bad.json"
    bad.write_text('{"kind":"not-a-kind"}')
    rejected = subprocess.run(
        [
            sys.executable,
            "-m",
            "graphunslopify.cli",
            "render",
            str(bad),
            "--strict",
            "--json",
            "--api",
            "local",
        ],
        capture_output=True,
        text=True,
        encoding="utf8",
        check=False,
    )
    assert rejected.returncode == 2
    assert json.loads(rejected.stdout)["status"] == "failed"
