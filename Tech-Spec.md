# Technical Specification

## Objective

Build the framework incrementally under the unique import name `hello_agents_framework`, without shadowing or replacing the official `hello-agents==0.2.0` textbook baseline imported as `hello_agents`.

## Current Scope

- Preserve the existing OpenAI-compatible implementation in `hello_agents_framework/core/llm.py`.
- Implement `core/message.py` as the framework's validated internal message format.
- Implement `core/config.py` around the workspace's generic `LLM_*` environment contract without assuming OpenAI or a particular model ID.
- Implement `core/agent.py` as the abstract execution contract with bounded shared history behavior.
- Implement `agents/simple_agent.py` as the first concrete agent with direct conversation, bounded text-protocol tool calls, streaming, and explicit tool management.
- Implement `agents/react_agent.py` as a bounded one-action-per-step ReAct loop over the shared LLM, Message, Agent, and ToolRegistry contracts.
- Implement `agents/reflection_agent.py` as a bounded, task-generic initial → reflect → refine loop with replaceable prompt templates and an inspectable per-run trajectory.
- Implement `agents/plan_solve_agent.py` as a bounded plan → sequential solve → final synthesis workflow with safe Python-list parsing, explicit step state, prompt overrides, and failure termination.
- Implement `agents/function_call_agent.py` as a bounded native Chat Completions tool-calling loop that builds JSON schemas from registered tools, validates model arguments, executes only allowlisted tools, and feeds tool results back with matching call IDs.
- Implement the minimum tool boundary required by SimpleAgent: `Tool`, `ToolRegistry`, and a safe arithmetic-only `CalculatorTool`.
- Add `FunctionTool` as the single-path adapter for ordinary Python callables; `ToolRegistry.register_function()` must wrap and delegate to `register_tool()` rather than maintaining a second function registry.
- Implement `tools/builtin/search.py` as one stateful `SearchTool(Tool)` with explicit `hybrid`, `tavily`, and `serpapi` modes, deterministic Tavily-first fallback, and one normalized sourced text result contract.
- Implement `tools/chain.py` as a deterministic sequential composition layer over `ToolRegistry`, using structured parameter templates and named prior outputs rather than a second tool-dispatch mechanism.
- Implement `tools/async_executor.py` as a bounded adapter for existing synchronous tools using `asyncio.to_thread`, ordered fan-out results, timeouts, and structured task ownership.
- Keep the remaining planned modules as empty placeholders until their lessons are implemented.
- Keep the official-package quickstart in `examples/official_quickstart.py`, outside the local package directory so it imports the installed distribution.
- Keep real local integration examples under `examples/`; existing examples cover Simple, ReAct, Reflection, and Plan-and-Solve flows, while `local_function_call_agent.py` checks whether the configured OpenAI-compatible provider actually supports native `tools` and `tool_calls`.
- Keep this source tree isolated from projects 01–11 and from the shared environment's import path.
- Implement Chapter 8 Stage 1 as a local, dependency-free Working Memory vertical slice: validated memory records and configuration, one user-scoped TTL/capacity store, a coordinating `MemoryManager`, a registered `MemoryTool`, deterministic offline tests, and a local example. Semantic, Episodic, Perceptual, persistence, embedding, rerank, and RAG remain outside this stage even though their external resources have already been verified through the official-package examples.
- Extend the attributable RAG pipeline with opt-in MQE and HyDE query expansion. The original query remains authoritative, an injected LLM-backed expander may add bounded alternatives, and SQLite-backed source chunks are returned only after namespace-filtered Qdrant candidates are merged and deduplicated.
- Add a Chapter 8 knowledge-base learning application outside the reusable framework package. It composes `RAGTool`, `MemoryTool`, and the configured LLM into multi-format document ingestion, source-backed question answering, recall, durable monthly personal reports, and a session-isolated Gradio UI.

## Constraints

- Never create or install a local package named `hello_agents`; that import name is reserved for the official PyPI distribution.
- Keep the local teaching implementation under the unambiguous `hello_agents_framework` import name.
- Do not add this project directory to a global `PYTHONPATH`.
- Do not implement future framework modules ahead of their chapter.
- Never place credentials in this project; runtime configuration remains in the repository root `.env`.

## Acceptance Criteria

- The expected framework directory tree exists under this project.
- `hello_agents_framework/core/llm.py` retains `OpenAICompatibleClient`, `ChatMessage`, and `create_llm_client_from_env`.
- `hello_agents_framework/core/message.py` restricts roles, creates independent UTC timestamps and metadata, and converts to the OpenAI-compatible role/content shape.
- `hello_agents_framework/core/config.py` validates model, provider, generation, logging, timeout, and history settings; exported dictionaries omit the API key.
- `hello_agents_framework/core/agent.py` requires concrete subclasses to implement `run()`, validates agent names and messages, caps history using `Config.max_history_length`, and returns a copied history list.
- `hello_agents_framework/agents/simple_agent.py` uses the shared Agent contract, executes only registered tools, limits tool iterations, records only the user input and final answer in durable conversation history, and supports streaming only when tool calling is disabled.
- `hello_agents_framework/agents/react_agent.py` validates its prompt contract and step budget, extracts only the first complete `Thought`/`Action` pair when a provider emits extra pairs, executes at most one registered tool per step, records action/observation traces without persisting model reasoning, and terminates only through a valid `Finish[...]` action or the hard step limit.
- `hello_agents_framework/agents/reflection_agent.py` merges validated custom prompt overrides with generic defaults, bounds review/refinement iterations, resets and exposes the current run trajectory, stops only on the explicit normalized `无需改进` decision or the iteration limit, and stores only the task and final answer in shared conversation history.
- `hello_agents_framework/agents/plan_solve_agent.py` parses plans only with `ast.literal_eval`, validates a bounded list of non-empty strings, exposes pending/in-progress/completed/failed step state, stops on the first failed model stage, synthesizes only after all steps complete, and stores the original question and terminal answer in shared history.
- `hello_agents_framework/agents/function_call_agent.py` uses the existing configured model client and endpoint, sends registered tool JSON schemas through the native `tools` parameter, accepts structured `tool_calls`, validates and converts JSON arguments against the tool schema, executes only registered tools, and appends matching `tool` messages before the next model call.
- `hello_agents_framework/tools/base.py` defines the minimal tool contract; `registry.py` provides an explicit allowlist and dispatch boundary; `builtin/calculator.py` evaluates only a bounded arithmetic AST and never uses `eval()`.
- `hello_agents_framework/tools/function.py` validates supported callable signatures, infers a basic JSON Schema or accepts an explicit one, binds mapping arguments to the callable, and converts its return value to the Tool string-result contract. Function registration shares the same duplicate, discovery, schema, execution, and removal behavior as Tool objects.
- `hello_agents_framework/tools/builtin/search.py` accepts a required string `query`, discovers only backends with both a runtime credential and an importable client, never loads `.env` inside library code, and falls back from Tavily to SerpAPI only in `hybrid` mode. Results identify the backend and preserve source URLs; provider exceptions do not expose credentials or raw response bodies.
- `hello_agents_framework/tools/chain.py` validates non-empty chains, registered tools, unique output keys, and context references before dispatch. Parameter templates remain mappings; an exact `{key}` reference preserves the referenced value's type, while embedded references interpolate text.
- `hello_agents_framework/tools/async_executor.py` accepts mapping arguments, limits task count and concurrency, applies a per-call timeout, preserves input ordering, propagates failures, and leaves registry authorization and tool validation on the shared execution path.
- Focused tests live in the dedicated `tests` package and mirror framework modules as the project grows.
- All other planned Python modules remain placeholders.
- `import hello_agents` always resolves the official distribution; `import hello_agents_framework` always resolves this project's local implementation when run from project 12.
- Importing the quickstart module performs no API call; running it as a script performs the two tutorial model calls.
- Offline SimpleAgent tests use fake LLMs and tools; the local live example is separate and consumes model quota only when explicitly run.
- Offline ReActAgent tests cover successful tool use, malformed and unknown actions, bounded termination, prompt validation, public exports, and durable final-history behavior without consuming model or tool-service quota.
- `python -m examples.local_react_agent` is the manual ReAct integration check against the configured real model and consumes model quota; importing the module has no network side effect. It is not an automated integration or end-to-end test because it has no machine-evaluated external-result assertion.
- Offline ReflectionAgent tests cover immediate acceptance, refinement and convergence, hard iteration limits, custom prompt validation, trajectory reset, and shared final-history behavior without consuming model quota.
- `python -m examples.local_reflection_agent` is the manual Reflection integration check against the configured real model. It consumes two calls when the draft is accepted immediately and up to seven calls at the default three-iteration budget; it does not externally verify factual claims.
- Offline PlanAndSolveAgent tests cover fenced and raw plans, sequential context propagation, final synthesis, prompt overrides, malformed plans, model failures, state transitions, limits, and public history without consuming model quota.
- `python -m examples.local_plan_solve_agent` is the manual real-model Plan-and-Solve check; `--mode math` selects the supplied math-specific prompt overrides. A successful n-step plan consumes n+2 model calls.
- Offline FunctionCallAgent tests cover schema generation, native tool-call round trips, type conversion, malformed arguments, iteration limits, missing clients, and shared final history without making network requests.
- `python -m examples.local_function_call_agent` reuses root `LLM_MODEL_ID`, `LLM_API_KEY`, and `LLM_BASE_URL`. Success requires the configured provider—not merely the Python SDK—to implement Chat Completions `tools` and `tool_calls`.
- Offline tool tests cover function adaptation, inferred required/default parameters, unified duplicate handling, callable signature rejection, and direct execution. `python -m examples.local_registered_function` demonstrates the adapter without loading `.env` or consuming model quota.
- Offline search tests use fake provider clients to cover backend discovery, explicit selection, deterministic fallback, normalized sources, invalid input, and total failure without consuming search quota. `python -m examples.local_advanced_search` is a manual external-service integration check, not an automated test.
- Offline chain and async tests cover dependency flow, type-preserving references, invalid chains, ordered parallel results, concurrency bounds, and timeout behavior. `python -m examples.local_advanced_tools` demonstrates both mechanisms locally without model or external API quota.
- Chapter 8 Stage 1 stores only Working Memory and requires an explicit `user_id` and `memory_type`; no model-based classification occurs. Records use aware UTC timestamps, bounded importance, isolated metadata, optional expiry, and opaque IDs.
- Working Memory enforces per-user capacity and TTL, performs deterministic text retrieval with an explicit score, and scopes read, update, removal, forgetting, statistics, and clear operations to one user. Destructive clear requires explicit confirmation at the tool boundary.
- `MemoryTool` extends the existing Tool contract, exposes typed native-tool schema metadata, routes only allowlisted actions, and delegates storage behavior to `MemoryManager`. Its direct `execute()` convenience method and registry `run()` method share the same path.
- Stage 1 tests remain fully offline and cover validation, user isolation, expiry, capacity, ranking, CRUD, forgetting, registry dispatch, destructive-action confirmation, and public imports. The local example performs no LLM, embedding, database, or network request.
- Chapter 8 Stage 2 adds one persistent vertical slice: `EpisodicMemory` stores authoritative event records in SQLite and uses a separately injected text embedder plus vector index for semantic candidate retrieval. The implementation does not yet add SemanticMemory, Neo4j, PerceptualMemory, RAG, consolidation, or automatic model-based classification.
- Stage 2 storage contract: SQLite owns complete records, user scope, metadata, timestamps, updates, and deletion; the vector index stores only the derived vector and lookup payload. Retrieval must discard stale vector hits whose authoritative SQLite record no longer exists.
- Stage 2 provider contract: the framework exposes a minimal text-embedding boundary and a Qdrant adapter. The real example reads existing `EMBED_*` and `QDRANT_*` environment configuration only at the application boundary; unit tests inject deterministic fakes and never consume API quota or require Docker.
- Stage 2 completion criteria: persistent records survive a new SQLite store instance; add/search/update/remove/forget remain user-scoped through `MemoryManager` and `MemoryTool`; failed indexing does not leave a newly added SQLite record; all existing tests continue to pass; and a manual example is available for the configured Bailian/Qdrant boundary without being presented as automated test evidence.
- Chapter 8 RAG Stage 1 implements only the first attributable knowledge-retrieval slice: accept trusted text, split it deterministically, persist the source document and chunks in SQLite, index derived vectors in a dedicated Qdrant collection, retrieve namespace-scoped candidates, resolve them back to authoritative chunks, and return source IDs with scores.
- RAG Stage 1 deliberately separates retrieval from answer generation. `RAGTool.search` returns evidence; an Agent may later place that evidence into an LLM prompt, but the retrieval layer does not claim that an LLM answer is verified. `knowledge_base_path` is the allowed local ingestion root: UTF-8 text/Markdown is read directly, PDFs use `pypdf` with OCR fallback for pages without a text layer, images use local OCR, and supported Office/web formats use installed MarkItDown. Directory-wide ingestion, format-specific extraction evaluation, access-control policy, hybrid keyword search, reranking, and deletion/reindex recovery enter later stages.
- RAG Stage 1 completion criteria: repeated writes of the same `(namespace, document_id)` are idempotent; retrieval cannot cross namespaces; source documents survive a new SQLite store instance; Qdrant contains only vectors and lookup payload; stats come from SQLite; unit tests remain offline; and the manual example uses the existing external configuration without invoking the chat LLM.
- Advanced retrieval completion criteria: basic search makes no chat-model call; MQE and HyDE are disabled by default and require an explicitly configured query expander; the original query is always searched; expanded queries are bounded and deduplicated; candidates are deduplicated by chunk identity using their best vector score; every final result still resolves through SQLite; and fake-model tests prove the behavior without network or database services.
- Knowledge-base assistant completion criteria: uploaded files must match the explicit bounded document/image allowlist and be copied into the selected knowledge base's ingestion root; selecting files immediately performs parsing, chunking, embedding, and indexing, so an upload success means the file is already queryable and no second load action exists; RAG namespaces isolate knowledge bases and users; answers require a selected knowledge base but not a newly uploaded file in the current process; answers must be generated only after source-backed retrieval and include deterministic source labels; Working Memory records the active question while Episodic Memory records durable document and complete Q&A events; unsupported Semantic/Perceptual Memory must not be claimed; monthly reports read only the authenticated user's previous 30 days of complete Q&A and write only inside the configured user report directory; browser sessions must not share one global assistant instance; and offline tests must exercise the application flow with fakes before any live external run.

