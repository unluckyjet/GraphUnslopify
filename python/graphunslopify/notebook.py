"""Copy and optionally execute the packaged public notebook example."""

from __future__ import annotations

import sys
from importlib.resources import files
from pathlib import Path
from typing import Any

from .errors import SpecError


def execute_notebook(path: str | Path) -> dict[str, Any]:
    import nbformat
    from nbclient import NotebookClient

    source = Path(path).resolve()
    notebook = nbformat.read(source, as_version=4)
    client = NotebookClient(
        notebook,
        timeout=120,
        kernel_name="python3",
        resources={"metadata": {"path": str(source.parent)}},
    )
    # Use the current environment without changing any installed user kernel specs.
    client.km = client.create_kernel_manager()
    client.km.kernel_spec.argv = [
        sys.executable,
        "-m",
        "ipykernel_launcher",
        "-f",
        "{connection_file}",
    ]
    try:
        client.execute()
    except Exception as problem:
        raise SpecError(f"Notebook execution failed: {problem}") from problem
    finally:
        nbformat.write(notebook, source)
    images = sum(
        "image/png" in output.get("data", {})
        for cell in notebook.cells
        for output in cell.get("outputs", [])
    )
    return {
        "path": str(source),
        "executed": True,
        "cells": len(notebook.cells),
        "image_outputs": images,
    }


def create_notebook(path: str | Path, *, execute: bool = False) -> dict[str, Any]:
    destination = Path(path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    resource = files("graphunslopify").joinpath("examples/quickstart.ipynb")
    with destination.open("x", encoding="utf8") as handle:
        handle.write(resource.read_text(encoding="utf8"))
    return (
        execute_notebook(destination) if execute else {"path": str(destination), "executed": False}
    )
