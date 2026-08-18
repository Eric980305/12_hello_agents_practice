from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .admin_deletion import (
    AdminDeleteError,
    DeletePlan,
    DeleteSettings,
    DeleteTarget,
    QdrantDeletionGateway,
    VectorDeletionGateway,
    build_plan,
    execute_delete,
)

from .config import Settings
from .services import AssistantService, SessionService, utc_now


SHARED_OWNER_ID = "__shared__"
SHARED_EXPERT_ID = "default"


class AdminService:
    """Read global metadata and execute the existing verified deletion workflow."""

    def __init__(
        self,
        settings: Settings,
        assistants: AssistantService,
        sessions: SessionService,
        qdrant: VectorDeletionGateway | None = None,
    ) -> None:
        self.settings = settings
        self.assistants = assistants
        self.sessions = sessions
        self.delete_settings = DeleteSettings(
            database_path=settings.database_path,
            knowledge_root=settings.project_root / "knowledge_base",
            reports_root=settings.project_root / "monthly_personal_reports",
            rag_collection=settings.rag_collection,
            episodic_collection=settings.episodic_collection,
        )
        self.qdrant = qdrant
        self._initialize()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS expert_admin_audit_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actor_user_id TEXT NOT NULL,
                    actor_username TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target_user_id TEXT NOT NULL,
                    target_expert_id TEXT,
                    target_document_id TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )

    @staticmethod
    def _environment(name: str, default: str) -> str:
        import os

        return os.getenv(name, default)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.settings.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.create_function("document_size_bytes", 1, self._document_size)
        return connection

    def _document_size(self, metadata_json: str) -> int:
        try:
            metadata = json.loads(metadata_json)
            source_path = metadata.get("source_path") if isinstance(metadata, dict) else None
            if not isinstance(source_path, str) or not source_path.strip():
                return 0
            knowledge_root = (self.settings.project_root / "knowledge_base").resolve()
            resolved = Path(source_path).expanduser().resolve()
            if not resolved.is_relative_to(knowledge_root) or not resolved.is_file():
                return 0
            return resolved.stat().st_size
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            return 0

    def _qdrant(self) -> VectorDeletionGateway:
        if self.qdrant is None:
            self.qdrant = QdrantDeletionGateway(
                url=self._environment("QDRANT_URL", "http://127.0.0.1:6333"),
                api_key=self._environment("QDRANT_API_KEY", "") or None,
                timeout=float(self._environment("QDRANT_TIMEOUT", "30")),
                rag_collection=self.settings.rag_collection,
                episodic_collection=self.settings.episodic_collection,
            )
        return self.qdrant

    @staticmethod
    def _page(limit: int, offset: int) -> tuple[int, int]:
        return min(max(limit, 1), 100), max(offset, 0)

    @staticmethod
    def _like(query: str) -> str:
        return f"%{query.strip()}%"

    def overview(self) -> dict[str, Any]:
        with self._connect() as connection:
            counts = {
                "users": self._count(connection, "app_users"),
                "experts": self._count(connection, "rag_knowledge_bases"),
                "documents": self._count(connection, "rag_documents"),
                "chunks": self._count(connection, "rag_chunks"),
            }
        try:
            points = self._qdrant().collection_points()
            vector_store: dict[str, Any] = {
                "status": "available",
                "ragPoints": points["rag"],
                "episodicPoints": points["episodic"],
            }
        except Exception:
            vector_store = {
                "status": "unavailable",
                "ragPoints": None,
                "episodicPoints": None,
            }
        return {"counts": counts, "vectorStore": vector_store}

    @staticmethod
    def _count(connection: sqlite3.Connection, table: str) -> int:
        return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    def users(self, query: str, limit: int, offset: int) -> dict[str, Any]:
        limit, offset = self._page(limit, offset)
        like = self._like(query)
        with self._connect() as connection:
            total = int(
                connection.execute(
                    "SELECT COUNT(*) FROM app_users WHERE username LIKE ? OR user_id LIKE ?",
                    (like, like),
                ).fetchone()[0]
            )
            rows = connection.execute(
                """
                SELECT u.user_id, u.username, u.created_at,
                       (SELECT COUNT(*) FROM rag_knowledge_bases kb
                        WHERE kb.user_id = u.user_id) AS expert_count,
                       (SELECT COUNT(*) FROM rag_documents d
                        JOIN rag_knowledge_bases kb ON kb.namespace = d.namespace
                        WHERE kb.user_id = u.user_id) AS document_count,
                       (SELECT COUNT(*) FROM expert_web_sessions s
                        WHERE s.user_id = u.user_id) AS session_count,
                       COALESCE((
                           SELECT SUM(document_size_bytes(d.metadata_json))
                           FROM rag_documents d
                           JOIN rag_knowledge_bases kb ON kb.namespace = d.namespace
                           WHERE kb.user_id = u.user_id
                       ), 0) AS disk_bytes
                FROM app_users u
                WHERE u.username LIKE ? OR u.user_id LIKE ?
                ORDER BY disk_bytes DESC, u.created_at DESC, u.user_id ASC
                LIMIT ? OFFSET ?
                """,
                (like, like, limit, offset),
            ).fetchall()
        return {
            "items": [
                {
                    "id": row["user_id"],
                    "username": row["username"],
                    "expertCount": int(row["expert_count"]),
                    "documentCount": int(row["document_count"]),
                    "activeSessions": int(row["session_count"]),
                    "diskBytes": int(row["disk_bytes"]),
                    "createdAt": row["created_at"],
                    "isAdmin": self.sessions.is_admin(
                        {"user_id": row["user_id"], "username": row["username"]}
                    ),
                }
                for row in rows
            ],
            "total": total,
        }

    def experts(
        self,
        query: str,
        user_id: str,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        limit, offset = self._page(limit, offset)
        like = self._like(query)
        owner_filter = user_id.strip()
        where = "(kb.name LIKE ? OR kb.knowledge_base_id LIKE ? OR kb.namespace LIKE ?)"
        parameters: list[object] = [like, like, like]
        if owner_filter:
            where += " AND kb.user_id = ?"
            parameters.append(owner_filter)
        with self._connect() as connection:
            total = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM rag_knowledge_bases kb WHERE {where}",
                    tuple(parameters),
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""
                SELECT kb.user_id, kb.knowledge_base_id, kb.name, kb.namespace,
                       kb.created_at, u.username,
                       (SELECT COUNT(*) FROM rag_documents d
                        WHERE d.namespace = kb.namespace) AS document_count,
                       (SELECT COUNT(*) FROM rag_chunks c
                        WHERE c.namespace = kb.namespace) AS chunk_count,
                       COALESCE((
                           SELECT SUM(document_size_bytes(d.metadata_json))
                           FROM rag_documents d
                           WHERE d.namespace = kb.namespace
                       ), 0) AS disk_bytes
                FROM rag_knowledge_bases kb
                LEFT JOIN app_users u ON u.user_id = kb.user_id
                WHERE {where}
                ORDER BY disk_bytes DESC, kb.created_at DESC, kb.knowledge_base_id ASC
                LIMIT ? OFFSET ?
                """,
                (*parameters, limit, offset),
            ).fetchall()
        return {
            "items": [
                {
                    "id": row["knowledge_base_id"],
                    "name": row["name"],
                    "ownerId": row["user_id"],
                    "ownerName": row["username"] or "系统共享资源",
                    "namespace": row["namespace"],
                    "documentCount": int(row["document_count"]),
                    "chunkCount": int(row["chunk_count"]),
                    "diskBytes": int(row["disk_bytes"]),
                    "createdAt": row["created_at"],
                    "deletable": not (
                        row["user_id"] == SHARED_OWNER_ID
                        or row["knowledge_base_id"] == SHARED_EXPERT_ID
                    ),
                }
                for row in rows
            ],
            "total": total,
        }

    def documents(
        self,
        query: str,
        user_id: str,
        expert_id: str,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        limit, offset = self._page(limit, offset)
        like = self._like(query)
        where = "(d.document_id LIKE ? OR d.metadata_json LIKE ?)"
        parameters: list[object] = [like, like]
        if user_id.strip():
            where += " AND kb.user_id = ?"
            parameters.append(user_id.strip())
        if expert_id.strip():
            where += " AND kb.knowledge_base_id = ?"
            parameters.append(expert_id.strip())
        with self._connect() as connection:
            total = int(
                connection.execute(
                    f"""
                    SELECT COUNT(*) FROM rag_documents d
                    JOIN rag_knowledge_bases kb ON kb.namespace = d.namespace
                    WHERE {where}
                    """,
                    tuple(parameters),
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""
                SELECT d.document_id, d.metadata_json, d.created_at,
                       kb.user_id, kb.knowledge_base_id, kb.name AS expert_name,
                       u.username,
                       (SELECT COUNT(*) FROM rag_chunks c
                        WHERE c.namespace = d.namespace
                          AND c.document_id = d.document_id) AS chunk_count,
                       document_size_bytes(d.metadata_json) AS disk_bytes
                FROM rag_documents d
                JOIN rag_knowledge_bases kb ON kb.namespace = d.namespace
                LEFT JOIN app_users u ON u.user_id = kb.user_id
                WHERE {where}
                ORDER BY disk_bytes DESC, d.created_at DESC, d.document_id ASC
                LIMIT ? OFFSET ?
                """,
                (*parameters, limit, offset),
            ).fetchall()
        return {
            "items": [self._document_payload(row) for row in rows],
            "total": total,
        }

    @staticmethod
    def _document_payload(row: sqlite3.Row) -> dict[str, Any]:
        try:
            metadata = json.loads(str(row["metadata_json"]))
        except (json.JSONDecodeError, TypeError):
            metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}
        return {
            "id": row["document_id"],
            "fileName": metadata.get("original_name")
            or metadata.get("source_name")
            or row["document_id"],
            "sourceType": metadata.get("source_type") or "unknown",
            "ownerId": row["user_id"],
            "ownerName": row["username"] or "系统共享资源",
            "expertId": row["knowledge_base_id"],
            "expertName": row["expert_name"],
            "chunkCount": int(row["chunk_count"]),
            "diskBytes": int(row["disk_bytes"]),
            "createdAt": row["created_at"],
        }

    def preview(
        self,
        target: DeleteTarget,
        *,
        actor_user_id: str,
    ) -> dict[str, Any]:
        plan = build_plan(self.delete_settings, target, self._qdrant())
        self._assert_allowed(plan, actor_user_id=actor_user_id)
        return {
            "plan": self._plan_payload(plan),
            "confirmationText": self._confirmation_text(target),
        }

    def execute(
        self,
        target: DeleteTarget,
        *,
        confirmation: str,
        actor_user_id: str,
        actor_username: str,
    ) -> dict[str, Any]:
        expected = self._confirmation_text(target)
        if confirmation != expected:
            raise AdminDeleteError("confirmation must exactly match the target ID.")
        preview = self.preview(target, actor_user_id=actor_user_id)
        deleted = execute_delete(self.delete_settings, target, self._qdrant())
        if target.user_id == SHARED_OWNER_ID:
            self.assistants.discard_all()
        else:
            self.assistants.discard_user(target.user_id)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO expert_admin_audit_events(
                    actor_user_id, actor_username, action, target_user_id,
                    target_expert_id, target_document_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    actor_user_id,
                    actor_username,
                    target.action,
                    target.user_id,
                    target.expert_id,
                    target.document_id,
                    utc_now().isoformat(),
                ),
            )
        return {"deleted": self._plan_payload(deleted), "preview": preview["plan"]}

    def _assert_allowed(self, plan: DeletePlan, *, actor_user_id: str) -> None:
        if plan.action == "user" and plan.user_id == actor_user_id:
            raise AdminDeleteError("administrators cannot delete their own active account.")
        if plan.action == "user" and self.sessions.is_admin(
            {"user_id": plan.user_id, "username": plan.username}
        ):
            raise AdminDeleteError("administrator accounts are protected.")

    @staticmethod
    def _confirmation_text(target: DeleteTarget) -> str:
        return target.document_id or target.expert_id or target.user_id

    @staticmethod
    def _plan_payload(plan: DeletePlan) -> dict[str, Any]:
        return {
            "action": plan.action,
            "userId": plan.user_id,
            "username": plan.username,
            "expertId": plan.expert_id,
            "expertName": plan.expert_name,
            "documentId": plan.document_id,
            "namespaces": list(plan.namespaces),
            "sqliteRows": plan.sqlite_rows,
            "qdrantPoints": plan.qdrant_points,
            "filesystemTargets": [
                {"path": target.path, "kind": target.kind}
                for target in plan.filesystem_targets
            ],
        }


__all__ = ["AdminService"]
