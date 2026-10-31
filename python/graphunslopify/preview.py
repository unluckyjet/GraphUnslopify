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

from .audit import _outputs, _run, _validate_report
from .demo import write_demo
from .describe import profile
from .drafts import InvalidDraft
from .errors import SpecError
from .preview_drafts import PreviewDrafts
from .preview_staging import PreviewStages
from .transport import local_request
from .workbook import EXCEL_SUFFIXES, workbook_sheets


class PreviewState:
    def __init__(
        self,
        root: Path,
        max_upload: int,
        *,
        reuse_renderer: bool = False,
        reuse_translator: bool = False,
        cache_statistics: bool = False,
        staged_preview: bool = False,
        profile_driver: Path | None = None,
    ):
        self.root, self.max_upload = root.resolve(), max_upload
        self.token = secrets.token_urlsafe(32)
        self.uploads: dict[str, dict[str, Any]] = {}
        self.runs: dict[str, dict[str, Any]] = {}
        self.generations: dict[str, int] = {}
        self.lock = threading.Lock()
        self.render_lock = threading.Lock()
        self.drafts = PreviewDrafts(self)
        self.stages = PreviewStages(self.root) if staged_preview else None
        self.worker = None
        self.translator = None
        if reuse_translator:
            from .translator_worker import TranslatorWorker

            self.translator = TranslatorWorker(self.root)
        if reuse_renderer:
            from .preview_worker import RenderWorker

            self.worker = RenderWorker(
                self.root, profile_driver=profile_driver, cache_statistics=cache_statistics
            )

    def close(self):
        if self.stages is not None:
            self.stages.close()
        try:
            if self.worker is not None:
                self.worker.close()
        finally:
            if self.translator is not None:
                self.translator.close()

    def _compiler_request(self, operation, payload=None):
        if self.translator is not None:
            return self.translator.request(operation, payload)
        return local_request(operation, payload), {"mode": "process"}

    def local_request(self, operation, payload=None):
        return self._compiler_request(operation, payload)[0]

    def _run_generated(self, command, folder, timeout):
        return (
            self.worker.run(command, folder, timeout)
            if self.worker is not None
            else _run(command, folder, timeout)
        )

    def upload(self, name: str, content: bytes, *, palette: bool = False) -> dict[str, Any]:
        suffix = Path(name).suffix.lower()
        if suffix not in ({".json"} if palette else {".csv", ".json", ".parquet", *EXCEL_SUFFIXES}):
            raise ValueError(
                "Choose a CSV, regular JSON table, Parquet or Excel workbook"
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
        sheets: list[str] = []
        try:
            path.write_bytes(content)
            if palette:
                value = json.loads(content)
                if not isinstance(value, dict):
                    raise ValueError("Palette lock must be a JSON object")
                details = {"columns": [], "rows": None}
            else:
                sheets = workbook_sheets(path) if suffix in EXCEL_SUFFIXES else []
                if suffix in EXCEL_SUFFIXES and not sheets:
                    raise ValueError("This workbook has no worksheets")
                details = None if len(sheets) > 1 else profile(path)
                if details is not None and not details.get("ok"):
                    raise ValueError(details.get("error", "Could not read this data file"))
            # Validate the response before publishing a usable upload identity.
            json.dumps(details, allow_nan=False)
        except Exception:
            shutil.rmtree(folder)
            raise
        record = {
            "id": identity,
            "path": path,
            "name": Path(name).name,
            "filename": filename,
            "format": "excel" if suffix in EXCEL_SUFFIXES else suffix[1:],
            "palette": palette,
            "profile": details,
            "sheets": sheets,
            "workbook_id": identity if sheets else None,
        }
        with self.lock:
            self.uploads[identity] = record
        return self.upload_info(record)

    @staticmethod
    def upload_info(record: dict[str, Any]) -> dict[str, Any]:
        details = record["profile"]
        return {
            "id": record["id"],
            "name": record["name"],
            "format": record["format"],
            "rows": details.get("rows") if details is not None else None,
            "columns": details.get("columns", []) if details is not None else [],
            "profile": {**details, "path": record["filename"]} if details is not None else None,
            "requires_sheet": details is None,
            "sheets": record.get("sheets", []),
            "workbook_id": record.get("workbook_id"),
        }

    def select_sheet(self, identity: str, sheet: str) -> dict[str, Any]:
        with self.lock:
            source = self.uploads.get(identity)
        if source is None or source["palette"] or source["format"] != "excel":
            raise ValueError("Choose an Excel workbook first")
        if not isinstance(sheet, str) or sheet not in source["sheets"]:
            raise ValueError("Choose one of this workbook's worksheet names")
        details = profile(source["path"], sheet=sheet)
        if not details.get("ok"):
            raise ValueError(details.get("error", "Could not read this worksheet"))
        json.dumps(details, allow_nan=False)
        # A new selection never changes a previous render's input binding.
        record = {**source, "id": uuid.uuid4().hex, "profile": details}
        with self.lock:
            self.uploads[record["id"]] = record
        return self.upload_info(record)

    def selected_data(self, identity: str) -> dict[str, Any]:
        with self.lock:
            data = self.uploads.get(identity)
        if data is None or data["palette"]:
            raise ValueError("Choose a data file first")
        if data["profile"] is None:
            raise ValueError("Choose a worksheet before using this workbook")
        return data

    def prepare(
        self, payload: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]:
        with self.lock:
            palette = self.uploads.get(payload.get("palette_id", ""))
        data = self.selected_data(payload.get("data_id", ""))
        spec = copy.deepcopy(payload.get("spec"))
        if not isinstance(spec, dict):
            raise TypeError("The figure specification must be a JSON object")
        spec["data"] = {
            "path": data["filename"],
            "format": data["format"],
            "columns": [column["name"] for column in data["profile"]["columns"]],
        }
        if data["format"] == "excel":
            spec["data"]["sheet"] = data["profile"]["sheet"]
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
        if payload.get("stage_id") is not None and self.stages is None:
            raise ValueError("Provisional previews are unavailable in this session")
        attempt = (
            self.stages.begin(client, generation, payload.get("stage_id"))
            if self.stages is not None
            else None
        )
        try:
            return self._render(payload, attempt)
        finally:
            if attempt is not None:
                self.stages.finish(attempt)

    def _render(self, payload, attempt):
        client, generation = payload["client"], payload["generation"]
        with self.lock:
            self.generations[client] = max(generation, self.generations.get(client, -1))
        spec, data, palette = self.prepare(payload)
        translated, translation_execution = self._compiler_request("convert", spec)
        answer = {
            "generation": generation,
            "spec": spec,
            "translation": {k: v for k, v in translated.items() if k != "code"},
            "translation_execution": translation_execution,
            "report": None,
            "files": [],
            "run_id": None,
        }
        if translated.get("status") != "translated" or not translated.get("ok"):
            return answer
        with self.render_lock:
            with self.lock:
                if generation != self.generations[client] or (
                    attempt is not None and not self.stages.is_current(attempt)
                ):
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
            provisional = attempt is not None and attempt.ticket is not None
            if provisional:
                self.stages.bind(
                    attempt, folder, stem, payload["data_id"], folder / data["filename"]
                )
            completed = self._run_generated(
                [
                    sys.executable,
                    "-c",
                    (
                        "import os,sys; "
                        "sys.path[:]=[p for p in sys.path if p and "
                        "os.path.normcase(os.path.realpath(p)) != "
                        "os.path.normcase(os.path.realpath(os.getcwd()))]; "
                        f"sys.path.insert(0,{str(Path(__file__).resolve().parent.parent)!r}); "
                        "import runpy; runpy.run_module('graphunslopify.preview_render',run_name='__main__')"
                    ),
                    *(["--provisional"] if provisional else []),
                    "--geometry",
                    f"{stem}.edit-map.json",
                    "--diagnostics",
                    f"{stem}.diagnostic-map.json",
                    "--png",
                    f"{stem}.png",
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
                stale = generation != self.generations[client] or (
                    attempt is not None and not self.stages.is_current(attempt)
                )
            answer.update(
                {
                    "run_id": identity,
                    "report": report,
                    "files": [
                        {"name": name, "format": path.suffix[1:]} for name, path in paths.items()
                    ],
                    "stale": stale,
                    "exit_code": completed.returncode,
                    "execution": getattr(completed, "execution", {"mode": "process"}),
                }
            )
            geometry_path = folder / f"{stem}.edit-map.json"
            geometry = {"available": False, "targets": [], "error": "No PNG geometry was produced"}
            if geometry_path.is_file():
                try:
                    candidate = json.loads(geometry_path.read_text(encoding="utf8"))
                    if not isinstance(candidate, dict):
                        raise TypeError("PNG geometry must be an object")
                    image = next((item for item in exports if item["format"] == "png"), None)
                    if candidate.get("available") and image is not None:
                        if candidate["image"]["sha256"] != image["sha256"]:
                            raise ValueError("Geometry does not describe the current PNG")
                        geometry = {
                            **candidate,
                            "spec_hash": report["spec_hash"],
                            "run_id": identity,
                        }
                    else:
                        geometry["error"] = candidate.get("error", "PNG geometry is unavailable")
                except (OSError, ValueError, KeyError, TypeError) as problem:
                    geometry["error"] = str(problem)
            answer["edit_map"] = geometry
            from .preview_diagnostics import bind_diagnostic_map

            diagnostic_path = folder / f"{stem}.diagnostic-map.json"
            try:
                candidate = json.loads(diagnostic_path.read_text(encoding="utf8"))
            except (OSError, ValueError) as problem:
                candidate = {"schema_version": 1, "available": False, "error": str(problem)}
            if stale:
                candidate = {
                    "schema_version": 1,
                    "available": False,
                    "error": "Diagnostic geometry belongs to a stale render",
                }
            answer["diagnostic_map"] = bind_diagnostic_map(
                candidate,
                folder / f"{stem}.png",
                next((item for item in exports if item["format"] == "png"), None),
                report,
                identity,
            )
            return answer

    def bundle(self, identity: str, include_data: bool) -> bytes:
        from .runtime_bundle import create_bundle

        with self.lock:
            run = self.runs.get(identity)
        if run is None:
            raise ValueError("This preview is no longer available")
        files = {name: path.read_bytes() for name, path in run["files"].items()}
        if run["palette"]:
            files[run["palette"]] = (run["folder"] / run["palette"]).read_bytes()
        script = next(name for name in files if name.endswith(".py"))
        return create_bundle(
            files,
            script=script,
            inputs={run["data"]: (run["folder"] / run["data"]).read_bytes()},
            include_data=include_data,
            reference_outputs=set(run["files"]) - {script},
        )


class PreviewServer(ThreadingHTTPServer):
    # Complete bounded workers before removing the session directory.
    daemon_threads = False

    def __init__(
        self,
        port: int = 0,
        *,
        max_upload_mb: int = 100,
        reuse_renderer: bool = True,
        reuse_translator: bool = True,
        cache_statistics: bool = True,
        staged_preview: bool = True,
    ):
        self.temporary = tempfile.TemporaryDirectory(prefix="gu-preview-")
        self.state = PreviewState(
            Path(self.temporary.name),
            max_upload_mb * 1024 * 1024,
            reuse_renderer=reuse_renderer,
            reuse_translator=reuse_translator,
            cache_statistics=cache_statistics and reuse_renderer,
            staged_preview=staged_preview,
        )
        super().__init__(("127.0.0.1", port), PreviewHandler)

    def server_close(self):
        try:
            super().server_close()
        finally:
            try:
                self.state.close()
            finally:
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
        if not self.allowed(
            token=route
            not in {
                "/",
                "/app.js",
                "/app.css",
                "/controls.js",
                "/diagnostics.js",
                "/text-editing.js",
                "/drafts.js",
                "/diagnostic-overlays.js",
                "/staged-preview.js",
            }
        ):
            self.json({"error": "This local editor request is not authorized"}, 403)
            return
        if route in {
            "/",
            "/app.js",
            "/app.css",
            "/controls.js",
            "/diagnostics.js",
            "/text-editing.js",
            "/drafts.js",
            "/diagnostic-overlays.js",
            "/staged-preview.js",
        }:
            name = {
                "/": "index.html",
                "/app.js": "app.js",
                "/app.css": "app.css",
                "/controls.js": "controls.js",
                "/text-editing.js": "text-editing.js",
                "/diagnostics.js": "diagnostics.js",
                "/drafts.js": "drafts.js",
                "/diagnostic-overlays.js": "diagnostic-overlays.js",
                "/staged-preview.js": "staged-preview.js",
            }[route]
            data = files("graphunslopify").joinpath("web/" + name).read_bytes()
            data = data.replace(b"__PREVIEW_TOKEN__", self.server.state.token.encode())
            self.send(
                data,
                {
                    "index.html": "text/html; charset=utf-8",
                    "app.js": "text/javascript; charset=utf-8",
                    "controls.js": "text/javascript; charset=utf-8",
                    "text-editing.js": "text/javascript; charset=utf-8",
                    "diagnostics.js": "text/javascript; charset=utf-8",
                    "drafts.js": "text/javascript; charset=utf-8",
                    "diagnostic-overlays.js": "text/javascript; charset=utf-8",
                    "staged-preview.js": "text/javascript; charset=utf-8",
                    "app.css": "text/css; charset=utf-8",
                }[name],
            )
            return
        if route == "/api/model-provider":
            self.json(self.server.state.drafts.info())
            return
        if route == "/api/info":
            from .diagnostics import catalog

            info = self.server.state.local_request("info")
            self.json(
                {
                    "kinds": info["kinds"],
                    "recipes": self.server.state.local_request("recipes"),
                    "schema": self.server.state.local_request("schema"),
                    "diagnostics": catalog(),
                    "max_upload_mb": self.server.state.max_upload // 1024 // 1024,
                    "staged_preview": self.server.state.stages is not None,
                }
            )
            return
        parts = route.strip("/").split("/")
        if len(parts) in {2, 3} and parts[0] == "stage":
            try:
                stages = self.server.state.stages
                if stages is None:
                    raise ValueError("Provisional previews are unavailable")
                query = parse_qs(urlsplit(self.path).query)
                client = query.get("client", [""])[0]
                generation = query.get("generation", [""])[0]
                if re.fullmatch("[0-9]{1,32}", generation) is None:
                    raise ValueError("Invalid provisional revision")
                if len(parts) == 2:
                    self.json(stages.poll(parts[1], client, int(generation)))
                elif parts[2] == "png":
                    self.send(
                        stages.image(
                            parts[1], client, int(generation), query.get("attempt", [""])[0]
                        ),
                        "image/png",
                    )
                else:
                    raise ValueError("Unknown provisional output")
            except (ValueError, OSError, TypeError) as problem:
                self.json({"error": str(problem), "verified": False}, 404)
            return
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
            if route == "/api/model-provider":
                self.json(self.server.state.drafts.configure(payload))
            elif route in {
                "/api/draft/disclose",
                "/api/draft/propose",
                "/api/draft/accept",
                "/api/draft/cancel",
            }:
                operation = route.rsplit("/", 1)[-1]
                self.json(getattr(self.server.state.drafts, operation)(payload))
            elif route == "/api/demo":
                demo = self.server.state.root / "demo"
                spec_path = write_demo(demo)
                uploaded = self.server.state.upload(
                    "results.csv", (demo / "results.csv").read_bytes()
                )
                self.json({"data": uploaded, "spec": json.loads(spec_path.read_text())})
            elif route == "/api/suggest":
                data = self.server.state.selected_data(payload.get("data_id", ""))
                self.json(
                    self.server.state.local_request(
                        "suggest", {"profile": {**data["profile"], "path": data["filename"]}}
                    )
                )
            elif route == "/api/select-sheet":
                self.json(
                    self.server.state.select_sheet(payload.get("data_id", ""), payload.get("sheet"))
                )
            elif route in {"/api/validate", "/api/fix"}:
                spec, _, _ = self.server.state.prepare(payload)
                result = (
                    self.server.state.local_request(
                        "fix", {"spec": spec, "code": payload.get("code")}
                    )
                    if route == "/api/fix"
                    else self.server.state.local_request("convert", spec)
                )
                self.json({k: v for k, v in result.items() if k != "code"})
            elif route == "/api/render":
                self.json(self.server.state.render(payload))
            else:
                self.json({"error": "Not found"}, 404)
        except InvalidDraft as problem:
            self.json(
                {
                    "error": str(problem),
                    "invalid_draft": {"envelope": problem.envelope, "problems": problem.problems},
                    "verified": False,
                },
                400,
            )
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
