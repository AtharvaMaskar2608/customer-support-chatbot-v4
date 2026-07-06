"""Hybrid (vector + full-text) retrieval over ``qa_chunks``.

This module is the agent's RAG tool. It exposes a single public entrypoint,
:func:`rag_search`, backed by four internal helpers:

- :func:`embed_query`  — embed the query with the configured OpenAI model.
- :func:`vector_search` — cosine-distance ranking over ``qa_chunks.embedding``.
- :func:`fts_search`    — lexical ranking over the generated ``qa_chunks.fts``.
- :func:`rrf_fuse`      — Reciprocal Rank Fusion of the two ranked lists.

Vector-only search misses exact-keyword hits (product names, ticket IDs, TAT
phrasing); FTS-only search misses paraphrases. Fusing both with RRF captures
both. Every surviving row is mapped to a :class:`RetrievedChunk` carrying a
fully-populated :class:`Citation`, so every RAG answer is citable.

The table is small (~1,100 rows) and embeddings are 3072-d, so vector search
uses an exact/sequential scan (no ANN index). Configuration — model, key, DB
credentials — comes exclusively from :mod:`backend.config`; nothing is
hardcoded here.
"""

from __future__ import annotations

from openai import OpenAI
from pgvector import Vector
from psycopg.rows import dict_row

from backend.config import settings
from backend.contracts.rag_tool import RagToolInput, RagToolOutput
from backend.contracts.retrieval import Citation, RetrievedChunk
from backend.db.pool import get_connection

RRF_K: int = 60  # RRF smoothing constant — larger k flattens rank contribution.
CANDIDATE_LIMIT: int = 50  # rows pulled from each retriever before fusion.

# Columns selected by both retrievers; a shared key set keeps fusion and mapping
# uniform regardless of which retriever a row came from.
_SELECT_COLUMNS = "id, topic, section, question, answer, answer_source, tat, source_row, chunk"

# --- Optional tracing (P3 soft dependency) -----------------------------------
# Decorate public functions with ``@observe`` when P3 ``backend.tracing`` is
# installed; otherwise fall back to a no-op so this module imports and runs
# without the tracing foundation. The fallback supports both bare ``@observe``
# and parameterized ``@observe(...)`` usage.
try:  # pragma: no cover - exercised via the P3-absent import test
    from backend.tracing import observe
except Exception:  # noqa: BLE001 - any import failure degrades to no-op tracing

    def observe(*args, **kwargs):
        if len(args) == 1 and callable(args[0]) and not kwargs:
            # Used as a bare decorator: @observe
            return args[0]

        # Used with arguments: @observe(name=...) -> return the real decorator.
        def _decorator(fn):
            return fn

        return _decorator


@observe()
def embed_query(query: str) -> list[float]:
    """Embed ``query`` with the configured OpenAI model at full dimensions.

    Model name and API key come from :mod:`backend.config` — nothing is
    hardcoded. The model (``text-embedding-3-large``) is used at its native
    3072 dimensions (``dimensions=`` is deliberately not passed) so the returned
    vector matches ``qa_chunks.embedding vector(3072)``.
    """
    client = OpenAI(api_key=settings.embedding_api_key)
    resp = client.embeddings.create(model=settings.embedding_model, input=query)
    embedding = resp.data[0].embedding
    if len(embedding) != 3072:
        raise ValueError(
            f"expected a 3072-dim embedding from {settings.embedding_model}, "
            f"got {len(embedding)} dims"
        )
    return embedding


@observe()
def vector_search(embedding: list[float], limit: int = CANDIDATE_LIMIT) -> list[dict]:
    """Rank chunks by cosine distance to ``embedding`` (exact/sequential scan).

    pgvector's ``<=>`` is cosine distance (lower = more similar), so results are
    ordered ascending. Returns up to ``limit`` row dicts, each carrying its
    ``qa_chunks.id`` and the columns needed to build a ``RetrievedChunk`` and
    ``Citation``. Ranking is by row ordinal in the returned order.
    """
    sql = f"""
        SELECT {_SELECT_COLUMNS}
        FROM qa_chunks
        ORDER BY embedding <=> %(emb)s ASC
        LIMIT %(limit)s
    """
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        # Wrap in pgvector's ``Vector`` so the registered dumper serializes it as
        # a ``vector`` literal; a bare list would be sent as ``double precision[]``.
        cur.execute(sql, {"emb": Vector(embedding), "limit": limit})
        return cur.fetchall()


