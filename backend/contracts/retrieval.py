"""Retrieval and citation contracts.

Canonical shapes produced by the RAG retrieval layer (P1) and consumed by the
agent (P4), the API/SSE layer (P5), and evals (P6). Frozen once merged.
"""

from __future__ import annotations

from pydantic import BaseModel


class Citation(BaseModel):
    """Provenance for a retrieved chunk, enough to render a hoverable card.

    Fields map to columns on ``qa_chunks``; ``chunk_id`` equals ``qa_chunks.id``.
    """

    chunk_id: int
    topic: str | None = None
    section: str | None = None
    question: str | None = None
    answer_source: str | None = None
    source_row: int | None = None


class RetrievedChunk(BaseModel):
    """A single retrieval result with display text, fused score, and citation."""

    chunk_id: int
    chunk: str  # qa_chunks.chunk — concatenated text used for display
    question: str | None = None
    answer: str | None = None
    tat: str | None = None
    score: float  # fused RRF score
    citation: Citation
