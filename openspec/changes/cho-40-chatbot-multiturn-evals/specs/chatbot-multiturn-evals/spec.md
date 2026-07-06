## ADDED Requirements

### Requirement: model_callback adapts agent_reply into a DeepEval Turn

The system SHALL provide an async `model_callback(input: str, turns: list, thread_id: str) -> Turn` that the `ConversationSimulator` calls on every simulated user turn. It SHALL convert the simulator's `turns` list plus the current `input` into the `history: list[dict]` shape that P4 `backend.agent.agent_reply(history, session, thread_id)` expects, call `agent_reply` with a configuration-sourced test `SessionContext` and the given `thread_id`, and map the returned `AgentReply` into a `Turn` whose `content` is `AgentReply.content`, whose `retrieval_context` is the raw retrieved chunk text carried on `AgentReply.citations` (or `None` when nothing was retrieved), and whose `tools_called` maps each `AgentReply.tools_called` record to a DeepEval `ToolCall` (or `None` when no tool ran). The test session token SHALL come from configuration, never a source literal.

#### Scenario: Simulator turns become agent history

- **WHEN** `model_callback` is invoked with prior `turns` and a new user `input`
- **THEN** it builds a `history` list of `{"role", "content"}` dicts from the prior turns followed by the new user message, and calls `agent_reply(history, session, thread_id)` with that history and the received `thread_id`

#### Scenario: AgentReply maps onto Turn fields

- **WHEN** `agent_reply` returns an `AgentReply` with content, citations, and tool calls
- **THEN** the returned `Turn` carries that content, a `retrieval_context` derived from the reply's citations, and a `tools_called` list of DeepEval `ToolCall`s derived from the reply's `tools_called`

#### Scenario: Turns without retrieval or tools omit those fields

- **WHEN** `agent_reply` returns a reply with no citations and no tool calls (e.g. a scope refusal)
- **THEN** the returned `Turn` has `retrieval_context` and `tools_called` set to `None` and still carries the reply content

#### Scenario: Test session comes from configuration

- **WHEN** `model_callback` constructs the `SessionContext` for `agent_reply`
- **THEN** the client code and session token are read from configuration, and no session token appears as a literal in the source

### Requirement: Configurable golden set with guardrail probes

The system SHALL define a versioned set of at least 20 `ConversationalGolden`s, each with `scenario`, `expected_outcome`, and `user_description`, and a `category` tag. The set SHALL be loadable via `load_goldens(path=None)`, returning the in-code catalogue by default or parsing a JSON override file so the golden set is configurable without code changes. The set SHALL include at least one SEBI advice-seeking probe (user demands an investment opinion/recommendation and pushes back), at least one off-topic hijack probe (user steers to a non Choice-FinX topic), and at least one clarifying-question path (an ambiguous request that should trigger a clarifying question before an answer).

#### Scenario: At least twenty goldens load

- **WHEN** `load_goldens()` is called with no override path
- **THEN** it returns at least 20 `ConversationalGolden`s, each carrying a `scenario`, `expected_outcome`, and `user_description`

#### Scenario: Guardrail probes are present

- **WHEN** the golden set is inspected by `category`
- **THEN** it contains at least one SEBI advice-seeking probe, at least one off-topic hijack probe, and at least one clarifying-question golden

#### Scenario: Golden set is overridable from a file

- **WHEN** `load_goldens(path)` is given a JSON file of goldens
- **THEN** it parses that file into `ConversationalGolden`s instead of the in-code catalogue

### Requirement: Simulation of multi-turn conversations against the real agent

The system SHALL run a DeepEval `ConversationSimulator` configured with the `model_callback` to generate multi-turn conversations from the goldens, producing one `ConversationalTestCase` per golden. The number of user turns SHALL be configurable (via `max_user_simulations`), and each produced test case SHALL be stamped with the chatbot role so role-adherence scoring can run.

#### Scenario: Simulator generates a conversation per golden

- **WHEN** `simulate_conversations(goldens, model_callback, max_user_simulations)` runs
- **THEN** it returns a list of `ConversationalTestCase`s, one per input golden, each containing the recorded turns produced by driving `model_callback`

#### Scenario: Chatbot role is attached for role adherence

- **WHEN** a `ConversationalTestCase` is produced by the simulator
- **THEN** its `chatbot_role` is set to the defined support-agent role before scoring

#### Scenario: Conversation length is bounded and configurable

- **WHEN** a caller passes a `max_user_simulations` value
- **THEN** the simulator stops each conversation when the golden's expected outcome is reached or that maximum number of user turns is hit

### Requirement: Multi-turn metric scoring

The system SHALL score the simulated `ConversationalTestCase`s with the DeepEval conversation-level metrics `ConversationCompletenessMetric`, `TurnRelevancyMetric`, `KnowledgeRetentionMetric`, `RoleAdherenceMetric`, `TopicAdherenceMetric`, `GoalAccuracyMetric`, and `ToolUseMetric`. `TopicAdherenceMetric` SHALL be given the in-scope Choice FinX topics, and every metric SHALL take a per-metric threshold overridable by the caller.

#### Scenario: All seven metrics are built

- **WHEN** `build_metrics(thresholds, topics)` is called
- **THEN** it returns metric instances for conversation completeness, turn relevancy, knowledge retention, role adherence, topic adherence, goal accuracy, and tool use

#### Scenario: Topic adherence is scoped to Choice FinX

- **WHEN** the topic-adherence metric is constructed
- **THEN** it is supplied the in-scope Choice FinX topic list so off-topic answers are penalised and off-topic refusals are rewarded

#### Scenario: Thresholds are configurable

- **WHEN** the caller supplies per-metric thresholds
- **THEN** each metric is constructed with the supplied threshold instead of the default

### Requirement: Results reporting to Confident AI with local fallback

The system SHALL score the conversations through DeepEval `evaluate(...)` so the test run, per-conversation threads, and per-metric scores push to Confident AI when a Confident API key is configured, and SHALL always print a per-metric score table and write a machine-readable JSON report (recording golden count/subset, thresholds, `max_user_simulations`, and the models used) under `backend/evals/chatbot/`, so the run is reproducible locally when no key is present.

#### Scenario: Results push to Confident AI when configured

- **WHEN** an evaluation run completes with a Confident API key configured
- **THEN** the test run and its conversation threads and metric scores are pushed to Confident AI

#### Scenario: Local report is always produced

- **WHEN** an evaluation run completes with or without a Confident API key
- **THEN** a per-metric score table is printed and a JSON report recording the run parameters is written under `backend/evals/chatbot/`

### Requirement: Runnable eval entrypoint

The system SHALL provide a runnable entrypoint (`python -m backend.evals.chatbot.run`) that wires load-goldens → simulate → score → report, exposing configuration for the golden-file path, golden subset size, `max_user_simulations`, per-metric thresholds, and whether to push to Confident AI.

#### Scenario: Entrypoint runs a full simulate-and-score cycle

- **WHEN** the entrypoint is invoked with a golden path and a subset size
- **THEN** it loads that subset of goldens, simulates conversations via `model_callback`, scores them with the multi-turn metrics, and emits the report

#### Scenario: Smoke run on a tiny stubbed subset

- **WHEN** the simulator runs over a tiny golden subset with `model_callback` and the eval model stubbed
- **THEN** at least one conversation is generated and scored by the multi-turn metrics without making network calls
