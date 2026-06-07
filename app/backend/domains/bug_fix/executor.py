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
import copy
from collections import deque
from typing import Any

from app.backend.core.executors import ExecutorContext, ProgressEvent, WorkflowExecutor
from app.backend.core.workspace import clone_repo, ensure_workspace
from app.backend.domains.bug_fix.analyze_agent import AnalyzeConfigError, analyze_jira_issue
from app.backend.domains.bug_fix.anomaly_detection import AnomalyDetector
from app.backend.domains.bug_fix.jira_client import (
    JiraMcpConfigError,
    JiraMcpToolError,
    get_issue_detail,
)
from app.backend.domains.bug_fix.patch_agent import PatchConfigError, run_patch
from app.backend.domains.bug_fix.pr_agent import PrConfigError, open_pr
from app.backend.domains.bug_fix.token_tracking import aggregate_token_usage


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


def _parse_repo_url(url: str) -> tuple[str, str]:
    """Extract project key and repo slug from a Bitbucket repo URL.

    Supports formats like:
      - https://bitbucket.example.com/projects/PROJ/repos/my-repo
      - https://bitbucket.example.com/projects/PROJ/repos/my-repo/browse
      - /projects/PROJ/repos/my-repo
      - git@bitbucket.example.com:PROJ/my-repo.git  (SSH SCP-style)
      - ssh://git@bitbucket.example.com/PROJ/my-repo.git
      - ssh://git@bitbucket.example.com:7999/PROJ/my-repo.git  (with port)
      - ssh://git@bitbucket.example.com:7999/~user/my-repo.git (fork)
      - https://bitbucket.example.com/scm/PROJ/my-repo.git  (SCM HTTP)

    Returns:
        Tuple of (project, repo). Empty strings if parsing fails.
    """
    import re
    # Match /projects/<project>/repos/<repo> pattern (HTTP/HTTPS browse URLs)
    match = re.search(r"/projects/([^/]+)/repos/([^/]+)", url)
    if match:
        return match.group(1), match.group(2)
    # Match /scm/<project>/<repo>.git pattern (HTTP clone URLs)
    match = re.search(r"/scm/([^/]+)/([^/]+?)(?:\.git)?$", url)
    if match:
        return match.group(1), match.group(2)
    # Strip port number from SSH URLs: ssh://git@host:PORT/path → ssh://git@host/path
    cleaned = re.sub(r"(://[^/:]+):\d+", r"\1", url)
    # Match SSH SCP-style: git@host:PROJ/repo.git
    match = re.search(r":([^/]+)/([^/]+?)(?:\.git)?$", cleaned)
    if match:
        proj = match.group(1)
        # Skip if it looks like a port number rather than a project key
        if not proj.isdigit():
            return proj, match.group(2)
    # Match path-based: .../PROJ/repo.git (after port stripping)
    match = re.search(r"/([^/]+)/([^/]+?)(?:\.git)?$", cleaned)
    if match:
        return match.group(1), match.group(2)
    return "", ""


def _is_fork_url(url: str) -> bool:
    """Check if a remote URL points to a Bitbucket personal fork.

    Bitbucket Server fork URLs contain ~username in the path, e.g.:
      ssh://git@host:7999/~aeolus.zhang/nuclear-webui.git
      https://host/scm/~aeolus.zhang/nuclear-webui.git
    """
    import re
    return bool(re.search(r"[/:]~[^/]+/", url))


