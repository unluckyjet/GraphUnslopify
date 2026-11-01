"""Independent task gates must distinguish plausible plots from the requested task."""

from __future__ import annotations

import copy
import json
import runpy
import shutil
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "benchmarks/workspace"
BASELINE = runpy.run_path(str(HERE / "matplotlib_producer.py"))
GRAPH = runpy.run_path(str(HERE / "graphunslopify_producer.py"))
EVALUATE = runpy.run_path(str(HERE / "evaluation.py"))["evaluate"]
TRUTH = json.loads((HERE / "ground-truth.json").read_text(encoding="utf8"))


@pytest.fixture(scope="module")
def native_fixture(tmp_path_factory):
    spec = json.loads((HERE / "figures/iris-scatter-mm.json").read_text(encoding="utf8"))
    spec["output"].update(size="single_column", dpi=144)
    session = BASELINE["Session"](tmp_path_factory.mktemp("task-evaluation") / "owned")
    result = session.render(spec, HERE / "figures", "original")
    return spec, result, session.root / "runs/original"


def test_actual_mm_values_with_cm_labels_are_not_task_correct(tmp_path, native_fixture):
    spec, _, _ = native_fixture
    wrong = copy.deepcopy(spec)
    wrong["x"]["unit"] = wrong["y"]["unit"] = "cm"
    session = BASELINE["Session"](tmp_path / "owned")
    result = session.render(wrong, HERE / "figures", "wrong-authored-units")
    assert result["status"] == "passed"  # The author supplied the unit declaration.
    proof = EVALUATE(
        result,
        session.root / "runs/wrong-authored-units",
        spec,
        HERE / "figures",
        TRUTH["iris-scatter-mm"],
    )
    assert not proof["task_correct_verified"]
    assert "required_labels_or_units:png" in proof["errors"]


def test_same_pixels_with_changed_dpi_are_not_the_requested_export(tmp_path, native_fixture):
    spec, original, folder = native_fixture
    shutil.copytree(folder, tmp_path / "copy")
    path = tmp_path / "copy/figure.png"
    with Image.open(path) as image:
        image.save(path, dpi=(72, 72))
    result = copy.deepcopy(original)
    result["outputs"]["figure.png"] = BASELINE["digest"](path.read_bytes())
    proof = EVALUATE(result, path.parent, spec, HERE / "figures", TRUTH["iris-scatter-mm"])
    assert not proof["task_correct_verified"] and "actual_dpi" in proof["errors"]
    assert "actual_width:png" in proof["errors"]


def test_two_unknown_svg_identities_cannot_bind_a_changed_export(tmp_path, native_fixture):
    spec, original, folder = native_fixture
    shutil.copytree(folder, tmp_path / "copy")
    path = tmp_path / "copy/figure.svg"
    tree = ET.fromstring(path.read_bytes())
    style = next(tree.iter("{http://www.w3.org/2000/svg}style"))
    style.text = (style.text or "") + " path {fill:red}"
    path.write_bytes(ET.tostring(tree))
    result = copy.deepcopy(original)
    result["outputs"]["figure.svg"] = BASELINE["digest"](path.read_bytes())
    next(e for e in result["save_observations"] if e["format"] == "svg")["graphic_identity"] = None
    proof = EVALUATE(result, path.parent, spec, HERE / "figures", TRUTH["iris-scatter-mm"])
    assert "original_save_binding:svg" in proof["errors"]


def test_real_preflight_refusal_has_no_native_exit_report_or_saved_figure(tmp_path):
    spec = json.loads((HERE / "figures/penguins-absent-reference.json").read_text(encoding="utf8"))
    session = GRAPH["Session"](tmp_path / "owned")
    try:
        result = session.render(spec, HERE / "figures", "absent-reference")
        assert result["native_exit_code"] is None and not result["native_report_present"]
        assert result["exit_code_source"] == "adapter_strict_refusal_classification"
        assert not list(session.folder("absent-reference").glob("figure.*"))
        proof = EVALUATE(
            result,
            session.folder("absent-reference"),
            spec,
            HERE / "figures",
            TRUTH["penguins-absent-reference"],
        )
        assert proof["correct_refusal_without_native_report"] and not proof["task_correct_verified"]
    finally:
        session.close()


def test_observational_hook_preserves_actual_native_program_and_pixels(tmp_path):
    spec = json.loads((HERE / "figures/iris-scatter.json").read_text(encoding="utf8"))
    spec["output"].update(size="single_column", dpi=144, formats=["png"])
    observed = GRAPH["Session"](tmp_path / "observed")
    from graphunslopify.preview import PreviewState

    plain_root = tmp_path / "plain"
    plain_root.mkdir()
    plain = PreviewState(
        plain_root,
        1000000,
        reuse_renderer=True,
        reuse_translator=True,
        cache_statistics=True,
        staged_preview=True,
    )
    try:
        first = observed.render(spec, HERE / "figures", "observed")
        data = (HERE / "figures" / spec["data"]["path"]).read_bytes()
        uploaded = plain.upload("iris.csv", data)
        second = plain.render(
            {
                "client": "control",
                "generation": 1,
                "stage_id": uuid.uuid4().hex,
                "data_id": uploaded["id"],
                "spec": spec,
            }
        )
        actual = plain.runs[second["run_id"]]["folder"]
        assert (observed.folder("observed") / "figure.py").read_bytes() == (
            actual / "figure.py"
        ).read_bytes()
        graphic = BASELINE["MEASUREMENT"]["graphic_identity"]
        assert graphic((observed.folder("observed") / "figure.png").read_bytes(), "png") == graphic(
            (actual / "figure.png").read_bytes(), "png"
        )
        assert first["status"] == second["report"]["status"]
    finally:
        observed.close()
        plain.close()
