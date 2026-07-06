"""Contract validation tests.

Each model validates a representative payload and rejects malformed input,
covering the two behaviours downstream changes rely on: session whitespace
trimming and FINX report key aliasing.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.contracts import (
    AgentReply,
    Citation,
    CmlReportRequest,
    ContractNoteRequest,
    RagToolInput,
    RagToolOutput,
    ReportResult,
    RetrievedChunk,
    SessionContext,
    SseEvent,
    ToolCallRecord,
    UsageCost,
)


# --- retrieval ---------------------------------------------------------------


def test_citation_and_retrieved_chunk_validate():
    citation = Citation(
        chunk_id=42,
        topic="KYC",
        section="Account opening",
        question="How do I open an account?",
        answer_source="kb",
        source_row=7,
    )
    chunk = RetrievedChunk(
        chunk_id=42,
        chunk="You can open an account online...",
        question="How do I open an account?",
        answer="Follow these steps...",
        tat="1 day",
        score=0.87,
        citation=citation,
    )
    assert chunk.citation.chunk_id == chunk.chunk_id == 42


def test_retrieved_chunk_requires_score():
    with pytest.raises(ValidationError):
        RetrievedChunk(chunk_id=1, chunk="x", citation=Citation(chunk_id=1))


# --- rag tool ----------------------------------------------------------------


def test_rag_tool_io():
    inp = RagToolInput(query="reset password")
    assert inp.top_k == 10
    out = RagToolOutput(
        chunks=[
            RetrievedChunk(chunk_id=1, chunk="c", score=0.5, citation=Citation(chunk_id=1))
        ]
    )
    assert len(out.chunks) == 1


def test_rag_tool_input_rejects_bad_top_k():
    with pytest.raises(ValidationError):
        RagToolInput(query="x", top_k=0)


# --- reports (FINX key aliasing) ---------------------------------------------


def test_cml_request_aliases_to_finx_keys():
    req = CmlReportRequest(search_value="X130627")
    body = req.model_dump(by_alias=True)
    assert body == {
        "reportType": "cml",
        "searchBy": "client-id",
        "searchValue": "X130627",
    }


def test_cml_request_accepts_finx_keys_on_input():
    req = CmlReportRequest.model_validate(
        {"reportType": "cml", "searchBy": "client-id", "searchValue": "X1"}
    )
    assert req.search_value == "X1"


def test_contract_note_aliases_to_finx_keys():
    req = ContractNoteRequest(mobile_no="9920885615", contract_date="01-07-2024")
    body = req.model_dump(by_alias=True)
    assert body == {"mobileNo": "9920885615", "contractDate": "01-07-2024"}


def test_contract_note_requires_fields():
    with pytest.raises(ValidationError):
        ContractNoteRequest(mobile_no="9920885615")


def test_report_result():
    ok = ReportResult(ok=True, report_type="cml", data={"foo": "bar"})
    assert ok.error is None
    err = ReportResult(ok=False, report_type="contract-note", error="timeout")
    assert err.data is None


# --- session (whitespace trimming) -------------------------------------------


def test_session_trims_whitespace():
    ctx = SessionContext(client_code="  X130627  ", session_token="\t jwt-token \n")
    assert ctx.client_code == "X130627"
    assert ctx.session_token == "jwt-token"


def test_session_requires_both_fields():
    with pytest.raises(ValidationError):
        SessionContext(client_code="X1")


# --- agent -------------------------------------------------------------------


def test_agent_reply_validates():
    reply = AgentReply(
        content="Here is the answer.",
        citations=[Citation(chunk_id=1)],
        tools_called=[ToolCallRecord(name="rag_search", input={"query": "x"}, ok=True)],
        usage=UsageCost(input_tokens=100, output_tokens=50, cost_inr=0.42, latency_ms=1200),
    )
    assert reply.awaiting_user is False
    assert reply.ticket_offered is False
    assert reply.usage.cost_inr == 0.42


def test_agent_reply_defaults_empty_collections():
    reply = AgentReply(
        content="hi",
        usage=UsageCost(input_tokens=1, output_tokens=1, cost_inr=0.0, latency_ms=1),
    )
    assert reply.citations == []
    assert reply.tools_called == []


def test_usage_cost_rejects_non_numeric():
    with pytest.raises(ValidationError):
        UsageCost(input_tokens="lots", output_tokens=1, cost_inr=0.0, latency_ms=1)


# --- sse ---------------------------------------------------------------------


@pytest.mark.parametrize("name", ["status", "token", "citations", "usage", "done", "error"])
def test_sse_event_accepts_defined_names(name):
    evt = SseEvent(event=name, data={"message": "ok"})
    assert evt.event == name


def test_sse_event_rejects_unknown_name():
    with pytest.raises(ValidationError):
        SseEvent(event="heartbeat", data={})
