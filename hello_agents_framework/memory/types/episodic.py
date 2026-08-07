"""Persistent event memory backed by SQLite and a semantic vector index."""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import timedelta
from typing import Any

from ..base import (
    BaseMemory,
    ForgetStrategy,
    MemoryConfig,
    MemoryItem,
    MemorySearchResult,
    utc_now,
)
from ..embedding import TextEmbedder
from ..storage import SQLiteDocumentStore, VectorStore


class EpisodicMemory(BaseMemory):
    """Persist complete events in SQLite and retrieve candidates by vector."""

    memory_type = "episodic"

    def __init__(
        self,
        *,
        document_store: SQLiteDocumentStore,
        vector_store: VectorStore,
        embedder: TextEmbedder,
        config: MemoryConfig | None = None,
    ) -> None:
        self.config = config or MemoryConfig()
        self.document_store = document_store
        self.vector_store = vector_store
        self.embedder = embedder

    def add(self, item: MemoryItem) -> str:
        if item.memory_type != self.memory_type:
            raise ValueError("EpisodicMemory accepts episodic records only.")
        vector = self._embed(item.content)
        self.document_store.add(item)
        try:
            self._index(item, vector)
        except Exception:
            self.document_store.delete(item.id, user_id=item.user_id)
            raise
        return item.id

    def retrieve(
        self,
        query: str,
        *,
        user_id: str,
        limit: int,
        min_importance: float,
    ) -> list[MemorySearchResult]:
        normalized_query = self._required_text(query, "query")
        self._required_text(user_id, "user_id")
        if limit <= 0:
            raise ValueError("limit must be positive.")
        if not 0.0 <= min_importance <= 1.0:
            raise ValueError("min_importance must be between 0 and 1.")

        hits = self.vector_store.search(
            vector=self._embed(normalized_query),
            user_id=user_id,
            memory_type=self.memory_type,
            min_importance=min_importance,
            limit=max(limit * 5, 20),
        )
        results = []
        for hit in hits:
            item = self.document_store.get(hit.memory_id, user_id=user_id)
            if item is None or item.importance < min_importance:
                continue
            recency = self._recency_score(item)
            importance_weight = 0.8 + item.importance * 0.4
            score = (hit.score * 0.8 + recency * 0.2) * importance_weight
            results.append(
                MemorySearchResult(memory=item, score=max(0.0, min(1.0, score)))
            )
        results.sort(
            key=lambda result: (
                result.score,
                result.memory.importance,
                result.memory.created_at,
            ),
            reverse=True,
        )
        return results[:limit]

    def get(self, memory_id: str, *, user_id: str) -> MemoryItem | None:
        return self.document_store.get(memory_id, user_id=user_id)

    def update(
        self,
        memory_id: str,
        *,
        user_id: str,
        changes: Mapping[str, Any],
    ) -> MemoryItem:
        allowed = {"content", "importance", "metadata"}
        unexpected = set(changes) - allowed
        if unexpected:
            raise ValueError(f"unsupported memory updates: {sorted(unexpected)}")
        if not changes:
            raise ValueError("at least one memory field must be updated.")
        current = self.get(memory_id, user_id=user_id)
        if current is None:
            raise KeyError(f"memory '{memory_id}' was not found.")
        updated = MemoryItem.model_validate(
            current.model_copy(
                update={**dict(changes), "updated_at": utc_now()},
            ).model_dump()
        )
        vector = self._embed(updated.content)
        self.document_store.update(updated)
        try:
            self._index(updated, vector)
        except Exception:
            self.document_store.update(current)
            raise
        return updated

    def remove(self, memory_id: str, *, user_id: str) -> bool:
        if self.get(memory_id, user_id=user_id) is None:
            return False
        self.vector_store.delete(memory_id)
        return self.document_store.delete(memory_id, user_id=user_id)

    def list(self, *, user_id: str) -> list[MemoryItem]:
        return self.document_store.list(user_id=user_id)

    def forget(
        self,
        *,
        user_id: str,
        strategy: ForgetStrategy,
        threshold: float,
        max_age_days: int,
    ) -> int:
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold must be between 0 and 1.")
        if max_age_days <= 0:
            raise ValueError("max_age_days must be positive.")
        items = self.list(user_id=user_id)
        if strategy == "importance_based":
            candidates = [item for item in items if item.importance < threshold]
        elif strategy == "time_based":
            cutoff = utc_now() - timedelta(days=max_age_days)
            candidates = [item for item in items if item.created_at < cutoff]
        elif strategy == "capacity_based":
            excess = max(0, len(items) - self.config.episodic_memory_capacity)
            candidates = sorted(items, key=lambda item: item.created_at)[:excess]
        else:
            raise ValueError(f"unsupported forgetting strategy: {strategy}")
        return sum(self.remove(item.id, user_id=user_id) for item in candidates)

    def clear(self, *, user_id: str) -> int:
        return sum(
            self.remove(item.id, user_id=user_id)
            for item in self.list(user_id=user_id)
        )

    def _embed(self, text: str) -> list[float]:
        vector = self.embedder.embed(text)
        if len(vector) != self.embedder.dimension:
            raise RuntimeError("embedder returned an unexpected vector dimension.")
        return vector

    def _index(self, item: MemoryItem, vector: list[float]) -> None:
        self.vector_store.upsert(
            memory_id=item.id,
            vector=vector,
            payload={
                "memory_id": item.id,
                "user_id": item.user_id,
                "memory_type": item.memory_type,
                "importance": item.importance,
                "created_at": item.created_at.isoformat(),
            },
        )

    def _recency_score(self, item: MemoryItem) -> float:
        age_days = max(0.0, (utc_now() - item.created_at).total_seconds() / 86_400)
        half_life = self.config.episodic_recency_half_life_days
        return math.pow(0.5, age_days / half_life)

    @staticmethod
    def _required_text(value: str, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must not be empty.")
        return value.strip()


__all__ = ["EpisodicMemory"]
