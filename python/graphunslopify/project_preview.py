"""One local interface for a paper's definitions, shared intent and audit history."""

from __future__ import annotations

import base64
import contextlib
import copy
import json
import math
import mimetypes
import re
import secrets
import tempfile
import threading
import webbrowser
from http.server import ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .comparison import _explain, _metrics, _png_bytes, _preview, _select, _verified_bytes
from .errors import SpecError
from .preview import PreviewHandler
from .project import (
    MAX_SOURCE_BYTES,
    ProjectError,
    _config,
    _inside,
    _owner,
    _read,
    _review_token,
    _shared_schema,
    project_figure,
    project_history,
    project_status,
    run_project,
    set_project_entry,
    set_project_figure,
    set_project_shared,
)
from .transport import local_request


class ProjectState:
    def __init__(self, path):
        self.source, config = _config(path)
        self.project_id = config["project_id"]
        self.token = secrets.token_urlsafe(32)
        self.job_lock = threading.Lock()
        self.media_lock = threading.Lock()
        self.worker = None
        self.job = None
        self.closing = False

    def check_owner(self):
        if _owner(self.source.parent)["project_id"] != self.project_id:
            raise ProjectError(
                "Project ownership changed; close this workspace and reopen the intended project."
            )

    def job_info(self):
        with self.job_lock:
            return copy.deepcopy(self.job)

    def snapshot(self):
        self.check_owner()
        history = project_history(self.source)
        try:
            state = project_status(self.source)
        except (OSError, ValueError, KeyError, TypeError, SpecError) as problem:
            state = {
                "status": "unavailable",
                "revision": None,
                "figures": [],
                "shared": {},
                "error": str(problem),
            }
        state["history"] = [
            {
                key: event.get(key)
                for key in ("id", "action", "created_at", "phase", "integrity", "errors")
            }
            | {
                "status": event.get("result", {}).get("status"),
                "exit_code": event.get("result", {}).get("exit_code"),
            }
            for event in history["events"]
        ]
        state["history_integrity"] = history["integrity"]
        state["project_name"] = self.source.parent.parent.name
        state["job"] = self.job_info()
        return state

    def event(self, identity):
        self.check_owner()
        found = next(
            (x for x in project_history(self.source)["events"] if x["id"] == identity), None
        )
        if not found or not found["integrity"]:
            raise ProjectError(
                "Choose an intact completed history event; incomplete or changed evidence cannot be presented as a completed result."
            )
        return found

    def audit_root(self, event):
        return _inside(self.source.parent, "history/" + event["id"] + "/audit")

    @staticmethod
    def audited(event, identity):
        found = next(
            (
                x
                for x in (event["result"].get("audit") or {}).get("figures", [])
                if x["id"] == identity
            ),
            None,
        )
        if not found:
            raise ProjectError("This figure has no execution evidence in the selected event.")
        return found

    def saved_source(self, event_id, identity):
        event = self.event(event_id)
        root = _inside(self.source.parent, "history/" + event["id"])
        manifest = _read(_inside(root, "source/manifest.json"))
        index = next(
            (i for i, item in enumerate(manifest["figures"]) if item["id"] == identity), None
        )
        if index is None:
            raise ProjectError("This figure is not in the source captured for this event.")
        entry = manifest["figures"][index]
        if "spec" in entry and isinstance(entry["spec"], dict):
            text = json.dumps(entry["spec"], indent=2)
        else:
            name = f"source/{index:04d}." + ("py" if "script" in entry else "json")
            if name not in {item["path"] for item in event["files"]}:
                raise ProjectError("The original source was unavailable in this event.")
            text = _inside(root, name).read_text(encoding="utf8")
        return {
            "text": text,
            "entry": entry,
            "context": "Source used by this audit"
            if event["action"] == "run"
            else "Source before this change",
        }

    def artifact(self, event_id, identity, index):
        event = self.event(event_id)
        figure = self.audited(event, identity)
        if not 0 <= index < len(figure["outputs"]):
            raise ProjectError("Choose a recorded export from this figure.")
        item = figure["outputs"][index]
        root = self.audit_root(event)
        _inside(root, item["path"])
        name = re.sub(r"[^a-zA-Z0-9_.-]", "_", Path(item["path"]).name)
        return _verified_bytes(item, [root]), name

    def preview(self, event_id, identity):
        with self.media_lock, tempfile.TemporaryDirectory(prefix="gu-project-image-") as temporary:
            event = self.event(event_id)
            figure = self.audited(event, identity)
            _, item = _select(None, figure)
            if item:
                _inside(self.audit_root(event), item["path"])
            record, _ = _preview(item, [self.audit_root(event)], Path(temporary), "figure")
            if record["status"] != "available":
                raise ProjectError(
                    record.get(
                        "reason", "No static preview is available; use the recorded exports."
                    )
                )
            preview = record["preview"]
            return _verified_bytes(preview, [Path(temporary)]), preview["mime"]

    def comparison(self, event_id, identity):
        with (
            self.media_lock,
            tempfile.TemporaryDirectory(prefix="gu-project-comparison-") as temporary,
        ):
            event = self.event(event_id)
            if not event["result"].get("baseline"):
                return {"available": False, "reason": "This run has no baseline audit."}
            baseline = self.event(event["result"]["baseline"])
            before = next(
                (
                    x
                    for x in (baseline["result"].get("audit") or {}).get("figures", [])
                    if x["id"] == identity
                ),
                None,
            )
            after = next(
                (
                    x
                    for x in (event["result"].get("audit") or {}).get("figures", [])
                    if x["id"] == identity
                ),
                None,
            )
            if not before and not after:
                raise ProjectError("Choose a figure in this run or its baseline.")
            a, b = _select(before, after)
            for item, record in ((a, baseline), (b, event)):
                if item:
                    _inside(self.audit_root(record), item["path"])
            root = Path(temporary)
            left, image_a = _preview(a, [self.audit_root(baseline)], root, "before")
            right, image_b = _preview(b, [self.audit_root(event)], root, "after")
            images = {}
            for key, value in (("before", left), ("after", right)):
                preview = value.get("preview")
                if preview:
                    images[key] = (
                        "data:"
                        + preview["mime"]
                        + ";base64,"
                        + base64.b64encode(_verified_bytes(preview, [root])).decode("ascii")
                    )
            metrics = None
            if image_a is not None and image_b is not None and image_a.size == image_b.size:
                metrics, difference = _metrics(image_a, image_b)
                images["difference"] = "data:image/png;base64," + base64.b64encode(
                    _png_bytes(difference)
                ).decode("ascii")
            if sum(len(value) for value in images.values()) > MAX_SOURCE_BYTES:
                raise ProjectError(
                    "Comparison previews exceed the 20 MiB response limit; inspect the recorded exports separately."
                )
            change = next(
                (
                    x
                    for x in ((event["result"].get("audit") or {}).get("comparison") or {}).get(
                        "figures", []
                    )
                    if x["id"] == identity
                ),
                None,
            )
            return {
                "available": True,
                "baseline": baseline["id"],
                "before": left,
                "after": right,
                "images": images,
                "metrics": metrics,
                "changes": _explain(change, before, after),
                "scope": "Selected static exports; pixel differences do not establish scientific correctness or cross-format equivalence.",
            }

    def start(self, payload):
        self.check_owner()
        _review_token(payload.get("expected_revision"))
        timeout = payload.get("timeout", 120)
        if (
            type(timeout) not in (int, float)
            or not math.isfinite(timeout)
            or not 0 < timeout <= 600
        ):
            raise ProjectError("Choose a positive finite per-figure timeout up to 600 seconds.")
        for name in ("fail_on_warning", "fail_on_change"):
            if name in payload and type(payload[name]) is not bool:
                raise ProjectError(name + " must be true or false.")
        baseline = payload.get("baseline", "latest")
        if baseline is not None and not isinstance(baseline, str):
            raise ProjectError("Choose a saved baseline ID, latest or no baseline.")
        with self.job_lock:
            if self.closing or (self.job and self.job["phase"] == "running"):
                raise ProjectError("A paper audit is already running or the workspace is closing.")
            self.job = {"phase": "running", "result": None, "error": None}

            def work():
                try:
                    self.check_owner()
                    result = run_project(
                        self.source,
                        expected_revision=payload["expected_revision"],
                        baseline=baseline,
                        fail_on_warning=payload.get("fail_on_warning", False),
                        fail_on_change=payload.get("fail_on_change", False),
                        timeout=timeout,
                    )
                    outcome = {
                        "phase": "complete",
                        "result": {
                            key: result.get(key)
                            for key in ("id", "status", "audit_status", "exit_code")
                        },
                        "error": None,
                    }
                except Exception as problem:  # noqa: BLE001 -- keep an explicit terminal job result
                    outcome = {"phase": "failed", "result": None, "error": str(problem)}
                with self.job_lock:
                    self.job = outcome

            self.worker = threading.Thread(target=work, name="paper-audit", daemon=False)
            self.worker.start()
            return copy.deepcopy(self.job)

    def close(self):
        with self.job_lock:
            self.closing = True
        if self.worker:
            self.worker.join()


