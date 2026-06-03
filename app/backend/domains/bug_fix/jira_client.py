"""Direct Jira REST API client — no MCP server required.

Uses httpx to call the Jira REST API directly. Credentials are pulled
from environment variables: JIRA_BASE_URL, JIRA_USERNAME, JIRA_TOKEN.

Today we expose just the one function the bug_fix executor needs:
fetching issue details. Add more as later phases need them.
"""
from __future__ import annotations

import os
from typing import Any

import httpx


class JiraMcpConfigError(RuntimeError):
    """Raised when the Jira integration is not configured."""


class JiraMcpToolError(RuntimeError):
    """Raised when the Jira API returns an error."""


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise JiraMcpConfigError(
            f"Environment variable {name} is required for the Jira integration"
        )
    return value


def _get_jira_config() -> tuple[str, str, str]:
    """Return (base_url, username, token) from environment."""
    base_url = _required_env("JIRA_BASE_URL").rstrip("/")
    username = _required_env("JIRA_USERNAME")
    token = _required_env("JIRA_TOKEN")
    return base_url, username, token


async def search_bugs(
    project_key: str = "",
    status: str = "",
    issue_type: str = "",
    assignee_current_user: bool = True,
    max_results: int = 20,
) -> list[dict[str, Any]]:
    """Search Jira for bug issues matching the criteria.

    Uses JQL (Jira Query Language) to find bugs in the specified project.

    Args:
        project_key: Jira project key (e.g. "BI", "REPORT"). Empty = all projects.
        status: Issue status to filter. Empty = exclude closed statuses.
        issue_type: Issue type. Empty = all bug types.
        assignee_current_user: If True, filter by current user as assignee.
        max_results: Maximum number of results to return

    Returns:
        List of issue dicts with key, summary, status, priority, assignee, etc.
        Empty list if no bugs found or API error.
    """
    base_url, username, token = _get_jira_config()

    # Default bug types for Chinese Jira instances
    default_bug_types = '"客户BUG","一般BUG","内测BUG","缺陷","BUG"'
    # Default closed statuses for Chinese Jira instances
    default_closed_statuses = '"已解决","终止","被否决","结束","完成","关闭","终止开发"'

    # Build JQL query
    jql_parts = []

    if project_key:
        jql_parts.append(f'project = "{project_key}"')

    if issue_type:
        jql_parts.append(f'issuetype = "{issue_type}"')
    else:
        jql_parts.append(f'issuetype in ({default_bug_types})')

    if status:
        jql_parts.append(f'status = "{status}"')
    else:
        jql_parts.append(f'status not in ({default_closed_statuses})')

    if assignee_current_user:
        jql_parts.append('assignee = currentUser()')

    jql = " AND ".join(jql_parts) + " ORDER BY updated DESC"

    url = f"{base_url}/rest/api/2/search"
    params = {
        "jql": jql,
        "maxResults": max_results,
        "fields": "summary,status,priority,assignee,reporter,created,updated,description",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(
                url,
                params=params,
                auth=(username, token),
                headers={"Accept": "application/json"},
            )
        except httpx.RequestError as e:
            raise JiraMcpToolError(f"Jira API request failed: {e}") from e

        if response.status_code == 401:
            raise JiraMcpToolError("Jira API authentication failed (401)")
        if response.status_code != 200:
            raise JiraMcpToolError(
                f"Jira API error {response.status_code}: {response.text[:500]}"
            )

        try:
            data = response.json()
        except Exception as e:
            raise JiraMcpToolError(f"Failed to parse Jira response: {e}") from e

    # Flatten the response
    issues = data.get("issues", [])
    results = []
    for issue in issues:
        fields = issue.get("fields", {})
        results.append({
            "key": issue.get("key", ""),
            "id": issue.get("id", ""),
            "summary": fields.get("summary", ""),
            "status": (fields.get("status") or {}).get("name", ""),
            "priority": (fields.get("priority") or {}).get("name", ""),
            "assignee": (fields.get("assignee") or {}).get("displayName", ""),
            "reporter": (fields.get("reporter") or {}).get("displayName", ""),
            "created": fields.get("created", ""),
            "updated": fields.get("updated", ""),
            "description": fields.get("description", ""),
            "issuetype": (fields.get("issuetype") or {}).get("name", ""),
            "project": (fields.get("project") or {}).get("key", ""),
        })

    return results


async def get_issue_detail(issue_key: str) -> dict[str, Any]:
    """Fetch a single Jira issue's detail via the REST API.

    Returns a dict with the issue's fields (summary, description, comments,
    attachments, components, labels, etc.). Raises JiraMcpConfigError when
    env vars are missing, and JiraMcpToolError when Jira rejects the call
    (e.g. unknown issue, auth failure).
    """
    base_url, username, token = _get_jira_config()
    url = f"{base_url}/rest/api/2/issue/{issue_key}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(
                url,
                auth=(username, token),
                headers={"Accept": "application/json"},
            )
        except httpx.RequestError as e:
            raise JiraMcpToolError(f"Jira API request failed: {e}") from e

        if response.status_code == 401:
            raise JiraMcpToolError("Jira API authentication failed (401)")
        if response.status_code == 404:
            raise JiraMcpToolError(f"Jira issue {issue_key} not found (404)")
        if response.status_code != 200:
            raise JiraMcpToolError(
                f"Jira API error {response.status_code}: {response.text[:500]}"
            )

        try:
            data = response.json()
        except Exception as e:
            raise JiraMcpToolError(f"Failed to parse Jira response: {e}") from e

    # Flatten the response to match the format the rest of the code expects.
    # Raw Jira API returns: {"key": "...", "fields": {"summary": "...", ...}}
    # We flatten it so callers can access fields directly: {"key": "...", "summary": "..."}
    fields = data.get("fields", {})
    result = {
        "key": data.get("key", issue_key),
        "id": data.get("id", ""),
        **fields,
    }

    # Ensure comments are accessible in a consistent format.
    # Raw API: fields.comment.comments[]
    # We keep both the raw nested structure and a flattened "comments" list.
    comment_data = fields.get("comment", {})
    if isinstance(comment_data, dict):
        comments_list = comment_data.get("comments", [])
        result["comments"] = comments_list

    return result
