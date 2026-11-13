# LogiMind progress

Last updated: 13 Nov 2026, nineteenth session (`main`): `npm run dev` opens a tunnel and the Vercel console follows it via `?api=` (decision 0040). Before that, 12 Nov 2026, eighteenth session: public deployment plumbing (decision 0039). Before that, 11 Nov 2026, sixteenth session (branch `cleanup-and-fixes`): replans keep earlier disruptions (decision 0037); OpenAI no longer offered in the console (decision 0036 amended). Before that, 10 Nov 2026, fifteenth session (branch `ui-redesign`): "Load models" in the Copilot settings box (decision 0035). Fourteenth: start-dev.bat's port check reads the listener table (decision 0034).

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

### Phase 9 (driver app and notifications), 4 Nov 2026 (commits 1e33324, e8708f0, 330db95; decisions 0015-0017)
- **Driver access** (`backend/app/driver/`, `app/api/driver.py`, migration 0004).
  - A dispatcher creates a short-lived HMAC-signed link for **one route** of a completed, feasible plan (`POST /api/plans/{id}/driver-links`; default 12 h, at most 24 h), and can list and revoke links.
  - Each driver call checks the signature, the expiry and the link row (tenant, plan and route must all match).
  - Driver endpoints: `GET /api/driver/route`, `POST /api/driver/stops/{customer}/status` (delivered, or failed with a reason; `client_event_id` makes resends safe), `POST /api/driver/stops/{customer}/photo`.
  - Photos: JPEG/PNG/WebP detected from the bytes, at most 3 MB and 5 per stop, generated file names under `<data dir>/pod/<tenant>/`.
  - Dispatcher endpoints: `GET /api/plans/{id}/stop-reports` and `GET /api/photos/{id}`. Driver reports never change the plan.
- **Driver PWA** (`driver/`, React + Vite + vite-plugin-pwa).
  - Installable: manifest with 192/512 px and maskable icons; a precached app shell.
  - Offline: the stop list is cached per link; delivered/failed reports are queued and sent in order on start, on `online`, every 20 s and with "Sync now".
  - Stops have a navigation deep link (lon/lat plans only). Buttons are at least 52 px high.
  - Photos need a connection; they are re-encoded to JPEG of at most 1600 px first.
  - The ops console has a "Drivers" panel (link per route, revoke, latest reports).
- **ETA notifications** (`backend/app/messaging/`, `app/api/notifications.py`, migration 0005).
  - `MessageSender` adapter with **only a stub** that logs and never sends; any other `LOGIMIND_NOTIFY_PROVIDER` is refused.
  - `notification_log` records every message sent or skipped (no contact, no opt-in), with recipients masked.
  - Contacts need **explicit opt-in** (default off), with opt-in and opt-out times.
  - Templates: eta, delivered, failed.
  - ETAs come from the validator's own route schedule plus a shift start. Responses say "not live traffic", and plans with no time data say the default 1 min/km is assumed.
  - Delivered/failed messages follow driver reports; a sender failure never undoes a report.
- **Tests:**
  - Backend +17: 9 in `tests/test_driver.py`, which try other routes, other plans, other tenants, tampered, re-signed, expired and revoked tokens, and API key vs driver token mix-ups; 8 in `tests/test_notifications.py`.
  - Driver PWA 17 (`driver/src/test/`).
  - Console +2 (`frontend/src/test/ops.test.jsx`).
- **Verified in a real browser** (Chrome via the Claude in Chrome extension, against uvicorn on a temp SQLite DB with the research endpoints off, and the built PWA served by `vite preview`):
  - The driver link opened the stop list, and the token was removed from the address bar. The service worker was active and controlling the page; precache present; manifest linked.
  - A failed report ("Nobody home") synced at once.
  - With the preview server stopped, a reload showed the saved stop list marked Offline (app shell from the service worker). A delivered report was queued ("waiting to sync") and reached the server after the server came back and the page reloaded.
  - The ops console's Drivers panel showed the three reports and created a link. No console errors.
- **Found and fixed in the browser check:** with the server down but the network up, the browser sends no `online` event, so queued reports waited until a reload and "Sync now" was disabled. Added a 20 s retry, and "Sync now" stays enabled (new test).
- **Not verified:**
  - **Not installed on a real phone**, and the install prompt was not triggered. The camera capture and the canvas re-encoding path (`driver/src/lib/photo.js`) were not run in a browser; jsdom has no canvas, so the tests use the fallback path.
  - The maps deep link was not opened, and Chrome's browser-offline mode was not used (the server was stopped instead).
  - The stub sender was only checked by tests and logs. No real SMS or e-mail was sent (none exists).
- **Tests at the end of this session (4 Nov 2026, Python 3.14.7 / OR-Tools 9.15.6755):**
  - Backend **241 passed**, 0 failed (16 library deprecation warnings); `python -m ruff check .` passes.
  - Ops console **32 passed**. Driver PWA **17 passed**, and `vite build` makes `sw.js` + `manifest.webmanifest` (16 precached entries).
- **Flaky test seen once:** the opening full run of this session had **1 failure**, `tests/test_hybrid.py::test_guard_stops_a_frozen_run_and_reports_a_timeout` (223 passed, 1 failed). It then passed 3 times alone, once with its whole file, and in all 3 later full runs. That first run was tailed, so the assertion message was not captured. The test asserts wall-clock bounds (1.4 s <= wait < 10 s), so laptop load is the likely cause, but this is not proven.

### Fifth unattended session, 5 Nov 2026 (commits f3f4155, 6c1dc9d, 9e83546, and the PROGRESS commit)
- **Opening run (before any change):** backend 241 passed; ruff clean; console 32 passed; driver PWA 17 passed.
- **Flaky guard test fixed** (decision 0018). Cause, measured: `waited` included spawning the solver worker process, which took 5.8 s, 6.4 s and 5.9 s on the idle laptop, against a 10 s cap. The test now starts the worker before the clock, checks the guard's own hard limit (1.5 s) as the lower bound, uses 30 s as the upper bound (the frozen solver sleeps 60 s), and also checks that the frozen worker process is dead. **Run 10 times in a row: 10 passed.**
- **P4 road matrix, done offline** (decision 0019). `backend/app/distances/`: `DistanceProvider`, `HaversineProvider` (straight line x 1.3 at 25 km/h, both assumptions, labelled), `OsrmProvider` (table service, batching in chunks of max_table/2, size limit 250 points), `MatrixCache` (SQLite, 30 days), `DistanceService` (flagged fallback).
  - `POST /api/plans` takes `distance_source` = `straight_line` (default, unchanged) / `osrm` / `estimate`. The matrix is built before the solver, stored with the plan, and used for distances AND travel times by every engine, the validator, the metrics and the ETAs. Instance ids include the matrix digest; ids without a matrix are unchanged (tested).
  - If OSRM is not configured, not reachable, answers with an error or cannot route a pair, the plan uses the estimate with `distance_source.fallback: true` and the reason. Shown on the plan, the plan list, the ETA response, the audit row, and as a warning on the console's plan page.
  - Urgent-order replans extend the matrix to the new stop (checked in the browser: 9 to 10 points).
  - Tests: 16 backend (`tests/test_distances.py`), 2 console (`src/test/distances.test.jsx`). They replay **real OSRM answers for 6 synthetic Bengaluru points**, recorded once on 5 Nov 2026 from the public OSRM demo server (`backend/tests/fixtures/osrm/`, script `experiments/osrm/record_fixture.py`). The product never uses the demo server. The batched matrix (9 requests) equals the single-request matrix exactly.
  - Two bugs found by these tests and fixed before the commit: an empty `MatrixCache` counted as false (it defines `__len__`), so nothing was ever cached; and one test picked a batched URL instead of the 6-point one.
  - Measured on the fixture (30 pairs, too few to calibrate): road / straight line 1.16 to 1.66 (median 1.30); OSRM's implied speed 36.6 to 52.9 km/h (median 47.4). OSRM travel times are free-flow (no traffic), so they are likely optimistic for Bengaluru. Not calibrated (P10).
