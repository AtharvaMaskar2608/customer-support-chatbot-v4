## ADDED Requirements

### Requirement: SSE chat endpoint content type

The system SHALL expose a chat endpoint `POST /chat` accepting a JSON body `{session_id, thread_id, message}` that, for a valid session, responds `200` with `Content-Type: text/event-stream` and a streaming body, and SHALL set `Cache-Control: no-cache` and disable proxy buffering so intermediate events reach the client as they are produced.

#### Scenario: Successful chat opens a text/event-stream response

- **WHEN** `POST /chat` is called with a valid `session_id`, a `thread_id`, and a user `message`
- **THEN** the response status is `200` and its `Content-Type` is `text/event-stream`

### Requirement: Streamed event sequence relays the agent stream

The system SHALL call `backend.agent.agent_reply_stream(history, session, thread_id)` and relay each yielded `SseEvent` to the client as one SSE frame formatted as `event: <name>` and `data: <json>`, preserving the agent's emission order: one or more `status` events, then `token` events, then a `citations` event, then a `usage` event, then a terminal `done` event. The endpoint MUST NOT reorder, drop, or merge events, and MUST emit each event's `data` as JSON.

#### Scenario: KB question streams status, token, citations, usage, then done

- **WHEN** `POST /chat` is called with a knowledge-base question and the agent emits `status → token(s) → citations → usage → done`
- **THEN** the client receives SSE frames whose `event` names appear in that same order, ending with a `done` frame, each frame carrying the corresponding event's JSON `data`

#### Scenario: Intermediate status frames precede any token frame

- **WHEN** the agent yields an intermediate `status` event (e.g. "Looking up the knowledge base…") before producing output
- **THEN** the client receives that `status` frame before the first `token` frame

### Requirement: Per-session conversation history

The system SHALL maintain conversation history per `(session_id, thread_id)`, appending the incoming user `message` to that thread's history before invoking the agent and committing the assistant's final content to the history after the stream completes, so that a later request on the same thread includes the prior turns in the `history` passed to `agent_reply_stream`.

#### Scenario: Prior turns are included on the next request

- **WHEN** a second `POST /chat` is made on the same `session_id` and `thread_id` after a completed first turn
- **THEN** the `history` passed to `agent_reply_stream` contains the earlier user message and the earlier assistant reply

#### Scenario: Distinct threads keep separate histories

- **WHEN** two `POST /chat` requests use the same `session_id` but different `thread_id` values
- **THEN** each thread's `history` contains only its own turns and not the other thread's messages

### Requirement: Cumulative INR cost in usage events

The system SHALL track a cumulative conversation cost in INR per session, fold each turn's `UsageCost.cost_inr` into that running total, and enrich every outgoing `usage` event's `data` with `cumulative_cost_inr` alongside the per-message cost and latency, so the frontend can render per-message cost, latency, and a running conversation total.

#### Scenario: Usage event exposes per-message and cumulative cost

- **WHEN** the agent emits a `usage` event carrying this turn's `cost_inr` and `latency_ms`
- **THEN** the relayed `usage` frame's `data` contains that turn's `cost_inr` and `latency_ms` and a `cumulative_cost_inr` equal to the running total of all turns' `cost_inr` for that session

#### Scenario: Cumulative total increases across turns

- **WHEN** a second billable turn completes on a session whose first turn already cost some INR
- **THEN** the second `usage` frame's `cumulative_cost_inr` is greater than or equal to the first turn's `cumulative_cost_inr`

### Requirement: Streaming error handling

The system SHALL handle failures without leaking an unframed exception to the client. If the failure occurs before the stream is committed (e.g. unknown session), it SHALL return a JSON HTTP error. If the failure occurs while iterating `agent_reply_stream`, it SHALL emit a terminal `error` SSE event carrying an error message and stop the stream, and MUST NOT persist a partial assistant turn to history.

#### Scenario: Agent failure mid-stream emits a terminal error event

- **WHEN** `agent_reply_stream` raises an exception after some events were already streamed
- **THEN** the client receives an `error` SSE frame whose `data` contains a message, the stream ends, and no partial assistant reply is committed to that thread's history

#### Scenario: Failure before the stream opens returns a JSON error

- **WHEN** a chat request fails validation or references an unknown session before streaming begins
- **THEN** the response is a JSON HTTP error (not a `text/event-stream` body)

### Requirement: CORS for the frontend origin

The system SHALL configure Cross-Origin Resource Sharing so the separate frontend POC origin may call `POST /session` and `POST /chat` from the browser, with the allowed origin sourced from configuration rather than hardcoded.

#### Scenario: Browser preflight from the frontend origin is permitted

- **WHEN** the frontend origin issues a CORS preflight `OPTIONS` for `POST /chat`
- **THEN** the response permits that origin and the `POST` method
