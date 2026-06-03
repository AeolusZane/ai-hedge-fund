"""PR Review Sync — fetch PR reviews from Bitbucket and store in vector DB.

Syncs merged PRs and their review comments into the PR embedding vector store.
Designed to run as a scheduled task.

Usage:
    python -m app.backend.domains.bug_fix.pr_sync --project AI --repo corevo --since 7d
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Add project root to path for imports
_project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from app.backend.domains.bug_fix.bitbucket_client import (
    BitbucketMcpConfigError,
    BitbucketMcpToolError,
    get_pr_activities,
    get_pr_diff,
    list_pull_requests,
)
from app.backend.domains.bug_fix.pr_embedding.search import _get_store
from app.backend.domains.bug_fix.pr_embedding.vector_store import VectorStore

logger = logging.getLogger(__name__)


def _parse_since(since: str) -> datetime:
    """Parse a 'since' string like '7d', '30d', '1h' into a datetime."""
    match = re.match(r"^(\d+)([dhm])$", since.strip().lower())
    if not match:
        raise ValueError(f"Invalid since format: {since!r}. Use Nd (days), Nh (hours), or Nm (minutes)")

    value, unit = int(match.group(1)), match.group(2)
    if unit == "d":
        delta = timedelta(days=value)
    elif unit == "h":
        delta = timedelta(hours=value)
    else:
        delta = timedelta(minutes=value)

    return datetime.now(timezone.utc) - delta


def _extract_module(file_path: str) -> str:
    """Extract module name from file path."""
    parts = file_path.split("/")
    if len(parts) >= 2:
        return parts[1] if parts[0] in ("src", "app", "lib") else parts[0]
    return parts[0] if parts else "unknown"


def _classify_issue_type(comment: str) -> str:
    """Classify the issue type from a review comment."""
    text = comment.lower()
    if any(w in text for w in ["bug", "error", "fix", "crash", "null", "exception"]):
        return "bug"
    if any(w in text for w in ["slow", "performance", "cache", "optimize", "n+1"]):
        return "performance"
    if any(w in text for w in ["security", "xss", "injection", "auth", "permission"]):
        return "security"
    if any(w in text for w in ["style", "format", "naming", "convention"]):
        return "style"
    if any(w in text for w in ["refactor", "clean", "simplify", "duplicate"]):
        return "refactor"
    return "general"


async def sync_pr_reviews(
    project: str,
    repo: str,
    since: datetime,
    *,
    max_prs: int = 50,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Sync PR reviews from Bitbucket into the vector store.

    Args:
        project: Bitbucket project key
        repo: Repository slug
        since: Only sync PRs merged after this time
        max_prs: Maximum number of PRs to process
        dry_run: If True, don't actually write to DB

    Returns:
        Dict with sync statistics
    """
    stats = {
        "prs_fetched": 0,
        "comments_synced": 0,
        "prs_skipped": 0,
        "errors": [],
    }

    # Fetch merged PRs
    start = 0
    prs_to_process = []

    while len(prs_to_process) < max_prs:
        try:
            result = await list_pull_requests(
                project=project,
                repo=repo,
                state="MERGED",
                limit=25,
                start=start,
            )
        except (BitbucketMcpConfigError, BitbucketMcpToolError) as e:
            stats["errors"].append(f"Failed to list PRs: {e}")
            break

        values = result.get("values", [])
        if not values:
            break

        for pr in values:
            # Check merge date
            closed_at = pr.get("closedDate")
            if closed_at:
                # Bitbucket returns milliseconds
                merge_time = datetime.fromtimestamp(closed_at / 1000, tz=timezone.utc)
                if merge_time < since:
                    # PRs are sorted by date desc, so we can stop
                    break
            prs_to_process.append(pr)

        if result.get("isLastPage", True):
            break
        start = result.get("nextPageStart", start + 25)

    stats["prs_fetched"] = len(prs_to_process)
    logger.info(f"Fetched {len(prs_to_process)} merged PRs since {since.isoformat()}")

    if dry_run:
        logger.info("Dry run — not writing to DB")
        return stats

    # Get vector store
    store = _get_store()

    # Process each PR
    for pr in prs_to_process[:max_prs]:
        pr_id = pr.get("id")
        pr_title = pr.get("title", "")
        pr_state = pr.get("state", "")

        if not pr_id:
            stats["prs_skipped"] += 1
            continue

        logger.info(f"Processing PR #{pr_id}: {pr_title}")

        # Fetch activities (comments)
        try:
            activities = await get_pr_activities(
                project=project,
                repo=repo,
                pr_id=pr_id,
            )
        except (BitbucketMcpConfigError, BitbucketMcpToolError) as e:
            stats["errors"].append(f"PR #{pr_id}: failed to get activities: {e}")
            continue

        # Extract comments from activities
        comments = []
        for activity in activities:
            action = activity.get("action")
            if action != "COMMENTED":
                continue

            comment = activity.get("comment", {})
            if not comment:
                continue

            comment_text = comment.get("text", "")
            if not comment_text or len(comment_text.strip()) < 10:
                continue

            # Extract author
            author = comment.get("author", {})
            reviewer = author.get("displayName") or author.get("name") or "unknown"

            # Extract file path from comment anchor (if inline comment)
            file_path = ""
            line = 0
            anchor = comment.get("anchor") or activity.get("commentAnchor")
            if anchor:
                file_path = anchor.get("path", "")
                line = anchor.get("line", 0)

            comments.append({
                "reviewer": reviewer,
                "comment_raw": comment_text,
                "file_path": file_path,
                "line": line,
            })

        if not comments:
            stats["prs_skipped"] += 1
            continue

        # Fetch diff (optional, for context)
        code_diff = ""
        try:
            code_diff = await get_pr_diff(project=project, repo=repo, pr_id=pr_id)
            # Truncate if too long
            if len(code_diff) > 50000:
                code_diff = code_diff[:50000] + "\n... (truncated)"
        except (BitbucketMcpConfigError, BitbucketMcpToolError) as e:
            logger.warning(f"PR #{pr_id}: failed to get diff: {e}")

        # Store each comment as a document
        for i, c in enumerate(comments):
            doc_id = f"{project}/{repo}/pr/{pr_id}/comment/{i}"

            # Build searchable document text
            document = (
                f"{pr_title} {c['comment_raw']} "
                f"{c['file_path']} {code_diff[:2000]}"
            )

            # Metadata
            metadata = {
                "project": project,
                "pr_id": pr_id,
                "pr_title": pr_title,
                "pr_state": pr_state,
                "has_needs_work": 1 if any(a.get("action") == "RESCOPED" for a in activities) else 0,
                "file_path": c["file_path"],
                "module": _extract_module(c["file_path"]) if c["file_path"] else "unknown",
                "issue_type": _classify_issue_type(c["comment_raw"]),
                "comment_type": "inline" if c["file_path"] else "general",
                "reviewer": c["reviewer"],
                "date": datetime.now(timezone.utc).isoformat(),
                "line": c["line"],
                "comment_raw": c["comment_raw"],
                "code_diff": code_diff[:10000],  # Store truncated diff
            }

            store.upsert_doc(doc_id, document, metadata)
            stats["comments_synced"] += 1

    # Rebuild vectors after sync
    if stats["comments_synced"] > 0:
        logger.info("Rebuilding TF-IDF vectors...")
        store.build_vectors()

    return stats


async def main():
    parser = argparse.ArgumentParser(description="Sync PR reviews from Bitbucket")
    parser.add_argument("--project", required=True, help="Bitbucket project key")
    parser.add_argument("--repo", required=True, help="Repository slug")
    parser.add_argument("--since", default="7d", help="Sync PRs since (e.g., 7d, 30d, 1h)")
    parser.add_argument("--max-prs", type=int, default=50, help="Max PRs to process")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to DB")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    try:
        since = _parse_since(args.since)
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    stats = await sync_pr_reviews(
        project=args.project,
        repo=args.repo,
        since=since,
        max_prs=args.max_prs,
        dry_run=args.dry_run,
    )

    print(f"\nSync complete:")
    print(f"  PRs fetched: {stats['prs_fetched']}")
    print(f"  Comments synced: {stats['comments_synced']}")
    print(f"  PRs skipped: {stats['prs_skipped']}")
    if stats["errors"]:
        print(f"  Errors: {len(stats['errors'])}")
        for err in stats["errors"][:5]:
            print(f"    - {err}")


if __name__ == "__main__":
    asyncio.run(main())
