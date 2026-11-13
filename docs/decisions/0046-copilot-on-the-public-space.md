# 0046: The copilot on the public Space: keys from the Space's secrets, a fast status, limits that protect the key

Date: 13 Nov 2026. Status: accepted (team request: the copilot should work on https://rohti-logimind.hf.space with
Groq's free tier, the key set by the team as a Space secret).

## Problem
- Hosted keys were read only from the git-ignored `backend/.env` file (decision 0032), never from the environment,
  so a Space secret `GROQ_API_KEY` was ignored: the live Space said "GROQ_API_KEY is empty in backend\.env".
- The status check could take seconds (the provider probe used the 30 s completion timeout) and the console showed
  "server isn't answering" when a request failed, which is wrong for a slow copilot check.
- Anyone with the demo link uses the server's key, so the free tier could be used up by one visitor.

## Decision
- `LOGIMIND_LLM_KEYS_FROM_ENV=1` (exactly "1") lets `GROQ_API_KEY`, `GROQ_MODEL`, `GEMINI_API_KEY`, `GEMINI_MODEL`
  come from the process environment (a host's secret store); a non-empty environment value wins over the file.
  Base-URL overrides still come only from the file, so the key can only go to the provider. Without the switch
  nothing changes: a stray global variable is never picked up. `hf-space/app.py` sets the switch,
  `LOGIMIND_LLM_PROVIDER=groq` and `GROQ_MODEL=llama-3.3-70b-versatile` as defaults (Space variables win). The key
  itself exists only as the Space secret.
- `GET /api/copilot/status` returns `state`: `ready`, `not_configured` (no provider, key or model: no network call
  at all) or `unavailable` (set up, but the check failed), plus `max_message_chars`. The provider check uses a 5 s
  timeout (`PROBE_TIMEOUT_S`) and is cached as before (5 min when it works, 30 s when not); completions keep 30 s.
- Console: the status request gives up after 15 s with its own message ("The copilot check took too long", with
  "Check again"), never the "server isn't answering" text. `not_configured` shows one line: "Copilot needs a model.
  Plans and replans still work from the Plans page." The input's length limit comes from the server.
- Limits (`app/copilot/limits.py`) on calls that reach a model (chat, test, models; not status or confirm): per
  client IP and per chat session 5/min, whole server 12/min and 300 per UTC day, messages at most 500 characters.
  On by default only with `LOGIMIND_PUBLIC_DEMO=1`; elsewhere off and 2000 characters. All four are settings
  (`LOGIMIND_COPILOT_PER_CLIENT_PER_MIN`, `_PER_MIN`, `_PER_DAY`, `_MAX_CHARS`; 0 = off). A refusal is a 429 with
  `Retry-After` and a plain sentence that plans and replans still work.
- Client IP: the right-most public address in `X-Forwarded-For` (the host's own proxies use private addresses;
  entries further left can be typed by the caller), else the socket address.

## Limits
- The per-IP limit depends on how Hugging Face's proxies fill `X-Forwarded-For`; if they ever hide the client, all
  visitors share one bucket (stricter, not looser). The server-wide minute and day caps hold regardless, and they
  are the real protection of the key's quota. Session ids are chosen by the browser, so the per-session limit is
  only a convenience.
- Limits live in the one server process and reset when the Space restarts.
- Groq's free tier has its own limits; a 429 from Groq is shown as what it is (decision 0032).
