# Project Rules

- Keep the existing Gradio application under `apps/` unchanged unless a task explicitly targets it.
- Build the separated web application under `expert_platform/`.
- Reuse `hello_agents_framework` for RAG, storage, LLM, and memory behavior; do not duplicate those mechanisms in the web layer.
- Backend code uses FastAPI and Python 3.12. Frontend code uses Vue 3, TypeScript, Vite, Vue Router, and Pinia.
- Keep API contracts explicit in `expert_platform/docs/api-contract.md`.
- Run backend tests and the frontend production build before reporting completion.
- Chinese UI copy is intentional because the product targets Chinese users.
