# Technical Specification

## Architecture

- `frontend/`: Vue 3, TypeScript, Vite, Vue Router, and Pinia. It owns rendering,
  browser interaction, route guards, and API presentation state only.
- `backend/`: FastAPI on Python 3.12. It owns authentication, authorization,
  validation, upload staging, business orchestration, and API responses.
- `apps.pdf_learning_assistant.PDFLearningAssistant`: reused as the current product
  service so both UIs execute one business path while the separated application is
  established.
- `hello_agents_framework/`: remains the source of truth for LLM, embedding, memory,
  SQLite knowledge metadata, Qdrant retrieval, and RAG tools.

The backend may import application services from `apps/`, and those services may
compose `hello_agents_framework`. The frontend must depend only on the documented
HTTP API.

## Runtime boundaries

- The workspace-root `.env` is loaded once at the backend application boundary.
- SQLite stores accounts, authoritative product metadata, and completed Q&A events.
- Qdrant stores derived vectors; the configured embedding and chat providers are
  contacted only for document indexing, retrieval expansion, answers, and reports.
- One in-process assistant is created lazily for each authenticated browser session,
  so two logins to the same account do not share current-session UI history or
  counters. Completed Q&A is also written to the user's durable episodic memory so a
  monthly report can span browser sessions and backend restarts.
- The backend does not start or stop Docker implicitly. Infrastructure is an explicit
  local operation so frontend/backend process lifecycle does not own persistent data
  services.

## Security and data rules

- Session tokens are random, stored only as SHA-256 hashes in SQLite, and sent through
  an HttpOnly, SameSite=Lax cookie. Secure cookies are enabled by configuration for
  HTTPS deployments.
- `expert_web_sessions` is the only durable authentication-session entity. Backend
  initialization and token creation remove expired rows and rows whose account no
  longer exists; resolving an expired or orphaned presented token removes that exact
  row. The expiry column is indexed for bounded cleanup cost.
- A successful login replaces only the session cookie already presented by that
  browser. Other valid browser/device sessions remain independent. Closing a browser
  is not logout, and the service does not evict valid sessions by creation age or a
  per-user count cap.
- Logout is idempotent: it deletes the presented token and in-process assistant when
  present, always expires the browser cookie, and returns `204` even when the database
  row is already missing or expired.
- Every private-expert and expert-scoped operation resolves access from the live
  SQLite catalog before executing.
- Uploads are streamed to a temporary file with an enforced size limit; filenames
  never select a destination path. The existing product service performs suffix,
  size, digest, retention, and index validation.
- API errors expose stable Chinese messages without provider response bodies, paths,
  credentials, or raw exceptions.
- Registration, login, document deletion, and expert deletion preserve deterministic
  validation and confirmation checks outside model control.
- Admin authorization is an explicit SQLite role keyed by immutable user ID. The
  local `expert_platform/cli/manage_admin.py` command is the only privilege-management
  boundary in this release; public registration cannot grant roles. Route visibility
  in Vue is convenience only and never substitutes for FastAPI authorization.
- Login attempts are rate-limited per client/normalized username in the current
  backend process. Sensitive admin POSTs validate `Origin`, successful deletions write
  a metadata-only audit event, and authentication/admin responses are marked
  `Cache-Control: no-store`.
- Responses set content-sniffing, framing, referrer, and Content Security Policy
  headers. Production enables the existing Secure cookie setting behind HTTPS; ports
  or hidden navigation are never treated as a permission boundary.

## API and session model

- JSON uses camelCase for public fields. Query parameters use snake_case only where
  FastAPI multipart/form handling makes the mapping explicit in the contract.
- `GET /api/auth/me` is the browser session authority.
- `GET /api/bootstrap` returns the current user, accessible experts, and the session
  identifier needed by the UI.
- Aggregate expert selection is accepted only for document listing.
- RAG-dependent endpoints return HTTP 503 with a safe, user-readable message when an
  external resource is unavailable.
- Advanced MQE/HyDE retrieval is best-effort: if its additional provider calls fail,
  the assistant retries once with ordinary vector retrieval. If final answer
  generation fails after evidence was retrieved, the response degrades to attributed
  source excerpts instead of discarding the successful retrieval result. Degraded
  responses state which fallback was used so users do not mistake them for full
  advanced-search results.
