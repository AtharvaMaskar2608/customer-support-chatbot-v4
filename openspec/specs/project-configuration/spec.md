# project-configuration Specification

## Purpose
TBD - created by archiving change cho-33-foundations-and-contracts. Update Purpose after archive.
## Requirements
### Requirement: Environment-driven configuration

The system SHALL load all runtime configuration from environment variables (via a `.env` file in development) and SHALL NOT hardcode connection details, credentials, model names, or base URLs. A committed `.env.example` SHALL document every supported key.

#### Scenario: Config loaded from environment

- **WHEN** the backend process starts with a populated `.env`
- **THEN** a typed settings object exposes Anthropic, embedding, Postgres, FINX reports, and tracing settings sourced only from the environment

#### Scenario: No hardcoded connection details

- **WHEN** the source is inspected for DB host/port/name/user, API keys, model strings, or FINX base URLs
- **THEN** none of these values appear as literals outside `.env`/`.env.example` and the config loader defaults

### Requirement: Fail-fast validation

The system SHALL validate configuration at startup and SHALL raise an error identifying the missing or invalid key when a required setting is absent, rather than failing later during a request.

#### Scenario: Missing required key

- **WHEN** a required setting (e.g. `ANTHROPIC_API_KEY` or `DB_HOST`) is absent at startup
- **THEN** startup fails immediately with an error naming the missing key

### Requirement: Configurable model and embedding defaults

The system SHALL default `ANTHROPIC_MODEL` to `claude-sonnet-4-5` and `EMBEDDING_MODEL` to `text-embedding-3-large`, both overridable via environment, and SHALL expose a separate base-URL setting for FINX report services so hosts can differ per report type without code changes.

#### Scenario: Override model via environment

- **WHEN** `ANTHROPIC_MODEL` is set in the environment
- **THEN** the settings object returns that value instead of the default

