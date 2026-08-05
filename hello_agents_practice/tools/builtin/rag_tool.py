"""RAGTool facade for attributable text indexing and retrieval."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from ...memory import OpenAICompatibleEmbedding
from ...memory.rag import QueryExpander, RAGPipeline, RAGSearchResult
from ...memory.storage import QdrantVectorStore, SQLiteKnowledgeStore
from ..base import Tool


class RAGTool(Tool):
    name = "rag"
    description = "Index trusted text and retrieve namespace-scoped source chunks."

    _parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add_document", "add_text", "search", "stats"],
                "description": "RAG operation to execute.",
            },
            "text": {"type": "string", "description": "Trusted source text."},
            "file_path": {
                "type": "string",
                "description": "File inside knowledge_base_path to ingest.",
            },
            "document_id": {
                "type": "string",
                "description": "Stable source document identifier.",
            },
            "metadata": {
                "type": "object",
                "description": "Source metadata retained with every chunk.",
            },
            "query": {"type": "string", "description": "Knowledge query."},
            "limit": {
                "type": "integer",
                "description": "Maximum number of source chunks.",
            },
            "min_score": {
                "type": "number",
                "description": "Minimum vector similarity from 0.0 to 1.0.",
            },
            "enable_mqe": {
                "type": "boolean",
                "description": "Use LLM-generated alternative queries.",
            },
            "mqe_expansions": {
                "type": "integer",
                "description": "Number of MQE alternatives from 1 to 10.",
            },
            "enable_hyde": {
                "type": "boolean",
                "description": "Use an LLM-generated hypothetical answer for retrieval.",
            },
            "candidate_pool_multiplier": {
                "type": "integer",
                "description": "Candidate pool multiplier from 1 to 20.",
            },
        },
        "required": ["action"],
        "additionalProperties": False,
    }

    def __init__(
        self,
        knowledge_base_path: str = "./knowledge_base",
        qdrant_url: str | None = None,
        qdrant_api_key: str | None = None,
        collection_name: str | None = None,
        rag_namespace: str = "default",
        *,
        database_path: str | Path | None = None,
        pipeline: RAGPipeline | None = None,
        query_expander: QueryExpander | None = None,
    ) -> None:
        self.knowledge_base_path = Path(knowledge_base_path).expanduser().resolve()
        self.knowledge_base_path.mkdir(parents=True, exist_ok=True)
        if pipeline is None:
            embedder = OpenAICompatibleEmbedding.from_env()
            collection = collection_name or os.getenv(
                "PRACTICE_RAG_QDRANT_COLLECTION",
                f"hello_agents_practice_rag_{embedder.dimension}",
            )
            vector_store = QdrantVectorStore(
                collection_name=collection,
                vector_size=embedder.dimension,
                url=qdrant_url or os.getenv("QDRANT_URL", "http://localhost:6333"),
                api_key=qdrant_api_key or os.getenv("QDRANT_API_KEY") or None,
                timeout=float(os.getenv("QDRANT_TIMEOUT", "30")),
            )
            pipeline = RAGPipeline(
                namespace=rag_namespace,
                document_store=SQLiteKnowledgeStore(
                    database_path or self.knowledge_base_path / "knowledge.db"
                ),
                vector_store=vector_store,
                embedder=embedder,
                query_expander=query_expander,
            )
        elif pipeline.namespace != rag_namespace:
            raise ValueError("pipeline namespace does not match rag_namespace.")
        elif query_expander is not None:
            raise ValueError("configure query_expander on the injected pipeline.")
        self.pipeline = pipeline

    @property
    def parameters(self) -> dict[str, Any]:
        return deepcopy(self._parameters)

    def run(self, parameters: Mapping[str, Any]) -> str:
        if not isinstance(parameters, Mapping):
            raise TypeError("rag tool parameters must be a mapping.")
        values = dict(parameters)
        action = values.pop("action", None)
        return self.execute(action, **values)

    def execute(self, action: Any, **kwargs: Any) -> str:
        normalized = self._required_text(action, "action")
        handlers: dict[str, Callable[..., str]] = {
            "add_document": self._add_document,
            "add_text": self._add_text,
            "search": self._search,
            "stats": self._stats,
        }
        try:
            return handlers[normalized](**kwargs)
        except KeyError as error:
            raise ValueError(f"unsupported RAG action: {normalized}") from error

    def _add_document(
        self,
        *,
        file_path: Any,
        document_id: Any = None,
        metadata: Any = None,
    ) -> str:
        path = self._knowledge_file(file_path)
        if metadata is not None and not isinstance(metadata, Mapping):
            raise TypeError("metadata must be an object.")
        relative_path = path.relative_to(self.knowledge_base_path).as_posix()
        result = self.pipeline.add_document(
            file_path=path,
            document_id=(
                relative_path
                if document_id is None
                else self._required_text(document_id, "document_id")
            ),
            metadata=dict(metadata or {}),
        )
        return (
            f"文档已索引：document_id={result['document_id']} "
            f"chunks={result['chunks_indexed']} source={relative_path}"
        )

    def _add_text(
        self,
        *,
        text: Any,
        document_id: Any,
        metadata: Any = None,
    ) -> str:
        if metadata is not None and not isinstance(metadata, Mapping):
            raise TypeError("metadata must be an object.")
        result = self.pipeline.add_text(
            text=self._required_text(text, "text"),
            document_id=self._required_text(document_id, "document_id"),
            metadata=dict(metadata or {}),
        )
        return (
            f"知识已索引：document_id={result['document_id']} "
            f"chunks={result['chunks_indexed']}"
        )

    def _search(
        self,
        *,
        query: Any,
        limit: Any = 5,
        min_score: Any = 0.0,
        enable_mqe: Any = False,
        mqe_expansions: Any = 2,
        enable_hyde: Any = False,
        candidate_pool_multiplier: Any = 4,
    ) -> str:
        results = self.retrieve(
            query=self._required_text(query, "query"),
            limit=self._integer(limit, "limit", minimum=1, maximum=100),
            min_score=self._float(min_score, "min_score"),
            enable_mqe=self._boolean(enable_mqe, "enable_mqe"),
            mqe_expansions=self._integer(
                mqe_expansions,
                "mqe_expansions",
                minimum=1,
                maximum=10,
            ),
            enable_hyde=self._boolean(enable_hyde, "enable_hyde"),
            candidate_pool_multiplier=self._integer(
                candidate_pool_multiplier,
                "candidate_pool_multiplier",
                minimum=1,
                maximum=20,
            ),
        )
        if not results:
            return "未找到相关知识。"
        lines = [f"找到 {len(results)} 条相关知识："]
        lines.extend(
            f"{index}. {result.content} "
            f"(score={result.score:.3f}, source={result.document_id}, "
            f"chunk={result.chunk_index})"
            for index, result in enumerate(results, 1)
        )
        return "\n".join(lines)

    def retrieve(
        self,
        *,
        query: str,
        limit: int = 5,
        min_score: float = 0.0,
        enable_mqe: bool = False,
        mqe_expansions: int = 2,
        enable_hyde: bool = False,
        candidate_pool_multiplier: int = 4,
    ) -> list[RAGSearchResult]:
        """Return typed source evidence for application-layer answer generation."""
        return self.pipeline.search(
            query=query,
            limit=limit,
            min_score=min_score,
            enable_mqe=enable_mqe,
            mqe_expansions=mqe_expansions,
            enable_hyde=enable_hyde,
            candidate_pool_multiplier=candidate_pool_multiplier,
        )

    def has_document(self, document_id: str) -> bool:
        """Check the authoritative namespace before spending ingestion resources."""
        return self.pipeline.has_document(
            self._required_text(document_id, "document_id")
        )

    def list_documents(self) -> list[dict[str, object]]:
        """Return document summaries for the application management boundary."""
        return self.pipeline.list_documents()

    def delete_document(self, document_id: str) -> dict[str, object] | None:
        """Delete one exact document without exposing deletion to model tool calls."""
        return self.pipeline.delete_document(
            self._required_text(document_id, "document_id")
        )

    def stats(self) -> dict[str, int | str]:
        return {
            **self.pipeline.stats(),
            "knowledge_base_path": str(self.knowledge_base_path),
        }

    def _stats(self) -> str:
        return json.dumps(
            self.stats(),
            ensure_ascii=False,
            sort_keys=True,
        )

    def _knowledge_file(self, value: Any) -> Path:
        raw_path = Path(self._required_text(value, "file_path")).expanduser()
        path = raw_path.resolve() if raw_path.is_absolute() else (
            self.knowledge_base_path / raw_path
        ).resolve()
        if not path.is_relative_to(self.knowledge_base_path):
            raise PermissionError("file_path must stay inside knowledge_base_path.")
        if not path.is_file():
            raise FileNotFoundError(f"knowledge file was not found: {path.name}")
        return path

    @staticmethod
    def _required_text(value: Any, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string.")
        return value.strip()

    @staticmethod
    def _integer(value: Any, name: str, *, minimum: int, maximum: int) -> int:
        if isinstance(value, bool):
            raise TypeError(f"{name} must be an integer.")
        try:
            converted = int(value)
        except (TypeError, ValueError) as error:
            raise TypeError(f"{name} must be an integer.") from error
        if isinstance(value, float) and not value.is_integer():
            raise TypeError(f"{name} must be an integer.")
        if not minimum <= converted <= maximum:
            raise ValueError(f"{name} is outside the allowed range.")
        return converted

    @staticmethod
    def _float(value: Any, name: str) -> float:
        if isinstance(value, bool):
            raise TypeError(f"{name} must be a number.")
        try:
            converted = float(value)
        except (TypeError, ValueError) as error:
            raise TypeError(f"{name} must be a number.") from error
        if not 0.0 <= converted <= 1.0:
            raise ValueError(f"{name} must be between 0 and 1.")
        return converted

    @staticmethod
    def _boolean(value: Any, name: str) -> bool:
        if not isinstance(value, bool):
            raise TypeError(f"{name} must be a boolean.")
        return value


__all__ = ["RAGTool"]
