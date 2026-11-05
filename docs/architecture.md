# LogiMind architecture

Status words used here: **built and tested** (automated tests pass), **verified in a browser** (walked through by hand), **UNTESTED** (written, never run), **not run**. The full list of gaps is in [limitations.md](limitations.md).

## Picture in one paragraph
A dispatcher (ops console) or another program (REST API with an API key) sends orders. The API stores a **plan** and a **job** in the database. A **worker process** takes the job, gets the distances, runs a solver engine inside a **guarded solver process**, and sends the routes to the **independent validator**. Only the validator decides "feasible". The plan, the audit log and the webhooks then show the result. Drivers get a signed link to their own route in the **driver PWA**. The **copilot** turns plain-language requests into checked tool calls; it never writes routes.

```
 ops console (React)      other systems           driver PWA (React, offline queue)
        |  X-API-Key            |  X-API-Key               |  X-Driver-Token (one route)
        v                       v                          v
 +-------------------------- FastAPI (backend/app/api) -----------------------------+
 | auth + rate limit | plans | import | replan | webhooks | audit | copilot | driver |
 +---------+-------------------------+------------------------------+-----------------+
           | plan + job (1 transaction)                             | reports, photos
           v                                                        v
   +---------------- database (SQLite dev / PostgreSQL in Compose, UNTESTED) ---------+
   | tenants, api_keys, plans, jobs, audit_log, webhooks, driver_links, stop_events, |
   | contacts, notification_log  (tenant filter enforced in app/db/session.py)        |
   +-----------------------------------------^----------------------------------------+
                                             | claim / heartbeat / result
                              +--------------+---------------+
                              | worker (python -m app.jobs.worker)
                              |  distances -> guarded solver process -> validator
                              |  -> metrics -> plan row -> webhooks
                              +-------------------------------+
```

## Components
| Component | Where | Status |
| --- | --- | --- |
| Problem model (CVRP, time windows, service times, optional road matrix) | `backend/app/models/problem.py` | built and tested |
| Engines: OR-Tools (audited defaults), own GA (+ local search, fleet repair), hybrid (OR-Tools seed, then GA) | `backend/app/solvers/` | built and tested; compared in [report/evaluation.md](report/evaluation.md) |
| Wall-clock guard: every solve runs in a separate process that is killed at 1.5 x budget + 5 s | `backend/app/services/guard.py` | built and tested |
| Independent validator and metrics (capacity, time windows, lateness, unserved, fleet size) | `backend/app/evaluation/` | built and tested; all 93 published best-known solutions pass it |
| Engine picker (`engine=auto`) | `backend/app/selector/` | built and tested; trained on synthetic data; not a proven gain (model card) |
| Durable job queue + worker process | `backend/app/jobs/` (decision 0021) | built and tested, incl. a killed worker and a restart |
| Distances: straight line, estimate (x1.3 detour at 25 km/h), self-hosted OSRM, cache, flagged fallback | `backend/app/distances/` (decision 0019) | built and tested offline; never run against a self-hosted OSRM |
| Tenants, API keys (SHA-256 only), tenant filter at the data layer | `backend/app/db/` | built and tested (isolation tests) |
| Order import (.csv/.xlsx) with row-level errors | `backend/app/services/order_import.py` | built and tested; CSV verified in a browser |
| Replanning (breakdown, failed delivery, urgent order; frozen stops; warm start) | `backend/app/replan/` | built and tested; urgent order verified in a browser |
| Webhooks (HMAC-signed, retries, SSRF guard), audit log | `backend/app/services/notify.py`, `webhooks.py` | built and tested |
| Copilot (LangGraph; LLM returns one validated intent; six tools; grounding check) | `backend/app/copilot/` | built and tested with a fake LLM only; **no real model run** |
| Driver links, stop reports, photos | `backend/app/driver/` | built and tested; PWA verified in desktop Chrome, not on a phone |
| ETA notifications (stub sender only, opt-in) | `backend/app/messaging/` | built and tested; nothing is ever sent |
| Ops console | `frontend/` | tests pass; main flows verified in a browser |
| Docker Compose (postgres, api, worker, console, driver, optional osrm) | `docker-compose.yml` | **UNTESTED** (no Docker on the laptop) |

## Rules the design enforces
1. **The LLM never makes routes.** The copilot's model output is one Pydantic intent with no route fields (`extra="forbid"`); routes only come from an engine, and every plan passes the validator before it is called feasible.
2. **Failures are shown as failures.** Solver timeouts (`hard_timeout`), "no solution", worker crashes (job failed after 2 claims) and OSRM fallbacks are stored and displayed as such.
3. **Fair comparisons.** Same instance, same matrix, same objective, same total budget; benchmark jobs run alone (queue rule); the matrix is built before the clock starts.
4. **Tenant isolation at the data layer.** Every ORM query in a tenant session gets `tenant_id = :tenant`, and writes for another tenant are refused. The worker writes plan results through the job tenant's session.
5. **Offline tests.** Every outside service has an adapter and a fake: LLM (FakeLLM), OSRM (recorded answers), webhooks (FakeSender), messages (stub sender).

## A plan's life
1. `POST /api/plans` validates the instance, builds the distance matrix if asked (`distance_source`), picks the engine (or uses the requested one), and stores the plan and its job together. Answer: `202` with the plan id.
2. A worker claims the job (FIFO; benchmark jobs alone), marks the plan `running` and sends heartbeats every 2 s.
3. The solver runs in the guarded process. If it overruns, it is killed and the plan is stored as `hard_timeout` with no routes.
4. The validator checks the routes on the real instance; metrics are computed; the plan becomes `completed` with `feasible` true or false.
5. Webhooks `plan.completed` / `plan.failed` go out; the audit log gets a row.
6. If the worker dies, another worker (or the restarted one) requeues the job after 30 s without a heartbeat; after 2 claims the plan is failed with the reason.

## Configuration
All settings are environment variables (no secrets in files); the list is at the top of `backend/app/main.py` and `backend/app/jobs/worker.py`, and `.env.example` has the Compose ones.
