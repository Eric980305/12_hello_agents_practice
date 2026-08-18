from __future__ import annotations

import hashlib
import secrets
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import RLock
from time import monotonic
from typing import Any, Protocol
from uuid import uuid4

from apps.pdf_learning_assistant import (
    ALL_KNOWLEDGE_BASES,
    create_pdf_learning_assistant,
)
from apps.user_store import UserAccountStore

from .config import Settings


def utc_now() -> datetime:
    return datetime.now(UTC)


class Assistant(Protocol):
    session_id: str
    current_knowledge_base_id: str
    conversations: list[dict[str, str]]

    def list_knowledge_bases(self) -> list[dict[str, str]]: ...
    def create_knowledge_base(self, name: str) -> dict[str, str]: ...
    def delete_knowledge_base(self, knowledge_base_id: str, *, confirmed: bool) -> dict[str, object]: ...
    def select_knowledge_base(self, knowledge_base_id: str) -> str: ...
    def list_documents(self, knowledge_base_id: str | None = None, *, query: str = "", include_all: bool = False) -> list[dict[str, object]]: ...
    def load_document(self, file_path: str | Path, *, knowledge_base_id: str | None = None) -> dict[str, Any]: ...
    def delete_document(self, document_id: str, *, knowledge_base_id: str | None = None, confirmed: bool = False) -> dict[str, object]: ...
    def ask(self, question: str, *, knowledge_base_id: str | None = None, use_advanced_search: bool = False) -> str: ...
    def generate_monthly_personal_report(self, *, save_to_file: bool = True) -> dict[str, Any]: ...


class SessionService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        settings.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.users = UserAccountStore(settings.database_path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.settings.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS expert_web_sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_expert_web_sessions_expires
                ON expert_web_sessions(expires_at)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS expert_admin_roles (
                    user_id TEXT PRIMARY KEY,
                    granted_at TEXT NOT NULL
                )
                """
            )
            self._delete_invalid(connection, utc_now())

    @staticmethod
    def _delete_invalid(connection: sqlite3.Connection, now: datetime) -> None:
        connection.execute(
            "DELETE FROM expert_web_sessions WHERE expires_at <= ?",
            (now.isoformat(),),
        )
        connection.execute(
            """
            DELETE FROM expert_admin_roles
            WHERE NOT EXISTS (
                SELECT 1 FROM app_users
                WHERE app_users.user_id = expert_admin_roles.user_id
            )
            """
        )
        connection.execute(
            """
            DELETE FROM expert_web_sessions
            WHERE NOT EXISTS (
                SELECT 1 FROM app_users
                WHERE app_users.user_id = expert_web_sessions.user_id
            )
            """
        )

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def create(self, user_id: str, *, replace_token: str | None = None) -> str:
        token = secrets.token_urlsafe(32)
        now = utc_now()
        with self._connect() as connection:
            self._delete_invalid(connection, now)
            if replace_token:
                connection.execute(
                    "DELETE FROM expert_web_sessions WHERE token_hash = ?",
                    (self._hash_token(replace_token),),
                )
            connection.execute(
                """
                INSERT INTO expert_web_sessions(token_hash, user_id, created_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    self._hash_token(token),
                    user_id,
                    now.isoformat(),
                    (now + timedelta(days=self.settings.session_days)).isoformat(),
                ),
            )
        return token

    def resolve(self, token: str | None) -> dict[str, str] | None:
        if not token:
            return None
        token_hash = self._hash_token(token)
        now = utc_now().isoformat()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT user_id, expires_at FROM expert_web_sessions
                WHERE token_hash = ?
                """,
                (token_hash,),
            ).fetchone()
            if row is not None and row["expires_at"] <= now:
                connection.execute(
                    "DELETE FROM expert_web_sessions WHERE token_hash = ?",
                    (token_hash,),
                )
                return None
        if row is None:
            return None
        user = self.users.get_by_id(row["user_id"])
        if user is None:
            self.delete(token)
        return user

    def delete(self, token: str | None) -> None:
        if not token:
            return
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM expert_web_sessions WHERE token_hash = ?",
                (self._hash_token(token),),
            )

    def is_admin(self, user: dict[str, str]) -> bool:
        user_id = user.get("user_id", "")
        if not user_id:
            return False
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM expert_admin_roles WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return row is not None

    def grant_admin(self, username: str) -> dict[str, str]:
        with self._connect() as connection:
            user = connection.execute(
                "SELECT user_id, username FROM app_users WHERE username = ? COLLATE NOCASE",
                (username.strip(),),
            ).fetchone()
            if user is None:
                raise ValueError("找不到该用户。")
            connection.execute(
                "INSERT OR IGNORE INTO expert_admin_roles(user_id, granted_at) VALUES (?, ?)",
                (user["user_id"], utc_now().isoformat()),
            )
        return {"user_id": user["user_id"], "username": user["username"]}

    def revoke_admin(self, username: str) -> dict[str, str]:
        with self._connect() as connection:
            user = connection.execute(
                "SELECT user_id, username FROM app_users WHERE username = ? COLLATE NOCASE",
                (username.strip(),),
            ).fetchone()
            if user is None:
                raise ValueError("找不到该用户。")
            connection.execute(
                "DELETE FROM expert_admin_roles WHERE user_id = ?",
                (user["user_id"],),
            )
            connection.execute(
                "DELETE FROM expert_web_sessions WHERE user_id = ?",
                (user["user_id"],),
            )
        return {"user_id": user["user_id"], "username": user["username"]}

    def list_admins(self) -> list[dict[str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT u.user_id, u.username, r.granted_at
                FROM expert_admin_roles r
                JOIN app_users u ON u.user_id = r.user_id
                ORDER BY r.granted_at, u.username COLLATE NOCASE
                """
            ).fetchall()
        return [dict(row) for row in rows]


