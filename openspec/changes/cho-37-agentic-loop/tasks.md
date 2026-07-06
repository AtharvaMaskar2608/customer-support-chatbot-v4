## 1. Package skeleton (owned dir: backend/agent/)

- [ ] 1.1 Add `backend/agent/__init__.py` re-exporting `agent_reply` and `agent_reply_stream`
- [ ] 1.2 Add `backend/agent/tests/__init__.py`
- [ ] 1.3 Confirm no file outside `backend/agent/` is created or modified (P0 owns skeleton/root config; P1 `backend/rag/`; P2 `backend/tools/`; P3 `backend/tracing/`)

## 2. Tool registration & dispatch (backend/agent/tools.py)

- [ ] 2.1 Define the three tool JSON schemas: `rag_search` (`query`, optional `top_k` default 10), `cml_report` (`search_value`), `contract_note` (`mobile_no`, `contract_date` DD-MM-YYYY) — model-visible args only; `session` is NOT a schema property
- [ ] 2.2 Build a name→callable dispatch table: `rag_search(query, top_k)`, `cml_report(session, search_value)`, `contract_note(session, mobile_no, contract_date)`, injecting `SessionContext` server-side
- [ ] 2.3 On tool exception, return `ok=False` + an error `tool_result` to the model instead of raising; record a `ToolCallRecord{name, input, ok}` per call
- [ ] 2.4 Where P2 publishes canonical report tool schemas, mirror/import them so this table cannot drift from P2's contract

## 3. System prompt (backend/agent/prompt.py)

- [ ] 3.1 Define the in-scope KB question-category catalogue as a module constant
- [ ] 3.2 Implement `build_system_prompt()` composing role + (1) tool list + (2) KB categories + (3) guardrails, thinking disabled
- [ ] 3.3 Ensure the system prompt is re-supplied on every model call within a turn

## 4. Guardrails (backend/agent/guardrails.py)

- [ ] 4.1 Author the SEBI no-advice instruction block (no opinions/advice/recommendations on reports or investments, holds after tool use and under pressure)
- [ ] 4.2 Author the Choice FinX scope instruction block (decline + politely redirect off-topic)
- [ ] 4.3 Add a deterministic backstop that maps obvious advice-seeking / off-topic probes to the canonical decline/redirect text so guardrails do not depend solely on model compliance

## 5. Cost accounting (backend/agent/cost.py)

- [ ] 5.1 Define per-token USD input/output price constants for the configured Sonnet model (comment citing source)
- [ ] 5.2 Implement `compute_usage(input_tokens, output_tokens, latency_ms) -> UsageCost` with `cost_inr = (in_tokens×in_price + out_tokens×out_price) × Settings.USD_TO_INR`
- [ ] 5.3 Sum token usage across all model calls in a turn

## 6. Agentic loop & entrypoints (backend/agent/loop.py)

- [ ] 6.1 Implement the Anthropic Messages API loop: model call → execute tool calls → feed `tool_result` back → repeat until final text; thinking disabled; model from `Settings.ANTHROPIC_MODEL`
- [ ] 6.2 Implement the cap state machine: ≤2 clarifying questions (set `awaiting_user=True`), ≤10 to-and-fro messages, bounded per-turn tool iterations; on cap-without-resolution set `ticket_offered=True` and offer a support ticket
- [ ] 6.3 Aggregate `Citation`s from `rag_search` output into `AgentReply.citations`; ensure a RAG-grounded answer carries ≥1 citation
- [ ] 6.4 Implement `agent_reply(history, session, thread_id) -> AgentReply` (non-streaming) over the shared driver
- [ ] 6.5 Implement `agent_reply_stream(history, session, thread_id) -> Iterator[SseEvent]` emitting `status`→`token`*→`citations`→`usage`→`done` (or terminal `error`), with `token` never after `citations`
- [ ] 6.6 Wrap llm/tool/agent spans with optional `backend.tracing.observe` and call `set_thread_id(thread_id)` when P3 is present; degrade gracefully when absent

## 7. Verification & done condition

- [ ] 7.1 Tests (mocked Anthropic client + stubbed `rag_search`/report tools): multi-turn convo resolves a KB question WITH non-empty citations; a SEBI advice probe (incl. after report tool use and under pressure) is declined; an off-topic message is redirected; ≤2 clarifying-question cap and ≤10-message cap enforced with `ticket_offered=True` and a ticket offer; streaming event order asserted; non-streaming/streaming parity asserted
- [ ] 7.2 Run `openspec validate agentic-loop --strict` — passes
- [ ] 7.3 **Done condition:** the behavioural tests above are green — a KB question resolves with citations, SEBI advice is declined, off-topic is redirected, and both caps trigger a ticket offer. **Test command:** `pytest backend/agent -q`
