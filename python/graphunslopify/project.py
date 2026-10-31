"""Owned paper projects: shared intent, immutable audit history and input freshness."""

from __future__ import annotations

import copy
import csv
import hashlib
import json
import math
import os
import re
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path, PureWindowsPath

from .audit import _canonical, _digest, _spec, _validate_audit_report, audit, load_manifest
from .transport import local_request
from .workflow import _folder_name

DEFAULT_FOLDER = "graphunslopify-project"
KIND = "graphunslopify.paper-project"
EVENT = re.compile(r"[0-9]{8}-[a-f0-9]{32}")
MAX_SOURCE_BYTES = 20 * 1024 * 1024


class ProjectError(ValueError):
    """Project ownership, evidence or a requested change cannot be established."""


def _bytes(value) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False) + "\n").encode()


def _hash(value) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _execution_source() -> dict:
    """Bind local audit/compiler/scientific code without reading arbitrary inputs."""
    from . import _source_identity

    observed = _source_identity.current()
    if observed != _source_identity.IMPORTED_SOURCES:
        raise ProjectError(
            "Package sources changed since import; restart before reviewing or auditing."
        )
    return observed


def _inside(root: Path, name: str) -> Path:
    path = Path(name)
    if path.is_absolute() or PureWindowsPath(name).drive or "\\" in name or ".." in path.parts:
        raise ProjectError("Project evidence path must stay inside its owned folder.")
    part = root
    for component in path.parts:
        part /= component
        if part.is_symlink():
            raise ProjectError("Owned project evidence paths cannot be symlinks.")
    if not part.resolve().is_relative_to(root.resolve()):
        raise ProjectError("Project evidence path escapes its owned folder.")
    return part


def _atomic(root: Path, name: str, value) -> None:
    target = _inside(root, name)
    temporary = _inside(root, ".write-" + uuid.uuid4().hex)
    try:
        with temporary.open("xb") as handle:
            handle.write(_bytes(value))
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def _read(path: Path):
    if path.stat().st_size > MAX_SOURCE_BYTES:
        raise ProjectError("Project source/report exceeds the 20 MiB metadata limit.")
    return json.loads(path.read_text(encoding="utf8"))


def _source(path: str | Path) -> Path:
    source = Path(path).expanduser().resolve()
    if source.is_dir():
        source = (
            source / "project.json"
            if (source / "project.json").is_file()
            else source / DEFAULT_FOLDER / "project.json"
        )
    return source


def _owner(folder: Path) -> dict:
    value = _read(_inside(folder, "owner.json"))
    if (
        not isinstance(value, dict)
        or set(value) != {"kind", "project_id"}
        or value["kind"] != KIND
        or not isinstance(value["project_id"], str)
        or not re.fullmatch(r"[a-f0-9]{32}", value["project_id"])
    ):
        raise ProjectError("Choose an owned GraphUnslopify project folder.")
    return value


@lru_cache(maxsize=1)
def _shared_schema():
    from jsonschema import Draft7Validator

    properties = local_request("schema")["oneOf"][0]["properties"]
    style = copy.deepcopy(properties["style"])
    style.pop("required", None)
    output = {
        "type": "object",
        "additionalProperties": False,
        "properties": {key: properties["output"]["properties"][key] for key in ("size", "dpi")},
    }
    return Draft7Validator(
        {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "style": style,
                "output": output,
                "palette_lock": {"type": "string", "minLength": 1},
            },
        }
    )


def _validate_shared(value) -> None:
    _bytes(value)
    errors = sorted(_shared_schema().iter_errors(value), key=lambda e: str(e.path))
    if errors:
        raise ProjectError(
            "Invalid shared settings: "
            + "; ".join(f"{'/'.join(map(str, e.path))}: {e.message}" for e in errors)
        )
    if "palette_lock" in value and "://" in value["palette_lock"]:
        raise ProjectError("Project palette locks must be local files.")