@observe()
def fts_search(query: str, limit: int = CANDIDATE_LIMIT) -> list[dict]:
    """Lexically rank chunks over the generated ``fts`` tsvector via ``ts_rank``.

    ``websearch_to_tsquery`` tolerates natural phrasing and yields an empty
    tsquery for blank/all-stopword input — which matches zero rows and returns
    ``[]`` rather than raising. Returns up to ``limit`` row dicts in descending
    ``ts_rank`` order, with the same column set as :func:`vector_search`.
    """
    sql = f"""
        SELECT {_SELECT_COLUMNS}
        FROM qa_chunks
        WHERE fts @@ websearch_to_tsquery('english', %(q)s)
        ORDER BY ts_rank(fts, websearch_to_tsquery('english', %(q)s)) DESC
        LIMIT %(limit)s
    """
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, {"q": query, "limit": limit})
        return cur.fetchall()


def rrf_fuse(
    vector_rows: list[dict],
    fts_rows: list[dict],
    top_k: int,
    k: int = RRF_K,
) -> list[tuple[dict, float]]:
    """Fuse two ranked lists with Reciprocal Rank Fusion.

    Each chunk's fused score is the sum over both lists of ``1 / (k + rank)``
    (rank 1-based). A chunk present in both lists accumulates two terms, so it
    outranks equally-placed single-list chunks. Cosine distance and ``ts_rank``
    are not on a comparable scale, so RRF fuses ordinal ranks and sidesteps score
    normalization entirely. Dedup by ``id`` is inherent. Returns the top ``top_k``
    ``(row, fused_score)`` pairs ordered by descending fused score.
    """
    scores: dict[int, float] = {}
    rows_by_id: dict[int, dict] = {}
    for ranked in (vector_rows, fts_rows):
        for rank, row in enumerate(ranked, start=1):  # 1-based rank
            cid = row["id"]
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
            rows_by_id.setdefault(cid, row)
    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [(rows_by_id[cid], score) for cid, score in ordered[:top_k]]


def _row_to_chunk(row: dict, score: float) -> RetrievedChunk:
    """Map a ``qa_chunks`` row + fused score to a citable ``RetrievedChunk``.

    ``chunk_id == citation.chunk_id == qa_chunks.id`` guarantees citability.
    """
    citation = Citation(
        chunk_id=row["id"],
        topic=row["topic"],
        section=row["section"],
        question=row["question"],
        answer_source=row["answer_source"],
        source_row=row["source_row"],
    )
    return RetrievedChunk(
        chunk_id=row["id"],
        chunk=row["chunk"],
        question=row["question"],
        answer=row["answer"],
        tat=row["tat"],
        score=score,
        citation=citation,
    )


@observe()
def rag_search(query: str, top_k: int = 10) -> RagToolOutput:
    """Hybrid RAG retrieval: vector + full-text search fused with RRF.

    Validates the input via :class:`RagToolInput`. A blank query short-circuits
    to an empty result (no embedding call, no DB round-trip). Otherwise it embeds
    the query, runs both retrievers, fuses them with :func:`rrf_fuse`, and returns
    at most ``top_k`` :class:`RetrievedChunk`s ordered by descending fused score,
    each with a fully-populated citation.
    """
    params = RagToolInput(query=query, top_k=top_k)
    if not params.query.strip():
        return RagToolOutput(chunks=[])

    embedding = embed_query(params.query)
    vector_rows = vector_search(embedding)
    fts_rows = fts_search(params.query)
    fused = rrf_fuse(vector_rows, fts_rows, params.top_k)
    return RagToolOutput(chunks=[_row_to_chunk(row, score) for row, score in fused])