- **Docker Compose: written, UNTESTED** (decision 0020). Docker is not installed (`docker` not on the PATH; no Docker Desktop executable). Files: `docker-compose.yml` (postgres, api, console, driver; optional profile `osrm` with `osrm-prepare` and `osrm`), `backend/Dockerfile`, `backend/requirements-docker.txt` (adds psycopg), `frontend/` and `driver/` `Dockerfile` + `nginx.conf`, `.env.example` (empty `POSTGRES_PASSWORD` and `LOGIMIND_DRIVER_LINK_SECRET`; Compose refuses to start without them), README section. Only checked: the YAML parses, and every `${VAR}` is in `.env.example`.
  - **No separate worker service**: jobs run in the API process's guarded worker; a worker container needs the job queue (open P6 item). Said so instead of adding an empty service.
  - **OSRM extract not downloaded**: the smallest official file containing Bengaluru (Geofabrik `asia/india/southern-zone-latest.osm.pbf`) is 559,229,243 bytes (HTTP HEAD, 5 Nov 2026), above the ~150 MB limit; BBBike had no Bangalore extract at the URL tried (404). So no SHA-256 was recorded. Team decision needed (decision 0020 lists options).
- **Ops console checked in a real browser** (Chrome via Claude in Chrome; uvicorn on a temp SQLite DB, research endpoints off, OSRM not configured, Ollama not installed; Vite dev server):
  - Verified: API-key sign-in; import of a CSV with errors (row-level report: row 3 demand "not a number", row 4 duplicate id; nothing imported); import of a valid lon/lat CSV (8 synthetic orders); the new "Distances and travel times" choice (shown only for lon/lat orders); an auto plan with "Road network (OSRM)" that came back feasible with the **fallback warning and its reason**; an urgent-order replan with 2 stops completed on vehicle 0 (feasible, frozen stops `[4, 6]` kept, 0 frozen-stop violations, warm start used, matrix extended to 10 points; checked again through the API); the copilot page showing "No local model available" with the input disabled. No console errors after a reload of the plan page.
  - Fixed after the check: the fallback notice nested brackets and repeated itself; the map note said "great-circle distance" even when a matrix is used; "after a urgent_order event" wording.
  - **Not verified:** the copilot answering anything (no model); the breakdown and failed-delivery replan forms in the browser (covered by tests only); `.xlsx` import in the browser; OSRM road distances end to end (no OSRM server; only replayed recordings in tests).
- **Tests at the end of this session (5 Nov 2026, Python 3.14.7 / OR-Tools 9.15.6755):** backend **257 passed**, 0 failed (16 library deprecation warnings); console **34 passed**; driver PWA **17 passed**; `python -m ruff check .` passes.

### Sixth unattended session, 5 Nov 2026 (commits 5598d08, 5221166, 05cf946, and the deck/PROGRESS commit)
- **Opening run (before any change):** backend 257 passed; ruff clean; console 34 passed; driver PWA 17 passed. Docker and Ollama still not installed.
- **P6 job queue, done** (decision 0021, commit 5598d08).
  - Table `jobs` + `queue_lock` (migration 0006); a plan and its job are committed in one transaction.
  - Worker process `python -m app.jobs.worker` (`backend/app/jobs/`: `queue.py` claim/heartbeat/finish/recover, `execute.py` plan/replan/benchmark execution moved out of `services/plans.py`, `worker.py` loop + CLI).
  - The API runs no solver jobs (`LOGIMIND_WORKER=external`, the default); `inline` runs the same loop in an API thread for development and the tests (`tests/conftest.py`).
  - Benchmark jobs (research runs) start only when nothing else runs and block everything while they run; planning jobs may run side by side; FIFO. Claims are serialized by a lock row.
  - Heartbeat every 2 s; a job silent for 30 s is requeued; after 2 claims the job and its plan fail with the reason and a `plan.failed` webhook.
  - Tenant isolation: the worker writes through the job tenant's session (tested with a forged job). `GET /api/plans/{id}` shows the job (attempts, worker, requeues). `/api/health` shows the queue.
  - Tests: 8 new in `tests/test_jobs.py` (FIFO and benchmark rules, 8 concurrent claimers get 1 benchmark job, stale requeue then fail, hard-timeout guard + webhook through the queue, worker crashing twice fails the plan, forged cross-tenant job, and **two real worker processes: the first killed mid-job, the second finishes it with attempts = 2**; that test passed 4 of 4 runs). All existing API tests pass through the queue unchanged.
  - Compose has a `worker` service (UNTESTED, no Docker).
- **P10 evaluation, first version** (decision 0022, commit 5221166; `docs/report/evaluation.md`).
  - Found: all 10 P3 comparison instances are P2 audit instances, so the P3 tables are biased towards OR-Tools (now labelled so).
  - New: **24 held-out instances** (12 Solomon VRPTW, 12 CVRPLIB CVRP), OR-Tools / GA + LS / hybrid, 3 s, 3 repeats = 216 runs; estimate 11 min, actual 650 s (the only new solver compute this session).
  - Results (Wilcoxon signed-rank over instances, Holm-corrected): CVRP: GA + LS better than OR-Tools on 10 of 12 (p = 0.048, borderline); VRPTW: OR-Tools better than GA + LS on 12 of 12 (p = 0.0044); **hybrid not significantly different from OR-Tools** on CVRP, VRPTW or all 24 (negative result). One infeasible run: GA + LS on A-n45-k6 used 7 of 6 vehicles (caught by the validator).
  - Selector and replanning sections are summaries of stored synthetic runs. **Copilot: NOT RUN** (no model; eval set still DRAFT).
  - `experiments/p10_report.py` writes the report, CSV tables and SVG figures from stored files only; the figures were checked in a browser.
  - Process note: the first commit of this item passed ruff through a pipe that hid 8 lint errors; fixed and folded into the same (unpushed) commit with `--amend`.
- **Docs** (commit 05cf946): `docs/architecture.md`, `docs/api_guide.md`, `docs/demo_script.md`, `docs/limitations.md`; README links them.
  - Demo re-walked in Chrome with a **separate worker process** (API in external mode): CSV import, plan with the OSRM fallback warning, urgent-order replan, **vehicle-breakdown and failed-delivery replans** (first browser check of these two forms); jobs ran on the worker (`worker_id` on the plan; frozen stops kept; 0 violations).
  - **New weakness found:** a failed delivery with retry was planned again as the very next stop (immediate retry). Listed in limitations.
- **Deck draft** (`docs/report/deck_draft.md`): slides 1, 3, 11, 12, 13, 15, 17, 18-19, 24 with short bullets, ~60 s notes and a diagram line; placeholders [weeks remaining], [review dates]; the .pptx was not edited. It asks the team to confirm which old demo result was 10 s and which 3 s (not recorded anywhere I could check).
- **Tests at the end of this session (5 Nov 2026, Python 3.14.7 / OR-Tools 9.15.6755):** backend **265 passed**, 0 failed (16 library deprecation warnings); console **34 passed**; driver PWA **17 passed**; `python -m ruff check .` passes.

