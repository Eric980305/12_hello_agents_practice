"""Local user accounts for the Chapter 8 learning application."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


PASSWORD_HASH_ITERATIONS = 600_000
USERNAME_PATTERN = re.compile(r"^[\w.@+-]{2,64}$", re.UNICODE)


class UserAccountStore:
    """Persist local accounts without storing plaintext passwords."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path).expanduser().resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def register(self, username: str, password: str) -> dict[str, str]:
        normalized = self._validate_username(username)
        self._validate_password(password)
        salt = secrets.token_bytes(16)
        digest = self._derive_password(password, salt, PASSWORD_HASH_ITERATIONS)
        user_id = uuid4().hex
        created_at = datetime.now(timezone.utc).isoformat()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO app_users (
                        user_id, username, password_salt, password_hash,
                        password_iterations, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        normalized,
                        salt,
                        digest,
                        PASSWORD_HASH_ITERATIONS,
                        created_at,
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise ValueError("该用户名已注册。") from error
        return {"user_id": user_id, "username": normalized}

    def authenticate(self, username: str, password: str) -> dict[str, str] | None:
        normalized = self._validate_username(username)
        if not isinstance(password, str) or not password:
            return None
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT user_id, username, password_salt, password_hash,
                       password_iterations
                FROM app_users
                WHERE username = ? COLLATE NOCASE
                """,
                (normalized,),
            ).fetchone()
        if row is None:
            return None
        candidate = self._derive_password(
            password,
            row["password_salt"],
            int(row["password_iterations"]),
        )
        if not hmac.compare_digest(candidate, row["password_hash"]):
            return None
        return {"user_id": row["user_id"], "username": row["username"]}

    def get_by_id(self, user_id: str) -> dict[str, str] | None:
        """Return the public account identity used to restore a browser session."""
        if not isinstance(user_id, str) or not user_id:
            return None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT user_id, username FROM app_users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return {"user_id": row["user_id"], "username": row["username"]}

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS app_users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    password_salt BLOB NOT NULL,
                    password_hash BLOB NOT NULL,
                    password_iterations INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _derive_password(password: str, salt: bytes, iterations: int) -> bytes:
        return hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
        )

    @staticmethod
    def _validate_username(username: str) -> str:
        normalized = username.strip() if isinstance(username, str) else ""
        if not USERNAME_PATTERN.fullmatch(normalized):
            raise ValueError("用户名需为 2–64 位，可使用文字、数字及 . _ @ + -。")
        return normalized

    @staticmethod
    def _validate_password(password: str) -> None:
        if not isinstance(password, str) or not 6 <= len(password) <= 256:
            raise ValueError("密码长度需为 6–256 位。")


__all__ = ["UserAccountStore"]
