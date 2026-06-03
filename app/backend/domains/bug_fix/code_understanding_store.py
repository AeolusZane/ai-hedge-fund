"""Code Understanding Store — cache for code chain comprehension.

When the analyze agent digs into code to understand a bug, it builds
a mental model of "what this code does and how it connects." This store
caches that understanding so next time we hit the same code area, we
can verify instead of re-reason.

Key design:
- Indexed by file_path + context_key (function/class name)
- Stores the agent's reasoning as structured text
- Tracks file_hash to detect when code has changed
- verification_count tracks how many times the understanding was confirmed
"""
from __future__ import annotations

import hashlib
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
class CodeUnderstanding:
    """A cached understanding of a code area."""
    id: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    # Index keys
    file_path: str = ""           # e.g. "src/services/UserService.java"
    context_key: str = ""         # e.g. "authenticate" or "class:UserDAO" or "module"

    # The understanding itself
    understanding: str = ""       # Agent's reasoning about what this code does
    call_chain: list[str] = field(default_factory=list)  # Discovered call chain
    data_flow: str = ""           # How data flows through this code

    # Verification
    file_hash: str = ""           # SHA256 of file at time of understanding
    last_verified: Optional[str] = None
    verification_count: int = 0   # How many times verified and still valid

    # Provenance
    bug_types: list[str] = field(default_factory=list)  # What bugs led here
    issue_keys: list[str] = field(default_factory=list)  # Which issues triggered this

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> CodeUnderstanding:
        """Build from a database row."""
        data = dict(row)
        for key in ("call_chain", "bug_types", "issue_keys"):
            if key in data and isinstance(data[key], str):
                try:
                    data[key] = json.loads(data[key])
                except (json.JSONDecodeError, TypeError):
                    data[key] = []
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class CodeUnderstandingStore:
    """SQLite-backed code understanding cache."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = str(db_path or DATABASE_PATH)
        self._ensure_tables()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self) -> None:
        """Create tables if they don't exist."""
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS code_understandings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    context_key TEXT NOT NULL DEFAULT '',
                    understanding TEXT NOT NULL DEFAULT '',
                    call_chain TEXT NOT NULL DEFAULT '[]',
                    data_flow TEXT NOT NULL DEFAULT '',
                    file_hash TEXT NOT NULL DEFAULT '',
                    last_verified TEXT,
                    verification_count INTEGER NOT NULL DEFAULT 0,
                    bug_types TEXT NOT NULL DEFAULT '[]',
                    issue_keys TEXT NOT NULL DEFAULT '[]'
                )
            """)
            # Unique constraint on file_path + context_key
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_code_understanding_key
                ON code_understandings(file_path, context_key)
            """)
            # Index for file_path lookups
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_code_understanding_file
                ON code_understandings(file_path)
            """)
            conn.commit()

    def store(self, cu: CodeUnderstanding) -> int:
        """Store or update a code understanding.
        
        If an understanding for the same file_path + context_key exists,
        update it. Otherwise insert new.
        """
        now = datetime.now(timezone.utc).isoformat()
        
        with self._connect() as conn:
            # Check if exists
            row = conn.execute(
                "SELECT id FROM code_understandings WHERE file_path = ? AND context_key = ?",
                (cu.file_path, cu.context_key)
            ).fetchone()

            if row:
                # Update existing
                conn.execute("""
                    UPDATE code_understandings SET
                        updated_at = ?,
                        understanding = ?,
                        call_chain = ?,
                        data_flow = ?,
                        file_hash = ?,
                        last_verified = ?,
                        bug_types = ?,
                        issue_keys = ?
                    WHERE id = ?
                """, (
                    now,
                    cu.understanding,
                    json.dumps(cu.call_chain),
                    cu.data_flow,
                    cu.file_hash,
                    now,  # Also update last_verified on store
                    json.dumps(cu.bug_types),
                    json.dumps(cu.issue_keys),
                    row["id"],
                ))
                cu.id = row["id"]
                cu.updated_at = now
            else:
                # Insert new
                cursor = conn.execute("""
                    INSERT INTO code_understandings (
                        created_at, updated_at, file_path, context_key,
                        understanding, call_chain, data_flow, file_hash,
                        last_verified, verification_count, bug_types, issue_keys
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                """, (
                    now, now, cu.file_path, cu.context_key,
                    cu.understanding, json.dumps(cu.call_chain), cu.data_flow,
                    cu.file_hash, now,
                    json.dumps(cu.bug_types), json.dumps(cu.issue_keys),
                ))
                cu.id = cursor.lastrowid
                cu.created_at = now
                cu.updated_at = now

            conn.commit()
            return cu.id or 0

    def lookup(self, file_path: str, context_key: str = "") -> Optional[CodeUnderstanding]:
        """Look up a cached understanding by file_path + context_key."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM code_understandings WHERE file_path = ? AND context_key = ?",
                (file_path, context_key)
            ).fetchone()
            if row:
                return CodeUnderstanding.from_row(row)
        return None

    def lookup_by_file(self, file_path: str) -> list[CodeUnderstanding]:
        """Look up all understandings for a file (any context_key)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM code_understandings WHERE file_path = ? ORDER BY context_key",
                (file_path,)
            ).fetchall()
            return [CodeUnderstanding.from_row(r) for r in rows]

    def lookup_by_files(self, file_paths: list[str]) -> list[CodeUnderstanding]:
        """Look up understandings for multiple files."""
        if not file_paths:
            return []
        placeholders = ",".join("?" * len(file_paths))
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM code_understandings WHERE file_path IN ({placeholders}) ORDER BY file_path, context_key",
                file_paths
            ).fetchall()
            return [CodeUnderstanding.from_row(r) for r in rows]

    def verify(self, understanding_id: int, current_file_hash: str) -> tuple[bool, CodeUnderstanding | None]:
        """Verify if a cached understanding is still valid.
        
        Returns (is_valid, understanding).
        is_valid is True if file_hash matches (code hasn't changed).
        Always increments verification_count.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM code_understandings WHERE id = ?",
                (understanding_id,)
            ).fetchone()
            if not row:
                return False, None

            cu = CodeUnderstanding.from_row(row)
            is_valid = (cu.file_hash == current_file_hash)
            
            now = datetime.now(timezone.utc).isoformat()
            conn.execute("""
                UPDATE code_understandings SET
                    last_verified = ?,
                    verification_count = verification_count + 1
                WHERE id = ?
            """, (now, understanding_id))
            conn.commit()
            
            cu.last_verified = now
            cu.verification_count += 1
            
            return is_valid, cu

    def list_all(self, limit: int = 100) -> list[CodeUnderstanding]:
        """List all cached understandings."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM code_understandings ORDER BY verification_count DESC, updated_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [CodeUnderstanding.from_row(r) for r in rows]

    def delete(self, understanding_id: int) -> bool:
        """Delete a cached understanding."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM code_understandings WHERE id = ?",
                (understanding_id,)
            )
            conn.commit()
            return cursor.rowcount > 0

    def stats(self) -> dict[str, Any]:
        """Get aggregate stats."""
        with self._connect() as conn:
            row = conn.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(verification_count) as total_verifications,
                    COUNT(DISTINCT file_path) as unique_files
                FROM code_understandings
            """).fetchone()
            return {
                "total": row["total"] or 0,
                "total_verifications": row["total_verifications"] or 0,
                "unique_files": row["unique_files"] or 0,
            }


def compute_file_hash(file_path: str | Path) -> str:
    """Compute SHA256 hash of a file's content."""
    try:
        content = Path(file_path).read_bytes()
        return hashlib.sha256(content).hexdigest()[:16]  # First 16 chars is enough
    except Exception:
        return ""