async def _extract_lesson(exp: Any) -> tuple[str, list[str]]:
    """Use LLM to distill a reusable lesson from a bug fix experience.

    Incorporates feedback from previously low-rated lessons to improve quality.

    Returns:
        Tuple of (lesson_text, tags_list). Empty strings/list on failure.
    """
    import json as _json
    import os
    from src.llm.models import ModelProvider, get_model

    provider_name = os.getenv("BUG_FIX_ANALYZE_PROVIDER", "Anthropic")
    try:
        provider = ModelProvider(provider_name)
    except ValueError:
        provider = ModelProvider.ANTHROPIC
    model_name = os.getenv("BUG_FIX_ANALYZE_MODEL", "claude-sonnet-4-6")
    llm = get_model(model_name, provider)

    # Gather feedback from low-rated experiences to guide lesson extraction
    feedback_guidance = ""
    try:
        from app.backend.domains.bug_fix.experience_store import ExperienceStore
        store = ExperienceStore()
        low_rated, _ = store.list_experiences(min_rating=1, limit=5, reviewed_only=True)
        low_rated = [e for e in low_rated if e.human_rating is not None and e.human_rating <= 2]
        if low_rated:
            feedback_items = []
            for e in low_rated[:3]:
                feedback_items.append(
                    f"- Lesson \"{e.lesson}\" was rated {e.human_rating}/5. "
                    f"Feedback: {e.human_feedback or '(no feedback)'}"
                )
            feedback_guidance = f"""
## Previous Low-Rated Lessons (AVOID these patterns)
{chr(10).join(feedback_items)}

Learn from these mistakes. Make your lesson more specific, actionable, and focused on the root cause pattern.
"""
    except Exception:
        pass  # Non-fatal

    prompt = f"""You are a senior engineer reviewing a completed bug fix. Extract ONE reusable lesson.

## Bug Fix Summary
- **Issue**: {exp.issue_summary}
- **Bug type**: {exp.bug_type}
- **Root cause**: {exp.root_cause}
- **Fix strategy**: {exp.patch_strategy}
- **Files changed**: {', '.join(exp.files_changed) if exp.files_changed else '(not recorded)'}
{feedback_guidance}
## Task
Write ONE lesson that answers: "Next time you encounter a similar problem, what should you check first?"

Rules:
1. One sentence, max 80 words
2. NO specific file names, variable names, or code — abstract to the pattern level
3. Focus on the *root cause pattern*, not the fix details
4. Be SPECIFIC — "check for null values" is too vague; "when a service method accesses a nested property from an optional parameter, add a null guard at the entry point" is good
5. Give 2-4 short tags for future retrieval (e.g. "auth", "null-check", "concurrency")

Output ONLY valid JSON (no markdown fences):
{{"lesson": "your one-sentence lesson here", "tags": ["tag1", "tag2"]}}"""

    try:
        response = await llm.ainvoke(prompt)
        content = getattr(response, "content", response)
        text = content if isinstance(content, str) else str(content)

        # Parse JSON from response
        stripped = text.strip()
        if stripped.startswith("```"):
            import re
            stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
            stripped = re.sub(r"\s*```$", "", stripped)
        try:
            parsed = _json.loads(stripped)
        except _json.JSONDecodeError:
            import re
            match = re.search(r"\{[^{}]*\}", stripped)
            if match:
                parsed = _json.loads(match.group())
            else:
                return "", []

        lesson = parsed.get("lesson", "")
        tags = parsed.get("tags", [])

        if not lesson or len(lesson) > 500:
            return "", []
        if not isinstance(tags, list):
            tags = []
        tags = [str(t).strip() for t in tags if t][:6]

        return lesson, tags
    except Exception:
        return "", []


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


_RUNNABLE_TYPES = {
    "jira-issue-input-node",
    "bug-fix-stage-node",
    "gate-node",
}


# ─── Gate Registry ─────────────────────────────────────────────────
# Module-level dict for pending gate decisions. Keyed by (run_id, node_id).
# The executor blocks on an asyncio.Event when it hits a gate node;
# the API endpoint sets the decision and triggers the event.

import asyncio
from dataclasses import dataclass, field


@dataclass
class GateDecision:
    """Result of a human gate review."""
    action: str  # "approve" | "reject" | "modify"
    reason: str = ""
    context: str = ""


@dataclass
class PendingGate:
    """A gate waiting for human decision."""
    event: asyncio.Event = field(default_factory=asyncio.Event)
    decision: Optional[GateDecision] = None
    upstream_output: Optional[dict[str, Any]] = None


_pending_gates: dict[tuple[int, str], PendingGate] = {}


def get_pending_gate(run_id: int, node_id: str) -> Optional[PendingGate]:
    return _pending_gates.get((run_id, node_id))


def resolve_gate(run_id: int, node_id: str, decision: GateDecision) -> bool:
    """Resolve a pending gate. Returns True if the gate was found and resolved."""
    gate = _pending_gates.get((run_id, node_id))
    if gate is None:
        return False
    gate.decision = decision
    gate.event.set()
    return True


