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
from urllib.parse import parse_qs, unquote, urlsplit

from .comparison import _explain, _metrics, _png_bytes, _preview, _select, _verified_bytes
from .errors import SpecError
from .preview import PreviewHandler
from .project import (
    MAX_SOURCE_BYTES,
    ProjectError,
    _config,
    _inside,
    _native,
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
from .review_agent import DEFAULT_QUESTION, FigureReviewPlan, review_document
from .review_sessions import ReviewSessions
from .transport import local_request


class _PaperReviewPlan(FigureReviewPlan):
    """Recheck this actual workspace's ownership and job lifecycle on collection."""

    def __init__(self, state, provider, payload):
        self._workspace = state
        super().__init__(
            provider,
            state.source,
            figures=payload.get("figures"),
            question=payload.get("question", DEFAULT_QUESTION),
            event_id=payload.get("event"),
            author_context=payload.get("author_context", ""),
            structured_output=payload.get("structured_output", True),
        )

    def _collect(self):
        self._workspace.review_ready()
        collection = super()._collect()
        self._workspace.review_ready()
        return collection


class ProjectState:
    def __init__(self, path):
        self.source, config = _config(path)
        self.project_id = config["project_id"]
        self.mode = config.get("mode", "source_backed")
        self.token = secrets.token_urlsafe(32)
        self.job_lock = threading.Lock()
        self.media_lock = threading.Lock()
        self.worker = None
        self.job = None
        self.closing = False
        self.reviewer = ReviewSessions(
            self.review_plan, review_document, source_kind="paper-project"
        )

    def review_ready(self):
        self.check_owner()
        with self.job_lock:
            if self.closing or (self.job and self.job["phase"] == "running"):
                raise ProjectError("Wait for the paper job or reopen the closing workspace.")

    def review_plan(self, provider, payload):
        if set(payload) - {
            "client",
            "generation",
            "expected_revision",
            "figures",
            "question",
            "event",
            "author_context",
            "structured_output",
        }:
            raise ProjectError("Choose reviewer selection and author-context fields")
        # The expected revision is the actual review collection, not a client report
        # or the narrower editable-definition revision.
        _review_token(payload.get("expected_revision"))
        plan = _PaperReviewPlan(self, provider, payload)
        if plan._binding != payload["expected_revision"]:
            raise ProjectError("Review evidence changed since selection; refresh the collection.")
        return plan

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
            from .project_inspections import project_inspections

            pdfs = project_inspections(self.source)
            after = project_history(self.source)
            if state["revision"] != pdfs["native_revision"] or [
                (event["id"], event["integrity"]) for event in history["events"]
            ] != [(event["id"], event["integrity"]) for event in after["events"]]:
                raise ProjectError("Project changed while reading its collection; refresh.")
            state["inspection_revision"] = pdfs["revision"]
            state["inspections"] = [
                {
                    key: row[key]
                    for key in (
                        "id",
                        "name",
                        "origin",
                        "event",
                        "freshness",
                        "operation_status",
                        "evidence_state",
                        "assets_verified",
                        "current_sha256",
                        "errors",
                    )
                }
                for row in pdfs["sources"]
            ]
        except (OSError, ValueError, KeyError, TypeError, SpecError) as problem:
            state = {
                "status": "unavailable",
                "revision": None,
                "figures": [],
                "shared": {},
                "mode": self.mode,
                "inspections": [],
                "inspection_revision": None,
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
                "inspection_id": (event.get("result", {}).get("inspection_source") or {}).get("id"),
                "shared_change": event.get("action") == "settings"
                and event.get("integrity") is True
                and event.get("result", {}).get("status") == "settings_saved",
                "selection_change": event.get("action") == "selection"
                and event.get("integrity") is True
                and event.get("result", {}).get("status") == "selection_saved",
                "undo_of": event.get("result", {}).get("undo_of"),
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

    def journal_check(self, payload):
        from .journal_workspace import inspect_export

        self.check_owner()
        expected_revision = payload.get("expected_revision")
        _review_token(expected_revision)
        before = project_status(self.source)
        if expected_revision != before["revision"]:
            raise ProjectError("Project inputs changed; refresh before checking a journal profile")
        event = self.event(payload.get("event"))
        figure = self.audited(event, payload.get("figure"))
        index = payload.get("index")
        if type(index) is not int or not 0 <= index < len(figure["outputs"]):
            raise ProjectError("Choose a recorded figure export")
        item = figure["outputs"][index]
        # Reuse the existing containment, size and recorded-byte integrity boundary.
        self.artifact(event["id"], figure["id"], index)
        path = _inside(self.audit_root(event), item["path"])
        report = inspect_export(path, item, payload)
        self.event(event["id"])
        self.check_owner()
        if project_status(self.source)["revision"] != expected_revision:
            raise ProjectError("Project changed while journal checks ran; refresh and check again")
        return {
            "report": report,
            "context": {
                "kind": "saved_history_export",
                "event": event["id"],
                "figure": figure["id"],
                "index": index,
                "project_revision": expected_revision,
                "scope": "Saved history export; current figure and scientific acceptance are separate",
            },
        }

    def element_map(self, payload):
        """Read one current owned native map; never execute a selected source."""
        from .audit_geometry import checked_geometry

        self.check_owner()
        revision = payload.get("expected_revision")
        _review_token(revision)
        before = project_status(self.source)
        if revision != before["revision"]:
            raise ProjectError("Project inputs changed; refresh before inspecting elements")
        event = self.event(payload.get("event"))
        if (event["result"].get("snapshot") or {}).get("revision") != revision:
            raise ProjectError("Historical geometry cannot edit a different current revision")
        identity = payload.get("figure")
        definition = project_figure(self.source, identity)
        if (
            definition["revision"] != revision
            or not definition["editable"]
            or definition["source_type"] != "spec"
        ):
            raise ProjectError(
                "Element editing needs the matching editable current JSON definition"
            )
        figure = self.audited(event, identity)
        metadata = figure.get("edit_map") or {}
        if metadata.get("available") is not True:
            raise ProjectError(
                metadata.get("reason")
                or "This saved run has no element map; regenerate PNG evidence"
            )
        report = figure["report"]
        if metadata.get("spec_hash") != report["spec_hash"]:
            raise ProjectError("Element map belongs to a different canonical specification")
        index = next(
            (i for i, item in enumerate(figure["outputs"]) if item["format"] == "png"), None
        )
        if index is None:
            raise ProjectError("Element inspection needs an original recorded PNG")
        png = figure["outputs"][index]
        if metadata.get("image_sha256") != png["sha256"]:
            raise ProjectError("Element map belongs to a different recorded PNG")
        image_bytes, _ = self.artifact(event["id"], identity, index)
        raw = _verified_bytes(metadata, [self.audit_root(event)])
        geometry = checked_geometry(raw, png, image_bytes)
        self.event(event["id"])
        self.check_owner()
        if project_status(self.source)["revision"] != revision:
            raise ProjectError("Project changed while reading element geometry; refresh")
        return {
            "edit_map": {**geometry, "spec_hash": report["spec_hash"]},
            "spec_hash": report["spec_hash"],
            "image": {**png, "index": index},
            "context": {
                "kind": "paper_history",
                "project_revision": revision,
                "definition_revision": definition["revision"],
                "event": event["id"],
                "figure": identity,
                "scope": "Original JSON definition; manifest and paper presentation overrides keep their own controls",
            },
        }

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
        _native(_config(self.source)[1])
        _review_token(payload.get("expected_revision"))
        timeout = payload.get("timeout", 120)
        if (
            type(timeout) not in (int, float)
            or not math.isfinite(timeout)
            or not 0 < timeout <= 600
        ):
            raise ProjectError("Choose a positive finite per-figure timeout up to 600 seconds.")
        for name in ("fail_on_warning", "fail_on_change", "selective"):
            if name in payload and type(payload[name]) is not bool:
                raise ProjectError(name + " must be true or false.")
        baseline = payload.get("baseline", "latest")
        if baseline is not None and not isinstance(baseline, str):
            raise ProjectError("Choose a saved baseline ID, latest or no baseline.")
        return self._start_job(
            lambda: run_project(
                self.source,
                expected_revision=payload["expected_revision"],
                baseline=baseline,
                fail_on_warning=payload.get("fail_on_warning", False),
                fail_on_change=payload.get("fail_on_change", False),
                timeout=timeout,
                selective=payload.get("selective", False),
            ),
            "audit",
        )

    def start_inspection(self, payload, *, data=None, name=None):
        from .project_inspections import (
            _inspection_options,
            inspect_project_pdf,
            inspect_uploaded_pdf,
            project_inspections,
        )

        self.check_owner()
        options = {
            "identity": payload.get("id"),
            "expected_revision": payload.get("expected_revision"),
            "pages": payload.get("pages"),
            "dpi": payload.get("dpi", 144),
            "timeout": payload.get("timeout", 120),
        }
        _inspection_options(**options)
        if data is not None:
            if (
                not isinstance(name, str)
                or not name
                or len(name) > 255
                or any(ord(c) < 32 for c in name)
            ):
                raise ProjectError("Choose a PDF filename of 1-255 printable characters.")
            operation = lambda: inspect_uploaded_pdf(self.source, data, name=name, **options)
        else:
            current = project_inspections(self.source)
            if current["revision"] != options["expected_revision"]:
                raise ProjectError("Inspection evidence changed since review; refresh.")
            row = next(
                (row for row in current["sources"] if row["id"] == options["identity"]), None
            )
            if row is None:
                raise ProjectError("Choose a registered PDF source to inspect again.")
            file = self.source.parent.parent / row["path"]
            operation = lambda: inspect_project_pdf(
                self.source,
                file,
                source_name=row["name"],
                source_origin=row["origin"],
                **options,
            )
        return self._start_job(operation, "inspection")

    def _start_job(self, operation, kind):
        with self.job_lock:
            if self.closing or (self.job and self.job["phase"] == "running"):
                raise ProjectError("A paper audit is already running or the workspace is closing.")
            self.job = {"phase": "running", "kind": kind, "result": None, "error": None}

            def work():
                try:
                    self.check_owner()
                    result = operation()
                    outcome = {
                        "phase": "complete",
                        "kind": kind,
                        "result": {
                            key: result.get(key)
                            for key in ("id", "status", "audit_status", "exit_code")
                        },
                        "error": None,
                    }
                except Exception as problem:  # noqa: BLE001 -- keep an explicit terminal job result
                    outcome = {
                        "phase": "failed",
                        "kind": kind,
                        "result": None,
                        "error": str(problem),
                    }
                with self.job_lock:
                    self.job = outcome

            self.worker = threading.Thread(target=work, name="paper-" + kind, daemon=False)
            self.worker.start()
            return copy.deepcopy(self.job)

    def close(self):
        with self.job_lock:
            self.closing = True
        self.reviewer.close()
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
            "/project-review.js": "project-review.js",
            "/figure-reviewer.js": "figure-reviewer.js",
            "/figure-reviewer.css": "figure-reviewer.css",
            "/project-shared.js": "project-shared.js",
            "/project-selection.js": "project-selection.js",
            "/reuse-intent.js": "reuse-intent.js",
            "/journal-checks.js": "journal-checks.js",
            "/context-inspector.js": "context-inspector.js",
            "/workspace-commands.js": "workspace-commands.js",
            "/project.css": "project.css",
            "/app.css": "app.css",
            "/controls.js": "controls.js",
            "/diagnostics.js": "diagnostics.js",
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
                from .diagnostics import catalog
                from .figure_templates import presets
                from .journal import journal_profiles

                self.json(
                    {
                        "schema": local_request("schema"),
                        "shared_schema": _shared_schema().schema,
                        "diagnostics": catalog(),
                        "reuse_presets": presets(),
                        "journal_profiles": journal_profiles(),
                    }
                )
            elif route == "/api/figure":
                self.json(project_figure(state.source, value("id")))
            elif route == "/api/event":
                self.json(state.event(value("id")))
            elif route == "/api/review":
                from .project_review import project_review

                self.json(project_review(state.source, event_id=value("event") or None))
            elif route == "/api/reviewer/provider":
                self.json(state.reviewer.info())
            elif route == "/api/scorecard":
                from .project_scorecard import project_scorecard

                report = project_scorecard(state.source, event_id=value("event") or None)
                if value("expected_revision") and report["evidence_revision"] != value(
                    "expected_revision"
                ):
                    raise ProjectError("Scorecard evidence changed since selection; refresh.")
                self.json(report)
            elif route == "/api/pdf-asset":
                from .project_inspections import inspection_asset

                data, name = inspection_asset(state.source, value("event"), int(value("index")))
                if value("view") == "1" and name.endswith(".png"):
                    self.send(data, "image/png")
                else:
                    self.send(data, "application/octet-stream", download=name)
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
            route = urlsplit(self.path).path
            state = self.server.state
            state.check_owner()
            length = int(self.headers.get("Content-Length", "0"))
            if route == "/api/pdf-upload":
                from .project_inspections import MAX_PDF_BYTES

                if not 0 < length <= MAX_PDF_BYTES:
                    raise ProjectError("Upload a PDF no larger than 50 MiB.")
                if self.headers.get("Content-Type", "").split(";")[0] != "application/pdf":
                    raise ProjectError("Upload the selected file as application/pdf.")
                data = self.rfile.read(length)
                if len(data) != length or not data.startswith(b"%PDF-"):
                    raise ProjectError("The uploaded file is not a complete PDF.")
                query = parse_qs(urlsplit(self.path).query)
                value = lambda key, default="": query.get(key, [default])[0]
                pages = value("pages").replace(",", " ").split()
                payload = {
                    "id": value("id"),
                    "expected_revision": value("expected_revision"),
                    "pages": [int(page) for page in pages] if pages else None,
                    "dpi": int(value("dpi", "144")),
                    "timeout": float(value("timeout", "120")),
                }
                self.json(
                    state.start_inspection(
                        payload, data=data, name=unquote(self.headers.get("X-File-Name", ""))
                    ),
                    202,
                )
                return
            if not 0 < length <= MAX_SOURCE_BYTES:
                raise ProjectError("Choose a nonempty request smaller than 20 MiB.")
            if route.startswith("/api/reviewer/") and length > 65536:
                raise ProjectError("Reviewer controls must fit within 64 KiB.")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ProjectError("Request must be a JSON object.")
            if route.startswith("/api/reviewer/"):
                operation = {
                    "/api/reviewer/provider": state.reviewer.configure,
                    "/api/reviewer/disclose": state.reviewer.disclose,
                    "/api/reviewer/start": state.reviewer.start,
                    "/api/reviewer/status": state.reviewer.status,
                    "/api/reviewer/cancel": state.reviewer.cancel,
                    "/api/reviewer/download": state.reviewer.download,
                }.get(route)
                if operation is None:
                    self.json({"error": "Not found"}, 404)
                    return
                result = operation(payload)
                if route == "/api/reviewer/download":
                    self.send(
                        json.dumps(result, allow_nan=False).encode(),
                        "application/json; charset=utf-8",
                        download="figure-review-" + payload["which"] + ".json",
                    )
                else:
                    self.json(result, 202 if route == "/api/reviewer/start" else 200)
            elif route == "/api/run":
                self.json(state.start(payload), 202)
            elif route == "/api/journal-check":
                self.json(state.journal_check(payload))
            elif route == "/api/element-map":
                self.json(state.element_map(payload))
            elif route == "/api/review-export":
                from .project_export import create_review_packet

                with state.job_lock:
                    if state.closing or (state.job and state.job["phase"] == "running"):
                        raise ProjectError(
                            "Wait for the active project job before exporting review evidence."
                        )
                data = create_review_packet(
                    state.source,
                    event_id=payload.get("event") or None,
                    expected_revision=payload.get("expected_revision"),
                )
                self.send(data, "application/zip", download="paper-review.zip")
            elif route == "/api/pdf-inspection":
                self.json(state.start_inspection(payload), 202)
            elif route in ("/api/reuse/template", "/api/reuse/proposal"):
                import copy

                from .figure_templates import create_template, review_reuse

                with state.job_lock:
                    if state.closing or (state.job and state.job["phase"] == "running"):
                        raise ProjectError(
                            "Wait for the active paper job before reviewing figure intent."
                        )
                record = project_figure(state.source, payload.get("id"))
                if record["revision"] != payload.get("expected_revision"):
                    raise ProjectError(
                        "Project inputs changed; refresh before reviewing figure intent."
                    )
                if record["source_type"] != "spec" or (
                    route.endswith("/proposal") and not record["editable"]
                ):
                    raise ProjectError(
                        "Choose an editable JSON definition for this intent proposal."
                    )

                def validate(candidate):
                    prepared = copy.deepcopy(candidate)
                    if record["columns"]:
                        prepared.setdefault("data", {})["columns"] = record["columns"]
                    return local_request("validate", prepared)

                if route.endswith("/template"):
                    result = create_template(
                        payload.get("spec"), payload.get("name"), validator=validate
                    )
                else:
                    result = review_reuse(
                        payload.get("spec"),
                        template=payload.get("template"),
                        preset=payload.get("preset"),
                        mapping=payload.get("mapping"),
                        replace_claims=payload.get("replace_claims", False),
                        validator=validate,
                    )
                    result["notes"] = []
                    if len(record["shared_by"]) > 1:
                        result["notes"].append(
                            "Saving this original source also affects: "
                            + ", ".join(record["shared_by"])
                        )
                    if any(k in record["entry"] for k in ("data", "claims")):
                        result["notes"].append(
                            "Manifest data/claim overrides still take precedence over this original definition."
                        )
                    result["notes"].append(
                        "Shared and selected presentation settings still apply at audit. Apply changes a draft; save it,then audit."
                    )
                if (
                    project_figure(state.source, payload.get("id"))["revision"]
                    != record["revision"]
                ):
                    raise ProjectError("Project inputs changed during intent review; refresh.")
                self.json(result)
            elif route in (
                "/api/shared",
                "/api/shared-review",
                "/api/shared-apply",
                "/api/selection-review",
                "/api/selection-apply",
                "/api/definition",
                "/api/entry",
            ):
                with state.job_lock:
                    if state.closing or (state.job and state.job["phase"] == "running"):
                        raise ProjectError(
                            "Wait for the active paper audit before editing saved definitions."
                        )
                kwargs = {"expected_revision": payload.get("expected_revision")}
                if route in ("/api/selection-review", "/api/selection-apply"):
                    from .project_selection import apply_project_selection, review_project_selection

                    operation = (
                        review_project_selection
                        if route.endswith("-review")
                        else apply_project_selection
                    )
                    result = operation(
                        state.source,
                        payload.get("ids"),
                        payload.get("settings"),
                        reset=payload.get("reset", False),
                        undo_event=payload.get("undo_event"),
                        **kwargs,
                        **(
                            {"proposal_token": payload.get("proposal_token")}
                            if route.endswith("-apply")
                            else {}
                        ),
                    )
                    if route.endswith("-review"):
                        self.json(result)
                        return
                elif route in ("/api/shared-review", "/api/shared-apply"):
                    from .project_changes import apply_project_shared, review_project_shared

                    operation = (
                        review_project_shared
                        if route == "/api/shared-review"
                        else apply_project_shared
                    )
                    result = operation(
                        state.source,
                        payload.get("shared"),
                        undo_event=payload.get("undo_event"),
                        **kwargs,
                        **(
                            {"proposal_token": payload.get("proposal_token")}
                            if route == "/api/shared-apply"
                            else {}
                        ),
                    )
                    if route == "/api/shared-review":
                        self.json(result)
                        return
                elif route == "/api/shared":
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
    # A browser requests the module graph as a burst, often across open tabs.
    # Match the native editor's queue so queued imports are not reset at startup.
    request_queue_size = 128

    def __init__(self, path, port=0):
        self.state = ProjectState(path)
        super().__init__(("127.0.0.1", port), ProjectHandler)

    def server_close(self):
        # Cancellation must precede ThreadingHTTPServer's handler joins.
        try:
            self.state.close()
        finally:
            super().server_close()


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