## Change Log

### 2026-08-06 — Shared default library and explicit authentication flow

- Authentication UX: the application has separate login and registration views under one local authentication entry point. Registration validates a minimum six-character password, creates the account, then returns to login without creating an authenticated session; the user must enter credentials to log in.
- Identity storage: `app_users` remains the authoritative local account table. Passwords are never stored in plaintext and account lookup remains case-insensitive.
- Knowledge-base ownership: one `default` knowledge base uses a shared system scope and namespace visible to every authenticated account. Knowledge bases created through the UI remain owned by the authenticated user's opaque user ID and are not listed or queryable by other users.
- Shared-library policy for this learning stage: every authenticated user can read and manage the shared default knowledge base. Role-based administration is intentionally deferred; this shared write boundary must be restricted before untrusted multi-user deployment.
- Responsive UI: login and registration use one visual surface with transparent Gradio wrappers, a compact mode-switch action, and separate screen states. Mobile must not display nested card borders or compressed heading blocks.
- Acceptance: offline tests prove password validation, registration without auto-login, shared-default discovery, personal-library isolation, and shared namespace reuse. In-app browser verification covers login → registration → login → application entry and responsive visual states.
- Verification: all 109 offline tests pass. A real in-app-browser run at desktop and 390×844 widths verified registration, the return-to-login transition, six-character password login, resource initialization, explicit mobile navigation, and visibility of the shared default knowledge base. The temporary QA account and its owner-scoped rows were removed after verification.

### 2026-08-06 — User-scoped learning workspace

- Identity boundary: the application now opens on a local register/login screen. Accounts receive an opaque persistent user ID; passwords are stored only as salted PBKDF2 hashes in SQLite. The authenticated user ID, not a shared browser label, scopes knowledge-base catalogs, retained files, memory, vector namespaces, and generated reports.
- Resource lifecycle: model, embedding, Qdrant, memory, and RAG resources initialize only after successful authentication. Logging out removes the in-process assistant session without deleting the user's durable data.
- Navigation and responsive behavior: the three primary destinations use one explicit radio-navigation contract instead of Gradio's collapsible primary tabs. All destinations remain present at mobile widths and the selected view is the only visible primary content group.
- Learning report: report generation requires at least one real Q&A turn in the current authenticated session. It groups those turns by knowledge base, invokes the LLM once per represented knowledge base using only that group's recorded questions and grounded answers, labels every section with its source knowledge base, and saves the combined JSON artifact under the authenticated user's report directory. Notes, documents, and older sessions are not silently treated as current-session dialogue.
- UI refinement: the library selector is a compact surface, the manager uses a single header/body/footer hierarchy, and the mobile manager becomes a bottom sheet. Existing document deletion, upload, search, note, and Q&A behavior is preserved.
- Verification: 108 offline tests pass, dependency consistency and compile checks pass, desktop login/library/manager/Q&A flows render without console errors, and responsive CSS keeps all three primary destinations visible. The current browser harness cannot force a 390px viewport, so mobile behavior is additionally covered by the non-collapsing navigation structure and responsive CSS review.

### 2026-08-06 — Knowledge UI interaction correction

- Scope: preserve the `v0.1.0` page structure, knowledge-base boundaries, callbacks, and the user-owned application title while correcting four visible interaction defects.
- Dropdown behavior: clicking the arrow of an already-open Gradio dropdown must close that dropdown; opening, filtering, and selecting values continue to use the framework component.
- Q&A empty state and composer: an empty conversation displays “今天有什么想询问知识库的吗？” in the center. The question field and send action share one visual boundary, with the send button embedded at the field's right edge while remaining a separate accessible button.
- Mobile navigation: the three primary tabs remain visible at 390px so the active tab label and selected state match desktop behavior instead of leaving “知识库” visible while Q&A is active.
- Deletion contract: confirmed document deletion removes every indexed Qdrant chunk first, then the authoritative SQLite document and cascading chunk records, and finally the retained source file. Neo4j is not part of the RAG document path. A backend failure is surfaced rather than reported as successful deletion.
- Verification: focused UI/config tests, RAG deletion tests, full offline tests, desktop browser interaction checks, responsive 390px CSS review, and browser console inspection must pass before handoff. The available browser runtime cannot override its viewport, so mobile verification uses static responsive review rather than claiming a live 390px run.

### 2026-08-04 — PDF Learning Assistant Application

- Scope: implement the application-layer composition from Sections 8.4.2–8.4.5 and a local Gradio entry point while preserving the framework/application boundary.
- Adaptation from the official sample: use the local typed RAG results instead of parsing tool display strings; copy Gradio temporary uploads into the enforced knowledge-base root; configure chunking when building the pipeline; keep RAG retrieval separate from LLM answer generation; and isolate web sessions instead of storing one assistant in a process-global variable.
- Current memory truth: Working Memory and persistent Episodic Memory participate. Episodic Memory stores document-load and complete Q&A events; the note feature is retired. Perceptual Memory, consolidation, and selective forgetting are not presented as implemented application features.
- Verification: fake RAG, Memory, and LLM components cover PDF validation/retention, typed retrieval, grounded answer prompts, memory events, notes, recall, reports, and session isolation without external quota. All 86 offline tests, compilation, CLI help, and `pip check` passed. Gradio 6.22.0 launched on loopback and the start and question-answer tabs were visually inspected in the in-app browser without initializing external resources.

