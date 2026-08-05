import math
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import Mock
from uuid import uuid4

from qdrant_client import QdrantClient

from hello_agents_practice import (
    EpisodicMemory,
    MemoryManager,
    MemoryTool,
    OpenAICompatibleEmbedding,
    QdrantVectorStore,
    SQLiteDocumentStore,
    WorkingMemory,
)
from hello_agents_practice.memory import MemoryConfig, VectorSearchHit


class FakeEmbedder:
    dimension = 3

    def embed(self, text: str) -> list[float]:
        normalized = text.casefold()
        return [
            float("python" in normalized),
            float("react" in normalized or "前端" in normalized),
            float("project" in normalized or "项目" in normalized),
        ]


class FakeVectorStore:
    def __init__(self, *, fail_upsert: bool = False) -> None:
        self.points: dict[str, tuple[list[float], dict[str, Any]]] = {}
        self.fail_upsert = fail_upsert

    def upsert(
        self,
        *,
        memory_id: str,
        vector: list[float],
        payload: dict[str, Any],
    ) -> None:
        if self.fail_upsert:
            raise RuntimeError("index unavailable")
        self.points[memory_id] = (vector, payload)

    def search(
        self,
        *,
        vector: list[float],
        user_id: str,
        memory_type: str,
        min_importance: float,
        limit: int,
    ) -> list[VectorSearchHit]:
        hits = []
        for memory_id, (candidate, payload) in self.points.items():
            if (
                payload["user_id"] != user_id
                or payload["memory_type"] != memory_type
                or payload["importance"] < min_importance
            ):
                continue
            denominator = math.sqrt(sum(x * x for x in vector)) * math.sqrt(
                sum(x * x for x in candidate)
            )
            score = sum(a * b for a, b in zip(vector, candidate)) / denominator if denominator else 0.0
            hits.append(VectorSearchHit(memory_id=memory_id, score=score))
        return sorted(hits, key=lambda hit: hit.score, reverse=True)[:limit]

    def delete(self, memory_id: str) -> None:
        self.points.pop(memory_id, None)


class EpisodicMemoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "memory.db"
        self.vectors = FakeVectorStore()
        self.store = SQLiteDocumentStore(self.database_path)
        self.episodic = EpisodicMemory(
            document_store=self.store,
            vector_store=self.vectors,
            embedder=FakeEmbedder(),
        )
        self.manager = MemoryManager(
            stores={
                "working": WorkingMemory(),
                "episodic": self.episodic,
            }
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_persists_authoritative_record_and_retrieves_by_vector(self) -> None:
        python_event = self.manager.add_memory(
            user_id="user-a",
            content="完成了第一个 Python 项目",
            memory_type="episodic",
            importance=0.8,
            metadata={"session_id": "session-1"},
        )
        self.manager.add_memory(
            user_id="user-a",
            content="学习 React 前端组件",
            memory_type="episodic",
            importance=0.7,
        )
        self.manager.add_memory(
            user_id="user-b",
            content="另一个用户完成 Python 项目",
            memory_type="episodic",
            importance=0.9,
        )

        results = self.manager.retrieve_memories(
            user_id="user-a",
            query="Python project",
            memory_types=["episodic"],
            limit=3,
        )
        reloaded = SQLiteDocumentStore(self.database_path).get(
            python_event.id,
            user_id="user-a",
        )

        self.assertEqual(results[0].memory.id, python_event.id)
        self.assertEqual(len(results), 2)
        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded.metadata, {"session_id": "session-1"})

    def test_tool_updates_and_removes_persistent_event(self) -> None:
        tool = MemoryTool(user_id="user-a", manager=self.manager)
        added = tool.execute(
            "add",
            content="完成 Python 项目",
            memory_type="episodic",
            importance=0.8,
        )
        memory_id = added.split("id=", 1)[1].split(" ", 1)[0]

        tool.execute(
            "update",
            memory_id=memory_id,
            content="完成 React 前端项目",
        )

        self.assertIn(
            "React",
            tool.execute(
                "search",
                query="前端 React",
                memory_type="episodic",
            ),
        )
        self.assertEqual(tool.execute("remove", memory_id=memory_id), "记忆已删除。")
        self.assertIsNone(self.store.get(memory_id, user_id="user-a"))
        self.assertNotIn(memory_id, self.vectors.points)

    def test_rolls_back_sqlite_when_initial_indexing_fails(self) -> None:
        failing = EpisodicMemory(
            document_store=self.store,
            vector_store=FakeVectorStore(fail_upsert=True),
            embedder=FakeEmbedder(),
        )
        manager = MemoryManager(stores={"episodic": failing})

        with self.assertRaises(RuntimeError):
            manager.add_memory(
                user_id="user-a",
                content="无法建立索引的事件",
                memory_type="episodic",
            )

        self.assertEqual(self.store.list(user_id="user-a"), [])


