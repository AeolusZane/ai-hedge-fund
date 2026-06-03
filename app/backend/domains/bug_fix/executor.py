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
from app.backend.core.workspace import clone_repo, ensure_workspace
from app.backend.domains.bug_fix.analyze_agent import AnalyzeConfigError, analyze_jira_issue
from app.backend.domains.bug_fix.jira_client import (
    JiraMcpConfigError,
    JiraMcpToolError,
    get_issue_detail,
)
from app.backend.domains.bug_fix.patch_agent import PatchConfigError, run_patch
from app.backend.domains.bug_fix.pr_agent import PrConfigError, open_pr


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
}


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

        # Get run_id from context for workspace isolation
        run_id = context.run_id if hasattr(context, "run_id") else None

        state: dict[str, Any] = {
            "issue_key": issue_key,
            "api_keys": context.api_keys,
            "run_id": run_id,
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
            await self._do_analyze(node_id, node_data, state, done_payload, context)
        elif stage_name == "Patch":
            await self._do_patch(node_data, state, done_payload)
        elif stage_name == "Open PR":
            await self._do_open_pr(node_data, state, done_payload)
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

        try:
            analysis = await analyze_jira_issue(
                jira_detail,
                model_name=node_data.get("modelName"),
                model_provider=node_data.get("modelProvider"),
                api_keys=state.get("api_keys"),
                on_token=on_token,
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
        return result
