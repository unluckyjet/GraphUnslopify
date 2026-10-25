"""Negotiate real stdio sessions; check payload parity and explicit tool errors."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys

import pytest

from graphunslopify.transport import local_request

mcp = pytest.importorskip("mcp")


@pytest.mark.parametrize("mode", ["auto", "legacy"])
def test_real_stdio_agent_round_trip(mode):
    async def scenario():
        parameters = mcp.StdioServerParameters(
            command=sys.executable, args=["-m", "graphunslopify.cli", "mcp"]
        )
        async with mcp.Client(parameters, mode=mode, read_timeout_seconds=90) as client:
            tools = await client.list_tools()
            assert {tool.name for tool in tools.tools} == {
                "get_figure_schema",
                "figure_to_matplotlib",
                "validate_spec",
                "list_recipes",
                "suggest_figures",
                "score_spec",
                "apply_fixes",
            }
            assert all(tool.annotations.read_only_hint for tool in tools.tools)
            schema = await client.call_tool("get_figure_schema", {})
            assert not schema.is_error
            assert len(schema.structured_content["oneOf"]) == 21
            resource = await client.read_resource("graphunslopify://schema")
            assert json.loads(resource.contents[0].text) == schema.structured_content

            spec = {
                "kind": "line",
                "data": {"path": "nonexistent-must-not-be-read.csv"},
                "x": {"field": "x", "label": "X"},
                "y": {"field": "y", "label": "Y"},
            }
            generated = await client.call_tool("figure_to_matplotlib", {"spec": spec})
            assert not generated.is_error
            assert generated.structured_content == local_request("convert", spec)
            validated = await client.call_tool("validate_spec", {"spec": spec})
            assert validated.structured_content["ok"]
            scored = await client.call_tool("score_spec", {"spec": spec})
            assert isinstance(scored.structured_content["cost"], (float, int))

            recipes = await client.call_tool("list_recipes", {})
            assert len(recipes.structured_content["recipes"]) == 25
            name = recipes.structured_content["recipes"][0]["name"]
            recipe = await client.call_tool("list_recipes", {"name": name})
            assert recipe.structured_content["spec"]["kind"]

            repaired = await client.call_tool(
                "apply_fixes",
                {
                    "spec": {
                        **spec,
                        "kind": "bar",
                        "group": "model",
                        "stacked": True,
                        "aggregation": "mean",
                        "series_order": ["a", "b", "c", "d", "e", "f"],
                    }
                },
            )
            assert not repaired.is_error
            assert "stacked_costs_a_baseline" in repaired.structured_content["applied"]
            assert repaired.structured_content["spec"]["stacked"] is False

            profile = {
                "path": "experiments/actual.csv",
                "columns": [
                    {"name": "epoch", "role": "ordinal", "distinct": 30},
                    {"name": "score", "role": "measure", "distinct": 50},
                    {"name": "model", "role": "category", "distinct": 2},
                ],
            }
            suggested = await client.call_tool("suggest_figures", {"profile": profile})
            assert suggested.structured_content["candidates"]
            assert all(
                item["spec"]["data"]["path"] == "experiments/actual.csv"
                for item in suggested.structured_content["candidates"]
            )

            malformed = await client.call_tool(
                "figure_to_matplotlib", {"spec": {"kind": "unknown"}}
            )
            assert malformed.is_error
            assert malformed.structured_content["status"] == "invalid_spec"
            bad_validation = await client.call_tool("validate_spec", {"spec": {"kind": "unknown"}})
            assert bad_validation.is_error
            semantic = await client.call_tool(
                "figure_to_matplotlib",
                {"spec": {**spec, "kind": "bar", "axis_break": {"axis": "y", "from": 1, "to": 2}}},
            )
            assert semantic.is_error
            assert semantic.structured_content["ok"] is False
            assert semantic.structured_content["code"]  # Error and reviewable code may coexist.

    asyncio.run(scenario())


def test_generated_client_configuration_uses_the_active_environment():
    result = subprocess.run(
        [sys.executable, "-m", "graphunslopify.cli", "mcp-config"],
        capture_output=True,
        text=True,
        check=True,
    )
    entry = json.loads(result.stdout)["mcpServers"]["graphunslopify"]
    assert entry == {"command": sys.executable, "args": ["-m", "graphunslopify.cli", "mcp"]}
    codex = subprocess.run(
        [sys.executable, "-m", "graphunslopify.cli", "mcp-config", "--client", "codex"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "[mcp_servers.graphunslopify]" in codex.stdout
    assert f"command = {json.dumps(sys.executable)}" in codex.stdout
