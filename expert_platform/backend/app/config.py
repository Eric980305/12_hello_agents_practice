from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    project_root: Path
    database_path: Path
    temporary_root: Path
    frontend_dist: Path
    session_cookie: str = "expert_session"
    session_days: int = 30
    secure_cookie: bool = False
    allowed_origins: tuple[str, ...] = (
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    )
    max_upload_bytes: int = 50 * 1024 * 1024
    login_attempt_limit: int = 5
    login_attempt_window_seconds: int = 300
    rag_collection: str = "hello_agents_practice_rag_1024"
    episodic_collection: str = "hello_agents_practice_episodic_1024"


def default_settings() -> Settings:
    project_root = Path(__file__).resolve().parents[3]
    vector_size = os.getenv("QDRANT_VECTOR_SIZE", "1024")
    return Settings(
        project_root=project_root,
        database_path=project_root / "memory_data" / "practice_memory.db",
        temporary_root=project_root / ".runtime" / "expert_platform_uploads",
        frontend_dist=project_root / "expert_platform" / "frontend" / "dist",
        rag_collection=os.getenv(
            "PRACTICE_RAG_QDRANT_COLLECTION",
            f"hello_agents_practice_rag_{vector_size}",
        ),
        episodic_collection=os.getenv(
            "PRACTICE_EPISODIC_QDRANT_COLLECTION",
            f"hello_agents_practice_episodic_{vector_size}",
        ),
    )
