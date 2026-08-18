from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from expert_platform.backend.app.config import Settings
from expert_platform.backend.app.main import create_app
from expert_platform.backend.app.admin_deletion import user_scope


class FakeAdminQdrant:
    def __init__(self) -> None:
        self.rag: list[dict[str, str]] = []
        self.episodic: list[dict[str, str]] = []
        self.fail_delete = False

    def user_rag_namespaces(self, scope: str) -> set[str]:
        prefix = f"kb_{scope}_"
        return {
            point["rag_namespace"]
            for point in self.rag
            if point["rag_namespace"].startswith(prefix)
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
        self.episodic = [point for point in self.episodic if point["user_id"] != user_id]

    def collection_points(self) -> dict[str, int]:
        return {"rag": len(self.rag), "episodic": len(self.episodic)}


class FakeAssistant:
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        self.session_id = f"session-{user_id}"
        self.current_knowledge_base_id = "default"
        self.knowledge_bases = {
            "default": {"id": "default", "name": "共享专家库", "owner_user_id": "__shared__"}
        }
        self.documents: dict[str, list[dict[str, object]]] = {"default": []}
        self.conversations: list[dict[str, str]] = []

    def list_knowledge_bases(self) -> list[dict[str, str]]:
        return list(self.knowledge_bases.values())

    def create_knowledge_base(self, name: str) -> dict[str, str]:
        normalized = name.strip()
        if any(item["name"].casefold() == normalized.casefold() for item in self.knowledge_bases.values()):
            raise ValueError("专家名称已存在。")
        expert_id = f"private-{len(self.knowledge_bases)}"
        self.knowledge_bases[expert_id] = {
            "id": expert_id,
            "name": normalized,
            "owner_user_id": self.user_id,
        }
        self.documents[expert_id] = []
        self.current_knowledge_base_id = expert_id
        return {"id": expert_id, "name": normalized}

    def delete_knowledge_base(self, knowledge_base_id: str, *, confirmed: bool) -> dict[str, object]:
        if not confirmed:
            raise ValueError("删除专家前必须确认。")
        if knowledge_base_id == "default":
            raise ValueError("共享专家库不能删除。")
        item = self.knowledge_bases.pop(knowledge_base_id)
        count = len(self.documents.pop(knowledge_base_id))
        return {"id": item["id"], "name": item["name"], "documents_deleted": count}

    def select_knowledge_base(self, knowledge_base_id: str) -> str:
        self.current_knowledge_base_id = knowledge_base_id
        return self.knowledge_bases[knowledge_base_id]["name"]

    def list_documents(
        self,
        knowledge_base_id: str | None = None,
        *,
        query: str = "",
        include_all: bool = False,
    ) -> list[dict[str, object]]:
        expert_ids = list(self.documents) if include_all else [knowledge_base_id or "default"]
        result: list[dict[str, object]] = []
        for expert_id in expert_ids:
            for item in self.documents[expert_id]:
                if query.casefold() not in str(item["name"]).casefold():
                    continue
                result.append(
                    {
                        **item,
                        "knowledge_base_id": expert_id,
                        "knowledge_base_name": self.knowledge_bases[expert_id]["name"],
                    }
                )
        return result

    def load_document(self, file_path: str | Path, *, knowledge_base_id: str | None = None) -> dict[str, object]:
        source = Path(file_path)
        expert_id = knowledge_base_id or "default"
        document = {
            "document_id": f"doc-{source.name}",
            "name": source.name,
            "source_type": source.suffix.lstrip("."),
            "created_at": "2026-08-12T12:00:00+00:00",
        }
        self.documents[expert_id].append(document)
        return {
            "success": True,
            "duplicate": False,
            "message": "文件已加载。",
            "document": source.name,
            "document_id": document["document_id"],
        }

    def delete_document(
        self,
        document_id: str,
        *,
        knowledge_base_id: str | None = None,
        confirmed: bool = False,
    ) -> dict[str, object]:
        if not confirmed:
            raise ValueError("删除文档前必须明确确认。")
        expert_id = knowledge_base_id or "default"
        document = next(item for item in self.documents[expert_id] if item["document_id"] == document_id)
        self.documents[expert_id].remove(document)
        return document

    def ask(
        self,
        question: str,
        *,
        knowledge_base_id: str | None = None,
        use_advanced_search: bool = False,
    ) -> str:
        expert_id = knowledge_base_id or "default"
        answer = f"基于资料回答：{question}\n\n来源：\n[S1] fixture.md"
        self.conversations.append(
            {
                "knowledge_base_id": expert_id,
                "question": question,
                "answer": answer,
                "created_at": "2026-08-12T12:01:00+00:00",
            }
        )
        return answer

    def get_stats(self) -> dict[str, object]:
        return {
            "会话时长": "60 秒",
            "加载文档": sum(len(items) for items in self.documents.values()),
            "提问次数": len(self.conversations),
            "当前专家": self.knowledge_bases[self.current_knowledge_base_id]["name"],
            "当前文档": "未加载",
        }

    def generate_monthly_personal_report(self, *, save_to_file: bool = True) -> dict[str, object]:
        if not self.conversations:
            raise ValueError("最近 30 天还没有可总结的完整专家问答。")
        return {
            "period": {
                "startTime": "2026-07-14T12:00:00+00:00",
                "endTime": "2026-08-13T12:00:00+00:00",
                "days": 30,
            },
            "generatedAt": "2026-08-13T12:00:00+00:00",
            "reportMonth": "2026-08",
            "metrics": {
                "conversationCount": len(self.conversations),
                "conversationsUsed": len(self.conversations),
                "expertsUsed": 1,
            },
            "summary": "## 专家：共享专家库\n\n关键结论",
            "expertSummaries": [],
        }


class ApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        settings = Settings(
            project_root=root,
            database_path=root / "memory.db",
            temporary_root=root / "uploads",
            frontend_dist=root / "dist",
            rag_collection="rag-test",
            episodic_collection="episodic-test",
        )
        self.settings = settings
        self.admin_qdrant = FakeAdminQdrant()
        self.app = create_app(
            settings,
            assistant_factory=FakeAssistant,
            admin_qdrant=self.admin_qdrant,
        )
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.client.close()
        self.temporary.cleanup()

    def register_and_login(self, username: str = "junmin") -> None:
        register = self.client.post(
            "/api/auth/register",
            json={"username": username, "password": "secret12"},
        )
        self.assertEqual(register.status_code, 201)
        login = self.client.post(
            "/api/auth/login",
            json={"username": username, "password": "secret12"},
        )
        self.assertEqual(login.status_code, 200)
        self.assertIn("HttpOnly", login.headers["set-cookie"])

    def session_count(self) -> int:
        with sqlite3.connect(self.settings.database_path) as connection:
            return int(connection.execute("SELECT COUNT(*) FROM expert_web_sessions").fetchone()[0])

    def test_authentication_bootstrap_and_logout(self) -> None:
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        self.register_and_login()
        bootstrap = self.client.get("/api/bootstrap")
        self.assertEqual(bootstrap.status_code, 200)
        payload = bootstrap.json()
        self.assertEqual(payload["user"]["username"], "junmin")
        self.assertEqual(payload["experts"][0]["id"], "__all__")
        self.assertEqual(payload["experts"][1]["name"], "共享专家库")
        self.assertNotIn("stats", payload)
        self.assertEqual(self.client.get("/api/stats").status_code, 404)
        self.assertEqual(self.client.post("/api/reports/session").status_code, 404)
        self.assertEqual(self.client.post("/api/auth/logout").status_code, 204)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_same_account_sessions_keep_independent_conversations(self) -> None:
        self.register_and_login()
        second_client = TestClient(self.app)
        try:
            second_login = second_client.post(
                "/api/auth/login",
                json={"username": "junmin", "password": "secret12"},
            )
            self.assertEqual(second_login.status_code, 200)
            first_chat = self.client.post(
                "/api/chat",
                json={
                    "expertId": "default",
                    "question": "第一会话的问题",
                    "advanced": False,
                },
            )
            self.assertEqual(first_chat.status_code, 200)
            self.assertEqual(
                len(self.client.get("/api/chat/history").json()["items"]),
                2,
            )
            self.assertEqual(
                second_client.get("/api/chat/history").json()["items"],
                [],
            )
        finally:
            second_client.close()

    def test_relogin_replaces_only_the_current_browser_session(self) -> None:
        self.register_and_login()
        second_client = TestClient(self.app)
        try:
            self.assertEqual(
                second_client.post(
                    "/api/auth/login",
                    json={"username": "junmin", "password": "secret12"},
                ).status_code,
                200,
            )
            self.assertEqual(self.session_count(), 2)

            self.assertEqual(
                self.client.post(
                    "/api/auth/login",
                    json={"username": "junmin", "password": "secret12"},
                ).status_code,
                200,
            )

            self.assertEqual(self.session_count(), 2)
            self.assertEqual(self.client.get("/api/auth/me").status_code, 200)
            self.assertEqual(second_client.get("/api/auth/me").status_code, 200)
        finally:
            second_client.close()

    def test_expired_session_is_deleted_when_resolved(self) -> None:
        self.register_and_login()
        token = self.client.cookies.get("expert_session")
        self.assertIsNotNone(token)
        token_hash = hashlib.sha256(str(token).encode("utf-8")).hexdigest()
        with sqlite3.connect(self.settings.database_path) as connection:
            connection.execute(
                "UPDATE expert_web_sessions SET expires_at = ? WHERE token_hash = ?",
                ("2020-01-01T00:00:00+00:00", token_hash),
            )

        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        self.assertEqual(self.session_count(), 0)

    def test_logout_clears_cookie_when_session_record_is_missing(self) -> None:
        self.register_and_login()
        with sqlite3.connect(self.settings.database_path) as connection:
            connection.execute("DELETE FROM expert_web_sessions")

        self.assertEqual(self.client.post("/api/auth/logout").status_code, 204)
        self.assertIsNone(self.client.cookies.get("expert_session"))

    def test_login_rate_limit_blocks_repeated_password_guesses(self) -> None:
        self.assertEqual(
            self.client.post(
                "/api/auth/register",
                json={"username": "limited", "password": "secret12"},
            ).status_code,
            201,
        )
        for _ in range(self.settings.login_attempt_limit):
            self.assertEqual(
                self.client.post(
                    "/api/auth/login",
                    json={"username": "limited", "password": "wrong-password"},
                ).status_code,
                401,
            )
        blocked = self.client.post(
            "/api/auth/login",
            json={"username": "limited", "password": "secret12"},
        )
        self.assertEqual(blocked.status_code, 429)
        self.assertIn("Retry-After", blocked.headers)

    def test_startup_removes_expired_sessions_and_creates_expiry_index(self) -> None:
        self.register_and_login()
        with sqlite3.connect(self.settings.database_path) as connection:
            connection.execute(
                """
                INSERT INTO expert_web_sessions(token_hash, user_id, created_at, expires_at)
                SELECT ?, user_id, ?, ? FROM app_users LIMIT 1
                """,
                (
                    "expired-token-hash",
                    "2020-01-01T00:00:00+00:00",
                    "2020-01-02T00:00:00+00:00",
                ),
            )
            connection.execute(
                """
                INSERT INTO expert_web_sessions(token_hash, user_id, created_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    "orphaned-token-hash",
                    "missing-user",
                    "2026-08-16T00:00:00+00:00",
                    "2099-08-16T00:00:00+00:00",
                ),
            )

        create_app(self.settings, assistant_factory=FakeAssistant)

        with sqlite3.connect(self.settings.database_path) as connection:
            invalid = connection.execute(
                "SELECT 1 FROM expert_web_sessions WHERE token_hash IN (?, ?)",
                ("expired-token-hash", "orphaned-token-hash"),
            ).fetchone()
            index = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = ?",
                ("idx_expert_web_sessions_expires",),
            ).fetchone()
        self.assertIsNone(invalid)
        self.assertIsNotNone(index)
        self.assertEqual(self.session_count(), 1)

    def test_expert_document_chat_and_report_flow(self) -> None:
        self.register_and_login()
        created = self.client.post("/api/experts", json={"name": "法律专家"})
        self.assertEqual(created.status_code, 201)
        expert_id = created.json()["item"]["id"]

        upload = self.client.post(
            "/api/documents",
            data={"expert_id": expert_id},
            files={"file": ("fixture.md", b"authoritative source", "text/markdown")},
        )
        self.assertEqual(upload.status_code, 201)
        self.assertEqual(upload.json()["items"][0]["fileName"], "fixture.md")

        chat = self.client.post(
            "/api/chat",
            json={"expertId": expert_id, "question": "合同有哪些要求？", "advanced": True},
        )
        self.assertEqual(chat.status_code, 200)
        self.assertIn("[S1]", chat.json()["message"]["content"])
        self.assertEqual(len(self.client.get("/api/chat/history").json()["items"]), 2)
        report = self.client.post("/api/reports/monthly")
        self.assertEqual(report.status_code, 200)
        self.assertEqual(report.json()["report"]["metrics"]["conversationCount"], 1)
        self.assertNotIn("conversations", report.json()["report"])

        document_id = upload.json()["items"][0]["id"]
        self.assertEqual(
            self.client.delete(
                f"/api/documents/{document_id}",
                params={"expert_id": expert_id, "confirmed": "true"},
            ).status_code,
            204,
        )
        deleted = self.client.request(
            "DELETE",
            f"/api/experts/{expert_id}",
            json={"confirmed": True},
        )
        self.assertEqual(deleted.status_code, 200)

    def test_expert_documents_are_paginated_after_filtering(self) -> None:
        self.register_and_login()
        created = self.client.post("/api/experts", json={"name": "分页专家"})
        expert_id = created.json()["item"]["id"]
        for index in range(12):
            upload = self.client.post(
                "/api/documents",
                data={"expert_id": expert_id},
                files={"file": (f"page-{index}.md", b"source", "text/markdown")},
            )
            self.assertEqual(upload.status_code, 201)

        first = self.client.get(
            "/api/documents",
            params={"expert_id": expert_id},
        )
        second = self.client.get(
            "/api/documents",
            params={"expert_id": expert_id, "offset": 10},
        )
        filtered = self.client.get(
            "/api/documents",
            params={"expert_id": expert_id, "query": "page-1", "limit": 10, "offset": 0},
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["total"], 12)
        self.assertEqual(len(first.json()["items"]), 10)
        self.assertEqual(second.json()["total"], 12)
        self.assertEqual(len(second.json()["items"]), 2)
        self.assertEqual(filtered.json()["total"], 3)
        self.assertEqual(len(filtered.json()["items"]), 3)

    def test_aggregate_is_read_only_and_confirmation_is_required(self) -> None:
        self.register_and_login()
        self.assertEqual(
            self.client.post(
                "/api/chat",
                json={"expertId": "__all__", "question": "问题", "advanced": False},
            ).status_code,
            400,
        )

    def test_admin_authorization_lists_and_verified_user_deletion(self) -> None:
        self.register_and_login("ordinary")
        self.assertEqual(self.client.get("/api/admin/users").status_code, 403)

        admin_client = TestClient(self.app)
        try:
            self.assertEqual(
                admin_client.post(
                    "/api/auth/register",
                    json={"username": "admin", "password": "secret12"},
                ).status_code,
                201,
            )
            self.assertEqual(
                admin_client.post(
                    "/api/auth/login",
                    json={"username": "admin", "password": "secret12"},
                ).status_code,
                200,
            )
            self.assertEqual(admin_client.get("/api/admin/users").status_code, 403)
            self.app.state.sessions.grant_admin("admin")
            self.assertTrue(admin_client.get("/api/auth/me").json()["user"]["isAdmin"])
            self.assertEqual(
                admin_client.post(
                    "/api/admin/deletions/preview",
                    json={"action": "user", "userId": "missing"},
                ).status_code,
                403,
            )

            victim = admin_client.post(
                "/api/auth/register",
                json={"username": "victim", "password": "secret12"},
            ).json()["user"]
            victim_id = victim["id"]
            scope = user_scope(victim_id)
            namespace = f"kb_{scope}_research"
            source_dir = self.settings.project_root / "knowledge_base" / scope / "bases" / "research"
            source_dir.mkdir(parents=True)
            source = source_dir / "source.md"
            source.write_text("evidence", encoding="utf-8")
            larger_source = source_dir / "larger-source.md"
            larger_source.write_bytes(b"x" * 2048)
            timestamp = "2026-08-17T00:00:00+00:00"

            with sqlite3.connect(self.settings.database_path) as connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS rag_knowledge_bases (
                        user_id TEXT NOT NULL,
                        knowledge_base_id TEXT NOT NULL,
                        name TEXT NOT NULL,
                        namespace TEXT NOT NULL UNIQUE,
                        created_at TEXT NOT NULL,
                        PRIMARY KEY (user_id, knowledge_base_id),
                        UNIQUE (user_id, name)
                    );
                    CREATE TABLE IF NOT EXISTS rag_documents (
                        namespace TEXT NOT NULL,
                        document_id TEXT NOT NULL,
                        content TEXT NOT NULL,
                        metadata_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        PRIMARY KEY (namespace, document_id)
                    );
                    CREATE TABLE IF NOT EXISTS rag_chunks (
                        chunk_id TEXT PRIMARY KEY,
                        namespace TEXT NOT NULL,
                        document_id TEXT NOT NULL,
                        chunk_index INTEGER NOT NULL,
                        content TEXT NOT NULL,
                        metadata_json TEXT NOT NULL,
                        FOREIGN KEY (namespace, document_id)
                            REFERENCES rag_documents (namespace, document_id) ON DELETE CASCADE
                    );
                    CREATE TABLE IF NOT EXISTS episodic_memories (
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
                connection.execute(
                    "INSERT INTO rag_knowledge_bases VALUES (?, ?, ?, ?, ?)",
                    (victim_id, "research", "Research", namespace, timestamp),
                )
                connection.execute(
                    "INSERT INTO rag_documents VALUES (?, ?, ?, ?, ?)",
                    (
                        namespace,
                        "doc-1",
                        "evidence",
                        json.dumps(
                            {
                                "source_path": str(source),
                                "original_name": "source.md",
                                "source_type": "md",
                            }
                        ),
                        timestamp,
                    ),
                )
                connection.execute(
                    "INSERT INTO rag_documents VALUES (?, ?, ?, ?, ?)",
                    (
                        namespace,
                        "doc-2",
                        "larger evidence",
                        json.dumps(
                            {
                                "source_path": str(larger_source),
                                "original_name": "larger-source.md",
                                "source_type": "md",
                            }
                        ),
                        timestamp,
                    ),
                )
                connection.execute(
                    "INSERT INTO rag_chunks VALUES (?, ?, ?, ?, ?, ?)",
                    ("chunk-1", namespace, "doc-1", 0, "evidence", "{}"),
                )
                connection.execute(
                    "INSERT INTO episodic_memories VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    ("memory-1", victim_id, "answer", 0.5, timestamp, timestamp, None, "{}"),
                )
            self.admin_qdrant.rag.append(
                {"id": "chunk-1", "rag_namespace": namespace, "document_id": "doc-1"}
            )
            self.admin_qdrant.episodic.append({"id": "memory-1", "user_id": victim_id})

            overview = admin_client.get("/api/admin/overview")
            self.assertEqual(overview.status_code, 200)
            self.assertEqual(overview.json()["counts"]["documents"], 2)
            users = admin_client.get("/api/admin/users", params={"query": "victim"}).json()
            self.assertEqual(users["total"], 1)
            self.assertEqual(users["items"][0]["documentCount"], 2)
            self.assertEqual(users["items"][0]["diskBytes"], 2056)
            experts = admin_client.get("/api/admin/experts").json()
            self.assertEqual(experts["total"], 1)
            self.assertEqual(experts["items"][0]["diskBytes"], 2056)
            documents = admin_client.get("/api/admin/documents").json()
            self.assertEqual(documents["total"], 2)
            self.assertEqual(
                [(item["id"], item["diskBytes"]) for item in documents["items"]],
                [("doc-2", 2048), ("doc-1", 8)],
            )

            target = {"action": "user", "userId": victim_id}
            origin = {"Origin": "http://testserver"}
            preview = admin_client.post(
                "/api/admin/deletions/preview", json=target, headers=origin
            )
            self.assertEqual(preview.status_code, 200)
            self.assertEqual(preview.json()["plan"]["qdrantPoints"]["rag"], 1)
            self.assertEqual(
                admin_client.post(
                    "/api/admin/deletions/execute",
                    json={**target, "confirmation": "wrong"},
                    headers=origin,
                ).status_code,
                400,
            )
            deleted = admin_client.post(
                "/api/admin/deletions/execute",
                json={**target, "confirmation": victim_id},
                headers=origin,
            )
            self.assertEqual(deleted.status_code, 200)
            with sqlite3.connect(self.settings.database_path) as connection:
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM app_users WHERE user_id = ?",
                        (victim_id,),
                    ).fetchone()[0],
                    0,
                )
                audit = connection.execute(
                    """
                    SELECT actor_username, action, target_user_id
                    FROM expert_admin_audit_events
                    ORDER BY event_id DESC LIMIT 1
                    """
                ).fetchone()
                self.assertEqual(audit, ("admin", "user", victim_id))
            self.assertFalse(source_dir.parent.parent.exists())
            self.assertEqual(self.admin_qdrant.rag, [])
            self.assertEqual(self.admin_qdrant.episodic, [])

            admin_id = admin_client.get("/api/auth/me").json()["user"]["id"]
            self.assertEqual(
                admin_client.post(
                    "/api/admin/deletions/preview",
                    json={"action": "user", "userId": admin_id},
                    headers=origin,
                ).status_code,
                400,
            )
        finally:
            admin_client.close()
        self.assertEqual(self.client.get("/api/notes").status_code, 404)
        self.assertEqual(
            self.client.request(
                "DELETE",
                "/api/experts/default",
                json={"confirmed": True},
            ).status_code,
            400,
        )


if __name__ == "__main__":
    unittest.main()
