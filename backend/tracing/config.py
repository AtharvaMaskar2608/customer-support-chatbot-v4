"""Tracing initialization and the single enablement gate.

This module owns the one place where DeepEval / Confident AI is configured from
``backend.config.settings``. Everything else in ``backend.tracing`` asks
:func:`tracing_enabled` before touching DeepEval, so the whole package collapses
to a transparent no-op when tracing is off or no Confident API key is present.

Ordering note for callers (P1 rag / P4 agent): call :func:`init_tracing` at
application startup *before* importing the modules that apply the
:func:`backend.tracing.observe` decorator. ``observe`` decides at decoration time
whether to wrap or pass through, so the enablement state must be settled first.
"""

from __future__ import annotations

# Module-level enablement gate. Flipped on only by a successful init_tracing()
# where the toggle is on and a Confident API key is present. Read exclusively
# through tracing_enabled().
_ENABLED = False


def init_tracing() -> None:
    """Configure DeepEval / Confident AI from ``backend.config.settings``.

    Idempotent and no-op safe: if ``TRACING_ENABLED`` is off or no
    ``CONFIDENT_API_KEY`` is present, it leaves tracing in a disabled state and
    returns without raising. Never raises on missing or malformed config — a
    misconfigured tracing layer must never take down the request path.
    """
    global _ENABLED

    try:
        from backend.config import settings

        enabled = bool(settings.tracing_enabled) and bool(settings.confident_api_key)

        if not enabled:
            _ENABLED = False
            return

        # Import DeepEval lazily so a disabled/absent-key deployment never pays
        # the import cost and importing backend.tracing stays network-free.
        from deepeval.tracing import trace_manager

        trace_manager.configure(
            tracing_enabled=True,
            confident_api_key=settings.confident_api_key,
            sampling_rate=1.0,
        )
        _ENABLED = True
    except Exception:
        # Any failure (missing dependency, unexpected DeepEval signature, bad
        # config) degrades to the safe no-op state rather than propagating.
        _ENABLED = False


def tracing_enabled() -> bool:
    """Return whether tracing is live.

    True only after :func:`init_tracing` configured DeepEval with a Confident API
    key and the toggle on. This is the single gate that drives every no-op branch
    in ``observe``, the ``record_*`` helpers, and the thread helpers.
    """
    return _ENABLED