### 2026-08-04 — PDF ingestion idempotency correction

- The authoritative SQLite RAG document record, scoped by namespace and SHA-256 document ID, now gates PDF ingestion. Re-selecting identical content reuses the existing index and current-document selection without copying the file, parsing, embedding, Qdrant upserts, load counters, or duplicate episodic events.
- A retained file without an authoritative SQLite record is not treated as successfully indexed; the normal ingestion path repairs that incomplete state.
- Verification covers first ingestion versus duplicate reuse and the real SQLite-backed document-existence boundary without external services.

### 2026-08-04 — Automatic UI initialization and resource diagnostics

- Removed the manual user-ID and “初始化助手” controls. The local single-user Gradio application now creates the `web_user` assistant through a page-load callback and exposes only the actual first task: uploading a PDF.
- Replaced the opaque `UnexpectedResponse` label with a redacted, actionable Qdrant resource message. Raw provider response bodies are not returned to the browser.
- Root cause verified: the Chapter 8 Qdrant and Neo4j containers were stopped. Both services were restarted from the pinned Compose file; Qdrant health, Neo4j HTTP reachability, real assistant construction, and the browser's automatic ready state passed.
- Verification: all 88 unit tests, Python compilation, and `pip check` passed. Browser inspection confirmed the page displays “助手已就绪” automatically and contains no initialization button; this initialization performs local configuration, SQLite setup, and Qdrant collection checks but does not call Embedding or the chat LLM.

### 2026-08-04 — Upload outcome and process-owned infrastructure lifecycle

- PDF loading now reports three distinct user outcomes: first-time indexing success, an explicit “文档已上传过” result that reuses the existing index, and a safe business reason for validation, Qdrant, Embedding, parsing, or persistence failure.
- The application process owns the dedicated Chapter 8 Compose stack. `main()` runs `docker compose up -d` before launching Gradio and runs `docker compose stop` in `finally` when the server returns or receives `Ctrl+C`; named volumes remain intact, so stopping containers does not delete Qdrant or Neo4j data.
- This lifecycle is intentionally attached to the CLI application boundary, not to page reloads or browser sessions. Force termination such as `kill -9`, machine shutdown, or Docker failure cannot execute Python cleanup and remains an operational limitation.
- Verification: browser initialization and the no-file upload reason passed; a real `Ctrl+C` stopped both Compose services and a subsequent application launch restarted both. All 90 unit tests, compilation, and `pip check` passed.

### 2026-08-04 — Port-conflict preflight correction

- Reproduced: a previously running assistant owned port `7860`; a second invocation started Compose, failed when Gradio bound the occupied port, and then stopped the shared Chapter 8 containers in `finally`.
- Corrected startup order: the CLI now reserves and releases the requested host/port before `compose up`. A conflict fails immediately with an actionable message and never starts or stops Docker services.
- Verification: the agent-owned stale process was stopped, port `7860` and the Compose stack were confirmed inactive, and the focused 11-test application suite, compilation, and `pip check` passed.

### 2026-08-04 — Document-first responsive interaction

- Acceptance: selecting a PDF starts ingestion without a second button; successful or duplicate ingestion leaves the question input immediately available on the same view; learning notes live below Q&A; statistics remain the only separate tab; desktop and narrow mobile layouts must avoid horizontal overflow and preserve readable primary actions.
- PDF conversion must work with the installed dependency set. PDF uses the existing `pypdf` parser, while non-PDF commodity formats continue through MarkItDown; an unreadable or image-only PDF returns an explicit extraction failure instead of entering Embedding with empty content.
- Scope: preserve the existing RAG, memory, upload validation, idempotency, source attribution, and infrastructure lifecycle. Do not introduce a separate frontend framework or automatic paid integration test.
- Implemented: the file-upload event now invokes ingestion directly; Q&A and its collapsible learning-note editor share the primary tab; learning statistics and reports remain on the only secondary tab. The page adds a bounded desktop container and a mobile breakpoint that stacks the question controls.
- PDF root cause and correction: MarkItDown 0.1.7 raised `MissingDependencyException` inside `FileConversionException` because its optional PDF extra is absent. PDF extraction now uses the already-installed `pypdf`; other supported non-text formats still use MarkItDown.
- Verification: the supplied 171-page, 19.8 MB Happy-LLM PDF produced 225,251 characters and 618 chunks locally. Fourteen focused tests passed. Browser checks at 1280 px and 390 px both reported no horizontal overflow and showed the upload, question input, notes, and statistics without a second load button. The real full ingestion was intentionally not run, so no paid Embedding call or Qdrant write was made during this verification.

### 2026-08-04 — Persistent selectable knowledge bases and routed ingestion

- Acceptance: the application starts with a persistent default knowledge base; users may create and select additional named knowledge bases; selecting files immediately ingests them into the selected knowledge base; successful ingestion means the files are already loaded and queryable; failures identify the affected file and stage; asking requires a selected knowledge base but never a newly uploaded document in the current process.
- Isolation: every knowledge base receives a stable namespace in the shared SQLite and Qdrant backends. The existing `pdf_<user_scope>` namespace remains the default knowledge base so previously indexed data is preserved. Additional knowledge bases reuse the same Qdrant collection with namespace filters rather than creating a collection per knowledge base.
- File boundary: accept only explicit document/image extensions, never arbitrary executables. Text and Markdown are read directly, PDF uses `pypdf` and falls back to local OCR only when it has no text layer, images use local OCR, and other supported office/web formats use MarkItDown. OCR uses the already-installed Tesseract/Poppler binaries and must fail clearly when the needed executable or language data is unavailable.
- Scope: no audio/video ingestion, archive extraction, remote OCR provider, background indexing queue, or deletion UI in this stage. These require separate resource, security, and lifecycle contracts.
- Implemented: SQLite now persists the user-scoped knowledge-base catalog; the default knowledge base preserves the existing `pdf_<user_scope>` namespace, while newly named knowledge bases receive stable IDs, isolated ingestion directories, and namespace-filtered storage in the shared Qdrant collection. The Gradio uploader accepts multiple files and indexes each selected file immediately into the selected knowledge base.
- Supported boundary: `.bmp`, `.csv`, `.docx`, `.htm`, `.html`, `.jpeg`, `.jpg`, `.json`, `.markdown`, `.md`, `.pdf`, `.png`, `.pptx`, `.tif`, `.tiff`, `.txt`, `.webp`, `.xls`, `.xlsx`, and `.xml`. The installed MarkItDown Office extras are pinned as a direct dependency. Local OCR uses Tesseract and Poppler and treats the `chi_sim` language model as required rather than silently degrading to English-only recognition. This Mac uses the official Tesseract `tessdata_best` 4.1.0 `chi_sim.traineddata` artifact (SHA-256 `4fef2d1306c8e87616d4d3e4c6c67faf5d44be3342290cf8f2f0f6e3aa7e735b`).
- Verification: all 96 offline tests, compilation, and `pip check` passed. Real local smoke checks converted XLSX and PPTX, OCR-read an English image, a Chinese image, and a Chinese image-only PDF without model, Embedding, or database calls. The verified Chinese strings were `中华人民共和国` and `本合同依法生效`. Gradio was inspected at 1440 px and 390 px; the narrow layout had no horizontal overflow and exposed knowledge-base selection, immediate upload, notes, and statistics. The verification server was stopped afterward.

### 2026-08-04 — Knowledge-base management and note ownership

- Acceptance: the UI has a dedicated knowledge-base management tab where users create/select a knowledge base, upload files directly into it, inspect its authoritative document list, and remove a selected document only after explicit confirmation. The Q&A tab independently requires a knowledge-base selection and queries only that namespace.
- Ownership contract: document records, question events, and learning-note events carry the selected `knowledge_base_id` and name. Saving a note automatically inherits the Q&A tab's current knowledge base; users do not make a second note-specific knowledge-base choice.
- Storage contract: SQLite remains authoritative for the knowledge-base catalog, documents, metadata, and chunk identities. Qdrant stores derived chunk vectors. Document removal deletes the selected namespace's vectors and authoritative SQLite record, then removes the retained source file only when it is inside that knowledge base's ingestion root.
- Safety and scope: document deletion requires both an exact selected document ID and a confirmation control. This stage does not add whole-knowledge-base deletion, renaming, bulk deletion, cross-knowledge-base querying, or note migration.
- Verification: all 98 offline tests, compilation, and `pip check` passed. Browser QA verified the persistent document list, Q&A knowledge-base selector, automatic note-binding label, and an error-free console. The layout was checked at 1440×900 and 390×844; the mobile view has no horizontal overflow. The temporary verification server was stopped without changing the running Chapter 8 containers.

### 2026-08-04 — Knowledge-base isolation, batch ingestion, and library organization

