"""Loopback browser editor using the canonical local compiler and strict renderer."""

from __future__ import annotations

import contextlib
import copy
import hmac
import json
import mimetypes
import os
import re
import secrets
import shutil
import sys
import tempfile
import threading
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit
from zipfile import ZIP_DEFLATED, ZipFile

from .audit import _outputs, _run, _validate_report
from .demo import write_demo
from .describe import profile
from .errors import SpecError
from .transport import local_request


class PreviewState:
    def __init__(self, root: Path, max_upload: int):
        self.root, self.max_upload = root.resolve(), max_upload
        self.token = secrets.token_urlsafe(32)
        self.uploads: dict[str, dict[str, Any]] = {}
        self.runs: dict[str, dict[str, Any]] = {}
        self.generations: dict[str, int] = {}
        self.lock = threading.Lock()
        self.render_lock = threading.Lock()

    def upload(self, name: str, content: bytes, *, palette: bool = False) -> dict[str, Any]:
        suffix = Path(name).suffix.lower()
        if suffix not in ({".json"} if palette else {".csv", ".json", ".parquet"}):
            raise ValueError(
                "Choose a CSV, regular JSON table or Parquet file"
                if not palette
                else "Choose a palette lock JSON file"
            )
        if len(content) > self.max_upload:
            raise ValueError("This file exceeds the configured upload size")
        identity = uuid.uuid4().hex
        folder = self.root / "uploads" / identity
        folder.mkdir(parents=True)
        filename = "palette.lock.json" if palette else "data" + suffix
        path = folder / filename
        path.write_bytes(content)
        if palette:
            value = json.loads(content)
            if not isinstance(value, dict):
                raise ValueError("Palette lock must be a JSON object")
            details = {"columns": [], "rows": None}
        else:
            details = profile(path)
            if not details.get("ok"):
                raise ValueError(details.get("error", "Could not read this data file"))
        record = {
            "id": identity,
            "path": path,
            "name": Path(name).name,
            "filename": filename,
            "format": suffix[1:],
            "palette": palette,
            "profile": details,
        }
        with self.lock:
            self.uploads[identity] = record
        return {
            "id": identity,
            "name": record["name"],
            "format": record["format"],
            "rows": details.get("rows"),
            "columns": details.get("columns", []),
        }

    def prepare(
        self, payload: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]:
        with self.lock:
            data = self.uploads.get(payload.get("data_id", ""))
            palette = self.uploads.get(payload.get("palette_id", ""))
        if data is None or data["palette"]:
            raise ValueError("Choose a data file first")
        spec = copy.deepcopy(payload.get("spec"))
        if not isinstance(spec, dict):
            raise TypeError("The figure specification must be a JSON object")
        spec["data"] = {
            "path": data["filename"],
            "format": data["format"],
            "columns": [column["name"] for column in data["profile"]["columns"]],
        }
        if spec.get("palette_lock"):
            if palette is None or not palette["palette"]:
                raise ValueError("Choose a palette lock JSON file to use palette_lock")
            spec["palette_lock"] = palette["filename"]
        else:
            palette = None
        output = spec.setdefault("output", {})
        if not isinstance(output, dict):
            raise TypeError("output must be an object")
        stem = output.get("stem", "figure")
        if (
            not isinstance(stem, str)
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", stem) is None
            or stem.split(".")[0].upper()
            in {
                "CON",
                "PRN",
                "AUX",
                "NUL",
                *[f"COM{i}" for i in range(1, 10)],
                *[f"LPT{i}" for i in range(1, 10)],
            }
        ):
            raise ValueError(
                "In the local editor, output.stem must be a plain filename (letters, numbers, dot, underscore or dash)"
            )
        requested = output.get("formats", ["png", "svg", "pdf"])
        if (
            not isinstance(requested, list)
            or not requested
            or not all(isinstance(item, str) for item in requested)
        ):
            raise TypeError("output.formats must be an array")
        output["formats"] = list(dict.fromkeys([*requested, "png"]))
        return spec, data, palette

    def render(self, payload: dict[str, Any]) -> dict[str, Any]:
        client, generation = payload.get("client"), payload.get("generation")
        if (
            not isinstance(client, str)
            or not 1 <= len(client) <= 128
            or type(generation) is not int
            or generation < 0
        ):
            raise ValueError("Invalid preview revision")
        with self.lock:
            self.generations[client] = max(generation, self.generations.get(client, -1))
        spec, data, palette = self.prepare(payload)
        translated = local_request("convert", spec)
        answer = {
            "generation": generation,
            "spec": spec,
            "translation": {k: v for k, v in translated.items() if k != "code"},
            "report": None,
            "files": [],
            "run_id": None,
        }
        if translated.get("status") != "translated" or not translated.get("ok"):
            return answer
        with self.render_lock:
            with self.lock:
                if generation != self.generations[client]:
                    return {"generation": generation, "stale": True}
            identity = uuid.uuid4().hex
            folder = self.root / "runs" / identity
            folder.mkdir(parents=True)
            try:
                os.link(data["path"], folder / data["filename"])
            except OSError:
                shutil.copyfile(data["path"], folder / data["filename"])
            if palette:
                shutil.copyfile(palette["path"], folder / palette["filename"])
            stem = spec.get("output", {}).get("stem", "figure")
            script = folder / f"{stem}.py"
            script.write_text(translated["code"], encoding="utf8")
            completed = _run(
                [
                    sys.executable,
                    str(script),
                    "--strict",
                    "--json",
                    "--report",
                    f"{stem}.report.json",
                ],
                folder,
                120,
            )
            (folder / "render.log").write_text(completed.stderr, encoding="utf8")
            try:
                report = json.loads(completed.stdout)
            except json.JSONDecodeError as problem:
                detail = completed.stderr.strip().splitlines()
                raise ValueError(
                    detail[-1] if detail else "Renderer did not produce a report"
                ) from problem
            _validate_report(report)
            exports = (
                _outputs(report, folder, folder, require_all=False) if report.get("outputs") else []
            )
            expected = set(report["spec"]["output"]["formats"])
            if report["spec"]["output"].get("interactive"):
                expected.add("html")
            if report["spec"].get("animate"):
                expected.add(report["spec"]["animate"].get("format", "gif"))
            missing = expected - {item["format"] for item in exports}
            answer["export_errors"] = (
                ["Requested exports were not produced: " + ", ".join(sorted(missing))]
                if missing
                else []
            )
            spec_name = f"{stem}.figure.json"
            (folder / spec_name).write_text(json.dumps(report["spec"], indent=2), encoding="utf8")
            paths = {item["path"]: folder / item["path"] for item in exports}
            for name in (script.name, spec_name, f"{stem}.report.json"):
                paths[name] = folder / name
            record = {
                "folder": folder,
                "files": paths,
                "data": data["filename"],
                "palette": palette["filename"] if palette else None,
            }
            with self.lock:
                self.runs[identity] = record
                stale = generation != self.generations[client]
            answer.update(
                {
                    "run_id": identity,
                    "report": report,
                    "files": [
                        {"name": name, "format": path.suffix[1:]} for name, path in paths.items()
                    ],
                    "stale": stale,
                    "exit_code": completed.returncode,
                }
            )
            return answer

    def bundle(self, identity: str, include_data: bool) -> bytes:
        with self.lock:
            run = self.runs.get(identity)
        if run is None:
            raise ValueError("This preview is no longer available")
        import io

        buffer = io.BytesIO()
        with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
            for name, path in run["files"].items():
                archive.write(path, name)
            if run["palette"]:
                archive.write(run["folder"] / run["palette"], run["palette"])
            if include_data:
                archive.write(run["folder"] / run["data"], run["data"])
        return buffer.getvalue()