class QdrantVectorStoreTest(unittest.TestCase):
    def test_indexes_filters_and_deletes_vectors(self) -> None:
        store = QdrantVectorStore(
            collection_name="episodic_test",
            vector_size=3,
            client=QdrantClient(":memory:"),
        )
        store.upsert(
            memory_id="0f4e216b-1eb4-4ea1-afbd-3f881f673e2e",
            vector=[1.0, 0.0, 0.0],
            payload={
                "memory_id": "memory-a",
                "user_id": "user-a",
                "memory_type": "episodic",
                "importance": 0.8,
            },
        )
        store.upsert(
            memory_id="0e863fbd-343e-47d1-88b8-884902845a21",
            vector=[1.0, 0.0, 0.0],
            payload={
                "memory_id": "memory-b",
                "user_id": "user-b",
                "memory_type": "episodic",
                "importance": 0.9,
            },
        )

        hits = store.search(
            vector=[1.0, 0.0, 0.0],
            user_id="user-a",
            memory_type="episodic",
            min_importance=0.5,
            limit=3,
        )
        store.delete("0f4e216b-1eb4-4ea1-afbd-3f881f673e2e")
        remaining = store.search(
            vector=[1.0, 0.0, 0.0],
            user_id="user-a",
            memory_type="episodic",
            min_importance=0.5,
            limit=3,
        )

        self.assertEqual([hit.memory_id for hit in hits], ["memory-a"])
        self.assertEqual(remaining, [])

    def test_batches_bulk_upserts(self) -> None:
        store = QdrantVectorStore(
            collection_name="bulk_test",
            vector_size=3,
            client=QdrantClient(":memory:"),
        )
        original_upsert = store.client.upsert
        store.client.upsert = Mock(wraps=original_upsert)
        points = [
            (str(uuid4()), [1.0, 0.0, 0.0], {"index": index})
            for index in range(130)
        ]

        store.upsert_many(points, batch_size=64)

        self.assertEqual(store.client.upsert.call_count, 3)


class OpenAICompatibleEmbeddingTest(unittest.TestCase):
    def test_requests_and_validates_the_configured_dimension(self) -> None:
        embedder = OpenAICompatibleEmbedding(
            model="text-embedding-v4",
            api_key="test-key",
            base_url="https://example.invalid/compatible-api/v1",
            dimension=3,
        )

        class FakeEmbeddings:
            def create(self, **kwargs: Any) -> Any:
                self.kwargs = kwargs
                item = type(
                    "EmbeddingItem",
                    (),
                    {"embedding": [0.1, 0.2, 0.3], "index": 0},
                )()
                return type("EmbeddingResponse", (), {"data": [item]})()

        fake_embeddings = FakeEmbeddings()
        embedder._client = type("FakeClient", (), {"embeddings": fake_embeddings})()

        vector = embedder.embed("Python 项目")

        self.assertEqual(vector, [0.1, 0.2, 0.3])
        self.assertEqual(fake_embeddings.kwargs["model"], "text-embedding-v4")
        self.assertEqual(fake_embeddings.kwargs["dimensions"], 3)

    def test_batches_at_most_25_texts_per_embedding_request(self) -> None:
        embedder = OpenAICompatibleEmbedding(
            model="text-embedding-v4",
            api_key="test-key",
            base_url="https://example.invalid/compatible-api/v1",
            dimension=3,
        )

        class FakeEmbeddings:
            def __init__(self) -> None:
                self.batch_sizes: list[int] = []

            def create(self, **kwargs: Any) -> Any:
                texts = kwargs["input"]
                self.batch_sizes.append(len(texts))
                items = [
                    type(
                        "EmbeddingItem",
                        (),
                        {"embedding": [float(index), 0.0, 0.0], "index": index},
                    )()
                    for index in range(len(texts))
                ]
                return type("EmbeddingResponse", (), {"data": items})()

        fake_embeddings = FakeEmbeddings()
        embedder._client = type("FakeClient", (), {"embeddings": fake_embeddings})()

        vectors = embedder.embed_many([f"text-{index}" for index in range(51)])

        self.assertEqual(fake_embeddings.batch_sizes, [25, 25, 1])
        self.assertEqual(len(vectors), 51)


if __name__ == "__main__":
    unittest.main()