- Incident: one 618-chunk PDF caused one remote Embedding request and one local Qdrant upsert per chunk. The application also enabled MQE plus HyDE by default, so an ordinary question made two query-expansion LLM calls before retrieval and the final answer call. This request shape caused avoidable latency and provider request counts.
- Isolation acceptance: every Q&A, recall, note, document list, and document search operation receives an explicit knowledge-base ID. It resolves one immutable RAG tool/namespace for that operation and never relies on whichever knowledge base another UI callback last selected. Returned RAG evidence must match the selected namespace and, for newly indexed non-default data, the selected knowledge-base metadata.
- Ingestion acceptance: the Bailian OpenAI-compatible endpoint receives document chunks in batches of at most 10 inputs, matching the provider's synchronous `text-embedding-v4` limit. Qdrant receives bounded point batches. A 618-chunk document therefore requires 62 Embedding requests rather than 618; token billing still reflects the indexed text volume.
- Query acceptance: basic retrieval is the default fast path: one query embedding, one namespace-filtered Qdrant query, and one final LLM answer. MQE plus HyDE remains opt-in; expanded query embeddings are batched into one provider request.
- Library acceptance: knowledge-base management uses a library-detail layout with knowledge-base navigation separated from content. Each selected knowledge base has document and note categories. Documents support name search and file-type filtering; notes support content search, concept filtering, and newest/oldest ordering. Note creation time is persisted by the existing `MemoryItem.created_at` field and displayed in the selected knowledge base only.
- Verification: 103 deterministic tests passed, including 51-input Embedding batching, bounded Qdrant bulk writes, explicit knowledge-base selection under conflicting shared UI state, namespace isolation, and document/note filtering. `pip check` and Python compilation passed. Browser QA verified document and note surfaces at desktop size and a 390×844 mobile viewport; the temporary port-7861 server was closed, and the user's existing port-7860 app was left untouched. The embedding boundary was subsequently corrected and reverified as 10/10/10/10/10/1.

### 2026-08-04 — Knowledge workspace interaction correction

- Acceptance: the primary knowledge-base selector keeps only selection and a top-right management action. Management opens as an overlay containing knowledge-base creation and a read-only catalog of every knowledge base and its documents; notes are intentionally excluded from this catalog.
- Document interaction: the selected knowledge base's document list appears before upload, exposes only user-facing file name, type, added time, and a rightmost delete action, and requires a second confirmation overlay before deleting authoritative SQLite metadata, Qdrant vectors, and the retained source file.
- Note interaction: notes are classified by their owning knowledge base. The concept filter and visible sort-choice control are removed; one compact control above the table toggles chronological direction.
- Q&A interaction: the answer history and composer form one visual surface. The advanced-retrieval toggle remains opt-in and sits inside the composer footer instead of interrupting the question-to-answer flow.
- Verification: all 103 deterministic tests passed; Python compilation and `pip check` passed. Browser QA verified the document-before-upload order, rightmost row delete action, knowledge-base management overlay, deletion confirmation overlay, note ownership columns and compact sort control, and the continuous chat/composer surface. The 390×844 mobile viewport had no horizontal overflow. The temporary port-7861 server was stopped after verification without touching the user's port-7860 process.

### 2026-08-05 — Knowledge manager and Q&A control hierarchy

- The knowledge-base picker is now one card-level control: its management action lives in the card header instead of beside the card.
- The manager overlay shows one selected knowledge base at a time. A dropdown changes the document list, a top-right action opens a separate creation dialog, and the close action stays at the lower-right edge.
- Knowledge-base creation remains a deterministic application operation. The creation dialog collects only the name; on success all selectors receive the new option and the selected-base document views refresh together.
- The Q&A knowledge-base boundary and advanced-retrieval switch now sit at the lower-right of the conversation history. The question field and send action are one attached composer row, while switching knowledge bases still clears chat history to prevent source-boundary confusion.
- Verification covers the Gradio component contract, callback construction, full unit suite, and desktop/mobile browser rendering with the key overlays and controls exercised.

### 2026-08-05 — Compact Q&A retrieval controls

- The Q&A knowledge-base selector now uses Gradio's container-free rendering and a bounded 208px desktop width instead of a labeled 304px card. The advanced-retrieval option is a compact 100px control without a second explanatory line.
- Both controls share the conversation surface's neutral background, border token, radius, type scale, and spacing. Their behavior and knowledge-base boundary are unchanged.
- Browser verification measured a 51px desktop control row with no horizontal overflow; the 390px mobile layout remains stacked and overflow-free. Fifteen focused application tests and Python compilation passed.

### 2026-08-04 — Official Q&A assistant UI and feature correspondence

- The first implementation mirrored the official Chapter 8 assistant's four user-facing sections, explanatory header, initialization and document status, question examples, answer/recall presentation, note feedback, statistics, and report summary while retaining the practice implementation's advanced-search control.
- Official behavior is adapted rather than copied where correctness requires it: browser sessions remain isolated, uploaded files stay inside the enforced knowledge boundary, duplicate documents reuse authoritative indexes, typed RAG evidence drives answer generation, and only implemented Working/Episodic memory capabilities are exposed.
- The later knowledge-base-first interaction supersedes the four-section navigation: the knowledge-base tab contains separate document and note views, Q&A and its automatically bound note editor share a second tab, and statistics remains separate. UI configuration tests assert this contract, automatic upload, basic-retrieval default, advanced-search control, document deletion confirmation, and note ownership.

### 2026-08-03 — Practice RAG Stage 1.2: MQE and HyDE

- Scope: add opt-in query expansion and multi-query candidate merging to the existing source-backed RAG pipeline. Keep basic retrieval unchanged and free of chat-model calls.
- Runtime contract: MQE and HyDE use the configured conversational LLM only to propose additional retrieval text. Every original or expanded text is embedded by the existing embedding adapter and searched independently in the same namespace and embedding space.
- Quality boundary: model-generated expansions are untrusted retrieval hints, not facts or answers. Final chunks must still come from Qdrant candidates resolved against authoritative SQLite records. Reranking and answer generation remain separate later stages.
- Verification: fake expansion and embedding components, temporary SQLite, and in-memory Qdrant cover disabled-by-default behavior, MQE/HyDE generation, query deduplication, candidate merging, SQLite source resolution, tool option forwarding, and prompt-output parsing. All 80 offline tests, compilation, CLI help, and `pip check` passed without consuming external quota.

### 2026-08-03 — Practice RAG Stage 1.1: Markdown-Aware Chunking

- Replaced fixed character slicing with deterministic Markdown-aware processing: headings establish a `heading_path`, blank lines establish paragraph boundaries, and approximate CJK/word token counts control grouping and overlap.
- Chunk metadata now retains `heading_path`, source start, and source end. The heading path is prepended only to embedding input, so semantic vectors receive section context while returned source excerpts remain unchanged.
- Kept the project's active resource choices unchanged: Bailian `text-embedding-v4` provides 1024-dimensional vectors, Qdrant runs locally for vector lookup, and SQLite remains authoritative for source documents and chunks. No local/TF-IDF fallback is allowed inside an existing collection because silently changing embedding spaces would invalidate retrieval.
- Deliberately skipped a multi-pipeline registry, directory scanning, embedding batches, Rerank, and LLM answer synthesis. One `RAGTool` owns one explicit namespace; these capabilities enter only when their own business boundary is implemented and tested.
- Verification: focused RAG tests cover stable paragraph overlap, Markdown heading inheritance, embedding context, file ingestion, traversal protection, persistence, namespace isolation, and source-backed retrieval.

### 2026-08-03 — Practice RAG Stage 1: Attributable Text Retrieval

- Added `Document`, `DocumentChunk`, and `DocumentProcessor` with validated source metadata, deterministic overlapping text chunks, and stable chunk UUIDs. Re-indexing the same namespace/document produces the same identities rather than duplicate records.
- Added `SQLiteKnowledgeStore` tables inside the existing practice database for authoritative RAG documents and chunks. This reuses one SQLite deployment while keeping episodic-memory and knowledge-base schemas separate.
- Generalized the existing Qdrant adapter with a filtered `query()` boundary, then added `RAGPipeline` for text indexing and namespace-scoped retrieval. Qdrant stores vectors plus chunk/document lookup payload; every returned candidate must resolve to an authoritative SQLite chunk before release.
- Added `RAGTool` through the existing ToolRegistry path with the textbook-facing `knowledge_base_path`, `add_document`, `add_text`, `search`, and `stats`. The path is an enforced ingestion boundary, relative files resolve inside it, traversal is rejected, text/Markdown is read directly, and other formats use installed MarkItDown. Search output includes document source IDs, chunk positions, and scores; it returns evidence only and does not invoke or certify an LLM answer.
- Added `examples/local_rag_tool.py`, which idempotently writes the three textbook knowledge records, searches for Python history, and prints SQLite/Qdrant locations. Running it consumes four embedding calls and no chat-model call.
- Added offline tests using temporary SQLite and Qdrant's in-memory client for stable splitting, persistence, source attribution, namespace isolation, idempotent replacement, registry dispatch, search, and statistics.
- Deliberately deferred directory scanning, format-specific extraction evaluation, OCR/media policy, deletion UI, keyword/BM25 hybrid retrieval, access-control policy, query rewriting, MQE, HyDE, remote rerank integration, LLM answer synthesis, citation rendering, and cross-store repair jobs.
- Verification: all 74 unit tests passed; direct Markdown and MarkItDown HTML ingestion passed; compile checks, public imports, and `pip check` passed. The external Bailian/Qdrant example was not executed automatically.

### 2026-08-03 — Practice Memory Stage 2: Persistent Episodic Memory

