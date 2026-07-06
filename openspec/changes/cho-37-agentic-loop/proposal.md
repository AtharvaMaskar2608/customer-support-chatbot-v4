## Why

The Choice FinX support chatbot needs a single agentic brain that turns a multi-turn conversation into a grounded, safe, cost-accounted reply. Retrieval (P1), report tools (P2), and tracing (P3) each exist in isolation; nothing yet *orchestrates* them into an Anthropic Messages API tool-use loop, enforces the conversation caps, or holds the SEBI and scope guardrails across follow-ups and tool calls. This change owns that orchestration and nothing else.

It provides the two entrypoints every transport (P5) will call — `agent_reply` (non-streaming) and `agent_reply_stream` (streaming `SseEvent`s) — so that a KB question resolves *with citations*, a SEBI advice probe is *declined*, an off-topic message is *redirected*, and the agent never runs away: at most 2 clarifying questions and at most 10 to-and-fro messages, after which it offers to raise a support ticket.

## What Changes

- Implement an Anthropic Messages API agentic loop (call model → execute tool calls → feed `tool_result` back → repeat until a final text answer), **thinking disabled**, model read from `backend.config.settings.Settings.ANTHROPIC_MODEL`.
- Register three tools with JSON schemas and dispatch them: `rag_search` (P1), `cml_report` (P2), `contract_note` (P2). Report tools receive the `SessionContext`; the model never sees the session token.
- Build the system prompt from three mandatory blocks: (1) the list of available tools, (2) the list of KB question categories / in-scope topics the agent can answer, (3) the guardrails (SEBI no-advice; scope redirect; citation requirement; cap behaviour).
- Enforce conversation caps: at most 2 clarifying questions per conversation (set `AgentReply.awaiting_user=True` when asking one); at most 10 total to-and-fro messages; when a cap is reached without resolution, set `AgentReply.ticket_offered=True` and offer to raise a support ticket.
- Enforce guardrails across every turn and after any tool use: never give opinions/advice/recommendations on reports or investments (SEBI), no matter how the user pushes; decline and politely redirect anything unrelated to Choice FinX (scope).
- Aggregate `Citation`s from `rag_search` output into `AgentReply.citations`; a RAG-grounded answer MUST carry at least one citation.
- Compute `UsageCost`: `input_tokens`, `output_tokens`, `cost_inr = (input_tokens × in_price_usd + output_tokens × out_price_usd) × USD_TO_INR`, `latency_ms`.
- Provide `agent_reply_stream` emitting the ordered `SseEvent` sequence for P5: `status` (e.g. "Looking up the knowledge base…", "Generating the answer…") → `token`* → `citations` → `usage` → `done` (or `error`).
- Wrap the llm / tool / agent spans with the optional P3 `backend.tracing.observe` decorator and `set_thread_id`, degrading gracefully when tracing is absent.
- NOT in scope: HTTP/SSE transport & session storage (P5), retrieval internals (P1), report HTTP clients (P2), tracing setup (P3), evals, frontend.

## Capabilities

### New Capabilities
- `agentic-loop`: an Anthropic Messages API tool-use loop that orchestrates `rag_search`, `cml_report`, and `contract_note`, builds the system prompt (tools + in-scope KB categories + guardrails), enforces the clarifying-question and 10-message caps with a ticket offer, aggregates citations, accounts token cost + latency, and exposes non-streaming (`agent_reply`) and streaming (`agent_reply_stream`) entrypoints with a defined `SseEvent` order.
- `conversation-guardrails`: SEBI no-advice and Choice-FinX-scope enforcement that holds across every turn, after follow-ups, and after tool use — the agent declines investment/report advice however the user pushes, and politely redirects off-topic messages.

### Modified Capabilities
<!-- None — this change only adds new capabilities inside backend/agent/. -->

## Impact

- New files only, all inside the owned directory `backend/agent/`:
  - `backend/agent/__init__.py` — re-export `agent_reply`, `agent_reply_stream`.
  - `backend/agent/loop.py` — the Messages API loop, tool dispatch, cap state machine, cost accounting; `agent_reply` + `agent_reply_stream`.
  - `backend/agent/prompt.py` — system-prompt builder (tool list + KB categories + guardrails) and the KB category catalogue.
  - `backend/agent/tools.py` — the three tool JSON schemas and the name→callable dispatch table.
  - `backend/agent/guardrails.py` — guardrail instruction text and any deterministic scope/SEBI checks used alongside the model.
  - `backend/agent/cost.py` — `UsageCost` computation from token counts.
  - `backend/agent/tests/__init__.py`, `backend/agent/tests/test_agent.py` — mocked-Anthropic + stubbed rag/tools behavioural tests.
- Imports only (does not modify): `backend.config.settings.Settings`; `backend.contracts.session.SessionContext`; `backend.contracts.agent` (`AgentReply`, `ToolCallRecord`, `UsageCost`); `backend.contracts.retrieval.Citation`; `backend.contracts.sse.SseEvent`; `backend.rag.rag_search` (P1); `backend.tools.cml_report`, `backend.tools.contract_note` (P2); optionally `backend.tracing.observe` / `set_thread_id` (P3).
- No changes to `pyproject.toml`, `.env`, root config, DB schema, migrations, or lockfiles (owned by P0). The `anthropic` client dependency is already declared by P0; no new dependency is introduced. If the reviewer finds `anthropic` missing from the manifest, that is a P0 addition, not this change.
- Depends on P0 `foundations-and-contracts` (contracts + config) merged to `main` first; on P1 `rag-hybrid-retrieval` (`rag_search`); on P2 `finx-report-tools` (`cml_report`, `contract_note` + their tool schemas). Soft-depends on P3 `tracing-foundation` for span decorators; degrades gracefully without it.
- No file overlap with sibling changes: P1 owns `backend/rag/`, P2 owns `backend/tools/`, P3 owns `backend/tracing/`, P0 owns the skeleton + root config. This change writes only under `backend/agent/`.
