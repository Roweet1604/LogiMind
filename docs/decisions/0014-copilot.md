# 0014: Dispatch copilot (P8, backend)

Date: 4 Nov 2026. Status: accepted (decided unattended by Claude Code).

## Decision
- **Package** `backend/app/copilot/`. It contains `schemas.py` (the intents), `llm.py` (provider interface, fake, Ollama), `tools.py` (the six tools), `explain.py` (reply templates and the grounding check) and `agent.py` (the LangGraph graph, sessions and confirmation). The endpoints, all needing an API key and tenant-scoped, are `GET /api/copilot/status`, `POST /api/copilot/chat` and `POST /api/copilot/confirm`.
- **The LLM only parses.** It returns one `IntentEnvelope` as schema-constrained JSON (Ollama `format=<JSON schema>`, temperature 0). The intents are solve / validate / compare / explain / reroute / clarify / refuse, and every model uses `extra="forbid"`. **No schema has a route, stop or vehicle-assignment field**, so the LLM cannot hand the system a plan (tested). Plans come only from the solver tools and the validator.
- **Pydantic validation, one retry, then a clarifying question.** On invalid output the LLM gets exactly one more call with the error. A second failure ends in a fixed clarifying question (tested: exactly two calls).
- **Tools** (`tools.py`), tenant-scoped through `PlanService`:
  - `solve_with_ortools`, `solve_with_ga` (GA + local search) and `run_hybrid` re-solve an existing plan's orders as a NEW plan.
  - `validate_routes` re-runs the validator on stored routes.
  - `compare_results` adds a fairness note when the orders or budgets differ, and names the shortest feasible plan only when the orders are the same.
  - `reroute` uses the P7 replan.
  - `explain` (a helper, not one of the six) reads a plan's stored outputs.
  - A plan still running at the wait limit is reported as running, never as done.
- **Grounded replies.** Replies are templates filled from tool outputs; the LLM writes no free text. `ungrounded_numbers` blocks any reply containing a number that no tool output contains. Free LLM phrasing is left out on purpose, because small local models invent numbers. This can be revisited, with the same check kept.
- **Clarify** when the LLM chooses it, when the referenced plan is not in the tenant's account (the reply lists recent plans) or after two invalid outputs. **Refuse** when the LLM chooses it (e.g. hand-editing routes, other topics); a refusal lists what the copilot can do.
- **Confirmation.** `reroute` changes an active plan, so it is held as a pending action with an id and runs only after `POST /api/copilot/confirm` with `approve=true`. A wrong id, a second confirm, a cancel or any new message in the session drops it; all tested. Solving creates a new plan and leaves the old one alone, so it needs no confirmation.
- **Provider-agnostic interface** (`llm.py`):
  - `FakeLLM` is deterministic, scripted or a callable; tests only.
  - `OllamaLLM` uses langchain-ollama and is used only if the Ollama server answers and has the model. Otherwise it reports e.g. "no local model available: Ollama is not running at http://localhost:11434 ... run `ollama pull llama3.2:3b`".
  - `NoLLM` covers `LOGIMIND_LLM_PROVIDER=none`, which the tests use.
  - With no model, chat replies `kind: "unavailable"` with that plain reason. No paid or key-gated provider exists in the code.
- **Sessions** are in memory, keyed by (tenant, session id), so one tenant cannot confirm another's pending change (tested). The last 10 messages are kept, and the history stores only the parsed intents, not tool data. The system prompt lists only the caller's 15 newest plans.
- New dependencies, free and open source: `langgraph`, `langchain-core`, `langchain-ollama` (pulls in `ollama`).

## Not verified
- **No real model was run.** Ollama is not installed on this laptop (checked: nothing on port 11434). Every copilot test uses the fake LLM, so how well llama3.2:3b or qwen2.5:7b turns instructions into intents is unknown. The draft evaluation set (`docs/eval/copilot_instructions_DRAFT.json`) has not been run.
- Chat calls block until the solver finishes (budget x 1.5 + 20 s at most).
