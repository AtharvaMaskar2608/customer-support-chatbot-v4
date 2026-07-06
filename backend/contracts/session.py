"""Session context contract.

Carries the per-conversation identity used for FINX report calls. Both values
are trimmed of surrounding whitespace; ``session_token`` is used as the FINX
``Authorization`` JWT by the P2 report client.
"""

from __future__ import annotations

from pydantic import BaseModel, field_validator


class SessionContext(BaseModel):
    """Client identity + FINX session token for a conversation."""

    client_code: str
    session_token: str  # used as the FINX Authorization JWT

    @field_validator("client_code", "session_token")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()
