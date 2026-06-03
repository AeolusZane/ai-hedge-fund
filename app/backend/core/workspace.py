"""Workspace Manager — isolated working directories for pipeline runs.

Each pipeline run gets its own directory under WORKSPACE_ROOT/{run_id}/.
Default root: <tmp>/ai-workflow-studio/workspace (override via WORKSPACE_ROOT env var).
Repos are cloned here, patches applied, tests run — all isolated from
the host filesystem and other runs.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

# Base directory for workspaces.
# Default: <system-tmp>/ai-workflow-studio/workspace (e.g. /tmp/... on macOS/Linux).
# Override with WORKSPACE_ROOT env var for Docker / production deployments.
_default_root = Path(tempfile.gettempdir()) / "ai-workflow-studio" / "workspace"
WORKSPACE_ROOT = Path(os.environ.get("WORKSPACE_ROOT", str(_default_root)))


def get_workspace_path(run_id: int) -> Path:
    """Get the workspace directory for a specific run."""
    return WORKSPACE_ROOT / str(run_id)


def ensure_workspace(run_id: int) -> Path:
    """Create workspace directory if it doesn't exist, return path."""
    workspace = get_workspace_path(run_id)
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def cleanup_workspace(run_id: int) -> bool:
    """Remove a workspace directory. Returns True if removed."""
    workspace = get_workspace_path(run_id)
    if workspace.exists():
        shutil.rmtree(workspace, ignore_errors=True)
        return True
    return False


def workspace_exists(run_id: int) -> bool:
    """Check if a workspace exists."""
    return get_workspace_path(run_id).exists()


async def clone_repo(
    run_id: int,
    repo_url: str,
    branch: str = "main",
    repo_name: str = "repo",
) -> Path:
    """Clone a git repo into the workspace.

    Args:
        run_id: Pipeline run ID
        repo_url: Git remote URL (HTTPS or SSH)
        branch: Branch to checkout
        repo_name: Local directory name for the repo

    Returns:
        Path to the cloned repo

    Raises:
        RuntimeError: If clone fails
    """
    workspace = ensure_workspace(run_id)
    repo_path = workspace / repo_name

    # If repo already exists, just fetch and reset
    if repo_path.exists() and (repo_path / ".git").exists():
        proc = await asyncio.create_subprocess_exec(
            "git", "fetch", "origin",
            cwd=str(repo_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        proc = await asyncio.create_subprocess_exec(
            "git", "reset", "--hard", f"origin/{branch}",
            cwd=str(repo_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        return repo_path

    # Fresh clone
    proc = await asyncio.create_subprocess_exec(
        "git", "clone", "--branch", branch, "--single-branch",
        repo_url, str(repo_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)

    if proc.returncode != 0:
        raise RuntimeError(f"git clone failed: {stderr.decode(errors='replace')}")

    return repo_path


def list_files(
    run_id: int,
    path: str = "/",
    max_depth: int = 3,
) -> dict[str, Any]:
    """List files and directories in the workspace.

    Args:
        run_id: Pipeline run ID
        path: Relative path within workspace (e.g., "/" or "/repo/src")
        max_depth: Maximum directory depth to traverse

    Returns:
        Dict with 'path' and 'entries' list
    """
    workspace = get_workspace_path(run_id)
    if not workspace.exists():
        return {"path": path, "entries": [], "error": "workspace not found"}

    # Resolve the target path
    if path.startswith("/"):
        target = workspace / path.lstrip("/")
    else:
        target = workspace / path

    # Security: ensure we're still within workspace
    try:
        target = target.resolve()
        workspace_resolved = workspace.resolve()
        if not str(target).startswith(str(workspace_resolved)):
            return {"path": path, "entries": [], "error": "path outside workspace"}
    except Exception:
        return {"path": path, "entries": [], "error": "invalid path"}

    if not target.exists():
        return {"path": path, "entries": [], "error": "path not found"}

    entries = []

    def _scan(dir_path: Path, depth: int, prefix: str) -> None:
        if depth > max_depth:
            return
        try:
            items = sorted(dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            return

        for item in items:
            # Skip .git directory
            if item.name == ".git":
                continue

            rel_path = f"{prefix}/{item.name}" if prefix else f"/{item.name}"

            if item.is_dir():
                entries.append({
                    "name": item.name,
                    "path": rel_path,
                    "type": "dir",
                    "size": None,
                })
                _scan(item, depth + 1, rel_path)
            else:
                try:
                    size = item.stat().st_size
                except OSError:
                    size = None
                entries.append({
                    "name": item.name,
                    "path": rel_path,
                    "type": "file",
                    "size": size,
                })

    _scan(target, 0, path.rstrip("/") if path != "/" else "")

    return {"path": path, "entries": entries}


def read_file(run_id: int, path: str, max_size: int = 1_000_000) -> dict[str, Any]:
    """Read a file from the workspace.

    Args:
        run_id: Pipeline run ID
        path: Relative path within workspace
        max_size: Maximum file size to read (bytes)

    Returns:
        Dict with 'path', 'content', and metadata
    """
    workspace = get_workspace_path(run_id)
    if not workspace.exists():
        return {"path": path, "error": "workspace not found"}

    # Resolve the target path
    if path.startswith("/"):
        target = workspace / path.lstrip("/")
    else:
        target = workspace / path

    # Security check
    try:
        target = target.resolve()
        workspace_resolved = workspace.resolve()
        if not str(target).startswith(str(workspace_resolved)):
            return {"path": path, "error": "path outside workspace"}
    except Exception:
        return {"path": path, "error": "invalid path"}

    if not target.exists():
        return {"path": path, "error": "file not found"}

    if not target.is_file():
        return {"path": path, "error": "not a file"}

    try:
        size = target.stat().st_size
    except OSError:
        size = None

    if size and size > max_size:
        return {
            "path": path,
            "error": f"file too large ({size} bytes, max {max_size})",
            "size": size,
        }

    try:
        content = target.read_text(encoding="utf-8", errors="replace")
        return {
            "path": path,
            "content": content,
            "size": size,
            "encoding": "utf-8",
        }
    except Exception as e:
        return {"path": path, "error": f"read failed: {e}"}
