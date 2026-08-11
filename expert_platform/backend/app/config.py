from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    project_root: Path
    database_path: Path
    upload_root: Path
    session_cookie: str = "expert_session"
    session_days: int = 30
    shared_owner_id: str = "__shared__"
    shared_expert_id: str = "default"
    shared_expert_name: str = "通用专家"
    shared_namespace: str = "pdf_shared_default"


def default_settings() -> Settings:
    project_root = Path(__file__).resolve().parents[3]
    return Settings(
        project_root=project_root,
        database_path=project_root / "memory_data" / "practice_memory.db",
        upload_root=project_root / "knowledge_base" / "expert_platform",
    )
