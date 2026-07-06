# database-access Specification

## Purpose
TBD - created by archiving change cho-33-foundations-and-contracts. Update Purpose after archive.
## Requirements
### Requirement: Read-only connection to qa_chunks

The system SHALL provide a Postgres connection helper built from configuration that reads the pre-populated `qa_chunks` table. The helper SHALL register the pgvector type so `embedding vector(3072)` values round-trip, and SHALL be used read-only (no writes, no schema changes) since embeddings and the `fts` column already exist.

#### Scenario: Connection uses configured credentials

- **WHEN** the connection helper is created
- **THEN** it connects using `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD` from configuration

#### Scenario: Vector values round-trip

- **WHEN** a query selects the `embedding` column from `qa_chunks`
- **THEN** the value is returned as a usable vector type without manual parsing

### Requirement: No schema mutation

The system SHALL NOT create, alter, or drop tables, indexes, or columns. The `qa_chunks` table (including `embedding` and the generated `fts` tsvector with its GIN index) is treated as an existing, read-only fixture.

#### Scenario: No migrations shipped

- **WHEN** this change is inspected for DDL
- **THEN** it contains no `CREATE`, `ALTER`, or `DROP` statements against `qa_chunks`

