## Context

This change adds the RAG retrieval-quality eval harness. It lives entirely in `backend/evals/rag/` and is the sole owner of that directory.

- **Consumes (imports, does not modify):**
  - `backend.config.settings.Settings` (P0) — Claude generator/eval model id (`claude-sonnet-4-5`), OpenAI/Anthropic keys.
  - `backend.db.pool.get_connection()` (P0) — read-only access to `qa_chunks` for golden generation.
  - `backend.contracts.retrieval.RetrievedChunk` / `Citation` (P0) — shape of retrieved chunks (`chunk_id`, `chunk`, `score`, `citation`).
  - `backend.contracts.rag_tool.RagToolOutput` (P0) — return type of `rag_search` (`chunks: list[RetrievedChunk]`).
  - `backend.rag.rag_search(query: str, top_k: int = 10) -> RagToolOutput` (P1) — the pipeline under test; called, never reimplemented.
  - `deepeval` (P0 dependency): `Synthesizer`, `LLMTestCase`, `ContextualRecallMetric` / `ContextualPrecisionMetric` / `ContextualRelevancyMetric`, `evaluate`, and a Claude-backed DeepEval model wrapper.
- **Reference docs:** `docs/rag_guide/2_rag_eval_synthetic_data.md` (Synthesizer), `docs/rag_guide/3_rag_eval.md` (retrieval metrics).
- **Coexists with** P7 `chatbot-multiturn-evals` (`backend/evals/chatbot/`). No shared files. `backend/evals/__init__.py` is owned by P0 and is not touched.

## Goals / Non-Goals

**Goals**
- Generate a synthetic golden set from `qa_chunks` with recorded ground-truth `expected_chunk_ids`.
- Score the real `rag_search` pipeline with the three DeepEval contextual metrics plus a deterministic chunk-id recall.
- One runnable CLI with configurable `top_k` and thresholds; a reproducible printed table + JSON report.
- Smoke-testable offline (stub the model and `rag_search`; no live API or DB in tests).

**Non-Goals**
- Retrieval implementation or tuning (P1).
- Generation-quality metrics — faithfulness, answer-relevancy, GEval (out of scope; retrieval-only here).
- Multi-turn / conversational evals (P7).
- Tracing / observability wiring (P3).
- CI wiring, Confident AI login, or dashboards.

## Decisions

### Golden schema + storage path
- `RagGolden` (Pydantic v2 in `goldens_schema.py`): `input: str`, `expected_output: str`, `context: list[str]`, `expected_chunk_ids: list[int]`, plus optional `metadata: dict` (evolutions / quality scores from the Synthesizer).
- Ground-truth ids: `generate_goldens` synthesizes from `qa_chunks` content grouped by row and stamps each golden with the source `qa_chunks.id`s it was built from, enabling non-LLM chunk-id recall. Because DeepEval's `generate_goldens_from_contexts` takes explicit context lists, we pass one context group per `qa_chunks` row (or small similar-row groups) and keep the id mapping alongside.
- Storage: default `backend/evals/rag/goldens.json` (a JSON array of `RagGolden`). Committed as a regenerable artifact. `goldens_schema.py` provides `dump_goldens(path, goldens)` / `load_goldens(path) -> list[RagGolden]` for a clean generate/evaluate split.

### Metric list + thresholds
- LLM-judged (DeepEval, Claude eval model): `ContextualRecallMetric`, `ContextualPrecisionMetric`, `ContextualRelevancyMetric`. Recall/precision use `expected_output` as ground truth; relevancy is referenceless.
- Deterministic: `chunk_id_recall(golden, retrieved_chunks)` = `len(expected ∩ retrieved_ids) / len(expected)`; aggregate = mean over goldens. No LLM call.
- Default thresholds: `0.7` for each of the three contextual metrics; chunk-id recall is reported (and an optional `--min-chunk-id-recall` gate). All thresholds overridable via CLI flags.
- Default `top_k = 10` (matches `rag_search` default), overridable via `--top-k`.

### Runner interface
- Module `backend/evals/rag/run.py` with `main(argv=None)`, invokable as `python -m backend.evals.rag.run`.
- Subcommands / flags: `--goldens PATH` (default `goldens.json`), `--top-k INT`, `--recall-threshold`, `--precision-threshold`, `--relevancy-threshold`, `--limit N` (evaluate only first N goldens — the smoke subset), `--report PATH` (default `report.json`), and a `generate` mode (`--generate --num-goldens N`) that runs `generate_goldens` first.
- `evaluate_retrieval(goldens, top_k, thresholds, rag_search=rag_search, eval_model=...) -> RagEvalReport`: `rag_search` and the eval model are injected parameters (default to the real ones) so tests can stub them.
- Output: `report.py` renders the aggregate table to stdout and writes `RagEvalReport` (aggregates + per-golden rows + hyperparameters) to JSON.

### How rag_search is invoked
- Imported as `from backend.rag import rag_search` and called per golden: `rag_search(golden.input, top_k=top_k)`. The returned `RagToolOutput.chunks` (`list[RetrievedChunk]`) supply both the DeepEval `retrieval_context` (each `RetrievedChunk.chunk` text) and the ids for chunk-id recall (each `RetrievedChunk.chunk_id`). `rag_search` is passed as an injectable callable so the smoke test substitutes a fake returning a fixed `RagToolOutput` — no DB or OpenAI key needed in tests.

## Risks / Trade-offs

- **Synthesized ground truth is imperfect.** Goldens derived from a chunk may be answerable by sibling chunks, deflating chunk-id recall. Mitigation: treat chunk-id recall as a directional signal alongside LLM-judged recall; allow small similar-row context groups; keep goldens regenerable and inspectable in JSON.
- **LLM-judge cost/nondeterminism.** DeepEval contextual metrics call Claude per golden; scores vary run-to-run. Mitigation: `--limit` for cheap subsets, record model ids + thresholds in the report, and stub the model entirely in tests.
- **DeepEval API surface drift.** Synthesizer/metric signatures may differ by version. Mitigation: isolate all DeepEval calls behind our own functions (`generate_goldens`, `evaluate_retrieval`) and depend on the P0-pinned `deepeval` version; if `deepeval` is absent from the manifest it is a P0 addition, not this change.
- **No live DB/model in CI.** Smoke tests stub `rag_search` and the eval model, so they validate wiring (table produced, recall math correct) but not real retrieval quality — that requires a manual/live run of the CLI. Accepted: the done-condition test is explicitly a stubbed smoke run.
