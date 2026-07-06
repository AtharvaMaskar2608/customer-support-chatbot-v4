## 1. Preconditions (from P0, do not create here)

- [x] 1.1 Confirm P0 `foundations-and-contracts` is merged: `backend.config.settings.Settings` exposes `FINX_REPORTS_BASE_URL` and `FINX_CONTRACT_NOTE_BASE_URL`; `backend.contracts.session.SessionContext` and `backend.contracts.reports.{CmlReportRequest, ContractNoteRequest, ReportResult}` are importable; `httpx` is installed. (If `httpx` is missing, it is a P0 addition — do not modify dependency files here.)

## 2. HTTP client (`backend/tools/finx_client.py`)

- [x] 2.1 Add private helpers: `_finx_headers(session) -> dict` (Authorization=session_token, authType=jwt, source=FINX_WEB, Content-Type=application/json) and path constants `_CML_PATH="/mis/reports/generate"`, `_CONTRACT_NOTE_PATH="/mis/v2/contract-note/generate"`.
- [x] 2.2 Implement `async def cml_report(session: SessionContext, search_value: str) -> ReportResult` — build `CmlReportRequest(search_value=...).model_dump(by_alias=True)`, POST to `FINX_REPORTS_BASE_URL` + `_CML_PATH` with a timeout, return `ReportResult(ok=True, report_type="cml", data=<json>)` on 2xx.
- [x] 2.3 Implement `async def contract_note(session: SessionContext, mobile_no: str, contract_date: str) -> ReportResult` — build `ContractNoteRequest(...).model_dump(by_alias=True)`, POST to `FINX_CONTRACT_NOTE_BASE_URL` + `_CONTRACT_NOTE_PATH` with a timeout, return `ReportResult(ok=True, report_type="contract-note", data=<json>)` on 2xx.
- [x] 2.4 Wrap both in try/except so no HTTP status, `httpx.TimeoutException`, `httpx.RequestError`, or JSON-decode error propagates — map each to `ReportResult(ok=False, report_type=..., data=None, error=<structured message including status/detail>)`.
- [x] 2.5 Read base URLs from `Settings` (via the P0 accessor) with `.rstrip('/')`; assert no base URL is hardcoded.

## 3. Tool schemas (`backend/tools/schemas.py`)

- [x] 3.1 Define `CML_REPORT_TOOL` (name `cml_report`, required `["search_value"]`) and `CONTRACT_NOTE_TOOL` (name `contract_note`, required `["mobile_no","contract_date"]`) as Anthropic tool-use dicts; sessions excluded from `input_schema`.
- [x] 3.2 Re-export `cml_report`, `contract_note`, `CML_REPORT_TOOL`, `CONTRACT_NOTE_TOOL` from `backend/tools/__init__.py`.

## 4. Tests (`backend/tools/tests/test_finx_client.py`, mocked httpx)

- [x] 4.1 200 path: mock httpx to return a 200 JSON body; assert `cml_report` and `contract_note` return `ok=True`, correct `report_type`, and `data` == raw JSON.
- [x] 4.2 Header/body assertion: capture the request and assert headers include `Authorization`/`authType=jwt`/`source=FINX_WEB` and the JSON body uses FINX alias keys (`reportType`/`searchBy`/`searchValue`; `mobileNo`/`contractDate`).
- [x] 4.3 Failure paths: mock non-2xx (401/500), `httpx.TimeoutException`, and `httpx.RequestError`; assert each returns `ok=False` with a non-empty structured `error` and does not raise.
- [x] 4.4 Config-driven contract-note host: set `FINX_CONTRACT_NOTE_BASE_URL` distinct from `FINX_REPORTS_BASE_URL`; assert `contract_note` targets the former host + `/mis/v2/contract-note/generate`.

## 5. Verification

- [x] 5.1 Run `openspec validate finx-report-tools --strict` — passes.
- [x] 5.2 **Done condition:** with a stubbed/mocked httpx, `cml_report` and `contract_note` return an `ok=True` result on a 200 and a structured `ok=False` `ReportResult` on HTTP/network/timeout failure; outgoing headers include `Authorization`/`authType`/`source` and bodies use FINX alias keys; all changes confined to `backend/tools/`. **Test command:** `pytest backend/tools -q`
