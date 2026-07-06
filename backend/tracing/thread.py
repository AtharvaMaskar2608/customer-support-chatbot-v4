"""Multi-turn thread grouping.

Turns of one conversation are stitched into a single thread/session by attaching
the same ``thread_id`` to each turn's trace. Both helpers degrade to a
transparent no-op when tracing is disabled.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from backend.tracing.config import tracing_enabled


def set_thread_id(thread_id: str) -> None:
    """Attach ``thread_id`` to the current trace via ``update_current_trace`` so
    traces across turns sharing the id group into one thread. No-op when disabled.
    """
    if not tracing_enabled():
        return

    from deepeval.tracing import update_current_trace

    update_current_trace(thread_id=thread_id)


@contextmanager
def thread_context(thread_id: str) -> Iterator[None]:
    """Context-manager form: set ``thread_id`` on the current trace on enter, then
    yield. Sugar so a turn can be wrapped without a try/finally. No-op when
    tracing is disabled (still yields)."""
    set_thread_id(thread_id)
    yield
