"""TF-IDF vector store for semantic search.

Stores document vectors in SQLite using binary blob format.
Supports building vocab, computing TF-IDF vectors, and cosine similarity search.
"""
from __future__ import annotations

import math
import sqlite3
import struct
from pathlib import Path
from typing import Any, Optional

from app.backend.domains.bug_fix.pr_embedding.tokenizer import tokenize


class VectorStore:
    """TF-IDF vector storage and search in SQLite.

    Tables:
    - {prefix}_docs: document metadata + text
    - {prefix}_vectors: binary TF-IDF vectors
    - {prefix}_vocab: word -> (idx, idf) mapping
    """

    def __init__(self, db_path: str | Path, prefix: str = "pr"):
        self.db_path = str(db_path)
        self.prefix = prefix
        self._conn: Optional[sqlite3.Connection] = None

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def docs_table(self) -> str:
        return f"{self.prefix}_docs"

    @property
    def vectors_table(self) -> str:
        return f"{self.prefix}_vectors"

    @property
    def vocab_table(self) -> str:
        return f"{self.prefix}_vocab"

    def ensure_tables(self, doc_schema: str = "") -> None:
        """Create tables if they don't exist.

        Args:
            doc_schema: Additional columns for the docs table (SQL DDL fragment)
        """
        conn = self._connect()

        # Docs table — caller provides schema
        if doc_schema:
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.docs_table} (
                    id TEXT PRIMARY KEY,
                    document TEXT NOT NULL,
                    {doc_schema}
                )
            """)
        else:
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.docs_table} (
                    id TEXT PRIMARY KEY,
                    document TEXT NOT NULL
                )
            """)

        # Vectors table
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.vectors_table} (
                id TEXT PRIMARY KEY,
                vector BLOB NOT NULL
            )
        """)

        # Vocab table
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.vocab_table} (
                word TEXT PRIMARY KEY,
                idx INTEGER NOT NULL,
                idf REAL NOT NULL
            )
        """)

        conn.commit()

    def build_vectors(self) -> int:
        """Build TF-IDF vectors for all documents.

        Returns:
            Number of documents vectorized
        """
        conn = self._connect()

        rows = conn.execute(
            f"SELECT id, document FROM {self.docs_table}"
        ).fetchall()

        if not rows:
            return 0

        # Tokenize all documents
        all_docs = [tokenize(row["document"]) for row in rows]
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
        conn.execute(f"DELETE FROM {self.vocab_table}")
        for word, info in vocab.items():
            conn.execute(
                f"INSERT INTO {self.vocab_table} (word, idx, idf) VALUES (?, ?, ?)",
                (word, info["idx"], info["idf"]),
            )

        # Clear and rebuild vectors
        conn.execute(f"DELETE FROM {self.vectors_table}")

        dim = len(vocab)
        if dim == 0:
            conn.commit()
            return 0

        for i, (row, tokens) in enumerate(zip(rows, all_docs)):
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
                f"INSERT INTO {self.vectors_table} (id, vector) VALUES (?, ?)",
                (row["id"], blob),
            )

        conn.commit()
        return n_docs

    def search(self, query: str, n: int = 10) -> list[tuple[str, float]]:
        """Search for similar documents by cosine similarity.

        Args:
            query: Search text
            n: Max results

        Returns:
            List of (doc_id, score) tuples, sorted by score descending
        """
        conn = self._connect()

        # Load vocab
        vocab_rows = conn.execute(
            f"SELECT word, idx, idf FROM {self.vocab_table}"
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
            return []  # No matching tokens in vocab

        # Compute cosine similarity with all vectors
        vectors = conn.execute(
            f"SELECT id, vector FROM {self.vectors_table}"
        ).fetchall()

        scored = []
        for row in vectors:
            vec = struct.unpack(f"{dim}f", row["vector"])
            score = sum(a * b for a, b in zip(query_vec, vec))
            scored.append((row["id"], score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:n]

    def get_doc(self, doc_id: str) -> Optional[dict]:
        """Get a document by ID."""
        conn = self._connect()
        row = conn.execute(
            f"SELECT * FROM {self.docs_table} WHERE id = ?", (doc_id,)
        ).fetchone()
        return dict(row) if row else None

    def upsert_doc(
        self,
        doc_id: str,
        document: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Insert or update a document. Does NOT rebuild vectors — call build_vectors() after batch."""
        conn = self._connect()
        meta = metadata or {}

        # Build column list and values
        cols = ["id", "document"] + list(meta.keys())
        placeholders = ", ".join(["?"] * len(cols))
        values = [doc_id, document] + list(meta.values())

        # Use INSERT OR REPLACE for upsert
        conn.execute(
            f"INSERT OR REPLACE INTO {self.docs_table} ({', '.join(cols)}) VALUES ({placeholders})",
            values,
        )
        conn.commit()

    def get_docs(self, doc_ids: list[str]) -> list[dict]:
        """Get multiple documents by ID, preserving order."""
        if not doc_ids:
            return []
        conn = self._connect()
        placeholders = ",".join(["?"] * len(doc_ids))
        rows = conn.execute(
            f"SELECT * FROM {self.docs_table} WHERE id IN ({placeholders})",
            doc_ids,
        ).fetchall()
        # Preserve order
        by_id = {row["id"]: dict(row) for row in rows}
        return [by_id[did] for did in doc_ids if did in by_id]

    def count(self) -> int:
        """Count documents."""
        conn = self._connect()
        row = conn.execute(f"SELECT COUNT(*) as cnt FROM {self.docs_table}").fetchone()
        return row["cnt"] if row else 0

    def vocab_size(self) -> int:
        """Count vocab words."""
        conn = self._connect()
        row = conn.execute(f"SELECT COUNT(*) as cnt FROM {self.vocab_table}").fetchone()
        return row["cnt"] if row else 0
