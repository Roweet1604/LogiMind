# 0021: Durable job queue and a real worker process

Date: 5 Nov 2026 (unattended session). Status: built and tested on SQLite; the Compose `worker` service is UNTESTED (no Docker, decision 0020).

## Problem
Plans, replans and research runs ran on a thread inside the API process (plus the guarded solver process). Queued work was lost on a restart, and the API could not be separated from the solvers (P6 open item).

## Decision
- **Table `jobs`** (migration 0006) in the main database: kind (`plan`, `replan`, `benchmark`), lane (`planning`, `benchmark`), tenant, plan, payload, state, attempts, worker id, heartbeat, result (benchmark jobs), error and requeue history. A plan and its job are committed **in one transaction**, so a stored plan always has its job.
- **Worker process:** `python -m app.jobs.worker` (Compose service `worker`). It claims one job at a time, runs it in the existing guarded solver process (the hard wall-clock guard is unchanged: a frozen run is killed and stored as `hard_timeout`), writes the result, and sends the webhooks. The API process runs no solver jobs. `LOGIMIND_WORKER=inline` runs the same worker loop in a thread of the API, for development and the test suite only.
- **Claim rules:** FIFO over all jobs. A **benchmark** job starts only when nothing else is running, and nothing starts while it runs (invariant 4: one benchmark job at a time). **Planning** jobs may run side by side when several workers run. A waiting benchmark job is not overtaken by later planning jobs. Every claim first updates the single `queue_lock` row, which serializes claims on SQLite (database write lock) and PostgreSQL (row lock); a test with 8 concurrent claimers and 3 benchmark jobs gets exactly one claim.
- **Crash recovery:** a running job sends a heartbeat every 2 s. A job without a heartbeat for 30 s (`LOGIMIND_JOB_STALE_S`) is requeued, with a history entry, up to 2 claims in total; after that the job and its plan are **failed with the reason** and a `plan.failed` webhook is sent. A worker that lost its job cannot record a result on it. A job's solve may therefore run twice; results are written once.
- **Research runs** (dev-only endpoints) become `benchmark` jobs; the research store submits them one by one and waits for each.
- **Tenant isolation:** `jobs` is not a tenant-owned table, because benchmark jobs have no tenant and only workers read it. The worker reads and writes a job's plan **through a tenant session for the job's tenant**, so a job naming another tenant's plan fails without touching it (tested with a forged job). Tenants see their own plan's job (state, attempts, requeues) in `GET /api/plans/{id}`, through an explicit tenant filter.
- **Replan timing:** `disruption_to_feasible_s` now uses the wall clock (request received in the API, result made in the worker; two processes), not `perf_counter`.

## Limits (known, not hidden)
- The queue cannot stop **other** programs from loading the machine: the CLI experiment scripts (`experiments/*.py`) still run outside the queue. Run them when no worker is busy.
- Polling (0.5 s) plus one claim per poll; fine for a small fleet, not tuned for high load.
- Without a worker, plans stay `queued` (shown on the plan and in `/api/health`); the console does not yet warn that no worker is running.
- Tested on SQLite only (including two real worker processes, a hard kill and a restart). PostgreSQL behaviour of the lock row is by design, not tested.
