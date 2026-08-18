# Changelog

This file records user-visible milestones for `12_hello_agents_practice`.

## [Unreleased]

## [0.3.0] - 2026-08-18

### Milestone: Secure Expert Platform Administration

### Added

- Added a dry-run-first local administration script for owner-validated deletion of
  users, private experts, or individual expert documents across SQLite, retained
  files, and the active RAG/episodic Qdrant collections.
- Added direct list arguments for deleting multiple users, multiple experts under one
  user, or multiple documents under one expert with one preflight and confirmation.
- Added an authenticated same-site administration console for global user, expert,
  and document inspection with deterministic pagination, retained-file disk usage,
  protected deletion previews, and metadata-only audit events.
- Added dependency-free Simplified Chinese and English interface switching across
  authentication, Q&A, experts, reports, profiles, and administration.
- Added 10-record pagination to expert-document management after scope and search
  filtering.

### Removed

- Removed note creation and browsing from the Vue frontend, FastAPI API, shared
  assistant service, and Gradio UI.
- Removed persisted `learning_note` events and their derived episodic Qdrant points
  without affecting completed Q&A used by monthly reports.

### Changed

- Tightened the existing `expert_web_sessions` lifecycle without adding session
  entities: startup and login remove expired/orphaned rows, resolution removes an
  expired or orphaned presented token, re-login replaces only the current browser
  session, and logout remains successful when the server-side row is already absent.
- Replaced the current-session inquiry-statistics surface with a personal monthly
  report covering the signed-in user's previous 30 days of completed expert Q&A.
- Persist complete question/answer pairs in existing user-scoped `qa_interaction`
  episodic records so reporting survives logout, independent browser sessions, and
  backend restarts.
- Group monthly summaries by the expert identity recorded at conversation time and
  limit model input to the newest 30 turns per expert.
- Save one atomic snapshot per user and generation month under
  `monthly_personal_reports/`; existing `learning_reports/` files remain untouched.
- Moved local administrator and destructive-maintenance commands under
  `expert_platform.cli`, with shared deletion planning in the backend domain module.
- Added immutable-user-ID administrator roles, bounded login-rate limiting,
  same-origin checks for destructive browser requests, hardened response headers,
  and immediate session invalidation after role revocation.

### Verified

- Added focused Session coverage for startup cleanup, lazy expiry deletion,
  current-browser re-login replacement, valid multi-browser preservation, and
  idempotent logout.
- Added focused coverage for durable report input, expert grouping, rolling-window
  filtering, incomplete legacy records, and the monthly API contract.
- Added isolated cross-store deletion tests for namespace isolation, shared-expert
  protection, stale vector cleanup, and SQLite rollback when Qdrant fails.
- Verified the complete Python suite, FastAPI integration suite, frontend type check,
  production build, and desktop/mobile browser behavior for the release.

## [0.2.3] - 2026-08-12

### Milestone: Intelligent Expert Platform

### Added

- Rebuilt `expert_platform/` as a routed Vue 3 and TypeScript frontend with a FastAPI backend.
- Added explicit HTTP contracts for authentication, experts, documents, grounded chat, notes, session statistics, and real-Q&A reports.
- Added durable hashed web sessions, streamed upload staging, safe API error boundaries, backend integration tests, and desktop/mobile browser QA.

### Changed

- Repositioned the user-facing product from a knowledge-base manager to an intelligent expert platform: users assemble experts, supply source material, ask source-grounded questions, and preserve expert-scoped notes.
- Kept `apps.pdf_learning_assistant.PDFLearningAssistant` as the shared application service so Gradio and the separated API execute the same `hello_agents_framework` memory, RAG, LLM, and storage paths.

### Release boundary

- The Gradio entry point remains supported and unchanged.
- Web sessions are durable, while assistant objects, conversations, and current-session counters remain process-local.
- Production SSO, account recovery, RBAC, CSRF tokens, rate limiting, audit logging, distributed jobs, and deployment automation remain outside this learning release.

## [0.2.2] - 2026-08-09

### Fixed

- Made the knowledge-base manager table resize immediately after catalog creation or deletion.
- Refined the create-knowledge-base and manager dialogs to use a single responsive surface without residual mobile whitespace.
- Added regression coverage for dynamic manager-table row counts and height updates.

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
