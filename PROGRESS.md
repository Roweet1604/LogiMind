# LogiMind progress

Last updated: 4 Nov 2026, third unattended session: ops console on the tenant API, P8 copilot (fake LLM only), draft eval set. Current phase: **P8 needs a real-model check (Ollama), then P9 / rest of P6**; see Next steps.

## Done and verified
### Phase 0
- `docs/context/` assembled and committed; baseline read and audited; CLAUDE.md, PLAN.md, decision records 0001 and 0002.
### Phase 1 (time windows + public benchmarks)
- **Baseline migrated** unchanged to `backend/`, `frontend/`, `experiments/` (own commit). Verified: 54 backend tests and 13 frontend tests passed right after the copy.
- **Time windows in the model:** ready/due/service times per customer, depot opening hours, `time_per_distance`. Plain CVRP ids unchanged (tested against ids from the untouched baseline).
- **Validator 1.1:** late stops and late depot returns, with total lateness. **Metrics:** time-window violations, lateness, waiting, route durations; new CSV columns.
- **OR-Tools:** hard time windows (Time dimension, conservative integer rounding).
- **GA:** lateness penalty in the split + repair move (latest customer, or a customer from the shortest route when there are too many routes) + due-time seeding.
- **API:** time-window fields on `POST /api/instances`; `GET /api/benchmarks`, `POST /api/benchmarks/{set}/{name}`.
- **Benchmarks:** parsers for Solomon/Homberger text and TSPLIB CVRP files and `.sol` solutions. `fetch_benchmarks.py` downloads from CVRPLIB (2 Nov 2026): all 56 Solomon, all 27 Set A, and the 10 smallest Set X instances. `bks.csv` holds 93 best-known values with source URL and date. Files are not committed (see SOURCES.md, decision 0004).
- **Verified against CVRPLIB:** all 93 published best-known solutions pass our validator, and our recomputed distance equals the published cost exactly (max difference 0.0).
- **Tests:** backend **90 passed** (54 baseline + 36 new, incl. 3 that use the downloaded files), run on 2 Nov 2026 with Python 3.14.7 / OR-Tools 9.15.6755. Frontend 13 passed (baseline, unchanged since).
- `experiments/run_benchmarks.py` smoke run works (10 customers, 1 s).
- **Re-verified in a new session (2 Nov 2026):** backend 90 passed (4 library deprecation warnings), frontend 13 passed, benchmark smoke run OK. No code changed; P1 was not redone.

### Phase 2 (OR-Tools audit)
- **Audit tool:** `backend/app/benchmarks/audit.py` (grid, per-run rows, analysis) and `experiments/ortools_audit.py` (CLI with `--estimate-only`, `--resume`, `--analyze-only`). Runs strictly one at a time. Every row stores configuration, budget, repeat, OR-Tools status, build/search time, gap to BKS (benchmarks only), Python/OR-Tools/NumPy versions, machine and git commit.
- **OR-Tools has no seed parameter**, so "seeds" are repeats of the same configuration (recorded in every row as `seed_note`).
- **Full grid run:** 4 start strategies x 4 metaheuristics x 1/3/10 s x 3 repeats on 12 instances (6 Solomon, 4 CVRPLIB, 2 synthetic CVRP) = 1728 runs. Results committed in `experiments/results/ortools_audit_2026-11-02/` (raw.csv, report.md, summary/variation/recommendations CSVs, manifest).
- **Interrupted once:** Claude Code stopped the audit after 308 runs because the system was low on memory; it was resumed with `--resume`. One run (A-n32-k5, SAVINGS + GLS, 10 s) took 1506.7 s just before the stop (machine most likely frozen); it is kept in raw.csv but excluded from statistics as a timing anomaly and listed in the report. Manifest `created_at` is the resume time (noted in the manifest; script fixed).
- **Findings** (details in docs/decisions/0005): the old default PATH_CHEAPEST_ARC fails on R101 and RC101 at every budget and metaheuristic (72 failed runs); quality depends strongly on budget (chosen CVRP default: gap to BKS 5.69% at 1 s, 3.73% at 3 s, 2.94% at 10 s) and the best configuration changes with the budget; run-to-run spread is mostly 0, max 5.9%.
- **Audited defaults** per problem type (CVRP / VRPTW) and budget class (short <= 2 s, medium <= 6 s, long) are now used by `solve_ortools` when no strategy is given; the run config records `budget_class` and `search_choice`. API default is now `null` (= audited default); UI has an "Audited default (by budget)" option; Methodology text updated. With the default, R101 is solved (tested).
- **Tests (2 Nov 2026, Python 3.14.7 / OR-Tools 9.15.6755):** backend **106 passed** (90 + 16 new in `tests/test_ortools_audit.py`), frontend **13 passed**.

