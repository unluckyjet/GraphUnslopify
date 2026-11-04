"""Reviewer evidence from completed, owned native editor executions."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import stat
import uuid
from pathlib import Path

from .drafts import _digest
from .project import _execution_source, _inside
from .project_review import _groups
from .review_agent import DEFAULT_QUESTION, FigureReviewPlan

MAX_FILE_BYTES = 256 * 1024 * 1024


def _stamp(value):
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def _file(root, name):
    """Hash bounded regular owned files, checking identity before and after reading."""
    target = _inside(root, name)
    before = target.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_FILE_BYTES:
        raise ValueError("Review evidence requires regular owned files of at most 256MiB")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    with os.fdopen(os.open(target, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode) or _stamp(before) != _stamp(opened):
            raise ValueError("Review evidence file changed while opening")
        digest, size = hashlib.sha256(), 0
        for chunk in iter(lambda: stream.read(65536), b""):
            size += len(chunk)
            if size > MAX_FILE_BYTES:
                raise ValueError("Review evidence file exceeds 256MiB")
            digest.update(chunk)
        after = os.fstat(stream.fileno())
    if (
        _inside(root, name) != target
        or _stamp(before) != _stamp(after)
        or _stamp(before) != _stamp(target.lstat())
        or size != before.st_size
    ):
        raise ValueError("Review evidence file changed while reading")
    return {"sha256": digest.hexdigest(), "bytes": size}


class _EditorReviewPlan(FigureReviewPlan):
    source_kind = "editor-render"

    def __init__(self, owner, provider, payload):
        self._owner = owner
        self._render = {key: payload.get(key) for key in owner.selection_fields}
        super().__init__(
            provider,
            owner.state.root,
            question=payload.get("question", DEFAULT_QUESTION),
            figures=payload.get("figures", ["figure"]),
            author_context=payload.get("author_context", ""),
            structured_output=payload.get("structured_output", True),
        )

    def _collect(self):
        return self._owner.collect(self._render)


class PreviewReviews:
    """Bind one rendered figure without pretending it is a saved paper project."""

    selection_fields = frozenset({"run_id", "render_client", "render_generation"})

    def __init__(self, state):
        self.state = state
        self.identity = uuid.uuid4().hex  # Public identity, never the HTTP authorization token.
        self.root_identity = (state.root.stat().st_dev, state.root.stat().st_ino)

    def _root(self):
        observed = self.state.root.lstat()
        if (
            not stat.S_ISDIR(observed.st_mode)
            or (observed.st_dev, observed.st_ino) != self.root_identity
        ):
            raise ValueError("Editor workspace ownership changed; reopen the editor")

    def _name(self, path):
        return Path(path).relative_to(self.state.root).as_posix()

    def begin(self, spec, data, palette, folder, script):
        """Capture original uploads and the actual run files before native execution."""
        try:
            self._root()
            paths = [data["path"], folder / data["filename"], script]
            if palette:
                paths.extend([palette["path"], folder / palette["filename"]])
            manifest = {
                self._name(path): _file(self.state.root, self._name(path)) for path in paths
            }
            for upload in (data, palette):
                if upload is not None and (
                    manifest[self._name(upload["path"])]["sha256"] != upload["sha256"]
                    or manifest[self._name(folder / upload["filename"])]["sha256"]
                    != upload["sha256"]
                ):
                    raise ValueError("An uploaded input changed; upload it again before review")
            return {
                "available": True,
                "files": manifest,
                "execution_source": _execution_source(),
                "prepared_spec": copy.deepcopy(spec),
                "data_id": data["id"],
                "palette_id": palette["id"] if palette else None,
                "palette_run": self._name(folder / palette["filename"]) if palette else None,
                "data_sha256": data["sha256"],
                "script": self._name(script),
            }
        except (OSError, ValueError, KeyError) as problem:
            # Evidence refusal must not replace the renderer's actual report or exit.
            return {"available": False, "error": str(problem)}

    def finish(self, before, record, report, exit_code, execution, export_errors):
        if not before["available"]:
            return before
        try:
            self._root()
            for name, expected in before["files"].items():
                if name == before["palette_run"]:
                    # The native allocator can extend its run copy. Verify its
                    # actual input snapshot separately from its final saved bytes.
                    continue
                if _file(self.state.root, name) != expected:
                    raise ValueError("Native execution inputs or program changed during rendering")
            if _execution_source() != before["execution_source"]:
                raise ValueError("Compiler sources changed during rendering")
            if (
                report.get("script", {}).get("sha256")
                != before["files"][before["script"]]["sha256"]
            ):
                raise ValueError("Native report does not describe the executed program")
            if report.get("data", {}).get("sha256_prefix") != before["data_sha256"][:16]:
                raise ValueError("Native report data prefix does not match the bound input")
            if (
                type(exit_code) is not int
                or report.get("exit_code") != exit_code
                or report.get("policy", {}).get("strict") is not True
            ):
                raise ValueError("Native report does not match the actual strict execution")
            metadata = copy.deepcopy(before)
            if before["palette_run"] is not None:
                observation = Path(self.state.root / before["script"]).with_suffix(
                    ".review-inputs.json"
                )
                name = self._name(observation)
                observed_file = _file(self.state.root, name)
                if observed_file["bytes"] > 1024 * 1024:
                    raise ValueError("Native reviewer input observation exceeds 1MiB")
                observed = json.loads(observation.read_text(encoding="utf8"))
                expected = before["files"][before["palette_run"]]
                allowed = [
                    {
                        "schema_version": 1,
                        "palette_reads": [
                            {
                                "path": record["palette"],
                                "bytes": expected["bytes"],
                                "sha256": expected["sha256"],
                            }
                        ],
                    }
                ]
                final_palette = _file(self.state.root, before["palette_run"])
                # Some native figures do not use their supplied palette. A
                # recorded absence of reads is valid only if the run copy stayed
                # unchanged; it is never a fallback for a different input read.
                if final_palette == expected:
                    allowed.append({"schema_version": 1, "palette_reads": []})
                if (
                    not isinstance(observed, dict)
                    or type(observed.get("schema_version")) is not int
                    or observed not in allowed
                    or _file(self.state.root, name) != observed_file
                ):
                    raise ValueError("Native palette read differs from its bound input snapshot")
                metadata["files"][name] = observed_file
                metadata["files"][before["palette_run"]] = final_palette
                metadata["palette_read"] = (
                    copy.deepcopy(observed["palette_reads"][0])
                    if observed["palette_reads"]
                    else None
                )
            for path in record["files"].values():
                name = self._name(path)
                metadata["files"][name] = _file(self.state.root, name)
            report_path = record["folder"] / (report["spec"]["output"]["stem"] + ".report.json")
            if report_path.stat().st_size > 20 * 1024 * 1024:
                raise ValueError("Native review report exceeds 20MiB")
            if json.loads(report_path.read_text(encoding="utf8")) != report:
                raise ValueError("Saved native report differs from the actual renderer response")
            metadata.update(
                report=copy.deepcopy(report),
                exit_code=exit_code,
                execution=copy.deepcopy(execution),
                exports_verified=bool(report.get("outputs")) and not export_errors,
            )
            return metadata
        except (OSError, ValueError, KeyError) as problem:
            return {"available": False, "error": str(problem)}

    def _selected(self, payload):
        if not isinstance(payload, dict) or set(payload) != self.selection_fields:
            raise ValueError("Choose an owned run and its renderer client and generation")
        identity, client, generation = (
            payload["run_id"],
            payload["render_client"],
            payload["render_generation"],
        )
        if (
            not isinstance(identity, str)
            or not isinstance(client, str)
            or not 1 <= len(identity) <= 128
            or not 1 <= len(client) <= 128
            or type(generation) is not int
            or not 0 <= generation <= 2**53 - 1
        ):
            raise ValueError("Choose a valid owned renderer revision")
        with self.state.lock:
            record = self.state.runs.get(identity)
            if (
                self.state.closing
                or record is None
                or record["client"] != client
                or record["generation"] != generation
                or self.state.generations.get(client) != generation
                or self.state.render_attempts.get(client) != record["attempt"]
            ):
                raise ValueError(
                    "Selected render is unavailable or stale; render the current figure"
                )
        return record

    def collect(self, payload):
        self._root()
        record = self._selected(payload)
        evidence = record.get("review_evidence", {})
        if not evidence.get("available"):
            raise ValueError(evidence.get("error", "No completed native evidence is available"))
        source = _execution_source()
        if source != evidence["execution_source"]:
            raise ValueError("Native execution sources changed; render the current figure")
        for name, expected in evidence["files"].items():
            if _file(self.state.root, name) != expected:
                raise ValueError(
                    "Native review input, program, report or export changed; render again"
                )
        report = evidence["report"]
        snapshot = {"id": "figure", "source_type": "spec", "input_coverage": "complete"}
        event = {
            "id": payload["run_id"],
            "result": {"execution_source": source, "snapshot": {"figures": [snapshot]}},
        }
        groups = _groups(report, snapshot, event, evidence["exports_verified"], source)
        groups["reproduction"].update(
            execution=copy.deepcopy(evidence["execution"]),
            source_data="Local full SHA256 before/after; producer reports a 16-hex-character prefix.",
            scope="Completed ephemeral editor execution; no saved paper history or new reproduction.",
        )
        accepted = (
            report["status"] == "passed"
            and evidence["exit_code"] == 0
            and evidence["exports_verified"]
            and groups["reproduction"]["runtime"].get("matches_current_source") is True
            and groups["reproduction"]["environment"].get("versions_match") is True
        )
        revision = _digest({"render": payload, "evidence": evidence})
        result = {
            "schema_version": 1,
            "source_kind": "editor-render",
            "query_status": "ok",
            "project_id": self.identity,
            "current_revision": revision,
            "history_integrity": "not_applicable_ephemeral_editor",
            "selection": {
                "event": None,
                "run": payload["run_id"],
                "state": "ephemeral_native_render",
            },
            "scope": "Actual completed native editor evidence; not a saved paper audit or scientific certification.",
            "figures": [
                {
                    "key": "figure",
                    "source_type": "spec",
                    "freshness": "unchanged",
                    "evidence_state": "ephemeral_native_render"
                    if accepted
                    else "ephemeral_needs_review",
                    "matches_latest_accepted_inputs": False,
                    "rerun_recommended": not accepted,
                    "execution_status": report["status"],
                    "policy": copy.deepcopy(report["policy"]),
                    "groups": groups,
                }
            ],
        }
        result["evidence_revision"] = _digest(result)
        self._root()
        if self._selected(payload) is not record or _execution_source() != source:
            raise ValueError("Native review context changed while collecting evidence")
        for name, expected in evidence["files"].items():
            if _file(self.state.root, name) != expected:
                raise ValueError("Native review files changed while collecting evidence")
        if self._selected(payload) is not record or _execution_source() != source:
            raise ValueError("Native review context changed while collecting evidence")
        return result

    def plan(self, provider, payload):
        if (
            set(payload)
            - self.selection_fields
            - {
                "client",
                "generation",
                "expected_revision",
                "figures",
                "question",
                "author_context",
                "structured_output",
            }
        ):
            raise ValueError("Choose native reviewer selection and author-context fields")
        plan = _EditorReviewPlan(self, provider, payload)
        if plan._binding != payload.get("expected_revision"):
            raise ValueError("Native review evidence changed since selection; refresh")
        return plan

    @staticmethod
    def document(plan):
        if not isinstance(plan, _EditorReviewPlan):
            raise TypeError("Choose an owned editor reviewer plan")
        document = {
            "schema_version": 1,
            "kind": "editor-figure-review-request",
            "replayable": False,
            "scope": "Ephemeral editor disclosure; cannot be restored as a saved paper CLI request.",
            "selection": {
                "render": copy.deepcopy(plan._render),
                "question": plan._question,
                "figures": list(plan._figures),
                "author_context": plan._context,
                "structured_output": plan._structured,
            },
            "disclosure": plan.disclosure(),
        }
        document["fingerprint"] = _digest(document)
        return document