- Added the minimal reusable persistence boundary under `hello_agents_framework.memory`: `TextEmbedder`, an OpenAI-compatible embedding adapter for the existing Bailian configuration, `SQLiteDocumentStore`, and `QdrantVectorStore`.
- Added `EpisodicMemory` as a composed `BaseMemory` implementation. SQLite is the authoritative complete-record store; Qdrant contains derived vectors and lookup payload only. Semantic retrieval combines vector similarity, recency, and bounded importance weighting, then resolves every hit back through SQLite.
- Preserved one public lifecycle path: applications inject Working and Episodic stores into `MemoryManager`, and the existing `MemoryTool` handles add/search/update/remove/forget/clear without a second dispatcher. Failed initial vector indexing rolls back the SQLite insert instead of reporting a partially stored memory.
- Added `examples/local_episodic_memory.py`. It loads the root `.env` only at the application boundary, resets the fixed demo user to avoid duplicate example records, writes to `memory_data/practice_memory.db`, uses a dimension-specific practice Qdrant collection, and consumes two embedding calls when run. It is a manual external integration check, not an automated test.
- Added offline tests with deterministic embedding/vector fakes, real temporary SQLite persistence, and Qdrant's in-memory client. Coverage includes persistence, user filtering, vector retrieval, tool-driven update/remove, failed-index rollback, Qdrant filtering/deletion, and embedding request shape.
- Deliberately deferred SemanticMemory/Neo4j, PerceptualMemory, RAG, reranking of retrieved candidates, consolidation, automatic classification, background repair, and cross-process transaction recovery until their actual stage requires them.
- Verification: all 69 unit tests passed; compile checks, the offline Working Memory example, package-isolation imports, and `pip check` passed. The paid Bailian/local-Qdrant example was not executed automatically.

### 2026-08-03 — Practice Memory Stage 1: Working Memory Vertical Slice

- Added the first local Chapter 8 implementation under `hello_agents_framework.memory`: validated `MemoryItem`, `MemoryConfig`, `MemorySearchResult`, and the shared `BaseMemory` contract; a thread-safe in-process `WorkingMemory`; and a user-scoped `MemoryManager`.
- Added `MemoryTool` to the existing tool registry path with one `run()`/`execute()` dispatch flow, a native-tool JSON schema, typed coercion at the trust boundary, explicit Working Memory selection, CRUD, search, summary, statistics, forgetting, and confirmed per-user clear. Public exports now expose the memory types needed by applications.
- Working Memory enforces aware UTC timestamps, TTL pruning, per-user FIFO capacity, 0–1 importance, isolated metadata, user-scoped operations, and deterministic lexical retrieval whose score prioritizes query relevance before importance. Retrieval score is kept outside the stored record so later semantic retrieval and reranking can replace the strategy without rewriting memory data.
- Added `examples/local_memory_tool.py`, which runs entirely offline through `ToolRegistry`. Added focused tests for validation, expiry, capacity, ranking, CRUD, forgetting, registry dispatch, user isolation, unsupported future memory types, destructive confirmation, and public behavior.
- Deliberately deferred: SQLite, Qdrant, Neo4j, Embedding, Semantic/Episodic/Perceptual Memory, cross-type concurrency, consolidation, persistent reload, rerank, RAG, and real-model Agent tool selection. These enter only when their corresponding chapter stage defines a real boundary.
- Verification: the local example passed, all 64 offline unit tests passed, Python compilation passed, and `pip check` reported no broken requirements. No LLM, embedding, database, or external API call was made by the local example or tests.

### 2026-08-03 — Chapter 8 Official MemoryTool Experience Example

- Added `examples/official_memory_quickstart.py` for the Section 8.2.2 official-package experience path. It registers `MemoryTool`, writes three explicit semantic memories, searches only semantic memory for the frontend-engineer fact, and prints the cross-type memory summary.
- The example deliberately calls `MemoryTool.execute()` directly: embedding, Qdrant, and Neo4j participate, while the configured chat LLM is initialized only to mirror Agent setup and receives no request. Default `MemoryTool` construction also initializes EpisodicMemory and therefore the local SQLite document store, although the three semantic writes do not persist their source text in SQLite.
- The example reuses the validated Chapter 8 environment bootstrap so official package imports occur only after `.env` and local database defaults are loaded. It is a manual integration example, not an automated unit test.
- Verification: after restarting the existing local Qdrant and Neo4j containers, Python compilation and the complete example passed. The search found all three semantic memories and the expected frontend-engineer fact, and the summary reported exactly three semantic memories for the current process. Official 0.2.0's manager performs its final cross-type sort by `importance`, so the output order must not be described as pure semantic-relevance ranking.

### 2026-08-02 — Chapter 8 Official Memory/RAG Resource Verification

- Active configuration: Qdrant and Neo4j run locally through OrbStack/Docker on loopback-only ports, SQLite persists local document state, and Bailian `text-embedding-v4` supplies 1024-dimensional embeddings. The vector collections use dimension-specific names so vectors from the earlier 384-dimensional local experiment cannot be mixed with the active embedding space.
- Compatibility fix: pinned `qdrant-client==1.15.1`. Official `hello-agents==0.2.0` calls `QdrantClient.search()`, which was removed from the previously resolved 1.18.0 client even though the package's broad dependency range allowed that incompatible version.
- Provider-routing fix: the official quickstart now creates `HelloAgentsLLM(provider="auto")`. In official version 0.2.0, omitted-provider detection prioritizes a coexisting `DASHSCOPE_API_KEY`; explicit generic auto mode keeps the conversational model on the configured `LLM_*` endpoint while DashScope remains dedicated to embeddings.
- Agent smoke-test fix: `--agent` now checks the registry through `ToolRegistry.list_tools()`, instructs one deterministic text-protocol memory call, and rejects a final response that lacks the retrieved `Python` evidence. This avoids the official `SimpleAgent.list_tools()` bug (`tools` versus `_tools`) and its string-only parameter parser by using MemoryTool's typed default for `limit`. The overall success marker is emitted only after the Agent round trip passes.
- Verified resources: Qdrant HTTP health, Neo4j HTTP metadata and Bolt connectivity, SQLite initialization, Bailian embedding generation at dimension 1024, semantic-memory write and retrieval, RAG indexing and retrieval, and the optional real-model Agent response all completed successfully.
- Regression evidence: all 54 deterministic project tests pass, Python compilation passes, and `pip check` reports no broken requirements.
- Rerank verification: `--rerank` calls the workspace-scoped Bailian `qwen3-rerank` endpoint with three controlled candidates, validates the response schema, and requires the answer-bearing document to rank first. The configured chat/embedding base URL is normalized by host to the official `/compatible-api/v1/reranks` path; credentials are never logged. The live check passed with the relevant Python document ranked first.
- Scope limitation: the new flag proves remote rerank availability and behavior but does not yet feed actual Qdrant candidates through rerank. Official 0.2.0 defines an unused local CrossEncoder helper, while its wired `search_advanced` path performs MQE and HyDE only. Production RAG integration still requires a raw-candidate boundary between Qdrant retrieval and final context selection.
- Operations: the Qdrant and Neo4j containers remain running and use persistent named volumes. Credentials remain only in the root `.env` and are not recorded in project documentation or logs.

### 2026-08-01 — Chapter 8 Local Experience Baseline

- Changed: added `infra/compose.chapter8.yml` for localhost-only Qdrant and Neo4j services, documented their environment contract in the root `.env.example`, and added `examples/official_memory_rag_quickstart.py` against the official `hello-agents==0.2.0` package.
- Embedding decision: use `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` locally for the first learning loop. It supports Chinese, requires no new credential, produces the configured 384-dimensional vectors, and is reasonable on the current M1/16 GB development machine. DashScope remains a later optional provider when remote throughput or centralized embedding service is required.
- Verification contract: the default quickstart initializes both databases, writes and retrieves semantic memory, and indexes and retrieves one RAG text without invoking the LLM. `--agent` adds a real provider call and is intentionally opt-in.
- Security: database ports bind only to `127.0.0.1`; persistent Docker volumes retain data; Neo4j startup requires `NEO4J_PASSWORD` from the root `.env`; no credential is committed. The example loads the root `.env` before importing the official package because version 0.2.0 captures database configuration during module import.
- Scope: this is the official-package experience path. The from-scratch `hello_agents_framework.memory` and RAG implementation remains a later deep-learning stage.
- Verification performed: Compose syntax and both pinned image tags were validated; the multilingual embedding model downloaded and returned a 384-dimensional Chinese vector; spaCy `zh_core_web_sm==3.8.0` and `en_core_web_sm==3.8.0` both load; Qdrant started in OrbStack and its HTTP health request passed; `pip check` and all 54 existing project tests passed. Neo4j and the complete quickstart were not run because the root `.env` does not yet define `NEO4J_PASSWORD`.

### 2026-07-30 — Dedicated Test Package

- Changed: moved `test_message.py` from the project root to `tests/test_message.py` and added `tests/__init__.py`.
- Reason: the framework now has multiple planned modules, so a dedicated test package provides a stable, scalable structure instead of accumulating test files at the project root.
- Verification: run `../../.venv/bin/python -m unittest discover -s tests -v` from this project directory; all Message tests must pass without importing the official package by mistake.

### 2026-07-30 — Environment-Aligned Configuration

- Changed: implemented `core/config.py` and `tests/test_config.py` using `LLM_MODEL_ID`, `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_TEMPERATURE`, `LLM_MAX_TOKENS`, and `LLM_TIMEOUT`.
- Reason: `gpt-3.5-turbo` and `openai` are not valid universal defaults for this workspace's custom OpenAI-compatible endpoint. Model and endpoint defaults must come from deployment configuration, while `provider="auto"` keeps the transport generic.
- Security: API keys use `SecretStr`, are hidden from object representations, and are omitted from `to_dict()`.
- Verification: the isolated test suite covers defaults, environment parsing, secret-safe export, type coercion, bounds, and unknown-field rejection.

### 2026-07-30 — Abstract Agent Contract

- Changed: implemented `core/agent.py`, added `tests/test_agent.py`, and exposed `HelloAgentsLLM` as a compatibility name for the preserved Chapter 4 client.
- Reason: all later agent implementations need one execution entry point and common history behavior, but the local learning client has not yet been replaced by the full multi-provider implementation.
- Behavior: agent names and message types are validated; history retains only the newest `Config.max_history_length` messages; callers receive a copied list; concrete agents must implement `run()`.
- Verification: tests cover abstract instantiation, concrete execution, provider display, default configuration, message validation, bounded history, copied history, and clearing.

