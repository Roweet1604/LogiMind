# LogiMind: kickoff prompt pack

Three prompts, in the order you will use them:

- **Prompt A** starts the build (paste it into Claude Code or a Claude Project chat).
- **Prompt B** revises the review deck.
- **Prompt C** is the handoff template for when a session ends or hits a usage limit.

## Setup checklist (do this once, before Prompt A)

1. Create a new empty folder, for example `logimind/`, and open it in VS Code. Install Claude Code, run `claude login`, and sign in with the Pro account.
2. **Do not set `ANTHROPIC_API_KEY` as a global or system environment variable.** If that variable exists, Claude Code bills the API instead of your Pro plan. The copilot needs no key at all: it runs on a local model (see item 7).
3. Create `docs/context/` and put these in it: the pivot message you wrote (save it as `PIVOT.md`), `Capstone_Review_2.pptx`, the Product Guide PDF, the `measured_evidence.zip`, and the unzipped `route-optimization-v3` folder as `docs/context/prior-code/`.
4. Optional but recommended: in claude.ai, create a **Project** called LogiMind and add the same files as project knowledge, so chat sessions have the context too.
5. Fill in the TEAM INPUTS block in Prompt A. Anything you leave blank, the agent must ask about; it must not guess.
6. Run Prompt A. After the agent's Phase 0 answers, run each later phase in its own session and commit after each one.
7. The copilot needs an LLM at runtime. Install Ollama and pull a small open model such as `qwen2.5:7b-instruct` or `llama3.1:8b` (use `llama3.2:3b` if a laptop has little free RAM). No API key and no paid service is used anywhere in this project.

---

# PROMPT A: Project kickoff

