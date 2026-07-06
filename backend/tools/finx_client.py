"""FINX MIS report tool clients (P2).

Two read-only async tools the agent can call:

- :func:`cml_report` — the client's CML (Client Master List) holdings report.
- :func:`contract_note` — the client's contract note for a trade date.

Both POST to the FINX MIS endpoints using base URLs from :class:`Settings`
and the three FINX auth headers assembled from :class:`SessionContext`
(``Authorization`` JWT, ``authType``, ``source``) — never from the request
body. Every HTTP status, timeout, or network error is contained and returned
as ``ReportResult(ok=False, ...)``; these functions never raise.
"""

from __future__ import annotations

import httpx

from backend.contracts.reports import (
    CmlReportRequest,
    ContractNoteRequest,
    ReportResult,
)
from backend.contracts.session import SessionContext

# FINX MIS paths (base hosts come from Settings — never hardcoded here).
_CML_PATH = "/mis/reports/generate"
_CONTRACT_NOTE_PATH = "/mis/v2/contract-note/generate"

# Single attempt with an explicit timeout — no retries/backoff for the POC.
_TIMEOUT = httpx.Timeout(10.0)

# Truncate an error body so a large FINX HTML/JSON page never floods the result.
_ERROR_BODY_LIMIT = 500


def _finx_headers(session: SessionContext) -> dict[str, str]:
    """Assemble the FINX auth headers from the session (not the body)."""
    return {
        "Authorization": session.session_token,
        "authType": "jwt",
        "source": "FINX_WEB",
        "Content-Type": "application/json",
    }


async def _post_report(
    *,
    report_type: str,
    url: str,
    body: dict,
    session: SessionContext,
) -> ReportResult:
    """POST one report request and map every outcome to a ``ReportResult``.

    Never raises: HTTP status, timeout, connection, and JSON-decode errors are
    all contained and returned as ``ReportResult(ok=False, ...)``.
    """
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(
                url,
                json=body,
                headers=_finx_headers(session),
            )
    except httpx.TimeoutException:
        return ReportResult(
            ok=False,
            report_type=report_type,
            data=None,
            error="timeout after 10.0s",
        )
    except httpx.RequestError as exc:
        return ReportResult(
            ok=False,
            report_type=report_type,
            data=None,
            error=f"request error: {exc}",
        )

    if not response.is_success:
        detail = response.text[:_ERROR_BODY_LIMIT]
        return ReportResult(
            ok=False,
            report_type=report_type,
            data=None,
            error=f"HTTP {response.status_code}: {detail}",
        )

    try:
        data = response.json()
    except ValueError:
        return ReportResult(
            ok=False,
            report_type=report_type,
            data=None,
            error="invalid JSON response",
        )

    return ReportResult(ok=True, report_type=report_type, data=data, error=None)


async def cml_report(session: SessionContext, search_value: str) -> ReportResult:
    """Fetch the client's CML report from FINX. Read-only; never raises."""
    # Imported lazily so importing this module has no config-validation side
    # effect (Settings is an eagerly-validated singleton in P0).
    from backend.config import get_settings

    settings = get_settings()
    url = f"{settings.finx_reports_base_url.rstrip('/')}{_CML_PATH}"
    body = CmlReportRequest(search_value=search_value).model_dump(by_alias=True)
    return await _post_report(
        report_type="cml",
        url=url,
        body=body,
        session=session,
    )


async def contract_note(
    session: SessionContext, mobile_no: str, contract_date: str
) -> ReportResult:
    """Fetch the client's contract note from FINX. Read-only; never raises."""
    from backend.config import get_settings

    settings = get_settings()
    base_url = settings.finx_contract_note_base_url or settings.finx_reports_base_url
    url = f"{base_url.rstrip('/')}{_CONTRACT_NOTE_PATH}"
    body = ContractNoteRequest(
        mobile_no=mobile_no, contract_date=contract_date
    ).model_dump(by_alias=True)
    return await _post_report(
        report_type="contract-note",
        url=url,
        body=body,
        session=session,
    )
