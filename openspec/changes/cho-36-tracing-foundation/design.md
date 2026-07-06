## Context

Phase 1 of the Choice FinX support chatbot is decomposed into eight parallel changes. Two of them need tracing: P1 `rag-hybrid-retrieval` (retriever + llm spans on the RAG path) and P4 `agentic-loop` (an agent root span, tool spans, llm spans, and multi-turn thread grouping). Both are built in parallel by different agents. Per the repo's parallel-workflow rules, the shared interface they both import must land in `main` first and be owned by exactly one change. This change (P3 `tracing-foundation`) owns `backend/tracing/` and provides that interface.

Grounding facts (confirmed):
- Tracing stack: DeepEval `@observe` + Confident AI, per `docs/tracing/1_rag_tracing.md` and `docs/tracing/2_multi_turn_chat_tracing.md`. `deepeval` is already a declared P0 dependency.
- DeepEval model: a **trace** is one request; a **span** is one function call (`retriever` | `tool` | `llm` | `agent`); a **thread** is traces grouped by a shared `thread_id`.
- DeepEval surface used: `deepeval.tracing.observe`, `update_current_span`, `update_current_trace`, `trace_manager.configure`.
- Config surface (frozen P0 contract, import only): `backend.config.settings.Settings` exposes `CONFIDENT_API_KEY` and the tracing toggle keys.
- Agent model `claude-sonnet-4-5`; Anthropic clients are auto-patchable by DeepEval for token capture, but auto-patch wiring belongs to whichever change constructs the client (P4), not here.

## Goals / Non-Goals

**Goals:**
- Provide one stable tracing interface (`init_tracing`, `observe`, `set_thread_id`/`thread_context`, `record_*`) so P1 and P4 compile against stable imports and stay parallelizable.
- Wrap DeepEval so downstream code imports `backend.tracing`, not DeepEval directly — one place to change if the tracing vendor changes.
- Fix the span-type taxonomy and the per-span recording conventions once, here.
- Degrade to a safe no-op when tracing is disabled or no key is present, so rag/agent code runs identically in tests and offline.

**Non-Goals:**
- No decorators applied inside `backend/rag/` or `backend/agent/` — P1/P4 do that by importing this module.
- No evaluation metrics or metric collections — those are P6 `rag-evals` / P7 `chatbot-multiturn-evals`.
- No Anthropic/OpenAI client auto-patch wiring (belongs to the change that owns the client) and no DB or config changes.

## Decisions

**Wrap DeepEval, do not re-export it.** Downstream depends only on `backend.tracing`. This isolates the DeepEval API surface behind a thin adapter, so a vendor change or a disabled-tracing fallback is a one-file edit here rather than edits scattered across rag/agent.

**Public interface (frozen once merged):**

`backend/tracing/config.py`
```python
def init_tracing() -> None:
    """Configure DeepEval / Confident AI from backend.config.settings.
    Idempotent. No-op safe: if CONFIDENT_API_KEY is absent or the tracing
    toggle is off, sets a disabled state and returns without raising."""

def tracing_enabled() -> bool:
    """Internal: True only after init_tracing() configured a live key with
    the toggle on. Drives the no-op branches of observe / record_* / thread."""
```

`backend/tracing/spans.py`
```python
SPAN_TYPES = ("retriever", "tool", "llm", "agent")

def observe(span_type: str, name: str | None = None):
    """Decorator wrapping deepeval.tracing.observe(type=span_type, name=name).
    Raises ValueError at decoration time if span_type not in SPAN_TYPES.
    When tracing is disabled, returns the wrapped function unchanged."""

def record_retriever(query: str, chunks: list, *, metadata: dict | None = None) -> None:
    """On the active retriever span: input=query, retrieval_context=chunks."""

def record_tool(name: str, input: dict, output, ok: bool) -> None:
    """On the active tool span: tool name, input, output, ok flag."""

def record_llm(model: str, input_tokens: int, output_tokens: int) -> None:
    """On the active llm span: model name and token counts."""

def record_agent(*, thread_id: str | None = None, metadata: dict | None = None) -> None:
    """On the agent root span/trace: thread_id and per-turn metadata."""
```

`backend/tracing/thread.py`
```python
def set_thread_id(thread_id: str) -> None:
    """Attach thread_id to the current trace via update_current_trace.
    No-op when tracing disabled."""

@contextmanager
def thread_context(thread_id: str):
    """Context manager form: set_thread_id on enter; yields. No-op when disabled."""
```

