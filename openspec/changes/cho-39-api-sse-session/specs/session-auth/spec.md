## ADDED Requirements

### Requirement: Session creation from trimmed credentials

The system SHALL expose `POST /session` accepting a JSON body `{client_code, session_token}`, and SHALL construct a `backend.contracts.session.SessionContext` from them so that both values are stripped of surrounding whitespace before storage. On success it SHALL create a server-side session and return `200` with a JSON body `{session_id}` carrying an opaque server-issued identifier. The endpoint MUST NOT return the raw session token in the response.

#### Scenario: Valid credentials create a session and return an id

- **WHEN** `POST /session` is called with a non-empty `client_code` and `session_token`
- **THEN** it responds `200` with a JSON `{session_id}` whose value is a non-empty opaque string, and the response body does not echo the `session_token`

#### Scenario: Surrounding whitespace is trimmed from both inputs

- **WHEN** `POST /session` is called with `client_code` and `session_token` that have leading and trailing whitespace
- **THEN** the stored `SessionContext.client_code` and `SessionContext.session_token` equal the whitespace-stripped values

#### Scenario: Empty-after-trim credentials are rejected

- **WHEN** `POST /session` is called with a `client_code` or `session_token` that is empty or whitespace-only
- **THEN** it responds `422` and no session is created

### Requirement: Session token retained as FINX authorization for reuse

The system SHALL retain the trimmed `session_token` server-side within the created session's `SessionContext` so it can be reused as the FINX `Authorization` JWT on later agent report calls, and SHALL key the session by the returned `session_id` so subsequent requests reference the session by id rather than resending the credentials.

#### Scenario: Stored session exposes the trimmed token to the agent

- **WHEN** a chat request references an existing `session_id`
- **THEN** the handler passes that session's `SessionContext` (carrying the trimmed `session_token` as the FINX JWT) to `agent_reply_stream` without requiring the client to resend the token

#### Scenario: Same session id is reusable across multiple requests

- **WHEN** two successive requests reference the same `session_id`
- **THEN** both resolve to the same stored `SessionContext` and the session is not recreated

### Requirement: Unknown session id is rejected

The system SHALL reject any chat request whose `session_id` does not correspond to a stored session with an HTTP error rather than attempting to stream or silently creating a new session.

#### Scenario: Chat against an unknown session id returns 404

- **WHEN** a chat request is made with a `session_id` that was never issued by `POST /session`
- **THEN** the endpoint responds `404` and does not open an SSE stream
