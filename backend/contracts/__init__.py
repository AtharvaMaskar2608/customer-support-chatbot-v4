"""Canonical shared data contracts (Pydantic v2).

The single source of truth for every shape crossing module boundaries. All
downstream changes import from here; these signatures are frozen once merged.
"""

from backend.contracts.agent import AgentReply, ToolCallRecord, UsageCost
from backend.contracts.rag_tool import RagToolInput, RagToolOutput
from backend.contracts.reports import (
    CmlReportRequest,
    ContractNoteRequest,
    ReportResult,
)
from backend.contracts.retrieval import Citation, RetrievedChunk
from backend.contracts.session import SessionContext
from backend.contracts.sse import SseEvent, SseEventName

__all__ = [
    # retrieval
    "Citation",
    "RetrievedChunk",
    # rag tool
    "RagToolInput",
    "RagToolOutput",
    # reports
    "CmlReportRequest",
    "ContractNoteRequest",
    "ReportResult",
    # session
    "SessionContext",
    # agent
    "ToolCallRecord",
    "UsageCost",
    "AgentReply",
    # sse
    "SseEvent",
    "SseEventName",
]
