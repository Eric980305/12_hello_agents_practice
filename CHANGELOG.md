# Changelog

This file records user-visible milestones for `12_hello_agents_framework`.

## [0.1.0] - 2026-08-05

### Milestone: Intelligent Knowledge Management Platform

- Built the local `hello_agents_practice` framework with message, configuration, model, Agent, tool registry, and bounded orchestration contracts.
- Implemented Simple, ReAct, Reflection, Plan-and-Solve, and native function-calling Agent patterns.
- Added working and episodic memory, document storage, Qdrant-backed retrieval, RAG ingestion, optional MQE/HyDE expansion, and reranking integration.
- Added a Gradio document assistant with multiple knowledge bases, scoped document and note management, automatic document ingestion, OCR support, scoped Q&A, and learning statistics.
- Added local Qdrant and Neo4j infrastructure through Docker Compose.
- Established deterministic offline tests and separated runtime data, uploaded documents, reports, caches, and secrets from source control.

### Release boundary

- This is a learning and customization milestone, not a production release.
- External model, embedding, reranking, OCR, Qdrant, and Neo4j behavior still depends on runtime configuration and service availability.
- Runtime databases and user-uploaded content are intentionally excluded from Git and require separate backup when their data must be preserved.

