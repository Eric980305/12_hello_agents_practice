# Expert Platform Web

Vue 3 + TypeScript frontend and FastAPI backend for the version 0.3.0 Intelligent
Expert Platform. The existing Gradio application remains available through
`python -m apps.pdf_learning_assistant`.

## Architecture

```text
frontend/               Vue, TypeScript, Vite, Vue Router, Pinia
backend/app/main.py     FastAPI routes and transaction boundary
backend/app/services.py authentication sessions and assistant lifecycle
backend/app/admin_deletion.py
                        shared administrative deletion domain logic
cli/                    local administrator and deletion commands
apps/pdf_learning_assistant.py
                        reused product service
hello_agents_framework/
                        LLM, Agent, memory, RAG, tools, and adapters
```

The frontend never accesses SQLite, Qdrant, model providers, or uploaded files
directly. FastAPI validates each request and delegates product operations to the
existing `PDFLearningAssistant`, which already composes `hello_agents_framework`.

The `/reports` page reads the signed-in user's complete `qa_interaction` records from
the previous 30 days, groups them by expert, and generates one personal monthly
summary. Notes are no longer part of the product. New snapshots are stored under the user's `monthly_personal_reports/`
directory; legacy `learning_reports/` files remain untouched.

## Development

Install the shared Python environment from the workspace root, then install the
frontend dependencies:

```bash
cd /Users/eric/Documents/Codex/Hello-agent-v0.0.1
.venv/bin/python -m pip install -r requirements.txt

cd projects/12_hello_agents_practice/expert_platform/frontend
pnpm install
```

Start the backend from the project directory:

```bash
cd /Users/eric/Documents/Codex/Hello-agent-v0.0.1/projects/12_hello_agents_practice
../../.venv/bin/python -m uvicorn expert_platform.backend.app.main:app \
  --host 127.0.0.1 --port 8000 --reload
```

Start the frontend in a second terminal:

```bash
cd /Users/eric/Documents/Codex/Hello-agent-v0.0.1/projects/12_hello_agents_practice/expert_platform/frontend
pnpm dev
```

Open <http://127.0.0.1:5173/>. Vite proxies `/api` to FastAPI. The backend loads
the shared workspace `.env`; it does not import `workspace_llm.py` and instead uses
the local framework adapters already composed by the product service.

Qdrant and the configured embedding/model services must be available before using
document ingestion or chat. The separated backend deliberately does not own Docker
startup or shutdown.

## Administrator access

The admin console is part of the same website at `/admin`; it does not use a second
port. The navigation item appears only after the backend reports an active admin role,
and every `/api/admin/*` request independently checks that role in SQLite.

Create the first administrator from a local terminal. The password is read with
hidden input, must contain at least 12 characters, and is never accepted as a
command-line argument:

```bash
cd /Users/eric/Documents/Codex/Hello-agent-v0.0.1/projects/12_hello_agents_practice
../../.venv/bin/python -m expert_platform.cli.manage_admin create admin
```

Existing accounts can be granted or revoked explicitly, and current administrators
can be listed without exposing credential material:

```bash
../../.venv/bin/python -m expert_platform.cli.manage_admin grant USERNAME
../../.venv/bin/python -m expert_platform.cli.manage_admin revoke USERNAME
../../.venv/bin/python -m expert_platform.cli.manage_admin list
```

Revocation removes that account's active sessions. Registering an account named
`admin` through the website does not grant any privilege.

## Administrative deletion

Stop the FastAPI backend before destructive maintenance so an in-flight upload cannot
write data while the stores are being cleaned. Run the command once without
`--execute` to inspect the resolved owner, namespace, row counts, Qdrant point counts,
and filesystem targets:

```bash
cd /Users/eric/Documents/Codex/Hello-agent-v0.0.1/projects/12_hello_agents_practice

../../.venv/bin/python -m expert_platform.cli.delete_data user \
  --user-id USER_ID_1 USER_ID_2

../../.venv/bin/python -m expert_platform.cli.delete_data expert \
  --user-id USER_ID --expert-id EXPERT_ID_1 EXPERT_ID_2

../../.venv/bin/python -m expert_platform.cli.delete_data document \
  --user-id USER_ID --expert-id EXPERT_ID \
  --document-id DOCUMENT_ID_1 DOCUMENT_ID_2
```

After reviewing the dry-run output, repeat the same command with `--execute`. The
command asks for the target ID again for one item, or `DELETE N` for a batch of N
items. `--execute --yes` is available only for an already-reviewed non-interactive
invocation. Expert batches belong to one supplied user, and document batches belong
to one supplied user/expert pair, so the CLI never guesses cross-owner mappings.

The shared expert is protected. Expert deletion removes its catalog, documents,
chunks, source directory, and RAG points but intentionally retains historical Q&A
events for monthly reports. User deletion also invalidates sessions and removes the
user's episodic memories, monthly reports, and episodic vectors.

All batch targets are validated before confirmation. Execution is sequential because
SQLite, Qdrant, and the filesystem cannot provide one distributed transaction across
multiple targets; if a later target fails, completed earlier targets stay deleted and
the command reports the completed count.

## Production build

```bash
cd expert_platform/frontend
pnpm build

cd ../..
../../.venv/bin/python -m uvicorn expert_platform.backend.app.main:app \
  --host 127.0.0.1 --port 8000
```

When `frontend/dist/` exists, FastAPI serves the generated SPA and preserves Vue
Router history fallback. Open <http://127.0.0.1:8000/>.

## Verification

```bash
../../.venv/bin/python -m unittest discover -s expert_platform/backend/tests -v
../../.venv/bin/python -m compileall -q expert_platform

cd expert_platform/frontend
pnpm typecheck
pnpm build
```

See `docs/PRD.md`, `docs/Tech-Spec.md`, and `docs/api-contract.md` before changing
product behavior or the HTTP boundary.
