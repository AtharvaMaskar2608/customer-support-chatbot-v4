## 1. API package skeleton

- [ ] 1.1 Create `backend/api/__init__.py` re-exporting `create_app` (all new files live under the owned dir `backend/api/` only)
- [ ] 1.2 Create `backend/api/tests/__init__.py`
- [ ] 1.3 Confirm imports resolve against P0/P4: `backend.config.settings.Settings`, `backend.contracts.session.SessionContext`, `backend.contracts.sse.SseEvent`, `backend.contracts.agent.UsageCost`, `backend.contracts.retrieval.Citation`, `backend.agent.agent_reply_stream` — no redefinition of any P0 contract

## 2. HTTP DTOs

- [ ] 2.1 Implement `backend/api/schemas.py` with `SessionCreateRequest{client_code, session_token}`, `SessionCreateResponse{session_id}`, `ChatRequest{session_id, thread_id, message}` (transport shapes only; import `SessionContext`, do not redefine it)

## 3. Session store

- [ ] 3.1 Implement `backend/api/sessions.py` with a `Session` dataclass (`session_id`, `context: SessionContext`, `threads: dict[str, list[dict]]`, `cumulative_cost_inr: float`) and a thread-safe `SessionStore` (`create`, `get`, `history`, `append_turn`, `add_cost`) using a `threading.Lock`; session ids are `uuid4` hex
- [ ] 3.2 Contract: `SessionStore.create(ctx) -> Session`; `get(session_id) -> Session | None`; `history(session_id, thread_id) -> list[dict]`; `append_turn(session_id, thread_id, user_msg, assistant_msg) -> None`; `add_cost(session_id, cost_inr) -> float` (returns new cumulative)

## 4. Routes

- [ ] 4.1 Implement `POST /session` in `backend/api/routes.py`: build `SessionContext` (trims both fields), reject empty-after-trim with `422`, create a session, return `SessionCreateResponse{session_id}` with `200` (never echo the token)
- [ ] 4.2 Implement `POST /chat` SSE handler: resolve `session_id` (`404` if unknown), append user `message` to `(session_id, thread_id)` history, iterate `agent_reply_stream(history, session.context, thread_id)`, and yield one SSE frame per `SseEvent` as `event: <name>\ndata: <json>\n\n` preserving order `status → token(s) → citations → usage → done`
- [ ] 4.3 In the `usage` event, call `store.add_cost(...)` with the turn's `cost_inr` and inject `cumulative_cost_inr` into the event `data` before yielding
- [ ] 4.4 Accumulate `token` text and commit the assistant turn to history only after `done`; on exception during iteration emit a terminal `error` frame and do not persist a partial turn
- [ ] 4.5 Return the stream as `StreamingResponse(..., media_type="text/event-stream")` with `Cache-Control: no-cache` and buffering-disabled headers; add `GET /healthz`

## 5. App factory & entrypoint

- [ ] 5.1 Implement `create_app() -> FastAPI` in `backend/api/app.py`: instantiate one `SessionStore`, add `CORSMiddleware` with origin from `Settings` (fallback `http://localhost:5173`), mount the router; no import-time side effects
- [ ] 5.2 Implement `backend/api/main.py` exposing `app = create_app()` for `uvicorn backend.api.main:app`

## 6. Tests

- [ ] 6.1 `backend/api/tests/test_session.py`: `POST /session` returns a `session_id`; whitespace is trimmed on the stored `SessionContext`; empty-after-trim → `422`; response never contains the raw token (uses starlette `TestClient` / httpx `AsyncClient`)
- [ ] 6.2 `backend/api/tests/test_chat_sse.py`: with a **stubbed `agent_reply_stream`** yielding `status → token → citations → usage → done`, assert the SSE response `Content-Type` is `text/event-stream`, the framed events arrive in that order, `usage.data` includes `cumulative_cost_inr`, per-`(session,thread)` history accumulates across turns, unknown `session_id` → `404`, and a raising stub yields a terminal `error` frame with no partial history commit
- [ ] 6.3 Run `openspec validate api-sse-session --strict` — passes
- [ ] 6.4 **Done condition:** `POST /session` returns a session and the SSE `/chat` endpoint streams `status + token + citations + usage (with cumulative_cost_inr) + done` events for a KB question with a stubbed agent. **Test command:** `pytest backend/api -q`