def _config(path: str | Path) -> tuple[Path, dict]:
    source = _source(path)
    owner = _owner(source.parent)
    value = _read(_inside(source.parent, source.name))
    if (
        not isinstance(value, dict)
        or set(value) != {"schema_version", "kind", "project_id", "manifest", "shared"}
        or value.get("schema_version") != 1
        or value.get("kind") != KIND
        or value.get("project_id") != owner["project_id"]
        or not isinstance(value.get("manifest"), str)
        or Path(value["manifest"]).parts[:1] != ("..",)
        or len(Path(value["manifest"]).parts) != 2
        or "\\" in value["manifest"]
    ):
        raise ProjectError(
            "Invalid project.json; preserve its owner and relative manifest reference."
        )
    _validate_shared(value["shared"])
    if (source.parent / value["manifest"]).resolve().parent != source.parent.parent:
        raise ProjectError("Project manifest must remain beside its owned project folder.")
    return source, value


@contextmanager
def _operation(folder: Path):
    lock = _inside(folder, ".operation.lock")
    token = uuid.uuid4().hex
    try:
        with lock.open("x", encoding="utf8") as handle:
            handle.write(json.dumps({"token": token, "pid": os.getpid()}))
    except FileExistsError as problem:
        raise ProjectError(
            "Project operation is locked. Check the owning process before removing a stale .operation.lock."
        ) from problem
    try:
        yield
    finally:
        try:
            value = _read(lock) if lock.is_file() and not lock.is_symlink() else None
            if isinstance(value, dict) and value.get("token") == token:
                lock.unlink()
        except (OSError, ValueError):
            pass  # Never erase a replaced/corrupt lock or hide the primary result.


def initialize_project(path: str | Path = ".", *, folder: str = DEFAULT_FOLDER) -> dict:
    source, _ = load_manifest(path)
    folder = _folder_name(folder)
    target = source.parent / folder
    target.mkdir(exist_ok=False)
    owner = {"kind": KIND, "project_id": uuid.uuid4().hex}
    (target / "owner.json").write_bytes(_bytes(owner))
    config = {"schema_version": 1, **owner, "manifest": "../" + source.name, "shared": {}}
    (target / "project.json").write_bytes(_bytes(config))
    (target / ".gitignore").write_text("history/\n.operation.lock\n.write-*\n", encoding="utf8")
    (target / "README.md").write_text(
        "# Paper project\n\nThe original manifest/specs/data remain authoritative.\n"
        "Use project-status, project-run and project-history with this folder.\n"
        "Shared settings live in project.json; change them with a current revision token.\n"
        "History is local and includes source definitions/reports/exports, not raw dataset copies.\n"
        "Selected scripts execute as trusted Python during an explicit audit.\n"
        "A stored result does not verify later edits or untracked dependencies.\n",
        encoding="utf8",
    )
    return {"project_id": owner["project_id"], "config": str(target / "project.json")}


def _locator(path: Path, paper: Path) -> str:
    path = path.resolve()
    return path.relative_to(paper).as_posix() if path.is_relative_to(paper) else str(path)


