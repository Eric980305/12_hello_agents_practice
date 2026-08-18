# Intelligent Expert Platform PRD

## Goal

Rebuild the current `apps.pdf_learning_assistant` Gradio product as an easy-to-read,
frontend/backend-separated web application while keeping the Gradio entry point
runnable.

The new application must preserve the product behavior documented for version 0.2.3:
authenticated users assemble an expert team, give each expert source documents, ask
source-grounded questions, and review their recent month of conversations across
experts.

## Users and value

- A signed-in user can use the shared expert and create private experts for distinct
  domains.
- Documents and retrieval stay inside the selected expert boundary. Monthly
  reports are user-scoped and group that user's recent conversations by expert.
- Answers expose their source evidence and decline when the selected expert has no
  sufficient source material.
- The separated codebase lets the product UI and API evolve without coupling product
  work to Gradio callback internals.

## Product surfaces

- `/login`: sign in with a local account.
- `/register`: create a local account, then return to sign in.
- `/chat`: select one concrete expert, ask grounded questions, enable advanced
  retrieval, and inspect source references.
- `/experts`: browse documents across accessible experts, select one expert
  for writes, upload/search/delete documents, create/delete private experts.
- `/reports`: generate a personal summary from real Q&A completed during the previous
  30 days, grouped by expert.
- `/profile`: view account information and sign out.
- `/admin`: allow configured administrators to inspect global platform counts, search
  users, experts, and documents, preview the complete impact of a deletion, and
  execute that deletion only after exact-ID confirmation.

## Permission model

- `共享专家库` is visible to every authenticated user and cannot be deleted.
- A private expert belongs to exactly one user and is invisible to other users.
- `所有专家` is a read-only aggregate for document browsing only.
- Upload, question, document deletion, and expert deletion require a concrete
  authorized expert.
- Deleting a private expert requires explicit confirmation and removes its derived
  vectors, authoritative document/chunk records, retained files, and catalog record.
- Administrative routes require both a valid session and an administrator role in
  SQLite. Ordinary users receive no admin navigation and a direct request is rejected
  with `403`; registering the username `admin` alone never grants that role.
- The shared expert catalog is protected from deletion. Its documents may be managed
  individually because they are writable product data, but deleting a user or private
  expert never crosses into the shared namespace.

## Acceptance criteria

- The legacy `python -m apps.pdf_learning_assistant` entry remains runnable, with its
  note controls removed alongside the separated application.
- The Vue application has real routes for every product surface above and works at
  desktop and mobile widths.
- Refreshing the browser restores a valid authenticated session through an opaque
  HttpOnly cookie; logout invalidates it.
- The backend owns validation, authorization, business transactions, framework calls,
  and safe error mapping. The browser never connects directly to SQLite, Qdrant,
  embedding, or chat-model services.
- Document ingestion retains the existing 50 MB limit, supported-format allowlist,
  SHA-256 idempotency, parser, embedding, and Qdrant indexing behavior.
- Basic and MQE/HyDE retrieval, grounded LLM answers, source labels, and durable
  real-Q&A records preserve the Gradio semantics.
- Clicking the monthly-summary action reads only the signed-in user's completed Q&A
  from the previous 30 days, groups it by expert, and asks the configured chat model
  to summarize those records.
- One generated JSON report per user and generation month is stored under
  `monthly_personal_reports/<user_scope>/`; regenerating in the same month replaces
  that month's report atomically.
- The frontend exposes no note controls, the backend exposes no note endpoints, and
  persisted `learning_note` rows plus their same-ID Qdrant points are removed without
  touching other episodic events.
- Backend automated tests and the frontend type check and production build pass.
- A real browser run verifies login, navigation, responsive layout, and representative
  authenticated workflows without console errors or horizontal overflow.
- Admin API tests prove role enforcement, global list scoping, protected targets,
  exact-ID confirmation, Qdrant-failure rollback, and successful user/expert/document
  cleanup against temporary SQLite, filesystem, and fake-vector stores.
- Repeated failed logins are rate-limited. Destructive admin requests require a
  same-origin browser request, record a metadata-only audit event after success, and
  never allow an administrator account to delete itself or another administrator.
- Admin user, expert, and document tables expose retained source-file bytes, sorted
  by that value descending before pagination. User totals sum all managed documents
  owned by that user; expert totals sum documents in that expert; document totals are
  the individual retained source file. Missing, invalid, or out-of-root paths count as
  zero and never disclose arbitrary filesystem metadata.
- The expert document table displays 10 matching records per page. Changing expert
  scope or submitting a new search returns to page one; deletion moves to the previous
  page when the current last page becomes empty.

## Out of scope

- Rewriting `hello_agents_framework`.
- Removing or refactoring the Gradio product.
- Production deployment, payments, editable VIP tiers, SSO, account recovery, general
  multi-role RBAC, dedicated CSRF tokens, distributed sessions, or cross-process job
  queues.
- Admin-side account creation, password reset, privilege editing, expert creation,
  document upload, bulk deletion, data editing, or Qdrant point-level browsing.
- Recovering answers from legacy `qa_interaction` records that stored only questions.
- Migrating or deleting existing files under `learning_reports/`.
