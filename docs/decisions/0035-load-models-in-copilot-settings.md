# 0035: "Load models" in the Copilot settings box

Date: 10 Nov 2026. Status: accepted (asked for by the team). Extends decision 0033.

## Decision
- **Button and dropdown:** "Load models" saves the tab's settings (the key stays in sessionStorage as before) and calls
  `POST /api/copilot/models` with the same `X-LLM-*` headers. On success a dropdown "Available models (N)" appears;
  picking a model fills the model name and runs **Test connection** at once, with the result in plain words. The text
  field always stays as the fallback: a list that cannot be fetched shows its plain reason (Key rejected, Rate limit
  reached, Not reachable, Address not allowed, Settings not accepted, or "no chat models") plus "You can still type the
  model name."
- **List endpoints** (one call, through the same code path as every provider call: guard and pinning for console
  addresses, https, no redirects, 5 s connect / 30 s read, 1 MB cap): Groq and OpenAI-compatible `GET {base}/models`
  (`data[].id`); Gemini `GET /v1beta/models?pageSize=1000`, models whose `supportedGenerationMethods` contain
  `generateContent`, without the `models/` prefix (key in the `x-goog-api-key` header, never the URL); Ollama
  `/api/tags`.
- **Chat models only:** ids containing embed, whisper, tts, guard, moderation, dall-e, imagen, image-generation,
  transcri, speech, audio, aqa, rerank, playai or orpheus are left out; names are trimmed, de-duplicated, printable,
  at most 200 characters, sorted, at most 500. The server returns names only, or `ok: false` with a kind and a plain
  message; never the key (scrubbed even if a provider echoes it).
- **Empty model name:** for settings chosen in the console (decision 0033) with no model name in the box **and** none
  in `backend\.env` for that provider, the server lists the models and uses the **first chat model of the sorted
  list**, and says so: "No model name was given, so X was chosen (the first chat model in its list)." The console then
  writes that name into the field and saves it for the tab, so the following requests use the same model. Settings in
  `backend\.env` alone still need a model name (decision 0032 unchanged).
- A typed model name is never replaced; a name that is not in the provider's list still gives "Model not found".

## Why
Model ids are long and change often; picking from the provider's own list avoids typos, and an empty name should not
be a dead end.

## Limits
- "First in the sorted list" is a deterministic choice, not a judgement of which model is best or cheapest. On a paid
  OpenAI-compatible service, check the chosen model's price.
- The chat-model filter is a list of name fragments; a new kind of non-chat model may slip through (Test connection
  then shows what happens), and Gemini's list is read up to 1000 models.

## Tests
`backend/tests/test_copilot_models.py` (14, fake HTTP layer and fake DNS: Groq, Gemini and OpenAI-compatible lists,
guard and metadata address, 401/429/network/1 MB/redirect/empty list, no key, automatic choice through test, status
and chat, a typed name never replaced, Ollama, cleaning and limit); `frontend/src/test/copilotModels.test.jsx` (7).

## Checked in a real browser (10 Nov 2026, Chrome via Claude in Chrome, fake Groq server)
Wrong key → "Key rejected … You can still type the model name." (no dropdown); working key → "2 chat models found"
(a speech and a guard model were filtered out); picking `fake-groq-model` → field filled and "Works" at once; empty
name → "another-chat-model was chosen (the first chat model in its list)" and written into the field;
OpenAI-compatible at `https://169.254.169.254/v1` → "Address not allowed", nothing sent; provider down → "Not
reachable". No key in localStorage, the page or the API's logs. Not checked: a real provider's list, Gemini's list in
the browser, Ollama's list in the browser (no Ollama installed).
