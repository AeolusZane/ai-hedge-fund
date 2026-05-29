"""BugFixExecutor — canvas-driven execution.

The Jira Issue Input node and the (former) Fetch Jira stage are merged:
the input node both holds the issue key AND performs the MCP fetch as
the first step of the run. Downstream stages (Analyze, Patch, Test,
Open PR) read state["jira_detail"] populated by the input.

When the canvas is empty we fall back to a built-in sequence: an
implicit fetch followed by the four stub stages. Fetch failures (real or
default) terminate the run via JiraFetchError — there is nothing
meaningful to do without the Jira context.
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


# Default stages run in order when the caller doesn't draw a graph.
# The implicit fetch happens before this list and isn't represented here.
_DEFAULT_STAGES = [
    ("analyze", "Analyze"),
    ("patch", "Patch"),
    ("test", "Test"),
    ("open_pr", "Open PR"),
]


class JiraFetchError(RuntimeError):
    """Raised to abort the whole run when the Jira fetch fails."""


def _stage_label(name: str) -> str:
    return {
        "Jira Issue Input": "Fetching Jira issue",
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


_RUNNABLE_TYPES = {"jira-issue-input-node", "bug-fix-stage-node"}


class BugFixExecutor(WorkflowExecutor):
    domain = "bug_fix"

    async def run(self, request: dict[str, Any], context: ExecutorContext) -> dict[str, Any]:
        delay = float(request.get("stage_delay_seconds", 0.4))
        issue_key = str(request.get("jira_issue") or "").strip()
        if not issue_key:
            raise ValueError("jira_issue is required in the request payload")

        graph_nodes = request.get("graph_nodes") or []
        graph_edges = request.get("graph_edges") or []
        runnable_nodes = [n for n in graph_nodes if n.get("type") in _RUNNABLE_TYPES]

        state: dict[str, Any] = {
            "issue_key": issue_key,
            "api_keys": context.api_keys,
        }

        try:
            if runnable_nodes:
                stages_executed = await self._run_graph(
                    runnable_nodes, graph_edges, delay, state, context
                )
            else:
                stages_executed = await self._run_default(delay, state, context)
        except JiraFetchError as e:
            raise RuntimeError(str(e)) from e

        return self._build_result(issue_key, state, stages_executed)

    async def _run_graph(
        self,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        delay: float,
        state: dict[str, Any],
        context: ExecutorContext,
    ) -> list[dict[str, str]]:
        ordered = _topological_order(nodes, edges)
        stages_executed: list[dict[str, str]] = []
        for n in ordered:
            if context.is_cancelled():
                raise asyncio.CancelledError()
            node_type = n.get("type", "")
            node_data = n.get("data") or {}
            node_id = n["id"]
            if node_type == "jira-issue-input-node":
                stage_name = "Jira Issue Input"
            else:
                stage_name = node_data.get("name", "")
            stages_executed.append({"node_id": node_id, "name": stage_name})
            await self._run_node(
                node_id=node_id,
                node_type=node_type,
                node_data=node_data,
                stage_name=stage_name,
                delay=delay,
                state=state,
                context=context,
            )
        return stages_executed

    async def _run_default(
        self,
        delay: float,
        state: dict[str, Any],
        context: ExecutorContext,
    ) -> list[dict[str, str]]:
        # Implicit fetch first (no node on the canvas to represent it).
        stages_executed = [{"node_id": "jira_input", "name": "Jira Issue Input"}]
        await self._run_node(
            node_id="jira_input",
            node_type="jira-issue-input-node",
            node_data={},
            stage_name="Jira Issue Input",
            delay=delay,
            state=state,
            context=context,
        )
        for node_id, name in _DEFAULT_STAGES:
            if context.is_cancelled():
                raise asyncio.CancelledError()
            stages_executed.append({"node_id": node_id, "name": name})
            await self._run_node(
                node_id=node_id,
                node_type="bug-fix-stage-node",
                node_data={},
                stage_name=name,
                delay=delay,
                state=state,
                context=context,
            )
        return stages_executed

    async def _run_node(
        self,
        *,
        node_id: str,
        node_type: str,
        node_data: dict[str, Any],
        stage_name: str,
        delay: float,
        state: dict[str, Any],
        context: ExecutorContext,
    ) -> None:
        context.emit(ProgressEvent(node_id=node_id, status=_stage_label(stage_name)))
        done_payload: dict[str, Any] = {"stage": stage_name}

        if node_type == "jira-issue-input-node":
            await self._do_fetch(node_id, state, done_payload, context)
        elif stage_name == "Analyze":
            await self._do_analyze(node_data, state, done_payload)
        else:
            await asyncio.sleep(delay)

        context.emit(ProgressEvent(node_id=node_id, status="Done", payload=done_payload))

    async def _do_fetch(
        self,
        node_id: str,
        state: dict[str, Any],
        done_payload: dict[str, Any],
        context: ExecutorContext,
    ) -> None:
        try:
            detail = await get_issue_detail(state["issue_key"])
        except JiraMcpConfigError as e:
            message = f"Jira MCP not configured: {e}"
            done_payload["error"] = message
            # Emit Done so the canvas tile reflects the failure before we abort.
            context.emit(ProgressEvent(node_id=node_id, status="Done", payload=done_payload))
            raise JiraFetchError(message)
        except JiraMcpToolError as e:
            done_payload["error"] = str(e)
            context.emit(ProgressEvent(node_id=node_id, status="Done", payload=done_payload))
            raise JiraFetchError(str(e))
        except Exception as e:
            message = f"Jira MCP call failed: {e}"
            done_payload["error"] = message
            context.emit(ProgressEvent(node_id=node_id, status="Done", payload=done_payload))
            raise JiraFetchError(message)

        state["jira_detail"] = detail
        done_payload.update(
            {
                "summary": detail.get("summary"),
                "status": detail.get("status"),
                "assignee": detail.get("assignee"),
            }
        )

    async def _do_analyze(
        self,
        node_data: dict[str, Any],
        state: dict[str, Any],
        done_payload: dict[str, Any],
    ) -> None:
        jira_detail = state.get("jira_detail")
        if not jira_detail:
            state["analyze_error"] = (
                "Analyze requires a Jira Issue Input upstream in the graph"
            )
            done_payload["error"] = state["analyze_error"]
            return
        try:
            analysis = await analyze_jira_issue(
                jira_detail,
                model_name=node_data.get("modelName"),
                model_provider=node_data.get("modelProvider"),
                api_keys=state.get("api_keys"),
            )
        except AnalyzeConfigError as e:
            state["analyze_error"] = f"Analyze not configured: {e}"
            done_payload["error"] = state["analyze_error"]
            return
        except Exception as e:
            state["analyze_error"] = f"Analyze failed: {e}"
            done_payload["error"] = state["analyze_error"]
            return
        state["analysis"] = analysis
        done_payload["root_cause_hypothesis"] = analysis.get("root_cause_hypothesis")

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
        jira_detail = state.get("jira_detail")
        if jira_detail:
            result["jira"] = jira_detail
            result["summary"] = jira_detail.get("summary") or f"Stub fix applied for {issue_key}"
        else:
            result["summary"] = f"Stub fix applied for {issue_key}"
        if "analysis" in state:
            result["analysis"] = state["analysis"]
        if state.get("analyze_error"):
            result["analyze_error"] = state["analyze_error"]
        return result
