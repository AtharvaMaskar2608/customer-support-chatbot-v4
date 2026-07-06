## Why

QA testers need a lightweight browser UI to exercise the Choice FinX support chatbot end-to-end: log in with a client code + session token, ask a knowledge-base question, and watch the agent stream its intermediate steps, output tokens, citations, and per-message cost/latency. This is P8, a static POC frontend that consumes the already-defined SSE/session contract (P0 `data-contracts`) and the endpoints served by P5 (`api-sse-session`). It ships no backend of its own — it is a thin, disposable testing surface, not a production client.

## What Changes

- Add a static, dependency-light frontend under `frontend/` only (plain HTML/CSS/JS + Tailwind via CDN). No build step, no framework, no bundler.
- **Login page**: two inputs — client code and session token — both trimmed/stripped on submit; `POST /session`; on success store the returned session id and navigate to the chat view; on failure show an inline error.
- **Chat view**: a message input box; on send, open an SSE stream to `POST /chat` and consume `SseEvent`s:
  - `status` → render as a transient "thinking" step line ("Looking up the knowledge base…", "Generating the answer…") that is replaced/cleared once tokens arrive.
  - `token` → append `text` to the current assistant message as it streams.
  - `citations` → render a hoverable citation card at the END of the assistant message, showing each citation's topic / section / question / source.
  - `usage` → show that message's cost (INR) and latency (ms) directly under the message, and update the top-left cumulative-cost card from `cumulative_cost_inr`.
  - `done` → finalize the message; `error` → surface an inline error and stop the stream.
- **Cumulative cost card**: a WEB-ONLY (hidden on narrow/mobile viewports) card fixed in the TOP-LEFT showing the running conversation cost in INR.
- Responsive, minimal white & blue theme; mobile compatible.
- Document a manual QA checklist (and an optional Playwright smoke test) as the done condition.
- NOT in scope: any backend code, agent loop, retrieval, report tools, tracing, or evals. This change only reads the P5 endpoints and the P0 contracts.

## Capabilities

### New Capabilities
- `frontend-poc`: a static Tailwind login + streaming-chat UI for QA testers that consumes the `POST /session` and SSE `POST /chat` endpoints — rendering streamed status steps, output tokens, hoverable citations, per-message cost/latency, and a web-only cumulative INR cost card, in a responsive white/blue theme with error handling.

### Modified Capabilities
<!-- None — this change adds a new frontend capability and modifies no existing spec. -->

## Impact

- New files only, entirely within `frontend/` (the directory placeholder created by P0 `foundations-and-contracts`). Files added: `frontend/index.html` (login), `frontend/chat.html` (chat view), `frontend/css/app.css` (small theme overrides on top of Tailwind), `frontend/js/config.js` (backend base URL), `frontend/js/api.js` (`/session` + `/chat` SSE client), `frontend/js/login.js`, `frontend/js/chat.js`, `frontend/README.md` (run + manual QA checklist), and optionally `frontend/tests/smoke.spec.js` + `frontend/playwright.config.js`.
- Consumes P0 contracts (`SseEvent`, `Citation`, `UsageCost`, `SessionContext`) and P5 endpoints (`POST /session`, `POST /chat`). No contract or endpoint is defined here.
- MUST NOT modify `pyproject.toml`, `.env`/`.env.example`, any root config, or any `backend/` directory. The one non-obvious dependency (Tailwind) is delivered via CDN so no dependency manifest changes are required; if an offline/pinned Tailwind build is later desired, that is a P0 addition, not a change here.
- No dependency manifest, migration, or lockfile changes.
