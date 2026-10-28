"""Manifest-based local figure auditing and evidence comparison."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from PIL import Image

from .build import Figure, _relative_path
from .provenance import read_provenance


class AuditError(ValueError):
    """The manifest or comparison evidence is invalid."""


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf8"))


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False
    )


def _pixel_hash(path: Path) -> str:
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        return hashlib.sha256(str(rgba.size).encode() + rgba.tobytes()).hexdigest()


def _semantic_spec(spec: dict[str, Any]) -> dict[str, Any]:
    result = json.loads(json.dumps(spec))
    if not isinstance(result, dict) or not isinstance(result.get("data", {}), dict):
        raise AuditError("provenance spec/data must be objects")
    result.get("data", {}).pop("path", None)
    result.pop("palette_lock", None)
    return result


def load_manifest(path: str | Path) -> tuple[Path, dict[str, Any]]:
    source = Path(path).expanduser().resolve()
    if source.is_dir():
        source /= "graphunslopify.json"
    manifest = _json(source)
    from importlib.resources import files

    from jsonschema import Draft202012Validator

    schema = json.loads(
        files("graphunslopify").joinpath("schemas/manifest.schema.json").read_text()
    )
    problems = sorted(Draft202012Validator(schema).iter_errors(manifest), key=lambda e: str(e.path))
    if problems:
        raise AuditError(
            "; ".join(f"{'/'.join(map(str, e.path)) or '(root)'}: {e.message}" for e in problems)
        )
    ids = [entry["id"] for entry in manifest["figures"]]
    if len(ids) != len(set(ids)):
        raise AuditError("figure IDs must be unique")
    return source, manifest


def _spec(entry: dict[str, Any], root: Path) -> tuple[dict[str, Any], str]:
    value = entry["spec"]
    if isinstance(value, str):
        path = (root / value).resolve()
        spec, base = _json(path), path.parent
        source_hash = _digest(path)
    else:
        spec, base = json.loads(json.dumps(value)), root
        source_hash = hashlib.sha256(_canonical(spec).encode()).hexdigest()
    if not isinstance(spec, dict):
        raise AuditError("figure spec must be an object")
    data = spec.setdefault("data", {})
    if not isinstance(data, dict):
        raise AuditError("spec.data must be an object")
    data_name = entry.get("data", data.get("path", "results.csv"))
    if not isinstance(data_name, str) or "://" in data_name:
        raise AuditError("manifest auditing requires a local data file")
    data["path"] = str(
        ((root if "data" in entry else base) / Path(data_name).expanduser()).resolve()
    )
    if "claims" in entry:
        spec["claims"] = entry["claims"]
    if spec.get("palette_lock"):
        spec["palette_lock"] = str((base / spec["palette_lock"]).resolve())
    return spec, source_hash


def _input_data(path: Path, data_format: str) -> dict[str, Any]:
    import pandas as pd

    readers = {"csv": pd.read_csv, "json": pd.read_json, "parquet": pd.read_parquet}
    frame = readers[data_format](path)
    numeric = frame.select_dtypes(include="number")
    # Hash exact binary float representations, not rounded display values. Row order
    # and inferred integer/float encodings/column names are part of this representation.
    encoded = numeric.to_csv(
        index=False, float_format=lambda number: float(number).hex(), lineterminator="\n"
    )
    return {
        "sha256": _digest(path),
        "numeric_sha256": hashlib.sha256(encoded.encode("utf8")).hexdigest()
        if len(numeric.columns)
        else None,
        "rows": len(frame),
        "numeric_columns": len(numeric.columns),
    }


def _outputs(
    report: dict[str, Any], folder: Path, output_root: Path, *, require_all: bool = True
) -> list[dict[str, Any]]:
    result = []
    for item in report.get("outputs", []):
        path = (folder / item["path"]).resolve()
        if not path.is_relative_to(folder):
            raise AuditError("reported output escapes the figure audit directory")
        digest = _digest(path)
        if digest != item["sha256"] or path.stat().st_size != item["bytes"]:
            raise AuditError(f"output bytes do not match the runtime report: {path.name}")
        record = {**item, "path": path.relative_to(output_root).as_posix(), "pixels_sha256": None}
        if path.suffix.lower() == ".png":
            record["pixels_sha256"] = _pixel_hash(path)
        if path.suffix.lower() in {".png", ".svg", ".pdf", ".html", ".htm"}:
            evidence = read_provenance(path)
            if (
                evidence["schema_version"] != 1
                or evidence["spec_hash"] != report["spec_hash"]
                or evidence["data_sha256_prefix"] != report["data"]["sha256_prefix"]
                or evidence["script_sha256"] != report.get("script", {}).get("sha256")
                or evidence.get("environment") != report.get("environment")
            ):
                raise AuditError(
                    f"output provenance does not match the runtime report: {path.name}"
                )
        result.append(record)
    if not result:
        raise AuditError("no output artifacts were verified")
    spec = report["spec"]
    expected = set(spec.get("output", {}).get("formats", []))
    if spec.get("output", {}).get("interactive"):
        expected.add("html")
    if spec.get("animate"):
        expected.add(spec["animate"].get("format", "gif"))
    missing = expected - {item["format"] for item in result}
    if missing and require_all:
        raise AuditError("requested output artifacts are missing: " + ", ".join(sorted(missing)))
    return result


def _validate_report(report: Any) -> None:
    from importlib.resources import files

    from jsonschema import Draft202012Validator

    schema = json.loads(
        files("graphunslopify").joinpath("schemas/runtime-report.schema.json").read_text()
    )
    problems = list(Draft202012Validator(schema).iter_errors(report))
    if problems:
        raise AuditError("invalid runtime report: " + problems[0].message)


def _run(command: list[str], folder: Path, timeout: float) -> subprocess.CompletedProcess[str]:
    options: dict[str, Any] = (
        {"start_new_session": True}
        if os.name != "nt"
        else {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    )
    with subprocess.Popen(
        command,
        cwd=folder,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf8",
        env={**os.environ, "MPLBACKEND": "Agg", "PYTHONIOENCODING": "utf-8"},
        **options,
    ) as process:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    check=False,
                )
            else:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
            process.kill()
            process.communicate()
            raise
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def _audit_one(
    entry: dict[str, Any], root: Path, output: Path, *, fail_on_warning: bool, timeout: float
) -> dict[str, Any]:
    folder = output / "figures" / entry["id"]
    # Each audit uses a fresh owned run directory; inputs and old evidence survive.
    folder.mkdir(parents=True)
    record: dict[str, Any] = {
        "id": entry["id"],
        "status": "failed",
        "errors": [],
        "warnings": [],
        "report": None,
        "outputs": [],
        "artifacts": [],
    }
    try:
        if "spec" in entry:
            spec, source_hash = _spec(entry, root)
            record["source_sha256"] = source_hash
            (folder / "input.spec.json").write_text(json.dumps(spec, indent=2), encoding="utf8")
            spec["data"]["path"] = _relative_path(spec["data"]["path"], folder)
            translated = Figure(spec).translate(api="local")
            record["static_findings"] = translated.get("findings", [])
            if not translated.get("ok"):
                raise AuditError("static errors: " + json.dumps(record["static_findings"]))
            script = folder / "figure.py"
            script.write_text(translated["code"], encoding="utf8")
            command = [
                sys.executable,
                str(script),
                "--strict",
                "--json",
                "--report",
                "runtime.report.json",
            ]
        else:
            script = (root / entry["script"]).resolve()
            record["source_sha256"] = _digest(script)
            shutil.copyfile(script, folder / "source.py")
            command = [
                sys.executable,
                "-m",
                "graphunslopify.audit_worker",
                str(script),
                str((root / entry.get("cwd", str(script.parent))).resolve()),
                str(folder),
            ]
        if fail_on_warning:
            command.append("--fail-on-warning")
        completed = _run(command, folder, timeout)
        (folder / "stdout.log").write_text(completed.stdout, encoding="utf8")
        (folder / "stderr.log").write_text(completed.stderr, encoding="utf8")
        try:
            report = json.loads(completed.stdout)
            _validate_report(report)
        except (ValueError, KeyError) as problem:
            raise AuditError(
                f"program did not return a valid runtime report: {completed.stderr[-800:] or completed.stdout[-800:]}"
            ) from problem
        record["report"] = report
        if "script" in entry and report.get("script", {}).get("sha256") != record["source_sha256"]:
            raise AuditError("script source changed during auditing or does not match its report")
        record["status"] = report["status"]
        if completed.returncode and record["status"] == "passed":
            record["status"] = "failed"
            record["errors"].append(f"process exited {completed.returncode}")
        record["outputs"] = _outputs(report, folder, output)
        data = report["data"]
        data_path = Path(data["path"])
        data_path = data_path if data_path.is_absolute() else folder / data_path
        record["data"] = _input_data(data_path, report["spec"]["data"]["format"])
        if record["data"]["sha256"][:16] != data["sha256_prefix"]:
            raise AuditError("data changed during auditing or does not match the runtime report")
        if (
            "script" in entry
            and "data" in entry
            and _digest(root / entry["data"]) != record["data"]["sha256"]
        ):
            raise AuditError("declared data file does not match the script's actual input")
        record["semantic_spec"] = _semantic_spec(report["spec"])
        for name in entry.get("artifacts", []):
            path = (root / name).resolve()
            evidence = read_provenance(path)
            matches = (
                evidence["schema_version"] == 1
                and _semantic_spec(evidence["spec"]) == record["semantic_spec"]
                and evidence["data_sha256_prefix"] == data["sha256_prefix"]
            )
            pixels_match = None
            if path.suffix.lower() == ".png":
                fresh = next((item for item in record["outputs"] if item["format"] == "png"), None)
                if fresh:
                    pixels_match = _pixel_hash(path) == fresh["pixels_sha256"]
                    if not pixels_match:
                        record["warnings"].append(
                            f"published PNG pixels differ; source or rendering environment may differ: {name}"
                        )
            if "script" in entry and evidence.get("script_sha256") != record["source_sha256"]:
                matches = False
            record["artifacts"].append(
                {
                    "path": name,
                    "sha256": _digest(path),
                    "provenance_matches": matches,
                    "pixels_match": pixels_match,
                }
            )
            if not matches:
                raise AuditError(
                    f"published artifact is stale or lacks complete provenance: {name}"
                )
    except subprocess.TimeoutExpired:
        record["errors"].append(f"figure exceeded {timeout:g} seconds")
    except Exception as problem:  # noqa: BLE001 -- record each figure's failure and continue
        # Per-figure fault isolation: one bad input/plugin must not hide the rest.
        record["errors"].append(f"{type(problem).__name__}: {problem}")
    if record["errors"]:
        record["status"] = "failed"
    if fail_on_warning and record["warnings"]:
        record["status"] = "failed"
    return record


def compare_audits(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    from importlib.resources import files

    from jsonschema import Draft202012Validator

    schema = json.loads(
        files("graphunslopify").joinpath("schemas/audit-report.schema.json").read_text()
    )
    if list(Draft202012Validator(schema).iter_errors(before)):
        raise AuditError("baseline is not a valid version 1 audit report")
    if len({f["id"] for f in before["figures"]}) != len(before["figures"]):
        raise AuditError("baseline has duplicate figure IDs")
    old = {item["id"]: item for item in before["figures"]}
    new = {item["id"]: item for item in after["figures"]}
    changes = []
    for name in sorted(old.keys() | new.keys()):
        if name not in old or name not in new:
            changes.append({"id": name, "kind": "added" if name in new else "removed"})
            continue
        left, right = old[name], new[name]
        a, b = left.get("report") or {}, right.get("report") or {}
        fields = {
            "status": left.get("status") != right.get("status"),
            "data_bytes": left.get("data", {}).get("sha256") != right.get("data", {}).get("sha256"),
            "numeric_representation": left.get("data", {}).get("numeric_sha256")
            != right.get("data", {}).get("numeric_sha256"),
            "spec": left.get("semantic_spec") != right.get("semantic_spec"),
            "source": left.get("source_sha256") != right.get("source_sha256"),
            "claims": a.get("claims") != b.get("claims"),
            "significance": a.get("significance") != b.get("significance"),
            "description": a.get("alt_text") != b.get("alt_text"),
            "findings": a.get("findings") != b.get("findings"),
            "errors": left.get("errors") != right.get("errors"),
            "warnings": left.get("warnings") != right.get("warnings"),
            "published_artifacts": left.get("artifacts") != right.get("artifacts"),
        }
        outputs = []
        keyed_a = {Path(i["path"]).name: i for i in left.get("outputs", [])}
        keyed_b = {Path(i["path"]).name: i for i in right.get("outputs", [])}
        for filename in sorted(keyed_a.keys() | keyed_b.keys()):
            x, y = keyed_a.get(filename), keyed_b.get(filename)
            if x is None or y is None or x["sha256"] != y["sha256"]:
                outputs.append(
                    {
                        "file": filename,
                        "bytes_changed": True,
                        "pixels_changed": None
                        if not x
                        or not y
                        or x.get("pixels_sha256") is None
                        or y.get("pixels_sha256") is None
                        else x["pixels_sha256"] != y["pixels_sha256"],
                    }
                )
        if any(fields.values()) or outputs:
            changes.append(
                {
                    "id": name,
                    "kind": "changed",
                    "fields": fields,
                    "outputs": outputs,
                    "claims_before": a.get("claims", []),
                    "claims_after": b.get("claims", []),
                }
            )
    return {"changed": bool(changes), "figures": changes}


def audit(
    path: str | Path,
    *,
    output: str | Path = ".graphunslopify-audit",
    baseline: str | Path | None = None,
    fail_on_warning: bool = False,
    fail_on_change: bool = False,
    timeout: float = 120,
) -> dict[str, Any]:
    if fail_on_change and baseline is None:
        raise AuditError("--fail-on-change requires --baseline")
    source, manifest = load_manifest(path)
    previous = _json(Path(baseline)) if baseline else None
    root = source.parent
    destination = Path(output).expanduser().resolve()
    if source == destination / "audit.report.json":
        raise AuditError("audit report would overwrite the manifest")
    if timeout <= 0:
        raise AuditError("timeout must be positive")
    destination.mkdir(parents=True, exist_ok=True)
    run_root = destination / "runs" / uuid.uuid4().hex
    figures = [
        _audit_one(entry, root, run_root, fail_on_warning=fail_on_warning, timeout=timeout)
        for entry in manifest["figures"]
    ]
    for figure in figures:
        for item in figure["outputs"]:
            item["path"] = (run_root.relative_to(destination) / item["path"]).as_posix()
    status = (
        "failed"
        if any(f["status"] == "failed" for f in figures)
        else "incomplete"
        if any(f["status"] == "incomplete" for f in figures)
        else "passed"
    )
    result: dict[str, Any] = {
        "schema_version": 1,
        "manifest": source.name,
        "run_directory": run_root.relative_to(destination).as_posix(),
        "status": status,
        "figures": figures,
        "counts": {
            key: sum(f["status"] == key for f in figures)
            for key in ("passed", "failed", "incomplete")
        },
        "comparison": None,
        "policy": {
            "strict": True,
            "fail_on_warning": fail_on_warning,
            "fail_on_change": fail_on_change,
        },
        "exit_code": 0,
    }
    if previous is not None:
        result["comparison"] = compare_audits(previous, result)
    result["exit_code"] = (
        2
        if status != "passed"
        or (fail_on_change and result["comparison"] and result["comparison"]["changed"])
        else 0
    )
    (destination / "audit.report.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=True, allow_nan=False) + "\n", encoding="utf8"
    )
    summary = [
        "# Figure audit",
        "",
        f"Status: **{status}**. Process exit: {result['exit_code']}.",
        "",
        "| Figure | Status | Errors and warnings |",
        "| --- | --- | --- |",
    ]
    summary.extend(
        f"| {f['id']} | {f['status']} | {'; '.join(f['errors'] + f['warnings']).replace('|', '/').replace(chr(10), ' ')} |"
        for f in figures
    )
    if result["comparison"]:
        summary += [
            "",
            "## Changes",
            "",
            "```json",
            json.dumps(result["comparison"], indent=2),
            "```",
        ]
    (destination / "audit.summary.md").write_text("\n".join(summary) + "\n", encoding="utf8")
    return result


def discover(path: str | Path) -> dict[str, Any]:
    root = Path(path).resolve()
    figures = []
    for source in sorted(root.rglob("*.json")):
        if any(
            part in {"node_modules", ".git", ".venv", "venv", ".graphunslopify-audit"}
            for part in source.relative_to(root).parts
        ):
            continue
        try:
            value = _json(source)
        except (ValueError, OSError):
            continue
        if isinstance(value, dict) and isinstance(value.get("kind"), str):
            name = (
                re.sub(
                    r"[^A-Za-z0-9_.-]+", "-", source.relative_to(root).with_suffix("").as_posix()
                ).strip("-._")[:64]
                or "figure"
            )
            figures.append({"id": name, "spec": source.relative_to(root).as_posix()})
    if not figures:
        raise AuditError(
            "no figure JSON specs found; provide a manifest mapping scripts/artifacts explicitly"
        )
    ids = [f["id"] for f in figures]
    if len(ids) != len(set(ids)):
        raise AuditError("discovered IDs collide; choose distinct IDs in a manual manifest")
    return {"schema_version": 1, "figures": figures}