class ProjectHandler(PreviewHandler):
    def end_headers(self):
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()

    def do_GET(self):
        route = urlsplit(self.path).path
        assets = {
            "/": "project.html",
            "/project.js": "project.js",
            "/project.css": "project.css",
            "/app.css": "app.css",
            "/controls.js": "controls.js",
        }
        if not self.allowed(token=route not in assets):
            self.json({"error": "This local project request is not authorized"}, 403)
            return
        try:
            if route in assets:
                name = assets[route]
                data = (
                    files("graphunslopify")
                    .joinpath("web/" + name)
                    .read_bytes()
                    .replace(b"__PREVIEW_TOKEN__", self.server.state.token.encode())
                )
                self.send(
                    data,
                    (mimetypes.guess_type(name)[0] or "application/octet-stream")
                    + "; charset=utf-8",
                )
                return
            state = self.server.state
            state.check_owner()
            query = parse_qs(urlsplit(self.path).query)
            value = lambda key: query.get(key, [""])[0]
            if route == "/api/state":
                self.json(state.snapshot())
            elif route == "/api/info":
                self.json(
                    {"schema": local_request("schema"), "shared_schema": _shared_schema().schema}
                )
            elif route == "/api/figure":
                self.json(project_figure(state.source, value("id")))
            elif route == "/api/event":
                self.json(state.event(value("id")))
            elif route == "/api/saved-source":
                self.json(state.saved_source(value("event"), value("figure")))
            elif route == "/api/job":
                self.json(state.job_info())
            elif route == "/api/preview":
                data, mime = state.preview(value("event"), value("figure"))
                self.send(data, mime)
            elif route == "/api/artifact":
                data, name = state.artifact(value("event"), value("figure"), int(value("index")))
                # Downloads never execute an HTML export in the workspace origin.
                self.send(data, "application/octet-stream", download=name)
            elif route == "/api/comparison":
                self.json(state.comparison(value("event"), value("figure")))
            else:
                self.json({"error": "Not found"}, 404)
        except (OSError, ValueError, TypeError, KeyError, SpecError) as problem:
            self.json({"error": str(problem)}, 400)

    def do_POST(self):
        if not self.allowed():
            self.json({"error": "This local project request is not authorized"}, 403)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_SOURCE_BYTES:
                raise ProjectError("Choose a nonempty request smaller than 20 MiB.")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ProjectError("Request must be a JSON object.")
            state = self.server.state
            state.check_owner()
            route = urlsplit(self.path).path
            if route == "/api/run":
                self.json(state.start(payload), 202)
            elif route in ("/api/shared", "/api/definition", "/api/entry"):
                with state.job_lock:
                    if state.closing or (state.job and state.job["phase"] == "running"):
                        raise ProjectError(
                            "Wait for the active paper audit before editing saved definitions."
                        )
                kwargs = {"expected_revision": payload.get("expected_revision")}
                if route == "/api/shared":
                    result = set_project_shared(state.source, payload.get("shared"), **kwargs)
                elif route == "/api/definition":
                    result = set_project_figure(
                        state.source, payload.get("id"), payload.get("spec"), **kwargs
                    )
                else:
                    result = set_project_entry(
                        state.source,
                        payload.get("id"),
                        payload.get("entry"),
                        mode=payload.get("mode", "update"),
                        **kwargs,
                    )
                self.json({key: result.get(key) for key in ("id", "status", "exit_code")})
            else:
                self.json({"error": "Not found"}, 404)
        except (OSError, ValueError, TypeError, KeyError, SpecError) as problem:
            self.json({"error": str(problem)}, 400)


class ProjectServer(ThreadingHTTPServer):
    daemon_threads = False

    def __init__(self, path, port=0):
        self.state = ProjectState(path)
        super().__init__(("127.0.0.1", port), ProjectHandler)

    def server_close(self):
        super().server_close()
        self.state.close()


def serve_project(path=".", port=8788, *, open_browser=False):
    if not 0 <= port <= 65535:
        raise ProjectError("Port must be between 0 and 65535.")
    with ProjectServer(path, port) as server:
        url = f"http://127.0.0.1:{server.server_address[1]}"
        print(json.dumps({"url": url}), flush=True)
        if open_browser:
            webbrowser.open(url)
        with contextlib.suppress(KeyboardInterrupt):
            server.serve_forever()
