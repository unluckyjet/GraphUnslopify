"""The local translator is the default. HTTP requires an explicit selection."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from importlib.resources import as_file, files
from typing import Any

from .errors import SpecError

DEFAULT_API = "https://json-translator-three.vercel.app"


def _node_command() -> list[str]:
    override = os.environ.get("GRAPHUNSLOPIFY_NODE")
    if override:
        return [override]
    if importlib.util.find_spec("nodejs_wheel") is not None:
        return [sys.executable, "-m", "nodejs_wheel"]
    # Useful for source development; normal wheels depend on the bundled runtime.
    if executable := shutil.which("node"):
        return [executable]
    raise SpecError("Node runtime is missing; reinstall graphunslopify with its dependencies")


def local_request(operation: str, payload: Any = None) -> Any:
    """Run the shipped emitter without contacting a network service."""
    resource = files("graphunslopify").joinpath("_translator.mjs")
    with as_file(resource) as bundle:
        if not bundle.is_file():
            raise SpecError(
                "Local translator is missing; source developers run npm run build:translator"
            )
        try:
            completed = subprocess.run(
                [*_node_command(), str(bundle)],
                input=json.dumps({"operation": operation, "payload": payload}),
                capture_output=True,
                text=True,
                encoding="utf8",
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as problem:
            raise SpecError(f"could not run the local translator: {problem}") from problem
    try:
        response = json.loads(completed.stdout)
    except json.JSONDecodeError as problem:
        raise SpecError(f"local translator returned no JSON: {completed.stderr[:400]}") from problem
    if completed.returncode or not response.get("ok"):
        raise SpecError(response.get("error", completed.stderr[:400]))
    return response["result"]


def post(path: str, payload: dict[str, Any], api: str | None = None) -> Any:
    selected = api if api is not None else os.environ.get("GRAPHUNSLOPIFY_API", "local")
    if selected == "local":
        operations = {"/api/convert": "convert", "/api/suggest": "suggest"}
        if path not in operations:
            raise SpecError(f"unsupported local endpoint: {path}")
        return local_request(operations[path], payload)
    if not selected.startswith(("http://", "https://")):
        raise SpecError("translator must be 'local' or an explicit http(s) URL")
    request = urllib.request.Request(
        f"{selected.rstrip('/')}{path}",
        data=json.dumps(payload).encode("utf8"),
        headers={"content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.loads(response.read().decode("utf8"))
    except urllib.error.HTTPError as problem:
        detail = problem.read().decode("utf8", errors="replace")
        try:
            return json.loads(detail)
        except json.JSONDecodeError:
            raise SpecError(f"{problem.code} from {path}: {detail[:400]}") from problem
    except urllib.error.URLError as problem:
        raise SpecError(f"could not reach {selected}: {problem.reason}") from problem
