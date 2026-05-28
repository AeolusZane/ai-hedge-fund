"""BugFixExecutor — partially-real bug-fix workflow.

`fetch_jira` now talks to the user's Jira MCP server and surfaces the real
issue summary/status. The remaining stages (analyze, patch, test, open_pr)
stay stubbed until later phases wire up code-fix and PR automation.
"""
from __future__ import annotations

import asyncio
from typing import Any

from app.backend.core.executors import ExecutorContext, ProgressEvent, WorkflowExecutor
from app.backend.domains.bug_fix.jira_client import (
    JiraMcpConfigError,
    JiraMcpToolError,
    get_issue_detail,
)


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
        # Allow callers (e.g. tests) to shorten the stub stages.
        delay = float(request.get("stage_delay_seconds", 0.4))
        issue_key = str(request.get("jira_issue") or "").strip()
        if not issue_key:
            raise ValueError("jira_issue is required in the request payload")

        jira_detail: dict[str, Any] = {}
        jira_error: str | None = None

        for node_id, status in _STAGES:
            if context.is_cancelled():
                raise asyncio.CancelledError()
            context.emit(ProgressEvent(node_id=node_id, status=status))

            if node_id == "fetch_jira":
                try:
                    jira_detail = await get_issue_detail(issue_key)
                except JiraMcpConfigError as e:
                    jira_error = f"Jira MCP not configured: {e}"
                except JiraMcpToolError as e:
                    jira_error = str(e)
                except Exception as e:  # network, spawn failure, etc.
                    jira_error = f"Jira MCP call failed: {e}"

                done_payload: dict[str, Any] = {"stage": node_id}
                if jira_error:
                    done_payload["error"] = jira_error
                else:
                    done_payload.update(
                        {
                            "summary": jira_detail.get("summary"),
                            "status": jira_detail.get("status"),
                            "assignee": jira_detail.get("assignee"),
                        }
                    )
                context.emit(
                    ProgressEvent(node_id=node_id, status="Done", payload=done_payload)
                )
            else:
                # Stub stages still just sleep + report Done.
                await asyncio.sleep(delay)
                context.emit(
                    ProgressEvent(node_id=node_id, status="Done", payload={"stage": node_id})
                )

        branch = f"fix/{issue_key.lower()}"
        result: dict[str, Any] = {
            "jira_issue": issue_key,
            "branch": branch,
            "pr_url": f"https://example.invalid/pulls/{issue_key.lower()}",
        }
        if jira_error:
            result["jira_error"] = jira_error
            result["summary"] = f"(Jira fetch failed) {jira_error}"
        else:
            result["jira"] = jira_detail
            result["summary"] = jira_detail.get("summary") or f"Stub fix applied for {issue_key}"
        return result
