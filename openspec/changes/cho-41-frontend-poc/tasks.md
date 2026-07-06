## 1. Scaffold & theme (frontend/ only)

- [ ] 1.1 Create `frontend/index.html` (login) and `frontend/chat.html` (chat), each pulling Tailwind via CDN and including the shared scripts
- [ ] 1.2 Add `frontend/css/app.css` with the white/blue theme variables and citation hover-card styles
- [ ] 1.3 Add `frontend/js/config.js` exposing the backend base URL as the single point of configuration
- [ ] 1.4 Confirm no files are created or modified outside `frontend/` (no `pyproject.toml`, `.env`, root config, or `backend/` changes)

## 2. Login flow

- [ ] 2.1 `frontend/js/login.js`: on submit, trim client code + session token, block empty (post-trim) values with an inline validation message
- [ ] 2.2 POST `{client_code, session_token}` to `POST /session`; on success store the returned session id in `sessionStorage` and navigate to `chat.html`
- [ ] 2.3 On `/session` failure, show an inline error and remain on the login page
- [ ] 2.4 `chat.html` redirects back to `index.html` when no session id is present

## 3. SSE chat client

- [ ] 3.1 `frontend/js/api.js`: `postSession()` and `streamChat()` — `streamChat()` uses `fetch` POST + `ReadableStream` reader + `TextDecoder`, buffering across chunks and parsing `text/event-stream` framing (blank-line-terminated events, `event:`/`data:` lines)
- [ ] 3.2 Dispatch parsed events to callbacks `onStatus`/`onToken`/`onCitations`/`onUsage`/`onDone`/`onError`, `JSON.parse`-ing each `data` payload
- [ ] 3.3 Disable the send control while a stream is in flight; re-enable on `done` or `error`

## 4. Chat rendering

- [ ] 4.1 On send: append user bubble, create assistant bubble with thinking-steps / text / citations / meta slots
- [ ] 4.2 `status` → show latest message as a single transient thinking line; clear it on first token or completion
- [ ] 4.3 `token` → append `text` to the assistant message body in arrival order
- [ ] 4.4 `citations` → render a hoverable/focusable citation card at the END of the message showing topic/section/question/source; no card when no `citations` event
- [ ] 4.5 `usage` → show that message's `cost_inr` (INR) + `latency_ms` under the message; update the top-left cumulative card from `cumulative_cost_inr`
- [ ] 4.6 `error` and transport failures → show inline error, stop the stream, re-enable send

## 5. Cost card & responsiveness

- [ ] 5.1 Add the fixed top-left cumulative INR cost card, `hidden md:block` (web-only, hidden on mobile)
- [ ] 5.2 Verify per-message cost/latency remain visible on all viewports and the layout is single-column with no horizontal overflow on mobile

## 6. Docs, QA & done condition

- [ ] 6.1 Write `frontend/README.md`: how to serve the static files (e.g. `python -m http.server` from `frontend/`), how to point `js/config.js` at the running backend, and the manual QA checklist
- [ ] 6.2 (Optional) Add `frontend/tests/smoke.spec.js` + `frontend/playwright.config.js` for a login → send → observe smoke test
- [ ] 6.3 Run `openspec validate frontend-poc --strict` — passes
- [ ] 6.4 **Done condition:** manual QA flow against a running backend — login → send a KB question → observe streamed status steps, streamed tokens, a hoverable citation card at message end, per-message cost + latency, and the top-left cumulative INR card updating; layout responsive in white/blue; error events shown inline. **Test command:** the documented manual QA checklist in `frontend/README.md` (plus optional `npx playwright test` if the smoke test is included).
