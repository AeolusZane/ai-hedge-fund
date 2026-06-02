"""Patch stage — drives Claude Code to edit a target repo.

Spawns the `claude` CLI as a subprocess in the repo working directory,
hands it the Jira context (and the Analyze hypothesis, when present),
then captures the resulting `git diff` and the list of touched files.
No commit / push happens here — that's Open PR's job.
"""
from __future__ import annotations

import asyncio
import os
import re
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


def _strip_image_refs(text: str) -> str:
    """Remove Jira image attachment references from text."""
    # Strip !filename.ext! and !filename.ext|width=...,height=...!
    text = re.sub(r'![^!]+\.(png|jpg|jpeg|gif|bmp|svg|webp)(\|[^!]*)?!', '', text, flags=re.IGNORECASE)
    # Strip Jira attachment macros: [^filename.ext]
    text = re.sub(r'\[\^[^\]]+\]', '', text)
    return text.strip()


def _has_actionable_text(text: str) -> bool:
    """Check if text contains at least 4 chars of real content after stripping image refs."""
    return len(_strip_image_refs(text)) >= 4


def _extract_comments(jira: dict[str, Any]) -> list[dict[str, str]]:
    """Extract comments from Jira detail (handles both raw and flattened formats)."""
    # Raw Jira API: fields.comment.comments[]
    comments_raw = (
        jira.get("comment", {}).get("comments", [])
        if isinstance(jira.get("comment"), dict)
        else []
    )
    # Flattened format: jira["comments"] = [...]
    if not comments_raw and isinstance(jira.get("comments"), list):
        comments_raw = jira["comments"]

    result = []
    for c in comments_raw:
        if not isinstance(c, dict):
            continue
        author = ""
        if isinstance(c.get("author"), dict):
            author = c["author"].get("displayName", "")
        elif isinstance(c.get("author"), str):
            author = c["author"]
        body = c.get("body", "") or ""
        created = c.get("created", "")
        if body.strip():
            result.append({"author": author, "body": body.strip(), "created": created})
    return result


def _extract_attachments(jira: dict[str, Any]) -> list[str]:
    """Extract attachment filenames from Jira detail."""
    attachments_raw = jira.get("attachment", [])
    if not isinstance(attachments_raw, list):
        return []
    names = []
    for a in attachments_raw:
        if isinstance(a, dict) and a.get("filename"):
            names.append(a["filename"])
        elif isinstance(a, str):
            names.append(a)
    return names


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

    # Comments — often contain reproduction steps, fix instructions, or clarifications
    comments = _extract_comments(jira)
    if comments:
        parts.append("Jira comments (most recent last, may contain fix instructions):")
        # Take last 10 comments, cap each at 500 chars
        for c in comments[-10:]:
            author = c["author"] or "unknown"
            body = _strip_image_refs(c["body"])[:500]
            if body:
                parts.append(f"  [{author}]: {body}")
        parts.append("")

    # Attachments — let the model know what images exist even if it can't read them
    attachments = _extract_attachments(jira)
    if attachments:
        parts.append(f"Attachments (images you cannot view): {', '.join(attachments)}")
        parts.append("")

    # Labels and components — help the model locate the right module
    labels = jira.get("labels") or []
    components = []
    for c in (jira.get("components") or []):
        if isinstance(c, dict):
            components.append(c.get("name", ""))
        elif isinstance(c, str):
            components.append(c)
    if labels:
        parts.append(f"Labels: {', '.join(labels)}")
    if components:
        parts.append(f"Components: {', '.join(components)}")
    if labels or components:
        parts.append("")

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
    target_branch: str = "main",
    timeout_seconds: float = 600.0,
) -> dict[str, Any]:
    """Drive Claude Code to fix the bug; return diff + touched files.

    Creates a ``fix/<issue-key>`` branch from *target_branch* before
    invoking Claude Code, so the working tree is clean and the diff is
    scoped to the fix.
    """
    repo = _validate_repo(repo_path)
    claude = _claude_binary()
    issue_key = (jira_detail.get("key") or "bug").strip()
    fix_branch = f"fix/{issue_key.lower()}"

    # ── Branch setup ──────────────────────────────────────────────
    # Fetch latest so we branch from an up-to-date base.
    await _run("git", "fetch", "origin", cwd=repo, timeout=60)

    # Stash or discard any local changes before switching branches.
    await _run("git", "stash", "--include-untracked", cwd=repo, timeout=30)

    # Delete the fix branch if it already exists locally (start fresh).
    await _run("git", "branch", "-D", fix_branch, cwd=repo, timeout=10)

    # Create the fix branch from the target branch.
    rc, _, err = await _run(
        "git", "checkout", "-b", fix_branch, f"origin/{target_branch}",
        cwd=repo, timeout=30,
    )
    if rc != 0:
        # Fallback: try local target branch if origin/ doesn't exist.
        rc, _, err = await _run(
            "git", "checkout", "-b", fix_branch, target_branch,
            cwd=repo, timeout=30,
        )
        if rc != 0:
            raise PatchConfigError(
                f"Failed to create branch '{fix_branch}' from '{target_branch}': {err.strip()}"
            )

    # Pre-flight: check if the Jira issue has ANY actionable text across
    # description + comments. If everything is image-only, skip the CLI call.
    raw_description = jira_detail.get("description") or ""
    comments = _extract_comments(jira_detail)
    has_text_in_description = _has_actionable_text(raw_description)
    has_text_in_comments = any(_has_actionable_text(c["body"]) for c in comments)
    if not has_text_in_description and not has_text_in_comments and not analysis:
        return {
            "status": "blocked",
            "branch": fix_branch,
            "claude_output": "",
            "files_changed": [],
            "diff": "",
            "diff_truncated": False,
            "blocker_reason": (
                "Jira issue contains only image attachments with no actionable text "
                "in description or comments. Claude Code cannot read Jira image attachments."
            ),
            "blocker_next_step": (
                "Add a text description or comment to the Jira issue explaining the bug, "
                "or ensure the Analyze stage produces a hypothesis with target files."
            ),
        }

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
        # If the model hit max-turns, treat as blocked rather than error.
        # The model may have been exploring without converging.
        if "max turns" in stderr.lower() or "max turns" in stdout.lower():
            output_text = stdout.strip()[:8000]
            return {
                "status": "blocked",
                "branch": fix_branch,
                "claude_output": output_text,
                "files_changed": [],
                "diff": "",
                "diff_truncated": False,
                "blocker_reason": "Model exhausted exploration budget without converging on a fix",
                "blocker_next_step": "Provide a more detailed bug description or narrow the target files in the Analyze stage",
            }
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
        "branch": fix_branch,
        "claude_output": output_text,
        "files_changed": files_changed,
        "diff": diff_payload,
        "diff_truncated": diff_truncated,
        "blocker_reason": blocker_reason,
        "blocker_next_step": blocker_next_step,
    }
