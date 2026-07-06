"""Agent reply contract.

The shape returned by the agent loop (P4) for one conversational turn, including
citations, the tools invoked, and per-message usage/cost accounting.
"""

from __future__ import annotations

from pydantic import BaseModel

from backend.contracts.retrieval import Citation


class ToolCallRecord(BaseModel):
    """One tool invocation made during a turn."""

    name: str  # "rag_search" | "cml_report" | "contract_note"
    input: dict
    ok: bool


class UsageCost(BaseModel):
    """Per-message token usage, INR cost, and latency."""

    input_tokens: int
    output_tokens: int
    cost_inr: float  # this message's cost in INR
    latency_ms: int


class AgentReply(BaseModel):
    """Final result of one agent turn."""

    content: str  # final assistant text
    citations: list[Citation] = []  # empty if no retrieval used
    tools_called: list[ToolCallRecord] = []
    usage: UsageCost
    awaiting_user: bool = False  # true when agent asked a clarifying question
    ticket_offered: bool = False  # true when caps hit and support ticket offered
