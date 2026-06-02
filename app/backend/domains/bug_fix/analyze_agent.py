"""Analyze stage — turns a Jira issue into a structured root-cause hypothesis.

Provider-agnostic: dispatches through the shared LLM registry
(`src.llm.models.get_model`) so any backend the platform already knows
about (Anthropic, DeepSeek, OpenAI, Google, Groq, Kimi, Ollama, …) can
power the Analyze call without changes here. Caller picks the model
by passing model_name + model_provider; the executor forwards the
choice from the request.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Awaitable, Callable, Optional

from src.llm.models import ModelProvider, get_model


# Callback fired per-chunk while the LLM streams; the executor uses it to
# push partial output to the SSE stream so the canvas can render the
# response as it grows.
OnToken = Callable[[str], Awaitable[None]]


_DEFAULT_PROVIDER = os.getenv("BUG_FIX_ANALYZE_PROVIDER", "Anthropic")
_DEFAULT_MODEL = os.getenv("BUG_FIX_ANALYZE_MODEL", "claude-sonnet-4-6")
_MAX_COMMENTS = 8


class AnalyzeConfigError(RuntimeError):
    """Raised when the chosen provider's credentials are missing."""


def _strip_image_refs(text: str) -> str:
    """Remove Jira image attachment references from text."""
    text = re.sub(r'![^!]+\.(png|jpg|jpeg|gif|bmp|svg|webp)(\|[^!]*)?!', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[\^[^\]]+\]', '', text)
    return text.strip()


def _extract_comments(jira: dict[str, Any]) -> list[dict[str, str]]:
    """Extract comments from Jira detail (handles both raw and flattened formats)."""
    # Raw Jira API: fields.comment.comments[]
    comments_raw = (
        jira.get("comment", {}).get("comments", [])
        if isinstance(jira.get("comment"), dict)
        else []
    )
    # Flattened format: jira["comments"] = [...]
    if not comments_raw and isinstance(jira.get("comments"), list):
        comments_raw = jira["comments"]

    result = []
    for c in comments_raw:
        if not isinstance(c, dict):
            continue
        author = ""
        if isinstance(c.get("author"), dict):
            author = c["author"].get("displayName", "")
        elif isinstance(c.get("author"), str):
            author = c["author"]
        body = c.get("body", "") or ""
        updated = c.get("updated", "") or c.get("created", "")
        if body.strip():
            result.append({"author": author, "body": _strip_image_refs(body.strip()), "updated": updated})
    return result


def _build_prompt(jira: dict[str, Any]) -> str:
    summary = jira.get("summary") or "(no summary)"
    description = (jira.get("description") or "(no description)")[:4000]
    comments = _extract_comments(jira)
    recent = comments[-_MAX_COMMENTS:]
    comment_block = "\n".join(
        f"- [{c.get('updated','')}] {c.get('author','?')}: {c.get('body','')[:400]}"
        for c in recent
    ) or "(no comments)"

    # Extract components (handle both raw and flattened formats)
    components = []
    for c in (jira.get("components") or []):
        if isinstance(c, dict):
            components.append(c.get("name", ""))
        elif isinstance(c, str):
            components.append(c)

    return (
        "You are a senior engineer triaging a bug. Read the Jira context and"
        " return ONLY a JSON object (no prose, no fences) with these keys:\n"
        "  root_cause_hypothesis: one sentence guess at the underlying cause.\n"
        "  affected_areas: array of short strings naming likely files/modules/components.\n"
        "  suggested_approach: 2-3 short steps a developer would take next.\n"
        "  open_questions: array of clarifying questions (empty if none).\n"
        "\n"
        f"Summary: {summary}\n"
        f"Status: {jira.get('status','')}\n"
        f"Priority: {jira.get('priority','')}\n"
        f"Components: {', '.join(components) or '(none)'}\n"
        f"\nDescription:\n{description}\n"
        f"\nRecent comments:\n{comment_block}\n"
    )


def _parse_analysis(text: str) -> dict[str, Any]:
    """Pull a JSON object out of the model's response, tolerating fences."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else stripped
        if stripped.endswith("```"):
            stripped = stripped[: -3]
        stripped = stripped.strip()
        if stripped.startswith("json"):
            stripped = stripped[4:].lstrip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return {"raw": text.strip()}
    return parsed if isinstance(parsed, dict) else {"raw": text.strip()}


def _resolve_provider(name: str) -> ModelProvider:
    try:
        return ModelProvider(name)
    except ValueError as e:
        raise AnalyzeConfigError(f"Unknown provider {name!r}") from e


async def analyze_jira_issue(
    jira_detail: dict[str, Any],
    *,
    model_name: Optional[str] = None,
    model_provider: Optional[str] = None,
    api_keys: Optional[dict[str, str]] = None,
    on_token: Optional[OnToken] = None,
) -> dict[str, Any]:
    """Run the LLM analyze pass against the requested model.

    If `on_token` is supplied, the response is streamed via `astream` and
    each chunk's text is forwarded to the callback. The final parsed
    dict is still returned at the end so the executor's existing return
    contract is unchanged.

    Raises AnalyzeConfigError when the provider name is unknown or the
    underlying client can't be constructed (e.g. missing API key).
    """
    chosen_model = model_name or _DEFAULT_MODEL
    chosen_provider = _resolve_provider(model_provider or _DEFAULT_PROVIDER)

    try:
        llm = get_model(chosen_model, chosen_provider, api_keys=api_keys or {})
    except Exception as e:  # ValueError on missing key, etc.
        raise AnalyzeConfigError(str(e)) from e
    if llm is None:
        raise AnalyzeConfigError(
            f"get_model returned None for {chosen_provider.value}/{chosen_model}"
        )

    prompt = _build_prompt(jira_detail)

    if on_token is None:
        response = await llm.ainvoke(prompt)
        content = getattr(response, "content", response)
        text = content if isinstance(content, str) else str(content)
        return _parse_analysis(text)

    # Streaming path: accumulate chunks while echoing each one to the caller.
    parts: list[str] = []
    async for chunk in llm.astream(prompt):
        piece = getattr(chunk, "content", chunk)
        token = piece if isinstance(piece, str) else str(piece)
        if not token:
            continue
        parts.append(token)
        try:
            await on_token(token)
        except Exception:
            # A failing UI sink mustn't break the LLM read.
            pass
    return _parse_analysis("".join(parts))
