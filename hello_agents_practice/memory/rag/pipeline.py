"""Attributable text indexing and retrieval pipeline."""

from __future__ import annotations

import re
from math import ceil
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from ...core.llm import HelloAgentsLLM
from ..embedding import TextEmbedder
from ..storage import QdrantVectorStore, SQLiteKnowledgeStore
from .document import Document, DocumentProcessor


class QueryExpander(Protocol):
    def expand(self, query: str, count: int) -> list[str]: ...

    def hypothetical_document(self, query: str) -> str | None: ...


class LLMQueryExpander:
    """Use a configured chat model only to propose additional retrieval text."""

    def __init__(self, llm: HelloAgentsLLM) -> None:
        self.llm = llm

    def expand(self, query: str, count: int) -> list[str]:
        response = self.llm.invoke(
            [
                {
                    "role": "system",
                    "content": (
                        "你是检索查询扩展助手。生成语义等价或互补的中文查询，"
                        "每行一个，不要解释。"
                    ),
                },
                {
                    "role": "user",
                    "content": f"原始查询：{query}\n请生成 {count} 个不同表述。",
                },
            ]
        )
        queries = []
        for line in response.splitlines():
            normalized = re.sub(r"^\s*(?:[-*]|\d+[.、)])\s*", "", line).strip()
            if normalized:
                queries.append(normalized)
        return queries[:count]

    def hypothetical_document(self, query: str) -> str | None:
        response = self.llm.invoke(
            [
                {
                    "role": "system",
                    "content": (
                        "根据问题写一段用于向量检索的客观假设答案。"
                        "只输出答案性段落，不要分析过程。"
                    ),
                },
                {"role": "user", "content": f"问题：{query}"},
            ]
        ).strip()
        return response or None


class RAGSearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    content: str
    score: float = Field(ge=0.0, le=1.0)
    document_id: str
    chunk_id: str
    chunk_index: int = Field(ge=0)
    namespace: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RAGPipeline:
    """Keep source text in SQLite and derived retrieval vectors in Qdrant."""

    def __init__(
        self,
        *,
        namespace: str,
        document_store: SQLiteKnowledgeStore,
        vector_store: QdrantVectorStore,
        embedder: TextEmbedder,
        processor: DocumentProcessor | None = None,
        query_expander: QueryExpander | None = None,
    ) -> None:
        if not namespace.strip():
            raise ValueError("namespace must not be empty.")
        self.namespace = namespace.strip()
        self.document_store = document_store
        self.vector_store = vector_store
        self.embedder = embedder
        self.processor = processor or DocumentProcessor()
        self.query_expander = query_expander

    def add_text(
        self,
        *,
        text: str,
        document_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, int | str]:
        document = Document(
            id=document_id,
            namespace=self.namespace,
            content=text,
            metadata=dict(metadata or {}),
        )
        chunks = self.processor.split(document)
        if not chunks:
            raise ValueError("document produced no searchable chunks.")

        old_ids = set(
            self.document_store.get_chunk_ids(
                namespace=self.namespace,
                document_id=document.id,
            )
        )
        new_ids = {chunk.id for chunk in chunks}
        vectors = self._embed_many(
            [self.processor.text_for_embedding(chunk) for chunk in chunks]
        )
        points = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            if len(vector) != self.embedder.dimension:
                raise RuntimeError("embedder returned an unexpected vector dimension.")
            points.append(
                (
                    chunk.id,
                    vector,
                    {
                        "chunk_id": chunk.id,
                        "document_id": document.id,
                        "rag_namespace": self.namespace,
                        "is_rag_data": True,
                        "chunk_index": chunk.index,
                    },
                )
            )
        bulk_upsert = getattr(self.vector_store, "upsert_many", None)
        if callable(bulk_upsert):
            bulk_upsert(points)
        else:
            for memory_id, vector, payload in points:
                self.vector_store.upsert(
                    memory_id=memory_id,
                    vector=vector,
                    payload=payload,
                )

        self.document_store.replace_document(document, chunks)
        for stale_id in old_ids - new_ids:
            self.vector_store.delete(stale_id)
        return {
            "document_id": document.id,
            "chunks_indexed": len(chunks),
        }

    def add_document(
        self,
        *,
        file_path: str | Path,
        document_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, int | str]:
        document = self.processor.load_file(
            file_path,
            namespace=self.namespace,
            document_id=document_id,
            metadata=metadata,
        )
        return self.add_text(
            text=document.content,
            document_id=document.id,
            metadata=document.metadata,
        )

    def has_document(self, document_id: str) -> bool:
        """Return whether this namespace already has an authoritative document."""
        return self.document_store.has_document(
            namespace=self.namespace,
            document_id=document_id,
        )

    def list_documents(self) -> list[dict[str, object]]:
        return self.document_store.list_documents(namespace=self.namespace)

    def delete_document(self, document_id: str) -> dict[str, object] | None:
        document = self.document_store.get_document(
            namespace=self.namespace,
            document_id=document_id,
        )
        if document is None:
            return None
        chunk_ids = self.document_store.get_chunk_ids(
            namespace=self.namespace,
            document_id=document_id,
        )
        for chunk_id in chunk_ids:
            self.vector_store.delete(chunk_id)
        if not self.document_store.delete_document(
            namespace=self.namespace,
            document_id=document_id,
        ):
            raise RuntimeError("authoritative document deletion failed.")
        return document

    def search(
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
        if not query.strip():
            raise ValueError("query must not be empty.")
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100.")
        if not 0.0 <= min_score <= 1.0:
            raise ValueError("min_score must be between 0 and 1.")
        if not 1 <= mqe_expansions <= 10:
            raise ValueError("mqe_expansions must be between 1 and 10.")
        if not 1 <= candidate_pool_multiplier <= 20:
            raise ValueError("candidate_pool_multiplier must be between 1 and 20.")

        queries = self._expanded_queries(
            query.strip(),
            enable_mqe=enable_mqe,
            mqe_expansions=mqe_expansions,
            enable_hyde=enable_hyde,
        )
        per_query = (
            max(limit * 3, 10)
            if not enable_mqe and not enable_hyde
            else max(
                limit,
                ceil(limit * candidate_pool_multiplier / len(queries)),
            )
        )
        hits_by_chunk = {}
        query_vectors = self._embed_many(queries)
        for _, vector in zip(queries, query_vectors, strict=True):
            if len(vector) != self.embedder.dimension:
                raise RuntimeError("embedder returned an unexpected vector dimension.")
            hits = self.vector_store.query(
                vector=vector,
                matches={"rag_namespace": self.namespace, "is_rag_data": True},
                limit=per_query,
                score_threshold=min_score,
            )
            for hit in hits:
                chunk_id = hit.payload.get("chunk_id")
                if not isinstance(chunk_id, str):
                    continue
                current = hits_by_chunk.get(chunk_id)
                if current is None or hit.score > current.score:
                    hits_by_chunk[chunk_id] = hit

        hits = sorted(
            hits_by_chunk.values(),
            key=lambda hit: hit.score,
            reverse=True,
        )
        chunk_ids = [
            chunk_id
            for hit in hits
            if isinstance((chunk_id := hit.payload.get("chunk_id")), str)
        ]
        chunks = self.document_store.get_chunks(
            chunk_ids,
            namespace=self.namespace,
        )
        results = []
        for hit in hits:
            chunk_id = hit.payload.get("chunk_id")
            chunk = chunks.get(chunk_id) if isinstance(chunk_id, str) else None
            if chunk is None:
                continue
            results.append(
                RAGSearchResult(
                    content=chunk.content,
                    score=hit.score,
                    document_id=chunk.document_id,
                    chunk_id=chunk.id,
                    chunk_index=chunk.index,
                    namespace=chunk.namespace,
                    metadata=chunk.metadata,
                )
            )
        return results[:limit]

    def _expanded_queries(
        self,
        query: str,
        *,
        enable_mqe: bool,
        mqe_expansions: int,
        enable_hyde: bool,
    ) -> list[str]:
        if not enable_mqe and not enable_hyde:
            return [query]
        if self.query_expander is None:
            raise RuntimeError("MQE/HyDE requires a configured query expander.")

        candidates = [query]
        if enable_mqe:
            candidates.extend(self.query_expander.expand(query, mqe_expansions))
        if enable_hyde:
            hypothetical = self.query_expander.hypothetical_document(query)
            if hypothetical:
                candidates.append(hypothetical)

        unique = []
        seen = set()
        for candidate in candidates:
            normalized = candidate.strip()
            identity = normalized.casefold()
            if normalized and identity not in seen:
                unique.append(normalized)
                seen.add(identity)
        return unique

    def _embed_many(self, texts: list[str]) -> list[list[float]]:
        batch_embed = getattr(self.embedder, "embed_many", None)
        if callable(batch_embed):
            return batch_embed(texts)
        return [self.embedder.embed(text) for text in texts]

    def stats(self) -> dict[str, int | str]:
        return {
            "namespace": self.namespace,
            **self.document_store.stats(namespace=self.namespace),
        }


__all__ = ["LLMQueryExpander", "QueryExpander", "RAGPipeline", "RAGSearchResult"]
