"""Local, provenance-aware document knowledge store with SQLite full-text search."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from genesis_core.state import StateStore


class KnowledgeError(ValueError):
    """Raised for invalid knowledge documents or search requests."""


class KnowledgeStore:
    """Stores document chunks locally and retrieves them with lexical full-text search.

    Embeddings are intentionally optional and not required by this first implementation.
    Search results always retain their source document and chunk location.
    """

    MAX_DOCUMENT_CHARS = 1_000_000
    CHUNK_SIZE = 1400
    CHUNK_OVERLAP = 180

    def __init__(self, state: StateStore | None = None) -> None:
        self.database_path: Path = (state or StateStore()).database_path
        self.fts_available = False
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database_path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        return db

    def _initialise(self) -> None:
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_documents (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    source_uri TEXT NOT NULL DEFAULT '',
                    content_hash TEXT NOT NULL UNIQUE,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id TEXT NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    UNIQUE(document_id, chunk_index)
                )
            """)
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_document "
                "ON knowledge_chunks(document_id, chunk_index)"
            )
            try:
                db.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts
                    USING fts5(content, title, source_uri, tokenize='unicode61')
                """)
                self.fts_available = True
            except sqlite3.OperationalError:
                # Some SQLite builds omit FTS5; a bounded LIKE fallback remains available.
                self.fts_available = False

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @classmethod
    def _split_chunks(cls, content: str) -> list[str]:
        text = re.sub(r"\r\n?", "\n", content).strip()
        if not text:
            return []
        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = min(start + cls.CHUNK_SIZE, len(text))
            if end < len(text):
                boundary = max(text.rfind("\n", start, end), text.rfind(" ", start, end))
                if boundary > start + cls.CHUNK_SIZE // 2:
                    end = boundary
            part = text[start:end].strip()
            if part:
                chunks.append(part)
            if end >= len(text):
                break
            start = max(start + 1, end - cls.CHUNK_OVERLAP)
        return chunks

    def ingest_text(
        self,
        title: str,
        content: str,
        source_uri: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        title = title.strip()
        source_uri = source_uri.strip()[:1000]
        if not title or len(title) > 240:
            raise KnowledgeError("Document title must contain 1 to 240 characters.")
        if not isinstance(content, str) or not content.strip():
            raise KnowledgeError("Document content cannot be empty.")
        if len(content) > self.MAX_DOCUMENT_CHARS:
            raise KnowledgeError("Document exceeds the 1,000,000 character import limit.")
        if metadata is not None and not isinstance(metadata, dict):
            raise KnowledgeError("Document metadata must be an object.")
        clean_content = content.strip()
        digest = hashlib.sha256(clean_content.encode("utf-8")).hexdigest()
        now = self._now()
        chunks = self._split_chunks(clean_content)
        with self._connect() as db:
            existing = db.execute(
                "SELECT * FROM knowledge_documents WHERE content_hash = ?", (digest,)
            ).fetchone()
            if existing:
                count = db.execute(
                    "SELECT COUNT(*) FROM knowledge_chunks WHERE document_id = ?",
                    (existing["id"],),
                ).fetchone()[0]
                return {**dict(existing), "metadata": json.loads(existing["metadata"]),
                        "chunk_count": count, "duplicate": True}
            document_id = uuid.uuid4().hex[:16]
            db.execute(
                "INSERT INTO knowledge_documents VALUES (?, ?, ?, ?, ?, ?, ?)",
                (document_id, title, source_uri, digest,
                 json.dumps(metadata or {}, ensure_ascii=False), now, now),
            )
            for index, chunk in enumerate(chunks):
                cursor = db.execute(
                    "INSERT INTO knowledge_chunks(document_id, chunk_index, content) "
                    "VALUES (?, ?, ?)", (document_id, index, chunk),
                )
                if self.fts_available:
                    db.execute(
                        "INSERT INTO knowledge_fts(rowid, content, title, source_uri) "
                        "VALUES (?, ?, ?, ?)",
                        (cursor.lastrowid, chunk, title, source_uri),
                    )
        return {
            "id": document_id, "title": title, "source_uri": source_uri,
            "content_hash": digest, "metadata": metadata or {},
            "created_at": now, "updated_at": now,
            "chunk_count": len(chunks), "duplicate": False,
        }

    def ingest_file(self, path: str | Path) -> dict[str, Any]:
        """Import a user-selected UTF-8 text file (Markdown or plain text)."""
        file_path = Path(path).expanduser().resolve(strict=True)
        if not file_path.is_file():
            raise KnowledgeError("The selected path is not a regular file.")
        if file_path.suffix.lower() not in {".txt", ".md", ".markdown", ".rst"}:
            raise KnowledgeError("Supported file types: .txt, .md, .markdown and .rst.")
        size = file_path.stat().st_size
        if size > self.MAX_DOCUMENT_CHARS * 4:
            raise KnowledgeError("File exceeds the 4 MB import limit.")
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise KnowledgeError("File must be valid UTF-8 text.") from exc
        return self.ingest_text(
            title=file_path.name,
            content=content,
            source_uri=str(file_path),
            metadata={"format": file_path.suffix.lower(), "size_bytes": size},
        )

    def list_documents(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT d.*, COUNT(c.id) AS chunk_count FROM knowledge_documents d "
                "LEFT JOIN knowledge_chunks c ON c.document_id = d.id "
                "GROUP BY d.id ORDER BY d.updated_at DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(item["metadata"])
            result.append(item)
        return result

    def delete_document(self, document_id: str) -> None:
        with self._connect() as db:
            rows = db.execute(
                "SELECT id FROM knowledge_chunks WHERE document_id = ?", (document_id,)
            ).fetchall()
            if not db.execute(
                "SELECT 1 FROM knowledge_documents WHERE id = ?", (document_id,)
            ).fetchone():
                raise KeyError(document_id)
            if self.fts_available:
                db.executemany(
                    "DELETE FROM knowledge_fts WHERE rowid = ?",
                    [(row["id"],) for row in rows],
                )
            db.execute("DELETE FROM knowledge_chunks WHERE document_id = ?", (document_id,))
            db.execute("DELETE FROM knowledge_documents WHERE id = ?", (document_id,))

    def search(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        if not isinstance(query, str) or not query.strip():
            raise KnowledgeError("Search query cannot be empty.")
        terms = list(dict.fromkeys(re.findall(r"[\w-]{2,}", query.lower(), flags=re.UNICODE)))[:12]
        if not terms:
            return []
        safe_limit = max(1, min(limit, 30))
        with self._connect() as db:
            rows: list[sqlite3.Row]
            if self.fts_available:
                expression = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
                try:
                    rows = db.execute(
                        "SELECT c.id, c.document_id, c.chunk_index, c.content, "
                        "d.title, d.source_uri, bm25(knowledge_fts) AS rank "
                        "FROM knowledge_fts JOIN knowledge_chunks c ON c.id = knowledge_fts.rowid "
                        "JOIN knowledge_documents d ON d.id = c.document_id "
                        "WHERE knowledge_fts MATCH ? ORDER BY rank LIMIT ?",
                        (expression, safe_limit),
                    ).fetchall()
                except sqlite3.OperationalError:
                    rows = []
            else:
                rows = []
            if not rows:
                clauses = " OR ".join("c.content LIKE ?" for _ in terms)
                rows = db.execute(
                    "SELECT c.id, c.document_id, c.chunk_index, c.content, "
                    "d.title, d.source_uri, 0.0 AS rank "
                    "FROM knowledge_chunks c JOIN knowledge_documents d "
                    "ON d.id = c.document_id WHERE " + clauses +
                    " ORDER BY d.updated_at DESC LIMIT ?",
                    tuple("%" + term + "%" for term in terms) + (safe_limit,),
                ).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            text = item.pop("content")
            item["excerpt"] = text[:700]
            item["citation"] = {
                "document_id": item["document_id"],
                "title": item["title"],
                "source": item["source_uri"] or f"knowledge://{item['document_id']}",
                "chunk": item["chunk_index"] + 1,
            }
            results.append(item)
        return results


__all__ = ["KnowledgeError", "KnowledgeStore"]
