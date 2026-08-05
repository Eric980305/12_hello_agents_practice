"""Validated contracts shared by the practice memory subsystem."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


MemoryType = Literal["working", "episodic", "semantic", "perceptual"]
ForgetStrategy = Literal["importance_based", "time_based", "capacity_based"]


def utc_now() -> datetime:
    """Return an aware UTC timestamp."""
    return datetime.now(timezone.utc)


class MemoryConfig(BaseModel):
    """Configure only the memory behavior implemented in the current stage."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    working_memory_capacity: int = Field(default=50, gt=0, le=10_000)
    working_memory_ttl_seconds: int = Field(default=7_200, gt=0)
    episodic_memory_capacity: int = Field(default=10_000, gt=0, le=1_000_000)
    episodic_recency_half_life_days: float = Field(default=30.0, gt=0.0)


class MemoryItem(BaseModel):
    """Represent one user-scoped memory record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(default_factory=lambda: str(uuid4()), min_length=1)
    user_id: str = Field(min_length=1)
    content: str = Field(min_length=1)
    memory_type: MemoryType
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id", "user_id", "content")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized

    @field_validator("created_at", "updated_at", "expires_at")
    @classmethod
    def require_aware_datetime(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("memory timestamps must include a timezone")
        return value

    def is_expired(self, now: datetime | None = None) -> bool:
        return self.expires_at is not None and self.expires_at <= (now or utc_now())


class MemorySearchResult(BaseModel):
    """Keep retrieval score separate from the stored memory record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    memory: MemoryItem
    score: float = Field(ge=0.0, le=1.0)


class BaseMemory(ABC):
    """Define the stable behavior required from each memory type."""

    memory_type: MemoryType

    @abstractmethod
    def add(self, item: MemoryItem) -> str:
        raise NotImplementedError

    @abstractmethod
    def retrieve(
        self,
        query: str,
        *,
        user_id: str,
        limit: int,
        min_importance: float,
    ) -> list[MemorySearchResult]:
        raise NotImplementedError

    @abstractmethod
    def get(self, memory_id: str, *, user_id: str) -> MemoryItem | None:
        raise NotImplementedError

    @abstractmethod
    def update(
        self,
        memory_id: str,
        *,
        user_id: str,
        changes: Mapping[str, Any],
    ) -> MemoryItem:
        raise NotImplementedError

    @abstractmethod
    def remove(self, memory_id: str, *, user_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def list(self, *, user_id: str) -> list[MemoryItem]:
        raise NotImplementedError

    @abstractmethod
    def forget(
        self,
        *,
        user_id: str,
        strategy: ForgetStrategy,
        threshold: float,
        max_age_days: int,
    ) -> int:
        raise NotImplementedError

    @abstractmethod
    def clear(self, *, user_id: str) -> int:
        raise NotImplementedError


__all__ = [
    "BaseMemory",
    "ForgetStrategy",
    "MemoryConfig",
    "MemoryItem",
    "MemorySearchResult",
    "MemoryType",
    "utc_now",
]
