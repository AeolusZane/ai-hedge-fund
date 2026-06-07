"""PR Feedback Sync — LLM-powered analysis of PR review comments.

Reviewers write natural language comments on the PR. This module reads those
comments and uses an LLM to judge the fix quality, extract actionable feedback,
and derive a rating — no structured format required from the reviewer.

Flow:
1. Agent creates PR → posts a brief "this was auto-generated" marker comment
2. Reviewer reviews code normally — writes whatever they want in natural language
3. Sync reads all PR comments → sends to LLM → LLM judges quality & extracts lessons
4. LLM output (rating, feedback, difficulty, lesson) is written back to experience store
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from app.backend.domains.bug_fix.bitbucket_client import (
    get_pr_comments,
    post_pr_comment,
    BitbucketMcpConfigError,
    BitbucketMcpToolError,
)
from app.backend.domains.bug_fix.experience_store import ExperienceStore

logger = logging.getLogger(__name__)

# LLM config — reuse the same provider/model as the analyze stage
_DEFAULT_PROVIDER = os.getenv("BUG_FIX_ANALYZE_PROVIDER", "Anthropic")
_DEFAULT_MODEL = os.getenv("BUG_FIX_ANALYZE_MODEL", "claude-sonnet-4-6")

# ─── PR Marker Comment ───────────────────────────────────────────────────────

# Minimal marker — not a feedback form, just a note that this PR is auto-generated
PR_MARKER_TEMPLATE = """\
> **Bug Fix Agent** · {issue_key}
>
> This PR was automatically generated. Review comments will be analyzed to improve future fixes.
>
> _Experience ID: {experience_id}_
"""


# ─── LLM Analysis ────────────────────────────────────────────────────────────

_ANALYSIS_PROMPT = """\
You are analyzing code review comments on a pull request that was automatically generated
by a Bug Fix Agent. Your job is to evaluate the quality of the fix based on reviewer feedback
and extract actionable lessons for the agent to learn from.