### Phase 3 (hybrid, local search, equal-clock comparison, guard)
- **GA weak spot fixed:** new fleet repair (empties the smallest routes when there are more routes than vehicles, without making any stop later). R101 with the GA alone: before 28 to 30 routes for 25 vehicles (infeasible); now 25 routes, feasible in every run (tested). The GA also gets about twice as many generations, because the old expensive repair branch is no longer needed.
- **Local search** (relocate, swap, intra-route 2-opt) as a switchable GA option (`local_search`, `ls_rate`, `ls_neighbours`); GA's own code, still no OR-Tools import in the GA (tested). GA now checks the clock after every child.
- **Hybrid** (`algorithm="hybrid"`, `app/solvers/hybrid.py`): OR-Tools for half the budget, then the GA seeded with the OR-Tools tour (+4 mutated copies) for the rest; labelled "hybrid"; unseeded or failed phases are reported. Available through the API (`POST /api/runs`, `hybrid` params); not in the UI yet.
- **Wall-clock guard** (`app/services/guard.py`): API runs execute in a worker process; a run past 1.5 x time limit + 5 s is killed and reported as `hard_timeout` (no plan). Tested with a deliberately frozen solver. UI shows the new status text.
- **Comparison + ablation:** `experiments/compare_engines.py`; 240 runs (6 methods x 10 instances x 3/10 s x 2 seeds, team chose the reduced size), results in `experiments/results/compare_2026-11-02/`. No hard timeouts; longest run 10.07 s on a 10 s budget. Findings (docs/decisions/0006): local search is what makes the GA competitive; on CVRP, GA + local search beat OR-Tools on average (2.26% vs 3.07% gap to BKS at 10 s) but not on every instance; on VRPTW OR-Tools stays best or tied; the hybrid's GA phase rarely improves the OR-Tools seed (0 to 9 of 20 runs), so with the untuned 50/50 split the hybrid is **not** a clear improvement over OR-Tools alone.
- **ruff** added (`ruff.toml`, requirements); `python -m ruff check .` passes (17 import-order fixes, 10 long lines wrapped).
- **Tests (2 Nov 2026, Python 3.14.7 / OR-Tools 9.15.6755):** backend **123 passed** (106 + 17 new in `tests/test_hybrid.py`), frontend **15 passed** (13 + 2 new tests for the "Audited default" option).

### Phase 5 (engine selector), 4 Nov 2026, unattended session
- **Win counts** from the P3 results (`experiments/selector_win_counts.py`, 20 cases): OR-Tools wins or ties 55%, the hybrid 55%, GA + LS 40%. No engine reaches 80%, so we built the **engine picker** (decision 0007).
- **Features** (`backend/app/selector/features.py`): budget, time-window tightness, size, demand fill, clustering. **Generator** (`generator.py`): uniform / clustered / mixed families with no / loose / tight windows. All output is labelled synthetic.
- **Dataset**: estimate 12.4 min, actual 10.2 min. 324 runs, one at a time through the guard; all feasible, no timeouts. Stored in `experiments/results/selector_2026-11-04/`; training copy in `backend/app/selector/data/training_cases.csv`.
- **Evaluation** (leave-one-family-out CV): the served regret trees have 0.52% mean regret; classifier 0.94%, always-hybrid 0.63%, always-OR-Tools 1.34%, random 1.55%. Leave-one-size-out: regret trees 1.06%, always-hybrid 0.63%. **This is not a proven improvement over always using the hybrid** (negative result, in `docs/model_card_selector.md`).
- **API**: `POST /api/plans` with `engine=auto` returns the choice with an explanation (predicted regret per engine plus the tree rule). `GET /api/plans/{id}` returns the plan; the validator's verdict is in `feasible`.
- **Tests**: 18 new in `tests/test_selector.py` (the P5 API tests moved to `tests/test_plans_api.py` in 6b).