- Runtime logs record only redacted exception class names for failed chat requests;
  provider response bodies, credentials, and user questions are not logged.

## Monthly personal reports

- A completed Q&A turn is stored as an existing `qa_interaction` episodic record with
  structured `question`, `answer`, expert ID/name, source chunk IDs, session ID, and
  timestamp metadata. The existing `episodic_memories.user_id` boundary remains the
  report authorization boundary; no report query accepts a browser-supplied user ID.
- `POST /api/reports/monthly` uses a rolling 30-day UTC window ending at generation
  time. It excludes legacy or incomplete events without a stored answer, groups the
  remaining records by their recorded expert identity, and sends at most the newest
  30 turns per expert to the configured chat model.
- Historical records retain the expert name captured at conversation time, so deleting
  an expert does not erase the user's conversation history or break later reporting.
- Reports are written atomically to
  `monthly_personal_reports/<user_scope>/monthly_personal_report_YYYY-MM.json`.
  Repeated generation in one month refreshes that month's snapshot instead of creating
  unbounded session files. Existing `learning_reports/` files remain untouched.

## Note feature retirement

- Remove note controls and note browsing from both Vue and Gradio surfaces.
- Remove the `/api/notes` contract, request schema, service adapters, and shared
  `PDFLearningAssistant` note methods. Monthly reports continue to read only complete
  `qa_interaction` events.
- Existing notes are `learning_note` rows in the shared `episodic_memories` table, not
  a separate table. Delete only those rows and their same-ID points from the episodic
  Qdrant collection; retain the table, its user/time index, and all other event types.

## Verification

- Unit and API integration tests use temporary SQLite/filesystem state and fake
  assistants so they make no LLM, embedding, Qdrant, Docker, or network request.
- Existing project tests protect the reused Gradio/framework behavior.
- `vue-tsc --noEmit` and `vite build` are frontend gates.
- Browser QA covers login, register navigation, route guards, expert selection,
  responsive navigation, modal/dialog states, mobile overflow, and console errors.

## Intentional simplifications

- The first separated release reuses `PDFLearningAssistant` instead of copying its
  business logic into a second service hierarchy. Extract a framework-independent
  application service only after both UIs need independently evolving behavior.
- Runtime assistant sessions remain process-local, matching the current learning
  product. Add durable/distributed session state only when multi-process deployment
  becomes an actual requirement.

## Frontend internationalization

- The Vue client owns interface localization. The initial locale catalog contains
  `zh-CN` and `en-US`; adding a language means adding another complete catalog and a
  selector option, without changing backend contracts.
- The selected locale is stored under `expert-platform:locale` in browser
  `localStorage`, independently of authentication, and updates the document language,
  title, dates, and all product-owned UI copy immediately.
- User content, filenames, custom expert names, model answers, monthly report content,
  and backend-provided error/result messages are not machine-translated. They remain
  source data rather than interface copy.
- A dependency-free catalog is intentional at the current two-locale scale. Adopt a
  dedicated i18n library only when pluralization, locale-aware routing, lazy-loaded
  catalogs, or translator tooling becomes a demonstrated requirement.

## Document upload target consistency

- The expert selected in the document page's browse scope is the single source of
  truth for both document listing and upload. Upload requests must send that expert's
  ID rather than the separately persisted chat expert selection.
- `所有专家` is an aggregate read view and therefore has no valid upload target. The
  upload action stays disabled until the user selects `共享专家库` or a private expert.
- Browser acceptance checks cover switching between two private experts and the
  aggregate view, on desktop and mobile viewports.
- Expert-document reads return `{ items, total }`. The web service filters and sorts
  the accessible result set before applying bounded `limit`/`offset`; the Vue table
  requests a fixed page size of 10 and resets its offset when scope or search changes.
  The current assistant adapter still enumerates accessible document summaries before
  slicing; move pagination into the document store only when measured catalog size
  makes that metadata scan a bottleneck.

## Administrative deletion CLI

