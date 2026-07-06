## Why

The Choice FinX support agent must answer knowledge-base questions with **citable** grounding, not free-form generation. The `qa_chunks` table already carries OpenAI `text-embedding-3-large` (3072-d) embeddings and a generated `fts` tsvector. To turn that into reliable retrieval we need a single, tested entrypoint that runs both semantic (vector) and lexical (full-text) search and fuses them, so the agent (P4) can call one RAG tool and render citation cards. Vector-only search misses exact-keyword hits (product names, ticket IDs, TAT phrasing); FTS-only search misses paraphrases. Hybrid retrieval fused with Reciprocal Rank Fusion (RRF) captures both, per `docs/rag_guide/1_building_rag_pt1.md`.

This change owns `backend/rag/` only. It consumes the frozen P0 contracts (`RetrievedChunk`, `Citation`, `RagToolInput`, `RagToolOutput`) and the P0 config + DB helper. It does not touch schema, dependencies, or any other package.

## What Changes

- Implement the public entrypoint `rag_search(query, top_k=10) -> RagToolOutput` in `backend/rag/`, backed by four internal helpers: `embed_query`, `vector_search`, `fts_search`, `rrf_fuse`.
- `embed_query`: embed the query with OpenAI `text-embedding-3-large` at full 3072 dims (model + key from `backend.config.settings`).
- `vector_search`: cosine-distance ranking over `qa_chunks.embedding` via pgvector `<=>`, exact/sequential scan (no ANN index), read-only connection from `backend.db.pool.get_connection()`.
- `fts_search`: lexical ranking over `qa_chunks.fts` using `websearch_to_tsquery('english', query)` and `ts_rank`.
- `rrf_fuse`: combine the two ranked candidate lists by Reciprocal Rank Fusion into a single ordered list, dedup by `chunk_id`, return top_k.
- Map each surviving `qa_chunks` row to a `RetrievedChunk` with a fully populated `Citation` (`chunk_id = qa_chunks.id`), so every RAG answer is citable, and wrap them in `RagToolOutput`.
- Consume (optional) tracing decorators from P3 `backend.tracing` when present, but keep every rag function runnable without P3 installed.

## Capabilities

### New Capabilities
- `rag-hybrid-retrieval`: hybrid (vector + full-text) retrieval over `qa_chunks`, fused with Reciprocal Rank Fusion, exposed as `rag_search(query, top_k)` returning citation-populated `RetrievedChunk`s as the agent's RAG tool.

### Modified Capabilities
<!-- None — this change only adds a new capability inside backend/rag/. -->

## Impact

- New files only, all inside the owned directory `backend/rag/`:
  - `backend/rag/__init__.py` — re-export `rag_search`.
  - `backend/rag/search.py` — `rag_search` + helpers `embed_query`, `vector_search`, `fts_search`, `rrf_fuse`.
  - `backend/rag/tests/__init__.py`
  - `backend/rag/tests/test_rag_search.py` — sample-query, RRF-ordering, citation-population tests with a DB fixture.
- Imports only (does not modify): `backend.config.settings.Settings`, `backend.db.pool.get_connection`, `backend.contracts.retrieval` (`Citation`, `RetrievedChunk`), `backend.contracts.rag_tool` (`RagToolInput`, `RagToolOutput`), and optionally `backend.tracing`.
- No changes to `pyproject.toml`, `.env`, root config, or DB schema (owned by P0). The `openai` client dependency is already declared by P0; no new dependency is introduced. If the reviewer finds `openai` missing from the manifest, that is a P0 addition, not this change.
- Depends on P0 `foundations-and-contracts` (contracts, config, DB helper) being merged to `main` first. Soft-depends on P3 `tracing-foundation` for decorators; degrades gracefully without it.
