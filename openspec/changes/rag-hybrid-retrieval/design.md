## Context

This change (P1 `rag-hybrid-retrieval`) implements the agent's RAG tool as hybrid retrieval over the pre-populated `qa_chunks` table. It is one of eight parallel changes and owns exactly one directory: `backend/rag/`.

Grounding facts (confirmed, from P0):
- DB: Postgres `localhost:5433`, db `customer_support_chatbot`, user `atharva`, table `qa_chunks`. Columns: `id bigint`, `topic`, `section`, `question`, `answer`, `answer_source`, `tat`, `source_sheet`, `source_row int`, `chunk text`, `embedding vector(3072)`, `fts tsvector` (generated from `chunk`; GIN index `qa_chunks_fts_gin`). Embeddings + FTS already populated — **no migration, no ingestion**.
- ~1,100 rows, so exact/sequential scan for vector search (no IVFFlat/HNSW). Per `docs/rag_guide/1_building_rag_pt1.md`, small tables → sequential scan (100% recall, O(n) is fine at this size). Also 3072 dims exceeds the 2000-dim cap for ANN indexes, which independently forces sequential scan.
- Embeddings: OpenAI `text-embedding-3-large`, full 3072 dims (no Matryoshka truncation).

Files this change touches (all under `backend/rag/`):
- `backend/rag/__init__.py` — re-export `rag_search`.
- `backend/rag/search.py` — `rag_search` + `embed_query`, `vector_search`, `fts_search`, `rrf_fuse`, and a small `_row_to_chunk` mapper.
- `backend/rag/tests/__init__.py`, `backend/rag/tests/test_rag_search.py`.

Imported (not modified): `backend.config.settings.Settings`; `backend.db.pool.get_connection`; `backend.contracts.retrieval.{Citation, RetrievedChunk}`; `backend.contracts.rag_tool.{RagToolInput, RagToolOutput}`; optionally `backend.tracing`.

Dependencies by change name: hard-depends on P0 `foundations-and-contracts`; soft-depends on P3 `tracing-foundation`.

## Goals / Non-Goals

**Goals:**
- One tested public entrypoint `rag_search(query, top_k=10) -> RagToolOutput`.
- Hybrid retrieval: cosine vector search + `websearch_to_tsquery`/`ts_rank` FTS, fused by RRF.
- Every returned chunk is citable: fully-populated `Citation` sourced from the `qa_chunks` row.
- Runnable with or without P3 tracing installed.

**Non-Goals:**
- Agent loop / tool dispatch (P4), evals (P6), tracing setup itself (P3), API/SSE and frontend (P5/P8).
- No schema changes, no ingestion, no ANN index, no dependency-manifest edits.
- No query rewriting, reranking model, or Matryoshka truncation in this change.

## Decisions

### Public entrypoint and helpers

```python
# backend/rag/search.py
from backend.config.settings import Settings
from backend.db.pool import get_connection
from backend.contracts.retrieval import Citation, RetrievedChunk
from backend.contracts.rag_tool import RagToolInput, RagToolOutput

RRF_K: int = 60                 # RRF smoothing constant
CANDIDATE_LIMIT: int = 50       # rows pulled from each retriever before fusion

def rag_search(query: str, top_k: int = 10) -> RagToolOutput: ...
def embed_query(query: str) -> list[float]: ...                       # len == 3072
def vector_search(embedding: list[float], limit: int = CANDIDATE_LIMIT) -> list[dict]: ...
def fts_search(query: str, limit: int = CANDIDATE_LIMIT) -> list[dict]: ...
def rrf_fuse(vector_rows: list[dict], fts_rows: list[dict], top_k: int, k: int = RRF_K) -> list[tuple[dict, float]]: ...
def _row_to_chunk(row: dict, score: float) -> RetrievedChunk: ...
```

**Contract of `rag_search`:** validates input via `RagToolInput(query=query, top_k=top_k)`; if `query` is blank it returns `RagToolOutput(chunks=[])`. Otherwise: `emb = embed_query(query)`; `v = vector_search(emb)`; `f = fts_search(query)`; `fused = rrf_fuse(v, f, top_k)`; returns `RagToolOutput(chunks=[_row_to_chunk(r, s) for r, s in fused])`.

**Row dicts** returned by both retrievers carry the same key set so fusion and mapping are uniform:
`{id, topic, section, question, answer, answer_source, tat, source_row, chunk}`. Ranking within each retriever is by list position (1-based) after the SQL `ORDER BY`, so RRF does not need the raw distance/rank scores — only ordinal position.

### Embedding — `embed_query`

Uses the OpenAI client configured from `Settings` (`EMBEDDING_MODEL=text-embedding-3-large`, `EMBEDDING_API_KEY`/`OPENAI_API_KEY`). Full dimensions (do NOT pass `dimensions=`), so the returned vector length is 3072, matching `qa_chunks.embedding`.

