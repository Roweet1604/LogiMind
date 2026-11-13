# 0042: Scripted copilot stand-in for demos without a model (LOGIMIND_LLM_PROVIDER=scripted)

Date: 13 Nov 2026. Status: accepted (asked for by the team: the copilot showed "No local model is available" and a
demo was due, with no paid or external key).

## Context
The only fake model was `FakeLLM`, which the tests set directly and `.env` cannot select (decision 0014). No file
in the repository produced the "fake-scripted" model name; the report figure with that label was made outside it.

## Decision
- New provider `scripted` (`ScriptedLLM` in `backend/app/copilot/llm.py`), selected with
  `LOGIMIND_LLM_PROVIDER=scripted` in `backend/.env`. It is **not a language model**: fixed rules turn a few phrasings
  into one intent (vehicle breakdown with "after its first / N stops", failed delivery with or without retry, solve
  with an engine, validate, explain, compare). "Move/edit/assign" requests are refused, and anything else gets a
  clarify question listing what it understands. "The latest plan" is the first plan in the prompt's list.
- It is labelled as what it is: the console shows "scripted · fake-scripted", and the status reason says "scripted
  demo stand-in, not a language model". It is never shown as Ollama.
- Its output takes the same path as a real model's: schema validation, the tools, the solver and the validator, and
  the user's confirmation before a replan. It has no field for routes, the same as any model (invariant 1).
- The default stays `ollama`. Tests run offline as before.

## Limits
- It understands only the phrasings above; anything that is not a fixed rule needs a real model (Ollama or a free
  hosted key, decisions 0032-0033).
- Report figures made with it must say it was the scripted stand-in, not a model.
