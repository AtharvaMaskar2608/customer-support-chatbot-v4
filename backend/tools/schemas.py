"""Anthropic tool-use JSON schemas for the FINX report tools (P2).

Plain dicts for P4 to pass to the Anthropic ``tools=[...]`` param. Only the
agent-supplied arguments are exposed; the ``SessionContext`` is injected by P4
and is never model-controlled, so it does not appear in any ``input_schema``.
Tool ``name`` values match the function names in :mod:`backend.tools.finx_client`.
"""

from __future__ import annotations

CML_REPORT_TOOL = {
    "name": "cml_report",
    "description": (
        "Fetch the client's CML (Client Master List) holdings/account report "
        "from FINX. Read-only."
    ),
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
    "description": (
        "Fetch the client's contract note for a given trade date from FINX. "
        "Read-only."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "mobile_no": {
                "type": "string",
                "description": "Client's registered mobile number.",
            },
            "contract_date": {
                "type": "string",
                "description": "Trade date in DD-MM-YYYY format.",
            },
        },
        "required": ["mobile_no", "contract_date"],
    },
}
