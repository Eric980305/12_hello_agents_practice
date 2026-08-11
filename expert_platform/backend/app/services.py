from __future__ import annotations

import hashlib
import json
import secrets
import shutil
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Any

from apps.user_store import UserAccountStore
from hello_agents_framework.memory.storage.document_store import SQLiteKnowledgeStore
from hello_agents_framework.tools.builtin.rag_tool import RAGTool

from .config import Settings


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_now() -> str:
    return utc_now().isoformat()


class SessionService:
    def __init__(self, settings: Settings):
        self.settings = settings
        settings.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.users = UserAccountStore(settings.database_path)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.settings.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS expert_sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS expert_messages (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    session_key TEXT NOT NULL,
                    expert_id TEXT NOT NULL,
                    expert_name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    sources_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_expert_messages_user_session
                ON expert_messages(user_id, session_key, created_at);
                CREATE TABLE IF NOT EXISTS expert_notes (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    expert_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def create(self, user_id: str) -> str:
        token = secrets.token_urlsafe(32)
        now = utc_now()
        with self._connect() as connection:
            connection.execute("DELETE FROM expert_sessions WHERE expires_at <= ?", (now.isoformat(),))
            connection.execute(
                "INSERT INTO expert_sessions(token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (
                    self._hash_token(token),
                    user_id,
                    now.isoformat(),
                    (now + timedelta(days=self.settings.session_days)).isoformat(),
                ),
            )
        return token

    def resolve(self, token: str | None) -> dict[str, Any] | None:
        if not token:
            return None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT user_id FROM expert_sessions WHERE token_hash = ? AND expires_at > ?",
                (self._hash_token(token), iso_now()),
            ).fetchone()
        return self.users.get_by_id(row["user_id"]) if row else None

    def delete(self, token: str | None) -> None:
        if not token:
            return
        with self._connect() as connection:
            connection.execute("DELETE FROM expert_sessions WHERE token_hash = ?", (self._hash_token(token),))


class ExpertService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.store = SQLiteKnowledgeStore(settings.database_path)
        self.settings.upload_root.mkdir(parents=True, exist_ok=True)
        self.store.ensure_knowledge_base(
            settings.shared_owner_id,
            settings.shared_expert_id,
            settings.shared_expert_name,
            settings.shared_namespace,
        )
        self._rag_tools: dict[str, RAGTool] = {}
        self._rag_lock = RLock()

    def _accessible(self, user_id: str) -> list[dict[str, Any]]:
        items = self.store.list_accessible_knowledge_bases(user_id, self.settings.shared_owner_id)
        return [dict(item) for item in items]

    def list_experts(self, user_id: str) -> list[dict[str, Any]]:
        result = [{"id": "all", "name": "所有专家", "kind": "aggregate", "deletable": False}]
        for item in self._accessible(user_id):
            shared = item["knowledge_base_id"] == self.settings.shared_expert_id
            result.append(
                {
                    "id": item["knowledge_base_id"],
                    "name": self.settings.shared_expert_name if shared else item["name"],
                    "kind": "shared" if shared else "private",
                    "deletable": not shared,
                }
            )
        return result

    def get_expert(self, user_id: str, expert_id: str) -> dict[str, Any]:
        for item in self._accessible(user_id):
            if item["knowledge_base_id"] == expert_id:
                return item
        raise LookupError("专家不存在或无权访问")

    def create_expert(self, user_id: str, name: str) -> dict[str, Any]:
        clean_name = " ".join(name.split())
        if not clean_name:
            raise ValueError("专家名称不能为空")
        if any(item["name"].casefold() == clean_name.casefold() for item in self._accessible(user_id)):
            raise ValueError("同名专家已存在")
        expert_id = uuid.uuid4().hex
        namespace = f"expert_{user_id}_{expert_id}"
        self.store.ensure_knowledge_base(user_id, expert_id, clean_name, namespace)
        return {"id": expert_id, "name": clean_name, "kind": "private", "deletable": True}

    def delete_expert(self, user_id: str, expert_id: str) -> int:
        if expert_id == self.settings.shared_expert_id:
            raise ValueError("通用专家不可删除")
        expert = self.get_expert(user_id, expert_id)
        if expert["owner_user_id"] != user_id:
            raise PermissionError("只能删除自己创建的专家")
        documents = self.store.list_documents(expert["namespace"])
        for document in documents:
            self.delete_document(user_id, expert_id, document["document_id"])
        if not self.store.delete_owned_knowledge_base(user_id, expert_id):
            raise LookupError("专家不存在")
        return len(documents)

    def list_documents(self, user_id: str, expert_id: str) -> list[dict[str, Any]]:
        experts = self._accessible(user_id) if expert_id == "all" else [self.get_expert(user_id, expert_id)]
        rows: list[dict[str, Any]] = []
        for expert in experts:
            expert_name = (
                self.settings.shared_expert_name
                if expert["knowledge_base_id"] == self.settings.shared_expert_id
                else expert["name"]
            )
            for document in self.store.list_documents(expert["namespace"]):
                rows.append(
                    {
                        "id": document["document_id"],
                        "fileName": document.get("file_name") or document["document_id"],
                        "expertId": expert["knowledge_base_id"],
                        "expertName": expert_name,
                        "createdAt": document.get("created_at", ""),
                    }
                )
        rows.sort(key=lambda item: item["createdAt"], reverse=True)
        return rows

    @staticmethod
    def _safe_file_name(file_name: str) -> str:
        return Path(file_name).name.replace("\x00", "")

    def _rag(self, expert: dict[str, Any]) -> RAGTool:
        namespace = expert["namespace"]
        with self._rag_lock:
            if namespace not in self._rag_tools:
                root = self.settings.upload_root / namespace
                root.mkdir(parents=True, exist_ok=True)
                self._rag_tools[namespace] = RAGTool(
                    knowledge_base_path=str(root),
                    rag_namespace=namespace,
                    database_path=self.settings.database_path,
                )
            return self._rag_tools[namespace]

    def upload_document(self, user_id: str, expert_id: str, source: Path, original_name: str) -> dict[str, Any]:
        if expert_id == "all":
            raise ValueError("请先选择一位专家")
        expert = self.get_expert(user_id, expert_id)
        document_id = self._safe_file_name(original_name)
        if self.store.has_document(expert["namespace"], document_id):
            raise FileExistsError("该专家下已存在同名文件")
        destination = self.settings.upload_root / expert["namespace"] / document_id
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        try:
            result = self._rag(expert).execute(
                "add_document",
                file_path=str(destination),
                document_id=document_id,
                metadata={"uploaded_by": user_id, "expert_id": expert_id},
            )
            if isinstance(result, dict) and result.get("success") is False:
                raise RuntimeError(result.get("error") or result.get("message") or "文档索引失败")
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        return self.list_documents(user_id, expert_id)[0]

    def delete_document(self, user_id: str, expert_id: str, document_id: str) -> None:
        expert = self.get_expert(user_id, expert_id)
        if expert["knowledge_base_id"] == self.settings.shared_expert_id or expert["owner_user_id"] == user_id:
            try:
                self._rag(expert).execute("delete_document", document_id=document_id)
            except Exception:
                self.store.delete_document(expert["namespace"], document_id)
            (self.settings.upload_root / expert["namespace"] / self._safe_file_name(document_id)).unlink(missing_ok=True)
            return
        raise PermissionError("无权删除该文档")

    def search(self, user_id: str, expert_id: str, query: str, advanced: bool = False) -> list[dict[str, Any]]:
        expert = self.get_expert(user_id, expert_id)
        results = self._rag(expert).retrieve(query=query, limit=5, advanced=advanced)
        return results if isinstance(results, list) else []


