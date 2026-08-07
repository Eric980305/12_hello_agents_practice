"""Coordinate user-scoped memory types without owning their storage logic."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import timedelta
from typing import Any

from .base import (
    BaseMemory,
    ForgetStrategy,
    MemoryConfig,
    MemoryItem,
    MemorySearchResult,
    MemoryType,
    utc_now,
)
from .types import WorkingMemory


class MemoryManager:
    """Provide one validated entry point over enabled memory implementations."""

    def __init__(
        self,
        config: MemoryConfig | None = None,
        stores: Mapping[MemoryType, BaseMemory] | None = None,
    ) -> None:
        self.config = config or MemoryConfig()
        self._stores: dict[MemoryType, BaseMemory] = dict(
            stores or {"working": WorkingMemory(self.config)}
        )
        if not self._stores:
            raise ValueError("at least one memory store must be enabled.")
        for memory_type, store in self._stores.items():
            if memory_type != store.memory_type:
                raise ValueError("memory store key does not match its memory_type.")

    @property
    def enabled_types(self) -> tuple[MemoryType, ...]:
        return tuple(self._stores)

    def add_memory(
        self,
        *,
        user_id: str,
        content: str,
        memory_type: MemoryType = "working",
        importance: float = 0.5,
        metadata: Mapping[str, Any] | None = None,
        ttl_seconds: int | None = None,
    ) -> MemoryItem:
        store = self._require_store(memory_type)
        now = utc_now()
        expires_at = None
        if memory_type == "working":
            ttl = (
                self.config.working_memory_ttl_seconds
                if ttl_seconds is None
                else ttl_seconds
            )
            if ttl <= 0:
                raise ValueError("ttl_seconds must be positive.")
            expires_at = now + timedelta(seconds=ttl)
        item = MemoryItem(
            user_id=user_id,
            content=content,
            memory_type=memory_type,
            importance=importance,
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
            metadata=dict(metadata or {}),
        )
        store.add(item)
        return item

    def retrieve_memories(
        self,
        *,
        user_id: str,
        query: str,
        memory_types: Sequence[MemoryType] | None = None,
        limit: int = 5,
        min_importance: float = 0.0,
    ) -> list[MemorySearchResult]:
        if limit <= 0:
            raise ValueError("limit must be positive.")
        selected = tuple(memory_types or self.enabled_types)
        if not selected:
            raise ValueError("at least one memory type must be selected.")

        results: list[MemorySearchResult] = []
        for memory_type in selected:
            store = self._require_store(memory_type)
            results.extend(
                store.retrieve(
                    query,
                    user_id=user_id,
                    limit=limit,
                    min_importance=min_importance,
                )
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

    def update_memory(
        self,
        *,
        user_id: str,
        memory_id: str,
        content: str | None = None,
        importance: float | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> MemoryItem:
        changes = {
            key: value
            for key, value in {
                "content": content,
                "importance": importance,
                "metadata": dict(metadata) if metadata is not None else None,
            }.items()
            if value is not None
        }
        for store in self._stores.values():
            if store.get(memory_id, user_id=user_id) is not None:
                return store.update(
                    memory_id,
                    user_id=user_id,
                    changes=changes,
                )
        raise KeyError(f"memory '{memory_id}' was not found.")

    def remove_memory(self, *, user_id: str, memory_id: str) -> bool:
        return any(
            store.remove(memory_id, user_id=user_id)
            for store in self._stores.values()
        )

    def list_memories(
        self,
        *,
        user_id: str,
        memory_type: MemoryType,
    ) -> list[MemoryItem]:
        """Return one user's authoritative records for a declared memory type."""
        return self._require_store(memory_type).list(user_id=user_id)

    def forget_memories(
        self,
        *,
        user_id: str,
        strategy: ForgetStrategy,
        threshold: float = 0.1,
        max_age_days: int = 30,
    ) -> int:
        return sum(
            store.forget(
                user_id=user_id,
                strategy=strategy,
                threshold=threshold,
                max_age_days=max_age_days,
            )
            for store in self._stores.values()
        )

    def clear_memories(self, *, user_id: str) -> int:
        return sum(store.clear(user_id=user_id) for store in self._stores.values())

    def get_memory_stats(self, *, user_id: str) -> dict[str, Any]:
        by_type: dict[str, dict[str, float | int]] = {}
        total = 0
        for memory_type, store in self._stores.items():
            items = store.list(user_id=user_id)
            count = len(items)
            total += count
            by_type[memory_type] = {
                "count": count,
                "average_importance": (
                    sum(item.importance for item in items) / count if count else 0.0
                ),
            }
        return {
            "user_id": user_id,
            "enabled_types": list(self.enabled_types),
            "total_memories": total,
            "memories_by_type": by_type,
        }

    def _require_store(self, memory_type: MemoryType) -> BaseMemory:
        try:
            return self._stores[memory_type]
        except KeyError as error:
            raise ValueError(
                f"memory type '{memory_type}' is not enabled; "
                f"enabled types: {', '.join(self.enabled_types)}"
            ) from error


__all__ = ["MemoryManager"]
