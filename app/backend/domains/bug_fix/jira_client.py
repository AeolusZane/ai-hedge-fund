"""Thin wrapper around the Jira MCP server.

The server lives outside this repo as a standalone Node.js process; we
spawn it on demand via stdio and forward calls through the MCP protocol.
Credentials are pulled from environment variables only — nothing here
should ever land in a commit.

Today we expose just the two tools the bug_fix executor needs: fetching
issue details and posting a comment. Add more as later phases need them.
"""
from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class JiraMcpConfigError(RuntimeError):
    """Raised when the Jira MCP integration is not configured."""


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise JiraMcpConfigError(
            f"Environment variable {name} is required for the Jira MCP integration"
        )
    return value


def _server_params() -> StdioServerParameters:
    return StdioServerParameters(
        command="node",
        args=[_required_env("JIRA_MCP_NODE_PATH")],
        env={
            # Pass through PATH so `node` and its deps resolve.
            "PATH": os.environ.get("PATH", ""),
            "JIRA_BASE_URL": _required_env("JIRA_BASE_URL"),
            "JIRA_USERNAME": _required_env("JIRA_USERNAME"),
            "JIRA_TOKEN": _required_env("JIRA_TOKEN"),
        },
    )


@asynccontextmanager
async def _session() -> AsyncIterator[ClientSession]:
    """Spawn the MCP server and yield an initialised ClientSession."""
    params = _server_params()
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


def _first_text(result: Any) -> str:
    """Pull the first text payload out of an MCP tool-call result."""
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        if text:
            return text
    return ""


def _parse_json_or_raw(text: str) -> Any:
    """The Jira MCP server returns JSON-encoded strings; fall back to raw."""
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


class JiraMcpToolError(RuntimeError):
    """Raised when the MCP server returns an error for a tool call."""


async def get_issue_detail(issue_key: str) -> dict[str, Any]:
    """Fetch a single Jira issue's detail via the MCP server.

    Returns the parsed tool payload. Raises JiraMcpConfigError when env
    vars are missing, and JiraMcpToolError when Jira / the MCP server
    rejects the call (e.g. unknown issue, auth failure).
    """
    async with _session() as session:
        result = await session.call_tool(
            "jira_get_issue_detail",
            arguments={"issueKey": issue_key},
        )
    text = _first_text(result)
    if getattr(result, "isError", False):
        raise JiraMcpToolError(text or "Jira MCP returned an error")
    payload = _parse_json_or_raw(text)
    if not isinstance(payload, dict):
        # The Jira MCP wraps API errors in a plain-text payload prefixed
        # with "Jira API error". Surface those as tool errors rather than
        # pretending the response is data.
        if isinstance(payload, str) and payload.startswith("Jira API error"):
            raise JiraMcpToolError(payload)
        return {"raw": payload}
    return payload
