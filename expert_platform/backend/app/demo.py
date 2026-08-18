from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from uuid import uuid4

from .config import Settings
from .main import create_app


DEMO_ROOT = Path("/tmp/hello-agent-expert-platform-browser-qa-rbac")


class DemoQdrant:
    def user_rag_namespaces(self, scope: str) -> set[str]:
        return set()

    def count_rag(self, namespace: str, document_id: str | None = None) -> int:
        return 0

    def delete_rag(self, namespace: str, document_id: str | None = None) -> None:
        return None

    def count_episodic(self, user_id: str) -> int:
        return 0

    def delete_episodic(self, user_id: str) -> None:
        return None

    def collection_points(self) -> dict[str, int]:
        return {"rag": 1248, "episodic": 73}


class DemoAssistant:
    """In-memory browser-QA backend; never used by the production entry point."""

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        self.session_id = f"demo-{uuid4().hex}"
        self.current_knowledge_base_id = "default"
        self.knowledge_bases = {
            "default": {"id": "default", "name": "共享专家库", "owner_user_id": "__shared__"},
            "product": {"id": "product", "name": "产品研究专家", "owner_user_id": user_id},
        }
        self.documents: dict[str, list[dict[str, object]]] = {
            "default": [
                {
                    "document_id": "demo-handbook",
                    "name": "智能专家平台使用手册.md",
                    "source_type": "md",
                    "created_at": "2026-08-12T09:00:00+08:00",
                }
            ],
            "product": [],
        }
        self.conversations: list[dict[str, str]] = []

    def list_knowledge_bases(self):
        return list(self.knowledge_bases.values())

    def create_knowledge_base(self, name: str):
        normalized = name.strip()
        if any(item["name"].casefold() == normalized.casefold() for item in self.knowledge_bases.values()):
            raise ValueError("专家名称已存在。")
        expert_id = uuid4().hex[:12]
        self.knowledge_bases[expert_id] = {"id": expert_id, "name": normalized, "owner_user_id": self.user_id}
        self.documents[expert_id] = []
        return {"id": expert_id, "name": normalized}

    def delete_knowledge_base(self, knowledge_base_id: str, *, confirmed: bool):
        if not confirmed:
            raise ValueError("删除专家前必须确认。")
        if knowledge_base_id == "default":
            raise ValueError("共享专家库不能删除。")
        item = self.knowledge_bases.pop(knowledge_base_id)
        count = len(self.documents.pop(knowledge_base_id))
        return {"id": item["id"], "name": item["name"], "documents_deleted": count}

    def select_knowledge_base(self, knowledge_base_id: str):
        self.current_knowledge_base_id = knowledge_base_id
        return self.knowledge_bases[knowledge_base_id]["name"]

    def list_documents(self, knowledge_base_id=None, *, query="", include_all=False):
        expert_ids = list(self.documents) if include_all else [knowledge_base_id or "default"]
        return [
            {**item, "knowledge_base_id": expert_id, "knowledge_base_name": self.knowledge_bases[expert_id]["name"]}
            for expert_id in expert_ids
            for item in self.documents[expert_id]
            if query.casefold() in str(item["name"]).casefold()
        ]

    def load_document(self, file_path, *, knowledge_base_id=None):
        source = Path(file_path)
        expert_id = knowledge_base_id or "default"
        item = {
            "document_id": uuid4().hex,
            "name": source.name,
            "source_type": source.suffix.lstrip("."),
            "created_at": "2026-08-12T12:00:00+08:00",
        }
        self.documents[expert_id].append(item)
        return {"success": True, "duplicate": False, "message": "文件已加载并建立索引。", "document": source.name, "document_id": item["document_id"]}

    def delete_document(self, document_id, *, knowledge_base_id=None, confirmed=False):
        if not confirmed:
            raise ValueError("删除文档前必须明确确认。")
        expert_id = knowledge_base_id or "default"
        item = next(item for item in self.documents[expert_id] if item["document_id"] == document_id)
        self.documents[expert_id].remove(item)
        return item

    def ask(self, question, *, knowledge_base_id=None, use_advanced_search=False):
        expert_id = knowledge_base_id or "default"
        answer = (
            "智能专家平台会先在当前专家的资料范围内检索相关分块，再让模型基于这些资料生成回答。"
            "当资料不足时，平台会明确拒答，而不是使用无来源的模型记忆补充。 [S1]\n\n"
            "来源：\n[S1] 智能专家平台使用手册.md，chunk 0，score 0.932"
        )
        self.conversations.append({
            "knowledge_base_id": expert_id,
            "question": question,
            "answer": answer,
            "created_at": "2026-08-12T12:01:00+08:00",
        })
        return answer

    def get_stats(self):
        return {
            "会话时长": "8 分钟",
            "加载文档": sum(len(items) for items in self.documents.values()),
            "提问次数": len(self.conversations),
            "当前专家": self.knowledge_bases[self.current_knowledge_base_id]["name"],
            "当前文档": "智能专家平台使用手册.md",
        }

    def generate_monthly_personal_report(self, *, save_to_file=True):
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
            "summary": "## 专家：共享专家库\n\n重点主题：平台如何依据资料回答。\n关键结论：检索范围由当前专家限定，回答保留来源标签。\n待跟进事项：暂无。",
            "expertSummaries": [],
        }


app = create_app(
    Settings(
        project_root=DEMO_ROOT,
        database_path=DEMO_ROOT / "memory.db",
        temporary_root=DEMO_ROOT / "uploads",
        frontend_dist=Path(__file__).resolve().parents[2] / "frontend" / "dist",
    ),
    assistant_factory=DemoAssistant,
    admin_qdrant=DemoQdrant(),
)

try:
    app.state.sessions.grant_admin("admin")
except ValueError:
    app.state.sessions.users.register("admin", "admin-secret12")
    app.state.sessions.grant_admin("admin")

for demo_username in ("junmin", "researcher"):
    try:
        app.state.sessions.users.register(demo_username, "user-secret12")
    except ValueError:
        pass

with sqlite3.connect(app.state.settings.database_path) as connection:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS rag_knowledge_bases (
            user_id TEXT NOT NULL,
            knowledge_base_id TEXT NOT NULL,
            name TEXT NOT NULL,
            namespace TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            PRIMARY KEY (user_id, knowledge_base_id)
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
            metadata_json TEXT NOT NULL
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
    researcher = connection.execute(
        "SELECT user_id FROM app_users WHERE username = 'researcher'"
    ).fetchone()[0]
    timestamp = "2026-08-17T09:00:00+00:00"
    namespace = f"kb_{researcher[:12]}_product"
    demo_source = DEMO_ROOT / "knowledge_base" / researcher[:12] / "product-brief.md"
    demo_source.parent.mkdir(parents=True, exist_ok=True)
    demo_source.write_bytes(b"x" * 1536)
    connection.execute(
        "INSERT OR IGNORE INTO rag_knowledge_bases VALUES (?, ?, ?, ?, ?)",
        (researcher, "product", "Product Research", namespace, timestamp),
    )
    connection.execute(
        "INSERT OR REPLACE INTO rag_documents VALUES (?, ?, ?, ?, ?)",
        (
            namespace,
            "product-brief",
            "demo",
            json.dumps(
                {
                    "original_name": "product-brief.md",
                    "source_type": "md",
                    "source_path": str(demo_source),
                }
            ),
            timestamp,
        ),
    )
    connection.execute(
        "INSERT OR IGNORE INTO rag_chunks VALUES (?, ?, ?, ?, ?, ?)",
        ("product-brief-0", namespace, "product-brief", 0, "demo", "{}"),
    )
