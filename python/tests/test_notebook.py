"""Execute the packaged notebook through a real kernel in the active environment."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from graphunslopify.notebook import create_notebook


def test_packaged_notebook_copies_and_refuses_overwrite(tmp_path):
    destination = tmp_path / "quickstart.ipynb"
    result = create_notebook(destination)
    assert result["executed"] is False
    canonical = Path(__file__).resolve().parents[2] / "examples/quickstart.ipynb"
    assert destination.read_bytes() == canonical.read_bytes()
    with pytest.raises(FileExistsError):
        create_notebook(destination)


def test_notebook_executes_plots_and_expected_rejection(tmp_path, monkeypatch):
    pytest.importorskip("nbclient")
    pytest.importorskip("ipykernel")
    monkeypatch.setenv("GRAPHUNSLOPIFY_API", "http://127.0.0.1:9")
    destination = tmp_path / "executed.ipynb"
    result = create_notebook(destination, execute=True)
    assert result["image_outputs"] == 1
    notebook = json.loads(destination.read_text())
    code_cells = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]
    assert all(cell["execution_count"] is not None for cell in code_cells)
    assert all(
        output["output_type"] != "error" for cell in code_cells for output in cell["outputs"]
    )
    texts = " ".join(
        output.get("text", "")
        if isinstance(output.get("text", ""), str)
        else "".join(output["text"])
        for cell in code_cells
        for output in cell["outputs"]
    )
    assert "Expected rejection: the reversed claim fails." in texts
    assert sys.executable in texts