```python
client = OpenAI(api_key=settings.embedding_api_key)
resp = client.embeddings.create(model=settings.embedding_model, input=query)
return resp.data[0].embedding   # 3072 floats
```

### Vector search SQL — `vector_search`

Exact/sequential scan; cosine distance via `<=>`. The embedding is registered as a pgvector param by `get_connection()` (pgvector adapter registered per P0). Lower distance = more similar, so `ORDER BY ... ASC`.

```sql
SELECT id, topic, section, question, answer, answer_source, tat, source_row, chunk,
       embedding <=> %(emb)s AS distance
FROM qa_chunks
ORDER BY embedding <=> %(emb)s ASC
LIMIT %(limit)s;
```
Bind `%(emb)s` to the query vector (pgvector adapts `list[float]` -> `vector`), `%(limit)s` to `CANDIDATE_LIMIT`. Rank = row ordinal (1..N) in the returned order.

### Full-text search SQL — `fts_search`

Lexical match on the generated `fts` tsvector (GIN index `qa_chunks_fts_gin`), scored with `ts_rank`. `websearch_to_tsquery` tolerates natural phrasing and empty results.

```sql
SELECT id, topic, section, question, answer, answer_source, tat, source_row, chunk,
       ts_rank(fts, websearch_to_tsquery('english', %(q)s)) AS rank
FROM qa_chunks
WHERE fts @@ websearch_to_tsquery('english', %(q)s)
ORDER BY rank DESC
LIMIT %(limit)s;
```
Bind `%(q)s` to the raw query string, `%(limit)s` to `CANDIDATE_LIMIT`. Rank = row ordinal in the returned order. An all-stopword/blank query yields an empty tsquery and zero rows — handled as empty, not an error.

### RRF fusion — `rrf_fuse`

Reciprocal Rank Fusion combines the two ordinal rankings without needing comparable raw scores (cosine distance vs. ts_rank are not on the same scale, which is exactly why RRF is chosen over score normalization).

```python
def rrf_fuse(vector_rows, fts_rows, top_k, k=RRF_K):
    scores: dict[int, float] = {}
    rows_by_id: dict[int, dict] = {}
    for ranked in (vector_rows, fts_rows):
        for rank, row in enumerate(ranked, start=1):   # 1-based
            cid = row["id"]
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
            rows_by_id.setdefault(cid, row)
    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [(rows_by_id[cid], s) for cid, s in ordered[:top_k]]
```
A chunk present in both lists accumulates two reciprocal-rank terms, so it outranks equally-placed single-list chunks. Dedup is inherent (keyed by `id`). The fused float is written to `RetrievedChunk.score`.

### Row → contract mapping — `_row_to_chunk`

```python
def _row_to_chunk(row, score):
    citation = Citation(
        chunk_id=row["id"], topic=row["topic"], section=row["section"],
        question=row["question"], answer_source=row["answer_source"],
        source_row=row["source_row"],
    )
    return RetrievedChunk(
        chunk_id=row["id"], chunk=row["chunk"], question=row["question"],
        answer=row["answer"], tat=row["tat"], score=score, citation=citation,
    )
```
`chunk_id == citation.chunk_id == qa_chunks.id` guarantees citability.

### Optional tracing (P3 soft dependency)

```python
try:
    from backend.tracing import observe          # P3 decorator
except Exception:                                # module absent -> no-op
    def observe(*a, **k):
        def deco(fn): return fn
        return deco if (a and callable(a[0]) is False) else (a[0] if a else deco)
```
Public functions are decorated with `@observe(...)`; the fallback makes decoration a pass-through so nothing breaks without P3. The exact P3 decorator name is confirmed against `backend.tracing` at integration; the fallback shields import failure regardless.

## Risks / Trade-offs

- **Sequential scan latency**: O(n) over ~1,100 rows × 3072 dims is well within interactive latency; revisit with an index only if the KB grows past ~100k rows (and note 3072 dims exceeds the ANN 2000-dim cap, so growth would require Matryoshka truncation first). Accepted for this size.
- **RRF constant `k=60`**: standard default; controls how quickly rank contribution decays. Exposed as a parameter so P6 evals can tune it without code changes.
- **`CANDIDATE_LIMIT=50` per retriever**: large enough that a strong hit in either list survives to fusion for top_k≤10; bounded so fusion stays cheap. Adjustable constant.
- **Distinct score scales**: cosine distance and `ts_rank` are not comparable; RRF over ordinal ranks sidesteps normalization entirely — deliberate.
- **P3 decorator name drift**: if P3 names its decorator differently than assumed, only the import line changes; the no-op fallback guarantees the rag layer never hard-fails on tracing.
- **`openai` dependency ownership**: this change imports the OpenAI client but does not edit the manifest. If `openai` is not present in P0's `pyproject.toml`, that is a P0 addition to flag — not something this change may modify.
