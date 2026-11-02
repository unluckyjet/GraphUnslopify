"""Qualify actual complete preparation plans before creating a formal seal.

Evidence is trusted local custody, not authentication against a malicious owner.
No plotting SDK is imported here and no producer is executed during qualification.
"""

from __future__ import annotations

import hashlib
import json
import re
import runpy
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TOTALS = {
    "single": 192,
    "paper": 54,
    "reliability": 48,
    "local": 64,
    "native_ci": 64,
    "gui": 14,
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def validate_summary(seal):
    """A byte/CI seal alone cannot qualify incomplete controllers or parity."""
    summary = seal.get("qualification", {})
    if (
        summary.get("schema_version") != 1
        or summary.get("formal_measurements_used") is not False
    ):
        raise ValueError("Formal seal requires prospective preparation qualification")
    required = {
        "benchmarks/workspace/study_runner.py",
        "benchmarks/workspace/qualification.py",
        "scripts/run-workspace-study.py",
        "scripts/create-workspace-seal.py",
        "scripts/run-workspace-native-study.py",
    }
    if not required.issubset(seal.get("source_sha256", {})):
        raise ValueError("Formal seal lacks complete study-controller sources")
    canonical = json.dumps(
        {"source": seal["source_sha256"], "package": seal["package_sha256"]},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf8")
    if summary.get("implementation_sha256") != digest(canonical):
        raise ValueError(
            "Preparation qualification belongs to different implementation bytes"
        )
    tracks = summary.get("tracks", {})
    if set(tracks) != set(TOTALS):
        raise ValueError(
            "Formal qualification requires all six complete preparation tracks"
        )
    for track, count in TOTALS.items():
        row = tracks[track]
        if (
            row.get("cells") != count
            or row.get("complete") is not True
            or row.get("mode") != "preseal"
            or row.get("interrupted") is not False
        ):
            raise ValueError("Incomplete preparation qualification for " + track)
        evidence = row.get("evidence", [])
        if len(evidence) != (4 if track == "native_ci" else 1) or any(
            not isinstance(v.get("sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}", v["sha256"]) is None
            for v in evidence
        ):
            raise ValueError("Missing original preparation evidence identities")


def qualify(files, *, source_sha256, package_sha256, revision=None, native_run=None):
    """Read actual retained controllers, full plans and execution-context documents."""
    if not __debug__:
        raise RuntimeError("Do not optimize preparation qualification")
    if set(files) != set(TOTALS):
        raise ValueError("Supply all six full preparation tracks")
    runner = runpy.run_path(str(HERE / "study_runner.py"))
    tracks = {}
    native_profiles = set()
    for track, paths in files.items():
        if len(paths) != (4 if track == "native_ci" else 1):
            raise ValueError(
                "Preparation must include every native profile or one complete local track"
            )
        cells, evidence = 0, []
        for filename in paths:
            path = Path(filename).resolve()
            raw = path.read_bytes()
            proof = json.loads(raw)
            if (
                proof.get("track") != track
                or proof.get("mode") != "preseal"
                or proof.get("formal_comparison_performed") is not False
                or not proof.get("complete")
                or proof.get("interrupted")
                or proof.get("errors")
            ):
                raise ValueError(
                    "Incomplete, interrupted or non-preparation evidence: " + str(path)
                )
            actual_files = {
                p.relative_to(path.parent).as_posix(): digest(p.read_bytes())
                for p in sorted(path.parent.rglob("*"))
                if p.is_file()
                and p.relative_to(path.parent).as_posix()
                not in {"study.json", "progress.json"}
            }
            if not actual_files or proof.get("files_sha256") != actual_files:
                raise ValueError("Original preparation files changed or are missing")
            if (
                proof["source_sha256"] != source_sha256
                or proof["package_sha256"] != package_sha256
            ):
                raise ValueError(
                    "Preparation source/package bytes differ from this implementation"
                )
            profile = None
            if track == "native_ci":
                observed = proof["native_context"]["observed_parent"]
                context = observed["ci"]
                if (
                    not context["github_actions"]
                    or context["repository"] != "unluckyjet/GraphUnslopify"
                ):
                    raise ValueError("Native qualification needs actual CI evidence")
                if context["commit"] != revision or context["run_id"] != str(
                    native_run
                ):
                    raise ValueError(
                        "Native preparation does not bind the accepted implementation run"
                    )
                profile = proof["plan"][0]["case"]["profile"]
                environment = runpy.run_path(str(HERE / "environment.py"))
                environment["validate_worker"](
                    observed, profile, proof["native_context"]["expected_worker_ci"]
                )
                if profile in native_profiles:
                    raise ValueError("Duplicate native preparation profile")
                native_profiles.add(profile)
            expected = runner["plan"](track, native_profile=profile)
            if (
                proof["plan"] != expected
                or proof["planned_cells"] != sum(len(r["cells"]) for r in expected)
                or proof["retained_cells"] != proof["planned_cells"]
            ):
                raise ValueError("Preparation omitted or changed the fixed study plan")
            if len(proof["records"]) != len(expected):
                raise ValueError("Preparation has missing or extra actual case records")
            if track in {"local", "native_ci"}:
                repeats = proof.get("same_environment_png_comparisons", [])
                if len(repeats) != (8 if track == "native_ci" else 32) or any(
                    not r.get("both_available") or not r.get("reproduced")
                    for r in repeats
                ):
                    raise ValueError(
                        "Actual repeated PNG evidence is unavailable or differs"
                    )
            for planned, record in zip(expected, proof["records"], strict=True):
                if (
                    any(record.get(k) != v for k, v in planned.items())
                    or not record.get("attempted")
                    or record.get("outcome") != "completed"
                    or record.get("errors")
                ):
                    raise ValueError("Preparation case was not completely executed")
                document_path = path.parent / "contexts" / (planned["id"] + ".json")
                document = document_path.read_bytes()
                if digest(document) != record["context_sha256"]:
                    raise ValueError("Original preparation context bytes changed")
                context_value = json.loads(document)
                context = {
                    **context_value,
                    "context_sha256": digest(document),
                    "formal_comparison_performed": False,
                }
                execution = runner["EXECUTION"]["receipt"](context)
                if (
                    context_value["mode"] != "preseal"
                    or context_value["track"] != track
                    or context_value["arm"] != planned["case"]["arm"]
                    or context_value["case"]
                    != runner["context_case"](track, planned["case"])
                ):
                    raise ValueError(
                        "Original preparation context belongs to a different case"
                    )
                if runner["integrity_errors"](
                    track, record["result"], execution, planned["cells"]
                ):
                    raise ValueError(
                        "Actual preparation result fails its execution identity/envelope guards"
                    )
            cells += proof["planned_cells"]
            evidence.append(
                {
                    "file": path.name,
                    "sha256": digest(raw),
                    "started_utc": proof["started_utc"],
                    "finished_utc": proof["finished_utc"],
                }
            )
        if cells != TOTALS[track]:
            raise ValueError("Preparation denominator differs for " + track)
        tracks[track] = {
            "cells": cells,
            "complete": True,
            "mode": "preseal",
            "interrupted": False,
            "evidence": evidence,
        }
    if native_profiles != set(runner["PROTOCOL"]["reproduction"]["native_ci_profiles"]):
        raise ValueError(
            "Preparation does not contain the four actual registered native profiles"
        )
    canonical = json.dumps(
        {"source": source_sha256, "package": package_sha256},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf8")
    return {
        "schema_version": 1,
        "formal_measurements_used": False,
        "implementation_sha256": digest(canonical),
        "tracks": tracks,
    }