- `expert_platform/backend/app/admin_deletion.py` owns the deterministic deletion
  planner and executor shared by HTTP administration and local maintenance.
  `expert_platform/cli/delete_data.py` is a thin offline command boundary for deleting
  one user, one private expert, or one expert-owned document. FastAPI must be stopped
  before destructive CLI execution.
- SQLite resolves account ownership and the stored namespace from the exact supplied
  IDs. Command-line values never select a namespace or filesystem destination by
  themselves. The shared owner and `default` expert are protected.
- Commands are dry-run by default and show SQLite rows, Qdrant points, and filesystem
  targets. Execution requires `--execute` plus an exact interactive target-ID
  confirmation, unless the operator deliberately supplies `--yes`. The CLI accepts
  multiple user IDs, multiple expert IDs under one user, or multiple document IDs
  under one user/expert pair. It validates the full batch before one confirmation and
  rejects duplicate IDs.
- SQLite changes run in one immediate transaction. Qdrant deletion happens before
  that transaction commits, so a Qdrant failure rolls SQLite back and leaves source
  files untouched. Because SQLite and Qdrant cannot share one transaction, a user
  deletion that fails between Qdrant collections may have removed some derived
  vectors; rerunning is safe because SQLite remains authoritative. Files are deleted
  only after both active data stores succeed.
- Batch targets execute sequentially after complete preflight. Cross-target atomicity
  is intentionally not claimed: if a later target fails, earlier completed targets
  remain deleted and the CLI reports how many finished.
- Document deletion uses the owner/expert namespace plus document ID. Expert deletion
  removes that namespace's RAG data but preserves historical episodic Q&A. User
  deletion removes sessions, private catalogs, documents/chunks, episodic records,
  monthly reports, and both RAG and episodic vectors. User cleanup also scans RAG
  payloads for stale user namespaces that no longer have SQLite catalog rows.

## Administrative web console

- The web console intentionally reuses the authenticated application shell and lives
  at `/admin`; the user-facing site and admin console share one origin and deployment.
  Its visual source of truth is the generated desktop concept
  `exec-67b44fff-f88c-4de7-a8df-b16b4610b60e.png`: true-white chrome,
  cool-gray canvas, indigo selection, compact metrics, tabbed table workspace, and a
  focused destructive-impact modal. Existing typography, spacing, borders, Tabler
  icons, and responsive breakpoints remain authoritative.
- The frontend exposes users, experts, and documents as table views with search,
  ownership filters, refresh, empty/loading/error states, and horizontal mobile table
  scrolling. No charts, inline editing, fake trends, or duplicated creation/upload
  controls are introduced.
- The backend reads global summaries directly from SQLite without returning document
  or chunk bodies. Pagination is bounded and deterministic. Document display metadata
  is parsed defensively; invalid metadata never becomes executable input.
- Disk usage is the current `stat().st_size` of each retained source path in document
  metadata. A SQLite scalar function registered on each admin connection validates
  that the resolved regular file remains inside `knowledge_base/`, returns zero for
  missing/invalid paths, and lets SQLite aggregate and order usage before pagination.
  This intentionally excludes shared SQLite/Qdrant/index overhead because those bytes
  cannot be attributed faithfully to one document. Filesystem-stat cost is linear in
  matched managed documents; persist a trusted size column only if measured scale
  makes that read path too slow.
- `expert_platform.backend.app.admin_deletion` remains the single deletion planner
  and executor for SQLite, Qdrant, and retained files. The web service wraps the same target and plan
  contracts, adds administrator/self-protection and exact-ID HTTP confirmation, and
  invalidates affected process-local assistants after success. The admin role is
  resolved again for every API request, so revocation takes effect immediately; the
  local revoke command also deletes that account's active sessions.
- Deletion is synchronous and single-target in this release. The existing SQLite-first
  transaction, Qdrant rollback behavior, and post-commit filesystem cleanup semantics
  are preserved. Bulk operations and background jobs wait for measured operational
  need.
- The shared catalog remains undeletable. Individual shared documents are valid admin
  targets and resolve only through the canonical `__shared__/default` namespace and
  `knowledge_base/shared/default` filesystem root.