### Phase 6 (platform), 4 Nov 2026, unattended session (partly done)
- **6a done** (commit ecc2b37): SQLAlchemy 2 models (`backend/app/db/models.py`: tenants, api_keys, plans, audit_log) and Alembic migration `backend/migrations/versions/0001_*`. Tenant isolation at the data layer (`app/db/session.py`): every ORM query on a tenant session is filtered, and writes for another tenant are rejected. API keys are stored as SHA-256 only (`app/db/keys.py`). Admin CLI: `backend/manage.py`. 13 tests in `tests/test_tenancy.py` try to break the isolation and the key checks (PK lookup, explicit filter, bulk update/delete, foreign insert, moving a row, forged/tampered/revoked keys, migration = models). Known limit: raw SQL bypasses the filter (decision 0008).
- **6b done** (commit 5a1146b): `POST /api/plans` and `GET /api/plans/{id}` need `X-API-Key`. The instance is sent inline and stored per tenant. Another tenant's plan gives 404. OpenAPI security scheme added; audit rows for create/complete. The DB is migrated on start-up. 6 tests in `tests/test_plans_api.py` (decision 0009).
- **6c done** (commit 7c117f1): `POST /api/orders/import` (auth) for .csv/.xlsx files. Reports every problem with its spreadsheet row number; customers are returned only if all rows are valid; each import gets an audit row. 13 tests in `tests/test_order_import.py`.
- **6d done** (commit 04780c0): webhooks wired. `POST/GET/DELETE /api/webhooks` and `GET /api/webhooks/{id}/deliveries`; tables `webhooks` and `webhook_deliveries` (migration 0002). Plan completion, failure and replan send `LogiMind-Signature` (HMAC-SHA256) on a separate 2-thread pool, never on the solver thread. Up to 4 attempts with back-off; every delivery series is stored and audited. Basic SSRF guard: http(s) only, no localhost or literal private IPs. Host names are NOT resolved (known limit). Rate limit: one token bucket per API key in `require_principal` (429 + `Retry-After`; default 60/min, burst 20). `GET /api/audit` lists the tenant's log. 11 tests in `tests/test_platform_api.py` plus the 6 module tests (decision 0010).
- **Research endpoints locked** (commit 4e65afc): `/api/instances`, `/api/runs`, `/api/experiments` and `/api/benchmarks` (15 routes) return 403 unless `LOGIMIND_DEV_RESEARCH_ENDPOINTS=1`; only the exact value `1` works, and the setting is OFF by default. An API key alone would not be enough, because that store has no tenants. 7 tests in `tests/test_research_lock.py` (decision 0011). README updated. The React ops console needs the dev switch.

### Phase 7 (replanning), 4 Nov 2026 (commit 5a6fbad)
- `POST /api/plans/{id}/replan` with events `vehicle_breakdown`, `failed_delivery` (retry or drop) and `urgent_order`. `completed` (stops done per vehicle) are frozen; `now` applies the current time on time-window instances. The result is a new plan linked to its parent (migration 0003) and gets a `plan.replanned` webhook.
- **OR-Tools**: frozen prefixes are hard `NextVar` chains plus locks, and a broken vehicle cannot take unfinished stops. Warm start uses the adjusted current plan via `ReadAssignmentFromRoutes`; whether it was used or rejected is recorded. **Finding:** the audited SAVINGS default finds no first solution with frozen stops, so replans switch it to PARALLEL_CHEAPEST_INSERTION and record that. **GA** is seeded with the current plan, but only when nothing is frozen; with frozen stops it is refused with 422.
- A replanned plan is `feasible` only if the validator passes on the real instance **and** the independent frozen-stop check passes. An impossible breakdown is stored and shown as infeasible (tested). `replan.timing.disruption_to_feasible_s` runs from the request to the validated plan.
- **Experiment** (`experiments/results/replan_2026-11-04/`, synthetic, 96 replans, estimate 2.7 min, actual 2.1 min): 96/96 feasible, 0 frozen-stop violations, warm start accepted 36/36. Warm vs cold mean distance at 0.5 s: -2.6% to -5.3%. At 2 s: -2.0% to +0.2%. **Negative result:** breakdowns at 2 s were slightly worse with the warm start (+0.22%). Time to a feasible plan is about the budget, because the engines use their whole budget; OR-Tools' first solution came after 6 to 9 ms.
- 12 tests in `tests/test_replan.py`: each event type, GA seeding, the GA refusal, bad events, the 409 for unfinished or infeasible plans, a tenant-isolation test for replan, the solver hooks, and the independent check.
- **Test-run anomaly:** the first full run of `tests/test_replan.py` (older code) took 82 min; the cause was not found, and the laptop may have slept. Since then the file takes 27 s; test commands use `timeout` (decision 0012).
- **Tests (4 Nov 2026, Python 3.14.7 / OR-Tools 9.15.6755):** backend **207 passed**, 0 failed (4 library deprecation warnings). `python -m ruff check .` passes. Frontend not re-run (no frontend change; last result 15 passed).

