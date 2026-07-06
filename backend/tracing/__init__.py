"""backend.tracing — the thin, stable tracing interface for P1 (rag) and P4 (agent).

Wraps DeepEval / Confident AI so downstream code depends on ``backend.tracing``,
not on DeepEval's surface directly, and degrades to a safe no-op when tracing is
disabled or no Confident API key is present.

Public surface (frozen once merged):
    init_tracing, observe, set_thread_id, thread_context,
    record_retriever, record_tool, record_llm, record_agent, SPAN_TYPES

Importing this package performs no DeepEval import and no network calls; DeepEval
is imported lazily by ``init_tracing`` only when tracing is actually enabled.
"""

from __future__ import annotations

from backend.tracing.config import init_tracing
from backend.tracing.spans import (
    SPAN_TYPES,
    observe,
    record_agent,
    record_llm,
    record_retriever,
    record_tool,
)
from backend.tracing.thread import set_thread_id, thread_context

__all__ = [
    "init_tracing",
    "observe",
    "set_thread_id",
    "thread_context",
    "record_retriever",
    "record_tool",
    "record_llm",
    "record_agent",
    "SPAN_TYPES",
]
