"""Small Qdrant adapter for memory vectors."""

from __future__ import annotations

import os
from dataclasses import dataclass
from collections.abc import Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from qdrant_client import QdrantClient, models


@dataclass(frozen=True)
class VectorSearchHit:
    memory_id: str
    score: float


@dataclass(frozen=True)
class VectorQueryHit:
    point_id: str
    score: float
    payload: dict[str, Any]


@runtime_checkable
class VectorStore(Protocol):
    def upsert(self, *, memory_id: str, vector: list[float], payload: dict[str, Any]) -> None: ...

    def search(
        self,
        *,
        vector: list[float],
        user_id: str,
        memory_type: str,
        min_importance: float,
        limit: int,
    ) -> list[VectorSearchHit]: ...

    def delete(self, memory_id: str) -> None: ...


class QdrantVectorStore:
    """Store derived vectors and lookup payload; never store source documents."""

    def __init__(
        self,
        *,
        collection_name: str,
        vector_size: int,
        url: str = "http://localhost:6333",
        api_key: str | None = None,
        timeout: float = 30.0,
        client: QdrantClient | None = None,
    ) -> None:
        self.collection_name = self._required_text(collection_name, "collection_name")
        self.vector_size = self._positive_int(vector_size, "vector_size")
        self.client = client or QdrantClient(
            url=self._required_text(url, "url"),
            api_key=api_key or None,
            timeout=timeout,
        )
        self._ensure_collection()

    def upsert(
        self,
        *,
        memory_id: str,
        vector: list[float],
        payload: dict[str, Any],
    ) -> None:
        self._validate_vector(vector)
        self.client.upsert(
            collection_name=self.collection_name,
            points=[models.PointStruct(id=memory_id, vector=vector, payload=payload)],
            wait=True,
        )

    def upsert_many(
        self,
        points: Sequence[tuple[str, list[float], dict[str, Any]]],
        *,
        batch_size: int = 64,
    ) -> None:
        """Write validated vectors in bounded Qdrant requests."""
        if not 1 <= batch_size <= 1_000:
            raise ValueError("batch_size must be between 1 and 1000.")
        for start in range(0, len(points), batch_size):
            batch = points[start : start + batch_size]
            structs = []
            for memory_id, vector, payload in batch:
                self._validate_vector(vector)
                structs.append(
                    models.PointStruct(
                        id=memory_id,
                        vector=vector,
                        payload=payload,
                    )
                )
            if structs:
                self.client.upsert(
                    collection_name=self.collection_name,
                    points=structs,
                    wait=True,
                )

    def search(
        self,
        *,
        vector: list[float],
        user_id: str,
        memory_type: str,
        min_importance: float,
        limit: int,
    ) -> list[VectorSearchHit]:
        self._validate_vector(vector)
        points = self.query(
            vector=vector,
            matches={"user_id": user_id, "memory_type": memory_type},
            ranges={"importance": (min_importance, None)},
            limit=limit,
        )
        hits = []
        for point in points:
            memory_id = point.payload.get("memory_id")
            if isinstance(memory_id, str):
                hits.append(VectorSearchHit(memory_id=memory_id, score=point.score))
        return hits

    def query(
        self,
        *,
        vector: list[float],
        matches: Mapping[str, str | bool],
        limit: int,
        ranges: Mapping[str, tuple[float | None, float | None]] | None = None,
        score_threshold: float | None = None,
    ) -> list[VectorQueryHit]:
        """Query by declared payload filters for memory or RAG callers."""
        self._validate_vector(vector)
        conditions = [
            models.FieldCondition(key=key, match=models.MatchValue(value=value))
            for key, value in matches.items()
        ]
        for key, (minimum, maximum) in (ranges or {}).items():
            conditions.append(
                models.FieldCondition(
                    key=key,
                    range=models.Range(gte=minimum, lte=maximum),
                )
            )
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=vector,
            query_filter=models.Filter(must=conditions),
            limit=limit,
            with_payload=True,
            with_vectors=False,
            score_threshold=score_threshold,
        )
        hits = []
        for point in response.points:
            payload = point.payload or {}
            hits.append(
                VectorQueryHit(
                    point_id=str(point.id),
                    score=max(0.0, min(1.0, float(point.score))),
                    payload=dict(payload),
                )
            )
        return hits

    def delete(self, memory_id: str) -> None:
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=[memory_id],
            wait=True,
        )

    @classmethod
    def from_env(
        cls,
        *,
        vector_size: int,
        collection_name: str | None = None,
    ) -> "QdrantVectorStore":
        collection = collection_name or os.getenv(
            "PRACTICE_EPISODIC_QDRANT_COLLECTION",
            f"hello_agents_practice_episodic_{vector_size}",
        )
        return cls(
            collection_name=collection,
            vector_size=vector_size,
            url=os.getenv("QDRANT_URL", "http://localhost:6333"),
            api_key=os.getenv("QDRANT_API_KEY") or None,
            timeout=float(os.getenv("QDRANT_TIMEOUT", "30")),
        )

    def _ensure_collection(self) -> None:
        if not self.client.collection_exists(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=self.vector_size,
                    distance=models.Distance.COSINE,
                ),
            )
            return
        info = self.client.get_collection(self.collection_name)
        vectors = info.config.params.vectors
        size = getattr(vectors, "size", None)
        if size != self.vector_size:
            raise ValueError(
                f"Qdrant collection '{self.collection_name}' has vector size "
                f"{size}, expected {self.vector_size}."
            )

    def _validate_vector(self, vector: list[float]) -> None:
        if len(vector) != self.vector_size:
            raise ValueError(
                f"vector has size {len(vector)}, expected {self.vector_size}."
            )

    @staticmethod
    def _required_text(value: str, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string.")
        return value.strip()

    @staticmethod
    def _positive_int(value: object, name: str) -> int:
        if isinstance(value, bool):
            raise TypeError(f"{name} must be an integer.")
        converted = int(value)
        if converted <= 0:
            raise ValueError(f"{name} must be positive.")
        return converted


__all__ = [
    "QdrantVectorStore",
    "VectorQueryHit",
    "VectorSearchHit",
    "VectorStore",
]
