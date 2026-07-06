## Why

Phase 1 of the Choice FinX support chatbot is decomposed into eight parallel changes (P1–P8) that all depend on the same configuration surface and the same data contracts (RAG tool I/O, agent reply, SSE events, report-tool I/O, session context). To let those changes be built in parallel without merge conflicts or contract drift, the shared foundation must land in `main` first. This change owns that foundation and nothing else.

## What Changes

- Establish the Python + FastAPI backend project skeleton: `backend/{config,contracts,db,agent,rag,tools,api,evals}/` and `frontend/`, each with package `__init__.py` placeholders so downstream changes only add files inside their owned directory.
- Add the **single dependency manifest** (`pyproject.toml`) and `.env.example`. This change is the **sole owner** of dependency files and root config; no P1–P8 change modifies them.
- Add a typed configuration loader (`backend/config`) that reads all settings from `.env` (Anthropic, OpenAI embeddings, Postgres, FINX reports base URLs, tracing) with fail-fast validation. Nothing is hardcoded.
- Add a read-only Postgres connection helper (`backend/db`) over the existing `qa_chunks` table (pgvector, embeddings + FTS already loaded — no migration).
- Define the canonical shared data contracts (`backend/contracts`) as Pydantic v2 models consumed by every downstream change: retrieval results, RAG tool I/O, report-tool I/O, agent reply, SSE event envelope, session context, and usage/cost accounting.
- NOT in scope: any retrieval logic, agent loop, report HTTP clients, API endpoints, evals, tracing wiring, or frontend. Those belong to P1–P8. This change only provides types, config, DB access, and skeleton.

## Capabilities

### New Capabilities
- `project-configuration`: environment-driven configuration loading and validation for all backend settings, with no hardcoded connection details.
- `data-contracts`: the canonical, versioned data schemas (retrieval, RAG tool, report tools, agent reply, SSE events, session, usage/cost) that every downstream module imports.
- `database-access`: a read-only connection helper to the pre-populated `qa_chunks` pgvector table.

### Modified Capabilities
<!-- None — this is the foundational change; no existing specs to modify. -->

## Impact

- New files only; no existing behavior changes.
- Downstream P1–P8 all import from `backend.contracts` and `backend.config`; changing a contract after fan-out is a breaking change, so contracts are frozen once this lands.
- Dependencies introduced: `fastapi`, `uvicorn`, `pydantic>=2`, `pydantic-settings`, `psycopg[binary]`, `pgvector`, `anthropic`, `openai`, `httpx`, `python-dotenv`, `deepeval`; dev: `pytest`, `ruff`.