### 2026-07-30 — SimpleAgent and Minimal Tool Runtime

- Changed: implemented the local `SimpleAgent` directly instead of adding a duplicative `MySimpleAgent` layer; added `Tool`, `ToolRegistry`, `CalculatorTool`, public package exports, LLM invoke/stream methods, offline tests, and `examples/local_simple_agent.py`.
- Reason: this repository owns the framework implementation, so the behavior belongs in its concrete `SimpleAgent(Agent)`. A second subclass that repeats nearly the entire class would add inheritance without a distinct responsibility.
- Safety: tools execute only after explicit registration; the calculator parses a bounded arithmetic AST and never evaluates Python code; tool rounds are limited to 1–10 and each round to four calls; errors expose only their type; tool-assisted streaming is rejected until a coherent streaming tool protocol exists.
- Testing: live API examples are not unit tests. Offline tests use fake LLMs and cover direct history-aware chat, tool execution, iteration limits, streaming, dynamic tool management, registry behavior, safe arithmetic, package exports, and LLM invoke/stream adapters.
- Run locally: from this project directory use `../../.venv/bin/python -m examples.local_simple_agent`; this reads the root `.env` through `load_dotenv()` and consumes three model calls when calculation is answered directly, or four when the calculator tool is invoked and its result is sent back for final synthesis.

### 2026-07-30 — Official and Practice Package Isolation

- Changed: renamed the local source package from `hello_agents` to `hello_agents_framework` and updated every local example, test, documentation path, and mock target.
- Reason: import resolution must not depend on the current directory. The official distribution and learning implementation are different codebases and require different import names for reliable IDE navigation, testing, and future packaging.
- Contract: `hello_agents` means official PyPI 0.2.0 everywhere; `hello_agents_framework` means project 12's local implementation everywhere.
- Verification: tests must import only `hello_agents_framework`; the local example must resolve that package; the official example and repository root must resolve `hello_agents` from `.venv/site-packages`; no local `hello_agents` directory may remain.

### 2026-07-30 — Framework ReActAgent

- Changed: implemented the framework's native `ReActAgent(Agent)` instead of adding a second `MyReActAgent` wrapper, added focused offline tests, and added `examples/local_react_agent.py` for manual real-model integration verification.
- Reason: ReAct is now part of the framework being built; it should reuse the local Agent, Message, LLM, and ToolRegistry contracts while keeping only its action/observation loop specific to this agent type.
- Safety: one action is accepted per model response, only registered tools execute, malformed output becomes a bounded observation, tool errors are reduced to their type, model reasoning is not persisted, and the hard step limit always produces an explicit terminal answer.
- Verification: run `../../.venv/bin/python -m unittest discover -s tests -v` for deterministic offline checks. Run `../../.venv/bin/python -m examples.local_react_agent` only when a real-model integration check and its API cost are intended.

### 2026-07-31 — Multiple ReAct Pair Parsing Fix

- Reproduced: the real model emitted `calculator[...]` immediately followed by another `Thought` and `Finish[...]` in the same response. The parser treated the whole suffix as the calculator input, so the calculator correctly rejected it with `SyntaxError`.
- Changed: the output parser now extracts only the first complete bracketed Action from each response and ignores later pairs for that step. This preserves the one-action-per-step execution contract and prevents an unverified later `Finish` from being accepted early.
- Regression test: `test_uses_only_first_pair_when_model_emits_multiple_pairs` reproduces the exact concatenated response and requires the first calculator call to receive only `15 * 8 + 32`.
- Verification: the focused regression test and all 28 offline tests pass; the framework, tests, and examples compile successfully.

### 2026-07-31 — Framework ReflectionAgent

- Changed: implemented the framework-native `ReflectionAgent(Agent)`, exported it from `hello_agents_framework`, added focused fake-LLM tests, and added `examples/local_reflection_agent.py` with general and custom-code prompt modes.
- Reason: the framework owns this execution pattern, so a duplicate `MyReflectionAgent` wrapper would add no distinct responsibility. The implementation reuses shared LLM, Message, Config, Agent history, and example configuration behavior.
- Behavior: every run resets its short-term trajectory, generates an initial answer, reviews it, stops only on normalized `无需改进`, otherwise refines within a 1–10 iteration budget, and records only the original task and selected final answer in shared history. Custom prompts may override any subset of the three stages and are checked for unknown stages, empty templates, invalid braces, and unsupported fields.
- Limitation: model self-review is advisory, not external verification. If the iteration budget ends after a refinement, the latest revision has not received another review; high-risk or factual work still requires deterministic checks, authoritative sources, or human approval.
- Verification: all 32 offline tests pass; framework, tests, and examples compile; the example CLI help and public import succeed without making a model request.

### 2026-07-31 — Framework PlanAndSolveAgent

- Changed: implemented the framework-native `PlanAndSolveAgent(Agent)`, exported it publicly, added focused fake-LLM tests, and added `examples/local_plan_solve_agent.py` with default and math-specific prompt modes.
- Reason: planning, solving, step state, failure termination, and final synthesis are the stable framework mechanism. A separate `MyPlanAndSolveAgent` wrapper would duplicate that mechanism instead of defining application policy.
- Safety and reliability: plans are parsed only with bounded `ast.literal_eval`, never `eval`; every step has explicit state and sanitized failure type; execution stops on the first failed stage; no synthesis occurs unless all plan steps complete; custom prompt overrides reject unknown stages, invalid braces, empty templates, and unsupported fields.
- Difference from the tutorial minimum: final synthesis is a separate model stage rather than assuming the last step's raw output is automatically the answer. This preserves the original goal and all completed evidence at the final boundary.
- Limitation: this introductory framework Agent has no tools, parallel steps, persistence, checkpoint resume, or replanning. Model-produced calculations remain model claims until checked by a deterministic calculator or another verifier.
- Verification: all 37 offline tests pass; framework, tests, and examples compile; CLI help and public import succeed without making a model request.

### 2026-07-31 — Framework FunctionCallAgent

- Changed: implemented `FunctionCallAgent(Agent)`, extended the Tool contract with JSON parameter schemas, added CalculatorTool's `expression` schema, exported the Agent publicly, added fake-SDK unit tests, and added `examples/local_function_call_agent.py`.
- Mechanism: the Agent sends native Chat Completions `tools`, reads structured `message.tool_calls`, parses the function arguments as a JSON object, validates and converts values against the registered tool schema, executes only through ToolRegistry, and returns one `role=tool` message with the matching `tool_call_id` before asking the model for a final answer.
- Compatibility: it reuses the current local `HelloAgentsLLM` model, key, base URL, and OpenAI client. The local implementation exposes `client`, while the later official example uses `_client`; the Agent supports either attribute. Provider support remains a separate runtime requirement.
- Safety: tool names and schemas are validated; missing, unknown, unexpected, malformed, and enum-invalid arguments are rejected; calls and iterations are bounded; errors expose only exception types; tool output remains data rather than authority.
- Verification: installed OpenAI SDK 2.46.0 exposes Chat Completions `tools`, `tool_choice`, and message `tool_calls`; all 41 offline tests pass; framework, tests, and examples compile; public import succeeds. The real provider example was not run, so provider-side native function-call support remains unverified.

### 2026-07-31 — Unified FunctionTool Adapter

- Changed: added `FunctionTool`, `ToolRegistry.register_function()`, public exports, focused tests, and `examples/local_registered_function.py`.
- Architecture: `register_function()` wraps an ordinary callable and delegates to `register_tool()`. The registry still owns one `_tools` mapping and one discovery, validation, execution, and removal path.
- Contract: supported signatures are converted into JSON Schema from basic type annotations, default arguments remain optional and are applied at execution, and callers may supply an explicit object schema when inference is insufficient. Positional-only and variadic signatures are rejected because they do not map cleanly to named tool arguments.
- Verification: all 44 offline tests pass, including a native FunctionCallAgent round trip through a registered function; the local no-model example, public import, and compile checks also pass.

### 2026-07-31 — Multi-Provider SearchTool

- Changed: implemented and exported `SearchTool(Tool)`, added fake-provider unit tests, and added `examples/local_advanced_search.py` for one explicit real-service integration request.
- Architecture: the Tool owns initialized provider clients and configuration state, exposes one required `query` schema, and registers directly through `register_tool()`. It does not wrap a stateful class method through `register_function()`.
- Routing: `hybrid` uses available providers in deterministic Tavily-then-SerpAPI order and falls back on provider failure or empty results. Explicit `tavily` or `serpapi` modes never silently switch providers.
- Reliability: library code reads runtime environment values but never loads `.env`; normalized output identifies the actual backend and preserves source URLs; provider exceptions are reduced to backend status without exposing raw responses or credentials.
- Verification: offline tests cover discovery, preferred routing, fallback, explicit-mode isolation, validation, missing configuration, and source normalization. The real-provider example was limited to CLI help during implementation and consumed no search quota.

### 2026-07-31 — Tool Chains and Bounded Async Execution

- Changed: implemented and exported `ToolChain`, `ToolChainManager`, `AsyncToolExecutor`, and their public task/step types; added focused offline tests and `examples/local_advanced_tools.py`.
- Chain contract: each step names a registered tool, supplies mapping parameter templates, and stores a unique output key. Exact `{key}` references preserve structured values; embedded references interpolate text. All tools are validated before partial execution begins.
- Async contract: synchronous registry calls run through `asyncio.to_thread`; a semaphore bounds concurrency, `wait_for` applies a per-call timeout, TaskGroup owns child lifetimes and propagates failures, and result order matches task order.
- Difference from the tutorial: no string-only dispatch, no duplicate execution path, no unmanaged custom ThreadPoolExecutor, and no `__del__` cleanup. Native async tools and cancellation of already-running worker threads remain outside this introductory scope.
- Verification: six focused tests cover ordered dependencies, structured references, invalid chains, manager behavior, ordered fan-out, concurrency limits, existing-tool reuse, timeouts, and task validation.

