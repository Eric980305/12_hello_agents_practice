# Changelog

This file records user-visible milestones for `12_hello_agents_practice`.

## [Unreleased]

## [0.2.1] - 2026-08-08

### Changed

- Simplified knowledge-base management and added safe deletion for personal knowledge bases.
- Refined document search, table layout, uploader spacing, dialogs, and responsive presentation.
- Reduced the document table to the user-facing fields: file name, owning knowledge base, and operation.
- Strengthened shared/private knowledge-base isolation and repeated-switching regression coverage.

## [0.2.0] - 2026-08-07

### Milestone: Multi-user Intelligent Knowledge Base

### Added

- Added local user registration, login, session restoration, logout, and owner-scoped knowledge-base management.
- Added one system-owned shared knowledge base that all authenticated users can read from and upload to.
- Added per-user private knowledge bases, document and note isolation, current-session Q&A reports, and regression coverage for two-user access boundaries.

### Changed

- Renamed the learning project directory from `12_hello_agents_framework` to `12_hello_agents_practice`.
- Renamed the local framework import package from `hello_agents_practice` to `hello_agents_framework`; the official dependency continues to use `hello_agents`.
- Kept existing Qdrant collection names and browser-storage keys stable so the rename does not orphan persisted data.
- Made intelligent Q&A the authenticated landing page while preserving the active module across refreshes and resetting it after logout.
- Defined `所有知识库` as a read-only aggregate of the shared library plus the current user's private libraries.
- Corrected document switching, dynamic table height, upload reset, per-library duplicate detection, and Bailian embedding batch limits.
- Refined desktop and mobile authentication, knowledge management, uploader, dropdown, and dialog presentation with recorded visual QA evidence.

### Release boundary

- Authentication and sessions are local application mechanisms, not production SSO or federated identity.
- Shared-library writes are open to every authenticated user in this learning milestone; production deployment still requires role-based authorization, hardened server-side sessions, CSRF protection, rate limiting, and account recovery.
- Runtime databases, uploaded documents, generated reports, secrets, and vector-database state remain outside Git and require separate backup.

## [0.1.0] - 2026-08-05

### Milestone: Intelligent Knowledge Management Platform

- Built the local framework (then imported as `hello_agents_practice`) with message, configuration, model, Agent, tool registry, and bounded orchestration contracts.
- Implemented Simple, ReAct, Reflection, Plan-and-Solve, and native function-calling Agent patterns.
- Added working and episodic memory, document storage, Qdrant-backed retrieval, RAG ingestion, optional MQE/HyDE expansion, and reranking integration.
- Added a Gradio document assistant with multiple knowledge bases, scoped document and note management, automatic document ingestion, OCR support, scoped Q&A, and learning statistics.
- Added local Qdrant and Neo4j infrastructure through Docker Compose.
- Established deterministic offline tests and separated runtime data, uploaded documents, reports, caches, and secrets from source control.

### Release boundary

- This is a learning and customization milestone, not a production release.
- External model, embedding, reranking, OCR, Qdrant, and Neo4j behavior still depends on runtime configuration and service availability.
- Runtime databases and user-uploaded content are intentionally excluded from Git and require separate backup when their data must be preserved.
