# 0032: Optional hosted LLM providers for the copilot (Groq, Gemini)

Date: 10 Nov 2026. Status: accepted (asked for by the team). Changes CLAUDE.md invariant 12 and extends decision 0014.

## Decision
- **Zero-cost rule, relaxed:** optional **free-tier** hosted providers are allowed for the copilot. **Local Ollama stays
  the default**, the **tests never need the network**, and **keys live only in `backend\.env`** (git-ignored).
  Nothing else in the project may need a paid or key-gated service.
- **Providers** (`backend/app/copilot/llm.py`, `LOGIMIND_LLM_PROVIDER`): `ollama` (default), `groq`, `gemini`, `none`.
  `FakeLLM` stays the test provider and is never selected by configuration.
  - **Groq:** OpenAI-compatible `POST /openai/v1/chat/completions` with `response_format: {type: json_schema}`
    (structured outputs), temperature 0, `Authorization: Bearer` header. Availability probe: `GET /models`.
  - **Gemini:** `POST /v1beta/models/{model}:generateContent` with `responseMimeType: application/json` and
    `responseJsonSchema`, temperature 0; the key goes in the `x-goog-api-key` header, never in the URL (URLs are
    logged). Probe: `GET /models/{model}`.
  - Plain httpx (already a dependency); no new packages. The intent schema is sent without Pydantic's
    OpenAPI-only `discriminator` keyword.
- **Settings:** `GROQ_API_KEY`, `GROQ_MODEL`, `GEMINI_API_KEY`, `GEMINI_MODEL` are read from the `backend\.env`
  **file only**: a key in the global environment is ignored (tested), which also avoids the "global API key"
  mistake CLAUDE.md warns about. The model name is required (no hidden default). `.env.example` lists them empty.
  `LOGIMIND_GROQ_BASE_URL` / `LOGIMIND_GEMINI_BASE_URL` may point only to localhost (a local fake server for
  checks); any other host is refused so a typo can never send the key elsewhere.
- **Invariants kept:** the LLM still returns only one Pydantic `IntentEnvelope` (`extra="forbid"`, no route fields),
  with one retry and then the clarifying question (tested with the hosted adapter: exactly two calls, and a reply
  carrying a `routes` field is rejected); replies are templates over tool outputs with the grounding check.
- **Keys never leak:** not in `repr`, not in error messages (scrubbed even if a provider echoes it), not in logs
  (tested with captured logs), not in `/api/copilot/status` or chat replies (tested), never sent to the browser,
  so never in localStorage.
- **Errors as what they are:** 401/403 (and Gemini's 400 `API_KEY_INVALID`) = "{Provider} key missing or
  rejected"; 429 = "rate limit reached" with `Retry-After`; timeouts and connection errors = "could not be reached";
  5xx = "server problem"; 404 = unknown model. A missing key or model needs no request. Chat replies:
  `unavailable` for key problems, `error` for the rest, never a crash. The status is cached (5 min when working,
  30 s when not) and a rejected key updates it at once.
- **Console:** the copilot panel and page always name the provider and model ("groq · <model>", or
  "...: not available"), show the backend's headline (e.g. "Groq key missing or rejected"), and for a hosted model
  say that messages and plan names/ids are sent to the provider, routes are not.

## Why
A copilot that has never answered anything cannot be demonstrated or measured; Ollama is not installed on the team's
laptops. Free hosted tiers let the team try real models without a GPU, while the default and the tests stay local.

## Limits and risks
- Free tiers have small per-minute limits, can change their terms, models and limits at any time, and may use what is
  sent to improve their models. Send only synthetic data. A hosted model's accuracy is still **NOT RUN** until the
  team measures it on the frozen evaluation set.
- Model support for schema-constrained output differs per model; a model without it gives a plain
  "refused the request (HTTP 400)" message. Pydantic validation stays the real check either way.
- Docker Compose does not pass these settings (it has no `backend\.env`); hosted providers are for local use.

## Tests
`backend/tests/test_llm_providers.py` (21, fake HTTP layer through `httpx.MockTransport`, no network);
`frontend/src/test/providers.test.jsx` (3).

## Checked in a real browser (10 Nov 2026, Chrome via Claude in Chrome)
Set-up: a scratch clone of this commit with its own `backend\.env` (`LOGIMIND_LLM_PROVIDER=groq`, a fake key,
`GROQ_MODEL=fake-groq-model`, `LOGIMIND_GROQ_BASE_URL=http://127.0.0.1:8097/v1`) and a local **fake Groq server**
(OpenAI-compatible, accepts only the fake key, picks intents by keywords; not a language model). So the real
`GroqLLM` code, the agent and the console ran end to end; only the "model" was fake. The developer's own
`backend\.env` was not changed.
- Panel and page showed "groq · fake-groq-model" and the note on what is sent to the provider.
- "explain the latest plan" → answer from the `explain` tool; "re-run … with OR-Tools" → a new validated plan.
- A breakdown request → "needs confirmation"; **Cancel** → "Cancelled. The plan was not changed."; again → **Confirm**
  → the replan ran and was reported honestly as NOT feasible (one vehicle could not carry the orders).
- "move customer 3 to vehicle 2 by hand" → refused (the fake chose `refuse`; this checks the path, not a model).
- A 429 from the provider → "Groq rate limit reached (HTTP 429); try again in 20 s".
- Wrong key → "Groq key missing or rejected (HTTP 401)"; empty key → "Groq key missing or rejected: GROQ_API_KEY is
  empty in backend\.env" (page and docked panel); provider down → "Groq not reachable". Input disabled each time.
- No key in the status reply, the page or localStorage; neither test key in the API's logs. The fake server saw
  `response_format: json_schema` and temperature 0 on every call.
- Found and fixed: the hosted reason ran into the next sentence (missing full stop).
- **Not checked:** the real Groq or Gemini service (no key is set in the developer's `backend\.env`); Gemini in the
  browser at all (unit tests with the fake HTTP layer only); answer quality of any real model.
