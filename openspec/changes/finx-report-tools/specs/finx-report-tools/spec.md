## ADDED Requirements

### Requirement: CML report tool

The system SHALL provide `cml_report(session: SessionContext, search_value: str) -> ReportResult` that POSTs to `{FINX_REPORTS_BASE_URL}/mis/reports/generate` with a body serialized from `CmlReportRequest` (FINX keys `reportType="cml"`, `searchBy="client-id"`, `searchValue=<search_value>`) and returns a `ReportResult` with `report_type="cml"`.

#### Scenario: Successful CML fetch returns raw JSON

- **WHEN** `cml_report` is called with a valid session and client code and FINX responds `200` with a JSON body
- **THEN** it returns `ReportResult(ok=True, report_type="cml", data=<the raw JSON body>, error=None)`

#### Scenario: CML request body maps to FINX JSON keys

- **WHEN** `cml_report` builds the POST body for `search_value="X130627"`
- **THEN** the JSON sent is `{"reportType":"cml","searchBy":"client-id","searchValue":"X130627"}`

### Requirement: Contract note tool

The system SHALL provide `contract_note(session: SessionContext, mobile_no: str, contract_date: str) -> ReportResult` that POSTs to `{FINX_CONTRACT_NOTE_BASE_URL}/mis/v2/contract-note/generate` with a body serialized from `ContractNoteRequest` (FINX keys `mobileNo`, `contractDate` in `DD-MM-YYYY`) and returns a `ReportResult` with `report_type="contract-note"`.

#### Scenario: Successful contract-note fetch returns raw JSON

- **WHEN** `contract_note` is called with a valid session, mobile number, and `contract_date` and FINX responds `200` with a JSON body
- **THEN** it returns `ReportResult(ok=True, report_type="contract-note", data=<the raw JSON body>, error=None)`

#### Scenario: Contract-note request body maps to FINX JSON keys

- **WHEN** `contract_note` builds the POST body for `mobile_no="9876543210"` and `contract_date="03-07-2026"`
- **THEN** the JSON sent is `{"mobileNo":"9876543210","contractDate":"03-07-2026"}`

### Requirement: FINX authentication headers on every call

Both report tools SHALL attach the FINX headers `Authorization: <session.session_token>`, `authType: jwt`, and `source: FINX_WEB` to every request, derived from `SessionContext` and never from the request-body models.

#### Scenario: Headers are assembled from the session

- **WHEN** either report tool issues a request for a session whose `session_token` is a JWT string
- **THEN** the outgoing headers include `Authorization` equal to that JWT, `authType` equal to `jwt`, and `source` equal to `FINX_WEB`

### Requirement: Failures map to ReportResult without raising

Both report tools SHALL NOT raise on any HTTP status, timeout, or network/connection error; every failure SHALL be returned as `ReportResult(ok=False, report_type=<tool's type>, data=None, error=<structured message>)`.

#### Scenario: Non-2xx status becomes a structured error

- **WHEN** FINX responds with a non-2xx status (e.g. `401` or `500`)
- **THEN** the tool returns `ReportResult(ok=False, error=<message including the status code>)` and does not raise

#### Scenario: Network or timeout error becomes a structured error

- **WHEN** the request times out or the connection fails
- **THEN** the tool returns `ReportResult(ok=False, error=<message describing the timeout or request error>)` and does not raise

### Requirement: Contract-note endpoint is configuration-driven

The contract-note host SHALL be read from `Settings.FINX_CONTRACT_NOTE_BASE_URL` (separate from `FINX_REPORTS_BASE_URL`) so the unconfirmed contract-note host/path can be corrected without a code change; no base URL SHALL be hardcoded in the tools.

#### Scenario: Contract-note base URL comes from config

- **WHEN** `FINX_CONTRACT_NOTE_BASE_URL` is set to a given host
- **THEN** `contract_note` sends its POST to that host with path `/mis/v2/contract-note/generate`, independent of `FINX_REPORTS_BASE_URL`

### Requirement: Anthropic tool-use schemas for registration

The system SHALL export Anthropic tool-use JSON schemas `CML_REPORT_TOOL` and `CONTRACT_NOTE_TOOL` whose `name` values are `cml_report` and `contract_note` and whose `input_schema` exposes only the agent-supplied arguments (CML: `search_value`; contract note: `mobile_no`, `contract_date`), excluding the injected session.

#### Scenario: Schemas expose only model-controlled arguments

- **WHEN** P4 registers the report tools from these schemas
- **THEN** `CML_REPORT_TOOL.input_schema.required` is `["search_value"]` and `CONTRACT_NOTE_TOOL.input_schema.required` is `["mobile_no", "contract_date"]`, and neither schema references the session
