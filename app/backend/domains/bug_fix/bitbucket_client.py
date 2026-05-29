"""Thin wrapper around the Bitbucket MCP server.

Mirrors `jira_client.py`: spawns the Node.js MCP server on stdio,
opens a session, calls a single tool, parses the JSON text payload.
"""
from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class BitbucketMcpConfigError(RuntimeError):
    pass


class BitbucketMcpToolError(RuntimeError):
    pass


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise BitbucketMcpConfigError(
            f"Environment variable {name} is required for the Bitbucket MCP integration"
        )
    return value


def _server_params() -> StdioServerParameters:
    return StdioServerParameters(
        command="node",
        args=[_required_env("BITBUCKET_MCP_NODE_PATH")],
        env={
            "PATH": os.environ.get("PATH", ""),
            "BITBUCKET_BASE_URL": _required_env("BITBUCKET_BASE_URL"),
            "BITBUCKET_TOKEN": _required_env("BITBUCKET_TOKEN"),
            "BITBUCKET_USERNAME": os.environ.get("BITBUCKET_USERNAME", ""),
        },
    )


@asynccontextmanager
async def _session() -> AsyncIterator[ClientSession]:
    params = _server_params()
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


def _first_text(result: Any) -> str:
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        if text:
            return text
    return ""


def _parse(text: str) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


async def create_pr(
    *,
    project: str,
    repo: str,
    title: str,
    from_branch: str,
    to_branch: str,
    description: str = "",
    reviewers: list[str] | None = None,
) -> dict[str, Any]:
    async with _session() as session:
        result = await session.call_tool(
            "bitbucket_create_pr",
            arguments={
                "project": project,
                "repo": repo,
                "title": title,
                "fromBranch": from_branch,
                "toBranch": to_branch,
                "description": description,
                **({"reviewers": reviewers} if reviewers else {}),
            },
        )
    text = _first_text(result)
    if getattr(result, "isError", False):
        raise BitbucketMcpToolError(text or "Bitbucket MCP returned an error")
    payload = _parse(text)
    if isinstance(payload, dict):
        return payload
    # The server sometimes returns a plain-text "Created PR https://…".
    return {"raw": payload}