class ConversationService:
    def __init__(self, settings: Settings, experts: ExpertService):
        self.settings = settings
        self.experts = experts

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.settings.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def add_message(
        self,
        user_id: str,
        session_key: str,
        expert_id: str,
        expert_name: str,
        role: str,
        content: str,
        sources: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        message = {
            "id": uuid.uuid4().hex,
            "role": role,
            "content": content,
            "expertId": expert_id,
            "expertName": expert_name,
            "sources": sources or [],
            "createdAt": iso_now(),
        }
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO expert_messages
                (id, user_id, session_key, expert_id, expert_name, role, content, sources_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    message["id"], user_id, session_key, expert_id, expert_name, role,
                    content, json.dumps(message["sources"], ensure_ascii=False), message["createdAt"],
                ),
            )
        return message

    def history(self, user_id: str, session_key: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM expert_messages WHERE user_id = ? AND session_key = ? ORDER BY created_at",
                (user_id, session_key),
            ).fetchall()
        return [
            {
                "id": row["id"], "role": row["role"], "content": row["content"],
                "expertId": row["expert_id"], "expertName": row["expert_name"],
                "sources": json.loads(row["sources_json"]), "createdAt": row["created_at"],
            }
            for row in rows
        ]

    def answer(self, user_id: str, session_key: str, expert_id: str, question: str, advanced: bool) -> dict[str, Any]:
        if expert_id == "all":
            raise ValueError("问答时请选择一位具体专家")
        expert = self.experts.get_expert(user_id, expert_id)
        expert_name = self.settings.shared_expert_name if expert_id == self.settings.shared_expert_id else expert["name"]
        self.add_message(user_id, session_key, expert_id, expert_name, "user", question)
        hits = self.experts.search(user_id, expert_id, question, advanced)
        sources = []
        excerpts = []
        for hit in hits[:5]:
            metadata = hit.get("metadata", {}) if isinstance(hit, dict) else {}
            text = metadata.get("content") or hit.get("content") or ""
            if text:
                excerpts.append(text)
            sources.append(
                {
                    "documentId": metadata.get("document_id") or hit.get("id", ""),
                    "fileName": metadata.get("file_name") or metadata.get("document_id") or "来源文档",
                    "score": hit.get("score"),
                }
            )
        if excerpts:
            answer = "根据当前专家资料，相关内容如下：\n\n" + "\n\n".join(excerpts[:3])
        else:
            answer = "当前专家资料中没有检索到足够相关的内容。"
        return self.add_message(user_id, session_key, expert_id, expert_name, "assistant", answer, sources)

    def report(self, user_id: str, session_key: str) -> dict[str, Any]:
        messages = self.history(user_id, session_key)
        grouped: dict[str, list[dict[str, Any]]] = {}
        for message in messages:
            grouped.setdefault(message["expertName"], []).append(message)
        sections = []
        for expert_name, items in grouped.items():
            questions = [item["content"] for item in items if item["role"] == "user"]
            sections.append({"expertName": expert_name, "questions": questions, "messageCount": len(items)})
        return {"sessionKey": session_key, "sections": sections, "messageCount": len(messages)}