## Bug Context
- **Issue:** {issue_key} — {issue_summary}
- **Bug Type:** {bug_type}
- **Root Cause (agent's analysis):** {root_cause}
- **Patch Strategy:** {patch_strategy}
- **Files Changed:** {files_changed}

## Reviewer Comments
{comments_text}

## Your Task

Analyze ALL reviewer comments and produce a structured assessment. Reviewers write in
natural language — they may be brief ("LGTM"), detailed ("this approach won't work because..."),
or anywhere in between. You need to read between the lines.

Guidelines for rating:
- If reviewers approved or said "LGTM" / "looks good" / "approved" → rating 4-5
- If reviewers had minor suggestions but overall positive → rating 3-4
- If reviewers pointed out issues but the direction was right → rating 2-3
- If reviewers rejected the approach or found fundamental problems → rating 1-2
- If there are no substantive comments (only approvals or no comments) → rating 3 (neutral)

Guidelines for difficulty:
- L1: Trivial fix (typo, missing import, simple null check)
- L2: Straightforward bug with clear fix pattern
- L3: Requires understanding of system context or multiple components
- L4: Complex — concurrency, distributed systems, subtle race conditions

Respond with ONLY a JSON object (no markdown, no code fences):
{{
  "rating": <1-5 integer>,
  "difficulty": "<L1|L2|L3|L4>",
  "sentiment": "<positive|mixed|negative>",
  "feedback_summary": "<2-3 sentence summary of what reviewers said>",
  "lesson": "<one actionable lesson the agent should learn from this review, or empty string if nothing notable>",
  "lesson_tags": ["<tag1>", "<tag2>"],
  "key_concerns": ["<concern1>", "<concern2>"]
}}
"""


async def _call_llm(prompt: str) -> str:
    """Call LLM and return response text."""
    from src.llm.models import ModelProvider, get_model

    provider_name = _DEFAULT_PROVIDER
    model_name = _DEFAULT_MODEL

    # Resolve provider enum
    provider = None
    for p in ModelProvider:
        if p.value.lower() == provider_name.lower():
            provider = p
            break
    if provider is None:
        provider = ModelProvider.ANTHROPIC

    llm = get_model(model_name, provider, api_keys={})
    if llm is None:
        raise RuntimeError(f"get_model returned None for {provider.value}/{model_name}")

    response = await llm.ainvoke(prompt)
    content = getattr(response, "content", response)
    return content if isinstance(content, str) else str(content)


def _parse_llm_response(text: str) -> dict[str, Any]:
    """Parse LLM JSON response, with fallback on parse failure."""
    # Strip markdown code fences if present
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first and last lines (code fences)
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)

    try:
        result = json.loads(cleaned)
        # Validate required fields
        rating = result.get("rating", 3)
        if not isinstance(rating, int) or rating < 1 or rating > 5:
            result["rating"] = 3
        difficulty = result.get("difficulty", "")
        if difficulty not in ("L1", "L2", "L3", "L4"):
            result["difficulty"] = ""
        return result
    except (json.JSONDecodeError, TypeError):
        logger.warning(f"Failed to parse LLM response as JSON: {text[:200]}")
        return {
            "rating": 3,
            "difficulty": "",
            "sentiment": "unknown",
            "feedback_summary": text[:300],
            "lesson": "",
            "lesson_tags": [],
            "key_concerns": [],
        }


# ─── Post Marker ─────────────────────────────────────────────────────────────

async def post_feedback_template(
    *,
    project: str,
    repo: str,
    pr_id: int,
    experience_id: int,
    issue_key: str = "",
) -> bool:
    """Post a brief marker comment on the PR.

    Not a feedback form — just a note that this PR is auto-generated.
    Reviewers will review normally; we analyze their comments later.
    """
    try:
        comment_text = PR_MARKER_TEMPLATE.format(
            issue_key=issue_key,
            experience_id=experience_id,
        )
        await post_pr_comment(
            project=project,
            repo=repo,
            pr_id=pr_id,
            text=comment_text,
        )
        logger.info(f"Posted PR marker on PR #{pr_id} in {project}/{repo}")
        return True
    except (BitbucketMcpConfigError, BitbucketMcpToolError) as e:
        logger.warning(f"Failed to post PR marker on PR #{pr_id}: {e}")
        return False


# ─── Sync ────────────────────────────────────────────────────────────────────

async def sync_pr_feedback(
    *,
    project: str,
    repo: str,
    pr_id: int,
    experience_id: int,
    store: Optional[ExperienceStore] = None,
) -> dict:
    """Read PR comments, send to LLM for analysis, update the experience.

    The LLM reads all reviewer comments and judges:
    - Overall quality rating (1-5)
    - Difficulty level
    - Actionable feedback/lessons
    - Key concerns raised by reviewers
    """
    if store is None:
        store = ExperienceStore()

    exp = store.get_by_id(experience_id)
    if not exp:
        return {"error": f"Experience #{experience_id} not found"}

    # Fetch all PR comments
    try:
        comments = await get_pr_comments(project=project, repo=repo, pr_id=pr_id)
    except (BitbucketMcpConfigError, BitbucketMcpToolError) as e:
        return {"error": f"Failed to fetch PR comments: {e}"}

    # Filter out bot comments and our own marker
    human_comments = []
    for c in comments:
        text = c.get("text", "")
        # Skip our own marker
        if "Bug Fix Agent" in text and "Experience ID:" in text:
            continue
        # Skip bot comments
        author = c.get("author", "")
        if author.startswith("bot-") or author.endswith("[bot]"):
            continue
        # Skip empty or trivial comments
        if len(text.strip()) < 5:
            continue
        human_comments.append(c)

    if not human_comments:
        return {
            "synced": False,
            "message": "No reviewer comments found on this PR yet",
            "total_comments": len(comments),
        }

    # Build comments text for LLM
    comments_text = ""
    for c in human_comments:
        author = c.get("author_display") or c.get("author", "reviewer")
        text = c.get("text", "").strip()
        anchor = c.get("anchor")
        location = ""
        if anchor:
            path = anchor.get("path", "")
            line = anchor.get("line", "")
            if path:
                location = f" (on {path}" + (f":{line}" if line else "") + ")"
        comments_text += f"\n**{author}**{location}:\n{text}\n"

    # Build LLM prompt with bug context
    prompt = _ANALYSIS_PROMPT.format(
        issue_key=exp.issue_key,
        issue_summary=exp.issue_summary[:200],
        bug_type=exp.bug_type or "unknown",
        root_cause=(exp.root_cause or exp.root_cause_hypothesis or "unknown")[:300],
        patch_strategy=exp.patch_strategy or "unknown",
        files_changed=", ".join(exp.files_changed[:10]) if exp.files_changed else "unknown",
        comments_text=comments_text.strip(),
    )

    # Call LLM
    try:
        llm_response = await _call_llm(prompt)
    except Exception as e:
        logger.error(f"LLM call failed for PR #{pr_id}: {e}")
        return {"error": f"LLM analysis failed: {e}"}

    # Parse LLM response
    analysis = _parse_llm_response(llm_response)
    rating = analysis.get("rating", 3)
    difficulty = analysis.get("difficulty", "")
    feedback_summary = analysis.get("feedback_summary", "")
    lesson = analysis.get("lesson", "")
    lesson_tags = analysis.get("lesson_tags", [])
    key_concerns = analysis.get("key_concerns", [])
    sentiment = analysis.get("sentiment", "unknown")

    # Build feedback text that includes the LLM analysis and raw comments
    feedback_parts = [f"[PR #{pr_id} review analysis]"]
    feedback_parts.append(f"Sentiment: {sentiment}")
    if feedback_summary:
        feedback_parts.append(feedback_summary)
    if key_concerns:
        feedback_parts.append(f"Concerns: {'; '.join(key_concerns)}")

    # Append raw reviewer comments for reference
    raw_authors = set()
    for c in human_comments:
        author = c.get("author_display") or c.get("author", "reviewer")
        raw_authors.add(author)
    if raw_authors:
        feedback_parts.append(f"Reviewers: {', '.join(raw_authors)}")

    feedback_text = "\n".join(feedback_parts)

    # Update experience store
    now = datetime.now(timezone.utc).isoformat()
    success = store.sync_pr_feedback(
        exp_id=experience_id,
        rating=rating,
        feedback=feedback_text,
        synced_at=now,
    )

    # Update difficulty and lesson if extracted
    updates = {}
    if difficulty:
        updates["difficulty_level"] = difficulty
    if lesson:
        updates["lesson"] = lesson
    if lesson_tags:
        updates["lesson_tags"] = lesson_tags
    if updates:
        store.update_experience(experience_id, updates)

    logger.info(
        f"Synced PR #{pr_id} feedback: rating={rating}, difficulty={difficulty}, "
        f"sentiment={sentiment}, comments={len(human_comments)}"
    )

    return {
        "synced": success,
        "experience_id": experience_id,
        "rating": rating,
        "difficulty": difficulty,
        "sentiment": sentiment,
        "feedback": feedback_summary,
        "lesson": lesson,
        "lesson_tags": lesson_tags,
        "key_concerns": key_concerns,
        "reviewers": list(raw_authors),
        "pr_id": pr_id,
        "synced_at": now,
    }


async def sync_all_pending(store: Optional[ExperienceStore] = None) -> list[dict]:
    """Sync feedback for all experiences that have a PR but no rating yet."""
    if store is None:
        store = ExperienceStore()

    pending = store.get_unreviewed_with_pr()
    results = []

    for exp in pending:
        if not exp.pr_project or not exp.pr_repo or not exp.pr_id:
            continue
        result = await sync_pr_feedback(
            project=exp.pr_project,
            repo=exp.pr_repo,
            pr_id=exp.pr_id,
            experience_id=exp.id,
            store=store,
        )
        results.append({
            "experience_id": exp.id,
            "issue_key": exp.issue_key,
            **result,
        })

    return results
