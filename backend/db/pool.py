"""Read-only Postgres access to the pre-populated ``qa_chunks`` table.

This helper builds a psycopg 3 connection from :mod:`backend.config` and
registers the pgvector type adapter so ``embedding vector(3072)`` values
round-trip as Python sequences without manual parsing.

Usage is strictly read-only: this change ships no DDL and performs no writes.
The ``qa_chunks`` table (with its ``embedding`` column and generated ``fts``
tsvector + GIN index) is treated as an existing, read-only fixture.

Contract:
    get_connection() -> psycopg.Connection
        A new autocommit, read-only connection with pgvector registered.
        Caller is responsible for closing it (or use it as a context manager).
"""

from __future__ import annotations

import psycopg
from pgvector.psycopg import register_vector

from backend.config import settings


def get_connection() -> psycopg.Connection:
    """Open a read-only psycopg connection with pgvector registered.

    The connection is opened in autocommit mode and marked read-only so no
    accidental writes or schema changes can occur. pgvector's type adapter is
    registered on the connection so selecting ``embedding`` yields a usable
    vector value.
    """
    conn = psycopg.connect(settings.db_dsn, autocommit=True)
    try:
        conn.read_only = True
        register_vector(conn)
    except Exception:
        conn.close()
        raise
    return conn


def smoke_check() -> tuple[int, int]:
    """Verify the DB is reachable and populated, and that vectors deserialize.

    Returns ``(row_count, embedding_dims)``. Raises if ``qa_chunks`` is empty or
    the ``embedding`` column does not come back as a usable, correctly-sized
    vector. Intended for manual/CI verification, not the request path.
    """
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM qa_chunks")
        row_count = cur.fetchone()[0]
        if row_count <= 0:
            raise RuntimeError("qa_chunks is empty; expected a pre-populated table")

        cur.execute("SELECT embedding FROM qa_chunks WHERE embedding IS NOT NULL LIMIT 1")
        row = cur.fetchone()
        if row is None:
            raise RuntimeError("no rows with a non-null embedding in qa_chunks")
        embedding = row[0]
        dims = len(embedding)
        if dims <= 0:
            raise RuntimeError("embedding did not deserialize into a usable vector")

    return row_count, dims


if __name__ == "__main__":  # pragma: no cover - manual smoke check
    count, dims = smoke_check()
    print(f"qa_chunks rows={count}, embedding dims={dims}")
