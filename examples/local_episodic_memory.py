"""Run the practice Episodic Memory against configured SQLite/Bailian/Qdrant."""

from pathlib import Path

from dotenv import load_dotenv

from hello_agents_framework import (
    EpisodicMemory,
    MemoryManager,
    MemoryTool,
    OpenAICompatibleEmbedding,
    QdrantVectorStore,
    SQLiteDocumentStore,
    ToolRegistry,
    WorkingMemory,
)


PROJECT_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = Path(__file__).resolve().parents[3]


def main() -> None:
    load_dotenv(ROOT_DIR / ".env", override=False)

    embedder = OpenAICompatibleEmbedding.from_env()
    episodic = EpisodicMemory(
        document_store=SQLiteDocumentStore(
            PROJECT_DIR / "memory_data" / "practice_memory.db"
        ),
        vector_store=QdrantVectorStore.from_env(vector_size=embedder.dimension),
        embedder=embedder,
    )
    manager = MemoryManager(
        stores={"working": WorkingMemory(), "episodic": episodic}
    )
    manager.clear_memories(user_id="practice_episodic_demo")
    registry = ToolRegistry()
    registry.register_tool(MemoryTool(user_id="practice_episodic_demo", manager=manager))

    print("=== Add Episodic Memory ===")
    print(
        registry.execute_tool(
            "memory",
            {
                "action": "add",
                "content": "用户完成了第一个 Python 项目。",
                "memory_type": "episodic",
                "importance": 0.8,
                "metadata": {"event_type": "milestone"},
            },
        )
    )

    print("\n=== Search Episodic Memory ===")
    print(
        registry.execute_tool(
            "memory",
            {
                "action": "search",
                "query": "用户完成过什么 Python 里程碑",
                "memory_type": "episodic",
                "limit": 3,
            },
        )
    )
    print(f"\nSQLite: {episodic.document_store.database_path}")
    print(f"Qdrant collection: {episodic.vector_store.collection_name}")


if __name__ == "__main__":
    main()
