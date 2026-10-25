"""Local stdio MCP adapter for the canonical compiler; never opens user data."""

from __future__ import annotations

import json
from typing import Any

from mcp.server import MCPServer
from mcp.types import CallToolResult, TextContent, ToolAnnotations

from . import __version__
from .errors import SpecError
from .transport import local_request


def _result(value: dict[str, Any], *, error: bool = False) -> CallToolResult:
    error = error or value.get("status") == "invalid_spec" or value.get("ok") is False
    error = error or any(
        item.get("severity") == "error"
        for key in ("findings", "remaining")
        for item in value.get(key, [])
    )
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(value, ensure_ascii=True, indent=2))],
        structuredContent=value,
        isError=error,
    )


def _call(operation: str, payload: Any = None) -> CallToolResult:
    try:
        value = local_request(operation, payload)
        if (
            operation == "suggest"
            and not value
            and str(payload.get("profile", {}).get("path", ""))
            .lower()
            .endswith((".jsonl", ".ndjson"))
        ):
            return _result(
                {
                    "ok": False,
                    "candidates": [],
                    "error": "Convert JSON Lines to a regular JSON table or CSV before rendering",
                }
            )
        return _result(
            value
            if isinstance(value, dict)
            else {"candidates" if operation == "suggest" else "result": value}
        )
    except SpecError as problem:
        return _result({"ok": False, "error": str(problem)}, error=True)


def create_server() -> MCPServer:
    server = MCPServer(
        "GraphUnslopify",
        version=__version__,
        log_level="WARNING",
        instructions="Local semantic figure compiler. Start with get_figure_schema or list_recipes. Profile local data with graphunslopify describe, then validate and generate code. Run generated Python locally with --strict; compiler validation alone does not verify data claims or figure geometry. This server does not open data files or execute generated code.",
    )
    readonly = ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
    )

    @server.tool(annotations=readonly)
    def get_figure_schema() -> CallToolResult:
        """Get the canonical schema for all 21 kinds and their field requirements."""
        return _call("schema")

    @server.tool(annotations=readonly)
    def figure_to_matplotlib(spec: dict[str, Any]) -> CallToolResult:
        """Validate semantic intent and generate Python, findings and a filename. Honor ok/isError."""
        return _call("convert", spec)

    @server.tool(annotations=readonly)
    def validate_spec(spec: dict[str, Any]) -> CallToolResult:
        """Check schema and semantic findings without generating a program or reading data."""
        return _call("validate", spec)

    @server.tool(annotations=readonly)
    def list_recipes(name: str | None = None) -> CallToolResult:
        """List known-good starting designs, or get one recipe's complete spec by name."""
        try:
            value = local_request("recipes", {"name": name} if name else {})
            if name is None:
                value = {
                    "recipes": [
                        {"name": item["name"], "purpose": item["purpose"]} for item in value
                    ]
                }
            return _result(value)
        except SpecError as problem:
            return _result({"ok": False, "error": str(problem)}, error=True)

    @server.tool(annotations=readonly)
    def suggest_figures(profile: dict[str, Any], limit: int = 3) -> CallToolResult:
        """Rank candidates from a supplied local dataset profile; roles/units remain guesses."""
        return _call("suggest", {"profile": profile, "limit": limit})

    @server.tool(annotations=readonly)
    def score_spec(spec: dict[str, Any]) -> CallToolResult:
        """Compare a design's perceptual cost and lint findings; cost is not a correctness verdict."""
        return _call("score", spec)

    @server.tool(annotations=readonly)
    def apply_fixes(spec: dict[str, Any], budget: int = 3) -> CallToolResult:
        """Return bounded repairs offered by the static linter and remaining findings; no files change."""
        return _call("repair", {"spec": spec, "budget": budget})

    @server.resource("graphunslopify://schema")
    def schema_resource() -> str:
        """The canonical FigureSpec JSON schema."""
        return json.dumps(local_request("schema"))

    return server


def serve() -> None:
    create_server().run(transport="stdio")
