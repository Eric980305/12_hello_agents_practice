# Intelligent Expert Platform PRD

## Goal

Replace the product-facing Gradio implementation with a maintainable frontend/backend application while preserving the existing Gradio app.

## Users and value

Chinese users create private expert teams, use a shared general expert, upload source documents, ask source-grounded questions, record notes, and review session statistics.

## Scope

- Registration, login, logout, and persistent browser sessions.
- Shared `通用专家` and user-owned experts.
- Document upload, search, listing, and deletion per expert.
- Expert-scoped chat with optional advanced retrieval.
- Expert-scoped notes and session statistics.
- Personal center with username, VIP1 status, zero balance, and logout.
- Responsive desktop and mobile layouts.

## Acceptance criteria

- The legacy `apps.pdf_learning_assistant` remains unchanged and runnable.
- The backend starts without requiring Qdrant; unavailable RAG operations return a clear 503 response.
- A user can register, log in, refresh without losing the session, create/delete private experts, and cannot delete the shared expert.
- `所有专家` exposes only `通用专家` plus the current user's private experts.
- The frontend has distinct routes for login, registration, chat, experts, statistics, and profile.
- Backend automated tests and frontend production build pass.

## Out of scope

- Payments, editable VIP tiers, social login providers, production deployment, and migration away from the existing SQLite/Qdrant storage.