### 2026-08-05 — Immediate Chat Submission Feedback

- Changed: split chat submission into two Gradio event stages. The first stage clears the input and immediately renders the user message plus a pending-answer bubble; the queued RAG/LLM stage then replaces that bubble with the final answer or explicit error.
- Reason: retrieval and model calls can take long enough that waiting for the complete callback leaves users unable to tell whether the send action was accepted.
- State boundary: the submitted question is handed to the second stage through session-local `gr.State`; it is not recovered from mutable shared UI state.
- Verification: focused tests cover immediate input clearing, pending rendering, and replacement by the completed answer; runtime browser verification covers the visible two-stage interaction.

### 2026-08-05 — Unified Knowledge-Base Browsing

- Changed: the left knowledge-base selector is the single filter for both document and note tabs and includes `所有知识库`. Text searches, document-type filtering, and note sorting operate within that shared scope; the duplicate note-level selector was removed.
- Reason: two knowledge-base selectors could disagree and made the visible data boundary ambiguous. One parent selection matches the page hierarchy and keeps both child tabs consistent.
- Data boundary: the all-libraries view aggregates only the current user's registered knowledge bases. Document rows include their owning knowledge base so deletion is routed to the correct store; uploads require a concrete knowledge base. Note listing remains a local episodic-memory operation and does not call RAG or the model.
- Verification: tests cover cross-library document and note listing, one-library filtering, scoped text search, initial UI configuration, and the rendered tab interaction.

### 2026-08-05 — Version 0.1.0 Milestone Baseline

- Changed: established `12_hello_agents_practice` as an independent Git repository, added a single-source `VERSION` file and milestone `CHANGELOG.md`, and tagged the verified baseline as `v0.1.0`.
- Reason: the first runnable intelligent knowledge management platform is now valuable enough to preserve as a reproducible rollback point without coupling its history to the other learning projects.
- Scope: source code, examples, tests, infrastructure configuration, and design records are versioned. Secrets, virtual environments, caches, uploaded knowledge files, SQLite runtime state, and generated learning reports are excluded.
- Release meaning: `0.1.0` is the first usable learning/customization milestone, not a production-readiness claim. Runtime data requires its own backup because Git protects code history, not database or uploaded-document state.
- Verification gate: the repository may be tagged only after the deterministic test suite passes, dependency consistency passes, and the staged file list is checked for ignored runtime or secret material.

### 2026-08-06 — Shared-library naming and mobile interaction polish

- Changed: the user-visible `default` library name is now `共享知识库`; the stable internal ID and Qdrant namespace remain unchanged so existing documents and links continue to resolve. Startup performs an idempotent catalog upsert so existing SQLite rows receive the corrected display name.
- Mobile layout: authentication and application surfaces use the full available viewport, remove nested decorative containers, keep the welcome title on one line, and flatten knowledge-base filters into ordinary controls.
- Interaction: login and registration states animate on entry, an expanded dropdown closes when its trigger is pressed again, and the knowledge-base manager uses a destructive red close action as requested.
- Acceptance: unit tests must cover the display-name migration, and live desktop plus 390×844 browser checks must cover login, registration transition, authenticated layout, dropdown toggling, and the manager close action.

### 2026-08-06 — Shared-library collision and session-report correction

- Root cause: historical personal catalog rows also used `knowledge_base_id=default`; converting accessible rows into an ID-keyed mapping let one of those rows overwrite the system-owned shared catalog entry.
- Changed: the accessible-catalog query now always returns the system-owned `__shared__/default` row and excludes legacy personal `default` rows while retaining every user-owned non-default knowledge base. Startup also migrates all legacy display labels from `默认知识库` to `共享知识库` without changing IDs, namespaces, documents, or vectors.
- Authentication UI: username and password controls now have explicit light/dark input backgrounds, borders, text colors, and focus states for both Gradio textarea and input elements. The desktop card is wide enough to keep the welcome title on one line; the mobile layout remains bounded to the viewport.
- Report behavior: the report action summarizes only the current assistant instance's real Q&A turns, groups them by knowledge base, emits an explicitly labeled section per knowledge base, and reports the true turn/library counts.
- Verification: focused unit tests cover shared-row precedence, legacy-label migration, and multi-library report grouping. Live browser checks cover visible login fields, register-to-login transition, selectable `共享知识库`, and no horizontal overflow at 390×844 and 1440×900.

### 2026-08-06 — Knowledge-base selection and refresh-session recovery

- Selection contract: `所有知识库` is an aggregate read scope, not a writable knowledge base. `共享知识库` and every user-owned knowledge base are concrete choices and remain independently selectable. Uploads require a concrete choice; documents and notes may be listed through the aggregate scope.
- Root cause: Gradio choice updates could retain an aggregate or stale value after registration or knowledge-base creation, so the visible selector exposed only `所有知识库` and uploads had no concrete namespace. Selector updates now validate the current value against the accessible catalog, choose a safe concrete fallback when required, and return non-filterable interactive controls.
- Browser event fix: Gradio renders dropdown triggers and popup options through a shadow-tree-backed wrapper. The capture-phase second-click handler must inspect `event.composedPath()`, exempt `listbox`/`option` events, and consume only an already-expanded trigger. This preserves both concrete knowledge-base selection and repeated-trigger close behavior in the library and Q&A selectors.
- Session contract: the browser stores only an opaque session token in `gr.BrowserState`; the server-side `AssistantSessions` registry remains authoritative. Page reload restores the account with `UserAccountStore.get_by_id()` and rebuilds only that user's accessible knowledge bases. Logout clears both stores. A server process restart still invalidates local sessions by design.
- End-to-end verification: a temporary user registered and logged in, created a personal knowledge base, uploaded and indexed a text document, viewed it through `所有知识库`, refreshed without losing authentication, retrieved its unique phrase in Q&A, saved a scoped note, generated a knowledge-base-labelled session report, and deleted the document. Post-delete checks found zero authoritative SQLite chunks/documents and zero Qdrant vectors for the namespace; temporary account, catalog, vector, report, and fixture data were removed.

### 2026-08-07 — Mobile authentication surface and theme contrast

- Root cause: the mobile breakpoint still applied main-container padding and retained the desktop card width, exposing the page background as a visible outer ring. Theme-derived input colors also produced insufficient separation from the authentication panel in dark mode.
- Changed: the mobile application and authentication surface now fill the dynamic viewport without an outer card boundary. Authentication fields use explicit light/dark background, border, text, placeholder, and caret colors while preserving the existing registration and login flow.
- Acceptance: desktop light and dark modes retain a readable centered card; the narrow layout has no outer ring or horizontal overflow, and username/password fields remain visually identifiable in both themes.

### 2026-08-07 — Edge-to-edge application canvas

- Root cause: the root Gradio container still had a desktop `1180px` maximum width, centered margin, and padding. Its nested main container added more padding, so the browser body remained visible as a white or black ring around the application.
- Changed: the browser host, Gradio root, and main application canvas now occupy the full viewport with no outer margin or padding. The mobile authentication layer reuses the active Gradio page background instead of introducing a second light or dark surface. Spacing remains the responsibility of the page's internal panels and controls rather than the application shell.
- Acceptance: authenticated and authentication surfaces reach both viewport edges on desktop and mobile; light and dark themes no longer expose a contrasting outer ring.
### 2026-08-07 — Bailian embedding batch boundary

- `text-embedding-v4` accepts at most 10 input texts per compatible embeddings request; the practice embedder therefore batches document chunks in groups of 10 instead of 25.
- This prevents large-document uploads from failing with `400 BadRequestError` before Qdrant and SQLite persistence.
- Verification covers the provider boundary with a live 10/11-item probe and unit tests for batch splitting and limit validation.

### 2026-08-07 — Shared and personal knowledge-base access contract

- `共享知识库` is one system-owned library with the stable namespace `pdf_shared_default`. Every authenticated user reads and uploads to that same library.
- A personal library is owned by exactly one user. Its catalog row, source directory, SQLite namespace, and Qdrant namespace are user-scoped; other users must not discover, list, query, upload to, or delete it.
- `所有知识库` is a read-only aggregate consisting of `共享知识库` plus the current user's personal libraries. It never includes another user's personal library.
- Duplicate detection is scoped by `(namespace, SHA-256 document ID)`: the same content is rejected as a duplicate inside one library but may be indexed independently in another library.
- After an upload attempt completes, the file control is cleared while the status remains visible, allowing the next upload without a manual close action.
- Acceptance requires an isolated two-user regression test covering shared visibility, private isolation, aggregate contents, and per-library duplicate behavior, plus UI configuration verification for upload reset.
- Verification: the isolated Alice/Bob regression proves shared cross-user visibility, owner-only private discovery, correct `所有知识库` aggregation, and namespace-scoped duplicate handling. The upload callback returns an empty file value after completion. The complete offline suite passes 115 tests; compile, diff-whitespace, and dependency-consistency checks also pass.

### 2026-08-07 — Dynamic document-table height

