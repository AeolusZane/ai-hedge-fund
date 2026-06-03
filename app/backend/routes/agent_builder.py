"""Agent Builder API routes.

Provides endpoints for the Agent Builder feature:
- POST /api/v1/agent-builder/chat - Stream chat with Claude Code to design agents
- GET /api/v1/agent-builder/{agent_id} - Get agent configuration
- PUT /api/v1/agent-builder/{agent_id} - Update agent configuration
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/agent-builder", tags=["agent-builder"])


# ── Request/Response Models ───────────────────────────────────────────────────

class AgentSkill(BaseModel):
    name: str
    description: str


class AgentConfig(BaseModel):
    id: str
    name: str
    description: str | None = None
    skills: list[AgentSkill] = Field(default_factory=list)
    system_prompt: str | None = None
    engine: str = "claude-code"


class ChatRequest(BaseModel):
    agent_id: str
    agent_config: AgentConfig
    message: str
    conversation_history: list[dict[str, str]] = Field(default_factory=list)


# ── In-memory storage (replace with DB in production) ─────────────────────────

_agent_configs: dict[str, AgentConfig] = {}


# ── System Prompt ─────────────────────────────────────────────────────────────

def _build_system_prompt(agent_config: AgentConfig) -> str:
    """Build the system prompt for the Agent Builder AI."""
    config_json = json.dumps(agent_config.model_dump(), indent=2, ensure_ascii=False)
    
    return f"""你是一个 Agent 设计助手。帮助用户设计和构建 AI Agent。

当前 Agent 配置：
{config_json}

你的能力：
1. 帮助用户定义 Agent 的名称、描述、用途
2. 建议和设计 Agent 的 skills（技能）
3. 生成 Agent 的 system prompt
4. 解释 Agent 设计的最佳实践

当用户明确表达意图时，使用以下 JSON 格式输出工具调用（每行一个）：
```tool_call
{{"name": "set_agent_name", "args": {{"name": "新名称"}}}}
{{"name": "set_agent_description", "args": {{"description": "新描述"}}}}
{{"name": "add_skill", "args": {{"name": "技能名", "description": "技能描述"}}}}
{{"name": "set_system_prompt", "args": {{"prompt": "system prompt 内容"}}}}
```

指导原则：
- 用中文回复，保持简洁友好
- 主动询问用户的需求和场景
- 根据用户描述智能推荐合适的 skills
- 解释你的设计决策
- 当用户说"就这样"或"完成"时，总结最终的 Agent 配置
"""


# ── Claude Code Streaming ─────────────────────────────────────────────────────

async def _stream_claude_response(
    message: str,
    agent_config: AgentConfig,
    conversation_history: list[dict[str, str]],
) -> AsyncIterator[str]:
    """Stream Claude Code responses for agent building."""
    from app.backend.domains.bug_fix.node_chat_agent import _get_claude_bin
    
    claude_bin = _get_claude_bin()
    system_prompt = _build_system_prompt(agent_config)
    
    # Build conversation context
    context_parts = []
    if conversation_history:
        context_parts.append("Previous conversation:")
        for msg in conversation_history[-10:]:  # Last 10 messages
            role = "User" if msg.get("role") == "user" else "Assistant"
            context_parts.append(f"[{role}]: {msg.get('content', '')}")
        context_parts.append("")
    
    context_parts.append(f"Current message: {message}")
    user_prompt = "\n".join(context_parts)
    
    # Build CLI command
    cmd = [
        claude_bin,
        "-p",
        "--output-format", "stream-json",
        "--verbose",
        "--system-prompt", system_prompt,
        user_prompt,
    ]
    
    import os
    env = os.environ.copy()
    
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=env,
        )
    except FileNotFoundError:
        yield f"data: {json.dumps({'type': 'error', 'message': f'Claude CLI not found at {claude_bin}'})}\n\n"
        yield "data: [DONE]\n\n"
        return
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        yield "data: [DONE]\n\n"
        return
    
    assert process.stdout is not None
    
    try:
        async for line_bytes in process.stdout:
            line = line_bytes.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            
            event_type = event.get("type", "")
            
            if event_type == "system":
                continue
            
            elif event_type == "assistant":
                message_data = event.get("message", {})
                content_blocks = message_data.get("content", [])
                for block in content_blocks:
                    block_type = block.get("type", "")
                    if block_type == "text":
                        text = block.get("text", "")
                        if text:
                            # Check for tool_call patterns in the text
                            tool_calls = _extract_tool_calls(text)
                            if tool_calls:
                                for tc in tool_calls:
                                    yield f"data: {json.dumps({'type': 'tool_call', **tc})}\n\n"
                                # Remove tool_call blocks from text
                                clean_text = _remove_tool_calls(text)
                                if clean_text.strip():
                                    yield f"data: {json.dumps({'type': 'token', 'content': clean_text})}\n\n"
                            else:
                                yield f"data: {json.dumps({'type': 'token', 'content': text})}\n\n"
            
            elif event_type == "result":
                subtype = event.get("subtype", "")
                if subtype == "error":
                    error_msg = event.get("error", "Unknown error")
                    yield f"data: {json.dumps({'type': 'error', 'message': error_msg})}\n\n"
    
    except asyncio.CancelledError:
        process.kill()
        raise
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    try:
        await asyncio.wait_for(process.wait(), timeout=5.0)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
    
    yield "data: [DONE]\n\n"


def _extract_tool_calls(text: str) -> list[dict[str, Any]]:
    """Extract tool calls from Claude's response text."""
    import re
    tool_calls = []
    
    # Match ```tool_call blocks
    pattern = r'```tool_call\s*\n(.*?)```'
    matches = re.findall(pattern, text, re.DOTALL)
    
    for match in matches:
        try:
            tc = json.loads(match.strip())
            if "name" in tc and "args" in tc:
                tool_calls.append(tc)
        except json.JSONDecodeError:
            pass
    
    return tool_calls


def _remove_tool_calls(text: str) -> str:
    """Remove tool_call blocks from text."""
    import re
    pattern = r'```tool_call\s*\n.*?```'
    return re.sub(pattern, '', text, flags=re.DOTALL)


# ── API Endpoints ─────────────────────────────────────────────────────────────

@router.post("/chat")
async def chat(request: ChatRequest):
    """Stream chat with Claude Code to design an agent."""
    return StreamingResponse(
        _stream_claude_response(
            message=request.message,
            agent_config=request.agent_config,
            conversation_history=request.conversation_history,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.get("/{agent_id}")
async def get_agent_config(agent_id: str):
    """Get agent configuration."""
    if agent_id not in _agent_configs:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _agent_configs[agent_id]


@router.put("/{agent_id}")
async def update_agent_config(agent_id: str, config: AgentConfig):
    """Update agent configuration."""
    _agent_configs[agent_id] = config
    return {"status": "ok", "agent": config}
