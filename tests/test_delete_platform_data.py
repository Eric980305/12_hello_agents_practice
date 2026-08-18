from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from expert_platform.backend.app.admin_deletion import (
    AdminDeleteError,
    DeleteSettings,
    DeleteTarget,
    build_plan,
    execute_delete,
    user_scope,
)
from expert_platform.cli.delete_data import (
    build_parser,
    confirmation_text,
    targets_from_args,
)


class FakeQdrant:
    def __init__(self) -> None:
        self.rag = [
            {"id": "chunk-a1", "rag_namespace": "ns-a", "document_id": "doc-same"},
            {"id": "stale-a1", "rag_namespace": "ns-a", "document_id": "doc-same"},
            {"id": "chunk-a2", "rag_namespace": "ns-a", "document_id": "doc-a2"},
            {"id": "chunk-b1", "rag_namespace": "ns-b", "document_id": "doc-b"},
            {"id": "chunk-other", "rag_namespace": "ns-other", "document_id": "doc-same"},
            {
                "id": "chunk-shared",
                "rag_namespace": "pdf_shared_default",
                "document_id": "doc-shared",
            },
        ]
        self.episodic = [
            {"id": "memory-1", "user_id": "user-1"},
            {"id": "stale-memory", "user_id": "user-1"},
            {"id": "memory-2", "user_id": "user-2"},
        ]
        self.fail_delete = False

    def user_rag_namespaces(self, scope: str) -> set[str]:
        prefix = f"kb_{scope}_"
        legacy = f"pdf_{scope}"
        return {
            point["rag_namespace"]
            for point in self.rag
            if point["rag_namespace"].startswith(prefix)
            or point["rag_namespace"] == legacy
        }

    def count_rag(self, namespace: str, document_id: str | None = None) -> int:
        return sum(
            point["rag_namespace"] == namespace
            and (document_id is None or point["document_id"] == document_id)
            for point in self.rag
        )

    def delete_rag(self, namespace: str, document_id: str | None = None) -> None:
        if self.fail_delete:
            raise RuntimeError("qdrant unavailable")
        self.rag = [
            point
            for point in self.rag
            if not (
                point["rag_namespace"] == namespace
                and (document_id is None or point["document_id"] == document_id)
            )
        ]

    def count_episodic(self, user_id: str) -> int:
        return sum(point["user_id"] == user_id for point in self.episodic)

    def delete_episodic(self, user_id: str) -> None:
        if self.fail_delete:
            raise RuntimeError("qdrant unavailable")
        self.episodic = [
            point for point in self.episodic if point["user_id"] != user_id
        ]

    def collection_points(self) -> dict[str, int]:
        return {"rag": len(self.rag), "episodic": len(self.episodic)}


class DeletePlatformDataTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.database = self.root / "practice_memory.db"
        self.knowledge = self.root / "knowledge_base"
        self.reports = self.root / "monthly_personal_reports"
        self.knowledge.mkdir()
        self.reports.mkdir()
        self.settings = DeleteSettings(
            database_path=self.database,
            knowledge_root=self.knowledge,
            reports_root=self.reports,
            rag_collection="rag",
            episodic_collection="episodic",
        )
        self.qdrant = FakeQdrant()
        self.qdrant.rag.append(
            {
                "id": "orphan-vector",
                "rag_namespace": f"kb_{user_scope('user-1')}_orphan",
                "document_id": "orphan-document",
            }
        )
        self._create_schema()
        self._seed()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _create_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE app_users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    password_salt BLOB NOT NULL,
                    password_hash BLOB NOT NULL,
                    password_iterations INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE expert_web_sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                CREATE TABLE rag_knowledge_bases (
                    user_id TEXT NOT NULL,
                    knowledge_base_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    namespace TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, knowledge_base_id),
                    UNIQUE (user_id, name)
                );
                CREATE TABLE rag_documents (
                    namespace TEXT NOT NULL,
                    document_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (namespace, document_id)
                );
                CREATE TABLE rag_chunks (
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
                );
                CREATE TABLE episodic_memories (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    importance REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    expires_at TEXT,
                    metadata_json TEXT NOT NULL
                );
                """
            )

    def _seed(self) -> None:
        timestamp = "2026-08-15T00:00:00+00:00"
        with self._connect() as connection:
            connection.executemany(
                "INSERT INTO app_users VALUES (?, ?, ?, ?, ?, ?)",
                [
                    ("user-1", "alpha", b"s", b"h", 1, timestamp),
                    ("user-2", "beta", b"s", b"h", 1, timestamp),
                ],
            )
            connection.executemany(
                "INSERT INTO expert_web_sessions VALUES (?, ?, ?, ?)",
                [
                    ("session-1", "user-1", timestamp, timestamp),
                    ("session-2", "user-2", timestamp, timestamp),
                ],
            )
            connection.executemany(
                "INSERT INTO rag_knowledge_bases VALUES (?, ?, ?, ?, ?)",
                [
                    ("user-1", "exp-a", "Expert A", "ns-a", timestamp),
                    ("user-1", "exp-b", "Expert B", "ns-b", timestamp),
                    ("user-2", "exp-a", "Other Expert", "ns-other", timestamp),
                    ("__shared__", "default", "Shared", "pdf_shared_default", timestamp),
                ],
            )

            documents = [
                ("ns-a", "doc-same", "a1", "user-1", "exp-a"),
                ("ns-a", "doc-a2", "a2", "user-1", "exp-a"),
                ("ns-b", "doc-b", "b", "user-1", "exp-b"),
                ("ns-other", "doc-same", "other", "user-2", "exp-a"),
                ("pdf_shared_default", "doc-shared", "shared", "shared", "default"),
            ]
            for namespace, document_id, content, owner, expert_id in documents:
                if owner == "shared":
                    folder = self.knowledge / "shared" / "default"
                else:
                    folder = self.knowledge / user_scope(owner) / "bases" / expert_id
                folder.mkdir(parents=True, exist_ok=True)
                source = folder / f"{document_id}.txt"
                source.write_text(content, encoding="utf-8")
                metadata = json.dumps({"source_path": str(source)})
                connection.execute(
                    "INSERT INTO rag_documents VALUES (?, ?, ?, ?, ?)",
                    (namespace, document_id, content, metadata, timestamp),
                )
                connection.execute(
                    "INSERT INTO rag_chunks VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        f"chunk-{content}",
                        namespace,
                        document_id,
                        0,
                        content,
                        "{}",
                    ),
                )
            connection.executemany(
                "INSERT INTO episodic_memories VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    ("memory-1", "user-1", "one", 0.5, timestamp, timestamp, None, "{}"),
                    ("memory-2", "user-2", "two", 0.5, timestamp, timestamp, None, "{}"),
                ],
            )
        report_dir = self.reports / user_scope("user-1")
        report_dir.mkdir(parents=True)
        (report_dir / "report.json").write_text("{}", encoding="utf-8")

    def _count(self, table: str, where: str = "1", parameters: tuple[object, ...] = ()) -> int:
        with self._connect() as connection:
            return int(
                connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE {where}",
                    parameters,
                ).fetchone()[0]
            )

    def test_document_delete_is_scoped_by_owner_expert_and_namespace(self) -> None:
        target = DeleteTarget("document", "user-1", "exp-a", "doc-same")
        plan = build_plan(self.settings, target, self.qdrant)
        self.assertEqual(plan.sqlite_rows["documents"], 1)
        self.assertEqual(plan.qdrant_points["rag"], 2)

        execute_delete(self.settings, target, self.qdrant)

        self.assertEqual(
            self._count(
                "rag_documents",
                "namespace = ? AND document_id = ?",
                ("ns-a", "doc-same"),
            ),
            0,
        )
        self.assertEqual(
            self._count(
                "rag_documents",
                "namespace = ? AND document_id = ?",
                ("ns-other", "doc-same"),
            ),
            1,
        )
        self.assertFalse(
            (self.knowledge / user_scope("user-1") / "bases" / "exp-a" / "doc-same.txt").exists()
        )
        self.assertTrue(
            (self.knowledge / user_scope("user-2") / "bases" / "exp-a" / "doc-same.txt").exists()
        )
        self.assertFalse(any(point["id"] in {"chunk-a1", "stale-a1"} for point in self.qdrant.rag))
        self.assertTrue(any(point["id"] == "chunk-other" for point in self.qdrant.rag))

    def test_expert_delete_removes_documents_but_preserves_history(self) -> None:
        execute_delete(
            self.settings,
            DeleteTarget("expert", "user-1", "exp-a"),
            self.qdrant,
        )

        self.assertEqual(
            self._count(
                "rag_knowledge_bases",
                "user_id = ? AND knowledge_base_id = ?",
                ("user-1", "exp-a"),
            ),
            0,
        )
        self.assertEqual(self._count("rag_documents", "namespace = ?", ("ns-a",)), 0)
        self.assertEqual(self._count("rag_documents", "namespace = ?", ("ns-b",)), 1)
        self.assertEqual(self._count("episodic_memories", "user_id = ?", ("user-1",)), 1)
        self.assertFalse(
            (self.knowledge / user_scope("user-1") / "bases" / "exp-a").exists()
        )
        self.assertFalse(any(point["rag_namespace"] == "ns-a" for point in self.qdrant.rag))

    def test_user_delete_removes_all_user_owned_data(self) -> None:
        execute_delete(
            self.settings,
            DeleteTarget("user", "user-1"),
            self.qdrant,
        )

        user_tables = (
            "app_users",
            "expert_web_sessions",
            "rag_knowledge_bases",
            "episodic_memories",
        )
        for table in user_tables:
            self.assertEqual(self._count(table, "user_id = ?", ("user-1",)), 0)
        self.assertEqual(self._count("rag_documents", "namespace IN ('ns-a', 'ns-b')"), 0)
        self.assertEqual(self._count("rag_documents", "namespace = ?", ("ns-other",)), 1)
        self.assertFalse((self.knowledge / user_scope("user-1")).exists())
        self.assertFalse((self.reports / user_scope("user-1")).exists())
        self.assertFalse(
            any(
                point["rag_namespace"] in {"ns-a", "ns-b"}
                for point in self.qdrant.rag
            )
        )
        self.assertFalse(any(point["id"] == "orphan-vector" for point in self.qdrant.rag))
        self.assertFalse(
            any(point["user_id"] == "user-1" for point in self.qdrant.episodic)
        )
        self.assertEqual(self._count("app_users", "user_id = ?", ("user-2",)), 1)

    def test_shared_expert_and_wrong_owner_are_rejected(self) -> None:
        with self.assertRaises(AdminDeleteError):
            build_plan(
                self.settings,
                DeleteTarget("expert", "user-1", "default"),
                self.qdrant,
            )

    def test_shared_document_can_be_deleted_without_deleting_shared_expert(self) -> None:
        source = self.knowledge / "shared" / "default" / "doc-shared.txt"

        execute_delete(
            self.settings,
            DeleteTarget("document", "__shared__", "default", "doc-shared"),
            self.qdrant,
        )

        self.assertEqual(
            self._count(
                "rag_documents",
                "namespace = ? AND document_id = ?",
                ("pdf_shared_default", "doc-shared"),
            ),
            0,
        )
        self.assertEqual(
            self._count(
                "rag_knowledge_bases",
                "user_id = ? AND knowledge_base_id = ?",
                ("__shared__", "default"),
            ),
            1,
        )
        self.assertFalse(source.exists())
        self.assertFalse(any(point["id"] == "chunk-shared" for point in self.qdrant.rag))
        with self.assertRaises(AdminDeleteError):
            build_plan(
                self.settings,
                DeleteTarget("expert", "user-2", "exp-b"),
                self.qdrant,
            )

    def test_qdrant_failure_rolls_back_sqlite_and_keeps_files(self) -> None:
        self.qdrant.fail_delete = True
        source = self.knowledge / user_scope("user-1") / "bases" / "exp-a" / "doc-same.txt"

        with self.assertRaisesRegex(AdminDeleteError, "SQLite was rolled back"):
            execute_delete(
                self.settings,
                DeleteTarget("document", "user-1", "exp-a", "doc-same"),
                self.qdrant,
            )

        self.assertEqual(
            self._count("rag_documents", "namespace = ? AND document_id = ?", ("ns-a", "doc-same")),
            1,
        )
        self.assertTrue(source.exists())

    def test_cli_expands_multiple_ids_without_crossing_parent_scope(self) -> None:
        parser = build_parser()
        users = targets_from_args(
            parser.parse_args(["user", "--user-id", "user-1", "user-2"])
        )
        experts = targets_from_args(
            parser.parse_args(
                ["expert", "--user-id", "user-1", "--expert-id", "exp-a", "exp-b"]
            )
        )
        documents = targets_from_args(
            parser.parse_args(
                [
                    "document",
                    "--user-id",
                    "user-1",
                    "--expert-id",
                    "exp-a",
                    "--document-id",
                    "doc-same",
                    "doc-a2",
                ]
            )
        )

        self.assertEqual([target.user_id for target in users], ["user-1", "user-2"])
        self.assertEqual([target.expert_id for target in experts], ["exp-a", "exp-b"])
        self.assertEqual(
            [target.document_id for target in documents],
            ["doc-same", "doc-a2"],
        )
        self.assertTrue(all(target.user_id == "user-1" for target in experts))
        self.assertTrue(all(target.expert_id == "exp-a" for target in documents))
        self.assertEqual(confirmation_text(documents), "DELETE 2")

    def test_cli_rejects_duplicate_batch_ids(self) -> None:
        args = build_parser().parse_args(["user", "--user-id", "user-1", "user-1"])
        with self.assertRaises(AdminDeleteError):
            targets_from_args(args)


if __name__ == "__main__":
    unittest.main()