```
# ROLE
You are a principal software engineer, optimization engineer and applied-ML/LLM engineer working with a three-person final-year student team. You will plan and build "LogiMind" in the repository open in this workspace. Do the work: inspect files, write code, run it, test it, fix it. Do not just describe what you would do.

# 0. TEAM INPUTS (the team fills these in; if any line is blank, ASK me in your first reply and do not assume)
- Weeks remaining until final submission: [  ]
- Next review / demo dates: [  ]
- Team: Rohit Raj, Pragya, Ishika. Who owns which workstream: [  ]
- Pilot operator(s) with real delivery data (yes / no / maybe, and what data): [  ]
- LLM access for the copilot at runtime: local model only (Ollama). No API keys, no paid providers.
- Docker available on all laptops? Can we self-host OSRM? Cloud budget: zero. Everything runs on laptops via Docker Compose. [  ]
- Messaging for ETA notifications: stub only, no real provider (no spending).
- What the mentor (Dr. M. Selvam) expects as final deliverables (report, demo, paper, deployed system): [  ]

# 1. THE PRODUCT
Project: Capstone Project - I (7CS1999), batch ASAC-CP-056, Alliance School of Advanced Computing.
Title: "LogiMind: An API-First Hybrid Optimization Platform with an AI Dispatch Copilot for Small-Fleet Logistics".

Why this exists: our Review 2 (16 Oct 2026) was a comparative study of Google OR-Tools and a custom genetic algorithm (GA) for vehicle routing. Reviewers said it was "just a comparative study, not up to capstone level", wanted more features, preferred GenAI/LangChain over plain model training, and asked for a new title. We are turning it into a sellable, industry-acceptable product, not just a dashboard. Reference products: Locus, Routific, OptimoRoute. Target customers: small and mid-sized fleets (local distributors, courier franchises, institutional transport).

Pitch: no single solver wins everywhere, so LogiMind chooses, combines and explains solvers automatically, and a dispatcher can control it in plain English.

What we are building (all eight):
1. Hybrid solver: OR-Tools solutions seed the GA population (memetic approach), alongside the standalone OR-Tools and GA engines.
2. ML solver selector: instance features (customer count, demand variance, spatial clustering, time-window tightness, and the time budget) predict which engine wins. Training data comes from our own benchmark runs.
3. AI dispatch copilot: a LangChain/LangGraph agent with tools such as solve_with_ortools, solve_with_ga, run_hybrid, validate_routes, compare_results and reroute. It turns natural-language instructions into structured constraints (Pydantic schemas) and explains why a plan or solver was chosen.
4. API-first core: FastAPI with OpenAPI docs (POST /plans, POST /plans/{id}/replan, webhooks), CSV/Excel order import, authentication, multi-tenant data separation, Docker deployment, tests and logging.
5. Real road-network distances and travel times from a self-hosted OSRM in Docker on a free OpenStreetMap regional extract (for example Karnataka from Geofabrik), instead of straight-line distances. Haversine times a detour factor is the flagged fallback.
6. Dynamic replanning on breakdowns, failed deliveries and urgent orders, using warm-started re-optimization.
7. Driver mobile web app (PWA): stop list, navigation deep link, delivered/failed marking, proof-of-delivery photo.
8. Customer ETA notifications through a stub adapter that writes to the console and a log table (optionally a free Telegram bot or a local SMTP sink such as MailHog as a demo channel), and a chat interface for the copilot. A basic ops console is fine: the product is the API plus the workflow, not a dashboard.

DESIGN RULE: the LLM never generates routes. The solvers remain the source of truth. The LLM only translates, orchestrates and explains.

# 2. WHAT ALREADY EXISTS (inspect it; trust the code over the old deck)
A working baseline is in docs/context/prior-code/ (a FastAPI + React app, "route-optimization v3"). Read its README first. Facts:
- Backend (Python): shared Instance model with a distance matrix, OR-Tools adapter (guided local search, scaled integer costs, a total time budget that includes model build), our own GA (giant-tour permutation + optimal split decoder, order crossover, tournament selection, three mutations, elitism, nearest-neighbour seeding, repair through the split, fleet-size penalty), an independent route validator, shared metrics, a runner, a benchmark CLI, a single-worker job store with JSON-file persistence, and a REST API. 54 backend tests and 13 frontend tests passed.
- Frontend: React + Vite (JavaScript/JSX), Tailwind, Leaflet, Recharts, seven pages.
- What it does NOT have (the old deck claimed some of this; the code is the truth): NO time windows (it is CVRP only), NO Solomon/Gehring-Homberger/CVRPLIB import, NO best-known gaps, NO road distances (straight-line haversine only), NO auth, NO tenants, NO database, NO LLM, NO selector, NO hybrid, NO replanning. The GA is NOT the Zhu (2022) design with savings-based initialization and adaptive rates; it uses nearest-neighbour seeding and fixed rates.
- Measured findings (1-CPU sandbox, 10 s budget, synthetic haversine instances, 3 GA seeds, 2 OR-Tools repeats; re-measure on real hardware before quoting): GA ties OR-Tools at 50 customers (250.8 vs 252.0 km); OR-Tools is ahead from about 100 customers (GA +4.5% distance at 100, +21.1% at 200, +17.8% at 300, +23.0% at 500). The GA gap shrinks with more time (200 customers: +27% at 2 s, +9% at 60 s). With no nearest-neighbour seeding the GA is +129% worse, so its quality at scale comes mostly from its starting tours.
- IMPORTANT context for the "OR-Tools was 18.2% worse" demo Result B: that was the SAME 50-customer, tightly packed instance as Result A, at a 3-second budget instead of 10 s, on the team's laptop. At 3 s OR-Tools was still on its first plan (321.98 km); at 10 s it matched the GA (246.29 vs 246.54 km). In our sandbox, switching OR-Tools' first-solution strategy to SAVINGS reached cost 487.6 at 10 s, beating every GA run. So the finding is that the winner depends on the time budget, the instance and the OR-Tools configuration. It is not a simple bug. The fix is a systematic tuning audit with multiple seeds, and the selector must treat the time budget as a feature.
- OR-Tools results under a time limit are not strictly repeatable (two default runs differed by about 12 km on one instance). The GA checks its clock only between generations, so tiny budgets on very large instances can overshoot.

# 3. NON-NEGOTIABLE INVARIANTS
1. The LLM never generates, edits or invents routes. Every plan comes from a solver and passes the independent validator before it is shown or stored as "feasible". The LLM only (a) parses instructions into validated schemas, (b) chooses and calls tools, (c) explains results using the tools' own numbers.
2. No infeasible plan is ever presented as a success. Timeouts, "no solution" and provider failures are shown as what they are.
3. Nothing fabricated: no invented results, benchmark values, best-known solutions or pilot data. Synthetic or simulated data is always labelled. Best-known values must come from official sources the team supplies or that you fetch with the URL and date recorded.
4. Fair engine comparisons: same instance, same distance matrix, same objective, the same TOTAL wall-clock budget (set-up included), and one benchmark job at a time.
5. Reproducibility: every run stores seed, configuration, software versions and an instance identity.
6. The hybrid is labelled as a hybrid. The standalone GA stays a real search of its own. Report ablations (OR-Tools seed only, plus local search, and so on) so each component's contribution is visible.
7. Tenant isolation is enforced at the data layer and covered by tests that try to break it.
8. Secrets only through environment variables. Never commit a secret and never ask me to paste one into chat or a file you will commit.
9. Every external service (LLM, OSRM, notifications) sits behind an adapter with a deterministic fake, so tests and CI run offline.
10. When a fallback is used (for example straight-line distance because the road service is down), the plan says so.
11. Never claim something is done if it is not. Keep PROGRESS.md truthful.
12. Zero cost: no paid or key-gated service anywhere in the build. Any new dependency must be free, open source and runnable offline.

# 4. SCOPE
- MUST HAVE: solver core (OR-Tools, GA, hybrid) with time windows; the selector; road matrix; the API; order import; driver PWA; replanning; the copilot.
- STRETCH, only after the must-haves work: customer-facing tracking link, richer ops console, a free demo notification channel (Telegram bot or local SMTP sink). The stub notification adapter is required.
- DEFERRED (future scope, do not build): RAG over policy documents, demand forecasting, carbon estimation, a real SMS/WhatsApp provider (costs money).
- The common CVRP/CVRPTW model, both solvers, the metrics and the demo results stay. The old comparison becomes the "Experimental Evaluation" section and the motivation for the selector.
- The must-have list is large. In Phase 0, compare it honestly against my weeks-remaining figure, tell me what will not fit, and propose a cut line with reasons. I approve the cut line; I do not need to approve ordinary coding decisions.

# 5. STACK (defaults; change only with a written reason in docs/decisions/)
- Backend: Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2 + Alembic (SQLite for development, Postgres in Docker Compose), OR-Tools, our own GA (NumPy allowed), scikit-learn for the selector (gradient boosting or random forest, plus simple baselines), LangGraph/LangChain with `langchain-ollama` (local model) behind a provider-agnostic LLM interface, httpx, structured JSON logging, pytest, ruff.
- Jobs: the simplest durable queue that works in Docker Compose. Benchmark jobs must run strictly one at a time (fair timing); production planning jobs may use a separate worker.
- Auth: per-tenant API keys (stored hashed) for the API; short-lived signed tokens for the console and for driver links; rate limiting; an audit log.
- Distance: a DistanceProvider interface with haversine and self-hosted OSRM implementations (no OpenRouteService, no hosted services), a persistent matrix cache, batching and matrix-size limits. The public OSRM demo server is not meant for production, so use the self-hosted OSRM on a free regional extract.
- Frontend: React + Vite (JavaScript/JSX, as in the baseline), Tailwind, Leaflet with OpenStreetMap tiles (demo traffic only, respect the tile usage policy), vite-plugin-pwa for the driver app. Keep the restrained engineering-tool look: warm neutral background, charcoal text, one teal accent, solid blue for OR-Tools and dashed orange for the GA, compact data, no gradients, glass, glow or decorative widgets. The driver PWA is mobile-first with large touch targets.
- Packaging: Docker Compose (api, worker, database, optional osrm), .env.example, one-command start, README with exact commands.

# 6. PHASES (each ends with passing tests, a commit and a PROGRESS.md update)
P0 Inspect, audit, feasibility, plan. Output CLAUDE.md (the invariants and commands, for future sessions), PLAN.md (phases, cut line, risks), PROGRESS.md, docs/decisions/.
P1 Core model upgrade: add time windows and service times to the Instance model; OR-Tools time dimension; GA handling of time windows (penalty plus repair); validator checks for lateness; metrics for lateness; migrate the baseline into the new repository layout; keep its tests green. Import Solomon (and Gehring-Homberger if time allows) and CVRPLIB instances with the source, license and conversion documented, and a best-known-solutions table with provenance.
P2 OR-Tools audit (this is the reviewers' "fix before next review" item): grid over first-solution strategy x metaheuristic x time budget x seeds on benchmark and synthetic instances; record everything; choose and document defaults per budget class; report run-to-run variation. Do not hide the budget dependence.
P3 Hybrid solver: OR-Tools solution(s) seed the GA population; add local search (relocate, swap, 2-opt) on offspring as a switchable option; compare OR-Tools, GA, hybrid under the equal-clock rule; ablate each component.
P4 Road matrix: DistanceProvider, caching, fallback flagged in the plan, recorded fixtures for tests, travel times (not just distances) feeding the time windows and ETAs.
P5 Selector: feature extraction (including time budget and time-window tightness); a dataset generator across instance families (uniform, clustered, mixed; sizes; capacity and window tightness; budgets); labels = best engine by cost at the stated budget; grouped cross-validation by instance family; baselines (always OR-Tools, always hybrid, random); report accuracy and regret; model card; wire it into POST /plans with engine=auto and return an explanation of the choice.
P6 Platform: POST /plans, GET /plans/{id}, POST /plans/{id}/replan, webhooks (signed, with retries), CSV/Excel order import with a row-level validation report, auth, tenants, database, jobs, OpenAPI docs, structured logging, Docker Compose, tenant-isolation tests.
P7 Replanning: events (vehicle breakdown, failed delivery, urgent order); freeze completed stops; warm start from the current plan (OR-Tools initial assignment from routes; GA seeded from the current plan); record time from disruption to a feasible plan; tests for each event type.
P8 Copilot: LangGraph agent with tools solve_with_ortools, solve_with_ga, run_hybrid, validate_routes, compare_results, reroute; natural language to constrained Pydantic schemas; explanations grounded only in tool outputs; ask a clarifying question when extraction is ambiguous; require confirmation before applying a change to an active plan; refuse unsupported requests; a fake LLM for tests; a chat panel in the ops console. Small local models are weaker at tool calling, so use schema-constrained JSON output, validate everything with Pydantic, retry once on invalid output, and ask a clarifying question if it still fails. Build the evaluation set with the team: hand-written instructions (50 to 100). You may draft candidates, but mark them as drafts for the team to review.
P9 Driver PWA and notifications: installable, offline cache of the stop list; navigation deep link; delivered/failed marking with reason; proof-of-delivery photo (size limits, storage); driver access by signed link; ETA notifier adapters (a stub that logs messages; optionally a free Telegram bot or local SMTP sink; no paid provider), templates and opt-in handling.
P10 Evaluation and report material: run the evaluation plan, produce tables and figures from stored runs, write docs (architecture, API guide, demo script, limitations), and update the deck material.

# 7. EVALUATION PLAN
- Solver quality: optimality gap versus best-known solutions, runtime and constraint violations for OR-Tools, GA and hybrid, on benchmark and synthetic instances, with multiple seeds, the same total budget, and mean, median and spread. Use a significance test when comparing engines over many instances.
- Selector: accuracy and regret on held-out instance families against the baselines.
- Copilot: constraint-extraction accuracy on the hand-written test set (field-level exact match, plus a count of dangerous errors), ambiguity handling, refusal behaviour. Report results for the local model only, with its name and size recorded, and say plainly that results depend on that model. Do not compare against hosted models that were not run.
- Replanning: time from disruption to a feasible new plan (median and 95th percentile) and plan stability.
- Pilot: only if real delivery data exists. Agree on anonymisation and consent first. Compare against the operator's actual routes and report distance and cost savings with caveats. If no pilot exists, say so and use a clearly labelled realistic simulation instead.
- Report negative results honestly.

# 8. QUALITY BARS
Automated tests for every module (validation, solvers, API contract, tenant isolation, replanning, selector pipeline, copilot with a fake LLM, PWA logic); no network in the test suite; input validation everywhere; meaningful error codes; structured logs with request and plan IDs; no secrets in the repository; formatted and linted code; a README that gets a new teammate from clone to running demo in a few commands.

# 9. WORKING RULES
- Preserve working code; evolve the baseline instead of rewriting it without a strong reason.
- Edit files directly; do not paste large code blocks into chat for me to copy.
- Read real errors, fix the cause, rerun the affected tests.
- Make ordinary decisions yourself and record them in docs/decisions/. Ask me only about blockers.
- Keep PROGRESS.md current: what is done, what is verified (and how), what is not done, exact commands, next steps. If you are running out of context or usage, stop at a clean point and write the handoff first.
- Do not leave must-have functionality as TODOs or placeholders. Do not skip or weaken tests to make something pass.

# 10. FIRST ACTION (Phase 0 only, then STOP)
1. Read docs/context/ and the baseline code and tests.
2. Reply with: (a) a short confirmation of your understanding (at most 10 lines); (b) a feasibility check of the scope against my weeks-remaining figure, with a proposed cut line and the top risks; (c) ONE short numbered list of the questions you cannot answer yourself (no more than eight, nothing already answered in section 0); (d) the files CLAUDE.md, PLAN.md and PROGRESS.md created in the repository.
3. Wait for my answers. After that, work through P1 to P10 in order, autonomously, committing after each phase.
```

