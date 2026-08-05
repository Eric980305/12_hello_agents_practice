"""Replaceable text-embedding boundary for persistent memory."""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from openai import OpenAI


@runtime_checkable
class TextEmbedder(Protocol):
    """Return fixed-size vectors through single or bounded batch requests."""

    @property
    def dimension(self) -> int: ...

    def embed(self, text: str) -> list[float]: ...

    def embed_many(self, texts: Sequence[str]) -> list[list[float]]: ...


class OpenAICompatibleEmbedding:
    """Use an OpenAI-compatible embeddings endpoint, including Bailian."""

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        base_url: str,
        dimension: int,
        timeout: float = 30.0,
    ) -> None:
        self.model = self._required_text(model, "model")
        self._dimension = self._positive_int(dimension, "dimension")
        self._client = OpenAI(
            api_key=self._required_text(api_key, "api_key"),
            base_url=self._required_text(base_url, "base_url"),
            timeout=timeout,
        )

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, text: str) -> list[float]:
        return self.embed_many([text])[0]

    def embed_many(
        self,
        texts: Sequence[str],
        *,
        batch_size: int = 25,
    ) -> list[list[float]]:
        """Embed multiple texts using the provider's bounded array input."""
        if not texts:
            return []
        if not 1 <= batch_size <= 25:
            raise ValueError("batch_size must be between 1 and 25.")
        normalized = [self._required_text(text, "text") for text in texts]
        vectors: list[list[float]] = []
        for start in range(0, len(normalized), batch_size):
            batch = normalized[start : start + batch_size]
            response = self._client.embeddings.create(
                model=self.model,
                input=batch,
                dimensions=self.dimension,
            )
            data = sorted(response.data or [], key=lambda item: item.index)
            if len(data) != len(batch):
                raise RuntimeError("embedding provider returned an incomplete batch.")
            for item in data:
                vector = [float(value) for value in item.embedding]
                if len(vector) != self.dimension:
                    raise RuntimeError(
                        f"embedding dimension mismatch: expected {self.dimension}, "
                        f"received {len(vector)}."
                    )
                vectors.append(vector)
        return vectors

    @classmethod
    def from_env(cls) -> "OpenAICompatibleEmbedding":
        """Build the provider at the application boundary without loading .env."""
        api_key = os.getenv("EMBED_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
        base_url = os.getenv("EMBED_BASE_URL")
        model = os.getenv("EMBED_MODEL_NAME", "text-embedding-v4")
        dimension = os.getenv("QDRANT_VECTOR_SIZE", "1024")
        if not api_key or not base_url:
            raise RuntimeError("EMBED_API_KEY and EMBED_BASE_URL are required.")
        return cls(
            model=model,
            api_key=api_key,
            base_url=base_url,
            dimension=cls._positive_int(dimension, "QDRANT_VECTOR_SIZE"),
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
        try:
            converted = int(value)
        except (TypeError, ValueError) as error:
            raise TypeError(f"{name} must be an integer.") from error
        if converted <= 0:
            raise ValueError(f"{name} must be positive.")
        return converted


__all__ = ["OpenAICompatibleEmbedding", "TextEmbedder"]
