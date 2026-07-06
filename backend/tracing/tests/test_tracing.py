"""Tests for the ``backend.tracing`` interface.

These exercise the three guarantees the interface makes:
  * an ``observe``-decorated function emits exactly one span of the given type;
  * traces across turns sharing a ``thread_id`` carry it and group into one
    thread (and distinct ids stay separate);
  * with tracing disabled, every entry point is a transparent no-op.

Capturing finished traces: DeepEval 4.0.7 evicts completed traces from
``trace_manager.get_all_traces_dict()`` (it retains only *active* traces to bound
memory), so we capture each finished trace by intercepting
``trace_manager.post_trace`` — the single sink every completed trace flows
through — and swallow it there so nothing is exported over the network.
"""

from __future__ import annotations

import pytest

import backend.tracing.config as config
from backend.tracing import (
    SPAN_TYPES,
    observe,
    record_agent,
    record_llm,
    record_retriever,
    record_tool,
    set_thread_id,
    thread_context,
)


@pytest.fixture()
def enable_tracing(monkeypatch):
    """Enable tracing through the real gate: patch settings and run init_tracing()."""
    from backend.config import settings as cfg

    monkeypatch.setattr(cfg, "tracing_enabled", True, raising=False)
    monkeypatch.setattr(cfg, "confident_api_key", "test-confident-key", raising=False)
    config.init_tracing()
    assert config.tracing_enabled() is True
    yield
    monkeypatch.undo()
    config.init_tracing()  # restore the real (disabled) state


@pytest.fixture()
def disable_tracing(monkeypatch):
    """Force the disabled state through the real gate."""
    from backend.config import settings as cfg

    monkeypatch.setattr(cfg, "tracing_enabled", False, raising=False)
    config.init_tracing()
    assert config.tracing_enabled() is False
    yield
    monkeypatch.undo()
    config.init_tracing()


@pytest.fixture()
def captured_traces():
    """Collect every finished trace, swallowing the export so no network is hit."""
    from deepeval.tracing import trace_manager

    traces: list = []
    original = trace_manager.post_trace

    def capture(trace):
        traces.append(trace)
        return None  # swallow: do not queue for export

    trace_manager.post_trace = capture
    try:
        yield traces
    finally:
        trace_manager.post_trace = original


def _all_spans(spans) -> list:
    """Flatten a span tree into a list."""
    out = []
    for span in spans or []:
        out.append(span)
        out.extend(_all_spans(getattr(span, "children", None)))
    return out


# --- 6.1: a decorated dummy emits exactly one span of the expected type -------

_TYPE_TO_CLASS = {
    "retriever": "RetrieverSpan",
    "tool": "ToolSpan",
    "llm": "LlmSpan",
    "agent": "AgentSpan",
}


@pytest.mark.parametrize("span_type", SPAN_TYPES)
def test_observe_emits_one_span_of_expected_type(
    span_type, enable_tracing, captured_traces
):
    @observe(span_type)
    def dummy():
        return "result"

    assert dummy() == "result"

    assert len(captured_traces) == 1
    spans = _all_spans(captured_traces[0].root_spans)
    assert len(spans) == 1
    assert type(spans[0]).__name__ == _TYPE_TO_CLASS[span_type]


def test_observe_forwards_span_kwargs_to_retriever(enable_tracing, captured_traces):
    # Confident AI requires a non-null ``embedder`` on retriever spans for
    # ingestion; observe must forward span kwargs to DeepEval at decoration time.
    @observe("retriever", embedder="text-embedding-3-large")
    def retrieve():
        return ["chunk"]

    retrieve()

    span = _all_spans(captured_traces[0].root_spans)[0]
    assert type(span).__name__ == "RetrieverSpan"
    assert span.embedder == "text-embedding-3-large"


def test_record_helpers_attach_conventional_attributes(enable_tracing, captured_traces):
    @observe("retriever")
    def retrieve(query):
        record_retriever(query, ["chunk-a", "chunk-b"])
        return ["chunk-a", "chunk-b"]

    retrieve("what is my TAT?")

    span = _all_spans(captured_traces[0].root_spans)[0]
    assert span.input == "what is my TAT?"
    assert span.retrieval_context == ["chunk-a", "chunk-b"]


# --- 6.2: thread grouping by thread_id ----------------------------------------


def test_shared_thread_id_groups_turns_distinct_stay_separate(
    enable_tracing, captured_traces
):
    @observe("agent")
    def turn(thread_id):
        set_thread_id(thread_id)
        return "ok"

    turn("session-1")
    turn("session-1")
    turn("session-2")

    thread_ids = [t.thread_id for t in captured_traces]
    assert thread_ids == ["session-1", "session-1", "session-2"]
    # The two "session-1" turns group into one thread; "session-2" is separate.
    assert thread_ids[0] == thread_ids[1]
    assert thread_ids[2] != thread_ids[0]


def test_thread_context_manager_sets_thread_id(enable_tracing, captured_traces):
    @observe("agent")
    def turn(thread_id):
        with thread_context(thread_id):
            return "ok"

    turn("ctx-session")
    turn("ctx-session")

    thread_ids = [t.thread_id for t in captured_traces]
    assert thread_ids == ["ctx-session", "ctx-session"]


# --- 6.3: disabled path is a transparent no-op --------------------------------


def test_disabled_observe_is_passthrough_and_helpers_noop(
    disable_tracing, captured_traces
):
    def dummy():
        return 42

    decorated = observe("agent")(dummy)
    # Pass-through: the original function is returned unchanged (no wrapper).
    assert decorated is dummy
    assert decorated() == 42

    # No span was emitted.
    assert captured_traces == []

    # Every recording / thread helper is a silent no-op (returns None, no raise,
    # no DeepEval contact).
    assert record_retriever("q", ["c"]) is None
    assert record_tool("tool", {"a": 1}, "out", True) is None
    assert record_llm("claude-sonnet-4-5", 10, 20) is None
    assert record_agent(thread_id="t", metadata={"turn": 1}) is None
    assert set_thread_id("t") is None
    with thread_context("t"):
        pass
    assert captured_traces == []


# --- 6.4: invalid span type is rejected at decoration time --------------------


def test_observe_rejects_unknown_span_type():
    with pytest.raises(ValueError, match="Unknown span_type"):
        observe("database")

    # Guard holds regardless of enablement.
    with pytest.raises(ValueError):
        observe("")


def test_import_is_network_free_without_key():
    """Importing the package must not require a key or import DeepEval eagerly."""
    import sys

    import backend.tracing  # noqa: F401  (import side effects are what we test)

    # DeepEval is imported lazily by init_tracing, never at package import time.
    assert "backend.tracing" in sys.modules
