## Context

This is P5 (`api-sse-session`) in the eight-change parallel decomposition. It owns `backend/api/` exclusively and is the only HTTP surface in the backend. It sits directly above P4 (`agentic-loop`) and directly below P8 (`frontend-poc`):

- **Consumes (imports, never redefines):**
  - P0 `foundations-and-contracts`: `backend.config.settings.Settings`; `backend.contracts.session.SessionContext{client_code, session_token}` (both trimmed); `backend.contracts.sse.SseEvent{event, data}` with `event ∈ {status, token, citations, usage, done, error}`; `backend.contracts.agent.AgentReply`/`UsageCost{input_tokens, output_tokens, cost_inr, latency_ms}`; `backend.contracts.retrieval.Citation`.
  - P4 `agentic-loop`: `backend.agent.agent_reply_stream(history: list[dict], session: SessionContext, thread_id: str) -> Iterator[SseEvent]` (and the non-streaming `agent_reply`).
- **Depends on:** P0 and P4 merged to `main`. Tests stub `agent_reply_stream`, so P5 is buildable and testable before P4's real loop lands.

Files touched (all new, all under `backend/api/`): `__init__.py`, `app.py`, `sessions.py`, `schemas.py`, `routes.py`, `main.py`, and `tests/`.

**Endpoints:**
- `POST /session` → create a server-side session, return `session_id`.
- `POST /chat` → SSE (`text/event-stream`) stream of the agent's turn for a `(session_id, thread_id)`.
- `GET /healthz` → liveness probe (trivial; keeps uvicorn/canary happy).

## Goals / Non-Goals

**Goals:**
- Turn the P4 agent iterator into an HTTP+SSE surface the P8 frontend can consume, preserving the exact `SseEvent` ordering the agent emits.
- Establish and reuse a per-tester server-side session so the `session_token` (FINX JWT) and per-thread history live server-side, not in the request each turn.
- Maintain per-session cumulative INR cost and expose it, per-message cost, and latency to the frontend via `usage` events.
- Be fully testable with a stubbed agent (no DB, no Anthropic, no P4 loop required).

**Non-Goals:**
- No agent logic, prompt, tool dispatch, retrieval, report calls, or tracing (P1–P4).
- No durable session store, auth hardening, rate limiting, or multi-process session sharing — the store is a single-process in-memory dict for the POC (documented risk).
- No frontend code (P8).
- No new dependencies, no schema, no root-config edits (P0-owned).

## Decisions

### Route signatures & request/response bodies

Local HTTP DTOs live in `backend/api/schemas.py`. They are transport shapes, NOT redefinitions of P0 contracts (which are imported):

```python
# backend/api/schemas.py
class SessionCreateRequest(BaseModel):
    client_code: str
    session_token: str

class SessionCreateResponse(BaseModel):
    session_id: str          # opaque server-issued id (uuid4 hex)

class ChatRequest(BaseModel):
    session_id: str
    thread_id: str
    message: str             # the user's turn text
```

`POST /session`
- Request body: `SessionCreateRequest`.
- Build `SessionContext(client_code=..., session_token=...)` — the P0 validators trim both. If either is empty after trimming → `422`.
- Create a `Session` in the store, return `SessionCreateResponse{session_id}` with `200`.
- Contract: `create_session(client_code, session_token) -> session_id`.

`POST /chat`
- Request body: `ChatRequest`.
- Unknown `session_id` → `404` (JSON error, not an SSE stream).
- On success → `200` with `Content-Type: text/event-stream` and a streaming body (see SSE framing).

`GET /healthz` → `{"status": "ok"}`.

### SSE framing

- Response is a Starlette `StreamingResponse(generator, media_type="text/event-stream")` with headers `Cache-Control: no-cache`, `Connection: keep-alive`, `X-Accel-Buffering: no` (disable proxy buffering).
- Each `SseEvent` from the agent is serialized to one SSE frame following the Anthropic/standard SSE wire format:
  ```
  event: <SseEvent.event>\n
  data: <json.dumps(SseEvent.data)>\n
  \n
  ```
