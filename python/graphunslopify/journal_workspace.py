"""Inspect recorded owned exports without promoting their scientific acceptance."""

from __future__ import annotations

from pathlib import Path

from .journal import check_journal


def inspect_export(path: Path, expected: dict, payload: dict) -> dict:
    """Retain the export's recorded bytes and the server's actual policy date."""
    if "as_of" in payload:
        raise ValueError("Workspace checks use the server's current UTC date")
    if not isinstance(payload.get("profile"), str):
        raise TypeError("Choose a supported journal profile")
    report = check_journal(
        path,
        profile=payload["profile"],
        target_width_mm=payload.get("target_width_mm"),
        width_tolerance_mm=payload.get("width_tolerance_mm", 0.5),
    )
    if (
        report["source"]["sha256"] != expected["sha256"]
        or report["source"]["bytes"] != expected["bytes"]
        or not any(
            check["code"] == "source_current" and check["status"] == "passed"
            for check in report["checks"]
        )
    ):
        raise ValueError("Recorded export changed; regenerate or restore its matching bytes")
    return report
