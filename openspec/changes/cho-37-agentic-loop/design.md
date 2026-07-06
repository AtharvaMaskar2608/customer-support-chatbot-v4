## Context

This change lands the orchestration layer (P4) of the Choice FinX support chatbot. It sits above retrieval and the report tools and below the HTTP/SSE transport.

Files touched (all under the owned directory `backend/agent/`):
- `backend/agent/loop.py` — Messages API loop, tool dispatch, cap state machine, `agent_reply` / `agent_reply_stream`.
- `backend/agent/prompt.py` — system-prompt builder + KB category catalogue.
- `backend/agent/tools.py` — tool JSON schemas + name→callable dispatch.
- `backend/agent/guardrails.py` — guardrail instruction text + deterministic scope/SEBI checks.
- `backend/agent/cost.py` — `UsageCost` computation.
- `backend/agent/__init__.py`, `backend/agent/tests/`.

Dependencies (import, do not redefine):
- P0: `backend.config.settings.Settings` (`ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `USD_TO_INR`); `backend.contracts.session.SessionContext`; `backend.contracts.agent` (`AgentReply`, `ToolCallRecord`, `UsageCost`); `backend.contracts.retrieval.Citation`; `backend.contracts.sse.SseEvent`.
- P1: `backend.rag.rag_search(query, top_k=10) -> RagToolOutput{chunks: list[RetrievedChunk]}`.
- P2: `backend.tools.cml_report(session, search_value)` and `backend.tools.contract_note(session, mobile_no, contract_date) -> ReportResult`, plus their published tool JSON schemas.
- P3 (soft): `backend.tracing.observe(...)` decorator + `set_thread_id`.

The Anthropic model is `claude-sonnet-4-5` with **thinking disabled**; the concrete id is always read from `Settings.ANTHROPIC_MODEL`, never hardcoded.

## Goals / Non-Goals

Goals:
- One tested, transport-agnostic agent brain with a non-streaming and a streaming entrypoint.
- Deterministic caps and guardrails that hold across turns and tool use.
- Citable RAG answers and per-turn cost/latency accounting.

Non-Goals:
- HTTP routing, SSE wire framing, session persistence (P5).
- Retrieval internals (P1), report HTTP clients (P2), tracing backend setup (P3), evals, frontend.
- Multi-agent handoff, streaming *partial* tool arguments, or human-in-the-loop ticket *creation* (we only *offer* a ticket).

## Decisions

### Entrypoint signatures
```python
# backend/agent/loop.py
def agent_reply(
    history: list[dict],          # [{"role": "user"|"assistant", "content": str}, ...]
    session: SessionContext,
    thread_id: str,
) -> AgentReply: ...

def agent_reply_stream(
    history: list[dict],
    session: SessionContext,
    thread_id: str,
) -> Iterator[SseEvent]: ...       # generator; P5 adapts to text/event-stream
```
- `history` is the full to-and-fro so far; the newest user message is the last element. The loop maps it to Anthropic `messages` and never trusts the client for system text.
- `session` is passed to report-tool callables only; it is never serialized into the model context (the JWT stays server-side).
- `thread_id` is forwarded to `set_thread_id(thread_id)` so P3 spans correlate; a no-op when tracing is absent.
- Both entrypoints share one internal driver so behaviour (caps, guardrails, citations, cost) is identical; the streaming variant additionally yields `SseEvent`s.

### Tool registration (JSON schemas sent to Anthropic)
Three `tools=[...]` entries. Schemas describe only model-supplied arguments; `session` is injected server-side at dispatch and is NOT a tool property.
```jsonc
// rag_search
{"name": "rag_search",
 "description": "Search the Choice FinX knowledge base for grounded, citable answers. Use for any in-scope product/how-to/policy question.",
 "input_schema": {"type": "object",
   "properties": {"query": {"type": "string", "description": "Natural-language search query"},
                  "top_k": {"type": "integer", "default": 10, "minimum": 1, "maximum": 20}},
   "required": ["query"]}}

// cml_report  (session injected server-side)
{"name": "cml_report",
 "description": "Fetch the client's CML (Client Master List) report from Choice FinX. Returns data only; never interpret or advise on it.",
 "input_schema": {"type": "object",
   "properties": {"search_value": {"type": "string", "description": "Client code or identifier to search the CML by"}},
   "required": ["search_value"]}}

// contract_note  (session injected server-side)
{"name": "contract_note",
 "description": "Fetch a contract note for the client from Choice FinX. Returns data only; never interpret or advise on it.",
 "input_schema": {"type": "object",
   "properties": {"mobile_no": {"type": "string", "description": "Registered mobile number"},
                  "contract_date": {"type": "string", "description": "Contract date in DD-MM-YYYY"}},
   "required": ["mobile_no", "contract_date"]}}
```
Dispatch table maps tool name → callable: `rag_search(query, top_k)`; `cml_report(session, search_value)`; `contract_note(session, mobile_no, contract_date)`. The canonical report schemas are those published by P2; if they diverge, P2's schema wins and this table is updated (no contract redefinition here). Each dispatch appends a `ToolCallRecord{name, input, ok}` to the reply; a tool exception yields `ok=False` and a `tool_result` with `is_error=True` fed back to the model rather than crashing the loop.

### System-prompt structure (`prompt.py`)
`build_system_prompt()` composes, in order:
1. **Role**: "You are the Choice FinX customer-support assistant."
2. **Available tools**: names + one-line purpose for `rag_search`, `cml_report`, `contract_note` (block (1), mandatory).
3. **In-scope KB categories**: the catalogue of question categories the agent can answer (block (2), mandatory) — e.g. account opening & KYC, login/access, fund transfer/payments, brokerage & charges, reports (CML / contract notes), order & trade queries, technical/app issues, general Choice FinX product info. Anything outside is out of scope.
4. **Guardrails** (block (3), mandatory): SEBI no-advice; scope redirect; citation requirement for KB answers; clarifying-question and message caps + ticket-offer behaviour.
The catalogue lives as a module constant so tests can assert its presence and the same list appears in the prompt.

### Cap state machine (`loop.py`)
State derived from `history` + the current turn, not stored externally:
- `clarifying_asked = count(assistant turns in history that were clarifying questions)`. The agent may ask a clarifying question only if `clarifying_asked < 2`. When it does, the turn ends with `awaiting_user=True` and no tool answer is forced.
- `message_count = len(history) + 1` (this turn). If issuing another to-and-fro would exceed 10, or a cap is hit without resolution, the driver stops looping, sets `ticket_offered=True`, and returns a reply offering to raise a support ticket instead of continuing.
- Tool-call iterations within a single turn are bounded (max internal loop iterations, e.g. 6) to prevent infinite tool loops; exhausting them also triggers the ticket offer.
- Precedence per turn: guardrail block (SEBI/scope) → cap check → clarifying-question allowance → tool loop → final answer.

### Guardrails (`guardrails.py`)
- Primary enforcement is via the mandatory guardrail block in the system prompt, reinforced on every model call (persists across follow-ups and after tool results because the system prompt is re-sent each call).
- SEBI: never provide opinions/advice/recommendations on reports or investments; when a report tool returns data, present facts only and refuse interpretation even under pressure.
- Scope: decline non-Choice-FinX topics and politely redirect to Choice FinX support topics.
- A lightweight deterministic backstop may short-circuit obvious advice-seeking / off-topic probes into the canonical decline/redirect text, so guardrails do not depend solely on model compliance.

### Cost formula (`cost.py`)
```python
cost_inr = (input_tokens * IN_PRICE_USD_PER_TOKEN
            + output_tokens * OUT_PRICE_USD_PER_TOKEN) * settings.USD_TO_INR
```
Token counts come from the Anthropic response `usage`. Per-token USD prices for the configured Sonnet model are module constants (published list prices); `USD_TO_INR` comes from `Settings`. `latency_ms` is wall-clock around the turn. Streaming sums `usage` across all model calls in the turn.

### Streaming `SseEvent` order (`agent_reply_stream`)
Exactly this ordering per turn:
1. `status` — one per phase, e.g. `{"message": "Looking up the knowledge base…"}` before a `rag_search`, `{"message": "Generating the answer…"}` before the final generation.
2. `token` — zero or more, streaming the final answer text as `{"text": "…"}`.
3. `citations` — once, `{"citations": [Citation, …]}` (empty list if no RAG grounding).
4. `usage` — once, the `UsageCost` payload.
5. `done` — once, terminal, carrying the flags `{"awaiting_user": bool, "ticket_offered": bool}`.
On failure, an `error` event replaces the remaining sequence and is terminal. `citations`/`usage` precede `done`; `token`s never follow `citations`.

## Risks / Trade-offs
- **Guardrail reliability**: model-based guardrails can be jailbroken. Mitigation: re-send the guardrail block every call + deterministic backstop + tests for SEBI-pressure and off-topic probes.
- **Cap accounting from stateless `history`**: mis-counting could over/under-limit. Mitigation: derive counts deterministically and unit-test the 2-question and 10-message boundaries incl. the ticket offer.
- **P2 schema drift**: our tool JSON schemas mirror P2's published ones; if P2 changes them, our dispatch/schema must follow. Mitigation: import P2 schemas where exposed rather than re-typing, and pin the contract in tasks.
- **Price constants staleness**: hardcoded USD per-token prices can drift from Anthropic list prices. Mitigation: keep them isolated in `cost.py` as named constants with a comment citing the source; `USD_TO_INR` stays in config.
- **Streaming vs non-streaming parity**: two code paths risk divergence. Mitigation: share one driver; test that a fixed conversation yields the same final `content`, `citations`, and flags through both entrypoints.
