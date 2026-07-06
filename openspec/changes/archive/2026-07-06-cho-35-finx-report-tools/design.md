## Context

This change (P2) implements the two read-only FINX MIS report tools the agent can call. It lives entirely in `backend/tools/` and imports the frozen P0 surface — it defines no new contracts.

Files touched (all new, all under `backend/tools/`):
- `backend/tools/finx_client.py` — `cml_report`, `contract_note`, private header/URL helpers.
- `backend/tools/schemas.py` — `CML_REPORT_TOOL`, `CONTRACT_NOTE_TOOL` Anthropic tool-use schemas.
- `backend/tools/__init__.py` — re-exports.
- `backend/tools/tests/test_finx_client.py` — mocked-httpx tests.

Imported dependencies (frozen P0 contracts — IMPORT, do not redefine):
- `backend.config.settings.Settings` → `FINX_REPORTS_BASE_URL`, `FINX_CONTRACT_NOTE_BASE_URL`.
- `backend.contracts.session.SessionContext` → `client_code`, `session_token` (the JWT).
- `backend.contracts.reports` → `CmlReportRequest`, `ContractNoteRequest`, `ReportResult`.
- `httpx` (already declared by P0).

The two endpoints and the shared headers:
- **CML report** — `POST {FINX_REPORTS_BASE_URL}/mis/reports/generate`, body `{"reportType":"cml","searchBy":"client-id","searchValue":"<clientCode>"}` (e.g. `X130627`). Host confirmed on `finxomne.choiceindia.com`.
- **Contract note** — `POST {FINX_CONTRACT_NOTE_BASE_URL}/mis/v2/contract-note/generate`, body `{"mobileNo":"<phone>","contractDate":"<DD-MM-YYYY>"}`. Host/path NOT re-confirmed after CML moved to `finxomne` — driven by its own config key.
- **Shared headers on every call**: `Authorization: <session.session_token>`, `authType: jwt`, `source: FINX_WEB`.

## Goals / Non-Goals

**Goals:**
- Two callable, read-only tool functions that correctly hit the two FINX endpoints with session-derived auth.
- Total failure containment: no HTTP status, timeout, or network exception ever propagates to the caller — everything becomes a `ReportResult`.
- Provide Anthropic tool-use JSON schemas so P4 can register the tools without knowing the HTTP details.

**Non-Goals:**
- No agent loop, no tool dispatch/registration wiring (P4), no API endpoints/SSE (P5), no frontend (P8).
- No parsing/normalization of the FINX response body — success returns the raw JSON dict verbatim in `data`.
- No caching, retries with backoff policy tuning, or rate limiting (single attempt with a timeout is sufficient for the POC).
- No contract changes — `ReportResult`/request models come from P0 as-is.

## Decisions

**Function signatures** (async, httpx.AsyncClient):
```python
async def cml_report(session: SessionContext, search_value: str) -> ReportResult
async def contract_note(session: SessionContext, mobile_no: str, contract_date: str) -> ReportResult
```
Both are `async` to match the async FastAPI/agent runtime (P4/P5). Each opens a short-lived `httpx.AsyncClient` (so tests can patch `httpx.AsyncClient`), POSTs once, and returns a `ReportResult`.

