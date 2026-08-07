"""SQLite source of truth for persistent memory records."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from ..base import MemoryItem

if TYPE_CHECKING:
    from ..rag.document import Document, DocumentChunk


class SQLiteDocumentStore:
    """Persist complete memory records with user-scoped reads and writes."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path).expanduser().resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def add(self, item: MemoryItem) -> str:
        values = self._serialize(item)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO episodic_memories (
                    id, user_id, content, importance, created_at, updated_at,
                    expires_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
        return item.id

    def get(self, memory_id: str, *, user_id: str) -> MemoryItem | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM episodic_memories
                WHERE id = ? AND user_id = ?
                """,
                (memory_id, user_id),
            ).fetchone()
        return self._deserialize(row) if row is not None else None

    def update(self, item: MemoryItem) -> None:
        values = self._serialize(item)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE episodic_memories
                SET user_id = ?, content = ?, importance = ?, created_at = ?,
                    updated_at = ?, expires_at = ?, metadata_json = ?
                WHERE id = ? AND user_id = ?
                """,
                (*values[1:], item.id, item.user_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"memory '{item.id}' was not found.")

    def delete(self, memory_id: str, *, user_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM episodic_memories WHERE id = ? AND user_id = ?",
                (memory_id, user_id),
            )
        return cursor.rowcount == 1

    def list(self, *, user_id: str) -> list[MemoryItem]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM episodic_memories
                WHERE user_id = ?
                ORDER BY created_at ASC
                """,
                (user_id,),
            ).fetchall()
        return [self._deserialize(row) for row in rows]

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS episodic_memories (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    importance REAL NOT NULL CHECK (importance BETWEEN 0 AND 1),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    expires_at TEXT,
                    metadata_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_episodic_user_created
                ON episodic_memories (user_id, created_at)
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _serialize(item: MemoryItem) -> tuple[object, ...]:
        metadata_json = json.dumps(
            item.metadata,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return (
            item.id,
            item.user_id,
            item.content,
            item.importance,
            item.created_at.isoformat(),
            item.updated_at.isoformat(),
            item.expires_at.isoformat() if item.expires_at else None,
            metadata_json,
        )

    @staticmethod
    def _deserialize(row: sqlite3.Row) -> MemoryItem:
        return MemoryItem.model_validate(
            {
                "id": row["id"],
                "user_id": row["user_id"],
                "content": row["content"],
                "memory_type": "episodic",
                "importance": row["importance"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "expires_at": row["expires_at"],
                "metadata": json.loads(row["metadata_json"]),
            }
        )


__all__ = ["SQLiteDocumentStore"]


class SQLiteKnowledgeStore:
    """Persist authoritative RAG source documents and their text chunks."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path).expanduser().resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def replace_document(
        self,
        document: "Document",
        chunks: list["DocumentChunk"],
    ) -> list[str]:
        metadata_json = self._json(document.metadata)
        with self._connect() as connection:
            old_rows = connection.execute(
                """
                SELECT chunk_id FROM rag_chunks
                WHERE namespace = ? AND document_id = ?
                """,
                (document.namespace, document.id),
            ).fetchall()
            old_ids = [row["chunk_id"] for row in old_rows]
            connection.execute(
                "DELETE FROM rag_documents WHERE namespace = ? AND document_id = ?",
                (document.namespace, document.id),
            )
            connection.execute(
                """
                INSERT INTO rag_documents (
                    namespace, document_id, content, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    document.namespace,
                    document.id,
                    document.content,
                    metadata_json,
                    document.created_at.isoformat(),
                ),
            )
            connection.executemany(
                """
                INSERT INTO rag_chunks (
                    chunk_id, namespace, document_id, chunk_index, content,
                    metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        chunk.id,
                        chunk.namespace,
                        chunk.document_id,
                        chunk.index,
                        chunk.content,
                        self._json(chunk.metadata),
                    )
                    for chunk in chunks
                ],
            )
        return old_ids

    def ensure_knowledge_base(
        self,
        *,
        user_id: str,
        knowledge_base_id: str,
        name: str,
        namespace: str,
    ) -> None:
        """Persist one user-visible knowledge-base identity idempotently."""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO rag_knowledge_bases (
                    user_id, knowledge_base_id, name, namespace, created_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (user_id, knowledge_base_id) DO UPDATE SET
                    name = excluded.name,
                    namespace = excluded.namespace
                """,
                (
                    user_id,
                    knowledge_base_id,
                    name,
                    namespace,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def list_knowledge_bases(self, *, user_id: str) -> list[dict[str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT knowledge_base_id, name, namespace
                FROM rag_knowledge_bases
                WHERE user_id = ?
                ORDER BY created_at ASC
                """,
                (user_id,),
            ).fetchall()
        return [
            {
                "id": row["knowledge_base_id"],
                "name": row["name"],
                "namespace": row["namespace"],
            }
            for row in rows
        ]

    def list_accessible_knowledge_bases(
        self,
        *,
        user_id: str,
        shared_owner_id: str,
    ) -> list[dict[str, str]]:
        """List the shared library followed by libraries owned by one user."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT user_id, knowledge_base_id, name, namespace
                FROM rag_knowledge_bases
                WHERE (user_id = ? AND knowledge_base_id = 'default')
                   OR (user_id = ? AND knowledge_base_id <> 'default')
                ORDER BY CASE WHEN user_id = ? THEN 0 ELSE 1 END, created_at ASC
                """,
                (shared_owner_id, user_id, shared_owner_id),
            ).fetchall()
        return [
            {
                "id": row["knowledge_base_id"],
                "name": row["name"],
                "namespace": row["namespace"],
                "owner_user_id": row["user_id"],
            }
            for row in rows
        ]

    def rename_knowledge_base_display_name(
        self,
        *,
        old_name: str,
        new_name: str,
    ) -> int:
        """Rename legacy catalog labels without changing IDs or namespaces."""
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE rag_knowledge_bases
                SET name = ?
                WHERE name = ?
                """,
                (new_name, old_name),
            )
        return cursor.rowcount

    def delete_owned_knowledge_base(
        self,
        *,
        user_id: str,
        knowledge_base_id: str,
    ) -> bool:
        """Delete one private knowledge-base catalog entry owned by the user."""
        if knowledge_base_id == "default":
            raise ValueError("共享知识库不能删除。")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM rag_knowledge_bases
                WHERE user_id = ? AND knowledge_base_id = ?
                """,
                (user_id, knowledge_base_id),
            )
        return cursor.rowcount > 0

    def get_chunk_ids(self, *, namespace: str, document_id: str) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT chunk_id FROM rag_chunks
                WHERE namespace = ? AND document_id = ?
                ORDER BY chunk_index ASC
                """,
                (namespace, document_id),
            ).fetchall()
        return [row["chunk_id"] for row in rows]

    def has_document(self, *, namespace: str, document_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1 FROM rag_documents
                WHERE namespace = ? AND document_id = ?
                LIMIT 1
                """,
                (namespace, document_id),
            ).fetchone()
        return row is not None

    def list_documents(self, *, namespace: str) -> list[dict[str, object]]:
        """List authoritative documents without returning their full source text."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT d.document_id, d.metadata_json, d.created_at,
                       COUNT(c.chunk_id) AS chunk_count
                FROM rag_documents AS d
                LEFT JOIN rag_chunks AS c
                  ON c.namespace = d.namespace
                 AND c.document_id = d.document_id
                WHERE d.namespace = ?
                GROUP BY d.namespace, d.document_id
                ORDER BY d.created_at DESC
                """,
                (namespace,),
            ).fetchall()
        return [self._document_summary(row) for row in rows]

    def get_document(
        self,
        *,
        namespace: str,
        document_id: str,
    ) -> dict[str, object] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT d.document_id, d.metadata_json, d.created_at,
                       COUNT(c.chunk_id) AS chunk_count
                FROM rag_documents AS d
                LEFT JOIN rag_chunks AS c
                  ON c.namespace = d.namespace
                 AND c.document_id = d.document_id
                WHERE d.namespace = ? AND d.document_id = ?
                GROUP BY d.namespace, d.document_id
                """,
                (namespace, document_id),
            ).fetchone()
        return self._document_summary(row) if row is not None else None

    def delete_document(self, *, namespace: str, document_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM rag_documents
                WHERE namespace = ? AND document_id = ?
                """,
                (namespace, document_id),
            )
        return cursor.rowcount > 0

    def get_chunks(
        self,
        chunk_ids: list[str],
        *,
        namespace: str,
    ) -> dict[str, "DocumentChunk"]:
        if not chunk_ids:
            return {}
        placeholders = ",".join("?" for _ in chunk_ids)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM rag_chunks
                WHERE namespace = ? AND chunk_id IN ({placeholders})
                """,
                (namespace, *chunk_ids),
            ).fetchall()
        from ..rag.document import DocumentChunk

        return {
            row["chunk_id"]: DocumentChunk(
                id=row["chunk_id"],
                namespace=row["namespace"],
                document_id=row["document_id"],
                index=row["chunk_index"],
                content=row["content"],
                metadata=json.loads(row["metadata_json"]),
            )
            for row in rows
        }

    def stats(self, *, namespace: str) -> dict[str, int]:
        with self._connect() as connection:
            documents = connection.execute(
                "SELECT COUNT(*) FROM rag_documents WHERE namespace = ?",
                (namespace,),
            ).fetchone()[0]
            chunks = connection.execute(
                "SELECT COUNT(*) FROM rag_chunks WHERE namespace = ?",
                (namespace,),
            ).fetchone()[0]
        return {"documents": int(documents), "chunks": int(chunks)}

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS rag_knowledge_bases (
                    user_id TEXT NOT NULL,
                    knowledge_base_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    namespace TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, knowledge_base_id),
                    UNIQUE (user_id, name),
                    UNIQUE (namespace)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS rag_documents (
                    namespace TEXT NOT NULL,
                    document_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (namespace, document_id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS rag_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    namespace TEXT NOT NULL,
                    document_id TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    FOREIGN KEY (namespace, document_id)
                        REFERENCES rag_documents (namespace, document_id)
                        ON DELETE CASCADE,
                    UNIQUE (namespace, document_id, chunk_index)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_rag_chunks_namespace_document
                ON rag_chunks (namespace, document_id, chunk_index)
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _json(value: dict[str, object]) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _document_summary(row: sqlite3.Row) -> dict[str, object]:
        metadata = json.loads(row["metadata_json"])
        return {
            "document_id": row["document_id"],
            "name": (
                metadata.get("original_name")
                or metadata.get("source_name")
                or row["document_id"]
            ),
            "source_type": metadata.get("source_type", "unknown"),
            "chunk_count": int(row["chunk_count"]),
            "created_at": row["created_at"],
            "metadata": metadata,
        }


__all__.append("SQLiteKnowledgeStore")
