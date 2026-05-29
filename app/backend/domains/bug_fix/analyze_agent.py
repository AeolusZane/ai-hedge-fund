"""Analyze stage — turns a Jira issue into a structured root-cause hypothesis.

A single Claude call reads the issue's summary, description, and most
recent comments, and returns a JSON blob with the root-cause guess, the
parts of the system likely involved, and a suggested fix direction. The
prompt is deliberately terse: we want a starting point for a human (or a
later Patch agent), not a definitive diagnosis.
"""
from __future__ import annotations

import json
import os
from typing import Any

from anthropic import AsyncAnthropic


_MODEL = os.getenv("BUG_FIX_ANALYZE_MODEL", "claude-sonnet-4-6")
_MAX_COMMENTS = 8


class AnalyzeConfigError(RuntimeError):
    """Raised when the Anthropic credentials are missing or stubbed."""


def _require_api_key() -> str:
    key = os.getenv("ANTHROPIC_API_KEY") or ""
    if not key or key.startswith("your-"):
        raise AnalyzeConfigError(
            "ANTHROPIC_API_KEY is not set (or still the .env.example placeholder)"
        )
    return key


def _build_prompt(jira: dict[str, Any]) -> str:
    summary = jira.get("summary") or "(no summary)"
    description = (jira.get("description") or "(no description)")[:4000]
    comments = jira.get("comments") or []
    recent = comments[-_MAX_COMMENTS:]
    comment_block = "\n".join(
        f"- [{c.get('updated','')}] {c.get('author','?')}: {c.get('body','')[:400]}"
        for c in recent
    ) or "(no comments)"

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
        f"Components: {', '.join(jira.get('components') or []) or '(none)'}\n"
        f"\nDescription:\n{description}\n"
        f"\nRecent comments:\n{comment_block}\n"
    )


def _parse_analysis(text: str) -> dict[str, Any]:
    """Pull a JSON object out of the model's response, tolerating fences."""
    stripped = text.strip()
    if stripped.startswith("```"):
        # ```json … ``` or ``` … ```
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


async def analyze_jira_issue(jira_detail: dict[str, Any]) -> dict[str, Any]:
    """Run the LLM analyze pass. Caller is responsible for catching errors."""
    api_key = _require_api_key()
    client = AsyncAnthropic(api_key=api_key)
    prompt = _build_prompt(jira_detail)
    msg = await client.messages.create(
        model=_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    text = ""
    for block in msg.content:
        # Only TextBlock has `.text`; tool-use blocks shouldn't appear here.
        if getattr(block, "type", None) == "text":
            text += getattr(block, "text", "")
    return _parse_analysis(text)
