"""Direct Bitbucket REST API client — no MCP server required.

Uses httpx to call the Bitbucket Server REST API directly.
Credentials are pulled from environment variables:
  BITBUCKET_BASE_URL, BITBUCKET_TOKEN, BITBUCKET_USERNAME (optional).

Today we expose just the one function the bug_fix executor needs:
creating a pull request. Add more as later phases need them.
"""
from __future__ import annotations

import os
from typing import Any

import httpx


class BitbucketMcpConfigError(RuntimeError):
    """Raised when the Bitbucket integration is not configured."""


class BitbucketMcpToolError(RuntimeError):
    """Raised when the Bitbucket API returns an error."""


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise BitbucketMcpConfigError(
            f"Environment variable {name} is required for the Bitbucket integration"
        )
    return value


def _get_bitbucket_config() -> tuple[str, str, str]:
    """Return (base_url, token, username) from environment."""
    base_url = _required_env("BITBUCKET_BASE_URL").rstrip("/")
    token = _required_env("BITBUCKET_TOKEN")
    username = os.environ.get("BITBUCKET_USERNAME", "")
    return base_url, token, username


async def get_repo_info(
    *,
    project: str,
    repo: str,
) -> dict[str, Any]:
    """Get repository info from Bitbucket Server REST API.

    Returns the full repo object including 'origin' field for forks,
    which points to the parent repository.

    Args:
        project: Bitbucket project key (e.g. "~aeolus.zhang")
        repo: Repository slug (e.g. "nuclear-webui")

    Returns:
        Dict with repo details including origin (if fork)

    Raises:
        BitbucketMcpConfigError: When env vars are missing
        BitbucketMcpToolError: When the API returns an error
    """
    base_url, token, _ = _get_bitbucket_config()

    url = f"{base_url}/rest/api/1.0/projects/{project}/repos/{repo}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(url, headers=headers)
        except httpx.RequestError as e:
            raise BitbucketMcpToolError(f"Bitbucket API request failed: {e}") from e

        if response.status_code == 401:
            raise BitbucketMcpToolError("Bitbucket API authentication failed (401)")
        if response.status_code == 404:
            return {}  # Repo not found, return empty
        if response.status_code not in (200, 201):
            raise BitbucketMcpToolError(
                f"Bitbucket API error {response.status_code}: {response.text[:500]}"
            )

        try:
            return response.json()
        except Exception as e:
            raise BitbucketMcpToolError(f"Failed to parse Bitbucket response: {e}") from e


async def create_pr(
    *,
    project: str,
    repo: str,
    title: str,
    from_branch: str,
    to_branch: str,
    description: str = "",
    reviewers: list[str] | None = None,
    from_project: str | None = None,
    from_repo: str | None = None,
) -> dict[str, Any]:
    """Create a pull request via the Bitbucket Server REST API.

    Args:
        project: Bitbucket project key for target repo (e.g. "AI")
        repo: Repository slug for target repo (e.g. "corevo")
        title: PR title
        from_branch: Source branch
        to_branch: Target branch
        description: PR description (markdown)
        reviewers: Optional list of reviewer usernames
        from_project: Optional project key for source repo (for cross-repo PRs from forks)
        from_repo: Optional repo slug for source repo (for cross-repo PRs from forks)

    Returns:
        Dict with PR details including id, url, etc.

    Raises:
        BitbucketMcpConfigError: When env vars are missing
        BitbucketMcpToolError: When the API returns an error
    """
    base_url, token, username = _get_bitbucket_config()

    # Bitbucket Server REST API endpoint
    url = f"{base_url}/rest/api/1.0/projects/{project}/repos/{repo}/pull-requests"

    # For cross-repo PRs (from fork), use from_project/from_repo for fromRef
    # Otherwise use the same project/repo for both
    src_project = from_project or project
    src_repo = from_repo or repo

    # Build the request body
    body: dict[str, Any] = {
        "title": title,
        "description": description,
        "fromRef": {
            "id": f"refs/heads/{from_branch}",
            "repository": {
                "slug": src_repo,
                "project": {"key": src_project},
            },
        },
        "toRef": {
            "id": f"refs/heads/{to_branch}",
            "repository": {
                "slug": repo,
                "project": {"key": project},
            },
        },
    }

    # Add reviewers if provided
    if reviewers:
        body["reviewers"] = [{"user": {"name": r}} for r in reviewers]

    # Auth: Bearer token in Authorization header
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(url, json=body, headers=headers)
        except httpx.RequestError as e:
            raise BitbucketMcpToolError(f"Bitbucket API request failed: {e}") from e

        if response.status_code == 401:
            raise BitbucketMcpToolError("Bitbucket API authentication failed (401)")
        if response.status_code == 409:
            # PR already exists or conflict
            error_msg = response.text[:500]
            raise BitbucketMcpToolError(f"Bitbucket conflict (409): {error_msg}")
        if response.status_code not in (200, 201):
            raise BitbucketMcpToolError(
                f"Bitbucket API error {response.status_code}: {response.text[:500]}"
            )

        try:
            data = response.json()
        except Exception as e:
            raise BitbucketMcpToolError(f"Failed to parse Bitbucket response: {e}") from e

    # Flatten the response for easier consumption
    pr_id = data.get("id", "")
    pr_url = ""
    links = data.get("links", {})
    if "self" in links and links["self"]:
        pr_url = links["self"][0].get("href", "")

    return {
        "id": pr_id,
        "url": pr_url,
        "title": data.get("title", title),
        "state": data.get("state", ""),
        "from_branch": from_branch,
        "to_branch": to_branch,
        "raw": data,
    }