def build_understanding_context(
    store: CodeUnderstandingStore,
    file_paths: list[str],
    repo_path: Optional[str] = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Build context string from cached understandings for given files.
    
    Returns:
        Tuple of (context_string, cache_hits_info)
        context_string: formatted text to inject into LLM prompt
        cache_hits_info: list of dicts describing what was cached/verified
    """
    if not file_paths:
        return "", []

    understandings = store.lookup_by_files(file_paths)
    if not understandings:
        return "", []

    context_parts = []
    hits_info = []

    for cu in understandings:
        # Verify if we have the actual file
        is_valid = None
        if repo_path:
            full_path = Path(repo_path) / cu.file_path
            if full_path.exists():
                current_hash = compute_file_hash(full_path)
                is_valid, _ = store.verify(cu.id or 0, current_hash)
        
        status = "verified" if is_valid else ("unverified" if is_valid is None else "stale")
        
        context_parts.append(
            f"### {cu.file_path} ({cu.context_key or 'module'})\n"
            f"- Status: {status}\n"
            f"- Understanding: {cu.understanding}\n"
            + (f"- Call chain: {' → '.join(cu.call_chain)}\n" if cu.call_chain else "")
            + (f"- Data flow: {cu.data_flow}\n" if cu.data_flow else "")
        )
        
        hits_info.append({
            "file_path": cu.file_path,
            "context_key": cu.context_key,
            "status": status,
            "verification_count": cu.verification_count,
        })

    if context_parts:
        context_string = (
            "## Cached Code Understandings\n"
            "The following code areas have been analyzed before. "
            "If status is 'verified', trust the understanding. "
            "If 'stale', the code has changed — verify key points. "
            "If 'unverified', use as reference but confirm.\n\n"
            + "\n".join(context_parts)
        )
    else:
        context_string = ""

    return context_string, hits_info
