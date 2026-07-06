# data-contracts Specification

## Purpose
TBD - created by archiving change cho-33-foundations-and-contracts. Update Purpose after archive.
## Requirements
### Requirement: Retrieval and citation contracts

The system SHALL define canonical `RetrievedChunk` and `Citation` models that every retrieval consumer imports. `Citation` SHALL carry enough provenance (`chunk_id`, `topic`, `section`, `question`, `answer_source`, `source_row`) to render a hoverable citation card, and `RetrievedChunk` SHALL carry the display `chunk` text plus a fused `score`.

#### Scenario: Retrieval result carries citation provenance

- **WHEN** a retrieval produces a chunk from `qa_chunks`
- **THEN** it is representable as a `RetrievedChunk` whose `citation.chunk_id` equals the `qa_chunks.id` and whose citation fields are populated from that row

### Requirement: RAG tool I/O contract

The system SHALL define `RagToolInput` (`query`, `top_k` default 10) and `RagToolOutput` (`chunks: list[RetrievedChunk]`) as the tool-use contract for the RAG tool exposed to the agent.

#### Scenario: RAG tool schema is stable

- **WHEN** the agent invokes the RAG tool
- **THEN** the tool input validates against `RagToolInput` and the tool output validates against `RagToolOutput`

### Requirement: Report tool I/O contracts

The system SHALL define request models `CmlReportRequest` (`report_type`, `search_by`, `search_value`) and `ContractNoteRequest` (`mobile_no`, `contract_date` in `DD-MM-YYYY`), and a unified `ReportResult` (`ok`, `report_type`, `data`, `error`). FINX authentication headers SHALL NOT be part of the request body models.

#### Scenario: Report request maps to FINX JSON keys

- **WHEN** a `CmlReportRequest` is serialized for the FINX MIS API
- **THEN** its fields map to `reportType`, `searchBy`, and `searchValue`

### Requirement: Session context contract

The system SHALL define `SessionContext` (`client_code`, `session_token`) with both values trimmed of surrounding whitespace, where `session_token` is used as the FINX `Authorization` JWT for report calls.

#### Scenario: Session inputs are trimmed

- **WHEN** a `SessionContext` is constructed from user-entered client code and session token
- **THEN** leading and trailing whitespace is stripped from both values

### Requirement: Agent reply contract

The system SHALL define `AgentReply` capturing final `content`, `citations`, `tools_called`, `usage` (`UsageCost` with `input_tokens`, `output_tokens`, `cost_inr`, `latency_ms`), and the conversational flags `awaiting_user` and `ticket_offered`.

#### Scenario: Reply reports cost and latency

- **WHEN** the agent finishes a turn
- **THEN** the `AgentReply.usage` reports that turn's token counts, INR cost, and latency in milliseconds

### Requirement: SSE event envelope contract

The system SHALL define an `SseEvent` envelope with a named `event` (`status`, `token`, `citations`, `usage`, `done`, `error`) and a `data` payload, as the single streaming contract between backend and frontend.

#### Scenario: Streaming uses the shared envelope

- **WHEN** the backend streams an intermediate step or an output token
- **THEN** it emits an `SseEvent` whose `event` is one of the defined names with the corresponding `data` shape

