# rag-hybrid-retrieval Specification

## Purpose
TBD - created by archiving change cho-34-rag-hybrid-retrieval. Update Purpose after archive.
## Requirements
### Requirement: Hybrid RAG search entrypoint

The system SHALL expose a single public entrypoint `rag_search(query: str, top_k: int = 10) -> RagToolOutput` that runs both vector search and full-text search over `qa_chunks`, fuses the results with Reciprocal Rank Fusion, and returns at most `top_k` `RetrievedChunk`s ordered by descending fused score. The function SHALL accept the same shape as `RagToolInput` (a `query` string and an optional `top_k`) and MUST return a valid `RagToolOutput`.

#### Scenario: Knowledge-base query returns fused ranked chunks

- **WHEN** `rag_search` is called with a knowledge-base question that has matching content in `qa_chunks`
- **THEN** it returns a `RagToolOutput` whose `chunks` list is non-empty, contains at most `top_k` items, and is ordered by descending fused RRF `score`

#### Scenario: top_k bounds the result count

- **WHEN** `rag_search(query, top_k=k)` is called and more than `k` candidates match
- **THEN** the returned `chunks` list contains exactly `k` items and no more

#### Scenario: No-match query returns an empty result, not an error

- **WHEN** `rag_search` is called with a query that matches no rows in either vector or full-text search
- **THEN** it returns a `RagToolOutput` with an empty `chunks` list and raises no exception

### Requirement: Query embedding with the configured model

The system SHALL embed the incoming query using the OpenAI embedding model named by `backend.config.settings` (`text-embedding-3-large`) at its full 3072 dimensions, using the API key from configuration, and MUST NOT hardcode the model name, dimension count, or API key.

#### Scenario: Query embedded at full dimensions

- **WHEN** `embed_query` is called with a non-empty query
- **THEN** it returns a single 3072-dimension float vector produced by the configured `EMBEDDING_MODEL`

### Requirement: Exact cosine vector search over qa_chunks

The system SHALL rank candidate chunks by cosine distance between the query embedding and `qa_chunks.embedding` using pgvector's `<=>` operator over a read-only connection from `backend.db.pool.get_connection()`, relying on an exact/sequential scan (no ANN index), and SHALL convert cosine distance to a similarity-ordered rank.

#### Scenario: Vector search ranks by cosine similarity

- **WHEN** `vector_search(embedding, limit)` is called
- **THEN** it returns up to `limit` rows ordered by ascending cosine distance (`embedding <=> query`), each carrying its `qa_chunks.id` and the columns needed to build a `RetrievedChunk` and `Citation`

### Requirement: Full-text keyword search over qa_chunks.fts

The system SHALL run lexical search against the generated `qa_chunks.fts` tsvector using `websearch_to_tsquery('english', query)` and rank matches with `ts_rank`, returning results in descending rank order.

#### Scenario: Full-text search matches keywords

- **WHEN** `fts_search(query, limit)` is called with a query whose keywords appear in `qa_chunks.chunk`
- **THEN** it returns up to `limit` matching rows ordered by descending `ts_rank`, each carrying its `qa_chunks.id` and the columns needed to build a `RetrievedChunk` and `Citation`

### Requirement: Reciprocal Rank Fusion of the two result sets

The system SHALL fuse the vector and full-text ranked lists using Reciprocal Rank Fusion, computing each chunk's fused score as the sum over both lists of `1 / (k + rank)` (rank 1-based; `k` a fixed constant, default 60), deduplicating by `chunk_id`, and ordering the merged list by descending fused score. The fused score SHALL be written to `RetrievedChunk.score`.

#### Scenario: A chunk ranked highly by both retrievers outranks single-list hits

- **WHEN** a chunk appears near the top of both the vector and full-text lists and another chunk appears in only one list
- **THEN** after `rrf_fuse` the chunk present in both lists has a strictly higher fused `score` and is ordered ahead of the single-list chunk

#### Scenario: Duplicates across lists are merged once

- **WHEN** the same `chunk_id` appears in both the vector and full-text result lists
- **THEN** it appears exactly once in the fused output with a score equal to the sum of its reciprocal-rank contributions from both lists

### Requirement: Every returned chunk is citable

The system SHALL populate a fully-formed `Citation` for each returned `RetrievedChunk`, sourced from the originating `qa_chunks` row, with `citation.chunk_id` equal to `qa_chunks.id` and `topic`, `section`, `question`, `answer_source`, and `source_row` copied from that row. `RetrievedChunk.chunk_id` MUST equal `citation.chunk_id`, and `chunk`, `question`, `answer`, and `tat` MUST be taken from the same row.

#### Scenario: Returned chunk carries populated citation provenance

- **WHEN** `rag_search` returns a `RetrievedChunk`
- **THEN** its `citation.chunk_id` equals the source `qa_chunks.id`, its `chunk_id` equals `citation.chunk_id`, and the citation's `topic`, `section`, `question`, `answer_source`, and `source_row` are populated from the same row

### Requirement: Optional tracing without a hard dependency

The system SHALL use tracing decorators from `backend.tracing` (P3) when that module is importable, and SHALL remain fully functional when it is absent by falling back to a no-op, so the rag functions run without the tracing foundation installed.

#### Scenario: RAG runs without the tracing module

- **WHEN** `backend.tracing` is not importable in the environment
- **THEN** `rag_search` and its helpers still execute and return results, using a no-op tracing fallback and raising no ImportError

