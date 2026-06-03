"""Experience Store — persistent storage for bug fix learnings.

Stores completed bug fix cases as reusable experiences. When a new bug
comes in, the system searches for similar past cases to accelerate analysis.

Uses TF-IDF vector similarity search (primary) with FTS5 full-text search
as fallback. The vector search handles semantic similarity — e.g. matching
"登录超时白屏" with "session expired 导致页面崩溃".
"""
from __future__ import annotations

import json
import logging
import math
import sqlite3
import struct
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.backend.database.connection import DATABASE_PATH
from app.backend.domains.bug_fix.pr_embedding.tokenizer import tokenize

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
    """SQLite-backed experience storage with TF-IDF vector search + FTS5 fallback."""

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

                -- TF-IDF vector tables for semantic search
                CREATE TABLE IF NOT EXISTS experiences_vocab (
                    word TEXT PRIMARY KEY,
                    idx INTEGER NOT NULL,
                    idf REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS experiences_vectors (
                    exp_id INTEGER PRIMARY KEY,
                    vector BLOB NOT NULL
                );
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

    def build_vectors(self) -> int:
        """Build TF-IDF vectors for all experiences.

        Call this after storing new experiences to update the vector index.

        Returns:
            Number of experiences vectorized
        """
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT id, search_text FROM experiences WHERE search_text != ''"
            ).fetchall()

            if not rows:
                return 0

            # Tokenize all documents
            all_docs = [tokenize(row["search_text"]) for row in rows]
            n_docs = len(all_docs)

            # Compute document frequency
            df: dict[str, int] = {}
            for tokens in all_docs:
                for t in set(tokens):
                    df[t] = df.get(t, 0) + 1

            # Build vocab: filter out too-rare and too-common words
            vocab: dict[str, dict] = {}
            idx = 0
            for word, count in df.items():
                if 1 <= count <= n_docs * 0.9:
                    vocab[word] = {"idx": idx, "idf": math.log(n_docs / count)}
                    idx += 1

            # Clear and rebuild vocab
            conn.execute("DELETE FROM experiences_vocab")
            for word, info in vocab.items():
                conn.execute(
                    "INSERT INTO experiences_vocab (word, idx, idf) VALUES (?, ?, ?)",
                    (word, info["idx"], info["idf"]),
                )

            # Clear and rebuild vectors
            conn.execute("DELETE FROM experiences_vectors")

            dim = len(vocab)
            if dim == 0:
                conn.commit()
                return 0

            for row, tokens in zip(rows, all_docs):
                tf: dict[str, int] = {}
                for t in tokens:
                    if t in vocab:
                        tf[t] = tf.get(t, 0) + 1

                vec = [0.0] * dim
                for t, count in tf.items():
                    vec[vocab[t]["idx"]] = count * vocab[t]["idf"]

                # L2 normalize
                norm = math.sqrt(sum(v * v for v in vec))
                if norm > 0:
                    vec = [v / norm for v in vec]

                blob = struct.pack(f"{dim}f", *vec)
                conn.execute(
                    "INSERT INTO experiences_vectors (exp_id, vector) VALUES (?, ?)",
                    (row["id"], blob),
                )

            conn.commit()
            logger.info(f"Built vectors for {n_docs} experiences (vocab: {dim})")
            return n_docs
        except Exception as e:
            logger.warning(f"build_vectors failed: {e}")
            return 0
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
        """Search for similar experiences using TF-IDF vector similarity.

        Falls back to FTS5 full-text search if vector search fails or
        returns no results.

        Args:
            query: Natural language description of the bug to match against
            bug_type: Optional filter by bug type
            limit: Max results to return
            min_confidence: Minimum confidence threshold

        Returns:
            List of matching experiences, ranked by relevance
        """
        # Try vector search first
        results = self._vector_search(query, bug_type=bug_type, limit=limit, min_confidence=min_confidence)
        
        # Fallback to FTS5 if vector search returns nothing
        if not results:
            results = self._fts_search(query, bug_type=bug_type, limit=limit, min_confidence=min_confidence)
        
        # Final fallback to LIKE search
        if not results:
            results = self._fallback_search(query, bug_type=bug_type, limit=limit)
        
        return results

    def _vector_search(
        self,
        query: str,
        *,
        bug_type: str = "",
        limit: int = 5,
        min_confidence: float = 0.0,
    ) -> list[Experience]:
        """TF-IDF vector similarity search."""
        conn = self._connect()
        try:
            # Load vocab
            vocab_rows = conn.execute(
                "SELECT word, idx, idf FROM experiences_vocab"
            ).fetchall()
            
            if not vocab_rows:
                return []
            
            vocab = {row["word"]: {"idx": row["idx"], "idf": row["idf"]} for row in vocab_rows}
            dim = len(vocab)
            
            # Build query vector
            query_tokens = tokenize(query)
            tf: dict[str, int] = {}
            for t in query_tokens:
                if t in vocab:
                    tf[t] = tf.get(t, 0) + 1
            
            query_vec = [0.0] * dim
            for t, count in tf.items():
                query_vec[vocab[t]["idx"]] = count * vocab[t]["idf"]
            
            # L2 normalize
            norm = math.sqrt(sum(v * v for v in query_vec))
            if norm > 0:
                query_vec = [v / norm for v in query_vec]
            else:
                return []
            
            # Compute cosine similarity
            vectors = conn.execute(
                "SELECT exp_id, vector FROM experiences_vectors"
            ).fetchall()
            
            scored = []
            for row in vectors:
                vec = struct.unpack(f"{dim}f", row["vector"])
                score = sum(a * b for a, b in zip(query_vec, vec))
                scored.append((row["exp_id"], score))
            
            scored.sort(key=lambda x: x[1], reverse=True)
            top_ids = [exp_id for exp_id, score in scored[:limit * 2] if score > 0.01]
            
            if not top_ids:
                return []
            
            # Fetch experiences
            placeholders = ",".join(["?"] * len(top_ids))
            sql = f"""
                SELECT * FROM experiences
                WHERE id IN ({placeholders})
                  AND confidence >= ?
            """
            params: list[Any] = top_ids + [min_confidence]
            
            if bug_type:
                sql += " AND bug_type = ?"
                params.append(bug_type)
            
            rows = conn.execute(sql, params).fetchall()
            
            # Sort by vector score
            id_score = {exp_id: score for exp_id, score in scored}
            results = [Experience.from_row(r) for r in rows]
            results.sort(key=lambda e: id_score.get(e.id, 0), reverse=True)
            
            return results[:limit]
        except Exception as e:
            logger.debug(f"Vector search failed: {e}")
            return []
        finally:
            conn.close()

    def _fts_search(
        self,
        query: str,
        *,
        bug_type: str = "",
        limit: int = 5,
        min_confidence: float = 0.0,
    ) -> list[Experience]:
        """FTS5 full-text search fallback."""
        conn = self._connect()
        try:
            fts_query = query.strip()
            if not fts_query:
                return []

            words = [w for w in fts_query.split() if len(w) >= 2]
            if not words:
                return []

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
            return []
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
