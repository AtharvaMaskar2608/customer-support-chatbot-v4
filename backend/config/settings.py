"""Typed, environment-driven configuration for the backend.

All runtime settings are loaded from the environment (via a `.env` file in
development). Nothing — connection details, credentials, model names, base
URLs — is hardcoded outside this loader and its documented defaults. Required
keys are validated at import/startup so misconfiguration fails fast instead of
mid-conversation.
"""

from __future__ import annotations

import re
from functools import lru_cache

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Tolerant DSN parser. urlparse rejects raw special characters (e.g. an
# unencoded "[" in the password reads as an IPv6 literal), so parse the
# well-formed `scheme://user:pass@host:port/dbname` shape directly.
_DSN_RE = re.compile(
    r"^\w+://"
    r"(?:(?P<user>[^:/@]+)(?::(?P<password>[^@]*))?@)?"
    r"(?P<host>[^:/@]+)"
    r"(?::(?P<port>\d+))?"
    r"(?:/(?P<dbname>[^?]+))?"
)


class Settings(BaseSettings):
    """Canonical settings object consumed by every backend module.

    Contract: import ``from backend.config import settings`` (a singleton) or
    call :func:`get_settings`. All downstream changes (P1–P8) read configuration
    exclusively through this object.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Anthropic (agent) ---
    anthropic_api_key: str = Field(..., validation_alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field("claude-sonnet-4-5", validation_alias="ANTHROPIC_MODEL")

    # --- Embeddings (OpenAI) ---
    embedding_model: str = Field("text-embedding-3-large", validation_alias="EMBEDDING_MODEL")
    # Accept either EMBEDDING_API_KEY or OPENAI_API_KEY.
    embedding_api_key: str = Field(
        ...,
        validation_alias=AliasChoices("EMBEDDING_API_KEY", "OPENAI_API_KEY"),
    )

    # --- Postgres (read-only qa_chunks) ---
    database_url: str | None = Field(None, validation_alias="DATABASE_URL")
    db_host: str = Field("localhost", validation_alias="DB_HOST")
    db_port: int = Field(5433, validation_alias="DB_PORT")
    db_name: str = Field("customer-support-chatbot", validation_alias="DB_NAME")
    db_user: str = Field("atharva", validation_alias="DB_USER")
    db_password: str = Field("", validation_alias="DB_PASSWORD")

    # --- FINX report services ---
    finx_reports_base_url: str = Field(..., validation_alias="FINX_REPORTS_BASE_URL")
    finx_contract_note_base_url: str | None = Field(
        None, validation_alias="FINX_CONTRACT_NOTE_BASE_URL"
    )

    # --- Tracing / evals ---
    tracing_enabled: bool = Field(False, validation_alias="TRACING_ENABLED")
    confident_api_key: str | None = Field(None, validation_alias="CONFIDENT_API_KEY")

    # --- Cost card ---
    usd_to_inr: float = Field(95.0, validation_alias="USD_TO_INR")

    # --- API / CORS ---
    frontend_origin: str = Field("http://localhost:5173", validation_alias="FRONTEND_ORIGIN")

    @model_validator(mode="after")
    def _derive_defaults(self) -> "Settings":
        # If a DATABASE_URL is supplied, use it to fill the discrete DB_* fields
        # so both styles of configuration are supported.
        if self.database_url:
            match = _DSN_RE.match(self.database_url.strip())
            if not match:
                raise ValueError("DATABASE_URL is not a valid postgres connection URL")
            parts = match.groupdict()
            if parts["host"]:
                self.db_host = parts["host"]
            if parts["port"]:
                self.db_port = int(parts["port"])
            if parts["user"]:
                self.db_user = parts["user"]
            if parts["password"] is not None:
                self.db_password = parts["password"]
            if parts["dbname"]:
                self.db_name = parts["dbname"]

        # Contract Note host defaults to the reports host when unset.
        if not self.finx_contract_note_base_url:
            self.finx_contract_note_base_url = self.finx_reports_base_url

        # Tracing requires a key when enabled — fail fast rather than mid-run.
        if self.tracing_enabled and not self.confident_api_key:
            raise ValueError("CONFIDENT_API_KEY is required when TRACING_ENABLED is true")

        return self

    @property
    def db_dsn(self) -> str:
        """A libpq keyword/value conninfo string built from configured credentials.

        Built via psycopg's ``make_conninfo`` so passwords with special
        characters (``[``, ``!``, spaces, quotes) are escaped correctly instead
        of relying on URL percent-encoding.
        """
        from psycopg.conninfo import make_conninfo

        return make_conninfo(
            host=self.db_host,
            port=self.db_port,
            dbname=self.db_name,
            user=self.db_user,
            password=self.db_password,
        )


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton (validated on first call)."""
    return Settings()  # type: ignore[call-arg]


# Eagerly-validated singleton: importing this module fails fast on misconfig.
settings = get_settings()