### Ops console on the tenant API, 4 Nov 2026 (commit d4e76ee, decision 0013)
- API-key sign-in (`/login`). The key is checked with the new `GET /api/whoami` and kept only in sessionStorage for the tab.
- `/plans`: CSV/Excel import with the row-level report, or a seeded "synthetic sample"; fleet and engine form; the tenant's plan list from the new `GET /api/plans`.
- `/plans/:id`: validator verdict, metrics, engine explanation, replan lineage and timing, map, route table, and replan forms for breakdown, failed delivery and urgent order. GA is disabled when stops are completed.
- `/api/health` reports `research_endpoints`; the research pages show a banner when they are off. GET plan now also returns the instance.
- Found and fixed a real bug: the time-budget inputs (`min=0.1`, `step=0.5`) made 3 s an invalid value, so the browser blocked the form.
- **Verified:** frontend 26 tests at that commit; production build OK. A live smoke run against uvicorn with the research endpoints OFF and a temp DB worked: login, import, a feasible auto plan, and a 403 on `/api/instances`.
- **Not verified:** the console was **not opened in a real browser** this session; only component tests and the build.

### Phase 8 (copilot), 4 Nov 2026 (commits f28d2a0 backend, 4aea890 chat panel; decision 0014)
- `backend/app/copilot/`: a LangGraph agent. The LLM only returns one Pydantic `IntentEnvelope` (solve / validate / compare / explain / reroute / clarify / refuse), with `extra="forbid"` and **no route fields**; that is tested.
- Six tools: `solve_with_ortools`, `solve_with_ga`, `run_hybrid`, `validate_routes`, `compare_results` (with a fairness note), `reroute`.
- Replies are templates over tool outputs. A grounding check blocks any number that no tool produced.
- One retry with the error, then a clarifying question. Unknown plan: a clarifying question listing recent plans. Reroute waits for `POST /api/copilot/confirm`. Sessions are per tenant.
- LLM interface with a deterministic `FakeLLM`, an `OllamaLLM` (langchain-ollama, used only if the server answers and has the model) and `NoLLM`. With no model, the API and the console say plainly "no local model available ... run `ollama pull llama3.2:3b`".
- Chat panel `/copilot`: model status, replies with a kind badge, the tool results used, plan links, Confirm/Cancel.
- Tests: 16 backend (`tests/test_copilot.py`, fake LLM only) and 4 frontend (`test/copilot.test.jsx`).
- **Negative / not verified:** Ollama is not installed on this laptop, so **no real model was run**. How well llama3.2:3b (or qwen2.5:7b) turns instructions into intents is unknown. Chat calls block while the solver runs.

### Draft copilot evaluation set
- `docs/eval/copilot_instructions_DRAFT.json`: 50 hand-style instructions with the expected intents, against a fictional three-plan context.
  - Categories: 10 solve, 5 validate, 5 compare, 4 explain, 6 breakdown, 5 failed delivery, 5 urgent order, 5 clarify, 5 refuse.
- Every item is marked DRAFT for the team to review. A test checks only that each expected intent fits the schema. **Nothing was run on it and no numbers exist.**

- **Tests at the end of this session (4 Nov 2026, Python 3.14.7 / OR-Tools 9.15.6755 / langgraph 1.2.19 / langchain-ollama 1.1.0):** backend **224 passed**, 0 failed (16 library deprecation warnings: SWIG, langsmith). Frontend **30 passed**. `python -m ruff check .` passes.

## First solver observations from P1 (5 s, one seed, Rohit's laptop; indicative only, do not quote; superseded for OR-Tools by the P2 audit)
| Instance | OR-Tools (default) | GA (with repair) |
| --- | --- | --- |
| C101 (BKS 827.3) | 827.3, 0.0% gap | feasible, +161.8%, 22 routes vs 10 |
| R101 (BKS 1637.7) | **no solution** with PATH_CHEAPEST_ARC; PARALLEL_CHEAPEST_INSERTION +1.3%, SAVINGS +2.5% | **infeasible**: 30 routes, only 25 vehicles |
| RC201 (BKS 1261.8) | +2.5% | feasible, +199% |
| A-n32-k5 (BKS 784) | +1.5% | +5.9% |
| X-n101-k25 (BKS 27591) | +5.7% | +8.1% |

