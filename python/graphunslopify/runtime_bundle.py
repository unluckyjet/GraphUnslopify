"""Archive actual runtime source, figure files and explicit external requirements."""

from __future__ import annotations

import ast
import hashlib
import importlib.metadata
import io
import json
import platform
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile

from . import figure_runtime

_PREFIX = "_graphunslopify"
_CORE_REQUIREMENTS = {
    "matplotlib": ">=3.9",
    "pandas": ">=2.0",
    "numpy": ">=1.24",
    "pillow": ">=9",
    "pypdf": ">=5",
    "typing_extensions": ">=4.4",
    "jsonschema": ">=4",
}
_OPTIONAL_REQUIREMENTS = {
    "scipy": ("scipy", ">=1.11"),
    "plotly": ("plotly", ">=5.24"),
    "pyarrow": ("pyarrow", ">=15"),
    "python_calamine": ("python-calamine", ">=0.3.1"),
}


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _name(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or value == "."
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in value
        or ":" in value
        or str(path) != value
    ):
        raise ValueError("Bundle entries must use plain relative POSIX paths")
    return value


def _requirements(program: bytes, spec: dict) -> tuple[str, dict]:
    tree = ast.parse(program)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            imports.add(node.module.split(".")[0])
    requirements = dict(_CORE_REQUIREMENTS)
    for module, (distribution, floor) in _OPTIONAL_REQUIREMENTS.items():
        if module in imports:
            requirements[distribution] = floor
    if spec.get("data", {}).get("format") == "parquet":
        requirements["pyarrow"] = ">=15"
    if spec.get("data", {}).get("format") == "excel":
        requirements.update({"pandas": ">=2.2", "python-calamine": ">=0.3.1"})
    installed = {}
    for name in requirements:
        try:
            installed[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            installed[name] = None
    environment = {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.system(),
        "machine": platform.machine(),
        "observed_distribution_versions": installed,
        "scope": "Exporter environment; availability does not establish every package was used.",
    }
    return "\n".join(
        name + floor for name, floor in sorted(requirements.items())
    ) + "\n", environment


def _runtime_files() -> dict[str, bytes]:
    root = Path(__file__).parent
    result = {}
    for path in root.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        relative = path.relative_to(root)
        if any(part.startswith(".") for part in relative.parts):
            continue
        if (
            len(relative.parts) == 1
            and (
                path.suffix == ".py"
                or path.name
                in {
                    "_translator.mjs",
                    "diagnostics.json",
                    "LICENSE.txt",
                    "ZOD-LICENSE.txt",
                }
            )
        ) or relative.parts[0] in {"schemas", "web", "examples"}:
            result[f"{_PREFIX}/runtime/graphunslopify/{relative.as_posix()}"] = path.read_bytes()
    if f"{_PREFIX}/runtime/graphunslopify/LICENSE.txt" not in result:
        raise ValueError("Runtime license is missing; rebuild/install the complete distribution")
    return result


def create_bundle(
    files: dict[str, bytes],
    *,
    script: str,
    inputs: dict[str, bytes],
    include_data: bool = True,
    reference_outputs: set[str] | None = None,
) -> bytes:
    """Create a reproducible source archive; rendering/verification is a separate step.

    Input bytes are always fingerprinted. With include_data=False the archive
    states that the user must supply those exact files before reproduction.
    No private session sidecars or surrounding directories are traversed.
    """
    script = _name(script)
    entries = {_name(name): raw for name, raw in files.items()}
    if any(name == _PREFIX or name.startswith(_PREFIX + "/") for name in entries):
        raise ValueError("Figure files cannot use the reserved runtime folder")
    if script not in entries:
        raise ValueError("Bundle has no actual generated program")
    tree = ast.parse(entries[script])
    constants = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in {"EXPECTED_RUNTIME", "SPEC_JSON"}
    }
    if "EXPECTED_RUNTIME" not in constants:
        raise ValueError("Regenerate the figure with the current versioned runtime before bundling")
    expected = constants["EXPECTED_RUNTIME"]
    if not isinstance(expected, dict):
        raise TypeError("The figure's runtime expectation must be an object")
    # The same canonical binding validates actual component source/capabilities.
    figure_runtime.bind({}, **expected)
    spec = json.loads(constants["SPEC_JSON"])
    spec_path = _name(spec["output"]["stem"] + ".figure.json")
    entries[spec_path] = (json.dumps(spec, indent=2, ensure_ascii=False) + "\n").encode()
    requirements, environment = _requirements(entries[script], spec)
    input_info = []
    for input_name, raw in inputs.items():
        name = _name(input_name)
        if name in (_PREFIX, script) or name.startswith(_PREFIX + "/"):
            raise ValueError("Input cannot replace runtime or generated program")
        input_info.append(
            {"path": name, "sha256": _sha(raw), "bytes": len(raw), "included": include_data}
        )
        if include_data:
            entries[name] = raw
        else:
            entries.pop(name, None)
    runtime_files = _runtime_files()
    for name, digest in expected["components"].items():
        raw = runtime_files.get(f"{_PREFIX}/runtime/graphunslopify/{name}")
        if raw is None or _sha(raw) != digest:
            raise RuntimeError("The archived runtime changed; regenerate the figure and bundle")
    entries.update(runtime_files)
    reference_outputs = set(reference_outputs or ()) | {spec_path}
    if not reference_outputs.issubset(entries):
        raise ValueError("Reference outputs must name actual archived files")
    if reference_outputs & ({script} | set(inputs)) or any(
        name.startswith(_PREFIX + "/") for name in reference_outputs
    ):
        raise ValueError("Runtime/program/input files cannot be mutable reference outputs")
    entries[f"{_PREFIX}/requirements.txt"] = requirements.encode()
    entries[f"{_PREFIX}/environment.json"] = (json.dumps(environment, indent=2) + "\n").encode()
    pinned = []
    for line in requirements.strip().splitlines():
        name, floor = line.split(">=", 1)
        version = environment["observed_distribution_versions"].get(name)
        pinned.append(name + ("==" + version if version else ">=" + floor))
    # Preserve unknown versions as actual declared floors, not invented pins.
    entries[f"{_PREFIX}/requirements-observed.txt"] = (
        "# Observed exporter versions; use the recorded Python version for this environment.\n"
        + "\n".join(pinned)
        + "\n"
    ).encode()
    launcher = "reproduce.py"
    while launcher in entries:
        launcher = "_" + launcher
    entries[launcher] = _LAUNCHER.encode()
    instructions = "REPRODUCE.md"
    while instructions in entries:
        instructions = "_" + instructions
    entries[instructions] = (
        "# Reproduce this figure\n\n"
        f"Use Python 3.10+ with the scientific dependencies in `{_PREFIX}/requirements.txt`. "
        "The exact observed exporter environment is recorded separately; cross-version pixels may differ.\n\n"
        f"```sh\npython -m pip install -r {_PREFIX}/requirements.txt\npython {launcher} --json\n```\n\n"
        "GraphUnslopify's actual source runtime, inspection and licenses are included; "
        "no GraphUnslopify package installation or checkout is required. Third-party libraries "
        "are external dependencies, not vendored. MP4 outputs additionally need ffmpeg. "
        "Custom system fonts must also be available.\n\n"
        "The launcher checks immutable program/runtime files and original inputs before executing the "
        "program with its original strict policy. Missing or modified input is rejected. "
        "Archived reference outputs have recorded hashes and are replaced by actual rerendering. "
        "A source archive is not a successful scientific verification result: run it and "
        "inspect its actual report/exit code. Integrity hashes do not authenticate authorship.\n"
    ).encode()
    manifest = {
        "schema_version": 1,
        "script": script,
        "launcher": launcher,
        "instructions": instructions,
        "runtime": expected,
        "inputs": input_info,
        "files": {
            name: {"sha256": _sha(raw), "bytes": len(raw)} for name, raw in sorted(entries.items())
        },
        "immutable_files": sorted(set(entries) - reference_outputs),
        "reference_outputs": sorted(reference_outputs),
    }
    entries[f"{_PREFIX}/manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    stream = io.BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
        for name, raw in sorted(entries.items()):
            archive.writestr(name, raw)
    return stream.getvalue()


_LAUNCHER = '''"""Run the archived figure with its actual included scientific runtime."""
import hashlib
import json
import os
import runpy
import sys
from pathlib import Path, PurePosixPath

root = Path(__file__).resolve().parent
manifest = json.loads((root / "_graphunslopify/manifest.json").read_text(encoding="utf8"))
def checked_path(name):
    relative = PurePosixPath(name)
    if relative.is_absolute() or ".." in relative.parts or "\\\\" in name or ":" in name:
        raise RuntimeError("Invalid archived file path")
    path = root.joinpath(*relative.parts).resolve()
    if not path.is_relative_to(root):
        raise RuntimeError("Archived file escapes the bundle")
    return path
for name in manifest["immutable_files"]:
    expected = manifest["files"][name]
    path = checked_path(name)
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected["sha256"]:
        raise RuntimeError("Missing or modified archived file: " + name)
for expected in manifest["inputs"]:
    path = checked_path(expected["path"])
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected["sha256"]:
        raise RuntimeError("Supply the original unchanged input: " + expected["path"])
if "graphunslopify" in sys.modules:
    raise RuntimeError("Run this bundle in a fresh Python process")
sys.path.insert(0, str(root / "_graphunslopify/runtime"))
os.chdir(root)
runpy.run_path(str(checked_path(manifest["script"])), run_name="__main__")
'''
