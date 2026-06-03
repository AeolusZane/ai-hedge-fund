"""Open PR stage — creates a Bitbucket PR for an existing branch.

This stage assumes the fix branch already exists (created by Patch or
manually). It only creates the PR via the Bitbucket REST API — no local
git operations.

Required inputs:
  - project: Bitbucket project key (e.g. "AI")
  - repo: Repository slug (e.g. "corevo")
  - from_branch: Source branch (e.g. "fix/bug-123")
  - to_branch: Target branch (e.g. "main")
"""
from __future__ import annotations

from typing import Any

from app.backend.domains.bug_fix.bitbucket_client import (
    BitbucketMcpConfigError,
    BitbucketMcpToolError,
    create_pr,
)


class PrConfigError(RuntimeError):
    pass


async def open_pr(
    *,
    issue_key: str,
    summary: str,
    project: str,
    repo: str,
    from_branch: str,
    to_branch: str,
    analysis: dict[str, Any] | None = None,
    from_project: str | None = None,
    from_repo: str | None = None,
) -> dict[str, Any]:
    """Create a Bitbucket PR for an existing branch.

    Args:
        issue_key: Jira issue key (e.g. "BUG-123")
        summary: Issue summary for PR title
        project: Bitbucket project key (target repo)
        repo: Repository slug (target repo)
        from_branch: Source branch name
        to_branch: Target branch name
        analysis: Optional analysis result from Analyze stage
        from_project: Optional project key for source repo (fork)
        from_repo: Optional repo slug for source repo (fork)

    Returns:
        Dict with PR details including id, url, etc.
    """
    if not project or not repo:
        raise PrConfigError(
            "project and repo are required (set them on the Open PR node)"
        )
    if not from_branch:
        raise PrConfigError("from_branch is required")

    commit_message = f"{issue_key}: {summary}".strip() or issue_key

    description_lines = [f"Auto-opened by bug_fix workflow for {issue_key}."]
    if analysis:
        if analysis.get("root_cause_hypothesis"):
            description_lines.append("")
            description_lines.append(f"**Root cause:** {analysis['root_cause_hypothesis']}")
        steps = analysis.get("suggested_approach") or []
        if steps:
            description_lines.append("")
            description_lines.append("**Approach:**")
            for step in steps:
                description_lines.append(f"- {step}")

    try:
        pr_payload = await create_pr(
            project=project,
            repo=repo,
            title=commit_message,
            from_branch=from_branch,
            to_branch=to_branch or "main",
            description="\n".join(description_lines),
            from_project=from_project,
            from_repo=from_repo,
        )
    except BitbucketMcpConfigError as e:
        raise PrConfigError(f"Bitbucket MCP not configured: {e}")
    except BitbucketMcpToolError as e:
        raise PrConfigError(str(e))

    return {
        "branch": from_branch,
        "pr": pr_payload,
    }
