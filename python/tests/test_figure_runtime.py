"""Actual generated-context isolation and refusal of incompatible runtime bindings."""

import copy
import importlib.util
import json
import runpy
import zipfile
from pathlib import Path

import pytest

from graphunslopify import figure_runtime

ROOT = Path(__file__).resolve().parents[2]


def generated_context(folder, index):
    protocol = json.loads((ROOT / "benchmarks/runtime/protocol.json").read_text())
    case = protocol["cases"][index]
    folder.mkdir()
    script = folder / "figure.py"
    with zipfile.ZipFile(ROOT / "benchmarks/runtime" / protocol["baseline_archive"]) as z:
        script.write_bytes(z.read("cases/" + case["id"] + "/figure.py"))
    loaded = runpy.run_path(str(script), run_name="__runtime_context_test__")
    context = loaded["run_cli"].__globals__
    context["RUNTIME_OPTIONAL_PACKAGES"] = ["graphunslopify", "plotly", "scipy", "pypdf"]
    return context


def test_actual_generated_program_reports_and_globals_are_isolated(tmp_path):
    first = generated_context(tmp_path / "first", 0)
    second = generated_context(tmp_path / "second", 1)
    original_second = copy.deepcopy(second["RUN_REPORT"])
    for context in [first, second]:
        info = figure_runtime.bind(
            context,
            abi=figure_runtime.RUNTIME_ABI,
            source_sha256=figure_runtime.runtime_info()["source_sha256"],
            required=figure_runtime.FUNCTION_NAMES,
        )
        assert info["abi"] == 1
        for name in figure_runtime.FUNCTION_NAMES:
            assert context[name].__globals__ is context
            assert context[name].__code__ is getattr(figure_runtime, name).__code__
    assert first["RUN_REPORT"] is not second["RUN_REPORT"]
    first["finding"]("warning", "isolation_probe", "Only the first figure")
    assert first["RUN_REPORT"]["findings"][-1]["code"] == "isolation_probe"
    assert second["RUN_REPORT"] == original_second
    assert first["new_report"]()["spec"] == json.loads(first["SPEC_JSON"])
    assert second["new_report"]()["spec"] == json.loads(second["SPEC_JSON"])
    assert first["new_report"]()["spec_hash"] != second["new_report"]()["spec_hash"]


@pytest.mark.parametrize(
    "override",
    [
        {"abi": 2},
        {"abi": True},
        {"source_sha256": "0" * 64},
        {"required": ["new_report", "unsupported_capability"]},
        {"required": ["new_report", "new_report"]},
        {"required": []},
    ],
)
def test_incompatible_binding_refuses_before_mutating_program(override):
    context = {"existing": "preserved"}
    request = {
        "abi": figure_runtime.RUNTIME_ABI,
        "source_sha256": figure_runtime.runtime_info()["source_sha256"],
        "required": figure_runtime.FUNCTION_NAMES,
        **override,
    }
    with pytest.raises(RuntimeError, match="Install the exact GraphUnslopify runtime"):
        figure_runtime.bind(context, **request)
    assert context == {"existing": "preserved"}


def test_changed_source_after_import_refuses_without_partial_binding(tmp_path):
    path = tmp_path / "copied_runtime.py"
    path.write_bytes(Path(figure_runtime.__file__).read_bytes())
    spec = importlib.util.spec_from_file_location("copied_figure_runtime", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    imported_sha = module.runtime_info()["source_sha256"]
    path.write_bytes(path.read_bytes() + b"\n# Changed after import\n")
    context = {"existing": "preserved"}
    with pytest.raises(RuntimeError, match="source changed after import"):
        module.bind(context, abi=1, source_sha256=imported_sha, required=module.FUNCTION_NAMES)
    assert context == {"existing": "preserved"}


def actual_components():
    import hashlib

    return {
        name: hashlib.sha256(
            Path(figure_runtime.__file__).parent.joinpath(name).read_bytes()
        ).hexdigest()
        for name in figure_runtime.SOURCE_COMPONENTS
    }


@pytest.mark.parametrize("change", ["missing", "changed", "extra"])
def test_actual_component_mismatches_refuse_atomically(change):
    components = actual_components()
    if change == "missing":
        components.pop("diagnostics.json")
    elif change == "changed":
        components["inspect.py"] = "0" * 64
    else:
        components["invented.py"] = "0" * 64
    context = {"existing": "preserved"}
    with pytest.raises(RuntimeError, match="component"):
        figure_runtime.bind(
            context,
            abi=1,
            source_sha256=figure_runtime.runtime_info()["source_sha256"],
            required=figure_runtime.FUNCTION_NAMES,
            components=components,
        )
    assert context == {"existing": "preserved"}


def test_bound_advice_data_is_isolated_between_actual_generated_contexts(tmp_path):
    contexts = [generated_context(tmp_path / str(i), i) for i in range(2)]
    for context in contexts:
        figure_runtime.bind(
            context,
            abi=1,
            source_sha256=figure_runtime.runtime_info()["source_sha256"],
            required=figure_runtime.FUNCTION_NAMES,
            components=actual_components(),
        )
    first, second = contexts
    before = copy.deepcopy(second["DIAGNOSTIC_ADVICE"])
    first["DIAGNOSTIC_ADVICE"].clear()
    assert second["DIAGNOSTIC_ADVICE"] == before and before
    assert first["UNKNOWN_DIAGNOSTIC"] is not second["UNKNOWN_DIAGNOSTIC"]
