## 1. Package skeleton & constants

- [ ] 1.1 Add exports to `backend/evals/chatbot/__init__.py` (the placeholder seeded by P0) re-exporting `model_callback`, `load_goldens`, `build_metrics`, `simulate_conversations`, `run` — no other package touched
- [ ] 1.2 Add `backend/evals/chatbot/constants.py` with `CHATBOT_ROLE` (support-agent role text) and `IN_SCOPE_TOPICS` (Choice FinX topic list) for role/topic adherence

## 2. model_callback (agent_reply → Turn adapter)

- [ ] 2.1 Implement `backend/evals/chatbot/model_callback.py`: `turns_to_history(turns, input) -> list[dict]` mapping prior `Turn`s to `{"role","content"}` and appending the new user message
- [ ] 2.2 Implement a config-sourced test `SessionContext` provider (client code + session token from `Settings`/env; no literal token)
- [ ] 2.3 Implement `async def model_callback(input, turns, thread_id) -> Turn` calling P4 `agent_reply(history, session, thread_id)` and mapping `AgentReply.content` → `Turn.content`, `AgentReply.citations` → `retrieval_context` (or `None`), `AgentReply.tools_called` (`ToolCallRecord`) → `Turn.tools_called` DeepEval `ToolCall`s (or `None`)
- [ ] 2.4 Catch per-turn agent errors and return an assistant `Turn` with an error `content` so one failure does not abort the simulation

## 3. Golden set (≥20, incl. guardrail probes)

- [ ] 3.1 Author `backend/evals/chatbot/goldens.json` with ≥20 goldens (`scenario`, `expected_outcome`, `user_description`, `category`) across `kb`, `report_tool`, `retention`, `sebi_probe`, `scope_probe`, `clarifying`
- [ ] 3.2 Ensure ≥1 SEBI advice-seeking probe (pushes for an investment opinion/recommendation), ≥1 off-topic hijack probe, and ≥1 clarifying-question golden
- [ ] 3.3 Implement `backend/evals/chatbot/goldens.py`: in-code catalogue + `load_goldens(path=None)` returning `list[ConversationalGolden]` (default catalogue or JSON override), carrying `category` in `additional_metadata`

## 4. Simulation

- [ ] 4.1 Implement `backend/evals/chatbot/simulate.py`: `simulate_conversations(goldens, model_callback, max_user_simulations=10, max_concurrent=...)` building `ConversationSimulator(model_callback=..., async_mode=True, ...)` and calling `simulate(conversational_goldens=goldens, max_user_simulations=...)`
- [ ] 4.2 Stamp each returned `ConversationalTestCase` with `chatbot_role = CHATBOT_ROLE`

## 5. Metrics & reporting

- [ ] 5.1 Implement `backend/evals/chatbot/metrics.py`: `build_metrics(thresholds, topics)` returning `ConversationCompletenessMetric`, `TurnRelevancyMetric`, `KnowledgeRetentionMetric`, `RoleAdherenceMetric`, `TopicAdherenceMetric(topics=...)`, `GoalAccuracyMetric`, `ToolUseMetric` (Claude eval model from `Settings`, per-metric thresholds)
- [ ] 5.2 Implement `backend/evals/chatbot/report.py`: score via DeepEval `evaluate(test_cases, metrics)` (pushes to Confident AI when a key is configured), print a per-metric score table, and write a JSON report (golden count/subset, thresholds, `max_user_simulations`, models) under `backend/evals/chatbot/`

## 6. Entrypoint

- [ ] 6.1 Implement `backend/evals/chatbot/run.py` (`main()`, `python -m backend.evals.chatbot.run`) with CLI flags for golden path, subset size, `max_user_simulations`, per-metric thresholds, and push/no-push

## 7. Smoke tests & done condition

- [ ] 7.1 Add `backend/evals/chatbot/tests/__init__.py` and `backend/evals/chatbot/tests/fixtures/tiny_goldens.json` (2–3 goldens incl. one guardrail probe)
- [ ] 7.2 Add `backend/evals/chatbot/tests/test_smoke.py`: stub `model_callback` (and the eval model), run `simulate_conversations` + metric scoring over the tiny fixture with no network calls, assert ≥1 conversation is generated and scored; assert `load_goldens()` returns ≥20 goldens with the three guardrail-probe categories present
- [ ] 7.3 Run `openspec validate chatbot-multiturn-evals --strict` — passes
- [ ] 7.4 **Done condition:** the simulator generates ≥1 conversation via `model_callback` and scores it with the multi-turn metrics (`ConversationCompleteness`, `TurnRelevancy`, `KnowledgeRetention`, `RoleAdherence`, `TopicAdherence`, `GoalAccuracy`, `ToolUse`), and the guardrail-probe goldens (SEBI, off-topic, clarifying) are present. **Test command:** `pytest backend/evals/chatbot` (smoke run on a tiny golden subset with stubbed `model_callback`).