### Seventh unattended session, 5 Nov 2026 (commits f8d2912, 569d074, 06e0de0, and the deck/PROGRESS commit)
- **Opening run (exit codes checked directly):** ruff exit 0; backend 265 passed; console 34; driver PWA 17.
- **CLAUDE.md rule added:** never pipe or wrap a test or lint command so that its exit code is hidden; check ruff and the tests directly before each commit (followed for every commit this session).
- **Retry rule, done** (decision 0023, commit f8d2912). A retried failed delivery is never a route's next unfinished stop, unless it is that route's only remaining stop. OR-Tools: hard constraint (`not_next` in `backend/app/solvers/ortools_solver.py`); warm start: `insert_cheapest` skips the position; `check_replan` verifies it independently (`retry_too_soon` in `backend/app/replan/events.py`); the GA is refused for retries (`backend/app/replan/jobs.py`). 3 new tests in `backend/tests/test_replan.py`; one shows that without the rule OR-Tools retries at once on the test instance. My first test instance had a tie between two routes, so it did not show the problem; replaced by one where the immediate retry is strictly cheapest. Not re-walked in a browser.
- **10 s held-out run: PARTIAL** (decision 0024, commit 569d074). The session stopped the run after **134 of 216 runs** because the laptop was critically low on memory; it was **not restarted** (session rule). All 24 instances have 1-2 repeats per engine instead of 3. One run (A-n69-k9, GA + LS, seed 1) reports 2412 s for a 10 s budget (machine stalled); runs longer than the guard limit (1.5 x budget + 5 s) are now left out of every statistic and listed (report section 1.7).
  - **Preliminary answers:** the OR-Tools advantage with time windows **holds at 10 s** (OR-Tools better on 10 of 12, Holm p = 0.0176). The GA + LS advantage on capacity-only problems is in the **same direction but not significant at 10 s** (8 better / 2 ties / 2 worse, Holm p = 0.53). Hybrid vs OR-Tools: not significant at either budget.
  - The report now has an instance-size table (32-119 customers; the Solomon instances have 100), per-budget Holm (9 tests each) and a "does it hold at 10 s" table whose verdicts are computed. PARTIAL banners are generated from the manifest and disappear when the run is complete.
- **Selector out-of-distribution test, done** (commit 06e0de0; `experiments/selector_heldout_eval.py`, results in `experiments/results/selector_heldout_2026-11-05/`, report section 2.2). No solver runs: the served selector picks an engine for each of 48 benchmark cases (24 instances x 3 s / 10 s; 39 outside its training range), scored against the stored runs. Mean regret: **selector 0.49%**, always hybrid 0.62%, always OR-Tools 1.02%, always GA + LS 5.11%. **Negative results:** always GA + LS beats it on CVRP (0.31% vs 0.64%), always hybrid beats it at 3 s (0.51% vs 0.56%); on VRPTW it always picked OR-Tools; it made the same choice at both budgets for all 24 instances. The 10 s half uses the partial run. No significance test (cases not independent). Model card updated.
- **Deck draft updated** (`docs/report/deck_draft.md`): Result A = 10 s run, Result B = 3 s run of the same instance (captions with distance and cost); new held-out and selector findings on slides 13, 15, 19, 24, marked preliminary where they use the 10 s run. Placeholders kept; the .pptx was not edited.
- **Tests at the end of this session (5 Nov 2026, Python 3.14.7 / OR-Tools 9.15.6755; exit codes checked):** backend **268 passed** (exit 0, 16 library deprecation warnings); console **34 passed** (exit 0); driver PWA **17 passed** (exit 0); `python -m ruff check .` exit 0.

### Eighth unattended session, 10 Nov 2026: UI redesign (branch `ui-redesign`; commits 7f65dc7, 4dc53a2 and the screenshots/PROGRESS commit; decision 0025)
- **Opening run (exit codes checked):** console 34 passed, driver PWA 17 passed, both `vite build` exit 0. The backend was not changed this session.
- **Design tokens in one place:** `design/tokens.js` (colours, type scale, spacing, radii). Both `tailwind.config.js` files and the engine line styles (`frontend/src/lib/algos.js`) read it. Contrast measured with a script: every text pair is at least 4.5:1.
  - Because the tokens sit outside the app folders, the console/driver Docker builds now use the repo root as build context (`docker-compose.yml`, both Dockerfiles, new `.dockerignore`). Still **UNTESTED** (no Docker).
- **Console:** left rail with the existing sections; top bar with tenant, backend status and a Copilot toggle.
  - Plan view: a status strip at the top (validator verdict, engine, timeout, fallback distances, replanned + parent link), then the timeout / infeasible / fallback notices, then the map beside the route list. Clicking a route highlights it on the map.
  - Status badges always have an icon and a word. The hybrid has its own line style (dash-dot slate). Compact tables with right-aligned numbers. Synthetic order sets are labelled "synthetic".
  - The copilot is also a docked side panel. It shares one conversation with the `/copilot` page and is cleared when the signed-in key changes. Opening it moves focus into it, and Esc closes it. API calls and the Confirm/Cancel flow are unchanged.
