"""Experience Store — persistent storage for bug fix learnings.

Stores completed bug fix cases as reusable experiences. When a new bug
comes in, the system searches for similar past cases to accelerate analysis.

Uses SQLite FTS5 for full-text similarity search — no vector DB needed.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.backend.database.connection import DATABASE_PATH

logger = logging.getLogger(__name__)


@dataclass
class Experience:
    """A single bug fix experience."""
    id: Optional[int] = None
    created_at: Optional[str] = None

    # Source
    issue_key: str = ""
    issue_summary: str = ""
    issue_description: str = ""
    bug_type: str = ""  # null_pointer, logic_error, race_condition, etc.

    # Analysis result
    root_cause: str = ""
    root_cause_hypothesis: str = ""
    affected_areas: list[str] = field(default_factory=list)
    suggested_approach: list[str] = field(default_factory=list)
    confidence: float = 0.0

    # Patch result
    patch_summary: str = ""
    files_changed: list[str] = field(default_factory=list)
    patch_strategy: str = ""

    # Gate decision
    gate_action: str = ""  # approved / modified / rejected
    human_context: str = ""

    # Metadata
    components: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    run_id: str = ""
    duration_seconds: float = 0.0
    token_usage: dict[str, Any] = field(default_factory=dict)

    # Search text (auto-generated for FTS)
    search_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Experience:
        """Build from a database row."""
        data = dict(row)
        # Parse JSON fields
        for key in ("affected_areas", "suggested_approach", "files_changed",
                     "components", "labels", "token_usage"):
            if key in data and isinstance(data[key], str):
                try:
                    data[key] = json.loads(data[key])
                except (json.JSONDecodeError, TypeError):
                    data[key] = [] if key != "token_usage" else {}
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class ExperienceStore:
    """SQLite-backed experience storage with FTS5 search."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = str(db_path or DATABASE_PATH)
        self._ensure_tables()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self) -> None:
        """Create tables if they don't exist."""
        conn = self._connect()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS experiences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    issue_key TEXT NOT NULL DEFAULT '',
                    issue_summary TEXT NOT NULL DEFAULT '',
                    issue_description TEXT NOT NULL DEFAULT '',
                    bug_type TEXT NOT NULL DEFAULT '',
                    root_cause TEXT NOT NULL DEFAULT '',
                    root_cause_hypothesis TEXT NOT NULL DEFAULT '',
                    affected_areas TEXT NOT NULL DEFAULT '[]',
                    suggested_approach TEXT NOT NULL DEFAULT '[]',
                    confidence REAL NOT NULL DEFAULT 0.0,
                    patch_summary TEXT NOT NULL DEFAULT '',
                    files_changed TEXT NOT NULL DEFAULT '[]',
                    patch_strategy TEXT NOT NULL DEFAULT '',
                    gate_action TEXT NOT NULL DEFAULT '',
                    human_context TEXT NOT NULL DEFAULT '',
                    components TEXT NOT NULL DEFAULT '[]',
                    labels TEXT NOT NULL DEFAULT '[]',
                    run_id TEXT NOT NULL DEFAULT '',
                    duration_seconds REAL NOT NULL DEFAULT 0.0,
                    token_usage TEXT NOT NULL DEFAULT '{}',
                    search_text TEXT NOT NULL DEFAULT ''
                );

                -- FTS5 virtual table for full-text similarity search
                CREATE VIRTUAL TABLE IF NOT EXISTS experiences_fts
                USING fts5(
                    issue_summary,
                    issue_description,
                    root_cause,
                    root_cause_hypothesis,
                    patch_strategy,
                    bug_type,
                    content='experiences',
                    content_rowid='id'
                );

                -- Triggers to keep FTS in sync
                CREATE TRIGGER IF NOT EXISTS experiences_ai AFTER INSERT ON experiences BEGIN
                    INSERT INTO experiences_fts(rowid, issue_summary, issue_description,
                        root_cause, root_cause_hypothesis, patch_strategy, bug_type)
                    VALUES (new.id, new.issue_summary, new.issue_description,
                        new.root_cause, new.root_cause_hypothesis, new.patch_strategy, new.bug_type);
                END;

                CREATE TRIGGER IF NOT EXISTS experiences_ad AFTER DELETE ON experiences BEGIN
                    INSERT INTO experiences_fts(experiences_fts, rowid, issue_summary,
                        issue_description, root_cause, root_cause_hypothesis, patch_strategy, bug_type)
                    VALUES ('delete', old.id, old.issue_summary, old.issue_description,
                        old.root_cause, old.root_cause_hypothesis, old.patch_strategy, old.bug_type);
                END;

                CREATE TRIGGER IF NOT EXISTS experiences_au AFTER UPDATE ON experiences BEGIN
                    INSERT INTO experiences_fts(experiences_fts, rowid, issue_summary,
                        issue_description, root_cause, root_cause_hypothesis, patch_strategy, bug_type)
                    VALUES ('delete', old.id, old.issue_summary, old.issue_description,
                        old.root_cause, old.root_cause_hypothesis, old.patch_strategy, old.bug_type);
                    INSERT INTO experiences_fts(rowid, issue_summary, issue_description,
                        root_cause, root_cause_hypothesis, patch_strategy, bug_type)
                    VALUES (new.id, new.issue_summary, new.issue_description,
                        new.root_cause, new.root_cause_hypothesis, new.patch_strategy, new.bug_type);
                END;
            """)
            conn.commit()
        finally:
            conn.close()

    def store(self, exp: Experience) -> int:
        """Store a new experience. Returns the new row id."""
        # Build search text for FTS
        exp.search_text = " ".join([
            exp.issue_summary,
            exp.issue_description[:500],
            exp.root_cause,
            exp.root_cause_hypothesis,
            exp.patch_strategy,
            exp.bug_type,
        ])

        now = datetime.now(timezone.utc).isoformat()
        exp.created_at = now

        conn = self._connect()
        try:
            cursor = conn.execute(
                """INSERT INTO experiences (
                    created_at, issue_key, issue_summary, issue_description,
                    bug_type, root_cause, root_cause_hypothesis,
                    affected_areas, suggested_approach, confidence,
                    patch_summary, files_changed, patch_strategy,
                    gate_action, human_context, components, labels,
                    run_id, duration_seconds, token_usage, search_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    now, exp.issue_key, exp.issue_summary, exp.issue_description,
                    exp.bug_type, exp.root_cause, exp.root_cause_hypothesis,
                    json.dumps(exp.affected_areas), json.dumps(exp.suggested_approach),
                    exp.confidence,
                    exp.patch_summary, json.dumps(exp.files_changed), exp.patch_strategy,
                    exp.gate_action, exp.human_context,
                    json.dumps(exp.components), json.dumps(exp.labels),
                    exp.run_id, exp.duration_seconds, json.dumps(exp.token_usage),
                    exp.search_text,
                ),
            )
            conn.commit()
            exp.id = cursor.lastrowid
            logger.info(f"Stored experience #{exp.id}: {exp.issue_key} — {exp.issue_summary[:60]}")
            return exp.id
        finally:
            conn.close()

    def search_similar(
        self,
        query: str,
        *,
        bug_type: str = "",
        limit: int = 5,
        min_confidence: float = 0.0,
    ) -> list[Experience]:
        """Search for similar experiences using FTS5.

        Args:
            query: Natural language description of the bug to match against
            bug_type: Optional filter by bug type
            limit: Max results to return
            min_confidence: Minimum confidence threshold

        Returns:
            List of matching experiences, ranked by relevance
        """
        conn = self._connect()
        try:
            # Build FTS query — use the query text directly
            # FTS5 supports ranking via bm25()
            fts_query = query.strip()
            if not fts_query:
                return []

            # Escape special FTS characters and build OR query from words
            words = [w for w in fts_query.split() if len(w) >= 2]
            if not words:
                return []

            # Use OR to be more permissive (any word match)
            fts_expr = " OR ".join(words)

            sql = """
                SELECT e.*, rank
                FROM experiences_fts fts
                JOIN experiences e ON e.id = fts.rowid
                WHERE experiences_fts MATCH ?
                  AND e.confidence >= ?
            """
            params: list[Any] = [fts_expr, min_confidence]

            if bug_type:
                sql += " AND e.bug_type = ?"
                params.append(bug_type)

            sql += " ORDER BY rank LIMIT ?"
            params.append(limit)

            rows = conn.execute(sql, params).fetchall()
            return [Experience.from_row(r) for r in rows]
        except Exception as e:
            logger.warning(f"FTS search failed: {e}")
            # Fallback: simple LIKE search
            return self._fallback_search(query, bug_type=bug_type, limit=limit)
        finally:
            conn.close()

    def _fallback_search(
        self, query: str, *, bug_type: str = "", limit: int = 5
    ) -> list[Experience]:
        """Simple LIKE-based search when FTS fails."""
        conn = self._connect()
        try:
            sql = """
                SELECT * FROM experiences
                WHERE (issue_summary LIKE ? OR issue_description LIKE ?
                       OR root_cause LIKE ? OR search_text LIKE ?)
                  AND confidence >= 0.0
            """
            pattern = f"%{query[:100]}%"
            params: list[Any] = [pattern, pattern, pattern, pattern]

            if bug_type:
                sql += " AND bug_type = ?"
                params.append(bug_type)

            sql += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(sql, params).fetchall()
            return [Experience.from_row(r) for r in rows]
        except Exception as e:
            logger.warning(f"Fallback search also failed: {e}")
            return []
        finally:
            conn.close()

    def get_by_id(self, exp_id: int) -> Optional[Experience]:
        """Get a single experience by ID."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM experiences WHERE id = ?", (exp_id,)
            ).fetchone()
            return Experience.from_row(row) if row else None
        finally:
            conn.close()

    def get_by_issue_key(self, issue_key: str) -> list[Experience]:
        """Get all experiences for a specific issue key."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM experiences WHERE issue_key = ? ORDER BY created_at DESC",
                (issue_key,),
            ).fetchall()
            return [Experience.from_row(r) for r in rows]
        finally:
            conn.close()

    def list_recent(self, limit: int = 20) -> list[Experience]:
        """List most recent experiences."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM experiences ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [Experience.from_row(r) for r in rows]
        finally:
            conn.close()

    def count(self) -> int:
        """Total number of stored experiences."""
        conn = self._connect()
        try:
            row = conn.execute("SELECT COUNT(*) as cnt FROM experiences").fetchone()
            return row["cnt"] if row else 0
        finally:
            conn.close()

    def delete(self, exp_id: int) -> bool:
        """Delete an experience by ID."""
        conn = self._connect()
        try:
            cursor = conn.execute("DELETE FROM experiences WHERE id = ?", (exp_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def get_stats(self) -> dict[str, Any]:
        """Get aggregate stats about stored experiences."""
        conn = self._connect()
        try:
            total = conn.execute("SELECT COUNT(*) as cnt FROM experiences").fetchone()["cnt"]
            approved = conn.execute(
                "SELECT COUNT(*) as cnt FROM experiences WHERE gate_action = 'approve'"
            ).fetchone()["cnt"]
            avg_confidence = conn.execute(
                "SELECT AVG(confidence) as avg_c FROM experiences WHERE confidence > 0"
            ).fetchone()["avg_c"] or 0.0
            bug_types = conn.execute(
                "SELECT bug_type, COUNT(*) as cnt FROM experiences GROUP BY bug_type ORDER BY cnt DESC"
            ).fetchall()

            return {
                "total": total,
                "approved": approved,
                "avg_confidence": round(avg_confidence, 2),
                "bug_types": {row["bug_type"]: row["cnt"] for row in bug_types if row["bug_type"]},
            }
        finally:
            conn.close()


# ─── Helper: build Experience from executor state ────────────────────

def build_experience_from_state(state: dict[str, Any], gate_action: str = "approve") -> Experience:
    """Build an Experience object from the executor's final state.

    Called after a successful run with Gate approval.
    """
    jira = state.get("jira_detail") or {}
    analysis = state.get("analysis") or {}
    patch = state.get("patch") or {}

    # Extract components
    components = []
    for c in (jira.get("components") or []):
        if isinstance(c, dict):
            components.append(c.get("name", ""))
        elif isinstance(c, str):
            components.append(c)

    # Extract labels
    labels = jira.get("labels") or []
    if isinstance(labels, str):
        labels = [labels]

    # Build patch strategy summary
    patch_strategy = ""
    if analysis.get("suggested_approach"):
        patch_strategy = " → ".join(analysis["suggested_approach"])

    # Build patch summary from files changed
    files_changed = patch.get("files_changed") or []
    if isinstance(files_changed, str):
        files_changed = [files_changed]

    # Token usage
    token_usage = {}
    if analysis.get("_token_usage"):
        token_usage = analysis["_token_usage"]
    if patch.get("token_usage"):
        token_usage["patch"] = patch["token_usage"]

    return Experience(
        issue_key=state.get("issue_key", jira.get("key", "")),
        issue_summary=jira.get("summary", ""),
        issue_description=(jira.get("description") or "")[:2000],
        bug_type=analysis.get("decision_steps", [{}])[0].get("details", {}).get("bug_type", ""),
        root_cause=analysis.get("root_cause_hypothesis", ""),
        root_cause_hypothesis=analysis.get("root_cause_hypothesis", ""),
        affected_areas=analysis.get("affected_areas") or [],
        suggested_approach=analysis.get("suggested_approach") or [],
        confidence=_extract_overall_confidence(analysis),
        patch_summary=patch.get("summary", ""),
        files_changed=files_changed,
        patch_strategy=patch_strategy,
        gate_action=gate_action,
        human_context=state.get("human_context", ""),
        components=components,
        labels=labels,
        run_id=str(state.get("run_id", "")),
        token_usage=token_usage,
    )


def _extract_overall_confidence(analysis: dict[str, Any]) -> float:
    """Extract the overall confidence from analysis decision steps."""
    steps = analysis.get("decision_steps") or []
    if not steps:
        return 0.5
    # Use the last step's confidence as overall
    last = steps[-1]
    return float(last.get("confidence", 0.5))
