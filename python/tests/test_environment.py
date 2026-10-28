"""Real runtime context, export parity, unknowns and old records without backfill."""

from __future__ import annotations

import copy
import hashlib
import importlib.metadata
import importlib.util
import json
import platform
import subprocess
import sys
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from jsonschema import validate
from PIL import Image, PngImagePlugin

from graphunslopify import read_provenance
from graphunslopify.provenance import ProvenanceError
from graphunslopify.transport import local_request

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "docs/environment.schema.json").read_text())
REPORT_SCHEMA = json.loads((ROOT / "docs/runtime-report.schema.json").read_text())


def generated(folder, *, kind="line", interactive=False):
    raw = {
        "kind": kind,
        "data": {"path": str(folder / "data.csv")},
        "x": {"field": "x", "label": "Input"},
        "y": {"field": "y", "label": "Value"},
        "aggregation": "mean",
        "uncertainty": {"kind": "ci", "over": "unit"},
        "legend": {"show": False},
        "output": {
            "stem": "environment",
            "formats": ["png", "svg", "pdf"],
            "dpi": 100,
            "size": "double_column",
            "interactive": interactive,
        },
    }
    result = local_request("convert", raw)
    assert result["ok"], result
    path = folder / "figure.py"
    path.write_text(result["code"], encoding="utf8")
    spec = importlib.util.spec_from_file_location("environment_reference", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rows(folder):
    pd.DataFrame(
        {"x": [1, 1, 1, 2, 2, 2], "y": [1, 2, 3, 4, 5, 6], "unit": ["01", "1", "B"] * 2}
    ).to_csv(folder / "data.csv", index=False)


@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close("all")


@pytest.fixture(scope="module")
def exports(tmp_path_factory):
    folder = tmp_path_factory.mktemp("environment-exports")
    module = generated(folder, interactive=True)
    rows(folder)
    run = subprocess.run(
        [sys.executable, module.__file__, "--json"],
        cwd=folder,
        capture_output=True,
        text=True,
        check=False,
    )
    report = json.loads(run.stdout)
    assert run.returncode == 0 and report["status"] == "passed", report
    validate(report, REPORT_SCHEMA)
    return folder, report


@pytest.mark.parametrize("extension", ["png", "svg", "pdf", "html"])
def test_actual_exports_share_the_report_snapshot_and_loaded_versions(exports, extension):
    folder, report = exports
    actual = read_provenance(folder / f"environment.{extension}")["environment"]
    assert actual == report["environment"]
    validate(actual, SCHEMA)
    assert actual["capture_stage"] == "before_export"
    assert actual["loaded_core_versions"]["numpy"] == np.__version__
    assert actual["loaded_core_versions"]["pandas"] == pd.__version__
    assert actual["loaded_core_versions"]["matplotlib"] == matplotlib.__version__
    assert actual["python"]["version"] == platform.python_version()
    assert actual["rendering"]["backend"].lower() == "agg"
    assert actual["rendering"]["export_dpi"] == 100
    assert actual["rendering"]["figure_dpi"] > 0
    assert actual["execution"] == {"strict": True, "fail_on_warning": False, "source": "cli"}
    assert actual["random_constants"] == {"BOOTSTRAP_SEED": 20260902, "BOOTSTRAP_DRAWS": 2000}
    from matplotlib import font_manager

    font = actual["rendering"]["default_font"]
    rc = actual["rendering"]["rc_parameters"]
    path = font_manager.findfont(
        font_manager.FontProperties(
            family=rc["font.family"],
            style=rc["font.style"],
            weight=rc["font.weight"],
            variant=rc["font.variant"],
            stretch=rc["font.stretch"],
        )
    )
    assert font["sha256"] == hashlib.sha256(Path(path).read_bytes()).hexdigest()
    assert font["file"] == Path(path).name


def test_import_alone_does_not_capture_host_context(tmp_path, monkeypatch):
    calls = []
    original = importlib.metadata.version

    def record(name):
        calls.append(name)
        return original(name)

    monkeypatch.setattr(importlib.metadata, "version", record)
    module = generated(tmp_path)
    assert module.RUN_REPORT["environment"] is None
    assert not calls


@pytest.mark.parametrize("failure", ["absent", "unreadable"])
def test_optional_metadata_is_unknown_without_importing_or_leaking_errors(
    tmp_path, monkeypatch, failure
):
    module = generated(tmp_path)

    def unavailable(name):
        if failure == "absent":
            raise importlib.metadata.PackageNotFoundError(name)
        raise RuntimeError("private-error-marker")

    monkeypatch.setattr(importlib.metadata, "version", unavailable)
    _, ax = plt.subplots()
    snapshot = module.capture_environment(ax.figure)
    validate(snapshot, SCHEMA)
    assert all(value is None for value in snapshot["installed_optional_versions"].values())
    assert snapshot["loaded_core_versions"]["numpy"] == np.__version__
    assert "private-error-marker" not in json.dumps(snapshot)
    assert len(snapshot["unavailable"]) == (0 if failure == "absent" else 4)


def test_environment_scope_excludes_host_paths_secrets_and_arbitrary_configuration(
    tmp_path, monkeypatch
):
    module = generated(tmp_path)
    monkeypatch.setenv("GRAPHUNSLOPIFY_TEST_SECRET", "private-secret-marker")
    monkeypatch.setattr(platform, "node", lambda: "private-hostname-marker")
    _, ax = plt.subplots()
    snapshot = module.capture_environment(ax.figure)
    encoded = json.dumps(snapshot)
    assert not any(
        value in encoded
        for value in [str(tmp_path), "private-secret-marker", "private-hostname-marker"]
    )
    assert "cwd" not in encoded and "executable" not in encoded and "environ" not in snapshot
    validate(snapshot, SCHEMA)


def test_direct_main_captures_owned_render_settings_without_inventing_cli_policy(
    tmp_path, monkeypatch
):
    module = generated(tmp_path)
    rows(tmp_path)
    monkeypatch.chdir(tmp_path)
    with matplotlib.rc_context({"font.size": 23}):
        module.main()
        snapshot = module.RUN_REPORT["environment"]
        assert snapshot["rendering"]["rc_parameters"]["font.size"] == module.RC_PARAMS["font.size"]
        assert snapshot["rendering"]["rc_parameters"]["font.size"] != 23
        assert matplotlib.rcParams["font.size"] == 23
    assert snapshot["execution"] == {
        "strict": None,
        "fail_on_warning": None,
        "source": "direct_call",
    }
    validate(snapshot, SCHEMA)


@pytest.mark.parametrize("flags", [[], ["--no-strict"], ["--fail-on-warning"]])
def test_each_cli_run_resets_snapshot_and_records_effective_execution_policy(
    tmp_path, monkeypatch, flags
):
    module = generated(tmp_path)
    rows(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert module.run_cli(["--json"]) == 0
    first = module.RUN_REPORT["environment"]
    module.DPI = 144
    code = module.run_cli(["--json", *flags])
    second = module.RUN_REPORT["environment"]
    assert first["rendering"]["export_dpi"] == 100 and second["rendering"]["export_dpi"] == 144
    assert second["execution"]["strict"] == ("--no-strict" not in flags)
    assert second["execution"]["fail_on_warning"] == ("--fail-on-warning" in flags)
    assert code == (2 if "--fail-on-warning" in flags else 0)
    assert read_provenance(tmp_path / "environment.png")["environment"] == second


def test_early_failure_does_not_invent_a_rendered_figure_snapshot(tmp_path, monkeypatch):
    module = generated(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert module.run_cli(["--json"]) == 1
    snapshot = module.RUN_REPORT["environment"]
    assert snapshot["capture_stage"] == "no_export_snapshot"
    for key in ["figure_inches", "figure_dpi", "rc_parameters", "default_font"]:
        assert snapshot["rendering"][key] is None
    assert snapshot["execution"]["strict"]
    validate(snapshot, SCHEMA)


def test_table_metadata_captures_its_actual_figure_before_context_restoration(
    tmp_path, monkeypatch
):
    module = generated(tmp_path, kind="table")
    rows(tmp_path)
    monkeypatch.chdir(tmp_path)
    sizes = []
    original = module.check

    def observe(fig):
        sizes.append(list(fig.get_size_inches()))
        return original(fig)

    monkeypatch.setattr(module, "check", observe)
    assert module.run_cli(["--json"]) == 0
    snapshot = module.RUN_REPORT["environment"]
    assert snapshot["capture_stage"] == "before_export"
    assert snapshot["rendering"]["figure_inches"] == sizes[0]
    assert snapshot["rendering"]["figure_inches"] != list(module.FIGSIZE)
    for extension in ["png", "svg", "pdf"]:
        assert read_provenance(tmp_path / f"environment.{extension}")["environment"] == snapshot


@pytest.mark.parametrize("damage", [None, {"schema_version": 2}, "wrong", {"schema_version": True}])
def test_reader_rejects_malformed_environment_in_real_png(exports, tmp_path, damage):
    folder, _ = exports
    payload = read_provenance(folder / "environment.png")
    payload["environment"] = damage
    info = PngImagePlugin.PngInfo()
    info.add_text("GraphUnslopify", json.dumps(payload))
    path = tmp_path / "bad.png"
    Image.new("RGB", (2, 2)).save(path, pnginfo=info)
    with pytest.raises(ProvenanceError, match="environment"):
        read_provenance(path)


def test_reader_preserves_old_envelopes_without_backfilling_current_host(exports, tmp_path):
    folder, _ = exports
    payload = read_provenance(folder / "environment.png")
    payload.pop("environment")
    info = PngImagePlugin.PngInfo()
    info.add_text("GraphUnslopify", json.dumps(payload))
    path = tmp_path / "legacy-v1.png"
    Image.new("RGB", (2, 2)).save(path, pnginfo=info)
    assert read_provenance(path) == payload
    assert "environment" not in read_provenance(path)


def test_runtime_and_packaged_schemas_use_the_same_environment_contract():
    definition = copy.deepcopy(SCHEMA)
    definition.pop("$schema")
    definition.pop("$id")
    assert REPORT_SCHEMA["$defs"]["environment"] == definition
    assert (
        json.loads((ROOT / "python/graphunslopify/schemas/environment.schema.json").read_text())
        == SCHEMA
    )


def test_a_new_direct_report_does_not_inherit_a_previous_cli_policy(tmp_path, monkeypatch):
    module = generated(tmp_path)
    rows(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert module.run_cli(["--json", "--no-strict"]) == 0
    assert "_execution_policy" not in module.RUN_REPORT
    module.RUN_REPORT = module.new_report()
    module.main()
    assert module.RUN_REPORT["environment"]["execution"] == {
        "strict": None,
        "fail_on_warning": None,
        "source": "direct_call",
    }


def test_snapshot_is_detached_from_mutable_renderer_configuration(tmp_path):
    module = generated(tmp_path)
    _, ax = plt.subplots()
    family = matplotlib.rcParams["font.family"]
    before = list(family)
    snapshot = module.capture_environment(ax.figure)
    try:
        family.append("subsequent configuration")
        assert snapshot["rendering"]["rc_parameters"]["font.family"] == before
    finally:
        family[:] = before


@pytest.mark.parametrize("damage", ["policy", "rc", "path", "version", "extra", "stage"])
def test_reader_rejects_inconsistent_or_wrongly_typed_context(exports, tmp_path, damage):
    folder, _ = exports
    payload = read_provenance(folder / "environment.png")
    env = payload["environment"]
    if damage == "policy":
        env["execution"]["strict"] = "yes"
    elif damage == "rc":
        env["rendering"]["rc_parameters"]["font.size"] = {}
    elif damage == "path":
        env["rendering"]["default_font"]["file"] = "/private/font.ttf"
    elif damage == "version":
        env["loaded_core_versions"]["numpy"] = 123
    elif damage == "extra":
        env["hostname"] = "undeclared host field"
    else:
        env["capture_stage"] = "no_export_snapshot"
    info = PngImagePlugin.PngInfo()
    info.add_text("GraphUnslopify", json.dumps(payload))
    path = tmp_path / "invalid-context.png"
    Image.new("RGB", (2, 2)).save(path, pnginfo=info)
    with pytest.raises(ProvenanceError, match="environment"):
        read_provenance(path)


def test_audit_refuses_valid_but_different_embedded_environment(exports, tmp_path):
    from graphunslopify.audit import AuditError, _outputs

    folder, report = exports
    payload = read_provenance(folder / "environment.png")
    payload["environment"]["execution"]["strict"] = False
    info = PngImagePlugin.PngInfo()
    info.add_text("GraphUnslopify", json.dumps(payload))
    path = tmp_path / "mismatch.png"
    Image.new("RGB", (2, 2)).save(path, pnginfo=info)
    altered = copy.deepcopy(report)
    altered["outputs"] = [
        {
            "path": str(path),
            "format": "png",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size,
        }
    ]
    with pytest.raises(AuditError, match="provenance does not match"):
        _outputs(altered, tmp_path, tmp_path, require_all=False)


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_reader_rejects_nonfinite_context_even_when_json_parser_accepts_it(
    exports, tmp_path, value
):
    folder, _ = exports
    payload = read_provenance(folder / "environment.png")
    payload["environment"]["rendering"]["figure_dpi"] = value
    info = PngImagePlugin.PngInfo()
    info.add_text("GraphUnslopify", json.dumps(payload))
    path = tmp_path / "nonfinite.png"
    Image.new("RGB", (2, 2)).save(path, pnginfo=info)
    with pytest.raises(ProvenanceError, match="environment"):
        read_provenance(path)
