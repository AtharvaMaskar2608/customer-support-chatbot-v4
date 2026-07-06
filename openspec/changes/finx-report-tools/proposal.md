## Why

The support chatbot must answer account-specific questions that the RAG knowledge base cannot (a client's holdings, a day's contract note). FINX exposes two read-only MIS report endpoints for this: the CML report and the contract note. The agent (P4) needs callable tools that hit these endpoints with the tester's session JWT, tolerate network/HTTP failure without crashing the turn, and return the raw report JSON in the frozen `ReportResult` shape. This change owns those two tool clients and their Anthropic tool-use schemas — nothing else.

## What Changes

- Add `backend/tools/finx_client.py`: two async httpx-backed functions, `cml_report(session, search_value)` and `contract_note(session, mobile_no, contract_date)`, that POST to the FINX MIS endpoints using base URLs from `Settings` and headers assembled from `SessionContext`.
- Assemble the three FINX headers on every call — `Authorization: <session_token>`, `authType: jwt`, `source: FINX_WEB` — from the session, not from the request body.
- Serialize request bodies from the frozen `CmlReportRequest` / `ContractNoteRequest` models (FINX JSON-key aliases: `reportType`, `searchBy`, `searchValue`, `mobileNo`, `contractDate`).
- Never raise on HTTP status or network/timeout error: map every failure to `ReportResult(ok=False, ...)` with a structured `error` string; map a 2xx to `ReportResult(ok=True, data=<raw JSON>)`.
- Add `backend/tools/schemas.py`: Anthropic tool-use JSON schemas (`CML_REPORT_TOOL`, `CONTRACT_NOTE_TOOL`) for P4 to register on the agent. Read-only tools — no writes.
- Treat the contract-note host/path as configuration (`Settings.FINX_CONTRACT_NOTE_BASE_URL`), because it was not re-confirmed after CML moved to `finxomne`.
- NOT in scope: the agent loop (P4), API/SSE endpoints (P5), the RAG tool (P1), frontend (P8). No changes to `backend/contracts`, `backend/config`, or any dependency/root config file.

## Capabilities

### New Capabilities
- `finx-report-tools`: read-only FINX MIS report tool clients (CML report, contract note) with session-derived auth headers, failure-to-`ReportResult` mapping, and Anthropic tool-use schemas for agent registration.

### Modified Capabilities
<!-- None — this change adds a new capability and imports frozen P0 contracts without modifying them. -->

## Impact

- New files, all inside the owned directory `backend/tools/`:
  - `backend/tools/finx_client.py` — the two tool functions + private header/URL helpers.
  - `backend/tools/schemas.py` — the two Anthropic tool-use JSON schemas.
  - `backend/tools/__init__.py` — export the tool functions and schemas (the placeholder created by P0 gains exports; no other package touched).
  - `backend/tools/tests/test_finx_client.py` — tests with mocked httpx.
- Imports only (no redefinition): `backend.config.settings.Settings`; `backend.contracts.session.SessionContext`; `backend.contracts.reports.{CmlReportRequest, ContractNoteRequest, ReportResult}`.
- No new dependency introduced — `httpx` is already declared by P0 (foundations-and-contracts). If it were missing, it would be added there, not here.
- Depends on P0 `foundations-and-contracts` being merged to `main` (config + contracts).
