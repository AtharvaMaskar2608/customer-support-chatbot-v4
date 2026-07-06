## Context

Multi-turn evaluation of the P4 agentic loop. The agent's behaviours that matter — context retention, goal completion, guardrail adherence (SEBI no-advice, Choice-FinX scope), behavioural consistency — are only observable over a full conversation, and multi-turn conversations are non-deterministic (each user message depends on the previous assistant reply), so a fixed input/output set cannot express them. We therefore use DeepEval's scenario-based **simulation**: a `ConversationalGolden` describes the situation and the simulated user's persona, a `ConversationSimulator` role-plays the user against our real agent through a `model_callback`, and the resulting `ConversationalTestCase`s are scored with conversation-level metrics and pushed to Confident AI.

- Reference docs: `docs/chatbot_eval/1_multi_turn_eval.md` (workflow), `2_multi_turn_eval_metrics.md` (metric catalogue + field requirements), `3_multi_turn_simulation.md` (simulator, `Turn`, rich-turn fields, `max_user_simulations`, `async_mode`).
- Owned dir: `backend/evals/chatbot/` only.
- Imports (frozen, not modified): `backend.config.settings.Settings`; `backend.contracts.session.SessionContext`; `backend.contracts.agent.{AgentReply, ToolCallRecord}`; `backend.contracts.retrieval.Citation`.
- Calls P4: `backend.agent.agent_reply(history: list[dict], session: SessionContext, thread_id: str) -> AgentReply` (returns `content`, `citations`, `tools_called`).
- Coexists with P6 `rag-evals` (`backend/evals/rag/`). No shared files; P0 owns `backend/evals/__init__.py`.

## Goals / Non-Goals

**Goals**
- Adapt the real P4 agent into a DeepEval `model_callback` so simulated conversations exercise production behaviour, not a mock.
- Provide a configurable ≥20-golden benchmark that includes explicit SEBI-advice, off-topic-hijack, and clarifying-question guardrail probes.
- Score whole conversations with the seven multi-turn metrics and push traces/results to Confident AI, with a deterministic local fallback.
- Ship a runnable CLI entrypoint and a fast, offline smoke test.

**Non-Goals**
- Implementing or fixing the agent, retrieval, or tools (P4/P1/P2).
- RAG/retrieval-level (single-turn) evals — that is P6 `rag-evals`.
- Tracing/observability setup — that is P3; this change only consumes results DeepEval/Confident AI already surface.
- Guaranteeing the agent passes any threshold; this change measures, it does not tune.

## Decisions

### 1. `model_callback` signature and `AgentReply -> Turn` mapping
Signature (async, exactly as the simulator calls it):

```
async def model_callback(input: str, turns: list[Turn], thread_id: str) -> Turn
```

- **History adaptation**: `turns_to_history(turns, input)` maps each prior simulator `Turn` to `{"role": turn.role, "content": turn.content}` (roles `user`/`assistant`), then appends `{"role": "user", "content": input}`. That list is passed as `agent_reply`'s `history`.
- **Session**: a single test `SessionContext(client_code, session_token)` is built from configuration (e.g. `Settings` / env `EVAL_CLIENT_CODE`, `EVAL_SESSION_TOKEN`), never hardcoded, so report-tool paths can run against a tester's session.
- **Reply → Turn**:
  - `content = reply.content`
  - `retrieval_context = [<raw chunk text> for c in reply.citations]` — the raw retrieved grounding surfaced on `AgentReply.citations`; `None` when the turn retrieved nothing (RAG multi-turn metrics only run on turns that carry it).
  - `tools_called = [ToolCall(name=r.name, input_parameters=<args>, output=<result>) for r in reply.tools_called] or None` — each P0 `ToolCallRecord` mapped to a DeepEval `ToolCall`; `None` when no tool ran.
- The callback is resilient: an agent error inside a turn is caught and returned as an assistant `Turn` with an error `content` so one bad turn does not abort the whole simulation.

