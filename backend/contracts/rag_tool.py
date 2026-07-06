"""RAG tool I/O contract.

The tool-use schema for the RAG tool exposed to the agent (P4). The agent sends
``RagToolInput``; the retrieval layer (P1) returns ``RagToolOutput``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from backend.contracts.retrieval import RetrievedChunk


class RagToolInput(BaseModel):
    """Arguments the agent passes when invoking the RAG tool."""

    query: str
    top_k: int = Field(default=10, ge=1)


class RagToolOutput(BaseModel):
    """Result returned to the agent from the RAG tool."""

    chunks: list[RetrievedChunk]