- **Driver app:** dark sticky header with an Online / Offline / "Server unreachable" badge (icon + word), a progress bar and the sync row. The next stop has 64 px Navigate / Delivered / Failed; all other targets are at least 56 px. Inline SVG icons, no new dependency.
- **Behaviour kept:** API-key handling, validator display, replan confirmation, offline queue/sync and tenant behaviour use the same code. All 34 console and 17 driver tests pass unchanged; no test was weakened.
- **New tests:** console +5 (`src/test/design.test.jsx`: engine styles, status strip flags, dock open/focus/Esc/close); driver +3 (`src/test/design.test.jsx`: target sizes, icon + word statuses, "Server unreachable" on a 5xx).
- **Checked in a real browser** (desktop Chrome via Claude in Chrome; uvicorn on a temp SQLite DB, research endpoints off, OSRM pointed at a closed port, Ollama not installed; console on the Vite dev server, driver as a production build on `vite preview`). Screenshots and an index are in `docs/report/ui/`. All data is synthetic.
  - Console: sign-in; Plans list; plan views for an auto/hybrid plan with the real OSRM fallback warning, a planar hybrid plan and an urgent-order replan; route highlight; Drivers panel; replan form (displayed, not submitted); copilot page and dock with the real "no local model" state; signed-out state; a research page with its "switched off" banner; keyboard focus; the plan page and the dock at 390 px (in a 390 px iframe). No console errors (only React Router's existing future-flag warnings).
  - Driver: stop list; Delivered (synced at once); the Failed form; the API stopped, so a report was queued, "Server unreachable" was shown, then the API was restarted and Sync now sent it; an expired link after an API restart without a fixed link secret (the unsent report was mentioned). All at 390 px in an iframe.
  - **Found and fixed in the browser:** the map zoomed on the mouse wheel and trapped page scrolling (wheel zoom is now off); the driver badge said "Online" while showing the saved copy after a 5xx; the teal focus ring was 2.9:1 on the dark rail; the status chip and the long badge squeezed the titles at 390 px; Drivers table columns too wide.
  - **Found, not changed (existing behaviour, outside this task):** the console signs you out if the backend is unreachable when a page loads, because `AuthContext` treats any failed `whoami` as a bad key. The driver app numbers routes from 1 ("Route 2") while the console numbers vehicles from 0 ("Vehicle 1").
  - **Not checked:** a real phone or device emulation (the window resize did not apply; 390 px was checked in an iframe); sunlight readability beyond the measured contrast; the copilot with a real model, including the Confirm/Cancel buttons in the browser (unit tests only); the research pages' own workflows (research endpoints off); the Overview and Methodology pages after the restyle; a screen reader; Docker builds.
- **Tests at the end of this session (exit codes checked):** console **39 passed**, driver PWA **20 passed**, both builds exit 0; `python -m ruff check .` exit 0; backend **268 passed** (exit 0, 16 library deprecation warnings; backend unchanged).

- **`npm run dev` for both sides** (decision 0026, same session, at the team's request): `cd backend && npm run dev` starts uvicorn on :8000 with auto-reload and the inline worker (Python found in `LOGIMIND_PYTHON`, `%TEMP%\lmv`, `.venv` or the PATH); `cd frontend && npm run dev` was already Vite on :5173. Both were started and answered (health 200, console page 200, `/api` proxy 200). `npm run worker` and `npm test` also exist in `backend/`. Not checked: macOS/Linux, and Ctrl+C in an interactive terminal.
- **Local sign-in setup** (decision 0026 addendum): `backend/.env` (git-ignored; template `backend/.env.example`) is read by `npm run dev` / `worker` / `tenant`; `npm run tenant -- "<name>"` prints a test key once (only its hash is stored). New `backend/tests/test_manage_cli.py` (3 tests). Walk-through checked end to end on a throwaway database. Found: on Windows two servers can listen on port 8000 at once; a second `npm run dev` does not fail.

### Ninth unattended session, 10 Nov 2026: "Freight Yard" theme (branch `ui-redesign`; commits dadad17, 6a29935 and the PROGRESS commit; decision 0027)
- **Opening run (exit codes checked):** console 39 passed, driver PWA 20 passed, both builds exit 0. Backend not touched.
- **Theme** (look only; layout and behaviour kept): `design/tokens.js` now holds the Freight Yard values. Concrete grey page, ink text, safety yellow #FFC400 only as a background with ink text on light surfaces (text only on dark ones), dark sidebar and driver header, yellow active nav item and brand. Primary buttons are yellow with bold ink text, secondary ones have an ink outline. 4px corners, no shadows.
  - Fonts bundled from npm (OFL-1.1): Barlow Condensed 700 headings (uppercase) and IBM Plex Sans body; Inter removed.
  - Engine lines: #1D4ED8 solid, #C2410C dashed, #57606A dash-dot. Status labels have an icon and a word: feasible = green on white with an ink border; warning/draft = yellow on black; infeasible/failed/timeout = white on red.
  - Driver: 64px Navigate/Delivered/Failed on every stop; the next stop's Navigate is the yellow main action. New yellow PWA icons (`driver/scripts/make-icons.mjs`). The manifest colours read the tokens.
- **Contrast:** 25 text/background pairs checked (lowest 6.39:1; list in decision 0027). A new test computes them from the tokens and fails below 4.5:1; another checks that yellow is never a data line.
- **Tests at the end (exit codes checked):** console **41 passed** (+2), driver PWA **20 passed** (the size test now checks 64px on every stop and the yellow main action), both builds exit 0. No existing assertion was weakened.
- **Checked in real Chrome** against uvicorn on a temp SQLite DB (ports 8011/5193/5194, so the developer's own server on :8000 was left alone; research endpoints off, OSRM unreachable, Ollama not installed; synthetic data). Sign-in was typed in through the Claude in Chrome extension. That extension's screenshot call kept timing out, so the 17 screenshots in `docs/report/ui/` come from a headless Chrome script (puppeteer-core in %TEMP%, not a project dependency).
  - Measured: the sidebar focus ring is solid 2px yellow and the light-surface ring 2px ink; the driver's ring is 3px ink. Neither app scrolls sideways at 390px. Navigate/Delivered/Failed are 64px.
  - Driver offline check used Chrome's real offline mode for the first time: "Offline", a saved copy and a queued report; back online, it synced by itself. An invalid (tampered) link shows "Link no longer valid".
  - Found and fixed: ids in headings were uppercased; the map was squeezed when the copilot was docked; the hybrid line blended into greyscale tiles.
  - Noted, not changed: every console page asks for `/api/instances` and gets 403 when the research endpoints are off (30 times in this run; existing behaviour). A plan with no solution has `feasible = null`, so it shows the red "no plan" verdict but no "Not a feasible plan" notice (existing logic).
  - **Not checked:** a real phone or real sunlight (390px is Chrome emulation); a screen reader; Windows high-contrast mode; the copilot's Confirm/Cancel with a real model (unit tests only; no Ollama); the research pages' own workflows; Docker builds. Map roads are greyscale OSM tiles, not exactly #C9C9C3 (raster tiles cannot be recoloured exactly).
- **Mistake during the session, undone:** installing puppeteer-core in a folder without a `package.json` made npm use `C:\Users\rohit\package.json`. It added the dependency there and installed 82 packages into `C:\Users\rohit\node_modules`. `npm uninstall puppeteer-core` removed it again (81 packages); `package.json` is back to its three original dependencies. `C:\Users\rohit\package-lock.json` was rewritten by npm; its earlier content could not be checked.
- `frontend/node_modules` (in place) was updated with `npm install` so `npm run dev` finds the new fonts; `driver/` still needs `npm install` once.

- **`start-dev.bat`** (decision 0028, same day): one command opens the API, worker, console and driver windows; `start-dev.bat tenant "<name>"` makes a test tenant and key. The backend runs with Python only; npm only in `frontend\`/`driver\`. Tested on a throwaway database on ports 8031/5183/5184: all four answered, and the separate worker solved a synthetic plan. The first version never started npm (an `if … &` inside `cmd /k`); fixed. README quick start rewritten (one-time setup, tenant, one command, the same by hand). `driver\node_modules` now exists in place (installed by the script's first run).

### Tenth unattended session, 10 Nov 2026: simple to run and to look at (branch `ui-redesign`; commits 11f4860, 115ff08 and the console/README/PROGRESS commit)
- **Opening run (exit codes checked):** ruff exit 0; backend 271 passed (exit 0). `ui-redesign` was fast-forwarded to `main` first (it lacked the `start-dev.bat` commit f2508d7).
- **Demo mode** (decision 0029, commit 11f4860). `backend/app/demo.py`: off unless `LOGIMIND_DEMO_MODE=1` **and** `LOGIMIND_BIND_HOST` is loopback. On start it creates "Demo Fleet (synthetic)" if missing, rotates an in-memory key and queues three seeded synthetic plans once (12 stops OR-Tools, 15 stops with time windows `auto`, 10 stops GA + LS; 2 s each) through the normal queue, solvers and validator. `GET /api/demo/session` gives the key only to local requests (client, socket and Host local; no proxy headers); 404 when off. The console signs in by itself and shows a "Demo mode" label; a valid normal key wins; sign-out keeps the tab signed out. Never in Docker Compose (tested). Tests: backend +17, console +4.
- **One-command start** (decision 0030, commit 115ff08). `start-dev.bat` with no arguments makes the venv (`py -3`/`python`), installs packages, writes `backend\.env` with a generated driver-link secret, runs `npm install` in `frontend\`/`driver\`, checks ports (names the busy port and program, stops nothing), starts the four windows (API on 127.0.0.1 with demo mode), waits for the API and the console and opens the browser. Helpers in `backend/scripts/devtools.py` (+4 tests).
  - **Checked:** a fresh clone in the scratch folder with an empty TEMP folder on ports 8040/5185/5186: everything above ran (about 25 min, mostly the pip download), `/api/health` said `demo_mode: true`. On the real repository the port check found the developer's own Vite server on 5173 (node.exe) and stopped nothing, so the real repository was **not** started with the default ports.
  - **Incident:** during the session the main `%TEMP%\lmv` lost most `.py` files (only `__pycache__` left; ruff and pytest stopped working). Not caused by this session's commands as far as I can tell; cause NOT found. Rebuilt with `py -3 -m venv --clear` + `pip install`. The script now detects such damage and reinstalls (decision 0030). Team: consider a venv outside `%TEMP%` for the demo laptop.
- **Simpler console** (decision 0031). Sidebar: Overview, Plans, Drivers, Copilot, Account. Research workflow, Benchmark lab and Methodology behind one "Research" link shown only when `LOGIMIND_DEV_RESEARCH_ENDPOINTS=1`; the "Current research instance" footer only then; `/api/instances` is no longer requested when research is off (ends the 403s noted in the ninth session). New dispatcher Overview (counts from the validator verdicts) and Drivers page; the old research overview moved to `/research`. Plain error messages ("The server isn't running. Run start-dev.bat, then press Retry."), no commands in the UI. If the server is unreachable the session is kept and Retry is shown; only a rejected key signs out (this resolves the `AuthContext` point from the eighth/ninth sessions). Tests: console +7; two message assertions in `lib.test.js` updated to the new text (still check status and the `unreachable` flag).
- **Checked in real Chrome** (Claude in Chrome, against the fresh clone's servers on 8040/5185/5186, synthetic demo data): without typing a key the console opened signed in to "Demo Fleet (synthetic)" with the "Demo mode" label and three feasible demo plans; Overview, Plans, Drivers (driver-link panel for the chosen plan), a plan page (map, routes, validator verdict), Copilot ("No local model is available" in plain words; no Ollama installed) and the `/research` URL (plain "switched off" note). API stopped: the console kept the key, showed the plain message and Retry; API restarted (new demo key): Retry signed back in by itself, the three plans were not duplicated. No console errors. Found and fixed: the top bar said "not signed in" during an outage.
- **Checked after the third commit (not committed, per the three-commit limit):** `start-dev.bat` in the real repository on ports 8050/5195/5196: it filled the empty `LOGIMIND_DRIVER_LINK_SECRET` in `backend\.env`, started, waited and opened the default browser (Edge gained tabs; its address could not be read from here). In Chrome, a new tab on that console signed in by itself with three feasible synthetic plans and the five-item sidebar; no console errors. With the API restarted with `LOGIMIND_DEV_RESEARCH_ENDPOINTS=1`: one "Research" link, its six sub-pages under it when open, the research footer only in this mode, Benchmark lab not switched off. The demo tenant now exists in the developer's local database.
- **Not checked:** `start-dev.bat` on the default ports (5173 was busy with the developer's own server); a computer without Python or Node.js; the driver app (not changed); a phone. Plan "Created" times show UTC (for example 09:11 for 14:41 IST); existing behaviour, not changed.
- **Tests at the end (exit codes checked):** ruff exit 0; backend **292 passed** (exit 0, 16 library deprecation warnings; Python 3.14.7, OR-Tools 9.15.6755); console **52 passed**, build exit 0; driver PWA **20 passed**.

### Seventeenth session, 12 Nov 2026: clean-up, start-dev.bat outside OneDrive, solver-process leak (branch `cleanup-and-fixes`; commits f319957, 8f8e054)
- **Solver-process leak fixed:** every inline app (tests, one-process development) left its guarded solver process alive until the interpreter exited, about 500 MB committed each. Measured during the full suite: up to 92 Python processes and 65 GB committed, then "OpenBLAS error: Memory allocation still failed" in a child, which failed the two tests above in every full run (also with nothing else running). Now the app's lifespan stops the inline worker, and its thread closes the solver process after the current job. With the fix: peak 10 Python processes, 23 GB committed. Test `tests/test_jobs.py::test_app_shutdown_stops_the_inline_workers_solver_process` (fails without the fix). Tests that use `TestClient(app)` without `with` skip the lifespan and still leave their process until the end (8 call sites; not a problem at this count).
- **start-dev.bat** (decision 0038): the console and driver run from a mirror in `%LOCALAPPDATA%\LogiMind` (robocopy of `frontend\`, `driver\`, `design\`); `npm ci` runs there when the lock file changed. Checked from a fresh state (no node_modules in the repo, no mirror): `npm ci` twice (13 s each), API, worker, console and driver answered; the console signed in to "Demo Fleet (synthetic)" by itself in Chrome; one new plan (4 orders, engine auto -> hybrid, 2 s) was solved by the separate worker in 6 s, validator feasible, distance 24.00 (the hand-checked optimum). Not hot-reloading repo edits is the known cost.
- **Removed:** `frontend
ode_modules`, `driver
ode_modules`, `frontend\dist`, `driver\dist`, 30 cache folders (`__pycache__`, `.pytest_cache`, `.ruff_cache`, incl. 8 in `docs/context/prior-code`), the old `%TEMP%` folders `lm_shot`, `lmfe`, `lm_fe`, `lm_ui`, `lm_demo_s6`, `lm_browser_s5`, `lm_bench_smoke`, `bench`, `benchchk` and 31 old test logs. Repo on disk: 258.1 MB in 29,837 files -> 32.5 MB in 2,258 files (13.1 MB of it `.git`). The mirror outside OneDrive is 223.9 MB.
- README: repaired the damaged `backend
equirements.txt` path (its `
` had been stored as a carriage return).
- **Tests (12 Nov 2026):** backend **403 passed, 0 failed** (full suite alone, 4 min 29 s); ruff passes; console 87 passed and builds; driver 21 passed and builds.

### Sixteenth session, 11 Nov 2026: replan chain fix and OpenAI removed (branch `cleanup-and-fixes`; commits 04c1f09, b6c9317, 36db243)
- **Replans keep earlier disruptions** (decision 0037): `apply_event` reads the parent plan's replan record. A broken vehicle stays blocked (breaking it again is a 422), completed stops are at least the earlier frozen count, and retried customers keep the retry rule until completed or dropped. Each carried item is in the notes; the replan record now stores `retry`. Test `backend/tests/test_replan_chain.py` (3): all 3 failed on the old code (session-start run: 399 passed, 3 failed) and pass now.
- **Console replan form:** completed counts start from (and cannot go below) the frozen counts, a broken vehicle is not offered and its count is locked, the GA is disabled while a retry rule is carried. New test in `src/test/ops.test.jsx`.
- **Copilot settings:** OpenRouter kept; OpenAI not offered (keys refused in the browser, nothing sent; no OpenAI choice; "another OpenAI-compatible service" sends nothing without a base URL). Decision 0036 amended; README and CLAUDE.md invariant 12 match. Backend `openai` adapter unchanged.
- **Tests (11 Nov 2026):** ruff passes; console 87 passed, console build OK, driver 21 passed. Backend: full suite 400 passed, 2 failed (`test_replan_chain.py::test_second_replan_keeps_the_retry_rule` timed out in its *first* plan before any replan; `test_runner_export.py::test_benchmark_script_end_to_end`: "OpenBLAS error: Memory allocation still failed"). The laptop had ~5 GB free with browsers, VS Code and PowerPoint open; an earlier full run during a parallel disk scan also had `MemoryError` failures. Rerun alone, the three affected files pass (23 passed). **Cause found on 12 Nov (next section): a solver-process leak, not the laptop.**

### Fifteenth session, 10 Nov 2026: "Load models" (decision 0035)
- **Branch note:** the repository was on `main` when this session started, and the fourteenth session's commit 2d7649b had gone straight onto `main`. `ui-redesign` was fast-forwarded to `main` and this session's commit is on `ui-redesign`.
- **Built:** "Load models" in the Copilot settings box → `POST /api/copilot/models` (same key header, guard, https, timeouts and 1 MB cap). Groq / OpenAI-compatible `GET /models`, Gemini `GET /models?pageSize=1000` (generateContent models only), Ollama `/api/tags`; non-chat models (embedding, speech, guard, moderation, image) filtered out; sorted. Picking a model fills the name and runs Test connection at once. A list that cannot be fetched gives a plain reason and the text field stays. With no model name (console settings, none in `backend\.env`) the first chat model of the list is used and named; the console writes it into the field.
- **Tests:** backend +14 (`tests/test_copilot_models.py`, fake HTTP and DNS), console +7 (`src/test/copilotModels.test.jsx`).
- **Browser check** with a fake Groq server (screenshots 43-47 in `docs/report/demo/`): Key rejected with the fallback; 2 chat models listed (speech and guard filtered); pick → Works; empty name → "another-chat-model was chosen"; metadata address blocked; provider down → Not reachable; no key in localStorage, page or logs. Not checked: a real provider's list, Gemini's and Ollama's lists in the browser.
- **Tests at the end (exit codes checked):** ruff exit 0; console **77 passed**; driver PWA **21 passed**; console build exit 0. Backend: the first full run had **1 failure**, `tests/test_replan.py::test_replan_is_tenant_isolated` (its first 1 s plan was not finished within the test's 30 s wait; that run took 317 s instead of about 250 s). Alone it passed 3 of 3 and its file 15 of 15; the second full run: **386 passed** (exit 0). This change touches no replan code; the cause of the slow run was not found (laptop load is a guess). The test was not changed.

### Fourteenth session, 10 Nov 2026: the busy-port report (decision 0034)
- **Reported:** start-dev.bat said 8000, 5173 and 5174 were busy while `netstat ... | findstr` printed nothing.
- **Found:** the ports WERE in use by a LogiMind started with start-dev.bat at 20:11 (API answered `/api/health` on 8000, both Vite servers answered). netstat is unreliable on this Windows build (10.0.26300): the listener rows carry invalid state values (1/0/6 instead of 2), so netstat showed them as CLOSED or not at all, and two runs seconds apart disagreed. The old check (a successful connect = busy; owner from netstat text) could also be fooled by anything that accepts connections without a listening socket. No lock file exists.
- **Fixed:** busy = a LISTENING socket in the OS listener table (`GetExtendedTcpTable`, listener class, via ctypes; state field ignored), printed with program name, PID and address; Windows excluded port ranges reported as `[reserved]`; `start-dev.bat --force-ports` skips the check; flags in any order.
- **Tests:** `test_devtools.py` 4 → 10 (real IPv4 and IPv6 listeners with this process's PID, free ports, TIME_WAIT, a connect-only success, reserved ranges, the .bat with and without `--force-ports`). By hand: a listener on spare port 8091 named with its PID; `--force-ports` skipped; free ports passed.
- **Incident:** a manual busy-port run used a listener that exited at once, so start-dev.bat really started LogiMind on 8091-8093 with the real `backend\.env` and database; its windows were stopped by exact process tree. Its start-up rotated the demo key, so the LogiMind still running from 20:11 now gets 401 for its demo key: **restart it** (close its windows, run start-dev.bat). Known limit: two instances sharing one database revoke each other's demo key.
- **Tests at the end (exit codes checked):** ruff exit 0; backend **372 passed** (exit 0); console **70 passed**; driver PWA **21 passed** (both unchanged).

### Thirteenth session, 10 Nov 2026: Copilot settings in the console (commit 017113d and the browser-check/PROGRESS commit; decision 0033)
- **Built:** a "Copilot settings" box (docked panel and Copilot page): provider (server settings, Ollama, Groq, Gemini, OpenAI-compatible + base URL), model, key (password field), Test connection, Clear key. The key stays in sessionStorage for the tab only (never localStorage, never in a URL), shows as its last 4 characters, travels as an `X-LLM-Key` header on copilot requests, and is cleared on sign-out. `POST /api/copilot/test` makes one minimal call (model list) and returns only ok / a kind / a plain message. The server builds one LLM per request and never stores, logs, audits or returns the key; refused headers get a plain 400 that never repeats them. Console settings win field by field over `backend\.env`.
- **Outbound-request guard** (`backend/app/copilot/netguard.py`): https only (http only for the server's own Ollama URL, never typed); every resolved address must be public (private, loopback, link-local/metadata, CGNAT, multicast, ULA, IPv4-mapped blocked); connection pinned to the checked IP (DNS rebinding); no redirects; 5 s connect / 30 s read; 1 MB cap.
- **Tests:** backend +53 (`tests/test_copilot_settings.py`: 169.254.169.254, 10.x, 127.0.0.1, metadata.google.internal, a host resolving to 192.168.x, a host with one public and one private address, IPv6 ULA and IPv4-mapped forms; pinning; a DNS change between calls; redirect; 1 MB; plain results; key never in replies, logs or audit; precedence; invariants; tenant isolation; fake HTTP and fake DNS only). Console +11. Two expectations in `test_llm_providers.py` now name the new "model not found" kind (same strictness).
- **Browser check** with a local fake Groq server (details in decision 0033; screenshots 38-42 in `docs/report/demo/`): Key rejected, Rate limit reached, Model not found, Works, a tool-built answer, Settings not accepted (http), Address not allowed (metadata, localhost via real DNS, 10.0.0.5), Not reachable, Clear key; no key in localStorage, URLs, the page or the logs. **Fixed:** a refused setting made the panel say "undefined: not available" / "No local model is available".
- **Not checked:** any real provider; an OpenAI-compatible success and the pinned TLS connection to a real public host (unit tests only); Gemini in the browser.
- **Tests at the end (exit codes checked, foreground):** ruff exit 0; backend **366 passed** (exit 0, 16 library deprecation warnings); console **70 passed**; driver PWA **21 passed**; console build exit 0.

### Twelfth session, 10 Nov 2026: optional hosted copilot providers (commit 90a1bff and the browser-check/PROGRESS commit; decision 0032)
- **Before:** providers were `ollama` (default) and `none`, plus `FakeLLM` for tests; `llm_from_env()` read `LOGIMIND_LLM_PROVIDER` from the process environment once at start-up (start-dev.bat copies `backend\.env` into it).
- **Built:** `GroqLLM` (chat/completions, `response_format: json_schema`) and `GeminiLLM` (generateContent, `responseMimeType: application/json` + `responseJsonSchema`) on plain httpx; `LOGIMIND_LLM_PROVIDER=groq|gemini`; `GROQ_API_KEY`/`GROQ_MODEL`/`GEMINI_API_KEY`/`GEMINI_MODEL` read from the `backend\.env` file only (global environment ignored, tested), listed empty in `backend/.env.example`; base-URL override only to localhost. Key only in a request header, hidden from repr, scrubbed from messages. Plain errors for missing/rejected key, rate limit, network, server, unknown model; the agent replies instead of crashing. Validation, one retry and the clarifying question unchanged (tested with the hosted adapter). Console names provider and model. CLAUDE.md invariant 12 relaxed for optional free tiers only; README section with key creation and a do-not-share warning.
- **Tests:** backend +21 (`tests/test_llm_providers.py`, fake HTTP layer, no network), console +3 (`src/test/providers.test.jsx`).
- **Browser check** with a local fake Groq server on a scratch clone (details in decision 0032; screenshots 34-37 in `docs/report/demo/`): provider/model shown; tool-built answers; new plan; **Confirm and Cancel seen in a browser for the first time** (with the fake provider); refusal path; 429; wrong, empty key and unreachable provider shown plainly; no key in replies, page, localStorage or logs. Fixed: a missing full stop in the hosted message.
- **Not checked:** the real Groq or Gemini service (no key in `backend\.env`); Gemini in the browser; any real model's accuracy (still NOT RUN).
- **Noticed:** the developer's own `uvicorn` on port 8000 (process 39788) was no longer running at the end of the session; this session's kill commands targeted only its own process trees. Cause unknown (the laptop was low on memory earlier). Their Vite server on 5173 was still running.
- **Tests at the end (exit codes checked, run in the foreground):** ruff exit 0; backend **313 passed** (exit 0, 16 library deprecation warnings); console **59 passed**; driver PWA **21 passed**.

### Eleventh unattended session, 10 Nov 2026: every feature in a real browser, and the presentation script (commit 4185635 and the script/PROGRESS commit)
- **Opening state:** `ui-redesign` = `main` at ea11e61. `start-dev.bat` (no arguments, default ports) **stopped with a clear message**: port 8000 busy (python.exe, the developer's own `uvicorn --reload`) and 5173 busy (node.exe, their Vite); nothing was stopped. The walk-through therefore ran `start-dev.bat --no-browser` on ports 8070/5197/5198 with a throwaway database and data folder (the developer's database was not touched), OSRM not configured, Ollama not running, and `LOGIMIND_WEBHOOK_ALLOW_PRIVATE=1` for a local test receiver.
- **Results** (table, notes and 33 screenshots in `docs/report/demo/`): worked: demo and API-key sign-in, CSV import with bad rows, synthetic sample, plans with OR-Tools / GA / hybrid / auto (explanation shown), validator status, fallback-distance warning, timeout shown as a timeout, breakdown and urgent-order replans, driver link / app / delivered / failed with reason / photo / revoke, ETA opt-in rule (API), copilot no-model message, webhooks (signed, delivered on attempt 1), audit log, 429 after 20 requests, tenant isolation (every cross-tenant call 404), research comparison and Benchmark lab, OpenAPI page, separate worker. Worked with problems: Excel import (depot), time windows (no per-stop times on the plan page), timeout (wording), failed-delivery replan (see below), offline sync (badge), Benchmark lab chart ticks, selector model card (document only). **Not tested:** Confirm/Cancel and copilot answers/refusal (no local model), the Navigate target (link checked, external site not opened), Chrome's own offline mode (server stopped instead), a phone. **Failed:** none.
- **Fixed** (tests: console +4 in `src/test/fixes.test.jsx`, driver +1; the driver test was checked to fail without the fix): UTC timestamps shown as local time; lon/lat orders kept the planar depot 50/50; "This plan is completed" for a plan without a solution; Drivers page wording; driver badge "Online" while reports could not be sent. All re-checked in the browser.
- **Bigger problems, listed not fixed** (also in `docs/limitations.md`): replans forget earlier disruptions (a vehicle that broke down got 6 stops in the next replan); no arrival times on the plan page; selector model card not in the console; the OSRM fallback note names a setting.
- **Presentation script** `docs/DEMO_SCRIPT.md` (about 15 min; each step VERIFIED / NOT VERIFIED; numbers only from `docs/report/evaluation.md` and this walk-through). It **replaces** the old 10-minute `docs/demo_script.md`: on Windows the names differ only in case, so the new file overwrote the old one; the old text is in git history (before this commit). Synthetic demo files in `docs/demo_files/`.
- **Session notes:** the Claude in Chrome extension disconnected once and reconnected; the test API was restarted three times on purpose. A broad "stop all workers" command was refused by the permission system; the test processes were then stopped by exact process id.
- **Tests (exit codes checked):** before the first commit: ruff exit 0; backend **292 passed** (exit 0, 16 library deprecation warnings); console **56 passed** (+4); driver PWA **21 passed** (+1); both `vite build` exit 0. **Final run after the docs changes: ruff exit 0, console 56 passed, driver 21 passed; the backend run was STOPPED by Claude Code at 59% (no failures up to then) because the laptop was critically low on memory, and was not restarted (session rule).** The backend code did not change after the complete 292-passed run; the second commit holds documents only.
- **Memory:** the same low-memory stop also ended the test-instance launcher; the test servers (ports 8070/5197/5198) were then stopped by exact process id. The developer's own servers on 8000 and 5173 were never touched.

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
- **P9 limits:**
  - No offline photo queue.
  - No contacts / notification-log screen in the console (API only).
  - ETAs are planned times; they are not updated from the driver's progress.
  - The server does not strip EXIF from photos; only the PWA's re-encoding does, and that is untested in a browser.
  - Without `LOGIMIND_DRIVER_LINK_SECRET`, links die on restart. Production needs HTTPS and CORS (or the same origin) for the PWA.
  - The driver app has not been tried on a real phone.
- Ops console in a browser: sign-in, import (good and bad CSV), plan with the fallback flag, all three replan forms and the copilot's "no model" state were checked on 5 Nov 2026. Not checked in a browser: `.xlsx` import, the copilot with a model, the research pages and the Drivers panel since the queue change. The console does not warn when no worker is running (plans just stay queued).
- Copilot sessions are in memory (lost on restart). Chat requests block until the solver finishes.
- P6: job queue done and tested on SQLite (incl. a killed worker process). Docker Compose (with the worker service), Postgres and `.env.example` are written but **UNTESTED** (no Docker). Migrations tested on SQLite only. CLI experiment scripts run outside the queue.
- P4 limits: never run against a self-hosted OSRM; no OSRM map extract downloaded (559 MB smallest official file); detour factor 1.3 and 25 km/h are uncalibrated assumptions; OSRM durations are free-flow; the cache keeps whole matrices only.
- Webhook SSRF guard does not resolve host names (decision 0010). The rate limiter is in-process only.
- Replanning: the GA cannot keep frozen stops or retries. The failed attempt's own travel is not modelled; a retried delivery is no longer the next stop (decision 0023), but there is no minimum time delay. The replanning experiment (6 synthetic instances, one seed) ran before the retry rule.
- Selector: trained on synthetic data only; on the held-out benchmarks it had the lowest overall regret but lost to always-GA+LS on CVRP and to always-hybrid at 3 s; it ignores the budget (model card).
- P10: the 10 s held-out run is PARTIAL (134 of 216 runs; decision 0024; resume command there); copilot numbers NOT RUN; no calibration of the distance estimate. Gehring-Homberger not downloaded; hybrid split untuned. The full list is in `docs/limitations.md`.
- Team answers still missing (docs/decisions/0002). Docker and Ollama not installed.
- UI redesign (branch `ui-redesign`, not merged): not tried on a real phone; copilot Confirm/Cancel not seen in a browser (no model); research pages and Methodology not re-walked in a browser (now behind the Research link). The console now keeps the session when the server is down (decision 0031).
- Demo set-up: `start-dev.bat` ran on the default ports from a fresh state on 12 Nov 2026 (decision 0038); not yet on the demo laptop; the venv in `%TEMP%` can be damaged by something outside the project (seen once; decision 0030).

### Deployment plumbing, 12 Nov 2026 (decision 0039)
- Console reads the API address from `VITE_API_URL` at build time (old `VITE_API_BASE` still works); `frontend/vercel.json` rewrites routes to `index.html`.
- API: `GET /health`; CORS also allows `FRONTEND_URL` (environment, else the line in `backend/.env`); `LOGIMIND_PUBLIC_DEMO=1` (with `LOGIMIND_DEMO_MODE=1`) hands the synthetic demo key to any caller; `render.yaml` for a free Render web service; `backend/requirements.txt` pinned.
- **Verified:** backend **407 passed** (12 Nov 2026, Python 3.14.7), ruff passes, frontend **87 passed**, `npm run build` OK with `VITE_API_URL` set; a uvicorn start on an empty data dir with the public demo seeded three validator-feasible plans and answered CORS for `FRONTEND_URL`.
- `start-demo.bat` (repo root): starts the API (`npm run dev` in backend, reads `backend/.env`) and a Cloudflare quick tunnel in two windows, keeps either if already running, and prints the tunnel address (from cloudflared's local `/quicktunnel` metrics endpoint). Verified on 12 Nov 2026 with both already running: one backend, one tunnel; through the tunnel with Origin `https://logi-mind-ten.vercel.app`: `/health` OK, demo session handed out, 20 plans all completed and feasible. Not verified: a cold start of the tunnel by the script (it would have changed the live address).
- The console signs in to the demo by itself (`AuthContext` calls `/api/demo/session`); "not signed in" came from a backend started with plain uvicorn, which does not load `backend/.env` (demo mode off, 404). No frontend change was needed.
- **Not verified:** no Render deploy done; the Vercel console against the Cloudflare tunnel was not checked by Claude. Through a tunnel the local-only demo sign-in is refused (403), so the console shows the API-key sign-in unless `LOGIMIND_PUBLIC_DEMO=1` is set.

### Console on Vercel reaches `npm run dev` on this PC, 13 Nov 2026 (decision 0040)
- `npm run dev` (backend) also starts a Cloudflare quick tunnel when `backend/.env` has `LOGIMIND_PUBLIC_DEMO=1` and `FRONTEND_URL`, and prints `<FRONTEND_URL>/?api=<tunnel>`; `LOGIMIND_TUNNEL=0` turns it off (`start-demo.bat` sets it, as it runs its own tunnel).
- Console: `?api=` sets the API address at run time (only `*.trycloudflare.com` and localhost), remembered in localStorage until `?api=default`; header shows "Server: <host>"; a changed address clears the tab's sessionStorage (key, copilot settings). The offline banner now uses the same text as `SERVER_DOWN`.
- **Verified (13 Nov 2026):** frontend **89 passed** (+2 in `lib.test.js`), `vite build` OK; backend **407 passed**; ruff passes. A real `npm run dev` on port 8010 printed the link; through the tunnel `/health` 200, CORS allows `https://logi-mind-ten.vercel.app`, `/api/demo/session` returned the synthetic demo tenant.
- **Not verified:** the Vercel console itself with `?api=` (the new console code is not deployed until it is pushed and Vercel rebuilds). Stopping the background test run left its uvicorn (8010) and cloudflared child running; Ctrl+C in a normal console window stops both, since Windows sends it to the whole window.

## Known quirks
- Instance ids hash coordinates as given: `10` and `10.0` give different ids (baseline behaviour, kept so old ids stay valid). The API always sends floats.

## Next steps
1. Finish the 10 s held-out run with `--resume` (82 runs, about 14 min; close other programs first so memory is free; command in decision 0024), then `python experiments/selector_heldout_eval.py` and `python experiments/p10_report.py`; the PARTIAL labels go away by themselves. Update the deck's slide 24 if a verdict changes.
2. Install Docker Desktop (WSL2); run `docker compose up --build` (API + worker + Postgres) and fix what breaks (migrations and the queue lock on Postgres first). Team: choose the OSRM map source (decision 0020) and run one plan with `distance_source=osrm`.
3. Team: freeze `docs/eval/copilot_instructions_DRAFT.json`; install Ollama and measure the copilot for that exact model; fill [weeks remaining] / [review dates] in the deck. Then: retrain or drop the selector's budget-blind trees (it never changes its choice with the budget), and test the driver PWA on a phone.

4. Team: review the `ui-redesign` branch (screenshots in `docs/report/ui/`) and merge it, or ask for changes; try the driver app on a real phone outdoors.
5. Before the demo: close other dev servers, run `start-dev.bat` on the demo laptop once (first run downloads packages), and check that the browser opens signed in with three plans. Decide whether the venv should live outside `%TEMP%` (decision 0030).
6. Done 11 Nov 2026: replans keep earlier disruptions (decision 0037). Team: decide whether the plan page should show planned arrival times. Rehearse `docs/DEMO_SCRIPT.md` once with the screenshots as a fallback.

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

Commands added in the eighth unattended session (Git Bash; the tokens in `design/` must sit next to the app copies):
```
rm -rf "$TEMP/design" && cp -r design "$TEMP/design"         # %TEMP%\lmfe_s3 and %TEMP%\lmdrv resolve ../design
# copy frontend/* (not node_modules) to %TEMP%\lmfe_s3 and driver/* to %TEMP%\lmdrv, then in each:
npx vitest run; echo "vitest exit=$?"                          # console 39 passed, driver 20 passed
npx vite build; echo "build exit=$?"
```

Commands added in the seventh unattended session (Git Bash, repo root; exit codes checked, never piped):
```
"$TEMP/lmv/Scripts/python" -m ruff check .; echo "ruff exit=$?"
cd backend && timeout 1500 "$TEMP/lmv/Scripts/python" -m pytest -q > "$TEMP/backend.log" 2>&1; echo "pytest exit=$?"; tail -1 "$TEMP/backend.log"   # 268 passed
"$TEMP/lmv/Scripts/python" experiments/compare_engines.py --estimate-only --methods ortools ga_ls hybrid_seed_ls --budgets 10 --seeds 3 --instances <24 keys>   # 216 runs, ~36 min
"$TEMP/lmv/Scripts/python" experiments/selector_heldout_eval.py   # no solver runs
"$TEMP/lmv/Scripts/python" experiments/p10_report.py              # no solver runs
```

Commands added in the sixth unattended session (Git Bash; backend/ unless noted):
```
uvicorn app.main:app --port 8000          # API only queues jobs (LOGIMIND_WORKER=external, default)
python -m app.jobs.worker                 # second terminal: runs plans, replans and research runs
LOGIMIND_WORKER=inline uvicorn app.main:app --port 8000   # one-process development (tests do this)
timeout 1500 "$TEMP/lmv/Scripts/python" -m pytest -q        # 265 passed (tests/test_jobs.py starts real worker processes)
# repo root:
"$TEMP/lmv/Scripts/python" experiments/compare_engines.py --estimate-only --methods ortools ga_ls hybrid_seed_ls --budgets 3 --seeds 3 --instances <24 held-out keys, see decision 0022>
"$TEMP/lmv/Scripts/python" experiments/p10_report.py         # rebuilds docs/report from stored runs (no solver runs)
```

Commands added in the fifth unattended session (Git Bash, repo root):
```
cd backend && for i in $(seq 1 10); do timeout 300 "$TEMP/lmv/Scripts/python" -m pytest -q "tests/test_hybrid.py::test_guard_stops_a_frozen_run_and_reports_a_timeout"; done   # 10 passed
cd backend && "$TEMP/lmv/Scripts/python" -m pytest -q tests/test_distances.py      # 16 passed, offline
"$TEMP/lmv/Scripts/python" experiments/osrm/record_fixture.py --base-url http://localhost:5000 --out <file>   # re-record from your OSRM
LOGIMIND_OSRM_URL=http://localhost:5000 uvicorn app.main:app --port 8000          # road distances (unset: flagged fallback)
docker compose up --build                                                         # UNTESTED; needs .env (copy .env.example)
```

Commands added in the fourth unattended session (Git Bash, repo root):
```
cd backend && timeout 1500 "$TEMP/lmv/Scripts/python" -m pytest -q --tb=short     # 241 passed
# driver PWA: copy driver/ to %TEMP%\lmdrv (npm install there once), then:
npx vitest run            # 17 passed
npx vite build && npx vite preview --port 5174   # service worker + manifest; proxies /api to :8000
# console: copy frontend/src to %TEMP%\lmfe_s3, then npx vitest run   # 32 passed
LOGIMIND_DRIVER_LINK_SECRET=<32+ chars> uvicorn app.main:app --port 8000   # links survive restarts
```