class LoginRateLimiter:
    """Bound repeated login attempts without persisting credentials or passwords."""

    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._attempts: dict[str, list[float]] = {}
        self._lock = RLock()

    def retry_after(self, key: str) -> int:
        now = monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            attempts = [value for value in self._attempts.get(key, []) if value > cutoff]
            if attempts:
                self._attempts[key] = attempts
            else:
                self._attempts.pop(key, None)
            if len(attempts) < self.limit:
                return 0
            return max(1, int(self.window_seconds - (now - attempts[0])))

    def fail(self, key: str) -> None:
        with self._lock:
            self._attempts.setdefault(key, []).append(monotonic())

    def clear(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)


class AssistantService:
    def __init__(
        self,
        settings: Settings,
        factory: Callable[[str], Assistant] | None = None,
    ) -> None:
        self.settings = settings
        self.factory = factory or create_pdf_learning_assistant
        self._assistants: dict[str, Assistant] = {}
        self._lock = RLock()

    @staticmethod
    def _session_key(session_token: str) -> str:
        return hashlib.sha256(session_token.encode("utf-8")).hexdigest()

    def get(self, session_token: str, user_id: str) -> Assistant:
        session_key = self._session_key(session_token)
        with self._lock:
            assistant = self._assistants.get(session_key)
            if assistant is None:
                assistant = self.factory(user_id)
                self._assistants[session_key] = assistant
            return assistant

    def discard(self, session_token: str | None) -> None:
        if not session_token:
            return
        with self._lock:
            self._assistants.pop(self._session_key(session_token), None)

    def discard_user(self, user_id: str) -> None:
        with self._lock:
            self._assistants = {
                key: assistant
                for key, assistant in self._assistants.items()
                if getattr(assistant, "user_id", None) != user_id
            }

    def discard_all(self) -> None:
        with self._lock:
            self._assistants.clear()

    @staticmethod
    def _expert_name(assistant: Assistant, expert_id: str) -> str:
        return next(
            item["name"]
            for item in assistant.list_knowledge_bases()
            if item["id"] == expert_id
        )

    @staticmethod
    def experts(assistant: Assistant) -> list[dict[str, Any]]:
        result = [
            {
                "id": ALL_KNOWLEDGE_BASES,
                "name": "所有专家",
                "kind": "aggregate",
                "deletable": False,
            }
        ]
        for item in assistant.list_knowledge_bases():
            shared = item["id"] == "default"
            result.append(
                {
                    "id": item["id"],
                    "name": item["name"],
                    "kind": "shared" if shared else "private",
                    "deletable": not shared,
                }
            )
        return result

    def documents(
        self,
        assistant: Assistant,
        expert_id: str,
        query: str,
        limit: int = 10,
        offset: int = 0,
    ) -> dict[str, Any]:
        include_all = expert_id == ALL_KNOWLEDGE_BASES
        documents = assistant.list_documents(
            None if include_all else expert_id,
            query=query,
            include_all=include_all,
        )
        result = []
        for document in documents:
            resolved_id = str(document.get("knowledge_base_id") or expert_id)
            result.append(
                {
                    "id": str(document.get("document_id") or document.get("id") or ""),
                    "fileName": str(document.get("name") or document.get("document_id") or ""),
                    "sourceType": str(document.get("source_type") or ""),
                    "expertId": resolved_id,
                    "expertName": str(
                        document.get("knowledge_base_name")
                        or self._expert_name(assistant, resolved_id)
                    ),
                    "createdAt": str(document.get("created_at") or ""),
                }
            )
        ordered = sorted(result, key=lambda item: item["createdAt"], reverse=True)
        return {
            "items": ordered[offset : offset + limit],
            "total": len(ordered),
        }

    @staticmethod
    def history(assistant: Assistant) -> list[dict[str, str]]:
        items: list[dict[str, str]] = []
        for turn in assistant.conversations:
            expert_id = turn["knowledge_base_id"]
            expert_name = AssistantService._expert_name(assistant, expert_id)
            created_at = turn["created_at"]
            base_id = uuid4().hex
            items.extend(
                [
                    {
                        "id": f"{base_id}-user",
                        "role": "user",
                        "content": turn["question"],
                        "expertId": expert_id,
                        "expertName": expert_name,
                        "createdAt": created_at,
                    },
                    {
                        "id": f"{base_id}-assistant",
                        "role": "assistant",
                        "content": turn["answer"],
                        "expertId": expert_id,
                        "expertName": expert_name,
                        "createdAt": created_at,
                    },
                ]
            )
        return items
