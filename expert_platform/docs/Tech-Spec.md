# Technical Specification

## Architecture

- `frontend/`: React + TypeScript + Vite + React Router. It owns rendering and browser interaction only.
- `backend/`: FastAPI. It owns authentication, authorization, validation, orchestration, and API responses.
- `hello_agents_framework/`: existing framework reused for document metadata, RAG indexing/retrieval, and LLM calls.
- `memory_data/practice_memory.db`: existing SQLite database, extended with web sessions, messages, and notes.

## Security boundaries

- The browser receives an opaque HttpOnly session cookie.
- Every private-expert operation verifies ownership in the backend.
- Uploaded filenames are normalized and stored below a controlled knowledge-base directory.
- API inputs are validated by typed schemas; secrets are read only through existing environment configuration.

## Runtime behavior

- Startup creates local SQLite tables and the shared expert metadata.
- RAGTool instances are created only for an operation that needs indexing or retrieval.
- Chat retrieval is restricted to one concrete expert; the aggregate `所有专家` selection is not accepted for chat or upload.
- Document deletion removes metadata and vector records through the existing RAG boundary when available.

## Verification

- FastAPI tests cover authentication, session persistence, expert isolation, and protected shared resources.
- TypeScript compilation and Vite production build verify the frontend.
- A local smoke check calls the health endpoint and loads the built frontend.

