"""Readable, bounded correction guidance from the canonical compiler catalog."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files


@lru_cache(maxsize=1)
def catalog():
    return json.loads(
        files("graphunslopify").joinpath("diagnostics.json").read_text(encoding="utf8")
    )


def advice(code: str) -> dict[str, str]:
    data = catalog()
    return dict(data["advice"].get(code, data["unknown"]))


def explain(finding: dict) -> dict:
    guidance = advice(finding.get("code", ""))
    return {**guidance, **finding}


def format_finding(finding: dict) -> str:
    item = explain(finding)
    return (
        f"{item.get('severity', 'error').upper()} [{item.get('code', 'invalid_spec')}] {item['message']}\n"
        f"  Why it matters: {item['consequence']}\n"
        f"  Recommended correction: {item['correction']}"
    )


def schema_findings(issues: list[dict]) -> list[dict]:
    return [
        explain(
            {
                "severity": "error",
                "code": "invalid_spec",
                **issue,
                "message": f"{issue.get('path', '(root)')}: {issue['message']}",
            }
        )
        for issue in issues
    ]


def format_findings(findings: list[dict]) -> str:
    return "\n".join(format_finding(item) for item in findings)
