"""BugFixExecutor — canvas-driven execution with a hard-coded fallback.

When the request supplies `graph_nodes` / `graph_edges`, we walk the
React Flow graph in topological order and execute one stage per node,
keyed by the human-readable name carried in `node.data.name`. Without a
graph we keep the original fixed five-stage sequence so the dialog form
path still works for callers that don't draw anything on the canvas.

Only `Fetch Jira` actually hits the Jira MCP server today; the rest are
still stubs that sleep + report Done. Wiring those up to real work is a
later phase.
"""
from __future__ import annotations

import asyncio
from collections import deque
from typing import Any

from app.backend.core.executors import ExecutorContext, ProgressEvent, WorkflowExecutor
from app.backend.domains.bug_fix.analyze_agent import AnalyzeConfigError, analyze_jira_issue
from app.backend.domains.bug_fix.jira_client import (
    JiraMcpConfigError,
    JiraMcpToolError,
    get_issue_detail,
)


# Default stages used when the caller doesn't draw a graph.
_DEFAULT_STAGES = [
    ("fetch_jira", "Fetch Jira", "Fetching Jira issue"),
    ("analyze", "Analyze", "Analyzing root cause"),
    ("patch", "Patch", "Drafting patch"),
    ("test", "Test", "Running tests"),
    ("open_pr", "Open PR", "Opening pull request"),
]


def _stage_label(name: str) -> str:
    return {
        "Fetch Jira": "Fetching Jira issue",
        "Analyze": "Analyzing root cause",
        "Patch": "Drafting patch",
        "Test": "Running tests",
        "Open PR": "Opening pull request",
    }.get(name, name)


def _topological_order(
    nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Kahn's algorithm. Falls back to input order if the graph has a cycle."""
    by_id = {n["id"]: n for n in nodes if "id" in n}
    indeg: dict[str, int] = {nid: 0 for nid in by_id}
    out: dict[str, list[str]] = {nid: [] for nid in by_id}
    for e in edges:
        src, tgt = e.get("source"), e.get("target")
        if src in by_id and tgt in by_id:
            out[src].append(tgt)
            indeg[tgt] += 1
    queue = deque([nid for nid, d in indeg.items() if d == 0])
    ordered: list[str] = []
    while queue:
        nid = queue.popleft()
        ordered.append(nid)
        for nxt in out[nid]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)
    if len(ordered) != len(by_id):
        return list(by_id.values())  # cycle — fall back
    return [by_id[nid] for nid in ordered]


class BugFixExecutor(WorkflowExecutor):
    domain = "bug_fix"

    async def run(self, request: dict[str, Any], context: ExecutorContext) -> dict[str, Any]:
        delay = float(request.get("stage_delay_seconds", 0.4))
        issue_key = str(request.get("jira_issue") or "").strip()
        if not issue_key:
            raise ValueError("jira_issue is required in the request payload")

        graph_nodes = request.get("graph_nodes") or []
        graph_edges = request.get("graph_edges") or []
        bug_fix_nodes = [
            n for n in graph_nodes if n.get("type") == "bug-fix-stage-node"
        ]

        state: dict[str, Any] = {
            "issue_key": issue_key,
            "analyze_model_name": request.get("analyze_model_name"),
            "analyze_model_provider": request.get("analyze_model_provider"),
            "api_keys": context.api_keys,
        }

        if bug_fix_nodes:
            ordered = _topological_order(bug_fix_nodes, graph_edges)
            stages_executed = [
                {"node_id": n["id"], "name": (n.get("data") or {}).get("name", "")}
                for n in ordered
            ]
            for n in ordered:
                if context.is_cancelled():
                    raise asyncio.CancelledError()
                await self._run_stage(
                    node_id=n["id"],
                    stage_name=(n.get("data") or {}).get("name", ""),
                    delay=delay,
                    state=state,
                    context=context,
                )
        else:
            stages_executed = [
                {"node_id": node_id, "name": name}
                for (node_id, name, _) in _DEFAULT_STAGES
            ]
            for node_id, name, _label in _DEFAULT_STAGES:
                if context.is_cancelled():
                    raise asyncio.CancelledError()
                await self._run_stage(
                    node_id=node_id,
                    stage_name=name,
                    delay=delay,
                    state=state,
                    context=context,
                )

        return self._build_result(issue_key, state, stages_executed)

    async def _run_stage(
        self,
        *,
        node_id: str,
        stage_name: str,
        delay: float,
        state: dict[str, Any],
        context: ExecutorContext,
    ) -> None:
        context.emit(ProgressEvent(node_id=node_id, status=_stage_label(stage_name)))

        done_payload: dict[str, Any] = {"stage": stage_name}

        if stage_name == "Fetch Jira":
            try:
                detail = await get_issue_detail(state["issue_key"])
                state["jira_detail"] = detail
                done_payload.update(
                    {
                        "summary": detail.get("summary"),
                        "status": detail.get("status"),
                        "assignee": detail.get("assignee"),
                    }
                )
            except JiraMcpConfigError as e:
                state["jira_error"] = f"Jira MCP not configured: {e}"
                done_payload["error"] = state["jira_error"]
            except JiraMcpToolError as e:
                state["jira_error"] = str(e)
                done_payload["error"] = state["jira_error"]
            except Exception as e:  # network, spawn failure, etc.
                state["jira_error"] = f"Jira MCP call failed: {e}"
                done_payload["error"] = state["jira_error"]
        elif stage_name == "Analyze":
            jira_detail = state.get("jira_detail")
            if not jira_detail:
                state["analyze_error"] = (
                    "Analyze requires Fetch Jira to run earlier in the graph"
                )
                done_payload["error"] = state["analyze_error"]
            else:
                try:
                    analysis = await analyze_jira_issue(
                        jira_detail,
                        model_name=state.get("analyze_model_name"),
                        model_provider=state.get("analyze_model_provider"),
                        api_keys=state.get("api_keys"),
                    )
                    state["analysis"] = analysis
                    done_payload["root_cause_hypothesis"] = analysis.get(
                        "root_cause_hypothesis"
                    )
                except AnalyzeConfigError as e:
                    state["analyze_error"] = f"Analyze not configured: {e}"
                    done_payload["error"] = state["analyze_error"]
                except Exception as e:
                    state["analyze_error"] = f"Analyze failed: {e}"
                    done_payload["error"] = state["analyze_error"]
        else:
            # Stub: sleep + report Done.
            await asyncio.sleep(delay)

        context.emit(ProgressEvent(node_id=node_id, status="Done", payload=done_payload))

    def _build_result(
        self,
        issue_key: str,
        state: dict[str, Any],
        stages_executed: list[dict[str, str]],
    ) -> dict[str, Any]:
        branch = f"fix/{issue_key.lower()}"
        result: dict[str, Any] = {
            "jira_issue": issue_key,
            "branch": branch,
            "pr_url": f"https://example.invalid/pulls/{issue_key.lower()}",
            "stages_executed": stages_executed,
        }
        jira_error = state.get("jira_error")
        jira_detail = state.get("jira_detail")
        if jira_error:
            result["jira_error"] = jira_error
            result["summary"] = f"(Jira fetch failed) {jira_error}"
        elif jira_detail:
            result["jira"] = jira_detail
            result["summary"] = jira_detail.get("summary") or f"Stub fix applied for {issue_key}"
        else:
            result["summary"] = f"Stub fix applied for {issue_key}"
        if "analysis" in state:
            result["analysis"] = state["analysis"]
        if state.get("analyze_error"):
            result["analyze_error"] = state["analyze_error"]
        return result
