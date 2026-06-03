"""Node-level Agent for interactive debugging — powered by Claude CLI.

When a pipeline node fails or is running, this Agent can:
- Analyze the error and explain what went wrong
- Report current progress based on live output and timeline
- Read/write files in the workspace directory
- Suggest and apply configuration fixes
- Trigger node retry

Uses Claude CLI (claude-code) with streaming support for real-time responses.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from pydantic import BaseModel, Field


# ── Claude CLI path ───────────────────────────────────────────────────────────

def _get_claude_bin() -> str:
    """Resolve the claude.exe binary path."""
    # Try project-local first
    project_root = Path(__file__).resolve().parents[4]  # app/backend/domains/bug_fix/ -> project root
    local_bin = project_root / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
    if local_bin.exists():
        return str(local_bin)
    # Fallback to global
    return "claude"


# ── Request Model ─────────────────────────────────────────────────────────────

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
    workspace_path: Optional[str] = None
    model_name: Optional[str] = None
    model_provider: Optional[str] = None
    api_keys: Optional[dict[str, str]] = None


# ── System Prompt ─────────────────────────────────────────────────────────────

def _build_system_prompt(request: NodeChatRequest) -> str:
    """Build the system prompt with node context."""
    config_str = json.dumps(request.node_config, indent=2, ensure_ascii=False)
    error_section = f"\n\nError:\n{request.error_info}" if request.error_info else ""
    
    # Workspace / repo info
    work_dir = request.workspace_path or request.repo_path
    work_section = ""
    if work_dir:
        work_section = f"\n\nWorking directory: {work_dir}\nYou can read and write files in this directory."
    
    # Streaming output context for in-progress nodes
    streaming_section = ""
    if request.streaming_output and request.node_status == "IN_PROGRESS":
        output = request.streaming_output
        if len(output) > 2000:
            output = "..." + output[-2000:]
        streaming_section = f"\n\nCurrent progress (live output):\n{output}"
    
    # Progress timeline
    timeline_section = ""
    if request.progress_timeline:
        timeline_section = f"\n\nProgress timeline:\n{request.progress_timeline}"
    
    status_section = f"\nNode status: {request.node_status}" if request.node_status else ""

    return f"""You are an assistant for a CI/CD pipeline node.

Current node: {request.node_name} (type: {request.node_type})
Node ID: {request.node_id}{status_section}

Current configuration:
{config_str}{error_section}{work_section}{streaming_section}{timeline_section}

Your capabilities:
1. Report current progress and explain what's happening (when node is running)
2. Analyze errors and explain what went wrong (when node has failed)
3. Read and write files in the working directory to inspect code or apply fixes
4. Suggest configuration fixes and explain the reasoning
5. Help debug issues by examining source code, logs, and configuration files

Guidelines:
- Be concise and actionable
- When the node is running, summarize the current progress based on the live output and timeline
- When suggesting fixes, explain the reasoning
- You can read files to understand the codebase and diagnose issues
- You can write/patch files when the user asks you to make changes
- Respond in the same language as the user (Chinese if they speak Chinese)
"""


def _build_user_prompt(request: NodeChatRequest) -> str:
    """Build the full user prompt including conversation history."""
    parts = []
    
    # Include conversation history as context
    if request.conversation_history:
        parts.append("Previous conversation:")
        for msg in request.conversation_history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            prefix = "User" if role == "user" else "Assistant"
            parts.append(f"[{prefix}]: {content}")
        parts.append("")
    
    parts.append(f"Current question: {request.message}")
    return "\n".join(parts)


# ── Claude CLI Streaming ──────────────────────────────────────────────────────

async def chat_with_node(
    request: NodeChatRequest,
) -> AsyncIterator[dict[str, Any]]:
    """Stream Agent responses using Claude CLI.

    Yields events:
    - {"type": "token", "content": "..."} for text chunks
    - {"type": "tool_call", "name": "...", "args": {...}} for tool invocations
    - {"type": "done"} when complete
    """
    claude_bin = _get_claude_bin()
    system_prompt = _build_system_prompt(request)
    user_prompt = _build_user_prompt(request)
    
    # Determine working directory
    cwd = request.workspace_path or request.repo_path or os.getcwd()
    
    # Build CLI command
    cmd = [
        claude_bin,
        "-p",                          # print mode (non-interactive)
        "--output-format", "stream-json",  # streaming JSON output
        "--verbose",                   # include tool use details
        "--system-prompt", system_prompt,
        user_prompt,
    ]
    
    # Set up environment with API keys
    env = os.environ.copy()
    if request.api_keys:
        # Map common API key names to environment variables
        key_mapping = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "google": "GOOGLE_API_KEY",
        }
        for provider, key in request.api_keys.items():
            env_var = key_mapping.get(provider.lower())
            if env_var and key:
                env[env_var] = key
    
    # Model selection
    if request.model_name:
        cmd.extend(["--model", request.model_name])
    
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
        )
    except FileNotFoundError:
        yield {"type": "error", "message": f"Claude CLI not found at {claude_bin}. Install with: npm install @anthropic-ai/claude-code"}
        return
    except Exception as e:
        yield {"type": "error", "message": f"Failed to start Claude CLI: {e}"}
        return
    
    # Parse streaming output
    assert process.stdout is not None
    buffer = ""
    
    async for line_bytes in process.stdout:
        line = line_bytes.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            # Not JSON, skip
            continue
        
        event_type = event.get("type", "")
        
        if event_type == "system":
            # Init event, skip
            continue
        
        elif event_type == "assistant":
            # Assistant message with content blocks
            message = event.get("message", {})
            content_blocks = message.get("content", [])
            for block in content_blocks:
                block_type = block.get("type", "")
                if block_type == "text":
                    text = block.get("text", "")
                    if text:
                        yield {"type": "token", "content": text}
                elif block_type == "tool_use":
                    yield {
                        "type": "tool_call",
                        "name": block.get("name", ""),
                        "args": block.get("input", {}),
                    }
        
        elif event_type == "result":
            # Final result
            subtype = event.get("subtype", "")
            if subtype == "error":
                error_msg = event.get("error", "Unknown error")
                yield {"type": "error", "message": error_msg}
            # Success — done event will be yielded at the end
        
        elif event_type == "tool":
            # Tool result (for verbose mode)
            # We can optionally surface this to the user
            pass
    
    # Wait for process to finish
    await process.wait()
    
    if process.returncode != 0 and process.stderr:
        stderr = await process.stderr.read()
        stderr_text = stderr.decode("utf-8", errors="replace").strip()
        if stderr_text:
            yield {"type": "error", "message": f"Claude CLI error: {stderr_text}"}
    
    yield {"type": "done"}
