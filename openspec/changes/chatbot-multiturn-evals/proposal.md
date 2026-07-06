## Why

The Choice FinX support chatbot is an end-to-end agentic system (P4 `agent_reply`) whose quality only shows up **across a whole conversation**: does it retain context between turns, actually complete the user's goal, hold the SEBI no-advice and scope guardrails when the user pushes back over several turns, and behave consistently? Single-turn scoring cannot see any of that. A fixed input/output test set cannot either, because each user message depends on the assistant's previous reply.

The industry approach (`docs/chatbot_eval/1_multi_turn_eval.md`, `2_multi_turn_eval_metrics.md`, `3_multi_turn_simulation.md`) is **scenario-based simulation**: an LLM role-plays the user against our *real* agent to generate reproducible multi-turn conversations, which are then scored with conversation-level metrics. This change owns that harness — a DeepEval `ConversationSimulator` driven by a `model_callback` that wraps P4 `agent_reply`, a versioned set of `ConversationalGolden` scenarios (including deliberate SEBI-advice, off-topic-hijack, and clarifying-question guardrail probes), and multi-turn metric scoring pushed to Confident AI. It measures behaviour; it implements neither the agent (P4) nor retrieval-level evals (P6).

This change owns `backend/evals/chatbot/` only. It imports the frozen P0 contracts and calls P4 `backend.agent.agent_reply`; it touches no other package.

## What Changes

- Add an async **`model_callback(input, turns, thread_id) -> Turn`** (`backend/evals/chatbot/model_callback.py`) that adapts P4 `agent_reply`: it converts the simulator's `turns` list into the `history: list[dict]` shape `agent_reply` expects, calls `agent_reply(history, session, thread_id)`, and maps the resulting `AgentReply` into a DeepEval `Turn` — `content` from `AgentReply.content`, `retrieval_context` from the raw retrieved chunk text carried on `AgentReply.citations`, and `tools_called` from `AgentReply.tools_called` (each `ToolCallRecord` mapped to a DeepEval `ToolCall`). A test `SessionContext` is sourced from configuration (no session token in code).
- Add a versioned, **configurable golden set** of **≥20 `ConversationalGolden`s** (`backend/evals/chatbot/goldens.py` + optional on-disk `goldens.json` override), each with `scenario`, `expected_outcome`, `user_description`, and a `category` tag. Categories cover normal KB question paths, report-tool goal paths (CML report / contract note), context-retention paths, and — mandatory — **guardrail probes**: SEBI advice-seeking (user demands an investment opinion/recommendation and pushes back), off-topic hijack (user steers to non-Choice-FinX topics), and clarifying-question paths (ambiguous request that should trigger a clarifying question before an answer).
- Add **simulation** (`backend/evals/chatbot/simulate.py`): build a `ConversationSimulator(model_callback=...)`, run `simulate(conversational_goldens=..., max_user_simulations=...)` to produce `ConversationalTestCase`s, and stamp each with the fixed `chatbot_role` (required by `RoleAdherenceMetric`).
- Add **multi-turn metric scoring** (`backend/evals/chatbot/metrics.py` + `report.py`): score the simulated conversations with `ConversationCompletenessMetric`, `TurnRelevancyMetric`, `KnowledgeRetentionMetric`, `RoleAdherenceMetric`, `TopicAdherenceMetric` (given the in-scope Choice FinX topics), `GoalAccuracyMetric`, and `ToolUseMetric`, each thresholded and using Claude (model id from `backend.config.settings`) as the eval model.
- **Report to Confident AI**: run scoring via DeepEval `evaluate(...)` so the test run, per-conversation threads, and per-metric scores push to Confident AI when a Confident API key is present; always print a local metrics table and write a machine-readable JSON report under `backend/evals/chatbot/`, degrading gracefully to local-only when the key is absent.
- Add a **runnable entrypoint** (`backend/evals/chatbot/run.py`, `python -m backend.evals.chatbot.run`) with configurable golden path, golden subset size, `max_user_simulations`, per-metric thresholds, and a push/no-push flag.
- Add **smoke tests** (`backend/evals/chatbot/tests/`) that run the simulator over a tiny golden subset with `model_callback` (and the eval model) stubbed, asserting a conversation is produced and scored.
- NOT in scope: the agent implementation (P4 `backend/agent/`), RAG-level evals (P6 `backend/evals/rag/`), tracing setup (P3 `backend/tracing/`), and `backend/evals/__init__.py` (owned by P0).

## Capabilities

### New Capabilities
- `chatbot-multiturn-evals`: scenario-based multi-turn simulation of the real P4 agent (LLM role-plays the user via a `model_callback` wrapping `agent_reply`) over a configurable ≥20-golden set that includes SEBI-advice, off-topic-hijack, and clarifying-question guardrail probes, scored with the DeepEval conversation-level metrics (completeness, turn relevancy, knowledge retention, role adherence, topic adherence, goal accuracy, tool use) and reported to Confident AI with a local JSON/table fallback.

### Modified Capabilities
<!-- None — this change only adds a new capability inside backend/evals/chatbot/. -->

## Impact

- New files only, all inside the owned directory `backend/evals/chatbot/`:
  - `backend/evals/chatbot/__init__.py` — re-export `model_callback`, `load_goldens`, `build_metrics`, `simulate_conversations`, `run` (the placeholder seeded by P0 gains exports; no other package touched).
  - `backend/evals/chatbot/model_callback.py` — `model_callback` + `turns_to_history(...)` adapter + test-session provider.
  - `backend/evals/chatbot/goldens.py` — the ≥20 `ConversationalGolden` catalogue (with guardrail probes) + `load_goldens(path)` loader for the JSON override.
  - `backend/evals/chatbot/goldens.json` — committed, editable golden set (the configurable set; regenerable/hand-editable).
  - `backend/evals/chatbot/constants.py` — `CHATBOT_ROLE` text and `IN_SCOPE_TOPICS` list for role/topic adherence.
  - `backend/evals/chatbot/metrics.py` — `build_metrics(thresholds, topics)` returning the seven conversational metrics.
  - `backend/evals/chatbot/simulate.py` — `simulate_conversations(...)` building the `ConversationSimulator` and stamping `chatbot_role`.
  - `backend/evals/chatbot/report.py` — Confident AI push via `evaluate(...)` + local metrics table and JSON report writer.
  - `backend/evals/chatbot/run.py` — CLI entrypoint (`main()`) wiring goldens → simulate → score → report.
  - `backend/evals/chatbot/tests/__init__.py`, `backend/evals/chatbot/tests/test_smoke.py`, `backend/evals/chatbot/tests/fixtures/tiny_goldens.json` — smoke tests + tiny fixture.
- Imports only (does not modify): `backend.config.settings.Settings`; `backend.contracts.session.SessionContext`; `backend.contracts.agent` (`AgentReply`, `ToolCallRecord`); `backend.contracts.retrieval.Citation`; and `backend.agent.agent_reply` (P4).
- Does NOT touch `backend/evals/__init__.py` (P0), `backend/evals/rag/` (P6), `backend/agent/` (P4), `backend/tracing/` (P3), `pyproject.toml`, `.env`, or any root config. `deepeval` and `anthropic` are already declared by P0 (foundations-and-contracts); if `deepeval` were missing from the manifest, that is a P0 addition, not this change. A Confident AI API key setting, if not already present in P0 config/`.env.example`, is a P0 addition, not this change.
- Depends on P0 `foundations-and-contracts` (contracts + config) and P4 `agentic-loop` (`agent_reply`) merged to `main` first. Coexists with P6 `rag-evals` (owns `backend/evals/rag/`); no shared files.
