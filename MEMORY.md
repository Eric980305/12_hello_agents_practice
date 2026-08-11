# Project Memory

## Durable decisions

- The original Gradio application is retained as a runnable historical implementation.
- The new product-facing implementation lives in `expert_platform/` and separates a FastAPI backend from a React TypeScript frontend.
- Existing framework components remain the source of truth for user accounts, knowledge metadata, RAG indexing, retrieval, and model access.
- `通用专家` is shared by all users. A private expert belongs to exactly one user. `所有专家` is a read-only aggregate view of the shared expert plus the signed-in user's private experts.
- Authentication uses an opaque server-side session stored in SQLite and an HttpOnly cookie; passwords remain managed by the existing `UserAccountStore`.
- RAG resources are initialized lazily so login, expert management, and metadata browsing remain available when Qdrant or an embedding provider is unavailable.
- The workspace root is the shared configuration boundary for the numbered projects: the root `.env` contains model and service settings, while `workspace_llm.py` is a compatibility client used only by projects that explicitly import it. Project 12 does not depend on `workspace_llm.py`; its reusable `hello_agents_framework` reads the same environment through its own `core/config.py`, `core/llm.py`, and embedding adapters. The historical Gradio app and the `expert_platform` web application should load the root `.env` but obtain Agent, tool, memory, RAG, and LLM behavior from `hello_agents_framework`. UI, authentication/session handling, authorization, product workflow, and domain policy remain application-layer responsibilities.
