## ADDED Requirements

### Requirement: Anthropic Messages API tool-use loop

The system SHALL run an Anthropic Messages API loop that calls the model, executes any requested tool calls, feeds each `tool_result` back into the conversation, and repeats until the model returns a final text answer. Thinking MUST be disabled and the model id MUST be read from `backend.config.settings.Settings.ANTHROPIC_MODEL` (never hardcoded). Three tools SHALL be registered — `rag_search`, `cml_report`, `contract_note` — and dispatched to `backend.rag.rag_search`, `backend.tools.cml_report`, and `backend.tools.contract_note`; the `SessionContext` MUST be injected server-side into report-tool calls and MUST NOT be exposed as a model-visible tool argument. Each tool invocation SHALL be recorded as a `ToolCallRecord{name, input, ok}` on the resulting `AgentReply`, and a tool error SHALL be returned to the model as an error `tool_result` rather than crashing the loop.

#### Scenario: Model requests a tool and receives the result

- **WHEN** the model responds with a tool-use block for `rag_search` during a turn
- **THEN** the loop executes `rag_search`, appends a `ToolCallRecord{name="rag_search", ok=True}`, feeds the tool result back as a `tool_result`, and calls the model again until a final text answer is produced

#### Scenario: Report tool receives the session server-side

- **WHEN** the model requests `cml_report` with `search_value`
- **THEN** the loop calls `cml_report(session, search_value)` with the server-held `SessionContext`, and the session token is never present in the model-visible messages or tool schema

### Requirement: System prompt contents

The system SHALL construct the system prompt so that it always contains three blocks: (1) the list of available tools (`rag_search`, `cml_report`, `contract_note`), (2) the list of KB question categories / in-scope topics the agent can answer, and (3) the guardrails. The system prompt MUST be re-supplied on every model call within a turn so its instructions persist across tool use.

#### Scenario: Prompt lists tools and in-scope categories

- **WHEN** the system prompt is built for a turn
- **THEN** it contains the three tool names and the enumerated in-scope KB question categories, and it is passed as the system prompt on every model call in that turn

### Requirement: Clarifying-question cap

The agent SHALL ask at most 2 clarifying questions per conversation. When the agent asks a clarifying question, it MUST end the turn with `AgentReply.awaiting_user=True` and MUST NOT be forced to answer in the same turn. Once 2 clarifying questions have already been asked in the conversation, the agent MUST NOT ask a third and MUST instead proceed to answer or offer a support ticket.

#### Scenario: Agent asks a clarifying question

- **WHEN** the newest user message is ambiguous and fewer than 2 clarifying questions have been asked so far
- **THEN** the agent returns a clarifying question with `awaiting_user=True` and does not fabricate an answer

#### Scenario: Third clarifying question is suppressed

- **WHEN** the conversation already contains 2 prior clarifying questions and the newest message is still ambiguous
- **THEN** the agent does not ask a third clarifying question and instead attempts an answer or offers to raise a support ticket

### Requirement: Message cap with ticket offer

The conversation SHALL be limited to at most 10 to-and-fro messages. When a cap (the 10-message limit, or exhaustion of the per-turn tool-iteration budget) is reached without the user's issue being resolved, the agent MUST set `AgentReply.ticket_offered=True` and offer to raise a support ticket instead of continuing to loop.

#### Scenario: Message cap reached without resolution

- **WHEN** continuing the conversation would exceed 10 to-and-fro messages and the issue is unresolved
- **THEN** the agent stops looping, sets `ticket_offered=True`, and returns a message offering to raise a support ticket

#### Scenario: Tool-iteration budget exhausted

- **WHEN** a single turn exhausts its bounded tool-call iterations without reaching a final answer
- **THEN** the agent stops, sets `ticket_offered=True`, and offers to raise a support ticket rather than looping indefinitely

### Requirement: Citations in RAG-grounded answers

When an answer is grounded in `rag_search` output, the agent SHALL aggregate the `Citation`s from the retrieved chunks into `AgentReply.citations`, and such a grounded answer MUST carry at least one citation.

#### Scenario: KB answer includes citations

- **WHEN** the agent answers a knowledge-base question using `rag_search` results
- **THEN** `AgentReply.citations` is non-empty and its citations correspond to the chunks used

### Requirement: Cost and latency accounting

The agent SHALL populate `AgentReply.usage` (`UsageCost`) with the turn's `input_tokens` and `output_tokens` from the Anthropic response, `cost_inr = (input_tokens × input USD price + output_tokens × output USD price) × Settings.USD_TO_INR`, and `latency_ms` as the wall-clock duration of the turn. Token usage across all model calls in a turn MUST be summed.

#### Scenario: Reply reports summed cost and latency

- **WHEN** a turn makes more than one model call (because a tool was used)
- **THEN** `usage.input_tokens` and `usage.output_tokens` are the sums across those calls, `cost_inr` applies the USD prices and `USD_TO_INR`, and `latency_ms` reflects the whole turn

### Requirement: Entrypoints

The system SHALL expose `agent_reply(history: list[dict], session: SessionContext, thread_id: str) -> AgentReply` for non-streaming use and `agent_reply_stream(history, session, thread_id) -> Iterator[SseEvent]` for streaming use. Both MUST share one internal driver so caps, guardrails, citations, and cost behave identically, and both MUST forward `thread_id` to tracing (`set_thread_id`) when available, degrading gracefully when P3 tracing is absent.

#### Scenario: Non-streaming and streaming agree

- **WHEN** the same `history` and `session` are processed by `agent_reply` and by `agent_reply_stream`
- **THEN** the final `content`, `citations`, and the `awaiting_user`/`ticket_offered` flags are equivalent between the two entrypoints

### Requirement: Streaming event sequence

`agent_reply_stream` SHALL emit `SseEvent`s in the order: one or more `status` events (e.g. "Looking up the knowledge base…", "Generating the answer…"), then zero or more `token` events carrying answer text, then exactly one `citations` event, then exactly one `usage` event, then a terminal `done` event carrying the `awaiting_user` and `ticket_offered` flags. On failure, a terminal `error` event MUST replace the remaining sequence. `token` events MUST NOT be emitted after the `citations` event.

#### Scenario: Successful stream ordering

- **WHEN** a KB question is answered via streaming
- **THEN** the consumer receives `status` event(s), then `token` events, then one `citations` event, then one `usage` event, then a `done` event, in that order

#### Scenario: Error terminates the stream

- **WHEN** an unrecoverable error occurs mid-stream
- **THEN** an `error` event is emitted and no further events (including `done`) follow it
