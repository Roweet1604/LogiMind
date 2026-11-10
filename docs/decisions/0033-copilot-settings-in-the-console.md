# 0033: Copilot settings in the console (provider, model, key) and an outbound-request guard

Date: 10 Nov 2026. Status: accepted (asked for by the team). Extends decision 0032 (which kept keys only in
`backend\.env`): a key may now also be pasted in the console for one browser tab.

## Decision
- **Where:** a "Copilot settings" box in the docked copilot panel and on the Copilot page. Provider: server settings
  (`backend\.env`, the default), Ollama (local), Groq, Gemini, OpenAI-compatible (with a base URL field). Model name,
  key (password field), **Test connection**, **Clear key**.
- **Key in the browser:** `sessionStorage` for the tab only (key `logimind.llm`), never `localStorage`, never in a URL.
  After it is saved the field is emptied and only the last 4 characters are shown. Signing out clears it.
- **Key to the server:** headers on copilot requests only (`X-LLM-Provider`, `X-LLM-Model`, `X-LLM-Base-URL`,
  `X-LLM-Key`; not on confirm, which needs no model). The server reads them by hand (a typed FastAPI parameter would
  echo a refused value in its 422 reply), builds the LLM for that one request and keeps nothing: not stored, not logged,
  not audited, not returned, scrubbed from provider error texts (all tested). Header limits: provider 20, model 200,
  base URL 500, key 512 printable ASCII characters; a refused header gets a plain 400 that never repeats it.
- **Precedence:** console settings win field by field; empty fields fall back to `backend\.env` (key and model of the
  same provider). No provider chosen = the server's own settings, unchanged.
- **Test connection** (`POST /api/copilot/test`): one minimal call, never a completion (Groq / OpenAI-compatible:
  `GET /models`; Gemini: `GET /models/{model}`; Ollama: `/api/tags`). Returns only `ok`, a `kind` (`ok`, `auth`,
  `model`, `rate_limit`, `network`, `blocked`, `server`, `bad_request`, `bad_response`) and a plain message; the console
  shows "Works", "Key rejected", "Model not found", "Rate limit reached", "Not reachable", "Address not allowed".
- **Outbound-request guard** (`backend/app/copilot/netguard.py`) for every hosted call made with console settings:
  - `https` only; plain http only for the server's own local Ollama URL, which is server configuration (the console
    can choose Ollama and a model, never its URL). No user name/password, query or fragment in a base URL.
  - The host is resolved (an address typed as the host is used as is) and **every** address must be public: private,
    loopback, link-local (incl. 169.254.169.254 metadata), CGNAT (100.64/10, e.g. 100.100.100.200), multicast,
    reserved, unspecified, IPv6 ULA (fd00:ec2::254) and IPv4-mapped forms are refused **before** anything is sent.
  - **DNS rebinding:** the connection is pinned to the checked address (a custom httpcore network backend; TLS still
    verifies the real host name), and every call checks again.
  - No redirects are followed (a redirect is an error); connect timeout 5 s, read timeout 30 s; answers over 1 MB are
    refused while streaming.
  - Groq and Gemini chosen in the console use their public addresses through the same guard. Only an operator's
    `LOGIMIND_GROQ_BASE_URL` / `LOGIMIND_GEMINI_BASE_URL` in `backend\.env` may point to localhost (decision 0032);
    that is server configuration, not console input.
- **Invariants kept:** the per-request LLM goes through the same agent: one Pydantic intent, no route fields, one retry
  then a clarifying question, replies from tool outputs only (tested with console settings). Tenant isolation: a
  tenant's settings never reach another request (nothing is stored), and another tenant's plan id is still not found
  (tested).

## Why
The team wants to try hosted models without editing a file on the server. Pasting a key into a web page and sending
it to the server is safe only if the server never keeps it and cannot be used to reach internal addresses.

## Risks and limits
- Anyone who can use the console can make the server call a public https address of their choice (limited to the
  model-list and chat paths of an OpenAI-compatible API, with the guard above). Acceptable for a single-team
  deployment; a shared deployment should add an allow-list of provider hosts.
- `sessionStorage` is readable by scripts on the console's own origin; the console loads no third-party scripts.
- Paid OpenAI-compatible services charge per message; free tiers have small limits. Messages and plan names and ids
  go to the provider (routes do not). The README says so.
- The pinned transport sets the private `_pool` attribute of `httpx.HTTPTransport` (httpx 0.28.1, httpcore 1.0.9);
  an httpx upgrade must re-run `tests/test_copilot_settings.py`.

## Tests
`backend/tests/test_copilot_settings.py` (SSRF attempts: 169.254.169.254, 10.x, 127.0.0.1, metadata.google.internal,
a host resolving to 192.168.x, a host with one public and one private address, IPv6 ULA, IPv4-mapped; pinning;
DNS change between calls; redirects; 1 MB cap; plain results; key never in replies, logs or audit; precedence;
invariants; tenant isolation). `frontend/src/test/copilotSettings.test.jsx`.
