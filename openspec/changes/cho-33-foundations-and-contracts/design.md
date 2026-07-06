## Context

Eight downstream changes (P1 rag-hybrid-retrieval, P2 finx-report-tools, P3 tracing-foundation, P4 agentic-loop, P5 api-sse-session, P6 rag-evals, P7 chatbot-multiturn-evals, P8 frontend-poc) are built in parallel by different agents. Per the repo's parallel-workflow rules, shared types/interfaces/API schemas must be committed to `main` before fan-out, and one change must solely own lockfiles/migrations/root config. This change is that foundation.

Grounding facts (confirmed):
- DB: Postgres `localhost:5433`, db `customer_support_chatbot`, user `atharva`, table `qa_chunks`. Columns: `id bigint`, `topic`, `section`, `question`, `answer`, `answer_source`, `tat`, `source_sheet`, `source_row int`, `chunk text`, `embedding vector(3072)`, `fts tsvector` (generated from `chunk`, GIN index `qa_chunks_fts_gin`). Embeddings + FTS already populated — **no migration and no ingestion**.
- Embeddings: OpenAI `text-embedding-3-large`, full 3072 dims.
- Agent model: `claude-sonnet-4-5`, thinking disabled.

## Goals / Non-Goals

**Goals:**
- Freeze the contract surface so P1–P8 compile against stable imports.
- One dependency manifest, one config loader, one DB helper — all owned here.
- Fail-fast config validation so misconfiguration surfaces at startup, not mid-conversation.

**Non-Goals:**
- No business logic (retrieval, agent, HTTP clients, endpoints, evals, tracing spans, UI). Contracts define shapes only; behavior lives in P1–P8.
- No DB schema changes.

## Decisions

**Pydantic v2 models as the contract layer** (over dataclasses/TypedDict): validation, JSON schema, and FastAPI-native. All models live in `backend/contracts/` and are the ONLY place these shapes are defined.

**Canonical contracts** (module → key models). These signatures are frozen once merged:

`backend/contracts/retrieval.py`
```python
class Citation(BaseModel):
    chunk_id: int            # qa_chunks.id
    topic: str | None
    section: str | None
    question: str | None
    answer_source: str | None
    source_row: int | None

class RetrievedChunk(BaseModel):
    chunk_id: int
    chunk: str               # qa_chunks.chunk (concatenated text used for display)
    question: str | None
    answer: str | None
    tat: str | None
    score: float             # fused RRF score
    citation: Citation
```

`backend/contracts/rag_tool.py` (the RAG tool's tool-use contract)
```python
class RagToolInput(BaseModel):
    query: str
    top_k: int = 10

class RagToolOutput(BaseModel):
    chunks: list[RetrievedChunk]
```

`backend/contracts/reports.py` (P2 report tools; base URL from config)
```python
class CmlReportRequest(BaseModel):
    report_type: str = "cml"     # -> JSON key "reportType"
    search_by: str = "client-id" # -> "searchBy"
    search_value: str            # -> "searchValue" (client code, e.g. "X130627")

class ContractNoteRequest(BaseModel):
    mobile_no: str               # -> "mobileNo"
    contract_date: str           # -> "contractDate", format DD-MM-YYYY

class ReportResult(BaseModel):
    ok: bool
    report_type: str             # "cml" | "contract-note"
    data: dict | None            # raw JSON body from FINX MIS on success
    error: str | None
```
(FINX headers — `Authorization: <session JWT>`, `authType: jwt`, `source: FINX_WEB` — are added by the P2 client from `SessionContext`, not part of the request body models.)

`backend/contracts/session.py`
```python
class SessionContext(BaseModel):
    client_code: str             # trimmed
    session_token: str           # trimmed; used as FINX Authorization JWT
```

`backend/contracts/agent.py`
```python
class ToolCallRecord(BaseModel):
    name: str                    # "rag_search" | "cml_report" | "contract_note"
    input: dict
    ok: bool

class UsageCost(BaseModel):
    input_tokens: int
    output_tokens: int
    cost_inr: float              # this message's cost in INR
    latency_ms: int

class AgentReply(BaseModel):
    content: str                 # final assistant text
    citations: list[Citation]    # empty if no retrieval used
    tools_called: list[ToolCallRecord]
    usage: UsageCost
    awaiting_user: bool = False  # true when agent asked a clarifying question
    ticket_offered: bool = False # true when caps hit and support-ticket offered
```

`backend/contracts/sse.py` (SSE envelope for P5 frontend/streaming)
```python
# event names: "status" | "token" | "citations" | "usage" | "done" | "error"
class SseEvent(BaseModel):
    event: str
    data: dict                   # status:{message}; token:{text}; citations:{items:[Citation]};
                                 # usage:{UsageCost + cumulative_cost_inr}; done:{}; error:{message}
```

**Config loader** (`backend/config/settings.py`) via `pydantic-settings.BaseSettings` reading `.env`. Keys: `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` (default `claude-sonnet-4-5`), `EMBEDDING_MODEL` (default `text-embedding-3-large`), `EMBEDDING_API_KEY`/`OPENAI_API_KEY`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `FINX_REPORTS_BASE_URL` (e.g. `https://finxomne.choiceindia.com`), `FINX_CONTRACT_NOTE_BASE_URL` (defaults to reports base; separate key because CML moved host), `CONFIDENT_API_KEY`/tracing toggles, `USD_TO_INR` (for cost card), `FRONTEND_ORIGIN` (CORS allow-origin for the P5 API, default `http://localhost:5173`). Missing required keys raise at import/startup.

**DB helper** (`backend/db/pool.py`): a `psycopg` connection/pool factory built from config, read-only usage. Registers pgvector type adapter so `embedding` round-trips. Exposes `get_connection()`; no ORM.

**Cost accounting convention**: `UsageCost.cost_inr` computed from Anthropic token usage × per-token USD price × `USD_TO_INR`. Price table location and exact math are defined by P4 (agent) / P5 (SSE); this change only fixes the `UsageCost` shape and the INR unit.

## Risks / Trade-offs

- [Contract change after fan-out breaks parallel work] → Freeze `backend/contracts` once merged; any change requires a new proposal and re-sync, surfaced in the merge-conflict pass.
- [Over-specifying shapes downstream needs to extend] → Models allow additive fields; downstream adds fields via follow-up only if non-breaking, otherwise coordinates here.
- [Contract Note host/path not re-confirmed] → `FINX_CONTRACT_NOTE_BASE_URL` is a separate config key so P2 can point it correctly without a code change; flagged as open question.

## Open Questions

- Exact Contract Note endpoint host/path (CML confirmed on `finxomne.choiceindia.com/mis/reports/generate`; contract note assumed `/mis/v2/contract-note/generate`). Resolved via config, confirmed before P2 wiring.
- Per-token INR price source for the cost card (static table vs config) — finalized in P4/P5.