## Not done / not verified
- **Copilot with a real model:** not run (Ollama not installed). Next: install Ollama, `ollama pull llama3.2:3b`, have the team review and freeze the DRAFT eval set, then measure the share of exact intent matches. Report the numbers for that exact model only.
- The ops console was not checked in a real browser this session (component tests, build and an API-level live smoke run only).
- Copilot sessions are in memory (lost on restart). Chat requests block until the solver finishes.
- Rest of P6 not started: job queue beyond the single solver thread, Docker Compose / Postgres, `.env.example`. Migrations tested on SQLite only.
- Webhook SSRF guard does not resolve host names (decision 0010). The rate limiter is in-process only.
- Replanning: the GA cannot keep frozen stops. The failed attempt's own travel is not modelled. The experiment covered 6 synthetic instances with one seed.
- Selector: synthetic data only; not a proven improvement over always-hybrid (model card).
- P9 driver PWA, P4 OSRM and P10 not started. Gehring-Homberger not downloaded; hybrid split untuned.
- Team answers still missing (docs/decisions/0002). Docker and Ollama not installed.

## Known quirks
- Instance ids hash coordinates as given: `10` and `10.0` give different ids (baseline behaviour, kept so old ids stay valid). The API always sends floats.

## Next steps
1. Team: review and freeze `docs/eval/copilot_instructions_DRAFT.json`. Then install Ollama (`ollama pull llama3.2:3b`) and run the copilot on the frozen set; record the model, version and results honestly.
2. Open the ops console in a browser against a backend started without the dev switch. Walk through sign-in, import, plan, replan and copilot, and fix what the component tests missed.
3. P9 driver PWA (stop list per vehicle from `/api/plans/{id}`, delivered/failed buttons that call the replan endpoint), then Docker Compose with Postgres.

## Restart commands
See CLAUDE.md "Commands". In a new session: read CLAUDE.md, PLAN.md and PROGRESS.md, run the backend tests and report the real result.

Exact commands used this session (from the repo root, Git Bash):
```
"$TEMP/lmv/Scripts/python" -m pip install -r backend/requirements.txt     # adds scikit-learn, sqlalchemy, alembic, openpyxl, python-multipart
"$TEMP/lmv/Scripts/python" experiments/selector_win_counts.py             # P5 step 1, no solver runs
"$TEMP/lmv/Scripts/python" experiments/selector_dataset.py --estimate-only # 324 runs, ~12.4 min
"$TEMP/lmv/Scripts/python" experiments/selector_dataset.py [--resume]
"$TEMP/lmv/Scripts/python" experiments/selector_train_eval.py
cd backend && "$TEMP/lmv/Scripts/python" -m pytest -q                      # 177 passed
"$TEMP/lmv/Scripts/python" -m ruff check .                                 # from the repo root
cd backend && LOGIMIND_DATABASE_URL=sqlite:///<path>.db "$TEMP/lmv/Scripts/python" manage.py create-tenant "Name"
```

Commands added in the second unattended session (Git Bash, repo root):
```
"$TEMP/lmv/Scripts/python" experiments/replan_experiment.py --estimate-only    # 6 base + 96 replans, ~2.7 min
"$TEMP/lmv/Scripts/python" experiments/replan_experiment.py                    # writes experiments/results/replan_2026-11-04
cd backend && timeout 900 "$TEMP/lmv/Scripts/python" -m pytest -q               # 207 passed
LOGIMIND_DEV_RESEARCH_ENDPOINTS=1 uvicorn app.main:app --port 8000              # local dev with the ops console
```

Commands added in the third unattended session:
```
"$TEMP/lmv/Scripts/python" -m pip install -r backend/requirements.txt   # now also langgraph, langchain-core, langchain-ollama
# frontend tests: copy frontend/src etc. to %TEMP%\lmfe_s3 (npm ci there once), then:  npx vitest run   # 30 passed
LOGIMIND_LLM_PROVIDER=none uvicorn app.main:app --port 8000             # copilot off on purpose; default "ollama" uses it only if running
```

