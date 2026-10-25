"""Errors shared by the builder and local/HTTP transports."""

from __future__ import annotations

from typing import Any


class SpecError(RuntimeError):
    """A spec or renderer was rejected; report contains available runtime evidence."""

    def __init__(self, message: str, report: dict[str, Any] | None = None):
        super().__init__(message)
        self.report = report
