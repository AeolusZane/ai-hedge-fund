"""Search interface for PR review records.

Provides a unified search function that combines TF-IDF vector similarity
with document retrieval. Used by both the bug fix analyzer and the
pr_embedding_client.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

from app.backend.domains.bug_fix.pr_embedding.vector_store import VectorStore

logger = logging.getLogger(__name__)

# Default DB path — same location as the standalone pr-embedding service
_DEFAULT_DB_PATH = os.environ.get(
    "PR_EMBEDDING_DB",
    str(Path(__file__).parent / "data" / "pr_review.db"),
)

_store: Optional[VectorStore] = None


def _get_store(db_path: Optional[str] = None) -> VectorStore:
    """Get or create the shared VectorStore instance."""
    global _store
    if _store is None or (db_path and _store.db_path != db_path):
        path = db_path or _DEFAULT_DB_PATH
        _store = VectorStore(path, prefix="reviews")
        _store.ensure_tables(doc_schema="""
            project TEXT DEFAULT 'corevo',
            pr_id INTEGER,
            pr_title TEXT,
            pr_state TEXT,
            has_needs_work INTEGER,
            file_path TEXT,
            module TEXT,
            issue_type TEXT,
            comment_type TEXT,
            reviewer TEXT,
            date TEXT,
            line INTEGER,
            comment_raw TEXT,
            code_diff TEXT
        """)
    return _store


def search_reviews(
    query: str,
    *,
    n: int = 10,
    project: Optional[str] = None,
    module: Optional[str] = None,
    issue_type: Optional[str] = None,
    reviewer: Optional[str] = None,
    min_score: float = 0.0,
    db_path: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Search PR review records by semantic similarity.

    Args:
        query: Natural language search text
        n: Max results to return
        project: Filter by project name
        module: Filter by code module
        issue_type: Filter by issue type (bug/performance/security/...)
        reviewer: Filter by reviewer name
        min_score: Minimum similarity score threshold
        db_path: Override DB path (default: bundled data/pr_review.db)

    Returns:
        List of matching review records with similarity scores
    """
    if not query.strip():
        return []

    store = _get_store(db_path)

    # Vector similarity search
    scored = store.search(query, n=n * 3)  # Over-fetch for post-filtering

    if not scored:
        return []

    # Fetch documents
    doc_ids = [doc_id for doc_id, score in scored if score >= min_score]
    docs = store.get_docs(doc_ids)

    # Apply filters
    results = []
    id_score = {doc_id: score for doc_id, score in scored}

    for doc in docs:
        score = id_score.get(doc["id"], 0)
        if project and doc.get("project") != project:
            continue
        if module and doc.get("module") != module:
            continue
        if issue_type and doc.get("issue_type") != issue_type:
            continue
        if reviewer and doc.get("reviewer") != reviewer:
            continue

        results.append({**doc, "score": score})

    # Sort by score and limit
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:n]


def get_stats(db_path: Optional[str] = None) -> dict[str, Any]:
    """Get statistics about the PR review database."""
    store = _get_store(db_path)
    conn = store._connect()

    try:
        total = store.count()
        vocab = store.vocab_size()

        # Per-project counts
        project_stats = conn.execute(
            f"SELECT project, COUNT(*) as count, COUNT(DISTINCT pr_id) as pr_count "
            f"FROM {store.docs_table} GROUP BY project"
        ).fetchall()

        return {
            "total_records": total,
            "vocab_size": vocab,
            "projects": [dict(r) for r in project_stats],
            "db_path": store.db_path,
        }
    except Exception as e:
        logger.warning(f"Stats query failed: {e}")
        return {"total_records": 0, "vocab_size": 0, "projects": [], "db_path": store.db_path}
