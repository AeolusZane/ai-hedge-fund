"""Stub BugFixExecutor used to validate the multi-domain plumbing.

The real implementation would talk to Jira, run a code-fix agent, and
open a PR. For now we emit a sequence of progress events on a short
timer and return a deterministic mock result so the platform run loop,
the generic /workflows/{domain}/run route, and the frontend domain
switcher can all be exercised end-to-end.
"""
from __future__ import annotations

import asyncio
from typing import Any

from app.backend.core.executors import ExecutorContext, ProgressEvent, WorkflowExecutor


_STAGES = [
    ("fetch_jira", "Fetching Jira issue"),
    ("analyze", "Analyzing root cause"),
    ("patch", "Drafting patch"),
    ("test", "Running tests"),
    ("open_pr", "Opening pull request"),
]


class BugFixExecutor(WorkflowExecutor):
    domain = "bug_fix"

    async def run(self, request: dict[str, Any], context: ExecutorContext) -> dict[str, Any]:
        # Allow callers to override the simulated stage delay (defaults to
        # 0.4s per stage; tests can shorten it).
        delay = float(request.get("stage_delay_seconds", 0.4))
        issue_key = str(request.get("jira_issue") or "BUG-0000")

        for node_id, status in _STAGES:
            if context.is_cancelled():
                raise asyncio.CancelledError()
            context.emit(ProgressEvent(node_id=node_id, status=status))
            await asyncio.sleep(delay)
            context.emit(
                ProgressEvent(
                    node_id=node_id,
                    status="Done",
                    payload={"stage": node_id},
                )
            )

        branch = f"fix/{issue_key.lower()}"
        return {
            "jira_issue": issue_key,
            "branch": branch,
            "pr_url": f"https://example.invalid/pulls/{issue_key.lower()}",
            "summary": f"Stub fix applied for {issue_key}",
        }
