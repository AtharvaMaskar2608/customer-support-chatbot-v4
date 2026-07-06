## Why

The Choice FinX support chatbot must be observable end-to-end: both the RAG retrieval path (P1) and the multi-turn agentic loop (P4) need structured traces — spans for retrieval, tool calls, model/LLM calls, and per-turn agent behavior — with multi-turn traces stitched into one thread/session by a shared `thread_id`. DeepEval + Confident AI provide the tracing primitives (`@observe`, `update_current_span`, `update_current_trace`, `trace_manager.configure`), but P1 and P4 are built in parallel by different agents and must not each re-invent tracing setup, span-type choices, or thread-grouping wiring. That would produce drift (inconsistent span types, duplicated config, divergent recording conventions) and would couple two otherwise-independent changes.

This change owns `backend/tracing/` only. It provides the thin, stable **tracing interface** that P1 and P4 import to instrument their functions — a single `init_tracing()`, a typed `observe(...)` decorator, a `set_thread_id(...)` helper, and the documented conventions for what each span type records. It wraps DeepEval so downstream code depends on `backend.tracing`, not on DeepEval's surface directly, and it degrades to a safe no-op when tracing is disabled or no key is present. It applies no decorators inside rag/agent code (P1/P4 do that) and defines no evaluation metrics (P6/P7).

## What Changes

- Add `init_tracing() -> None` in `backend/tracing/`: configure DeepEval / Confident AI from `backend.config.settings` (Confident API key, environment, sampling rate, tracing toggle). Idempotent and no-op safe when the key is absent or tracing is disabled — never raises on missing config.
- Add `observe(span_type: str, name: str | None = None)`: a decorator that wraps DeepEval's `@observe`, restricting `span_type` to `{"retriever", "tool", "llm", "agent"}`. When tracing is disabled it returns the wrapped function unchanged (pass-through), so decorated code runs identically with or without tracing.
- Add `set_thread_id(thread_id: str) -> None` plus a `thread_context(thread_id)` context-manager helper: attach `thread_id` to the current trace (via DeepEval's `update_current_trace`) so multi-turn traces group into one thread/session. No-op when tracing is disabled.
- Add span-recording helpers so callers record conventionally without importing DeepEval directly: `record_retriever(query, chunks, ...)`, `record_tool(name, input, output, ok)`, `record_llm(model, input_tokens, output_tokens)`, `record_agent(...)` — thin wrappers over `update_current_span` / `update_current_trace`. Each is a no-op when tracing is disabled.
- Document the conventions for what each span type records: retriever (input query, output chunks / `retrieval_context`, latency), tool (name, input, output, ok), llm (model, input/output tokens), agent (root span; `thread_id`, per-turn metadata).
- NOT in scope: applying decorators inside `backend/rag/` or `backend/agent/` (P1/P4 do that by importing `backend.tracing`); no eval metrics or metric collections (P6/P7); no changes to `pyproject.toml`, `.env`, root config, or DB schema.

## Capabilities

### New Capabilities
- `tracing-observability`: a DeepEval/Confident AI-backed tracing interface (`init_tracing`, the typed `observe` span decorator, `set_thread_id`/`thread_context`, and per-span-type recording conventions) that P1 (rag) and P4 (agent) import to emit retriever/tool/llm/agent spans and group multi-turn traces by `thread_id`, degrading to a safe no-op when tracing is disabled.

### Modified Capabilities
<!-- None — this change only adds a new capability inside backend/tracing/. -->

## Impact

- New files only, all inside the owned directory `backend/tracing/`:
  - `backend/tracing/__init__.py` — re-export `init_tracing`, `observe`, `set_thread_id`, `thread_context`, and the `record_*` helpers.
  - `backend/tracing/config.py` — `init_tracing()` and the internal "is tracing enabled" check driven by `backend.config.settings`.
  - `backend/tracing/spans.py` — the `observe` decorator, span-type taxonomy constant, and `record_*` recording helpers.
  - `backend/tracing/thread.py` — `set_thread_id` and the `thread_context` context manager.
  - `backend/tracing/tests/__init__.py`
  - `backend/tracing/tests/test_tracing.py` — decorated-dummy emits a span; two traces sharing a `thread_id` group into one thread; disabled mode degrades to no-op.
- Imports only (does not modify): `backend.config.settings.Settings` (`CONFIDENT_API_KEY` / tracing toggle keys) and DeepEval's `deepeval.tracing` (`observe`, `update_current_span`, `update_current_trace`, `trace_manager`).
- Depends on P0 `foundations-and-contracts` (config surface) being merged to `main` first. `deepeval` is already declared in the P0 dependency manifest; no new dependency is introduced. If the reviewer finds `deepeval` missing from the manifest, that is a P0 addition, not this change.
- Downstream P1 (rag) and P4 (agent) soft-depend on this change for decorators and thread grouping; both are written to degrade gracefully if `backend.tracing` is absent, so this change and P1/P4 stay parallelizable.
