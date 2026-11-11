# 0036: Copilot settings need only an API key

Date: 10 Nov 2026. Status: accepted (asked for by the team). Builds on decisions 0032, 0033 and 0035; replaces 0035's
"first model of the sorted list" rule. **Amended 11 Nov 2026: OpenAI removed from the console (see "Amendment").**

## Decision
- **One field by default:** "API key" (password field; browser autofill off: `autocomplete="new-password"`, password
  manager ignore attributes, `autocomplete="off"` on the form). Provider, model, Load models, base URL and a manual
  Test connection are under a collapsed **"Advanced (optional)"**. The box opens by itself while nothing is set.
- **Provider from the key's prefix, in the browser, before anything is sent** (OpenAI: see the amendment) (`frontend/src/lib/keyDetect.js`):
  `gsk_` Groq; `AIza` Gemini; `sk-or-` OpenRouter (OpenAI-compatible, `https://openrouter.ai/api/v1`); `sk-ant-`
  Anthropic: **"Anthropic keys are not supported yet: LogiMind has no Anthropic adapter, so nothing was sent."**;
  `sk-proj-` / `sk-` OpenAI (OpenAI-compatible, `https://api.openai.com/v1`). Surrounding spaces and one pair of quotes
  are removed. An **unknown prefix** shows a small service choice and sends nothing until one is picked; "another
  OpenAI-compatible service" also needs its base URL first, so the key can never go to OpenAI by default. **A key is
  never tried against several providers**: one test, to one provider.
- **Test a moment after pasting** (0.7 s after the field stops changing) **or on Enter**; the result is **one plain
  sentence**: "Works: Groq is ready." or the server's reason, e.g. for a 401 "Groq rejected this key. Check that the
  whole key was copied, with no spaces or quotes." LogiMind's own server not answering ("LogiMind's own server is not
  answering, so the key could not be tested. Start LogiMind with start-dev.bat, then try again.") is told apart from
  the provider ("Groq could not be reached from the LogiMind server (ConnectError); check the internet connection or
  try again later."). A successful test sets the panel's status to ready at once, so no stale "not available" badge
  stays.
- **Model chosen automatically** from the provider's list (one list call, same guard and limits): a model the provider
  marks as free first (OpenRouter ids ending in `:free`), then a short list of well-known chat models per provider
  (Groq `openai/gpt-oss-20b`, `openai/gpt-oss-120b`, `llama-3.3-70b-versatile`, `llama-3.1-8b-instant`; Gemini
  `gemini-2.5-flash`, `gemini-2.0-flash`, `gemini-2.5-flash-lite`, `gemini-1.5-flash`; OpenAI `gpt-4o-mini`,
  `gpt-4.1-mini`, `gpt-4.1-nano`, `gpt-4o`, `gpt-4.1`), then the first chat model of the sorted list. The non-chat
  filter now also drops completion-only and special OpenAI models (babbage, davinci, realtime, computer-use,
  search-preview, codex, sora, turbo-instruct, gpt-image). The chosen model is remembered for the tab and shown in one
  small line: "Model: X (chosen automatically[, free])".
- **Server side:** providers `openrouter` and `openai` (default base `https://api.openai.com/v1` when no base URL is
  sent; another host = "OpenAI-compatible service"), named OpenRouter / OpenAI in messages by host; `anthropic` is
  refused with the sentence above (400). The operator may point OpenRouter/OpenAI at a local fake with
  `LOGIMIND_OPENROUTER_BASE_URL` / `LOGIMIND_OPENAI_BASE_URL` in `backend\.env` (localhost only, like decision 0032);
  any other value is ignored.
- Unchanged: the key stays in sessionStorage for the tab, goes to our server only in the `X-LLM-Key` header, and is
  never stored, logged, returned or put in a URL; the outbound guard, https, timeouts and size cap apply to every call.

## Amendment (11 Nov 2026): OpenRouter kept, OpenAI not offered
CLAUDE.md invariant 12 (zero cost) allows only hosted providers with a free tier. OpenRouter has free models (`:free`)
and stays. OpenAI has no free tier, so the console no longer offers it:
- A key starting `sk-proj-` / `sk-` (other than `sk-or-` and `sk-ant-`) is refused in the browser with "OpenAI keys
  are not offered: OpenAI has no free tier and LogiMind stays free to run, so nothing was sent. Use Groq, Gemini or
  OpenRouter." No request is made.
- "OpenAI" is gone from the unknown-key service choice and from the Advanced provider list. The `openai` adapter
  remains only as **"Another OpenAI-compatible service (needs its base URL)"**; with no base URL the console sends
  nothing ("Enter the service's https base URL first; nothing was sent."), so a key never goes to OpenAI by default
  from the console. That option is opt-in and nothing needs it.
- Server side unchanged: the backend `openai` provider still defaults to `https://api.openai.com/v1` when called
  without a base URL (only reachable by a hand-made request with the tenant's own key, or by `backend\.env`). The
  README's provider table and CLAUDE.md invariant 12 were updated to match.
- Tests: `frontend/src/test/copilotSettings.test.jsx` (OpenAI key refused with nothing sent; no OpenAI choice; the
  compatible service sends nothing without a base URL).

## Limits
- Prefixes are conventions, not guarantees; a service may change them. Any other key gets the service choice.
- The preferred-model lists will age; when none is offered the first chat model is used, and Test connection says
  which. "Free" is only what a provider marks; OpenRouter's free models have their own limits and may not support
  schema-constrained output (the copilot then falls back to its clarifying question).

## Tests
Backend `tests/test_copilot_keyonly.py` (each provider's list endpoint and chosen model, Anthropic refused with nothing
sent, the 401 sentence per provider, provider outage, chosen model used in the chat, choice order, defaults and the
operator override); updated expectations in `test_copilot_models.py` / `test_copilot_settings.py` (new 401 sentence,
new choice). Console `src/test/copilotSettings.test.jsx` (each prefix, unknown prefix, custom service needs a base URL,
Anthropic, plain failures, server down vs provider down, stale badge cleared, autofill off, Advanced, Clear key,
sign-out) and `src/test/copilotModels.test.jsx`.
