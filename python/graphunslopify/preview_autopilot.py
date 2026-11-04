"""Session-owned three-draft review, native verification and explicit editor selection."""

from __future__ import annotations

import copy
import hashlib
import io
import json
import secrets
import shutil
import threading
import time
from urllib.parse import quote
from zipfile import ZIP_DEFLATED, ZipFile

from .autopilot import AutopilotError, generate_drafts, propose_figures
from .experiment_imports import _contained_bytes
from .preview_experiments import _context


class PreviewAutopilot:
    def __init__(self, state):
        self.state = state
        self.root = state.root / "autopilot"
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.readers = threading.BoundedSemaphore(2)
        self.renderers = threading.BoundedSemaphore(1)
        self.plans = {}
        self.closed = False

    def _remove(self, identity, plan):
        folder = plan.get("folder")
        if folder is not None:
            if folder.parent != self.root or folder.name != identity or folder.is_symlink():
                raise AutopilotError("Draft folder no longer belongs to this session")
            shutil.rmtree(folder, ignore_errors=True)
        self.plans.pop(identity, None)

    def _expire(self):
        for identity, plan in list(self.plans.items()):
            if time.monotonic() - plan["created"] > 600:
                plan["cancelled"] = True
                if not plan["busy"]:
                    self._remove(identity, plan)

    def close(self):
        with self.lock:
            self.closed = True
            for identity, plan in list(self.plans.items()):
                plan["cancelled"] = True
                if not plan["busy"]:
                    self._remove(identity, plan)

    def _current(self, payload):
        with self.state.lock:
            newer = self.state.generations.get(payload["client"], -1) > payload["generation"]
        if newer:
            raise AutopilotError("A newer editor revision superseded these drafts")

    def _get(self, payload, *, current=True):
        client, context = _context(payload)
        if current:
            self._current(payload)
        with self.lock:
            self._expire()
            plan = self.plans.get(payload.get("id"))
            if (
                self.closed
                or plan is None
                or plan["cancelled"]
                or plan["client"] != client
                or plan["context"] != context
            ):
                raise AutopilotError("Draft review expired or belongs to different editor settings")
            plan["created"] = time.monotonic()
            return plan

    def _analyze(self, path, question, choices):
        if not self.readers.acquire(blocking=False):
            raise AutopilotError("Two dataset readers are active; retry after one finishes")
        try:
            return propose_figures(path, question, **choices)
        finally:
            self.readers.release()

    def review(self, payload):
        client, context = _context(payload)
        with self.lock:
            if self.closed:
                raise AutopilotError("Draft session is closed")
        self._current(payload)
        data = self.state.selected_data(payload.get("data_id"))
        choices = copy.deepcopy(payload.get("choices", {}))
        if not isinstance(choices, dict):
            raise AutopilotError("Figure choices must be an object")
        if data["format"] == "excel":
            sheet = data["profile"]["sheet"]
            if "sheet" in choices and choices["sheet"] != sheet:
                raise AutopilotError("Use the worksheet actually selected in this editor")
            choices["sheet"] = sheet
        elif "sheet" in choices:
            raise AutopilotError("Worksheet choices only apply to a selected workbook")
        proposal = self._analyze(data["path"], payload.get("question"), choices)
        self._current(payload)
        identity = None
        with self.lock:
            if self.closed:
                raise AutopilotError("Draft session closed while reading the dataset")
            if proposal.report["ready"]:
                identity = secrets.token_urlsafe(24)
                self._expire()
                if len(self.plans) >= 8:
                    raise AutopilotError("Eight pending draft reviews are retained")
                self.plans[identity] = {
                    "client": client,
                    "context": context,
                    "created": time.monotonic(),
                    "proposal": proposal,
                    "source_name": data["name"],
                    "busy": False,
                    "cancelled": False,
                    "result": None,
                    "selected": False,
                    "folder": None,
                }
        sample = json.loads(proposal.data_bytes)[:20] if proposal.data_bytes else []
        return {
            "id": identity,
            "report": copy.deepcopy(proposal.report),
            "drafts": copy.deepcopy(proposal.drafts),
            "source_name": data["name"],
            "normalized_sample": sample,
            "sample_limit": 20,
            "applied": False,
            "verified": False,
            "expires_after_idle_seconds": 600,
        }

    def cancel(self, payload):
        client, _ = _context(payload)
        with self.lock:
            plan = self.plans.get(payload.get("id"))
            if plan and plan["client"] == client:
                plan["cancelled"] = True
                if not plan["busy"]:
                    self._remove(payload["id"], plan)
        return {"cancelled": True}

    @staticmethod
    def _source_unchanged(plan):
        proposal = plan["proposal"]
        raw = _contained_bytes(proposal.source.parent, proposal.source.name)
        if hashlib.sha256(raw).hexdigest() != proposal.report["original_sha256"]:
            raise AutopilotError("Selected source changed; review the dataset again")

    def _bytes(self, plan, name):
        expected = plan.get("files", {}).get(name) or plan.get("packets", {}).get(name)
        if expected is None:
            raise AutopilotError("This draft file is not registered")
        raw = _contained_bytes(plan["folder"], name, limit=32 * 1024 * 1024)
        if len(raw) != expected["bytes"] or hashlib.sha256(raw).hexdigest() != expected["sha256"]:
            raise AutopilotError("A generated draft file changed; generate a fresh comparison")
        return raw

    @staticmethod
    def _url(identity, name):
        return "/autopilot-artifact/" + identity + "/" + quote(name, safe="")

    def _view(self, identity, plan):
        result = copy.deepcopy(plan["result"])
        result.update(id=identity, source_name=plan["source_name"], applied=False)
        for draft in result["drafts"]:
            names = [
                name
                for name in plan["files"]
                if name.startswith(draft["id"] + "/") and name.endswith(".png")
            ]
            draft["preview_url"] = self._url(identity, names[0]) if len(names) == 1 else None
        result["files"] = [
            {"name": name, "url": self._url(identity, name)}
            for name in plan["files"]
            if name != "autopilot-data.json"
        ]
        return result

    def generate(self, payload):
        plan = self._get(payload)
        if payload.get("reviewed") is not True:
            raise AutopilotError(
                "Review the question, fields, units and all three draft assumptions"
            )
        if (
            plan["proposal"].report["excluded_count"]
            and payload.get("accept_exclusions") is not True
        ):
            raise AutopilotError("Explicitly accept the recorded joint-sample exclusions")
        if not self.renderers.acquire(blocking=False):
            raise AutopilotError("A three-draft check is already running; wait for it to finish")
        try:
            with self.lock:
                if plan["busy"] or plan["result"] is not None:
                    raise AutopilotError("These drafts are already generating or checked")
                plan["busy"] = True
            try:
                original = plan["proposal"]
                fresh = self._analyze(
                    original.source,
                    original.report["question"],
                    original.report["requested_choices"],
                )
                if (
                    fresh.report != original.report
                    or fresh.drafts != original.drafts
                    or fresh.data_bytes != original.data_bytes
                ):
                    raise AutopilotError("Source, reader or reviewed choices changed; review again")
                self._current(payload)
                with self.lock:
                    if self.closed or plan["cancelled"]:
                        raise AutopilotError("Draft generation was cancelled")
                    folder = self.root / payload["id"]
                    plan["folder"] = folder
                result = generate_drafts(
                    fresh,
                    folder,
                    reviewed=True,
                    accept_exclusions=payload.get("accept_exclusions") is True,
                )
                files = {}
                total = 0
                for path in sorted(folder.rglob("*")):
                    if not path.is_file():
                        continue
                    name = path.relative_to(folder).as_posix()
                    raw = _contained_bytes(folder, name, limit=32 * 1024 * 1024)
                    total += len(raw)
                    if len(files) >= 128 or total > 128 * 1024 * 1024:
                        raise AutopilotError(
                            "Generated draft files exceed the comparison size bound"
                        )
                    files[name] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
                with self.lock:
                    plan.update(result=result, files=files, created=time.monotonic())
                    cancelled = self.closed or plan["cancelled"]
                self._current(payload)
                if cancelled:
                    raise AutopilotError("Draft generation was superseded or cancelled")
                return self._view(payload["id"], plan)
            finally:
                with self.lock:
                    plan["busy"] = False
                    if self.closed or plan["cancelled"]:
                        self._remove(payload["id"], plan)
        finally:
            self.renderers.release()

    def artifact(self, identity, name):
        with self.lock:
            self._expire()
            plan = self.plans.get(identity)
            if self.closed or plan is None or plan["cancelled"] or plan["result"] is None:
                raise AutopilotError("These draft files are no longer available")
            if name == "autopilot-data.json":
                raise AutopilotError("Choose an explicit data-including comparison download")
            raw = self._bytes(plan, name)
            plan["created"] = time.monotonic()
            return raw

    def packet(self, payload):
        # Historical results remain downloadable after applying a draft or editing intent.
        plan = self._get(payload, current=False)
        if plan["result"] is None:
            raise AutopilotError("Generate all three drafts before saving their comparison")
        include = payload.get("include_data", False)
        if type(include) is not bool:
            raise AutopilotError("Choose whether to include normalized observations")
        stream = io.BytesIO()
        inventory = {}
        with self.lock, ZipFile(stream, "w", ZIP_DEFLATED) as archive:
            for name, expected in plan["files"].items():
                included = name != "autopilot-data.json" or include
                inventory[name] = {**expected, "included": included}
                if included:
                    archive.writestr(name, self._bytes(plan, name))
            archive.writestr(
                "comparison-manifest.json",
                json.dumps(
                    {"schema_version": 1, "files": inventory, "include_data": include}, indent=2
                ),
            )
            archive.writestr(
                "README.txt",
                "These are the original three generated programs, reports and exports.\n"
                "Each draft has its own directory and verification verdict; failed drafts remain failed.\n"
                "Replay with the recorded scientific environment and GraphUnslopify revision.\n"
                "From each draft directory run its generated .py program and inspect the new report.\n"
                "Normalized observations are included only when explicitly requested.\n"
                "The original uploaded source is not included. An archive is not new verification.\n",
            )
        raw = stream.getvalue()
        if len(raw) > 32 * 1024 * 1024:
            raise AutopilotError("Compressed draft comparison exceeds32MiB")
        name = "comparison-with-data.zip" if include else "comparison.zip"
        with self.lock:
            if self.closed or plan["cancelled"] or plan["folder"].is_symlink():
                raise AutopilotError("Comparison download was cancelled")
            temporary = plan["folder"] / (name + "." + secrets.token_hex(8) + ".tmp")
            with temporary.open("xb") as output:
                output.write(raw)
            temporary.replace(plan["folder"] / name)
            plan.setdefault("packets", {})[name] = {
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        return {"url": self._url(payload["id"], name), "include_data": include}

    def select(self, payload):
        plan = self._get(payload)
        result = plan["result"]
        if result is None:
            raise AutopilotError("Generate and compare all three drafts before selecting one")
        chosen = next((d for d in result["drafts"] if d["id"] == payload.get("draft_id")), None)
        if chosen is None or chosen["status"] != "passed":
            raise AutopilotError("Choose a draft whose strict native checks passed")
        if not result["source_unchanged"] or not result["materialized_data_unchanged"]:
            raise AutopilotError("Source or plotting data changed during generation; review again")
        with self.lock:
            if plan["busy"] or plan["selected"]:
                raise AutopilotError("This comparison is busy or a draft was already selected")
            plan["busy"] = True
        uploaded = None
        try:
            self._source_unchanged(plan)
            for name in plan["files"]:
                self._bytes(plan, name)
            data = self._bytes(plan, "autopilot-data.json")
            if data != plan["proposal"].data_bytes:
                raise AutopilotError("Normalized plotting values changed; review again")
            self._current(payload)
            ancestry = {
                "schema_version": 1,
                "chosen_draft": chosen["id"],
                "reviewed": True,
                "source_name": plan["source_name"],
                "comparison": copy.deepcopy(result),
                "scientific_appropriateness_certified": False,
            }
            uploaded = self.state.upload("autopilot-data.json", data)
            self._source_unchanged(plan)
            self._current(payload)
            with self.lock:
                if self.closed or plan["cancelled"]:
                    raise AutopilotError("Draft selection was cancelled")
                plan["selected"] = True
            with self.state.lock:
                self.state.uploads[uploaded["id"]]["autopilot"] = ancestry
            return {
                "data": uploaded,
                "spec": copy.deepcopy(chosen["spec"]),
                "report": ancestry,
                "verified": False,
                "notice": "The chosen checked draft now enters the editor's usual native checks.",
            }
        except Exception:
            if uploaded is not None:
                with self.state.lock:
                    record = self.state.uploads.pop(uploaded["id"], None)
                if record is not None:
                    shutil.rmtree(record["path"].parent, ignore_errors=True)
            raise
        finally:
            with self.lock:
                plan["busy"] = False
                if self.closed or plan["cancelled"]:
                    self._remove(payload["id"], plan)
