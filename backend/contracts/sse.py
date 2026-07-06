"""SSE event envelope contract.

The single streaming contract between the backend (P5) and the frontend (P8).
Every server-sent event is an :class:`SseEvent` with a named ``event`` and a
``data`` payload. The ``data`` shape per event name:

    status:    {"message": str}
    token:     {"text": str}
    citations: {"items": [Citation, ...]}
    usage:     {UsageCost fields..., "cumulative_cost_inr": float}
    done:      {}
    error:     {"message": str}
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

SseEventName = Literal["status", "token", "citations", "usage", "done", "error"]


class SseEvent(BaseModel):
    """A single server-sent event envelope."""

    event: SseEventName
    data: dict = {}