- Root cause: Gradio 6.22 virtualizes Dataframe rows. CSS `:has()` rules counted only the currently rendered DOM rows and then set that same virtual viewport's height. After visiting a one-row library, the 44 px viewport rendered only one row from a later aggregate result, so the CSS remained self-locked at one row even though the callback returned every document.
- Changed: document rows retain a deterministic 44 px non-wrapping presentation, but CSS no longer calculates or clamps the virtual body's height from rendered row elements. Every backend callback now returns both the authoritative rows and a `max_height` derived from their count. The viewport grows for zero through seven rows and then scrolls, so the uploader follows short lists without leaving a fixed empty block.
- Reason: rendered virtual rows are a viewport subset, not the dataset. Presentation code must not use them as a business row count.
- Verification: the live browser switched `共享知识库 → 切换验收库 → 所有知识库` twice. The visible sets remained 2 shared documents, 1 private document, and all 3 documents respectively on both cycles. Unit coverage fixes the zero/one/two/seven/eight-row height contract, and the Gradio configuration test prevents reintroducing virtual-body row-count selectors.
- Knowledge-base catalog reads refresh from SQLite before aggregation so a second browser tab immediately sees libraries created and populated in the first tab; an assistant's startup snapshot is not an authorization or discovery source.

### 2026-08-07 — Rounded mobile authentication card

- Changed: the mobile login and registration surface now uses one intentional inset card with a 24 px outer radius, 14 px form-control and primary-action radii, balanced safe-area spacing, and a soft theme-aware shadow. Duplicate Gradio wrapper borders and backgrounds remain flattened.
- Reason: the previous edge-to-edge rectangular form removed the outer ring but still looked unfinished on a phone. One compact rounded product panel improves hierarchy without reintroducing nested cards.
- Scope: authentication presentation only. Registration, login, session restoration, account storage, and resource initialization behavior are unchanged.
- Verification: Python compilation and the focused Gradio construction test pass. Live 390 × 844 light/dark captures report a 366 px card at `x=12`, 24 px outer radius, 14 px input/button radii, readable dark-theme field contrast, and no horizontal overflow. The 1280 px desktop card remains centered at 520 px wide.

### 2026-08-07 — Q&A-first authenticated landing

- Changed: the authenticated application now opens on `智能问答`; `知识库` and `学习统计` remain explicit primary-navigation destinations.
- Reason: asking the indexed knowledge base is the product's primary user task, while document management is a supporting operation.
- Verification: the Gradio configuration regression test asserts the `chat` navigation value, and the initial view visibility matches that value.

### 2026-08-07 — Navigation persistence and deterministic library scope

- Refresh contract: an authenticated browser persists its active primary module in browser-local state. Refresh restores that module together with the server session; an invalid or expired session falls back to the login surface.
- Login contract: explicit logout clears both the server session and the persisted primary module. Every subsequent fresh login opens `智能问答`, regardless of the module used before logout.
- Selection contract: every library-switch callback resolves against a fresh SQLite catalog snapshot, and only the most recent pending selection may update the rendered document and note state.
- Access contract: `共享知识库` remains the single system-owned `pdf_shared_default` namespace. `所有知识库` aggregates that shared library plus only the authenticated user's private libraries; another user's private libraries are excluded at the catalog query boundary.
- Acceptance: unit tests cover navigation normalization, repeated library switching, global shared visibility, and private aggregate isolation. Runtime verification covers refresh persistence and logout/login reset when an authenticated browser session is available.
- Verification: 116 automated tests pass; browser acceptance confirms that a fresh login opens `智能问答`, refresh preserves `知识库`, and logout followed by login resets to `智能问答`.

### 2026-08-07 — Knowledge-base switch callback consistency

- Callback risk: one user library switch also programmatically resets the document-type dropdown. Gradio's `.change` event fires for that internal update and can launch an unnecessary second table reload.
- Changed: user-driven knowledge-base selectors and the document-type filter use `.input` with `trigger_mode="always_last"`. Programmatic choice/value updates no longer invoke a second business reload; free-text document and note searches continue to use `.input`.
- Final rendered-row root cause: the disappearing aggregate rows were caused by the virtual-body CSS self-lock documented in “Dynamic document-table height”, not by SQLite aggregation or missing documents. Removing that CSS was required for the visible result to remain correct after repeated switching.
- Acceptance: a real authenticated browser must repeatedly switch `所有知识库 → 共享知识库 → 当前用户个人知识库 → 所有知识库`; the final aggregate must equal shared documents plus that user's private documents and exclude other users' private documents.

### 2026-08-07 — Compact document uploader

- Root cause: the document table already ended immediately above the uploader, but Gradio's file-drop component retained a 240 px default height. Its centered drop target looked like a large gap between the document list and upload action.
- Changed: the uploader is 144 px on desktop and 128 px on mobile while preserving click and drag-and-drop behavior. The real table-to-uploader spacing remains 0.35 rem.
- Acceptance: with two document rows, the uploader begins within 8 px of the table and the upload panel no longer dominates the document-management viewport.

### 2026-08-07 — Project and framework naming correction

- Naming contract: the Chapter 12 learning project is `12_hello_agents_practice`; its reusable local Python package is `hello_agents_framework`. The official PyPI package remains exclusively `hello_agents`.
- Migration scope: move the independent Git repository together with its `.git` directory, rename the tracked Python package, and update local imports, mock targets, commands, paths, and project documentation. Preserve unrelated uncommitted work.
- Compatibility boundary: persistent Qdrant collection names, browser-storage keys, and existing database identifiers keep their current values because they are storage contracts rather than Python import paths. Existing absolute source paths in persisted document metadata must be migrated to the new project directory.
- Acceptance: the complete offline suite passes from the renamed directory; `hello_agents_framework` resolves locally, `hello_agents` still resolves from the official environment, no source import uses the retired `hello_agents_practice` package name, existing knowledge files remain reachable, and the repository still exposes tag `v0.1.0` after its root directory moves.

### 2026-08-07 — Version 0.2.0 Milestone

- Changed: promoted the verified multi-user intelligent knowledge-base state to version `0.2.0` and prepared the independent repository for its first GitHub publication.
- Scope: local authentication and session restoration, shared/private knowledge-base boundaries, scoped document and note management, Q&A-first navigation, current-session reports, provider-safe embedding batches, responsive UI, visual QA evidence, framework source, examples, infrastructure, and automated tests.
- Excluded: secrets, virtual environments, caches, SQLite runtime data, uploaded knowledge files, generated learning reports, and external Qdrant/Neo4j state.
- Verification gate: the complete offline test suite, Python compilation, dependency consistency, whitespace validation, staged-file review, secret-pattern scan, and remote tag verification must pass before the milestone is considered published.

### 2026-08-07 — Focused knowledge-base management

- Management scope: the `管理知识库` dialog manages knowledge-base identities only. It lists the shared and current user's personal libraries, creates personal libraries, and deletes personal libraries after confirmation; document browsing remains on the main knowledge-base page.
- Safety rules: `共享知识库` cannot be deleted. Names are unique across the knowledge bases visible to the current user using case-insensitive comparison, and duplicate creation returns a visible validation error instead of selecting the existing library. Deleting a personal library first removes every document from Qdrant, SQLite, and retained source storage, then removes its catalog row.
- Document discovery: the main document view uses one filename search field. Enter and the explicit `搜索` button execute the same scoped search; the file-type filter is removed.
- Presentation: the document table exposes only file name, owning knowledge base, and operation with stable explicit column widths. The simplified manager dialog is bounded to the mobile viewport and contains no document table.
- Acceptance: storage and assistant tests cover protected shared deletion, duplicate rejection, personal-library cleanup, selector fallback, and scoped search. The Gradio configuration test verifies the reduced dialog, explicit search actions, removed type filter, and fixed table widths. Desktop and mobile visual QA must confirm alignment and full dialog visibility.

### 2026-08-12 — Version 0.2.3 separated expert platform

- Replaced the previous incomplete `expert_platform/` implementation with a Vue 3, TypeScript, Vite, Vue Router, and Pinia frontend plus a FastAPI backend. The prior directory was moved to the macOS Trash before reconstruction so the deletion remains recoverable.
- Preserved one business path by reusing `apps.pdf_learning_assistant.PDFLearningAssistant`; it continues to compose `hello_agents_framework` for LLM, embedding, memory, RAG, tools, SQLite, and Qdrant behavior. The browser depends only on the explicit API contract.
- Added routed authentication, chat, expert management, statistics, and profile surfaces; durable hashed-cookie sessions; bounded streaming uploads; safe backend error mapping; API integration tests; type/build gates; and desktop/mobile browser QA.
- The existing Gradio entry point and framework code were not refactored. Production identity, distributed assistant state, CSRF tokens, RBAC, rate limiting, audit logging, background jobs, and deployment automation remain outside the version 0.2.3 boundary.

### 2026-08-15 — Legacy tenant and shared-catalog cleanup

- Canonical shared identity: retain exactly one system-owned shared expert, `__shared__/default/pdf_shared_default`, displayed as `共享专家库`. Remove every older per-user `default`/`共享知识库` catalog without affecting retained private experts.
- User cleanup scope: remove accounts and all linked sessions, expert catalogs, documents, chunks, episodic events, retained source directories, RAG points, and episodic points for `eric`, `Jenny爱菲`, `codexqa0807`, `web_user`, and `default_user`. Preserve `ljm`, its private experts, the canonical shared expert, test-only `chapter8_rag_demo` records, and unrelated QA accounts.
- Recovery: before deletion, create a SQLite online backup, a complete `knowledge_base` archive, the monthly-report archive, and downloadable snapshots of both practice Qdrant collections under `.runtime/data-cleanup-backups/20260815-110416/`.
- Verified result: removed 10 knowledge-base catalogs, 6 documents, 1,243 RAG chunks/points, 20 episodic rows/points, 3 registered accounts, and 5 user-scope directories. SQLite integrity is `ok`; target and legacy queries return zero; every retained source path exists; SQLite and Qdrant RAG/episodic ID set differences are both zero.
