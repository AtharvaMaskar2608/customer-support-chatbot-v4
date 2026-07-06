"""Tests for hybrid RAG retrieval (``backend.rag.search``).

DB-backed tests run against the pre-populated ``qa_chunks`` table and skip
cleanly when the database is unreachable. To keep vector ranking deterministic
(and avoid live OpenAI calls), ``embed_query`` is monkeypatched to return the
stored embedding of a known row, so that row sorts to distance 0.
"""

from __future__ import annotations

import importlib
import sys

import pytest

from backend.contracts.rag_tool import RagToolOutput
from backend.contracts.retrieval import RetrievedChunk
from backend.db.pool import get_connection
from backend.rag import rag_search
from backend.rag import search as search_mod


def _db_available() -> bool:
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM qa_chunks LIMIT 1")
            return cur.fetchone() is not None
    except Exception:
        return False


requires_db = pytest.mark.skipif(not _db_available(), reason="qa_chunks DB not reachable")


@pytest.fixture()
def known_row() -> dict:
    """A real ``qa_chunks`` row plus its stored embedding as a ``list[float]``.

    Monkeypatching ``embed_query`` to return this embedding makes the row rank
    first in vector search (cosine distance 0), giving deterministic tests.
    """
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, topic, section, question, answer, answer_source, tat, "
            "source_row, chunk, embedding "
            "FROM qa_chunks WHERE embedding IS NOT NULL ORDER BY id LIMIT 1"
        )
        row = cur.fetchone()
    cols = [
        "id", "topic", "section", "question", "answer",
        "answer_source", "tat", "source_row", "chunk", "embedding",
    ]
    data = dict(zip(cols, row))
    emb = data["embedding"]
    data["embedding"] = emb.to_list() if hasattr(emb, "to_list") else list(emb)
    return data


# --- 5.2: sample query returns a bounded, descending-ordered RagToolOutput ----


@requires_db
def test_sample_query_returns_bounded_descending_output(known_row, monkeypatch):
    monkeypatch.setattr(search_mod, "embed_query", lambda q: known_row["embedding"])

    top_k = 5
    out = rag_search(known_row["question"], top_k=top_k)

    assert isinstance(out, RagToolOutput)
    assert len(out.chunks) >= 1
    assert len(out.chunks) <= top_k
    scores = [c.score for c in out.chunks]
    assert scores == sorted(scores, reverse=True)
    # The row whose embedding we injected must surface in the fused results.
    assert known_row["id"] in {c.chunk_id for c in out.chunks}


@requires_db
def test_top_k_bounds_result_count(known_row, monkeypatch):
    monkeypatch.setattr(search_mod, "embed_query", lambda q: known_row["embedding"])
    out = rag_search(known_row["question"], top_k=3)
    assert len(out.chunks) == 3  # >3 candidates match; result is capped at k


# --- 5.3: RRF ordering + dedup (pure unit test, no DB) ------------------------


def test_rrf_both_lists_outrank_single_list():
    vector_rows = [{"id": 1}, {"id": 2}, {"id": 3}]
    fts_rows = [{"id": 2}, {"id": 4}]  # id=2 appears in both lists

    fused = search_mod.rrf_fuse(vector_rows, fts_rows, top_k=10)
    ids = [row["id"] for row, _ in fused]

    # id=2 (both lists) beats id=1 (single list, rank 1 in vector).
    assert ids[0] == 2
    # Dedup: id=2 appears exactly once; every id present once.
    assert ids.count(2) == 1
    assert sorted(ids) == [1, 2, 3, 4]

    # id=2 score == sum of its reciprocal-rank contributions from both lists.
    k = search_mod.RRF_K
    score_by_id = {row["id"]: score for row, score in fused}
    assert score_by_id[2] == pytest.approx(1.0 / (k + 2) + 1.0 / (k + 1))
    assert score_by_id[1] == pytest.approx(1.0 / (k + 1))
    assert score_by_id[2] > score_by_id[1]


def test_rrf_respects_top_k():
    vector_rows = [{"id": i} for i in range(1, 11)]
    fused = search_mod.rrf_fuse(vector_rows, [], top_k=4)
    assert len(fused) == 4


# --- 5.4: citation population -------------------------------------------------


@requires_db
def test_every_chunk_is_citable(known_row, monkeypatch):
    monkeypatch.setattr(search_mod, "embed_query", lambda q: known_row["embedding"])
    out = rag_search(known_row["question"], top_k=5)

    assert out.chunks
    for chunk in out.chunks:
        assert isinstance(chunk, RetrievedChunk)
        # chunk_id == citation.chunk_id == qa_chunks.id
        assert chunk.chunk_id == chunk.citation.chunk_id

    # For the injected row, verify every citation field is copied from the source.
    by_id = {c.chunk_id: c for c in out.chunks}
    chunk = by_id[known_row["id"]]
    assert chunk.citation.chunk_id == known_row["id"]
    assert chunk.citation.topic == known_row["topic"]
    assert chunk.citation.section == known_row["section"]
    assert chunk.citation.question == known_row["question"]
    assert chunk.citation.answer_source == known_row["answer_source"]
    assert chunk.citation.source_row == known_row["source_row"]
    # Display fields come from the same row.
    assert chunk.chunk == known_row["chunk"]
    assert chunk.answer == known_row["answer"]
    assert chunk.tat == known_row["tat"]


# --- 5.5: empty result + import without tracing -------------------------------


def test_blank_query_returns_empty_and_raises_nothing():
    # Blank query short-circuits before any embedding/DB call.
    for q in ("", "   ", "\t\n"):
        out = rag_search(q)
        assert isinstance(out, RagToolOutput)
        assert out.chunks == []


def test_module_imports_without_tracing(monkeypatch):
    # Simulate P3 ``backend.tracing`` being entirely unimportable.
    monkeypatch.setitem(sys.modules, "backend.tracing", None)
    try:
        reloaded = importlib.reload(search_mod)
        assert callable(reloaded.rag_search)

        # The fallback ``observe`` is a no-op for both decorator forms.
        def fn():
            return 42

        assert reloaded.observe()(fn)() == 42  # @observe(...)
        assert reloaded.observe(fn)() == 42  # @observe
    finally:
        # Restore normal module state for the rest of the suite.
        monkeypatch.undo()
        importlib.reload(search_mod)
