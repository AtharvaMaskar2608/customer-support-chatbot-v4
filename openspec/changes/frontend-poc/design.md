## Context

This is P8 (`frontend-poc`), the QA-facing browser UI for the Choice FinX support chatbot. It is built in parallel with P1–P7 and owns only the `frontend/` directory (a placeholder created by P0 `foundations-and-contracts`).

**Files touched (all under `frontend/`, all new):**
- `frontend/index.html` — login page.
- `frontend/chat.html` — chat view.
- `frontend/css/app.css` — minimal white/blue theme tweaks layered on Tailwind.
- `frontend/js/config.js` — backend base URL (single place to point at the running backend).
- `frontend/js/api.js` — `postSession()` and `streamChat()` SSE client.
- `frontend/js/login.js` — login form wiring (trim → POST → navigate).
- `frontend/js/chat.js` — chat rendering, SSE event handling, cost/citation UI.
- `frontend/README.md` — how to run + the manual QA checklist (the done condition).
- (optional) `frontend/tests/smoke.spec.js`, `frontend/playwright.config.js` — Playwright smoke.

**Dependencies:**
- P0 `data-contracts` (the `SseEvent`, `Citation`, `UsageCost`, `SessionContext` shapes) — frozen in `main` before this fans out.
- P5 `api-sse-session` — provides the two endpoints this UI calls. This change reads them; it does not implement or modify them.

**Consumed endpoints (owned by P5, not defined here):**
- `POST /session` — body `{client_code, session_token}` → returns a session id (e.g. `{session_id}`). Used to establish the FINX-authenticated session.
- `POST /chat` — SSE (`text/event-stream`). Request carries the session id and the user message; response streams `SseEvent` objects with `event ∈ {status, token, citations, usage, done, error}`:
  - `status.data = {message}`
  - `token.data = {text}`
  - `citations.data = {items: [Citation]}`, `Citation = {chunk_id, topic, section, question, answer_source, source_row}`
  - `usage.data = {input_tokens, output_tokens, cost_inr, latency_ms, cumulative_cost_inr}`
  - `done.data = {}`
  - `error.data = {message}`

## Goals / Non-Goals

**Goals:**
- Give a QA tester a zero-build page they open in a browser to run the full login → ask → observe flow against a running backend.
- Faithfully surface everything the backend emits: streamed steps, tokens, citations, per-message cost/latency, cumulative INR.
- Stay minimal, responsive, and obviously a testing tool (white/blue, uncluttered).

**Non-Goals:**
- No backend, agent, retrieval, report tools, tracing, or evals (P1–P7).
- No production concerns: no auth hardening, no persistence beyond the browser session, no accessibility audit, no i18n, no design system.
- No framework/bundler/state library. Vanilla JS is sufficient for a POC.

## Decisions

**Page structure — two static pages, no SPA router.** `index.html` is the login page; on successful `/session` it stores the session id in `sessionStorage` and does a plain navigation to `chat.html`. `chat.html` reads the session id from `sessionStorage`; if absent, it redirects back to `index.html`. Two files keep the POC trivially inspectable and avoid a router. Shared config/API code lives in `js/config.js` and `js/api.js`, included by both pages.

**Tailwind via CDN, not a build.** `<script src="https://cdn.tailwindcss.com"></script>` in each page's head. This keeps the POC build-free and adds no dependency-manifest changes (which this change is forbidden to touch). Trade-off: a network fetch and unpinned version; acceptable for an internal QA tool. `css/app.css` holds only the few white/blue theme variables and the citation hover-card styles that are awkward as utility classes. If an offline/pinned Tailwind is ever required, that is a P0 addition (a vendored asset), explicitly out of scope here.

**SSE client via `fetch` + `ReadableStream`, not `EventSource`.** `/chat` is a `POST` that must send a JSON body (session id + message), and the native `EventSource` only issues GET requests without a body. So `js/api.js#streamChat()` uses `fetch(POST, {body})`, reads `response.body.getReader()`, decodes chunks with `TextDecoder`, and parses the `text/event-stream` framing manually: split on blank lines into events, read `event:` and `data:` lines, `JSON.parse` the data payload, and dispatch to caller-provided callbacks (`onStatus`, `onToken`, `onCitations`, `onUsage`, `onDone`, `onError`). This is the standard workaround for POST-based SSE and keeps parsing in one small, testable function.

**Streaming render model.** On send: append a user bubble, then create an empty assistant bubble containing (a) a transient "thinking steps" area, (b) a growing text area, (c) a citations slot, (d) a meta (cost/latency) slot.
- `status` → replace the thinking-steps line with the latest `message` (a single live line, not an ever-growing log), so the tester sees "Looking up the knowledge base…" then "Generating the answer…".
- First `token` → clear the thinking-steps area; append each token's `text` to the text area.
- `citations` → render the citation card in the citations slot at the END of the message.
- `usage` → fill the meta slot with `cost_inr` (INR) and `latency_ms`, and update the cumulative card.
- `done` → mark the bubble complete and re-enable the input.
- `error` → render the `message` inline in the assistant bubble (error style) and re-enable the input.

**Citation hover-card markup.** The citations slot renders one small pill/summary per citation (e.g. its `topic`/`section`). Hovering (and focusing, for keyboard) a pill reveals an absolutely-positioned card showing `topic`, `section`, `question`, and source (`answer_source` / `source_row`, plus `chunk_id`). Implemented with a `.citation` wrapper + `.citation-card` child that is hidden by default and shown on `:hover`/`:focus-within` (CSS in `app.css`); no JS tooltip library. The card is what the QA tester "inspects" to verify retrieval provenance.

**Cost card (web-only, top-left).** A `position: fixed; top; left` card bound to a running total. It is updated from each `usage` event's `cumulative_cost_inr` (authoritative running total from the backend, not summed client-side, so it can't drift). It is hidden below Tailwind's `md` breakpoint (`hidden md:block`) so it does not overlap the chat on mobile — satisfying "web only". Per-message cost/latency (under each message) remains visible on all viewports.

**State handling.** Minimal module-scoped state in `chat.js`: the session id (from `sessionStorage`), a reference to the in-flight assistant bubble's DOM nodes, and a busy flag that disables the send button while a stream is active. No global store, no reactivity framework. The backend's `cumulative_cost_inr` is the source of truth for the cost card; the UI only mirrors it.

**Theme.** White background, blue (`#1e40af`/`#2563eb`-family) accents for the user bubble, header, and buttons; light-gray assistant bubbles; system font stack. Responsive via Tailwind flex/utility classes and `max-width` on bubbles; the layout is a single column that fills the viewport on mobile.

## Risks / Trade-offs

- **[Manual SSE parsing edge cases]** — a token that itself contains newlines, or an event split across two network chunks. Mitigation: buffer the decoded text and only process complete events (terminated by a blank line); keep the remainder in the buffer for the next read.
- **[Endpoint/response shape not final until P5 lands]** — the exact `POST /chat` request body (session id field name, message field name) and the `/session` response key are defined by P5. Mitigation: isolate all shape assumptions in `js/api.js` so a single file changes if P5 finalizes differently; the SSE event names/data are already frozen by P0.
- **[Tailwind CDN unpinned/offline]** — CDN version drift or no network for an air-gapped tester. Accepted for a POC; escalate to a vendored P0 asset only if it becomes a problem.
- **[No auth/session expiry handling]** — an expired session token surfaces only as a backend `error` event, shown inline. Acceptable for QA; not a production login.
- **[Web-only cost card hidden on mobile]** — intentional per spec; per-message cost/latency still visible everywhere so no data is lost on mobile.