**Header assembly** — a single private helper builds the FINX headers from the session, keeping auth in one place:
```python
def _finx_headers(session: SessionContext) -> dict[str, str]:
    return {
        "Authorization": session.session_token,
        "authType": "jwt",
        "source": "FINX_WEB",
        "Content-Type": "application/json",
    }
```
Headers come from `SessionContext`, never from the request-body models (matches P0's report-tool contract note).

**Body serialization** — build the frozen request model and dump with aliases so FINX gets `reportType`/`searchBy`/`searchValue`/`mobileNo`/`contractDate`:
```python
body = CmlReportRequest(search_value=search_value).model_dump(by_alias=True)
body = ContractNoteRequest(mobile_no=mobile_no, contract_date=contract_date).model_dump(by_alias=True)
```
`report_type` and `search_by` keep their frozen defaults (`"cml"`, `"client-id"`); the caller only supplies `search_value`.

**URL construction** — base URL from config, path constant per tool:
```python
_CML_PATH = "/mis/reports/generate"
_CONTRACT_NOTE_PATH = "/mis/v2/contract-note/generate"
url = f"{settings.FINX_REPORTS_BASE_URL.rstrip('/')}{_CML_PATH}"
url = f"{settings.FINX_CONTRACT_NOTE_BASE_URL.rstrip('/')}{_CONTRACT_NOTE_PATH}"
```
`Settings` is read via the P0 accessor (module-level `get_settings()`/`Settings()` per P0's loader); base URLs are never hardcoded.

**Timeout & error policy** — single attempt, explicit timeout (default `httpx.Timeout(10.0)`), and a wrapping try/except that maps outcomes:
- 2xx → `ReportResult(ok=True, report_type=<"cml"|"contract-note">, data=response.json(), error=None)`.
- Non-2xx → `ReportResult(ok=False, report_type=..., data=None, error="HTTP <status>: <truncated body>")`.
- `httpx.TimeoutException` → `error="timeout after <n>s"`.
- `httpx.RequestError` (connection/DNS) → `error="request error: <detail>"`.
- JSON decode failure on a 2xx → `ReportResult(ok=False, ..., error="invalid JSON response")`.
The functions never raise; `report_type` on the result is always set so the caller can tell the two tools apart even on error.

**Anthropic tool-use schemas** (`backend/tools/schemas.py`) — plain dicts for P4 to pass to the Anthropic `tools=[...]` param. Only agent-supplied arguments are exposed (session is injected by P4, never model-controlled):
```python
CML_REPORT_TOOL = {
    "name": "cml_report",
    "description": "Fetch the client's CML (Client Master List) holdings/account report from FINX. Read-only.",
    "input_schema": {
        "type": "object",
        "properties": {
            "search_value": {
                "type": "string",
                "description": "The client code, e.g. 'X130627'.",
            }
        },
        "required": ["search_value"],
    },
}
CONTRACT_NOTE_TOOL = {
    "name": "contract_note",
    "description": "Fetch the client's contract note for a given trade date from FINX. Read-only.",
    "input_schema": {
        "type": "object",
        "properties": {
            "mobile_no": {"type": "string", "description": "Client's registered mobile number."},
            "contract_date": {"type": "string", "description": "Trade date in DD-MM-YYYY format."},
        },
        "required": ["mobile_no", "contract_date"],
    },
}
```
Tool `name` values match the function names and `ToolCallRecord.name` values already enumerated in P0's agent contract (`cml_report`, `contract_note`).

## Risks / Trade-offs

- **[Contract-note host/path unconfirmed after CML moved to `finxomne`]** → driven by `Settings.FINX_CONTRACT_NOTE_BASE_URL` (a separate P0 config key) and a module-level path constant, so a correction is a config/one-line change, not a rewrite. Flagged below.
- **[Raw FINX JSON returned verbatim]** → the agent (P4) and prompt decide how to present it; if FINX wraps errors in a 200 body, that is not detected here (only HTTP status drives ok/failure). Acceptable for the POC; P4 can post-validate.
- **[Session JWT expiry / 401]** → surfaces as `ok=False, error="HTTP 401: ..."`; the agent can then offer a support ticket. No token refresh in scope.
- **[Async vs sync]** → chosen async to match the FastAPI/agent runtime; tests mock `httpx.AsyncClient` so no live network.

## Open Questions

- **Contract-note endpoint host/path.** CML is confirmed at `finxomne.choiceindia.com/mis/reports/generate`; the contract note is assumed at `{FINX_CONTRACT_NOTE_BASE_URL}/mis/v2/contract-note/generate`. Must be confirmed against the live FINX MIS before P2 is wired into P4. Resolved via config + the path constant — no contract change required either way.
