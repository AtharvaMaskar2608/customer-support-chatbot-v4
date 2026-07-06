## ADDED Requirements

### Requirement: Login with trimmed client code and session token

The login page SHALL present exactly two inputs — client code and session token — and on submit MUST trim (strip surrounding whitespace from) both values before use, POST them as `{client_code, session_token}` to `POST /session`, and on success store the returned session id and navigate to the chat view. Submitting an empty (post-trim) client code or session token MUST be prevented and MUST NOT issue the request.

#### Scenario: Inputs are trimmed before the session request

- **WHEN** a tester enters a client code and session token with leading/trailing whitespace and submits the login form
- **THEN** the values are stripped of surrounding whitespace and sent as `{client_code, session_token}` to `POST /session` with no whitespace

#### Scenario: Successful login navigates to the chat view

- **WHEN** `POST /session` returns a session id
- **THEN** the session id is stored (for the chat view to use) and the browser navigates to the chat view

#### Scenario: Empty inputs are rejected client-side

- **WHEN** a tester submits the login form with a client code or session token that is empty after trimming
- **THEN** an inline validation message is shown and no `POST /session` request is made

#### Scenario: Failed login shows an inline error

- **WHEN** `POST /session` returns an error or fails
- **THEN** an inline error message is shown on the login page and the tester remains on the login page

### Requirement: Streaming chat consumes the SSE event stream

The chat view SHALL, on message send, open an SSE stream to `POST /chat` carrying the stored session id and the message, and MUST consume `SseEvent` objects, dispatching by `event` name: `status`, `token`, `citations`, `usage`, `done`, and `error`. Because `/chat` is a POST with a body, the client MUST NOT rely on the native `EventSource`; it SHALL read the `text/event-stream` response body incrementally and parse events itself. The send control MUST be disabled while a stream is in flight and re-enabled on `done` or `error`.

#### Scenario: Sending a message opens the chat stream

- **WHEN** a tester types a knowledge-base question and sends it
- **THEN** the message appears as a user bubble, an assistant bubble is created, and an SSE stream to `POST /chat` is opened with the stored session id and the message text

#### Scenario: Multi-chunk stream framing is parsed correctly

- **WHEN** the `text/event-stream` response arrives split across multiple network chunks and/or a single token contains newlines
- **THEN** only complete events (terminated by a blank line) are processed, partial data is buffered until complete, and no event is dropped or duplicated

### Requirement: Transient thinking-step status messages

The chat view SHALL render each `status` event's `message` as a transient "thinking" step shown while the agent works (e.g. "Looking up the knowledge base…", "Generating the answer…"), showing the latest step as a single live line rather than an accumulating log, and MUST clear the thinking indicator once output tokens begin streaming or the message completes.

#### Scenario: Status events render as live thinking steps

- **WHEN** the stream emits `status` events with `data.message` values
- **THEN** the assistant bubble shows the latest status message as a transient thinking step, replacing the previous one

#### Scenario: Thinking indicator clears when tokens arrive

- **WHEN** the first `token` event arrives after one or more `status` events
- **THEN** the transient thinking step is cleared and token text begins rendering in its place

### Requirement: Streamed output tokens append to the assistant message

The chat view SHALL append each `token` event's `text` to the current assistant message in order as it streams, so the tester sees the answer build incrementally.

#### Scenario: Tokens accumulate into the assistant message

- **WHEN** the stream emits a sequence of `token` events with `text` fragments
- **THEN** the assistant message body shows the fragments concatenated in arrival order, growing as each token arrives

### Requirement: Hoverable citation card at the end of the message

When a `citations` event is received, the chat view SHALL render a citation UI at the END of that assistant message, one entry per `Citation` in `data.items`, where each entry is a hoverable (and keyboard-focusable) card the tester can inspect, exposing the citation's `topic`, `section`, `question`, and source (`answer_source` / `source_row`). Messages that receive no `citations` event MUST NOT show a citation card.

#### Scenario: Citations render as an inspectable hover card at message end

- **WHEN** a `citations` event with a non-empty `items` list is received for a message
- **THEN** a citation entry is rendered at the end of that assistant message, and hovering or focusing it reveals a card showing the citation's topic, section, question, and source

#### Scenario: No citations means no citation card

- **WHEN** an assistant message completes without any `citations` event
- **THEN** no citation card is shown for that message

### Requirement: Per-message cost and latency

The chat view SHALL, on each `usage` event, display that message's cost in INR (from `data.cost_inr`) and its latency in milliseconds (from `data.latency_ms`) directly beneath the corresponding assistant message, visible on all viewport sizes.

#### Scenario: Cost and latency shown under the message

- **WHEN** a `usage` event with `cost_inr` and `latency_ms` is received for a message
- **THEN** the message's INR cost and latency (ms) are shown directly below that message on both desktop and mobile viewports

### Requirement: Web-only cumulative INR cost card in the top-left

The chat view SHALL display a cumulative conversation-cost card fixed in the TOP-LEFT showing the running total in INR, and MUST update it from each `usage` event's `cumulative_cost_inr` (the backend-provided running total, not a client-side sum). This card is WEB-ONLY and MUST be hidden on narrow/mobile viewports.

#### Scenario: Cumulative card updates from the backend running total

- **WHEN** a `usage` event with `cumulative_cost_inr` is received
- **THEN** the top-left cumulative-cost card shows that value in INR as the conversation's running total

#### Scenario: Cumulative card is hidden on mobile

- **WHEN** the chat view is rendered on a narrow/mobile viewport
- **THEN** the top-left cumulative-cost card is not displayed, while per-message cost/latency remain visible

### Requirement: Responsive white-and-blue theme

The frontend SHALL use a minimal white background with blue accents and MUST be responsive/mobile-compatible, laying out as a single usable column on narrow viewports without horizontal overflow, built with plain HTML/CSS/JS plus Tailwind.

#### Scenario: Layout adapts to mobile width

- **WHEN** the login and chat pages are viewed at a mobile viewport width
- **THEN** content reflows into a single usable column with no horizontal scrolling, retaining the white/blue theme

### Requirement: Stream error handling

The chat view SHALL handle `error` events and stream/transport failures by surfacing the `error.data.message` (or a generic failure message) inline in the affected assistant message, stopping the stream, and re-enabling the send control so the tester can retry.

#### Scenario: Error event is surfaced inline

- **WHEN** the stream emits an `error` event with `data.message`
- **THEN** the message is shown inline in the assistant bubble in an error style, the stream stops, and the send control is re-enabled

#### Scenario: Transport failure is handled gracefully

- **WHEN** the `POST /chat` request fails or the stream drops before a `done` event
- **THEN** an inline error is shown, the stream stops, and the send control is re-enabled without leaving the UI stuck in a busy state