---

# PROMPT B: Deck revision

Use this in the same account after uploading `Capstone_Review_2.pptx` and the pivot message. Replace anything in [brackets].

```
Revise our review deck for the new project direction. The new title is "LogiMind: An API-First Hybrid Optimization Platform with an AI Dispatch Copilot for Small-Fleet Logistics". The pivot message (docs/context/PIVOT.md) overrides earlier assumptions where they conflict.

Draft the revised content for these slides: Title (1), Project Overview (3), Research Gap (11), Problem Statement (12), Objectives and Scope (13), Methodology (15), Architecture (17), Timeline (18-19) and Conclusion (24).

Rules:
- Keep the existing literature review slides. Reframe the gap around the lack of an ADAPTIVE framework that combines hybrid optimization, solver selection and an LLM interface.
- Delete the old boundary statement "does not claim to invent a new optimization algorithm."
- Keep the old comparison as the "Experimental Evaluation" and as the motivation for the selector. The demo Results A and B are the SAME instance at different time budgets (10 s and 3 s); caption them that way. Quote cost as well as distance.
- Describe the copilot as running on a local open-source LLM and the notifications as simulated, so the deck does not promise paid integrations.
- Say plainly what is built versus planned. At the time of writing the code has CVRP only, our own GA (not the Zhu-style design), straight-line distances, no selector, no hybrid, no copilot, no auth. Do not describe planned items as done.
- State the design rule on the architecture and objectives slides: the LLM never generates routes; solvers are the source of truth.
- Scope: must-haves, then deferred (RAG, demand forecasting, carbon estimation).
- Timeline: use [weeks remaining] and [review dates]; show the cut line.
- Do not invent results, pilot data or benchmark numbers.

Output, per slide: the new title, the on-slide text (short bullets), speaker notes (about 60 seconds each), and a one-line description of any diagram. Then ask whether to apply it to the .pptx.
```

---

# PROMPT C: Session handoff and restart

**When a session ends (or you see a usage warning), paste this into the agent:**

```
Stop at a clean point. Update PROGRESS.md with: what is finished and verified (and how), what is half-done (exact files and functions), failing tests, the exact commands to run the project and the tests, decisions made, and the next three concrete steps. Commit. Then reply with a 10-line summary.
```

**To restart in a new session:**

```
Read CLAUDE.md, PLAN.md and PROGRESS.md, then run the test suite and report the actual results. Continue with the next step in PROGRESS.md. Keep every invariant in CLAUDE.md. Update PROGRESS.md when you finish.
```