class PreviewServer(ThreadingHTTPServer):
    # Complete bounded workers before removing the session directory.
    daemon_threads = False

    def __init__(self, port: int = 0, *, max_upload_mb: int = 100):
        self.temporary = tempfile.TemporaryDirectory(prefix="gu-preview-")
        self.state = PreviewState(Path(self.temporary.name), max_upload_mb * 1024 * 1024)
        super().__init__(("127.0.0.1", port), PreviewHandler)

    def server_close(self):
        super().server_close()
        self.temporary.cleanup()


class PreviewHandler(BaseHTTPRequestHandler):
    server: PreviewServer
    timeout = 15

    def log_message(self, format, *args):
        pass

    def send(
        self, data: bytes, content_type: str, status: int = 200, *, download: str | None = None
    ):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'",
        )
        if download:
            self.send_header("Content-Disposition", f'attachment; filename="{download}"')
        self.end_headers()
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):
            self.wfile.write(data)

    def json(self, value: Any, status: int = 200):
        self.send(
            json.dumps(value, ensure_ascii=True, allow_nan=False).encode("utf8"),
            "application/json",
            status,
        )

    def allowed(self, *, token: bool = True) -> bool:
        port = self.server.server_address[1]
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host") not in hosts:
            return False
        origin = self.headers.get("Origin")
        if origin and origin not in {"http://" + host for host in hosts}:
            return False
        supplied = self.headers.get(
            "X-Preview-Token", parse_qs(urlsplit(self.path).query).get("token", [""])[0]
        )
        return not token or hmac.compare_digest(supplied, self.server.state.token)

    def do_GET(self):
        route = urlsplit(self.path).path
        if not self.allowed(token=route not in {"/", "/app.js", "/app.css", "/controls.js"}):
            self.json({"error": "This local editor request is not authorized"}, 403)
            return
        if route in {"/", "/app.js", "/app.css", "/controls.js"}:
            name = {
                "/": "index.html",
                "/app.js": "app.js",
                "/app.css": "app.css",
                "/controls.js": "controls.js",
            }[route]
            data = files("graphunslopify").joinpath("web/" + name).read_bytes()
            data = data.replace(b"__PREVIEW_TOKEN__", self.server.state.token.encode())
            self.send(
                data,
                {
                    "index.html": "text/html; charset=utf-8",
                    "app.js": "text/javascript; charset=utf-8",
                    "controls.js": "text/javascript; charset=utf-8",
                    "app.css": "text/css; charset=utf-8",
                }[name],
            )
            return
        if route == "/api/info":
            info = local_request("info")
            self.json(
                {
                    "kinds": info["kinds"],
                    "recipes": local_request("recipes"),
                    "schema": local_request("schema"),
                    "max_upload_mb": self.server.state.max_upload // 1024 // 1024,
                }
            )
            return
        parts = route.strip("/").split("/")
        if len(parts) == 3 and parts[0] == "artifact":
            run = self.server.state.runs.get(parts[1])
            path = run["files"].get(unquote(parts[2])) if run else None
            if path and path.is_file():
                self.send(
                    path.read_bytes(),
                    mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                    download=path.name
                    if "download" in parse_qs(urlsplit(self.path).query)
                    else None,
                )
                return
        if len(parts) == 2 and parts[0] == "bundle":
            try:
                content = self.server.state.bundle(
                    parts[1], parse_qs(urlsplit(self.path).query).get("data") == ["true"]
                )
                self.send(content, "application/zip", download="figure-bundle.zip")
            except ValueError as problem:
                self.json({"error": str(problem)}, 404)
            return
        self.json({"error": "Not found"}, 404)

    def do_POST(self):
        if not self.allowed():
            self.json({"error": "This local editor request is not authorized"}, 403)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size <= 0 or size > self.server.state.max_upload:
                raise ValueError("The request exceeds the configured upload size or is empty")
            body = self.rfile.read(size)
            route = urlsplit(self.path).path
            if route == "/api/upload":
                self.json(
                    self.server.state.upload(
                        unquote(self.headers.get("X-Filename", "data.csv")),
                        body,
                        palette=self.headers.get("X-Palette") == "true",
                    )
                )
                return
            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise TypeError("Request must be a JSON object")
            if route == "/api/demo":
                demo = self.server.state.root / "demo"
                spec_path = write_demo(demo)
                uploaded = self.server.state.upload(
                    "results.csv", (demo / "results.csv").read_bytes()
                )
                self.json({"data": uploaded, "spec": json.loads(spec_path.read_text())})
            elif route == "/api/suggest":
                data = self.server.state.uploads.get(payload.get("data_id", ""))
                if data is None or data["palette"]:
                    raise ValueError("Choose a data file first")
                self.json(
                    local_request(
                        "suggest", {"profile": {**data["profile"], "path": data["filename"]}}
                    )
                )
            elif route in {"/api/validate", "/api/fix"}:
                spec, _, _ = self.server.state.prepare(payload)
                result = (
                    local_request("fix", {"spec": spec, "code": payload.get("code")})
                    if route == "/api/fix"
                    else local_request("convert", spec)
                )
                self.json({k: v for k, v in result.items() if k != "code"})
            elif route == "/api/render":
                self.json(self.server.state.render(payload))
            else:
                self.json({"error": "Not found"}, 404)
        except (OSError, ValueError, TypeError, KeyError, SpecError) as problem:
            self.json({"error": str(problem)}, 400)
        except Exception as problem:  # noqa: BLE001 -- surface worker failures without killing the editor
            self.json({"error": f"Could not render this figure: {problem}"}, 500)


def serve_preview(port: int = 8787, *, open_browser: bool = False, max_upload_mb: int = 100):
    if not 0 <= port <= 65535:
        raise ValueError("Port must be between 0 and 65535")
    if max_upload_mb <= 0:
        raise ValueError("Upload limit must be positive")
    with PreviewServer(port, max_upload_mb=max_upload_mb) as server:
        url = f"http://127.0.0.1:{server.server_address[1]}"
        print(json.dumps({"url": url}), flush=True)
        if open_browser:
            webbrowser.open(url)
        with contextlib.suppress(KeyboardInterrupt):
            server.serve_forever()