`backend/tracing/__init__.py` re-exports: `init_tracing`, `observe`, `set_thread_id`, `thread_context`, `record_retriever`, `record_tool`, `record_llm`, `record_agent`, `SPAN_TYPES`.

**Span-type taxonomy** = exactly `{"retriever", "tool", "llm", "agent"}`, matching DeepEval's typed spans (typed spans unlock component metrics in P6/P7 and specialized rendering in Confident AI). `agent` is the root span for a turn.

**Recording conventions** (what each span type records):
- `retriever`: `input` = query; `retrieval_context` = retrieved chunks; latency captured automatically by `@observe`. (via `update_current_span`.)
- `tool`: tool `name`, `input`, `output`, `ok` boolean. (via `update_current_span`, with `metadata`.)
- `llm`: `model` name, `input_tokens`, `output_tokens`. (Token counts may also be auto-captured when the LLM client is auto-patched by whoever owns the client; `record_llm` covers the manual/unpatched path.)
- `agent` (root): `thread_id` and per-turn `metadata` (turn number, tags) via `update_current_trace`.

**Thread grouping** uses DeepEval's `update_current_trace(thread_id=...)`. Callers set the same `thread_id` on every turn of a conversation; Confident AI reconstructs the thread. `thread_context` is sugar so P4 can wrap a turn without a try/finally.

**No-op strategy.** `tracing_enabled()` is the single gate. When false: `observe` returns the original function (no wrapper), `set_thread_id`/`thread_context`/`record_*` return immediately. This guarantees rag/agent behavior is identical with tracing on or off and keeps DeepEval off the hot path in unit tests.

## Risks / Trade-offs

- [Interface change after fan-out breaks P1/P4] → Freeze the `backend/tracing` public interface once merged; any change requires a new proposal and re-sync, surfaced in the merge-conflict pass. Signatures above are the frozen surface.
- [DeepEval's actual configure/observe signature differs from the docs] → All DeepEval calls are isolated to `config.py`/`spans.py`/`thread.py`; adapting to the real API is a localized edit and cannot leak into rag/agent code.
- [Auto-patch ownership ambiguity for llm token capture] → This change provides only `record_llm` for the manual path; client auto-patching stays with the change that constructs the Anthropic/OpenAI client (P4). Flagged as a coordination point, not a code dependency.
- [Over-abstracting DeepEval] → Interface is deliberately thin (one decorator + a handful of helpers); downstream can still call DeepEval directly if a rare need arises, but the conventions live here.

## Implementation Notes (verified against a live Confident AI export)

Confirmed end-to-end on DeepEval 4.0.7 by exporting a two-turn `agent → retriever + llm` trace (shared `thread_id`) to Confident AI. Two findings that downstream changes (esp. P1 rag) must not rediscover the hard way:

- **Retriever spans require a non-null `embedder` for ingestion.** Confident AI's trace API rejects a `retriever` span with `retrieverSpans[0].embedder Required` (HTTP 400) when `embedder` is unset. `embedder` is fixed at *decoration time* — DeepEval accepts it as an `@observe(type="retriever", embedder=...)` kwarg, and it is **not** settable via `update_current_span`. To support this, `observe(span_type, name=None, **span_kwargs)` forwards extra kwargs to DeepEval's `@observe` (additive, backward-compatible with the frozen positional signature). **P1 must decorate its retriever with `observe("retriever", embedder=settings.embedding_model)`** or its retriever traces will fail to export. (`top_k` / `chunk_size` are *not* `@observe` kwargs in 4.0.7 — only `embedder` is forwarded onto the span.)
- **Use a Confident AI *project* API key, not an *org* key.** An org-scoped key (`confident_us_proj_…` vs `confident_us_org_…`) returns `401 Invalid API key` on trace ingestion. The project API key is the one from Project → Settings (or via `deepeval login`).
- **Verification mechanism for tests.** DeepEval 4.0.7 evicts completed traces from `trace_manager.get_all_traces_dict()` (it retains only *active* traces), so the unit tests capture finished traces by intercepting `trace_manager.post_trace` and swallowing the export — keeping tests fully offline.

## Open Questions

- Exact keyword name of the tracing toggle in `Settings` (e.g. `TRACING_ENABLED` vs deriving enablement from `CONFIDENT_API_KEY` presence) — resolved against the frozen P0 `Settings` at implementation time; the no-op contract holds either way.
- Whether P4's Anthropic client is passed to `trace_manager.configure(...)` for auto-patch here or in P4 — defaulting to P4 (client owner); revisit if P4 prefers this change to own the patch call.