def _capture(source: Path, config: dict) -> tuple[dict, dict, dict[str, bytes]]:
    config_raw = source.read_bytes()
    if json.loads(config_raw) != config:
        raise ProjectError("Project settings changed during capture; refresh and retry.")
    manifest_path, manifest = load_manifest(source.parent / config["manifest"])
    paper = manifest_path.parent
    raw = manifest_path.read_bytes()
    if json.loads(raw) != manifest:
        raise ProjectError("Manifest changed while being read; retry from current inputs.")
    originals = {"source/manifest.json": raw, "source/project.json": config_raw}
    rows, effective = [], []
    for index, entry in enumerate(manifest["figures"]):
        row = {
            "id": entry["id"],
            "kind": None,
            "source_type": "spec" if "spec" in entry else "script",
            "files": [],
            "errors": [],
            "input_coverage": "declared",
        }

        def file(role, path, *, keep=False, row=row, index=index):
            path = Path(path).resolve()
            record = {"role": role, "path": _locator(path, paper), "sha256": None}
            try:
                if keep:
                    if path.stat().st_size > MAX_SOURCE_BYTES:
                        raise ProjectError("Source definition exceeds 20 MiB.")
                    data = path.read_bytes()
                    record["sha256"] = hashlib.sha256(data).hexdigest()
                    originals[f"source/{index:04d}." + ("json" if role == "spec" else "py")] = data
                else:
                    record["sha256"] = _digest(path)
            except (OSError, ValueError) as problem:
                row["errors"].append(f"{role}: {type(problem).__name__}: {problem}")
            row["files"].append(record)
            return record["sha256"]

        normalized = copy.deepcopy(entry)
        if "artifacts" in entry:
            normalized["artifacts"] = [str((paper / name).resolve()) for name in entry["artifacts"]]
            for name in entry["artifacts"]:
                file("published", paper / name)
        if "data" in entry:
            normalized["data"] = str((paper / entry["data"]).resolve())
        if "spec" in entry:
            if isinstance(entry["spec"], str):
                normalized["spec"] = str((paper / entry["spec"]).resolve())
                original_sha = file("spec", paper / entry["spec"], keep=True)
            else:
                original_sha = _hash(entry["spec"])
            try:
                spec, observed_sha = _spec(entry, paper)
                if original_sha != observed_sha:
                    raise ProjectError("Figure definition changed during capture; retry.")
                row["kind"] = spec.get("kind")
                for key in ("style", "output"):
                    if key in config["shared"]:
                        spec[key] = {**spec.get(key, {}), **config["shared"][key]}
                if "palette_lock" in config["shared"]:
                    spec["palette_lock"] = str((paper / config["shared"]["palette_lock"]).resolve())
                file("data", Path(spec["data"]["path"]))
                if spec.get("palette_lock"):
                    file("palette", Path(spec["palette_lock"]))
                normalized = {
                    "id": entry["id"],
                    "spec": spec,
                    **({"artifacts": normalized["artifacts"]} if "artifacts" in normalized else {}),
                }
            except (OSError, ValueError, TypeError) as problem:
                row["errors"].append(f"spec: {type(problem).__name__}: {problem}")
        else:
            normalized["script"] = str((paper / entry["script"]).resolve())
            normalized["cwd"] = str(
                (paper / entry.get("cwd", str(Path(normalized["script"]).parent))).resolve()
            )
            file("script", Path(normalized["script"]), keep=True)
            if "data" in entry:
                file("data", paper / entry["data"])
            else:
                row["input_coverage"] = "unknown_script_inputs"
            if "palette_lock" in config["shared"]:
                file("palette", paper / config["shared"]["palette_lock"])
        row["fingerprint"] = _hash(
            {"entry": entry, "files": row["files"], "shared": config["shared"]}
        )
        rows.append(row)
        effective.append(normalized)
    snapshot = {
        "manifest": manifest_path.name,
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "project_id": config["project_id"],
        "shared": config["shared"],
        "figures": rows,
    }
    if (
        _digest(source) != hashlib.sha256(config_raw).hexdigest()
        or _digest(manifest_path) != hashlib.sha256(raw).hexdigest()
    ):
        raise ProjectError("Project settings/manifest changed during capture; retry.")
    snapshot["revision"] = _hash(
        {**snapshot, "config_sha256": hashlib.sha256(config_raw).hexdigest()}
    )
    return snapshot, {"schema_version": 1, "figures": effective}, originals