class BugFixExecutor(WorkflowExecutor):
    domain = "bug_fix"

    async def run(self, request: dict[str, Any], context: ExecutorContext) -> dict[str, Any]:
        delay = float(request.get("stage_delay_seconds", 0.4))
        issue_key = str(request.get("jira_issue") or "").strip()
        
        # Check if this is a rerun from a specific node
        rerun_from_node = request.get("rerun_from_node")
        
        if not issue_key and not rerun_from_node:
            raise ValueError("jira_issue is required in the request payload")

        graph_nodes = request.get("graph_nodes") or []
        graph_edges = request.get("graph_edges") or []
        runnable_nodes = [n for n in graph_nodes if n.get("type") in _RUNNABLE_TYPES]

        # Get run_id from context for workspace isolation
        run_id = context.run_id if hasattr(context, "run_id") else None

        # For reruns, use the provided state; otherwise create fresh state
        if rerun_from_node:
            # State is already populated from the snapshot via the API
            state: dict[str, Any] = {
                "issue_key": issue_key or request.get("issue_key", ""),
                "api_keys": context.api_keys,
                "run_id": run_id,
            }
            # Copy over any existing state from the request (from snapshot)
            for key in ["jira_detail", "analysis", "patch", "repo_path", "pr_target_branch"]:
                if key in request:
                    state[key] = request[key]
            # Add human context if provided
            if request.get("human_context"):
                state["human_context"] = request["human_context"]
        else:
            state = {
                "issue_key": issue_key,
                "api_keys": context.api_keys,
                "run_id": run_id,
            }

        # Initialize anomaly detector
        self._anomaly_detector = AnomalyDetector()

        try:
            if runnable_nodes:
                stages_executed = await self._run_graph(
                    runnable_nodes, graph_edges, delay, state, context,
                    start_from_node=rerun_from_node
                )
            else:
                stages_executed = await self._run_default(delay, state, context)
        except JiraFetchError as e:
            raise RuntimeError(str(e)) from e

        result = self._build_result(issue_key, state, stages_executed)
        
        # Emit anomaly notifications if any were detected
        if hasattr(self, '_anomaly_detector'):
            anomaly_summary = self._anomaly_detector.get_summary()
            if anomaly_summary["anomaly_count"] > 0:
                # Emit each anomaly as a separate progress event
                for anomaly in anomaly_summary["anomalies"]:
                    context.emit(ProgressEvent(
                        node_id=None,  # Global anomaly, not tied to specific node
                        status="Anomaly",
                        payload={
                            "type": "anomaly",
                            "anomaly_type": anomaly["type"],
                            "severity": anomaly["severity"],
                            "message": anomaly["message"],
                            "details": anomaly["details"],
                            "timestamp": anomaly["timestamp"],
                        }
                    ))
        
        return result

    async def _run_graph(
        self,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        delay: float,
        state: dict[str, Any],
        context: ExecutorContext,
        start_from_node: str | None = None,
    ) -> list[dict[str, str]]:
        ordered = _topological_order(nodes, edges)
        stages_executed: list[dict[str, str]] = []
        
        # Initialize state snapshots storage
        if not hasattr(self, '_state_snapshots'):
            self._state_snapshots = {}
        
        run_id = context.run_id or state.get('run_id') or 'default'
        if run_id not in self._state_snapshots:
            self._state_snapshots[run_id] = {}
        
        # If start_from_node is specified, skip nodes before it
        should_execute = start_from_node is None
        for n in ordered:
            node_id = n.get("id", "")
            
            # Check if we've reached the start node
            if not should_execute and node_id == start_from_node:
                should_execute = True
            
            if not should_execute:
                continue  # Skip this node
            
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
            
            # Mark stage start for timeout detection
            if hasattr(self, '_anomaly_detector'):
                self._anomaly_detector.mark_stage_start(node_id)
            
            await self._run_node(
                node_id=node_id,
                node_type=node_type,
                node_data=node_data,
                stage_name=stage_name,
                delay=delay,
                state=state,
                context=context,
            )
            
            # Check for stage timeout after completion
            if hasattr(self, '_anomaly_detector'):
                self._anomaly_detector.check_stage_timeout(node_id, stage_name)
            
            # Save state snapshot after node completes
            # Deep copy to avoid reference issues
            self._state_snapshots[run_id][node_id] = copy.deepcopy(state)
        
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
            await self._do_analyze(node_id, node_data, state, done_payload, context)
        elif stage_name == "Patch":
            await self._do_patch(node_data, state, done_payload)
        elif stage_name == "Open PR":
            await self._do_open_pr(node_data, state, done_payload)
        elif node_type == "gate-node":
            await self._do_gate(node_id, node_data, state, done_payload, context)
        else:
            # Stub: sleep + report Done (Test stage still uses this).
            await asyncio.sleep(delay)

        # Emit Error status when the stage recorded a failure in its
        # payload, so the frontend can paint the node red instead of
        # green.  _do_fetch emits its own terminal event before raising
        # JiraFetchError, so it bypasses this path — fix it there too.
        if done_payload.get("error"):
            context.emit(ProgressEvent(node_id=node_id, status="Error", payload=done_payload))
        else:
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
            # Emit Error so the canvas tile reflects the failure before we abort.
            context.emit(ProgressEvent(node_id=node_id, status="Error", payload=done_payload))
            raise JiraFetchError(message)
        except JiraMcpToolError as e:
            done_payload["error"] = str(e)
            context.emit(ProgressEvent(node_id=node_id, status="Error", payload=done_payload))
            raise JiraFetchError(str(e))
        except Exception as e:
            message = f"Jira MCP call failed: {e}"
            done_payload["error"] = message
            context.emit(ProgressEvent(node_id=node_id, status="Error", payload=done_payload))
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
        node_id: str,
        node_data: dict[str, Any],
        state: dict[str, Any],
        done_payload: dict[str, Any],
        context: ExecutorContext,
    ) -> None:
        jira_detail = state.get("jira_detail")
        if not jira_detail:
            state["analyze_error"] = (
                "Analyze requires a Jira Issue Input upstream in the graph"
            )
            done_payload["error"] = state["analyze_error"]
            return

        # Forward each streamed token to the SSE stream so the canvas
        # can render the response as it grows.
        async def on_token(token: str) -> None:
            context.emit(
                ProgressEvent(
                    node_id=node_id,
                    status="Analyzing root cause",
                    payload={"chunk": token},
                )
            )

        # Forward structured decision steps to the SSE stream so the
        # frontend can build a decision tree visualization.
        async def on_decision_step(step: dict[str, Any]) -> None:
            context.emit(
                ProgressEvent(
                    node_id=node_id,
                    status="Analyzing root cause",
                    payload={"decision_step": step},
                )
            )

        # Clone repo early so Analyze can search the codebase.
        # The repoUrl can be set on the Analyze node itself; if not,
        # we fall back to Jira-only analysis (no code search).
        repo_path = state.get("repo_path")  # may already exist from re-run
        repo_url = str(node_data.get("repoUrl") or "").strip()
        target_branch = str(node_data.get("targetBranch") or "main").strip()
        if repo_url and not repo_path:
            run_id = state.get("run_id")
            if not run_id:
                import time
                run_id = int(time.time())
                state["run_id"] = run_id
            try:
                repo_path_obj = await clone_repo(
                    run_id=run_id,
                    repo_url=repo_url,
                    branch=target_branch,
                    repo_name="repo",
                )
                repo_path = str(repo_path_obj)
                state["repo_path"] = repo_path
                state["pr_target_branch"] = target_branch
            except Exception as e:
                # Non-fatal: analysis continues without code search
                context.emit(
                    ProgressEvent(
                        node_id=node_id,
                        status="Analyzing root cause",
                        payload={"warning": f"Repo clone failed: {e}. Continuing without code search."},
                    )
                )

        try:
            analysis = await analyze_jira_issue(
                jira_detail,
                model_name=node_data.get("modelName"),
                model_provider=node_data.get("modelProvider"),
                api_keys=state.get("api_keys"),
                on_token=on_token,
                on_decision_step=on_decision_step,
                repo_path=repo_path,
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
        # Forward token usage for cost tracking
        if "_token_usage" in analysis:
            done_payload["token_usage"] = analysis["_token_usage"]
            state["analyze_token_usage"] = analysis["_token_usage"]

    async def _do_patch(
        self,
        node_data: dict[str, Any],
        state: dict[str, Any],
        done_payload: dict[str, Any],
    ) -> None:
        # Get repo URL from node config
        repo_url = str(node_data.get("repoUrl") or "").strip()
        target_branch = str(node_data.get("targetBranch") or "").strip() or "main"
        jira_detail = state.get("jira_detail")
        
        if not repo_url:
            state["patch_error"] = "Patch needs a repo URL (fill the repoUrl field on the Patch node)"
            done_payload["error"] = state["patch_error"]
            return
        if not jira_detail:
            state["patch_error"] = "Patch requires a Jira Issue Input upstream"
            done_payload["error"] = state["patch_error"]
            return
        
        # Clone repo into workspace
        run_id = state.get("run_id")
        if not run_id:
            # Generate a temporary run_id when flow_id wasn't provided
            import time
            run_id = int(time.time())
            state["run_id"] = run_id

        try:
            repo_path_obj = await clone_repo(
                run_id=run_id,
                repo_url=repo_url,
                branch=target_branch,
                repo_name="repo",
            )
            repo_path = str(repo_path_obj)
        except Exception as e:
            state["patch_error"] = f"Failed to clone repo: {e}"
            done_payload["error"] = state["patch_error"]
            return
        
        # Cache for downstream stages (Open PR needs the same path)
        state["repo_path"] = repo_path
        state["pr_target_branch"] = target_branch
        
        try:
            result = await run_patch(
                repo_path, jira_detail, state.get("analysis"),
                target_branch=target_branch,
            )
        except PatchConfigError as e:
            state["patch_error"] = str(e)
            done_payload["error"] = state["patch_error"]
            return
        except Exception as e:
            state["patch_error"] = f"Patch failed: {e}"
            done_payload["error"] = state["patch_error"]
            return
        state["patch"] = result
        done_payload["files_changed"] = result.get("files_changed", [])
        done_payload["patch_status"] = result.get("status", "applied")
        if result.get("status") == "blocked":
            done_payload["blocker_reason"] = result.get("blocker_reason", "")
            done_payload["blocker_next_step"] = result.get("blocker_next_step", "")

    async def _do_gate(
        self,
        node_id: str,
        node_data: dict[str, Any],
        state: dict[str, Any],
        done_payload: dict[str, Any],
        context: ExecutorContext,
    ) -> None:
        """Gate node — pause execution and wait for human approval.

        Emits a 'Gate' status event with upstream output, then blocks
        until the API endpoint resolves the gate via resolve_gate().
        """
        run_id = state.get("run_id") or context.run_id or 0
        prompt = node_data.get("prompt") or node_data.get("name") or "Review and approve to continue"

        # Gather upstream output (last completed stage's result)
        upstream = {}
        for key in ["analysis", "patch", "open_pr"]:
            if key in state:
                upstream[key] = state[key]

        # Register pending gate
        gate = PendingGate(upstream_output=upstream)
        _pending_gates[(run_id, node_id)] = gate

        # Emit gate waiting event
        context.emit(ProgressEvent(
            node_id=node_id,
            status="Gate",
            payload={
                "prompt": prompt,
                "upstream_output": upstream,
                "action": "waiting",
            },
        ))

        # Block until decision arrives or run is cancelled
        try:
            while not gate.event.is_set():
                if context.is_cancelled():
                    raise asyncio.CancelledError()
                try:
                    await asyncio.wait_for(gate.event.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    continue
        finally:
            _pending_gates.pop((run_id, node_id), None)

        decision = gate.decision
        if decision is None:
            done_payload["error"] = "Gate cancelled"
            return

        done_payload["gate_action"] = decision.action
        done_payload["gate_reason"] = decision.reason

        if decision.action == "reject":
            done_payload["error"] = f"Rejected: {decision.reason or 'no reason given'}"
        elif decision.action == "modify" and decision.context:
            state["human_context"] = decision.context

        # ── Experience Storage: save approved/modified cases ────────
        if decision.action in ("approve", "modify"):
            try:
                from app.backend.domains.bug_fix.experience_store import (
                    ExperienceStore,
                    build_experience_from_state,
                )
                store = ExperienceStore()
                exp = build_experience_from_state(state, gate_action=decision.action)
                if decision.context:
                    exp.human_context = decision.context

                # ── Lesson Extraction: LLM distills a reusable lesson ──
                try:
                    lesson, tags = await _extract_lesson(exp)
                    exp.lesson = lesson
                    exp.lesson_tags = tags
                except Exception as le:
                    import logging
                    logging.getLogger(__name__).warning(
                        f"Lesson extraction failed (non-fatal): {le}"
                    )

                exp_id = store.store(exp)
                store.build_vectors()
                done_payload["experience_stored"] = True
                done_payload["experience_id"] = exp_id
                done_payload["lesson"] = exp.lesson
                done_payload["lesson_tags"] = exp.lesson_tags

                # ── Evolution Metrics: record per-run metrics ──
                try:
                    # Calculate cumulative metrics
                    total_metrics = store.get_metrics_timeline(limit=10000)
                    total_runs = len(total_metrics) + 1
                    success_count = sum(
                        1 for m in total_metrics if m.get("first_fix_success") == 1
                    ) + (1 if state.get("first_fix_success") == 1 else 0)
                    total_iterations = sum(
                        m.get("iteration_count", 0) for m in total_metrics
                    ) + exp.iteration_count
                    total_knowledge = sum(
                        m.get("knowledge_used", 0) for m in total_metrics if m.get("knowledge_recalled", 0) > 0
                    )
                    total_recalled = sum(
                        m.get("knowledge_recalled", 0) for m in total_metrics if m.get("knowledge_recalled", 0) > 0
                    )

                    store.record_metrics({
                        "run_id": str(state.get("run_id", "")),
                        "experience_id": exp_id,
                        "difficulty_level": exp.difficulty_level,
                        "first_fix_success": exp.first_fix_success,
                        "iteration_count": exp.iteration_count,
                        "duration_seconds": exp.duration_seconds,
                        "knowledge_recalled": len(state.get("recalled_experiences", [])),
                        "knowledge_used": len(exp.knowledge_used),
                        "code_cache_hit": state.get("code_cache_hit", 0),
                        "code_cache_miss": state.get("code_cache_miss", 0),
                        "cumulative_first_fix_rate": success_count / total_runs if total_runs > 0 else 0,
                        "cumulative_avg_iterations": total_iterations / total_runs if total_runs > 0 else 0,
                        "cumulative_knowledge_utilization": total_knowledge / total_recalled if total_recalled > 0 else 0,
                    })
                except Exception as me:
                    import logging
                    logging.getLogger(__name__).warning(
                        f"Failed to record evolution metrics (non-fatal): {me}"
                    )

                # Emit a progress event so the frontend knows
                context.emit(ProgressEvent(
                    node_id=node_id,
                    status="Experience Stored",
                    payload={
                        "type": "experience_stored",
                        "experience_id": exp_id,
                        "issue_key": exp.issue_key,
                        "bug_type": exp.bug_type,
                        "confidence": exp.confidence,
                        "lesson": exp.lesson,
                        "lesson_tags": exp.lesson_tags,
                    },
                ))
            except Exception as e:
                # Non-fatal: log but don't block the pipeline
                import logging
                logging.getLogger(__name__).warning(
                    f"Failed to store experience: {e}"
                )
                done_payload["experience_stored"] = False

    async def _do_open_pr(
        self,
        node_data: dict[str, Any],
        state: dict[str, Any],
        done_payload: dict[str, Any],
    ) -> None:
        jira_detail = state.get("jira_detail") or {}
        issue_key = state.get("issue_key") or jira_detail.get("key") or "BUG"

        # Parse repoUrl to extract project/repo if provided
        project = str(node_data.get("project") or "").strip() or state.get("pr_project") or ""
        repo = str(node_data.get("repo") or "").strip() or state.get("pr_repo") or ""
        repo_url = str(node_data.get("repoUrl") or "").strip()
        if repo_url and (not project or not repo):
            parsed_project, parsed_repo = _parse_repo_url(repo_url)
            project = project or parsed_project
            repo = repo or parsed_repo

        # If the URL is a fork, query Bitbucket API to find the origin (main repo).
        # This allows users to just fill in their fork URL and have PRs auto-target the main repo.
        if _is_fork_url(repo_url) and project and repo:
            try:
                from app.backend.domains.bug_fix.bitbucket_client import get_repo_info
                repo_info = await get_repo_info(project=project, repo=repo)
                origin = repo_info.get("origin")
                if origin:
                    origin_project = origin.get("project", {}).get("key", "")
                    origin_repo = origin.get("slug", "")
                    if origin_project and origin_repo:
                        # Store fork info for push, use origin for PR target
                        state["pr_fork_project"] = project
                        state["pr_fork_repo"] = repo
                        project = origin_project
                        repo = origin_repo
            except Exception:
                pass  # API not configured or failed — fall through to use fork directly

        # Fallback: auto-detect project/repo from git remotes.
        # Strategy: if user specified a prTargetRemote, use that remote's URL.
        # Otherwise, classify each remote URL as "fork" (contains ~username)
        # or "main repo" (no ~). PR target = first non-fork remote.
        if (not project or not repo) and state.get("repo_path"):
            try:
                import subprocess
                remotes = subprocess.check_output(
                    ["git", "remote"],
                    cwd=state["repo_path"],
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                ).decode().strip().splitlines()
                # If user specified a target remote, use it directly
                preferred = str(node_data.get("prTargetRemote") or "").strip()
                if preferred and preferred in remotes:
                    remote_url = subprocess.check_output(
                        ["git", "remote", "get-url", preferred],
                        cwd=state["repo_path"],
                        stderr=subprocess.DEVNULL,
                        timeout=5,
                    ).decode().strip()
                    if remote_url:
                        parsed_project, parsed_repo = _parse_repo_url(remote_url)
                        project = project or parsed_project
                        repo = repo or parsed_repo
                else:
                    # Auto-detect: skip forks, pick first non-fork remote
                    for remote_name in remotes:
                        try:
                            remote_url = subprocess.check_output(
                                ["git", "remote", "get-url", remote_name],
                                cwd=state["repo_path"],
                                stderr=subprocess.DEVNULL,
                                timeout=5,
                            ).decode().strip()
                        except Exception:
                            continue
                        if not remote_url or _is_fork_url(remote_url):
                            continue  # skip forks — we want the main repo
                        parsed_project, parsed_repo = _parse_repo_url(remote_url)
                        if parsed_project and parsed_repo:
                            project = project or parsed_project
                            repo = repo or parsed_repo
                            break
            except Exception:
                pass  # git not available or not a git repo — fall through

        target_branch = (
            str(node_data.get("targetBranch") or "").strip()
            or state.get("pr_target_branch")
            or "main"
        )
        # from_branch: prefer the branch Patch actually created, then node config, then default
        patch_branch = (state.get("patch") or {}).get("branch")
        from_branch = (
            patch_branch
            or str(node_data.get("fromBranch") or "").strip()
            or f"fix/{issue_key.lower()}"
        )

        # ── Commit + push the fix branch before creating the PR ──
        repo_path = state.get("repo_path")
        patch_result = state.get("patch") or {}
        push_remote = str(node_data.get("pushRemote") or "origin").strip()
        if repo_path and patch_result.get("status") == "applied":
            try:
                await self._commit_and_push(
                    repo_path=repo_path,
                    branch=from_branch,
                    issue_key=issue_key,
                    summary=jira_detail.get("summary") or "",
                    push_remote=push_remote,
                )
            except Exception as e:
                state["open_pr_error"] = f"Commit/push failed: {e}"
                done_payload["error"] = state["open_pr_error"]
                return

        try:
            result = await open_pr(
                issue_key=issue_key,
                summary=jira_detail.get("summary") or "",
                project=project,
                repo=repo,
                from_branch=from_branch,
                to_branch=target_branch,
                analysis=state.get("analysis"),
                from_project=state.get("pr_fork_project"),
                from_repo=state.get("pr_fork_repo"),
            )
        except PrConfigError as e:
            state["open_pr_error"] = str(e)
            done_payload["error"] = state["open_pr_error"]
            return
        except Exception as e:
            state["open_pr_error"] = f"Open PR failed: {e}"
            done_payload["error"] = state["open_pr_error"]
            return
        state["open_pr"] = result
        done_payload.update({"branch": result.get("branch")})

        # ── PR Feedback: post template + link experience to PR ──
        pr_id = result.get("id")
        pr_url = result.get("url", "")
        if pr_id and project and repo:
            try:
                from app.backend.domains.bug_fix.pr_feedback_sync import (
                    post_feedback_template,
                )
                from app.backend.domains.bug_fix.experience_store import ExperienceStore

                # Find the experience we just stored for this run
                store = ExperienceStore()
                exp_id = done_payload.get("experience_id")
                if exp_id:
                    # Link experience to PR
                    store.update_pr_info(
                        exp_id=exp_id,
                        pr_url=pr_url,
                        pr_id=int(pr_id),
                        pr_project=project,
                        pr_repo=repo,
                    )
                    # Post feedback template comment on the PR
                    await post_feedback_template(
                        project=project,
                        repo=repo,
                        pr_id=int(pr_id),
                        experience_id=exp_id,
                    )
                    done_payload["pr_feedback_template_posted"] = True
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(
                    f"Failed to post PR feedback template (non-fatal): {e}"
                )

    async def _commit_and_push(
        self,
        *,
        repo_path: str,
        branch: str,
        issue_key: str,
        summary: str,
        push_remote: str = "origin",
    ) -> None:
        """Stage all changes, commit, and push the fix branch.

        push_remote defaults to "origin" but can be overridden by the
        Open PR node's configuration.
        """
        import os
        from pathlib import Path

        repo = Path(repo_path).expanduser()
        commit_msg = f"{issue_key}: {summary}".strip() or issue_key

        async def _git(*args: str) -> tuple[int, str, str]:
            proc = await asyncio.create_subprocess_exec(
                "git", *args,
                cwd=str(repo),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=60)
            return (
                proc.returncode or 0,
                out_b.decode(errors="replace"),
                err_b.decode(errors="replace"),
            )

        # Stage all changes
        rc, _, err = await _git("add", "-A")
        if rc != 0:
            raise RuntimeError(f"git add failed: {err.strip()}")

        # Check if there's anything to commit
        rc, stdout, _ = await _git("status", "--porcelain")
        if not stdout.strip():
            # Nothing to commit — branch may already have commits
            pass
        else:
            rc, _, err = await _git("commit", "-m", commit_msg)
            if rc != 0:
                raise RuntimeError(f"git commit failed: {err.strip()}")

        # Auto-detect push remote: prefer the fork (URL with ~username).
        # If the configured remote doesn't exist, scan all remotes for a fork.
        rc, remotes_out, _ = await _git("remote")
        if rc == 0:
            remotes = [r.strip() for r in remotes_out.strip().splitlines() if r.strip()]
            if push_remote not in remotes:
                # Try to find a fork remote (URL contains ~)
                fork_remote = None
                for r in remotes:
                    rc2, url_out, _ = await _git("remote", "get-url", r)
                    if rc2 == 0 and _is_fork_url(url_out):
                        fork_remote = r
                        break
                if fork_remote:
                    push_remote = fork_remote
                elif "origin" in remotes:
                    push_remote = "origin"
                elif remotes:
                    push_remote = remotes[0]

        # Push the branch to the configured push remote
        rc, _, err = await _git("push", "-u", push_remote, branch)
        if rc != 0:
            # Try force push if the branch already exists remotely
            rc, _, err = await _git("push", "-u", push_remote, branch, "--force-with-lease")
            if rc != 0:
                raise RuntimeError(f"git push to {push_remote} failed: {err.strip()}")

    def _build_result(
        self,
        issue_key: str,
        state: dict[str, Any],
        stages_executed: list[dict[str, str]],
    ) -> dict[str, Any]:
        branch = (state.get("open_pr") or {}).get("branch") or f"fix/{issue_key.lower()}"
        result: dict[str, Any] = {
            "jira_issue": issue_key,
            "branch": branch,
            "stages_executed": stages_executed,
        }
        jira_detail = state.get("jira_detail")
        if jira_detail:
            result["jira"] = jira_detail
            result["summary"] = jira_detail.get("summary") or f"Stub fix applied for {issue_key}"
        else:
            result["summary"] = f"Stub fix applied for {issue_key}"
        for key in ("analysis", "patch", "open_pr"):
            if key in state:
                result[key] = state[key]
        for key in ("analyze_error", "patch_error", "open_pr_error"):
            if state.get(key):
                result[key] = state[key]

        # Aggregate token usage from all stages
        token_usage_list: list[dict[str, Any]] = []
        # Analyze stage token usage
        analysis = state.get("analysis")
        if isinstance(analysis, dict) and analysis.get("token_usage"):
            token_usage_list.append(analysis["token_usage"])
        # Patch stage token usage (from Claude CLI)
        patch = state.get("patch")
        if isinstance(patch, dict) and patch.get("token_usage"):
            token_usage_list.append(patch["token_usage"])
        # Open PR stage token usage
        open_pr_data = state.get("open_pr")
        if isinstance(open_pr_data, dict) and open_pr_data.get("token_usage"):
            token_usage_list.append(open_pr_data["token_usage"])

        if token_usage_list:
            result["token_usage"] = aggregate_token_usage(token_usage_list)
            
            # Check token usage anomalies
            if hasattr(self, '_anomaly_detector'):
                self._anomaly_detector.check_token_usage(result["token_usage"])

        # Check confidence anomalies from analysis
        analysis = state.get("analysis")
        if isinstance(analysis, dict) and hasattr(self, '_anomaly_detector'):
            # Check overall confidence
            confidence = analysis.get("confidence")
            if confidence is not None:
                self._anomaly_detector.check_confidence("analyze", "Analyze", confidence)
            
            # Check individual decision steps
            for step in analysis.get("decision_steps", []):
                step_confidence = step.get("confidence")
                if step_confidence is not None:
                    self._anomaly_detector.check_confidence(
                        "analyze", 
                        f"Analyze: {step.get('step', 'unknown')}",
                        step_confidence
                    )

        # Check error patterns
        if hasattr(self, '_anomaly_detector'):
            self._anomaly_detector.check_error_pattern(result)
            anomaly_summary = self._anomaly_detector.get_summary()
            if anomaly_summary["anomaly_count"] > 0:
                result["anomalies"] = anomaly_summary

        return result