- The handler iterates `agent_reply_stream(history, session, thread_id)` and yields a frame per event, preserving order: `status` (one or more intermediate steps, e.g. "Looking up the knowledge base…", "Generating the answer…") → `token` (one per output-token chunk) → `citations` (once) → `usage` (once) → `done` (once).
- **Cost injection:** the handler intercepts the `usage` event, adds the session's running total as `data["cumulative_cost_inr"]` (see cost accounting), then yields it. All other events pass through unchanged.
- **History commit:** the assistant's final text (accumulated from `token` events) is appended to the thread history only after `done` is observed, so a mid-stream disconnect does not persist a partial turn.

### Session store

`backend/api/sessions.py` — process-local, thread-safe dict for the POC:

```python
@dataclass
class Session:
    session_id: str
    context: SessionContext                 # trimmed client_code + session_token (FINX JWT)
    threads: dict[str, list[dict]]          # thread_id -> [{role, content}, ...]
    cumulative_cost_inr: float = 0.0

class SessionStore:
    def create(self, ctx: SessionContext) -> Session          # new uuid4 id
    def get(self, session_id: str) -> Session | None
    def history(self, session_id: str, thread_id: str) -> list[dict]
    def append_turn(self, session_id, thread_id, user_msg, assistant_msg) -> None
    def add_cost(self, session_id: str, cost_inr: float) -> float   # returns new cumulative
```

- A single `SessionStore()` instance is created in `create_app()` and injected into the router (via FastAPI dependency / app state), so tests can swap it.
- Access guarded by a `threading.Lock` because SSE generators may interleave. The store is intentionally non-durable — reset on restart (POC risk, below).

### Cumulative cost accounting

- Per-message `UsageCost.cost_inr` is computed upstream by P4 (this change does NOT compute token prices).
- On each turn, when the `usage` event arrives, the handler reads `cost_inr` from `event.data`, calls `store.add_cost(session_id, cost_inr)` to fold it into `Session.cumulative_cost_inr`, and enriches the outgoing `usage` event's `data` with `cumulative_cost_inr` (running total for that session across all threads/messages).
- The frontend top-left card therefore reads per-message `cost_inr` + `latency_ms` and the conversation-level `cumulative_cost_inr` from the same event.

### CORS

- `create_app()` installs `CORSMiddleware` with allowed origins read from `Settings` (e.g. `FRONTEND_ORIGIN`, default `http://localhost:5173`), `allow_methods=["*"]`, `allow_headers=["*"]`, `allow_credentials=True`. If `FRONTEND_ORIGIN` is absent from P0's config, that is a P0 addition (noted); P5 falls back to a sensible localhost dev default so it runs standalone.

### App factory & entrypoint

- `create_app() -> FastAPI` builds the app, adds CORS, instantiates `SessionStore`, mounts the router — pure, no import-time side effects — so tests construct isolated apps.
- `backend/api/main.py` exposes `app = create_app()` for `uvicorn backend.api.main:app`.

## Risks / Trade-offs

- **[In-memory single-process session store]** → sessions vanish on restart and don't survive multiple workers. Acceptable for the POC; documented. A durable/shared store (Redis) is a follow-up, out of P5 scope.
- **[Session token stored server-side]** → the FINX JWT lives in process memory keyed by an opaque `session_id`; the id (not the token) crosses the wire on each chat. POC-appropriate; hardening (encryption at rest, TTL/expiry) is future work.
- **[SSE + buffering proxies]** → `X-Accel-Buffering: no` and `Cache-Control: no-cache` mitigate; a proxy that still buffers would delay `status`/`token` events. Frontend deployment must not buffer the stream.
- **[Client disconnect mid-stream]** → the generator wraps agent iteration in try/except and finally-closes; history is committed only after `done`, so partial turns are not persisted. The upstream agent is not cancelled beyond generator GC (POC-acceptable).
- **[Error surface]** → failures before headers flush return a JSON `4xx/5xx`; failures after the stream opens are emitted as a terminal `error` SSE event (cannot change the HTTP status once `200 text/event-stream` is committed).

## Open Questions

- Exact `FRONTEND_ORIGIN` value(s) for the deployed P8 POC — resolved via P0 config; P5 defaults to `http://localhost:5173` for local dev.
- Whether `/chat` should also be offered as `GET /chat/stream` (query-param based) for `EventSource` compatibility — P8's fetch-based SSE client uses `POST /chat`; a `GET` alias can be added non-breakingly if P8 needs native `EventSource`.
