"""Node-level Agent for interactive debugging.

When a pipeline node fails, this Agent can:
- Analyze the error and explain what went wrong
- Suggest configuration fixes
- Update node configuration via tool calls
- Trigger node retry

The Agent uses LangChain's tool-calling pattern with streaming support.
"""
from __future__ import annotations

import json
import subprocess
from typing import Any, AsyncIterator, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from src.llm.models import ModelProvider, get_model


# ── Tool Definitions ──────────────────────────────────────────────────────────

@tool
def update_config(key: str, value: str) -> str:
    """Update a node configuration field.

    Args:
        key: The configuration field name (e.g., 'pushRemote', 'prTargetRemote', 'targetBranch')
        value: The new value for the field

    Returns:
        Confirmation message with the updated configuration
    """
    return json.dumps({"action": "update_config", "key": key, "value": value})


@tool
def retry_node() -> str:
    """Mark the node for retry. The frontend will trigger a re-execution.

    Returns:
        Confirmation that retry has been requested
    """
    return json.dumps({"action": "retry_node"})


@tool
def get_git_remotes(repo_path: str) -> str:
    """Get the list of git remotes for a repository.

    Args:
        repo_path: Absolute path to the git repository

    Returns:
        JSON with remote names and their URLs
    """
    try:
        result = subprocess.run(
            ["git", "remote", "-v"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return json.dumps({"error": f"git remote failed: {result.stderr}"})

        remotes = {}
        for line in result.stdout.strip().splitlines():
            parts = line.split()
            if len(parts) >= 2:
                name = parts[0]
                url = parts[1]
                if name not in remotes:
                    remotes[name] = {"url": url, "type": "fetch" if "(fetch)" in line else "push"}
        return json.dumps({"remotes": remotes})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ── Agent Logic ───────────────────────────────────────────────────────────────

class NodeChatRequest(BaseModel):
    """Request payload for node chat."""
    node_id: str
    node_name: str
    node_type: str  # e.g., "Analyze", "Patch", "Open PR"
    message: str
    conversation_history: list[dict[str, str]] = Field(default_factory=list)
    node_config: dict[str, Any] = Field(default_factory=dict)
    error_info: Optional[str] = None
    streaming_output: Optional[str] = None
    progress_timeline: Optional[str] = None
    node_status: Optional[str] = None
    repo_path: Optional[str] = None
    model_name: Optional[str] = None
    model_provider: Optional[str] = None
    api_keys: Optional[dict[str, str]] = None


def _build_system_prompt(request: NodeChatRequest) -> str:
    """Build the system prompt with node context."""
    config_str = json.dumps(request.node_config, indent=2, ensure_ascii=False)
    error_section = f"\n\nError:\n{request.error_info}" if request.error_info else ""
    repo_section = f"\n\nRepository path: {request.repo_path}" if request.repo_path else ""
    
    # Add streaming output context for in-progress nodes
    streaming_section = ""
    if request.streaming_output and request.node_status == "IN_PROGRESS":
        # Truncate to last 2000 chars to avoid overwhelming the context
        output = request.streaming_output
        if len(output) > 2000:
            output = "..." + output[-2000:]
        streaming_section = f"\n\nCurrent progress (live output):\n{output}"
    
    # Add progress timeline for context
    timeline_section = ""
    if request.progress_timeline:
        timeline_section = f"\n\nProgress timeline:\n{request.progress_timeline}"
    
    status_section = f"\nNode status: {request.node_status}" if request.node_status else ""

    return f"""You are an assistant for a CI/CD pipeline node.

Current node: {request.node_name} (type: {request.node_type})
Node ID: {request.node_id}{status_section}

Current configuration:
{config_str}{error_section}{repo_section}{streaming_section}{timeline_section}

Your capabilities:
1. Report current progress and explain what's happening (when node is running)
2. Analyze errors and explain what went wrong (when node has failed)
3. Suggest configuration fixes
4. Update configuration using the update_config tool
5. Trigger a retry using the retry_node tool
6. Query git remotes using get_git_remotes tool

Guidelines:
- Be concise and actionable
- When the node is running, summarize the current progress based on the live output and timeline
- When suggesting fixes, explain the reasoning
- Use tools to make actual changes, don't just describe them
- After updating config, suggest retry if appropriate
- Respond in the same language as the user (Chinese if they speak Chinese)
"""


async def chat_with_node(
    request: NodeChatRequest,
) -> AsyncIterator[dict[str, Any]]:
    """Stream Agent responses with tool calls.

    Yields events:
    - {"type": "token", "content": "..."} for text chunks
    - {"type": "tool_call", "name": "...", "args": {...}} for tool invocations
    - {"type": "done"} when complete
    """
    # Resolve model
    model_name = request.model_name or "claude-3-5-sonnet-20241022"
    provider_name = request.model_provider or "Anthropic"
    try:
        provider = ModelProvider(provider_name)
    except ValueError:
        provider = ModelProvider.ANTHROPIC

    llm = get_model(model_name, provider, api_keys=request.api_keys or {})
    if llm is None:
        yield {"type": "error", "message": f"Failed to load model {model_name}"}
        return

    # Bind tools
    tools = [update_config, retry_node, get_git_remotes]
    llm_with_tools = llm.bind_tools(tools)

    # Build message history
    messages = [SystemMessage(content=_build_system_prompt(request))]
    for msg in request.conversation_history:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
    messages.append(HumanMessage(content=request.message))

    # Stream response
    tool_calls_buffer = []
    async for chunk in llm_with_tools.astream(messages):
        # Stream text content
        if hasattr(chunk, "content") and chunk.content:
            content = chunk.content if isinstance(chunk.content, str) else str(chunk.content)
            if content.strip():
                yield {"type": "token", "content": content}

        # Collect tool calls
        if hasattr(chunk, "tool_calls") and chunk.tool_calls:
            for tc in chunk.tool_calls:
                tool_calls_buffer.append(tc)

    # Emit tool calls
    for tc in tool_calls_buffer:
        yield {
            "type": "tool_call",
            "name": tc.get("name", ""),
            "args": tc.get("args", {}),
        }

    yield {"type": "done"}
