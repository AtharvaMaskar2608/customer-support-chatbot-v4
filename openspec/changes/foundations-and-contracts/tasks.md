## 1. Project skeleton & dependencies

- [ ] 1.1 Create `backend/` package with subpackages `config/`, `contracts/`, `db/`, `agent/`, `rag/`, `tools/`, `tracing/`, `api/`, `evals/`, `evals/rag/`, `evals/chatbot/`, each with `__init__.py` (empty placeholders so P1–P8 only add files inside their owned dir)
- [ ] 1.2 Create `frontend/` directory placeholder
- [ ] 1.3 Add `pyproject.toml` with runtime deps (fastapi, uvicorn, pydantic>=2, pydantic-settings, psycopg[binary], pgvector, anthropic, openai, httpx, python-dotenv, deepeval) and dev deps (pytest, ruff) — this change is the SOLE owner of this file

## 2. Configuration

- [ ] 2.1 Add `.env.example` documenting every key (Anthropic, embeddings, Postgres, FINX report base URLs, tracing, USD_TO_INR, FRONTEND_ORIGIN)
- [ ] 2.2 Implement `backend/config/settings.py` with `pydantic-settings` loading `.env`, defaults `ANTHROPIC_MODEL=claude-sonnet-4-5` and `EMBEDDING_MODEL=text-embedding-3-large`, and fail-fast validation for required keys
- [ ] 2.3 Assert no hardcoded connection details/keys/model strings exist outside config

## 3. Database access

- [ ] 3.1 Implement `backend/db/pool.py` connection helper from config with pgvector type registration, read-only usage
- [ ] 3.2 Add a smoke check that `SELECT count(*) FROM qa_chunks` returns > 0 and `embedding` deserializes

## 4. Shared data contracts

- [ ] 4.1 Implement `backend/contracts/retrieval.py` (`Citation`, `RetrievedChunk`)
- [ ] 4.2 Implement `backend/contracts/rag_tool.py` (`RagToolInput`, `RagToolOutput`)
- [ ] 4.3 Implement `backend/contracts/reports.py` (`CmlReportRequest`, `ContractNoteRequest`, `ReportResult`) with FINX JSON-key aliases
- [ ] 4.4 Implement `backend/contracts/session.py` (`SessionContext` with whitespace-trimming validators)
- [ ] 4.5 Implement `backend/contracts/agent.py` (`ToolCallRecord`, `UsageCost`, `AgentReply`)
- [ ] 4.6 Implement `backend/contracts/sse.py` (`SseEvent` envelope with defined event names)
- [ ] 4.7 Export all models from `backend/contracts/__init__.py`

## 5. Verification

- [ ] 5.1 Add `tests/test_contracts.py` asserting each model validates a representative payload and rejects malformed input (incl. session trimming, report key aliasing)
- [ ] 5.2 Run `openspec validate foundations-and-contracts --strict` — passes
- [ ] 5.3 **Done condition:** `pytest tests/test_contracts.py` green, config loads with a filled `.env`, and `python -c "from backend.db.pool import get_connection"` imports cleanly. **Test command:** `pytest tests/test_contracts.py -q`