### 2. Golden schema + count
Goldens are `ConversationalGolden(scenario, expected_outcome, user_description)` plus a `category` tag carried in `additional_metadata`. The **configurable** set lives in `goldens.json` (list of `{scenario, expected_outcome, user_description, category}`); `load_goldens(path=None)` returns the in-code catalogue by default or parses a JSON override. **≥20 goldens**, spanning categories:
- `kb` — normal knowledge-base question, single and multi-intent (goal completion, completeness).
- `report_tool` — CML report / contract note requests (tool use, goal accuracy); includes a path that must first ask for the missing identifier.
- `retention` — user states a fact early (client code, product) and references it later (knowledge retention).
- `sebi_probe` — user repeatedly demands an investment opinion/recommendation/"should I buy?"; expected outcome is a polite refusal that never gives advice (role/topic adherence).
- `scope_probe` — user hijacks to off-topic (weather, coding help, competitor products); expected outcome is a scope decline + redirect.
- `clarifying` — ambiguous request; expected outcome is the agent asking a clarifying question before answering.

At least one golden exists for each of `sebi_probe`, `scope_probe`, and `clarifying` (the mandated guardrail probes).

### 3. Metrics list
`build_metrics(thresholds, topics)` returns, from `deepeval.metrics`, using Claude (`Settings.ANTHROPIC_MODEL`) as the eval model where a model is taken:
- `ConversationCompletenessMetric` — all user intentions satisfied.
- `TurnRelevancyMetric` — each reply relevant to prior context.
- `KnowledgeRetentionMetric` — facts stated by the user are retained.
- `RoleAdherenceMetric` — stays in the support-agent role (requires `chatbot_role` on the test case).
- `TopicAdherenceMetric` — answers only in-scope Choice FinX topics, refuses off-topic (fed `IN_SCOPE_TOPICS`).
- `GoalAccuracyMetric` — plans/executes to reach the goal (uses `tools_called`).
- `ToolUseMetric` — correct tool selection + arguments (uses `tools_called`).
Each metric takes a per-metric `threshold` (default 0.7) overridable from the CLI.

### 4. Simulator config
`simulate_conversations(goldens, model_callback, max_user_simulations=10, max_concurrent=...)`:
- `ConversationSimulator(model_callback=model_callback, async_mode=True, max_concurrent=<config>)`.
- `simulate(conversational_goldens=goldens, max_user_simulations=max_user_simulations)` → `list[ConversationalTestCase]`; a conversation stops when the golden's `expected_outcome` is reached or the turn cap hits. `max_user_simulations` defaults to 10 (matching the agent's 10-message cap) and is lowered (e.g. 2) for smoke tests.
- Each returned `ConversationalTestCase` is stamped with `chatbot_role = CHATBOT_ROLE` before scoring (RoleAdherence requires it).

### 5. Confident AI reporting
Scoring goes through DeepEval `evaluate(test_cases=..., metrics=build_metrics(...))`, which creates a test run and pushes per-conversation threads + per-metric scores to Confident AI when a Confident API key is configured (env, surfaced via P0 `Settings`; login is a one-time `deepeval login` / `CONFIDENT_API_KEY`). Independently, `report.py` always prints a per-metric mean-score table and writes a JSON report (run params: golden count/subset, thresholds, `max_user_simulations`, models) under `backend/evals/chatbot/`. With no key, the run is local-only and still produces the table + JSON — so the eval is runnable and deterministic in CI.

## Risks / Trade-offs

- **Cost/latency**: simulation + LLM-judged metrics call models many times per golden. Mitigation: `async_mode` + `max_concurrent`, a configurable golden subset, and a stubbed smoke test that makes zero network calls; full runs are opt-in via the CLI.
- **Non-determinism of scores**: simulated conversations and judge scores vary run-to-run. Mitigation: fixed golden set + version + recorded run params give statistically comparable benchmarks; thresholds gate regressions rather than exact-match.
- **`retrieval_context` fidelity**: `AgentReply` exposes citations, not full `RetrievedChunk`s, so `retrieval_context` is reconstructed from citation text and may under-represent chunks the agent retrieved but did not cite. Accepted: the RAG multi-turn metrics are secondary here (owned depth is P6); the primary metrics are conversation/behaviour-level. If P0 later surfaces raw chunks on `AgentReply`, the mapping upgrades with no contract change here.
- **Contract coupling to P4**: relies on `agent_reply(history, session, thread_id)` and `AgentReply.{content, citations, tools_called}`. These are frozen P0/P4 contracts; a change there is a coordinated cross-change break, not a silent one.
