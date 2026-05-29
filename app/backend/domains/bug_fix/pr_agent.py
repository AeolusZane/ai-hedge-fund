"""Open PR stage — pushes the fix branch and opens a Bitbucket PR.

Sequence in the target repo:
  1. git checkout -B fix/<issue-key>
  2. git add -A && git commit -m "<key>: <summary>"
  3. git push -u origin fix/<issue-key>
  4. bitbucket_create_pr (project/repo/title/from/to)

A "nothing to commit" state (no diff produced by Patch) skips git work
and goes straight to PR creation against whatever the current branch
already is.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from app.backend.domains.bug_fix.bitbucket_client import (
    BitbucketMcpConfigError,
    BitbucketMcpToolError,
    create_pr,
)


class PrConfigError(RuntimeError):
    pass


async def _run(*args: str, cwd: Path, timeout: float = 60.0) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise PrConfigError(f"git {args[1] if len(args) > 1 else args[0]} timed out")
    return proc.returncode or 0, out_b.decode(errors="replace"), err_b.decode(errors="replace")


async def _commit_and_push(
    repo: Path, branch: str, commit_message: str
) -> dict[str, Any]:
    rc, _, err = await _run("git", "checkout", "-B", branch, cwd=repo)
    if rc != 0:
        raise PrConfigError(f"git checkout failed: {err.strip()}")

    # Stage everything Patch touched.
    await _run("git", "add", "-A", cwd=repo)

    # `git commit` exits non-zero when there is nothing to commit; treat
    # that as a no-op and continue to push (the branch may already hold
    # the diff from a previous run).
    rc, out, err = await _run(
        "git", "commit", "-m", commit_message, cwd=repo
    )
    committed = rc == 0
    if not committed and "nothing to commit" not in (out + err).lower():
        raise PrConfigError(f"git commit failed: {err.strip() or out.strip()}")

    rc, _, err = await _run(
        "git", "push", "--set-upstream", "origin", branch, cwd=repo, timeout=120.0
    )
    if rc != 0:
        raise PrConfigError(f"git push failed: {err.strip()}")

    return {"committed": committed, "branch": branch}


async def open_pr(
    *,
    repo_path: str,
    issue_key: str,
    summary: str,
    target_branch: str,
    project: str,
    repo: str,
    analysis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not repo_path:
        raise PrConfigError("repo_path is empty (Repo Path Input node required)")
    if not project or not repo:
        raise PrConfigError(
            "project and repo are required (set them on the PR Config node)"
        )
    repo_dir = Path(repo_path).expanduser()
    if not (repo_dir / ".git").exists():
        raise PrConfigError(f"{repo_dir} is not a git repository")

    branch = f"fix/{issue_key.lower()}"
    commit_message = f"{issue_key}: {summary}".strip() or issue_key
    git_result = await _commit_and_push(repo_dir, branch, commit_message)

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
            from_branch=branch,
            to_branch=target_branch or "main",
            description="\n".join(description_lines),
        )
    except BitbucketMcpConfigError as e:
        raise PrConfigError(f"Bitbucket MCP not configured: {e}")
    except BitbucketMcpToolError as e:
        raise PrConfigError(str(e))

    return {
        "branch": branch,
        "committed": git_result["committed"],
        "pr": pr_payload,
    }
