"""PR Embedding client — semantic search against historical PR review records.

Calls the pr-embedding service (FastAPI + TF-IDF on port 8100) to find
similar past PR reviews that match the current bug's description.

Falls back gracefully if the service is unavailable.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Service URL from environment, default to localhost:8100
PR_EMBEDDING_URL = os.environ.get("PR_EMBEDDING_URL", "http://localhost:8100")
SEARCH_TIMEOUT = 5.0  # seconds


async def search_similar_prs(
    query: str,
    *,
    project: str | None = None,
    module: str | None = None,
    issue_type: str | None = None,
    reviewer: str | None = None,
    n: int = 5,
) -> list[dict[str, Any]]:
    """Search the pr-embedding service for semantically similar PR reviews.

    The pr-embedding service uses TF-IDF vector search over historical
    Bitbucket PR review records, with jieba tokenization for Chinese text.

    Args:
        query: Natural language description of the bug
        project: Optional filter by project (e.g. "AI", "BUSSINESS")
        module: Optional filter by code module
        issue_type: Optional filter by issue type (性能/安全/逻辑/...)
        reviewer: Optional filter by reviewer name
        n: Max results to return

    Returns:
        List of matching PR review records with similarity scores.
        Empty list if service is unavailable or no matches found.
    """
    if not query.strip():
        return []

    params: dict[str, Any] = {"q": query, "n": n}
    if project:
        params["project"] = project
    if module:
        params["module"] = module
    if issue_type:
        params["issue"] = issue_type
    if reviewer:
        params["reviewer"] = reviewer

    try:
        async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT) as client:
            resp = await client.get(f"{PR_EMBEDDING_URL}/search", params=params)
            resp.raise_for_status()
            data = resp.json()

        # Response format: {"query": "...", "count": N, "results": [...]}
        items = data.get("results", []) if isinstance(data, dict) else data
        results = []
        for item in items[:n]:
            results.append({
                "pr_id": item.get("pr_id", ""),
                "pr_title": item.get("pr_title", ""),
                "reviewer": item.get("reviewer", ""),
                "severity": item.get("severity", ""),
                "issue_type": item.get("issue_type", ""),
                "module": item.get("module", ""),
                "file_path": item.get("file_path", ""),
                "comment": (item.get("comment") or item.get("comment_raw", ""))[:300],
                "date": item.get("date", ""),
                "project": item.get("project", ""),
            })

        logger.info(f"PR embedding search: found {len(results)} results for '{query[:60]}...'")
        return results

    except httpx.ConnectError:
        logger.debug(f"PR embedding service not available at {PR_EMBEDDING_URL}")
        return []
    except httpx.TimeoutException:
        logger.warning(f"PR embedding search timed out ({SEARCH_TIMEOUT}s)")
        return []
    except httpx.HTTPStatusError as e:
        logger.warning(f"PR embedding search failed: HTTP {e.response.status_code}")
        return []
    except Exception as e:
        logger.warning(f"PR embedding search failed: {e}")
        return []


async def health_check() -> bool:
    """Check if the pr-embedding service is reachable."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{PR_EMBEDDING_URL}/health")
            return resp.status_code == 200
    except Exception:
        return False
