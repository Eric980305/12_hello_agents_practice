"""In-process Working Memory with user isolation, capacity, and TTL."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import timedelta
from threading import RLock
from typing import Any

from ..base import (
    BaseMemory,
    ForgetStrategy,
    MemoryConfig,
    MemoryItem,
    MemorySearchResult,
    utc_now,
)


TOKEN_PATTERN = re.compile(r"[0-9a-zA-Z_]+|[\u4e00-\u9fff]")


class WorkingMemory(BaseMemory):
    """Store temporary records for the lifetime of the current process."""

    memory_type = "working"

    def __init__(self, config: MemoryConfig | None = None) -> None:
        self.config = config or MemoryConfig()
        self._items: dict[str, MemoryItem] = {}
        self._lock = RLock()

    def add(self, item: MemoryItem) -> str:
        if item.memory_type != self.memory_type:
            raise ValueError("WorkingMemory accepts working records only.")
        with self._lock:
            self._prune_expired(user_id=item.user_id)
            if item.id in self._items:
                raise ValueError(f"memory '{item.id}' already exists.")
            self._items[item.id] = item
            self._enforce_capacity(item.user_id)
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

        with self._lock:
            self._prune_expired(user_id=user_id)
            results = []
            for item in self._items.values():
                if item.user_id != user_id or item.importance < min_importance:
                    continue
                relevance = self._text_relevance(normalized_query, item.content)
                if relevance == 0.0:
                    continue
                score = min(1.0, relevance * 0.8 + item.importance * 0.2)
                results.append(MemorySearchResult(memory=item, score=score))

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
        with self._lock:
            self._prune_expired(user_id=user_id)
            item = self._items.get(memory_id)
            return item if item is not None and item.user_id == user_id else None

    def update(
        self,
        memory_id: str,
        *,
        user_id: str,
        changes: Mapping[str, Any],
    ) -> MemoryItem:
        allowed = {"content", "importance", "metadata", "expires_at"}
        unexpected = set(changes) - allowed
        if unexpected:
            raise ValueError(f"unsupported memory updates: {sorted(unexpected)}")
        if not changes:
            raise ValueError("at least one memory field must be updated.")

        with self._lock:
            item = self.get(memory_id, user_id=user_id)
            if item is None:
                raise KeyError(f"memory '{memory_id}' was not found.")
            updated = item.model_copy(
                update={**dict(changes), "updated_at": utc_now()},
            )
            updated = MemoryItem.model_validate(updated.model_dump())
            self._items[memory_id] = updated
            return updated

    def remove(self, memory_id: str, *, user_id: str) -> bool:
        with self._lock:
            item = self._items.get(memory_id)
            if item is None or item.user_id != user_id:
                return False
            del self._items[memory_id]
            return True

    def list(self, *, user_id: str) -> list[MemoryItem]:
        with self._lock:
            self._prune_expired(user_id=user_id)
            return sorted(
                (item for item in self._items.values() if item.user_id == user_id),
                key=lambda item: item.created_at,
            )

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

        with self._lock:
            removed = self._prune_expired(user_id=user_id)
            items = [item for item in self._items.values() if item.user_id == user_id]
            if strategy == "importance_based":
                candidates = [item for item in items if item.importance < threshold]
            elif strategy == "time_based":
                cutoff = utc_now() - timedelta(days=max_age_days)
                candidates = [item for item in items if item.created_at < cutoff]
            elif strategy == "capacity_based":
                excess = max(0, len(items) - self.config.working_memory_capacity)
                candidates = sorted(items, key=lambda item: item.created_at)[:excess]
            else:
                raise ValueError(f"unsupported forgetting strategy: {strategy}")

            for item in candidates:
                removed += int(self.remove(item.id, user_id=user_id))
            return removed

    def clear(self, *, user_id: str) -> int:
        with self._lock:
            ids = [
                item.id for item in self._items.values() if item.user_id == user_id
            ]
            for memory_id in ids:
                del self._items[memory_id]
            return len(ids)

    def _prune_expired(self, *, user_id: str) -> int:
        now = utc_now()
        ids = [
            item.id
            for item in self._items.values()
            if item.user_id == user_id and item.is_expired(now)
        ]
        for memory_id in ids:
            del self._items[memory_id]
        return len(ids)

    def _enforce_capacity(self, user_id: str) -> None:
        items = sorted(
            (item for item in self._items.values() if item.user_id == user_id),
            key=lambda item: item.created_at,
        )
        excess = len(items) - self.config.working_memory_capacity
        for item in items[:max(0, excess)]:
            del self._items[item.id]

    @staticmethod
    def _required_text(value: str, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must not be empty.")
        return value.strip().casefold()

    @staticmethod
    def _text_relevance(query: str, content: str) -> float:
        normalized_content = content.casefold()
        if query in normalized_content:
            return 1.0
        query_tokens = set(TOKEN_PATTERN.findall(query))
        content_tokens = set(TOKEN_PATTERN.findall(normalized_content))
        if not query_tokens or not content_tokens:
            return 0.0
        return len(query_tokens & content_tokens) / len(query_tokens)


__all__ = ["WorkingMemory"]
