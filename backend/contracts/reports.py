"""Report tool I/O contracts (P2 FINX report tools).

Request bodies serialize to the FINX MIS JSON keys via field aliases. FINX
authentication headers (``Authorization`` JWT, ``authType``, ``source``) are
NOT part of these body models — the P2 client adds them from
:class:`~backend.contracts.session.SessionContext`.

Serialize with ``model_dump(by_alias=True)`` to produce the FINX JSON body.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CmlReportRequest(BaseModel):
    """CML report request → FINX keys ``reportType``, ``searchBy``, ``searchValue``."""

    model_config = ConfigDict(populate_by_name=True)

    report_type: str = Field(default="cml", serialization_alias="reportType", alias="reportType")
    search_by: str = Field(
        default="client-id", serialization_alias="searchBy", alias="searchBy"
    )
    search_value: str = Field(serialization_alias="searchValue", alias="searchValue")


class ContractNoteRequest(BaseModel):
    """Contract note request → FINX keys ``mobileNo``, ``contractDate`` (DD-MM-YYYY)."""

    model_config = ConfigDict(populate_by_name=True)

    mobile_no: str = Field(serialization_alias="mobileNo", alias="mobileNo")
    contract_date: str = Field(serialization_alias="contractDate", alias="contractDate")


class ReportResult(BaseModel):
    """Unified result for both report tools."""

    ok: bool
    report_type: str  # "cml" | "contract-note"
    data: dict | None = None  # raw JSON body from FINX MIS on success
    error: str | None = None
