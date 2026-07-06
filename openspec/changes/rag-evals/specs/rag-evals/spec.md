## ADDED Requirements

### Requirement: Synthetic golden-set generation from qa_chunks

The system SHALL generate a synthetic golden set from the `qa_chunks` knowledge base using DeepEval's `Synthesizer` with Claude (`claude-sonnet-4-5`, model id from `backend.config.settings`) as the generator model, reading chunk content over a read-only connection from `backend.db.pool.get_connection()`. Each generated golden MUST record the originating `qa_chunks.id`s as `expected_chunk_ids`, and the golden set MUST be persisted to a JSON file under `backend/evals/rag/`. The generator SHALL accept a configurable cap on how many chunks/goldens to synthesize so a small subset can be produced for smoke runs, and MUST NOT hardcode the generator model name or API key.

#### Scenario: Goldens generated from knowledge-base content

- **WHEN** `generate_goldens` runs against `qa_chunks` content with a requested golden count
- **THEN** it produces goldens each carrying an `input` query, expected-context text, and a non-empty `expected_chunk_ids` list referencing the source `qa_chunks.id`s, and writes them to the configured JSON path under `backend/evals/rag/`

#### Scenario: Generation uses the configured Claude model, not a hardcoded one

- **WHEN** the synthesizer is constructed
- **THEN** its generator model id is taken from `backend.config.settings` (`claude-sonnet-4-5`) and the API key from configuration, with no hardcoded model name or key

### Requirement: Persisted golden schema

The system SHALL define and persist each golden in a stable schema with at least the fields `input` (the query string), `expected_output` (expected answer/context text), `context` (list of source chunk texts), and `expected_chunk_ids` (list of `qa_chunks.id`). The evaluator SHALL be able to load this file back into the same schema without loss, so generation and evaluation are decoupled and re-runnable.

#### Scenario: Golden round-trips through disk

- **WHEN** a golden set is written to JSON and then loaded by the evaluator
- **THEN** each loaded golden exposes the same `input`, `expected_output`, `context`, and `expected_chunk_ids` values that were written

### Requirement: Retrieval-quality metrics computed against rag_search

The system SHALL evaluate retrieval quality by invoking the P1 pipeline `backend.rag.rag_search(query, top_k)` for each golden's `input`, constructing a DeepEval `LLMTestCase` whose `retrieval_context` is the text of the returned `RetrievedChunk`s and whose `expected_output` is the golden's expected context, and scoring it with `ContextualRecallMetric`, `ContextualPrecisionMetric`, and `ContextualRelevancyMetric` (Claude as the evaluation model). Each metric SHALL use a configurable passing threshold, and `top_k` SHALL be configurable and passed through to `rag_search`.

#### Scenario: Each golden is scored against the real retrieval pipeline

- **WHEN** the evaluator runs over the golden set with a given `top_k`
- **THEN** for every golden it calls `rag_search(golden.input, top_k)`, builds an `LLMTestCase` from the returned chunks, and records a Contextual Recall, Contextual Precision, and Contextual Relevancy score

#### Scenario: Thresholds and top_k are configurable

- **WHEN** the runner is invoked with a custom `top_k` and custom per-metric thresholds
- **THEN** those values are applied — `rag_search` receives the given `top_k` and each DeepEval metric is constructed with the given threshold — rather than fixed defaults

### Requirement: Chunk-id recall metric

The system SHALL compute a chunk-id recall metric independent of the LLM-judged metrics, defined as the fraction of a golden's `expected_chunk_ids` that appear among the `chunk_id`s returned by `rag_search` for that golden, aggregated (mean) across the golden set. This metric MUST be derived from the retrieved `RetrievedChunk.chunk_id`s and the golden ground-truth ids, with no LLM call.

#### Scenario: Chunk-id recall reflects retrieved ids

- **WHEN** a golden has `expected_chunk_ids = [A, B]` and `rag_search` returns chunks whose ids include `A` but not `B`
- **THEN** that golden's chunk-id recall is 0.5, and the reported chunk-id recall is the mean of the per-golden values across the set

#### Scenario: Perfect retrieval yields recall 1.0

- **WHEN** every golden's `expected_chunk_ids` are all present in the ids returned by `rag_search`
- **THEN** the aggregated chunk-id recall equals 1.0

### Requirement: Reproducible metrics report and runnable entrypoint

The system SHALL expose a runnable entrypoint (a `main()` CLI invokable as `python -m backend.evals.rag.run`) that loads a golden set, runs the retrieval-quality evaluation, prints a metrics table (mean Contextual Recall, Precision, Relevancy and chunk-id recall), and writes a machine-readable JSON report file under `backend/evals/rag/`. The report SHALL record the run's hyperparameters (`top_k`, per-metric thresholds, generator/eval model ids) so results are reproducible and comparable across runs.

#### Scenario: Runner prints a metrics table and writes a report

- **WHEN** `python -m backend.evals.rag.run` is executed against a golden set
- **THEN** it prints a table with mean Contextual Recall, Contextual Precision, Contextual Relevancy, and chunk-id recall, and writes a JSON report file under `backend/evals/rag/` containing those aggregates plus the `top_k`, thresholds, and model ids used

#### Scenario: Report captures hyperparameters for reproducibility

- **WHEN** two evaluation runs use different `top_k` values
- **THEN** each written report records its own `top_k`, thresholds, and model ids, so the two runs are distinguishable and reproducible from the report alone
