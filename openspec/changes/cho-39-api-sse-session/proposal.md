## Why

The Choice FinX support agent (P4) exposes a Python iterator, `agent_reply_stream(...)`, but a browser POC (P8) cannot consume a Python iterator — it needs an HTTP surface. This change (P5) is the thin FastAPI layer that turns the agent into a web API: a login endpoint that establishes a server-side session from a tester's client code + session token, and a Server-Sent-Events (SSE) chat endpoint that streams the agent's intermediate status, output tokens, citations, and per-message + cumulative INR cost to the frontend. It owns `backend/api/` only and contains no agent, retrieval, tool, or tracing logic — it assembles the frozen P0 contracts and the P4 agent into HTTP and nothing else.

## What Changes

- Add a FastAPI app factory `create_app()` and a `uvicorn` entrypoint in `backend/api/`.
- Add `POST /session`: accept `client_code` + `session_token`, trim both (via `SessionContext`), create an in-memory server-side session, and return a `session_id`.
- Add the SSE chat endpoint (`POST /chat`, `text/event-stream`): accept a user `message` + `session_id` + `thread_id`, append the message to that session's per-thread conversation history, call `backend.agent.agent_reply_stream(history, session, thread_id)`, and relay each `SseEvent` to the client as an SSE frame in the order `status → token(s) → citations → usage → done`, emitting an `error` event on any failure.
- Track cumulative conversation cost in INR per session and inject `cumulative_cost_inr` into every `usage` event (alongside the per-message `UsageCost`), so the frontend's top-left cost card can render running total, per-message cost, and latency.
- Configure CORS for the frontend origin.
- NOT in scope: agent internals / prompt / loop (P4), retrieval + report tools + tracing (P1/P2/P3), and the frontend itself (P8). This change never redefines a P0 contract — it imports them.

## Capabilities

### New Capabilities
- `session-auth`: establish and reuse a server-side POC session from a trimmed client code + session token, where the session token is retained as the FINX `Authorization` JWT for the agent's report calls.
- `chat-sse-api`: an SSE HTTP endpoint that maintains per-session conversation history and streams the agent's `status`, `token`, `citations`, `usage` (with cumulative INR cost), `done`, and `error` events to the frontend.

### Modified Capabilities
<!-- None — this change only adds two new capabilities inside backend/api/. -->

## Impact

- New files only, all inside the owned directory `backend/api/`:
  - `backend/api/__init__.py` — re-export `create_app`.
  - `backend/api/app.py` — `create_app()` app factory, CORS wiring, router registration.
  - `backend/api/sessions.py` — in-memory session store (`session_id → SessionContext + per-thread history + cumulative_cost_inr`).
  - `backend/api/schemas.py` — request/response Pydantic models local to the HTTP layer (`SessionCreateRequest/Response`, `ChatRequest`) — NOT a redefinition of any P0 contract.
  - `backend/api/routes.py` — `POST /session` and the SSE `POST /chat` handler that adapts `SseEvent`s to SSE frames.
  - `backend/api/main.py` — `uvicorn` entrypoint (`uvicorn backend.api.main:app`).
  - `backend/api/tests/__init__.py`, `backend/api/tests/test_session.py`, `backend/api/tests/test_chat_sse.py`.
- Imports only (does not modify): `backend.config.settings.Settings`, `backend.contracts.session.SessionContext`, `backend.contracts.sse.SseEvent`, `backend.contracts.agent.AgentReply`/`UsageCost`, `backend.contracts.retrieval.Citation`, and `backend.agent.agent_reply_stream` / `agent_reply`.
- No changes to `pyproject.toml`, `.env`, root config, or DB schema (owned by P0). `fastapi`, `uvicorn`, and `httpx` are already declared by P0; no new dependency is introduced. If the reviewer finds `starlette`/`httpx` test extras missing from the manifest, that is a P0 addition, not this change.
- Depends on P0 `foundations-and-contracts` (contracts + config) and P4 `agentic-loop` (`agent_reply_stream`) being merged to `main` first. Tests stub `agent_reply_stream`, so this change is testable without P4's real implementation.