def _event(folder: Path, action: str) -> tuple[Path, dict]:
    history = _inside(folder, "history")
    history.mkdir(exist_ok=True)
    sequence = (
        max((int(p.name[:8]) for p in history.iterdir() if EVENT.fullmatch(p.name)), default=0) + 1
    )
    identity = f"{sequence:08d}-" + uuid.uuid4().hex
    target = _inside(history, identity)
    target.mkdir(exist_ok=False)
    record = {
        "schema_version": 1,
        "project_id": _owner(folder)["project_id"],
        "id": identity,
        "sequence": sequence,
        "action": action,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (target / "started.json").write_bytes(_bytes(record))
    return target, record


def _finish(folder: Path, record: dict, result: dict, originals: dict[str, bytes]) -> dict:
    inventory = []
    for name, data in {**originals, "result.json": _bytes(result)}.items():
        path = _inside(folder, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as handle:
            handle.write(data)
        inventory.append(
            {"path": name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
        )
    if result.get("audit") is not None:
        path = _inside(folder, "audit/audit.report.json")
        inventory.append(
            {
                "path": "audit/audit.report.json",
                "sha256": _digest(path),
                "bytes": path.stat().st_size,
            }
        )
    # Receipt is the commit marker: partial/interrupted work never looks complete.
    _atomic(folder, "receipt.json", {**record, "files": inventory})
    return {**record, **result, "directory": str(folder)}


def project_history(path: str | Path = ".") -> dict:
    source = _source(path)
    owner = _owner(source.parent)
    root = _inside(source.parent, "history")
    records = []
    for candidate in sorted(root.iterdir(), reverse=True) if root.exists() else []:
        if not EVENT.fullmatch(candidate.name):
            continue
        item = {
            "id": candidate.name,
            "sequence": int(candidate.name[:8]),
            "phase": "incomplete",
            "integrity": False,
            "errors": [],
        }
        try:
            folder = _inside(root, candidate.name)
            if not (folder / "receipt.json").exists():
                item["errors"].append(
                    "No completed receipt; work may be interrupted or still in progress."
                )
            else:
                receipt = _read(_inside(folder, "receipt.json"))
                if not isinstance(receipt, dict) or (
                    receipt.get("project_id") != owner["project_id"]
                    or receipt.get("id") != folder.name
                    or receipt.get("sequence") != item["sequence"]
                    or receipt.get("action") not in ("run", "settings", "figure", "entry")
                ):
                    raise ProjectError("Receipt ownership does not match this project/event.")
                names = set()
                for entry in receipt["files"]:
                    target = _inside(folder, entry["path"])
                    if (
                        entry["path"] in names
                        or target.stat().st_size != entry["bytes"]
                        or _digest(target) != entry["sha256"]
                    ):
                        raise ProjectError(
                            "Saved event evidence changed; restore matching files before using it."
                        )
                    names.add(entry["path"])
                if "result.json" not in names:
                    raise ProjectError("Receipt does not identify its result snapshot.")
                result = _read(folder / "result.json")
                if (
                    not isinstance(result, dict)
                    or type(result.get("exit_code")) is not int
                    or result["exit_code"] not in (0, 2)
                ):
                    raise ProjectError("Saved result is not a completed project operation.")
                if result.get("audit") is not None:
                    _validate_audit_report(result["audit"], "project history")
                    if (
                        "audit/audit.report.json" not in names
                        or _read(folder / "audit/audit.report.json") != result["audit"]
                    ):
                        raise ProjectError("Saved aggregate audit and result disagree.")
                item.update(**receipt, result=result, phase="complete", integrity=True)
        except (OSError, ValueError, KeyError, TypeError) as problem:
            item["phase"] = "damaged"
            item["errors"].append(f"{type(problem).__name__}: {problem}")
        records.append(item)
    return {
        "project_id": owner["project_id"],
        "events": records,
        "integrity": "verified" if all(x["integrity"] for x in records) else "partial",
        "exit_code": 0 if all(x["integrity"] for x in records) else 2,
    }


def project_status(path: str | Path = ".") -> dict:
    source, config = _config(path)
    snapshot, _, _ = _capture(source, config)
    history = project_history(source)
    rows = []
    for current in snapshot["figures"]:
        row = {
            **copy.deepcopy(current),
            "freshness": "not_run",
            "last_run": None,
            "last_status": "not_run",
            "last_accepted": False,
        }
        for event in history["events"]:
            if not event["integrity"] or event.get("action") != "run":
                continue
            previous = next(
                (
                    x
                    for x in (event["result"].get("snapshot") or {}).get("figures", [])
                    if x["id"] == current["id"]
                ),
                None,
            )
            if previous is None:
                row["last_run"] = event["id"]
                if event["result"].get("snapshot") is None:
                    row["errors"].append(
                        "The latest paper audit did not reach figure execution; review its setup errors and rerun."
                    )
                break
            audited = next(
                (
                    x
                    for x in (event["result"].get("audit") or {}).get("figures", [])
                    if x["id"] == current["id"]
                ),
                None,
            )
            row.update(
                last_run=event["id"],
                last_status=audited["status"] if audited else "not_run",
                last_accepted=bool(
                    audited
                    and audited["status"] == "passed"
                    and not event["result"].get("policy_errors", {}).get(current["id"])
                    and event["result"]["exit_code"] == 0
                ),
            )
            row["freshness"] = (
                "changed"
                if current["fingerprint"] != previous["fingerprint"]
                else "unknown"
                if current["input_coverage"] != "declared"
                else "unchanged"
            )
            if any(
                not x["integrity"] and x["sequence"] > event["sequence"] for x in history["events"]
            ):
                row["errors"].append(
                    "A newer history event is incomplete/damaged; review it before using an older result."
                )
            try:
                for output in (audited or {}).get("outputs", []):
                    target = _inside(
                        source.parent, f"history/{event['id']}/audit/" + output["path"]
                    )
                    if (
                        target.stat().st_size != output["bytes"]
                        or _digest(target) != output["sha256"]
                    ):
                        raise ProjectError("Saved figure export changed since its audit.")
                row["artifacts_verified"] = bool(audited and audited["outputs"])
            except (OSError, ValueError) as problem:
                row["errors"].append(str(problem))
                row["artifacts_verified"] = False
            break
        if row["errors"]:
            row["freshness"] = "unavailable"
        rows.append(row)
    latest = next(
        (x for x in history["events"] if x["integrity"] and x.get("action") == "run"), None
    )
    revision_matches = bool(
        latest and (latest["result"].get("snapshot") or {}).get("revision") == snapshot["revision"]
    )
    matches = revision_matches and all(
        x["freshness"] == "unchanged" and x["last_accepted"] and x.get("artifacts_verified")
        for x in rows
    )
    return {
        "schema_version": 1,
        "project_id": config["project_id"],
        "config": str(source),
        "revision": snapshot["revision"],
        "shared": config["shared"],
        "figures": rows,
        "status": "inputs_match_last_run" if matches else "needs_audit",
        "history_integrity": history["integrity"],
        "history_count": len(history["events"]),
        "matches_last_run_revision": revision_matches,
    }


def _expected(expected: str | None, snapshot: dict) -> None:
    if expected is not None and expected != snapshot["revision"]:
        raise ProjectError(
            "Project inputs/settings changed since review; refresh before applying this action."
        )


def _review_token(value: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ProjectError("Changes need the current project-status revision token.")


def _authoring_target(source: Path, target: Path, snapshot: dict) -> Path:
    paper = source.parent.parent
    if not target.absolute().is_relative_to(paper):
        raise ProjectError("Definitions outside the paper folder are read-only here.")
    target = _inside(paper, target.absolute().relative_to(paper).as_posix())
    if target.is_relative_to(source.parent):
        raise ProjectError(
            "Owned project configuration and saved history cannot be definition targets."
        )
    protected = {
        (paper / item["path"]).resolve()
        for row in snapshot["figures"]
        for item in row["files"]
        if item["role"] != "spec"
    }
    if target.resolve() in protected:
        raise ProjectError(
            "This path is also a data, palette, script or published-artifact input; change its manifest binding instead."
        )
    return target


def project_figure(path: str | Path, identity: str) -> dict:
    """Return one captured authoring definition without importing a selected script."""
    source, config = _config(path)
    snapshot, effective, originals = _capture(source, config)
    manifest = json.loads(originals["source/manifest.json"])
    index = next(
        (i for i, entry in enumerate(manifest["figures"]) if entry["id"] == identity), None
    )
    if index is None:
        raise ProjectError("Choose a figure ID in the current manifest.")
    entry = manifest["figures"][index]
    paper = source.parent.parent
    script = "script" in entry
    filename = (
        entry.get("script") if script else entry["spec"] if isinstance(entry["spec"], str) else None
    )
    raw = (
        originals.get(f"source/{index:04d}." + ("py" if script else "json"))
        if filename
        else _bytes(entry["spec"])
    )
    reason = (
        "Authored Python is read-only here; update its source deliberately, then audit again."
        if script
        else ""
    )
    if filename and not script:
        try:
            _authoring_target(source, paper / filename, snapshot)
        except ProjectError as problem:
            reason = str(problem)
    normalized = effective["figures"][index]
    clone = copy.deepcopy(entry)
    clone.pop("artifacts", None)
    effective_spec = normalized.get("spec")
    data_spec = effective_spec.get("data") if isinstance(effective_spec, dict) else None
    if not script and isinstance(data_spec, dict) and isinstance(data_spec.get("path"), str):
        spec = copy.deepcopy(normalized["spec"])
        spec["data"]["path"] = _locator(Path(spec["data"]["path"]), paper)
        if spec.get("palette_lock"):
            spec["palette_lock"] = _locator(Path(spec["palette_lock"]), paper)
        clone = {"id": identity, "spec": spec}
    hints = set()
    actual = normalized.get("spec")
    if isinstance(actual, dict):
        declared = data_spec.get("columns") if isinstance(data_spec, dict) else None
        if isinstance(declared, list):
            hints.update(value for value in declared if isinstance(value, str))
        for key in ("x", "y"):
            axis = actual.get(key)
            if isinstance(axis, dict) and isinstance(axis.get("field"), str):
                hints.add(axis["field"])
        if isinstance(actual.get("group"), str):
            hints.add(actual["group"])
        data = (
            Path(data_spec["path"])
            if isinstance(data_spec, dict) and isinstance(data_spec.get("path"), str)
            else None
        )
        if data is not None and data.suffix.lower() == ".csv":
            try:
                with data.open(encoding="utf-8-sig", newline="") as handle:
                    hints.update(next(csv.reader(handle), []))
            except (OSError, ValueError, csv.Error):
                pass  # Hints are optional; captured source errors remain explicit.
    return {
        "id": identity,
        "revision": snapshot["revision"],
        "entry": entry,
        "source_type": "script" if script else "spec",
        "source": filename or "inline in " + config["manifest"],
        "text": raw.decode("utf8") if raw is not None else "",
        "editable": not reason,
        "reason": reason,
        "errors": snapshot["figures"][index]["errors"],
        "clone": clone,
        "shared_by": [
            row["id"]
            for row in snapshot["figures"]
            if filename
            and any(
                item["role"] == ("script" if script else "spec")
                and Path(item["path"]) == Path(_locator(paper / filename, paper))
                for item in row["files"]
            )
        ],
        "columns": sorted(value for value in hints if isinstance(value, str)),
    }


def _write_authoring(paper: Path, target: Path, content: bytes, expected_sha: str | None) -> None:
    # Optimistic guards cover cooperative writers; this is not a filesystem CAS.
    target = _inside(paper, target.relative_to(paper).as_posix())
    current = _digest(target) if target.is_file() else None
    if current != expected_sha or (target.exists() and not target.is_file()):
        raise ProjectError("Definition changed since capture; refresh before saving.")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.parent / (".graphunslopify-write-" + uuid.uuid4().hex)
    try:
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def _edit_definition(path, identity, value, *, expected_revision, entry_mode=None):
    _review_token(expected_revision)
    source, config = _config(path)
    with _operation(source.parent):
        before, _, originals = _capture(source, config)
        _expected(expected_revision, before)
        manifest = json.loads(originals["source/manifest.json"])
        index = next(
            (i for i, item in enumerate(manifest["figures"]) if item["id"] == identity), None
        )
        paper = source.parent.parent
        target = paper / before["manifest"]
        expected_sha = before["manifest_sha256"]
        if entry_mode is not None:
            if entry_mode not in ("add", "update", "remove"):
                raise ProjectError("Choose add, update or remove for a manifest binding.")
            if (index is None) != (entry_mode == "add"):
                raise ProjectError(
                    "The figure ID is missing or already exists; refresh the manifest."
                )
            if entry_mode == "remove":
                manifest["figures"].pop(index)
            else:
                if not isinstance(value, dict) or value.get("id") != identity:
                    raise ProjectError("Keep the stable figure ID; use a new ID when duplicating.")
                if index is None:
                    manifest["figures"].append(copy.deepcopy(value))
                else:
                    manifest["figures"][index] = copy.deepcopy(value)
        else:
            if index is None or "spec" not in manifest["figures"][index]:
                raise ProjectError(
                    "Choose a JSON figure definition; authored scripts stay read-only."
                )
            if not isinstance(value, dict):
                raise ProjectError("A figure definition must be a JSON object.")
            checked = local_request("convert", value)
            if not checked.get("ok"):
                raise ProjectError("Correct the figure definition before saving: " + str(checked))
            old = manifest["figures"][index]
            if isinstance(old["spec"], str):
                target = _authoring_target(source, paper / old["spec"], before)
                expected_sha = next(
                    x["sha256"] for x in before["figures"][index]["files"] if x["role"] == "spec"
                )
            else:
                old["spec"] = copy.deepcopy(value)
        if target == paper / before["manifest"]:
            from importlib.resources import files

            from jsonschema import Draft202012Validator

            schema = json.loads(
                files("graphunslopify").joinpath("schemas/manifest.schema.json").read_text()
            )
            problems = list(Draft202012Validator(schema).iter_errors(manifest))
            ids = [item["id"] for item in manifest["figures"]]
            if problems or len(ids) != len(set(ids)):
                raise ProjectError(
                    "Invalid manifest binding: "
                    + (problems[0].message if problems else "duplicate figure ID")
                )
            content = _bytes(manifest)
            target = _authoring_target(source, target, before)
        else:
            content = _bytes(value)
        if len(content) > MAX_SOURCE_BYTES:
            raise ProjectError("Definition exceeds the 20 MiB authoring limit.")
        folder, event = _event(source.parent, "entry" if entry_mode else "figure")
        _write_authoring(paper, target, content, expected_sha)
        after, _, _ = _capture(source, config)
        return _finish(
            folder,
            event,
            {
                "status": "definition_saved",
                "exit_code": 0,
                "before": before,
                "snapshot": after,
                "audit": None,
                "figure_id": identity,
                "change": entry_mode or "definition",
            },
            originals,
        )


def set_project_figure(path, identity: str, spec: dict, *, expected_revision: str) -> dict:
    """Save a reviewed JSON definition and retain its previous captured source."""
    return _edit_definition(path, identity, spec, expected_revision=expected_revision)


def set_project_entry(
    path, identity: str, entry: dict | None, *, expected_revision: str, mode="update"
) -> dict:
    """Add/update/remove a manifest binding; never delete source programs or data."""
    return _edit_definition(
        path, identity, entry, expected_revision=expected_revision, entry_mode=mode
    )


def set_project_shared(path: str | Path, shared: dict, *, expected_revision: str) -> dict:
    if not isinstance(expected_revision, str) or not re.fullmatch(
        r"[a-f0-9]{64}", expected_revision
    ):
        raise ProjectError("Shared changes need the current project-status revision token.")
    _validate_shared(shared)
    source, config = _config(path)
    with _operation(source.parent):
        before, _, originals = _capture(source, config)
        _expected(expected_revision, before)
        folder, event = _event(source.parent, "settings")
        updated = {**config, "shared": copy.deepcopy(shared)}
        _atomic(source.parent, source.name, updated)
        after, _, _ = _capture(source, updated)
        return _finish(
            folder,
            event,
            {
                "status": "settings_saved",
                "exit_code": 0,
                "before": before,
                "snapshot": after,
                "audit": None,
            },
            originals,
        )


def _policy(report: dict, config: dict, paper: Path, manifest: dict) -> dict:
    errors = {}
    entries = {x["id"]: x for x in manifest["figures"]}
    for figure in report["figures"]:
        if not figure.get("report"):
            continue
        spec = (figure.get("report") or {}).get("spec", {})
        issues = []
        for key in ("style", "output"):
            for name, value in config["shared"].get(key, {}).items():
                if spec.get(key, {}).get(name) != value:
                    issues.append(
                        f"Shared {key}.{name} requires {value!r}; regenerate the authored program or update its settings."
                    )
        if "palette_lock" in config["shared"]:
            try:
                actual = spec.get("palette_lock")
                entry = entries[figure["id"]]
                base = Path(entry.get("cwd", paper)) if "script" in entry else paper
                if not actual or _digest(base / actual) != _digest(
                    paper / config["shared"]["palette_lock"]
                ):
                    raise ProjectError("Palette lock differs.")
            except (OSError, ValueError):
                issues.append(
                    "Shared palette lock is unavailable or does not match the recorded spec; regenerate/recheck this figure."
                )
        if issues:
            errors[figure["id"]] = issues
    return errors


def run_project(
    path: str | Path = ".",
    *,
    expected_revision: str | None = None,
    baseline: str | None = "latest",
    fail_on_warning: bool = False,
    fail_on_change: bool = False,
    timeout: float = 120,
) -> dict:
    if not math.isfinite(timeout) or timeout <= 0:
        raise ProjectError("Project audit timeout must be finite and positive.")
    source, config = _config(path)
    with _operation(source.parent):
        try:
            snapshot, effective, originals = _capture(source, config)
        except (OSError, ValueError, KeyError, TypeError) as problem:
            folder, event = _event(source.parent, "run")
            originals = {"source/project.json": source.read_bytes()}
            manifest = source.parent / config["manifest"]
            if manifest.is_file() and manifest.stat().st_size <= MAX_SOURCE_BYTES:
                originals["source/manifest.json"] = manifest.read_bytes()
            return _finish(
                folder,
                event,
                {
                    "status": "failed",
                    "audit_status": "not_run",
                    "exit_code": 2,
                    "snapshot": None,
                    "audit": None,
                    "errors": [f"{type(problem).__name__}: {problem}"],
                    "policy_errors": {},
                    "baseline": None,
                },
                originals,
            )
        _expected(expected_revision, snapshot)
        history = project_history(source)
        previous = None
        if baseline is not None:
            candidates = [
                x
                for x in history["events"]
                if x["integrity"] and x.get("action") == "run" and x["result"].get("audit")
            ]
            previous = next(
                (x for x in candidates if baseline == "latest" or x["id"] == baseline), None
            )
            if baseline != "latest" and previous is None:
                raise ProjectError(
                    "Choose a completed, intact baseline run ID from project-history."
                )
            if baseline == "latest" and any(
                not x["integrity"] and (previous is None or x["sequence"] > previous["sequence"])
                for x in history["events"]
            ):
                raise ProjectError(
                    "Latest history is incomplete/damaged; repair it or explicitly run with no baseline."
                )
        execution_source = _execution_source()
        folder, event = _event(source.parent, "run")
        result = {
            "status": "failed",
            "audit_status": "not_run",
            "exit_code": 2,
            "snapshot": snapshot,
            "audit": None,
            "errors": [],
            "policy_errors": {},
            "baseline": previous["id"] if previous else None,
            "execution_source": execution_source,
        }
        try:
            manifest_path = _inside(folder, "effective.manifest.json")
            manifest_path.write_bytes(_bytes(effective))
            old_root = (
                _inside(source.parent, "history/" + previous["id"] + "/audit") if previous else None
            )
            report = audit(
                manifest_path,
                output=_inside(folder, "audit"),
                baseline=old_root / "audit.report.json" if old_root else None,
                baseline_root=old_root,
                fail_on_warning=fail_on_warning,
                fail_on_change=fail_on_change,
                timeout=timeout,
            )
            result.update(
                audit=report,
                audit_status=report["status"],
                status=report["status"],
                exit_code=report["exit_code"],
            )
            if report["exit_code"]:
                result["status"] = "incomplete" if report["status"] == "incomplete" else "failed"
            result["policy_errors"] = _policy(report, config, source.parent.parent, effective)
            captured = {row["id"]: row for row in snapshot["figures"]}
            for figure in report["figures"]:
                declared = next(
                    (x["sha256"] for x in captured[figure["id"]]["files"] if x["role"] == "data"),
                    None,
                )
                if declared and figure.get("data") and figure["data"]["sha256"] != declared:
                    result["policy_errors"].setdefault(figure["id"], []).append(
                        "Audited data bytes differ from the captured project inputs; refresh and rerun."
                    )
            after, _, _ = _capture(source, config)
            if snapshot["revision"] != after["revision"]:
                result["errors"].append(
                    "Project inputs changed during auditing; refresh and rerun before acceptance."
                )
            if execution_source != _execution_source():
                result["errors"].append(
                    "Audit/compiler sources changed during execution; rerun before acceptance."
                )
            if any(row["errors"] for row in snapshot["figures"]):
                result["errors"].append(
                    "Some declared input evidence was unavailable at capture; inspect per-figure snapshot errors."
                )
            if result["errors"] or result["policy_errors"]:
                result.update(status="failed", exit_code=2)
        except (OSError, ValueError, KeyError, TypeError) as problem:
            result["errors"].append(f"{type(problem).__name__}: {problem}")
            result.update(status="failed", exit_code=2)
        return _finish(
            folder,
            event,
            result,
            {**originals, "source/effective.manifest.json": _bytes(effective)},
        )
