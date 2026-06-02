"""Patch stage — drives Claude Code to edit a target repo.

Spawns the `claude` CLI as a subprocess in the repo working directory,
hands it the Jira context (and the Analyze hypothesis, when present),
then captures the resulting `git diff` and the list of touched files.
No commit / push happens here — that's Open PR's job.
"""
from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path
from typing import Any


class PatchConfigError(RuntimeError):
    """Raised when the patch agent isn't configured (missing repo, claude, …)."""


def _claude_binary() -> str:
    path = shutil.which(os.getenv("CLAUDE_CLI", "claude"))
    if not path:
        raise PatchConfigError(
            "claude CLI not found on PATH; set CLAUDE_CLI or install Claude Code"
        )
    return path


def _validate_repo(repo_path: str) -> Path:
    if not repo_path:
        raise PatchConfigError("repo_path is empty (add a Repo Path Input node)")
    p = Path(repo_path).expanduser()
    if not p.is_dir():
        raise PatchConfigError(f"repo_path {p} is not a directory")
    if not (p / ".git").exists():
        raise PatchConfigError(f"repo_path {p} is not a git repository")
    return p


async def _run(
    *args: str, cwd: Path, timeout: float
) -> tuple[int, str, str]:
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
        raise PatchConfigError(f"Command {args[0]} timed out after {timeout:.0f}s")
    return proc.returncode or 0, out_b.decode(errors="replace"), err_b.decode(errors="replace")


def _build_prompt(jira: dict[str, Any], analysis: dict[str, Any] | None) -> str:
    summary = jira.get("summary") or "(no summary)"
    description = (jira.get("description") or "(no description)")[:4000]
    key = jira.get("key") or ""

    parts = [
        f"You are fixing Jira bug {key}: {summary}.",
        "",
        "Jira description:",
        description,
        "",
    ]
    if analysis:
        parts.extend(
            [
                "An earlier analyze pass produced this hypothesis (treat as a hint, verify before acting):",
                f"- Root cause: {analysis.get('root_cause_hypothesis','(unknown)')}",
                f"- Affected areas: {', '.join(analysis.get('affected_areas') or []) or '(unknown)'}",
                "- Suggested approach:",
            ]
        )
        for step in analysis.get("suggested_approach") or []:
            parts.append(f"  * {step}")
        parts.append("")

    parts.extend(
        [
            "Make the smallest code change that fixes the bug. Edit files in this repo as needed.",
            "Do NOT commit, push, or run git commands — another stage handles that.",
            "Do NOT ask the user any questions and do NOT wait for confirmation.",
            "If details are missing, make the safest minimal fix based on the available evidence.",
            "If you cannot safely make a code change, do not stop to ask questions.",
            "Instead, make no code changes and end with a short blocker report.",
            "",
            "At the end, output exactly one of these formats:",
            "",
            "1) If you changed code:",
            "PATCH_APPLIED",
            "summary: <what changed and why>",
            "files: <comma-separated files>",
            "",
            "2) If you could not safely change code:",
            "PATCH_BLOCKED",
            "reason: <why blocked>",
            "next_step: <specific next investigation step>",
        ]
    )
    return "\n".join(parts)


async def run_patch(
    repo_path: str,
    jira_detail: dict[str, Any],
    analysis: dict[str, Any] | None,
    *,
    timeout_seconds: float = 600.0,
) -> dict[str, Any]:
    """Drive Claude Code to fix the bug; return diff + touched files."""
    repo = _validate_repo(repo_path)
    claude = _claude_binary()
    prompt = _build_prompt(jira_detail, analysis)

    rc, stdout, stderr = await _run(
        claude,
        "--print",
        "--max-turns",
        "8",
        "--permission-mode",
        "acceptEdits",
        prompt,
        cwd=repo,
        timeout=timeout_seconds,
    )
    if rc != 0:
        # Surface stderr first since that's where claude reports auth /
        # rate-limit errors.
        message = (stderr.strip() or stdout.strip() or "(no output)")[:2000]
        raise PatchConfigError(f"claude exited {rc}: {message}")

    # Parse the structured exit protocol from the prompt.
    output_text = stdout.strip()[:8000]
    status = "applied"
    blocker_reason = ""
    blocker_next_step = ""
    if "PATCH_BLOCKED" in output_text:
        status = "blocked"
        for line in output_text.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("reason:"):
                blocker_reason = stripped.split(":", 1)[1].strip()
            elif stripped.lower().startswith("next_step:"):
                blocker_next_step = stripped.split(":", 1)[1].strip()

    # Capture what changed. `git status --porcelain=v1` lists every file
    # whose state moved; `git diff` (working tree vs HEAD) gives the
    # actual patch for review.
    _, status_out, _ = await _run("git", "status", "--porcelain=v1", cwd=repo, timeout=30)
    files_changed = [line[3:].strip() for line in status_out.splitlines() if line.strip()]

    _, diff_out, _ = await _run("git", "diff", "HEAD", cwd=repo, timeout=60)

    # Cap the diff so we don't bloat the FlowRun.results blob in SQLite.
    DIFF_LIMIT = 50_000
    diff_truncated = len(diff_out) > DIFF_LIMIT
    diff_payload = diff_out[:DIFF_LIMIT] if diff_truncated else diff_out

    return {
        "status": status,
        "claude_output": output_text,
        "files_changed": files_changed,
        "diff": diff_payload,
        "diff_truncated": diff_truncated,
        "blocker_reason": blocker_reason,
        "blocker_next_step": blocker_next_step,
    }
