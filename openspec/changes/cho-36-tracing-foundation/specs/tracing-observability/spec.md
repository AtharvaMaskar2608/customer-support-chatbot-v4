## ADDED Requirements

### Requirement: Tracing initialization from configuration

The system SHALL provide `init_tracing() -> None` that configures DeepEval / Confident AI from `backend.config.settings` (Confident API key, environment, sampling rate, and the tracing toggle). `init_tracing()` MUST be idempotent and MUST NOT raise when the Confident API key is absent or tracing is disabled; in that case it configures a disabled (no-op) tracing state instead of failing.

#### Scenario: Initialization with a Confident API key enables tracing

- **WHEN** `init_tracing()` is called and the configured settings provide a Confident API key with tracing enabled
- **THEN** DeepEval / Confident AI is configured with that key and subsequent `observe`-decorated calls emit spans

#### Scenario: Initialization without a key degrades to no-op

- **WHEN** `init_tracing()` is called and no Confident API key is present or the tracing toggle is off
- **THEN** the call returns without raising and tracing is left in a disabled state where decorators and recording helpers are pass-throughs

### Requirement: Typed span decorator for retriever, tool, llm, and agent spans

The system SHALL provide a decorator `observe(span_type: str, name: str | None = None)` that wraps DeepEval's `@observe`, where `span_type` is restricted to the taxonomy `{"retriever", "tool", "llm", "agent"}`. Applying the decorator to a function SHALL, when tracing is enabled, cause each invocation of that function to emit a span of the given type as part of the active trace, capturing the function input and output. An unknown `span_type` MUST be rejected.

#### Scenario: Decorated retriever function emits a retriever span

- **WHEN** a function decorated with `observe("retriever")` is called while tracing is enabled
- **THEN** a span of type `retriever` is emitted within the current trace recording the call's input and output

#### Scenario: Each taxonomy type emits its corresponding span

- **WHEN** functions decorated with `observe("tool")`, `observe("llm")`, and `observe("agent")` are called while tracing is enabled
- **THEN** each emits a span of the matching type (`tool`, `llm`, `agent`) nested under the active trace by call stack

#### Scenario: Invalid span type is rejected

- **WHEN** `observe` is applied with a `span_type` outside `{"retriever","tool","llm","agent"}`
- **THEN** a `ValueError` is raised at decoration time naming the allowed span types

### Requirement: Per-span-type recording conventions

The system SHALL provide recording helpers that attach conventional attributes to the active span or trace without callers importing DeepEval directly: retriever spans record the input query and the output chunks as `retrieval_context` (plus latency, captured automatically); tool spans record tool name, input, output, and an `ok` flag; llm spans record model name and input/output token counts; the agent root span records `thread_id` and per-turn metadata. Each helper MUST be a no-op when tracing is disabled.

#### Scenario: Retriever span records query and retrieved chunks

- **WHEN** a retriever recording helper is called with the query and retrieved chunks inside an active `retriever` span
- **THEN** the query is recorded as the span input and the chunks are attached as `retrieval_context` on that span

#### Scenario: LLM span records model and token usage

- **WHEN** an llm recording helper is called with a model name and input/output token counts inside an active `llm` span
- **THEN** the model name and token counts are recorded on that span

#### Scenario: Recording helpers no-op when tracing disabled

- **WHEN** any recording helper is called while tracing is disabled
- **THEN** it returns without error and without attempting to contact DeepEval or Confident AI

### Requirement: Multi-turn thread grouping by thread_id

The system SHALL provide `set_thread_id(thread_id: str) -> None` and a `thread_context(thread_id)` context-manager helper that attach the given `thread_id` to the current trace, so that traces produced across separate turns sharing the same `thread_id` are grouped into a single thread/session. These helpers MUST be a no-op when tracing is disabled.

#### Scenario: Two traces sharing a thread_id group into one thread

- **WHEN** two separate decorated turns are executed, each attaching the same `thread_id` via `set_thread_id` or `thread_context`
- **THEN** both resulting traces carry that `thread_id` and are grouped into one thread/session

#### Scenario: Distinct thread_ids remain separate threads

- **WHEN** two turns attach different `thread_id` values
- **THEN** their traces are not grouped into the same thread

### Requirement: Graceful no-op when tracing is disabled

The system SHALL ensure that when tracing is disabled (no Confident API key or the tracing toggle off), every public entry point — `observe`, `set_thread_id`, `thread_context`, and the recording helpers — behaves as a transparent pass-through: decorated functions return their normal results and no exception related to tracing is raised. Downstream code in `backend/rag/` and `backend/agent/` MUST run identically whether tracing is enabled or disabled.

#### Scenario: Decorated function runs unchanged with tracing disabled

- **WHEN** tracing is disabled and a function decorated with `observe("agent")` is invoked
- **THEN** the function executes and returns its normal result with no span emitted and no exception raised
