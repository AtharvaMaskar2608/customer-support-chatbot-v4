## Why

The Choice FinX support agent grounds its answers in hybrid retrieval over `qa_chunks` (P1 `rag_search`). Before that retrieval is trusted in production we must be able to **measure** it: does it surface the right chunks, in the right order, without noise? Hand-curating a test set over ~1,100 rows is slow and misses edge cases, so we generate a synthetic golden set from the knowledge base itself (DeepEval `Synthesizer`, Claude as generator) and then score the real `rag_search` pipeline against it with DeepEval's retrieval metrics plus a hard chunk-id recall check.

This gives us a repeatable, thresholded retrieval-quality report we can re-run whenever a retrieval hyperparameter (top_k, RRF `k`, embedding model, chunk size) changes, so regressions are caught by numbers rather than vibes. Reference: `docs/rag_guide/2_rag_eval_synthetic_data.md` (synthesis) and `docs/rag_guide/3_rag_eval.md` (retrieval metrics).

This change owns `backend/evals/rag/` only. It consumes the frozen P0 contracts and config and calls P1 `backend.rag.rag_search`; it implements no retrieval, no multi-turn chatbot evals (P7), and no tracing (P3).

## What Changes

- Add a **golden-set generator** (`backend/evals/rag/generate_goldens.py`): read `qa_chunks` content via `backend.db.pool.get_connection()`, feed it as contexts to DeepEval's `Synthesizer` (Claude `claude-sonnet-4-5` as the generator model, model id from `backend.config.settings`), and persist query / expected-context / source-chunk-id goldens to a versioned JSON file under `backend/evals/rag/`.
- Define a stable on-disk **golden schema** (`backend/evals/rag/goldens_schema.py`): each golden carries `input` (query), `expected_output` (expected answer/context text), `context` (source chunk text list), and `expected_chunk_ids` (the `qa_chunks.id`s the query was synthesized from) — the ground truth for chunk-id recall.
- Add a **retrieval-quality evaluator** (`backend/evals/rag/evaluate_retrieval.py`): for each golden, call `rag_search(query, top_k)`, build a DeepEval `LLMTestCase` (`retrieval_context` = returned chunk texts), score with `ContextualRecallMetric` / `ContextualPrecisionMetric` / `ContextualRelevancyMetric` (Claude as the eval model), and compute a **chunk-id recall** metric (fraction of `expected_chunk_ids` present in the retrieved chunk ids).
- Emit a **reproducible metrics report**: a printed metrics table (per-metric mean score + chunk-id recall) and a machine-readable JSON report file under `backend/evals/rag/`, with the run's hyperparameters (top_k, thresholds, models) recorded.
- Provide a **runnable entrypoint** (`python -m backend.evals.rag.run` / `main()` CLI) with configurable `top_k`, per-metric thresholds, golden-file path, and golden subset size.
- Add smoke tests (`backend/evals/rag/tests/`) that run the evaluator over a tiny golden fixture with model/`rag_search` calls stubbed, asserting the metrics table is produced.
- NOT in scope: retrieval implementation (P1), multi-turn chatbot evals (P7), tracing setup (P3), generation-quality metrics (faithfulness/answer-relevancy), or any change to `backend/evals/__init__.py` (owned by P0) or `backend/evals/chatbot/` (owned by P7).

## Capabilities

### New Capabilities
- `rag-evals`: synthetic golden-set generation from `qa_chunks` and thresholded retrieval-quality evaluation (contextual recall / precision / relevancy + chunk-id recall) of the P1 `rag_search` pipeline, with a runnable CLI and a reproducible metrics report.

### Modified Capabilities
<!-- None — this change only adds a new capability inside backend/evals/rag/. -->

## Impact

- New files only, all inside the owned directory `backend/evals/rag/`:
  - `backend/evals/rag/__init__.py` — package marker for the rag evals subpackage.
  - `backend/evals/rag/goldens_schema.py` — `RagGolden` model + JSON load/dump helpers (the golden schema).
  - `backend/evals/rag/generate_goldens.py` — `generate_goldens(...)` synthesizer over `qa_chunks` content.
  - `backend/evals/rag/evaluate_retrieval.py` — `evaluate_retrieval(...)` + `chunk_id_recall(...)` metric.
  - `backend/evals/rag/report.py` — metrics-table formatting + JSON report writer.
  - `backend/evals/rag/run.py` — CLI entrypoint (`main()`) wiring generation/evaluation with configurable `top_k` + thresholds.
  - `backend/evals/rag/goldens.json` — generated golden set (committed artifact; regenerable).
  - `backend/evals/rag/tests/__init__.py`, `backend/evals/rag/tests/test_evaluate_retrieval.py`, `backend/evals/rag/tests/fixtures/tiny_goldens.json` — smoke tests + tiny fixture.
- Imports only (does not modify): `backend.config.settings.Settings`, `backend.db.pool.get_connection`, `backend.contracts.retrieval` (`RetrievedChunk`, `Citation`), `backend.contracts.rag_tool` (`RagToolOutput`), and `backend.rag.rag_search` (P1).
- Does NOT touch `backend/evals/__init__.py` (P0), `backend/evals/chatbot/` (P7), `pyproject.toml`, `.env`, or any root config. `deepeval` and `anthropic` are already declared by P0 (foundations-and-contracts); if `deepeval` were missing from the manifest, that is a P0 addition, not this change.
- Depends on P0 `foundations-and-contracts` (contracts, config, DB helper) and P1 `rag-hybrid-retrieval` (`rag_search`) being merged to `main` first. Coexists with P7 `chatbot-multiturn-evals`; no shared files.
