"""Safely delete user-owned expert-platform data across all active stores."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from qdrant_client import QdrantClient, models


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SHARED_OWNER_ID = "__shared__"
SHARED_EXPERT_ID = "default"


class AdminDeleteError(RuntimeError):
    """Raised when a destructive target cannot be proven safe."""


@dataclass(frozen=True)
class DeleteSettings:
    database_path: Path
    knowledge_root: Path
    reports_root: Path
    rag_collection: str
    episodic_collection: str


@dataclass(frozen=True)
class DeleteTarget:
    action: str
    user_id: str
    expert_id: str | None = None
    document_id: str | None = None


@dataclass(frozen=True)
class FilesystemTarget:
    path: str
    kind: str


@dataclass(frozen=True)
class DeletePlan:
    action: str
    user_id: str
    username: str
    expert_id: str | None
    expert_name: str | None
    document_id: str | None
    namespaces: tuple[str, ...]
    sqlite_rows: dict[str, int]
    qdrant_points: dict[str, int]
    filesystem_targets: tuple[FilesystemTarget, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class VectorDeletionGateway(Protocol):
    def user_rag_namespaces(self, scope: str) -> set[str]: ...

    def count_rag(self, namespace: str, document_id: str | None = None) -> int: ...

    def delete_rag(self, namespace: str, document_id: str | None = None) -> None: ...

    def count_episodic(self, user_id: str) -> int: ...

    def delete_episodic(self, user_id: str) -> None: ...

    def collection_points(self) -> dict[str, int]: ...


class QdrantDeletionGateway:
    """Delete only points selected by authoritative payload boundaries."""

    def __init__(
        self,
        *,
        url: str,
        api_key: str | None,
        timeout: float,
        rag_collection: str,
        episodic_collection: str,
    ) -> None:
        self.client = QdrantClient(url=url, api_key=api_key or None, timeout=timeout)
        self.rag_collection = rag_collection
        self.episodic_collection = episodic_collection
        self._collection_cache: dict[str, bool] = {}

    @staticmethod
    def _filter(**matches: str) -> models.Filter:
        return models.Filter(
            must=[
                models.FieldCondition(
                    key=key,
                    match=models.MatchValue(value=value),
                )
                for key, value in matches.items()
            ]
        )

    def _exists(self, collection: str) -> bool:
        if collection not in self._collection_cache:
            self._collection_cache[collection] = self.client.collection_exists(collection)
        return self._collection_cache[collection]

    def _count(self, collection: str, point_filter: models.Filter) -> int:
        if not self._exists(collection):
            return 0
        return int(
            self.client.count(
                collection_name=collection,
                count_filter=point_filter,
                exact=True,
            ).count
        )

    def _delete(self, collection: str, point_filter: models.Filter) -> None:
        if not self._exists(collection):
            return
        self.client.delete(
            collection_name=collection,
            points_selector=point_filter,
            wait=True,
        )

    def user_rag_namespaces(self, scope: str) -> set[str]:
        """Discover stale user namespaces that no longer have a SQLite catalog row."""
        if not self._exists(self.rag_collection):
            return set()
        private_prefix = f"kb_{scope}_"
        legacy_namespace = f"pdf_{scope}"
        namespaces: set[str] = set()
        offset: object | None = None
        while True:
            points, next_offset = self.client.scroll(
                collection_name=self.rag_collection,
                limit=256,
                offset=offset,
                with_payload=["rag_namespace"],
                with_vectors=False,
            )
            for point in points:
                namespace = (point.payload or {}).get("rag_namespace")
                if isinstance(namespace, str) and (
                    namespace.startswith(private_prefix) or namespace == legacy_namespace
                ):
                    namespaces.add(namespace)
            if next_offset is None:
                return namespaces
            offset = next_offset

    def count_rag(self, namespace: str, document_id: str | None = None) -> int:
        matches = {"rag_namespace": namespace}
        if document_id is not None:
            matches["document_id"] = document_id
        return self._count(self.rag_collection, self._filter(**matches))

    def delete_rag(self, namespace: str, document_id: str | None = None) -> None:
        matches = {"rag_namespace": namespace}
        if document_id is not None:
            matches["document_id"] = document_id
        self._delete(self.rag_collection, self._filter(**matches))

    def count_episodic(self, user_id: str) -> int:
        return self._count(
            self.episodic_collection,
            self._filter(user_id=user_id),
        )

    def delete_episodic(self, user_id: str) -> None:
        self._delete(
            self.episodic_collection,
            self._filter(user_id=user_id),
        )

    def collection_points(self) -> dict[str, int]:
        return {
            "rag": int(self.client.get_collection(self.rag_collection).points_count or 0)
            if self._exists(self.rag_collection)
            else 0,
            "episodic": int(self.client.get_collection(self.episodic_collection).points_count or 0)
            if self._exists(self.episodic_collection)
            else 0,
        }


def default_settings() -> DeleteSettings:
    vector_size = os.getenv("QDRANT_VECTOR_SIZE", "1024")
    return DeleteSettings(
        database_path=PROJECT_ROOT / "memory_data" / "practice_memory.db",
        knowledge_root=PROJECT_ROOT / "knowledge_base",
        reports_root=PROJECT_ROOT / "monthly_personal_reports",
        rag_collection=os.getenv(
            "PRACTICE_RAG_QDRANT_COLLECTION",
            f"hello_agents_practice_rag_{vector_size}",
        ),
        episodic_collection=os.getenv(
            "PRACTICE_EPISODIC_QDRANT_COLLECTION",
            f"hello_agents_practice_episodic_{vector_size}",
        ),
    )


def default_qdrant(settings: DeleteSettings) -> QdrantDeletionGateway:
    return QdrantDeletionGateway(
        url=os.getenv("QDRANT_URL", "http://127.0.0.1:6333"),
        api_key=os.getenv("QDRANT_API_KEY") or None,
        timeout=float(os.getenv("QDRANT_TIMEOUT", "30")),
        rag_collection=settings.rag_collection,
        episodic_collection=settings.episodic_collection,
    )


def user_scope(user_id: str) -> str:
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:16]


def _connect(database_path: Path) -> sqlite3.Connection:
    if not database_path.is_file():
        raise AdminDeleteError(f"SQLite database does not exist: {database_path}")
    connection = sqlite3.connect(database_path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _required(value: str | None, name: str) -> str:
    normalized = value.strip() if isinstance(value, str) else ""
    if not normalized or len(normalized) > 128:
        raise AdminDeleteError(f"{name} must contain 1-128 characters.")
    return normalized


def _safe_target(path: Path, root: Path, *, kind: str) -> FilesystemTarget:
    resolved_root = root.expanduser().resolve()
    resolved = path.expanduser().resolve()
    if resolved == resolved_root or not resolved.is_relative_to(resolved_root):
        raise AdminDeleteError(f"unsafe filesystem target: {resolved}")
    return FilesystemTarget(path=str(resolved), kind=kind)


def _account(connection: sqlite3.Connection, user_id: str) -> sqlite3.Row:
    row = connection.execute(
        "SELECT user_id, username FROM app_users WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    if row is None:
        raise AdminDeleteError("user does not exist.")
    return row


def _expert(
    connection: sqlite3.Connection,
    *,
    user_id: str,
    expert_id: str,
) -> sqlite3.Row:
    if user_id == SHARED_OWNER_ID or expert_id == SHARED_EXPERT_ID:
        raise AdminDeleteError("the shared expert is protected and cannot be deleted here.")
    row = connection.execute(
        """
        SELECT user_id, knowledge_base_id, name, namespace
        FROM rag_knowledge_bases
        WHERE user_id = ? AND knowledge_base_id = ?
        """,
        (user_id, expert_id),
    ).fetchone()
    if row is None:
        raise AdminDeleteError("expert does not exist or is not owned by this user.")
    return row


def _document_metadata(
    connection: sqlite3.Connection,
    *,
    namespace: str,
    document_id: str,
) -> sqlite3.Row:
    row = connection.execute(
        """
        SELECT document_id, metadata_json
        FROM rag_documents
        WHERE namespace = ? AND document_id = ?
        """,
        (namespace, document_id),
    ).fetchone()
    if row is None:
        raise AdminDeleteError("document does not exist in the specified expert.")
    return row


def _scalar_count(
    connection: sqlite3.Connection,
    statement: str,
    parameters: tuple[object, ...],
) -> int:
    return int(connection.execute(statement, parameters).fetchone()[0])


def build_plan(
    settings: DeleteSettings,
    target: DeleteTarget,
    qdrant: VectorDeletionGateway,
    *,
    connection: sqlite3.Connection | None = None,
) -> DeletePlan:
    owns_connection = connection is None
    database = connection or _connect(settings.database_path)
    try:
        action = _required(target.action, "action")
        if action not in {"user", "expert", "document"}:
            raise AdminDeleteError("action must be user, expert, or document.")
        user_id = _required(target.user_id, "user_id")
        shared_document = (
            action == "document"
            and user_id == SHARED_OWNER_ID
            and target.expert_id == SHARED_EXPERT_ID
        )
        account = (
            {"user_id": SHARED_OWNER_ID, "username": "系统共享资源"}
            if shared_document
            else _account(database, user_id)
        )
        scope = user_scope(user_id)
        scope_root = settings.knowledge_root / scope
        expert_id: str | None = None
        expert_name: str | None = None
        document_id: str | None = None
        namespaces: tuple[str, ...]
        filesystem_targets: list[FilesystemTarget] = []

        if action == "user":
            rows = database.execute(
                """
                SELECT knowledge_base_id, name, namespace
                FROM rag_knowledge_bases
                WHERE user_id = ?
                ORDER BY created_at
                """,
                (user_id,),
            ).fetchall()
            catalog_namespaces = {str(row["namespace"]) for row in rows}
            orphan_rows = database.execute(
                """
                SELECT DISTINCT namespace FROM rag_documents
                WHERE namespace GLOB ? OR namespace = ?
                """,
                (f"kb_{scope}_*", f"pdf_{scope}"),
            ).fetchall()
            namespaces = tuple(
                sorted(
                    catalog_namespaces
                    | {str(row["namespace"]) for row in orphan_rows}
                    | qdrant.user_rag_namespaces(scope)
                )
            )
            filesystem_targets.extend(
                (
                    _safe_target(scope_root, settings.knowledge_root, kind="tree"),
                    _safe_target(
                        settings.reports_root / scope,
                        settings.reports_root,
                        kind="tree",
                    ),
                )
            )
        else:
            expert_id = _required(target.expert_id, "expert_id")
            if shared_document:
                expert_row = database.execute(
                    """
                    SELECT user_id, knowledge_base_id, name, namespace
                    FROM rag_knowledge_bases
                    WHERE user_id = ? AND knowledge_base_id = ?
                    """,
                    (SHARED_OWNER_ID, SHARED_EXPERT_ID),
                ).fetchone()
                if expert_row is None:
                    raise AdminDeleteError("shared expert does not exist.")
            else:
                expert_row = _expert(
                    database,
                    user_id=user_id,
                    expert_id=expert_id,
                )
            expert_name = str(expert_row["name"])
            namespace = str(expert_row["namespace"])
            namespaces = (namespace,)
            expert_root = (
                settings.knowledge_root / "shared" / SHARED_EXPERT_ID
                if shared_document
                else scope_root / "bases" / expert_id
            )
            if action == "expert":
                filesystem_targets.append(
                    _safe_target(expert_root, settings.knowledge_root, kind="tree")
                )
            else:
                document_id = _required(target.document_id, "document_id")
                document_row = _document_metadata(
                    database,
                    namespace=namespace,
                    document_id=document_id,
                )
                try:
                    metadata = json.loads(str(document_row["metadata_json"]))
                except json.JSONDecodeError as error:
                    raise AdminDeleteError("document metadata_json is invalid.") from error
                source_path = metadata.get("source_path") if isinstance(metadata, dict) else None
                if isinstance(source_path, str) and source_path.strip():
                    filesystem_targets.append(
                        _safe_target(Path(source_path), expert_root, kind="file")
                    )

        namespace_parameters = tuple(namespaces)
        sqlite_rows = {
            "users": 1 if action == "user" else 0,
            "sessions": _scalar_count(
                database,
                "SELECT COUNT(*) FROM expert_web_sessions WHERE user_id = ?",
                (user_id,),
            ) if action == "user" else 0,
            "experts": _scalar_count(
                database,
                "SELECT COUNT(*) FROM rag_knowledge_bases WHERE user_id = ?",
                (user_id,),
            ) if action == "user" else (1 if action == "expert" else 0),
            "documents": sum(
                _scalar_count(
                    database,
                    "SELECT COUNT(*) FROM rag_documents WHERE namespace = ?"
                    + (" AND document_id = ?" if document_id else ""),
                    (namespace, document_id) if document_id else (namespace,),
                )
                for namespace in namespace_parameters
            ),
            "chunks": sum(
                _scalar_count(
                    database,
                    "SELECT COUNT(*) FROM rag_chunks WHERE namespace = ?"
                    + (" AND document_id = ?" if document_id else ""),
                    (namespace, document_id) if document_id else (namespace,),
                )
                for namespace in namespace_parameters
            ),
            "episodic_memories": _scalar_count(
                database,
                "SELECT COUNT(*) FROM episodic_memories WHERE user_id = ?",
                (user_id,),
            ) if action == "user" else 0,
        }
        qdrant_points = {
            "rag": sum(
                qdrant.count_rag(namespace, document_id)
                for namespace in namespace_parameters
            ),
            "episodic": qdrant.count_episodic(user_id) if action == "user" else 0,
        }
        return DeletePlan(
            action=action,
            user_id=user_id,
            username=str(account["username"]),
            expert_id=expert_id,
            expert_name=expert_name,
            document_id=document_id,
            namespaces=namespaces,
            sqlite_rows=sqlite_rows,
            qdrant_points=qdrant_points,
            filesystem_targets=tuple(filesystem_targets),
        )
    finally:
        if owns_connection:
            database.close()


def _delete_sqlite(connection: sqlite3.Connection, plan: DeletePlan) -> None:
    if plan.action == "document":
        namespace = plan.namespaces[0]
        connection.execute(
            "DELETE FROM rag_chunks WHERE namespace = ? AND document_id = ?",
            (namespace, plan.document_id),
        )
        connection.execute(
            "DELETE FROM rag_documents WHERE namespace = ? AND document_id = ?",
            (namespace, plan.document_id),
        )
        return

    for namespace in plan.namespaces:
        connection.execute("DELETE FROM rag_chunks WHERE namespace = ?", (namespace,))
        connection.execute("DELETE FROM rag_documents WHERE namespace = ?", (namespace,))

    if plan.action == "expert":
        connection.execute(
            """
            DELETE FROM rag_knowledge_bases
            WHERE user_id = ? AND knowledge_base_id = ?
            """,
            (plan.user_id, plan.expert_id),
        )
        return

    connection.execute("DELETE FROM rag_knowledge_bases WHERE user_id = ?", (plan.user_id,))
    connection.execute("DELETE FROM episodic_memories WHERE user_id = ?", (plan.user_id,))
    connection.execute("DELETE FROM expert_web_sessions WHERE user_id = ?", (plan.user_id,))
    connection.execute("DELETE FROM app_users WHERE user_id = ?", (plan.user_id,))


def _delete_qdrant(plan: DeletePlan, qdrant: VectorDeletionGateway) -> None:
    for namespace in plan.namespaces:
        qdrant.delete_rag(namespace, plan.document_id)
    if plan.action == "user":
        qdrant.delete_episodic(plan.user_id)


def _delete_files(targets: tuple[FilesystemTarget, ...]) -> None:
    for target in targets:
        path = Path(target.path)
        if target.kind == "file":
            path.unlink(missing_ok=True)
        elif path.is_symlink():
            path.unlink(missing_ok=True)
        elif path.exists():
            shutil.rmtree(path)


def execute_delete(
    settings: DeleteSettings,
    target: DeleteTarget,
    qdrant: VectorDeletionGateway,
) -> DeletePlan:
    """Delete one validated target while keeping SQLite authoritative on failure."""
    connection = _connect(settings.database_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        plan = build_plan(settings, target, qdrant, connection=connection)
        _delete_sqlite(connection, plan)
        try:
            _delete_qdrant(plan, qdrant)
        except Exception as error:
            raise AdminDeleteError(
                "Qdrant deletion failed; SQLite was rolled back and files were kept. "
                "Some derived vectors may already be absent, so fix Qdrant and rerun."
            ) from error
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    try:
        _delete_files(plan.filesystem_targets)
    except OSError as error:
        raise AdminDeleteError(
            "SQLite and Qdrant deletion succeeded, but filesystem cleanup failed."
        ) from error
    return plan
