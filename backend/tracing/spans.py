"""The typed span decorator and per-span-type recording helpers.

``observe`` is the one decorator P1 (rag) and P4 (agent) apply to their
functions; the ``record_*`` helpers attach the conventional attributes to the
active span or trace so callers never import DeepEval directly. Every entry point
degrades to a transparent no-op when tracing is disabled.
"""

from __future__ import annotations

from typing import Any, Callable

from backend.tracing.config import tracing_enabled

# The fixed span taxonomy, matching DeepEval's typed spans. Typed spans unlock
# component-level metrics (P6/P7) and specialized rendering in Confident AI.
# ``agent`` is the root span for a conversational turn.
SPAN_TYPES = ("retriever", "tool", "llm", "agent")


def observe(
    span_type: str, name: str | None = None, **span_kwargs: Any
) -> Callable[[Callable], Callable]:
    """Decorator wrapping ``deepeval.tracing.observe(type=span_type, name=name)``.

    ``span_type`` is restricted to :data:`SPAN_TYPES`; an unknown type raises
    ``ValueError`` at decoration time. When tracing is disabled the wrapped
    function is returned unchanged (pass-through), so decorated code runs
    identically with or without tracing.

    ``span_kwargs`` are forwarded verbatim to DeepEval's ``@observe`` so callers
    can set span-type-specific attributes that DeepEval fixes at decoration time
    — notably ``embedder`` on a ``retriever`` span, which Confident AI requires
    as a non-null string for trace ingestion.
    """
    if span_type not in SPAN_TYPES:
        raise ValueError(
            f"Unknown span_type {span_type!r}; allowed span types are {SPAN_TYPES}"
        )

    def decorator(func: Callable) -> Callable:
        if not tracing_enabled():
            return func

        from deepeval.tracing import observe as _deepeval_observe

        kwargs = dict(span_kwargs)
        if name is not None:
            kwargs["name"] = name
        return _deepeval_observe(type=span_type, **kwargs)(func)

    return decorator


def record_retriever(
    query: str, chunks: list, *, metadata: dict | None = None
) -> None:
    """On the active ``retriever`` span: record ``input=query`` and attach the
    retrieved chunks as ``retrieval_context``. No-op when tracing is disabled."""
    if not tracing_enabled():
        return

    from deepeval.tracing import update_current_span

    update_current_span(
        input=query,
        retrieval_context=list(chunks),
        metadata=metadata,
    )


def record_tool(name: str, input: dict, output: Any, ok: bool) -> None:
    """On the active ``tool`` span: record the tool name, input, output, and an
    ``ok`` flag (name/ok carried in metadata). No-op when tracing is disabled."""
    if not tracing_enabled():
        return

    from deepeval.tracing import update_current_span

    update_current_span(
        input=input,
        output=output,
        name=name,
        metadata={"tool": name, "ok": ok},
    )


def record_llm(model: str, input_tokens: int, output_tokens: int) -> None:
    """On the active ``llm`` span: record the model name and token counts. Covers
    the manual/unpatched path (auto-patched clients capture tokens themselves).
    No-op when tracing is disabled."""
    if not tracing_enabled():
        return

    from deepeval.tracing import update_current_span

    update_current_span(
        metadata={
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        },
    )


def record_agent(
    *, thread_id: str | None = None, metadata: dict | None = None
) -> None:
    """On the agent root span/trace: record ``thread_id`` and per-turn metadata
    (turn number, tags) via ``update_current_trace``. No-op when disabled."""
    if not tracing_enabled():
        return

    from deepeval.tracing import update_current_trace

    kwargs: dict[str, Any] = {}
    if thread_id is not None:
        kwargs["thread_id"] = thread_id
    if metadata is not None:
        kwargs["metadata"] = metadata
    if kwargs:
        update_current_trace(**kwargs)
