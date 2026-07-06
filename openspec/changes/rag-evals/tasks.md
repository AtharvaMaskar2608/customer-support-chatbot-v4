## 1. Golden schema

- [ ] 1.1 Add `backend/evals/rag/__init__.py` (subpackage marker; do NOT touch `backend/evals/__init__.py`, owned by P0).
- [ ] 1.2 Define `RagGolden` (Pydantic v2) in `backend/evals/rag/goldens_schema.py` with `input`, `expected_output`, `context: list[str]`, `expected_chunk_ids: list[int]`, optional `metadata`.
  - Contract: `RagGolden` model; `dump_goldens(path: str, goldens: list[RagGolden]) -> None`; `load_goldens(path: str) -> list[RagGolden]`. Round-trips through JSON without loss.

## 2. Golden-set generation from qa_chunks

- [ ] 2.1 Implement `generate_goldens(num_goldens: int, out_path: str, *, settings=..., conn_factory=get_connection) -> list[RagGolden]` in `backend/evals/rag/generate_goldens.py`.
  - Contract: reads `qa_chunks` (id + chunk text) via `backend.db.pool.get_connection()`; builds per-row (or small similar-row) context groups; runs DeepEval `Synthesizer` with Claude (`claude-sonnet-4-5` from `Settings`, key from config) as generator; stamps each golden's `expected_chunk_ids` with source `qa_chunks.id`s; writes JSON to `out_path` (default `backend/evals/rag/goldens.json`) via `dump_goldens`.
  - No hardcoded model name / API key.

## 3. Retrieval-quality evaluation

- [ ] 3.1 Implement `chunk_id_recall(golden: RagGolden, retrieved: list[RetrievedChunk]) -> float` in `backend/evals/rag/evaluate_retrieval.py`.
  - Contract: `len(set(golden.expected_chunk_ids) & {c.chunk_id for c in retrieved}) / len(golden.expected_chunk_ids)`; no LLM call.
- [ ] 3.2 Implement `evaluate_retrieval(goldens, *, top_k=10, recall_threshold=0.7, precision_threshold=0.7, relevancy_threshold=0.7, rag_search=rag_search, eval_model=...) -> RagEvalReport`.
  - Contract: per golden calls `rag_search(golden.input, top_k=top_k)` → `RagToolOutput`; builds DeepEval `LLMTestCase(input, retrieval_context=[c.chunk for c in chunks], expected_output=golden.expected_output)`; scores `ContextualRecall/Precision/RelevancyMetric` (Claude eval model, given thresholds); records per-golden metric scores + `chunk_id_recall`. `rag_search` and `eval_model` are injectable for tests.

## 4. Report + runner

- [ ] 4.1 Define `RagEvalReport` + `format_table(report) -> str` + `write_report(path, report)` in `backend/evals/rag/report.py`.
  - Contract: `RagEvalReport` holds aggregates (mean recall/precision/relevancy + mean chunk-id recall), per-golden rows, and hyperparameters (`top_k`, thresholds, model ids). `format_table` renders the aggregate table; `write_report` writes JSON under `backend/evals/rag/`.
- [ ] 4.2 Implement `main(argv=None)` in `backend/evals/rag/run.py`, runnable as `python -m backend.evals.rag.run`.
  - Contract: flags `--goldens`, `--top-k`, `--recall-threshold`, `--precision-threshold`, `--relevancy-threshold`, `--limit`, `--report`, and `--generate --num-goldens N`; loads goldens (or generates), calls `evaluate_retrieval`, prints `format_table`, calls `write_report`.

## 5. Smoke tests

- [ ] 5.1 Add `backend/evals/rag/tests/__init__.py` and `backend/evals/rag/tests/fixtures/tiny_goldens.json` (2–3 hand-written goldens with known `expected_chunk_ids`).
- [ ] 5.2 Add `backend/evals/rag/tests/test_evaluate_retrieval.py`: unit-test `chunk_id_recall` math (0.5 / 1.0 cases) and run `evaluate_retrieval` over the tiny fixture with a stubbed `rag_search` (returns fixed `RagToolOutput`) and a stubbed `eval_model` (returns fixed scores), asserting the aggregate table is produced and a report is written.

## 6. DONE

- [ ] 6.1 DONE CONDITION: `python -m backend.evals.rag.run --goldens backend/evals/rag/tests/fixtures/tiny_goldens.json --limit 3` executes over the tiny golden subset and prints a metrics table (Contextual Recall / Precision / Relevancy + chunk-id recall), and the smoke test passes with model + `rag_search` calls stubbed.
  - TEST COMMAND: `pytest backend/evals/rag`
