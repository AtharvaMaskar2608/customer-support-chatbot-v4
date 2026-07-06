## 1. Tracing initialization

- [x] 1.1 Implement `backend/tracing/config.py` with `init_tracing()` configuring DeepEval / Confident AI from `backend.config.settings` (Confident API key, environment, sampling rate, tracing toggle); idempotent and no-op safe when the key is absent or tracing is disabled — never raises
- [x] 1.2 Implement the internal `tracing_enabled() -> bool` gate that drives every no-op branch (disabled unless `init_tracing()` configured a live key with the toggle on)

## 2. Span decorator & taxonomy

- [x] 2.1 Implement `backend/tracing/spans.py` with `SPAN_TYPES = ("retriever","tool","llm","agent")` and `observe(span_type, name=None)` wrapping `deepeval.tracing.observe(type=span_type, name=name)`
- [x] 2.2 Raise `ValueError` at decoration time when `span_type` is outside `SPAN_TYPES`; return the wrapped function unchanged when tracing is disabled (pass-through)

## 3. Recording conventions

- [x] 3.1 Implement `record_retriever(query, chunks, metadata=None)` → active retriever span input=query, `retrieval_context=chunks` (via `update_current_span`)
- [x] 3.2 Implement `record_tool(name, input, output, ok)` → active tool span records name/input/output/ok
- [x] 3.3 Implement `record_llm(model, input_tokens, output_tokens)` → active llm span records model + token counts
- [x] 3.4 Implement `record_agent(thread_id=None, metadata=None)` → agent root span/trace records thread_id + per-turn metadata (via `update_current_trace`)
- [x] 3.5 Make every `record_*` helper a no-op when tracing is disabled

## 4. Multi-turn thread grouping

- [x] 4.1 Implement `backend/tracing/thread.py` with `set_thread_id(thread_id)` calling `update_current_trace(thread_id=...)`; no-op when disabled
- [x] 4.2 Implement the `thread_context(thread_id)` context manager (sets thread_id on enter); no-op when disabled

## 5. Package surface

- [x] 5.1 Re-export `init_tracing`, `observe`, `set_thread_id`, `thread_context`, `record_retriever`, `record_tool`, `record_llm`, `record_agent`, `SPAN_TYPES` from `backend/tracing/__init__.py`
- [x] 5.2 Confirm the module imports cleanly without a Confident API key present (no import-time DeepEval network calls)

## 6. Verification

- [x] 6.1 Add `backend/tracing/tests/test_tracing.py`: a dummy function decorated with `observe(...)` emits exactly one span of the expected type when tracing is enabled (assert via `trace_manager.get_all_traces_dict()`)
- [x] 6.2 Test that two decorated turns sharing a `thread_id` (via `set_thread_id`/`thread_context`) both carry that `thread_id` and group into one thread; distinct thread_ids stay separate
- [x] 6.3 Test the disabled path: with tracing off, an `observe`-decorated function runs and returns its normal result with no span emitted and no exception, and every `record_*` / thread helper is a no-op
- [x] 6.4 Test `observe` raises `ValueError` on a span_type outside `SPAN_TYPES`
- [x] 6.5 Run `openspec validate tracing-foundation --strict` — passes
- [x] 6.6 **Done condition:** a decorated dummy function emits a span, and two traces sharing a `thread_id` group into one thread (or degrade to a no-op when tracing is disabled). **Test command:** `pytest backend/tracing`
