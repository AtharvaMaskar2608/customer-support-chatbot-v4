## 1. Package scaffold

- [x] 1.1 Create `backend/rag/__init__.py` re-exporting `rag_search` (so callers import `from backend.rag import rag_search`)
- [x] 1.2 Create `backend/rag/search.py` module skeleton importing P0 contracts (`Citation`, `RetrievedChunk`, `RagToolInput`, `RagToolOutput`), `Settings`, and `get_connection`; define constants `RRF_K = 60` and `CANDIDATE_LIMIT = 50`
- [x] 1.3 Add the optional-tracing shim in `search.py`: `try: from backend.tracing import observe` with a no-op fallback so the module imports without P3

## 2. Query embedding

- [x] 2.1 Implement `embed_query(query: str) -> list[float]` using the OpenAI client with `settings.embedding_model` (`text-embedding-3-large`) at full dims (do NOT pass `dimensions=`); assert nothing is hardcoded (model/key/dims come from config)
- [x] 2.2 Guarantee the returned vector length is 3072 to match `qa_chunks.embedding`

## 3. Retrievers

- [x] 3.1 Implement `vector_search(embedding, limit=CANDIDATE_LIMIT) -> list[dict]`: cosine `<=>` exact/sequential scan, `ORDER BY embedding <=> %(emb)s ASC LIMIT %(limit)s`, selecting `id, topic, section, question, answer, answer_source, tat, source_row, chunk`; read-only conn from `get_connection()`
- [x] 3.2 Implement `fts_search(query, limit=CANDIDATE_LIMIT) -> list[dict]`: `WHERE fts @@ websearch_to_tsquery('english', %(q)s) ORDER BY ts_rank(...) DESC LIMIT %(limit)s`, same column set; empty tsquery / no match returns `[]` (no exception)

## 4. Fusion and mapping

- [x] 4.1 Implement `rrf_fuse(vector_rows, fts_rows, top_k, k=RRF_K) -> list[tuple[dict, float]]`: sum `1/(k+rank)` (1-based rank) across both lists, dedup by `id`, sort by fused score desc, slice to `top_k`
- [x] 4.2 Implement `_row_to_chunk(row, score) -> RetrievedChunk` populating a full `Citation` (`chunk_id = row["id"]`) and setting `chunk_id == citation.chunk_id` and `score = fused RRF score`
- [x] 4.3 Implement `rag_search(query, top_k=10) -> RagToolOutput`: validate via `RagToolInput`; blank query -> empty output; else embed -> vector_search -> fts_search -> rrf_fuse -> map -> `RagToolOutput(chunks=[...])`

## 5. Tests (DB fixture)

- [x] 5.1 Create `backend/rag/tests/__init__.py` and `backend/rag/tests/test_rag_search.py` with a DB fixture using `get_connection()` (skip if DB unreachable) and a stubbed/monkeypatched `embed_query` for deterministic vector ranking
- [x] 5.2 Test: a sample KB query returns `RagToolOutput` with ≥1 chunk, `len(chunks) <= top_k`, and chunks ordered by descending `score`
- [x] 5.3 Test: RRF ordering — a chunk ranked in both vector and FTS lists outranks a single-list chunk; duplicate `chunk_id` across lists appears once
- [x] 5.4 Test: citation population — every returned chunk has `citation.chunk_id == chunk_id == qa_chunks.id` with `topic/section/question/answer_source/source_row` populated
- [x] 5.5 Test: no-match query returns empty `chunks` and raises nothing; module imports with `backend.tracing` absent

## 6. Validation & done

- [x] 6.1 Run `openspec validate rag-hybrid-retrieval --strict` — must print "is valid"
- [x] 6.2 **DONE CONDITION:** given a KB query, `rag_search` returns ≥1 cited chunk with a fully-populated `Citation` (`citation.chunk_id == qa_chunks.id`), results ordered by fused RRF score, and the module runs without P3 tracing. **TEST COMMAND:** `pytest backend/rag`
