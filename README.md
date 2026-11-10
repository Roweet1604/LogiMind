# LogiMind

## How to run (Windows)
1. Install Python 3.12+ (python.org, tick "Add to PATH") and Node.js LTS (nodejs.org). Nothing else.
2. Double-click `start-dev.bat` in this folder (or type `start-dev.bat` in Command Prompt here).
3. The first run sets itself up (Python packages, `backend\.env`, npm packages); this download can take 10-30 minutes, once.
4. Four "LogiMind" windows open and the browser opens the console, signed in to "Demo Fleet (synthetic)" with ready plans.
5. To stop, close the four "LogiMind" windows. If a port is busy, the script says which one and stops nothing.

An API-first hybrid optimization platform with an AI dispatch copilot for small-fleet logistics (Capstone ASAC-CP-056).

**Status:** P1-P3, P5, P7 and P9 done; P4 road matrix done offline (not yet run against a self-hosted OSRM); P6 done except that Docker Compose is written but UNTESTED (durable job queue and worker process added 5 Nov 2026); P8 copilot built but tested only with a fake LLM (no real model run yet). Route solvers (OR-Tools, our own GA, a hybrid), an engine picker, a tenant API with plans, imports, webhooks and replanning, a dispatch copilot, a driver PWA and stub ETA notifications. See `PROGRESS.md` for what works and what does not yet; `PLAN.md` has the roadmap.

## Documents
- [docs/architecture.md](docs/architecture.md): components, rules, a plan's life
- [docs/api_guide.md](docs/api_guide.md): the API step by step
- [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md): the 15-minute presentation script; every step marked VERIFIED or NOT VERIFIED from the browser walk-through in [docs/report/demo/](docs/report/demo/README.md)
- [docs/limitations.md](docs/limitations.md): everything UNTESTED, NOT VERIFIED or NOT RUN
- [docs/report/evaluation.md](docs/report/evaluation.md): P10 evaluation (tables, figures, significance tests)
- [docs/report/deck_draft.md](docs/report/deck_draft.md): revised slide content (draft)

## Quick start (Windows), in more detail
Keep the Python virtual environment **outside OneDrive** (OneDrive sync and long paths break installs).

**`start-dev.bat`** (decisions 0028, 0030) does everything that is missing, once: creates `%TEMP%\lmv` with `py -3`
or `python`, installs `backendequirements.txt`, writes `backend\.env` (git-ignored) from `backend\.env.example`
with a new `LOGIMIND_DRIVER_LINK_SECRET` (existing values are never changed), and runs `npm install` in `frontend\`
and `driver\`. Then it checks the ports, opens four windows: **API** (http://127.0.0.1:8000, local only),
**worker** (runs the solver jobs), **console** (http://localhost:5173) and **driver app** (http://localhost:5174),
waits until the API and the console answer, and opens the console. If a port is busy it names the port (and the
program, when Windows shows it), stops nothing and exits. `--dry-run` shows what would happen; `--no-browser` skips
the browser. Other ports: set `API_PORT`, `CONSOLE_PORT`, `DRIVER_PORT` first.

**Demo mode** (decision 0029): `start-dev.bat` turns it on. The API creates the tenant "Demo Fleet (synthetic)" with
three plans on made-up orders, and the console signs in to it by itself (label "Demo mode"). It works only on this
computer (API bound to 127.0.0.1) and is never on in Docker Compose. To start without it, put
`LOGIMIND_DEMO_MODE=0` in `backend\.env`. "Sign out" on the Account page lets you use a normal API key.

**Your own tenant and API key** (the key is printed once; only its SHA-256 is stored):
```
start-dev.bat tenant "Acme Fleet"
```
Copy the `lm_...` key it prints and paste it on the console's **Account** page. Lost it? `cd backend` then
`%TEMP%\lmv\Scripts\python manage.py issue-key <tenant_id>`.

**Research pages** (OR-Tools vs GA comparison, Benchmark lab, Methodology) appear under one "Research" link only when
the API runs with `LOGIMIND_DEV_RESEARCH_ENDPOINTS=1` (decision 0031).

**The same by hand, one Command Prompt each** (run `set` lines for every variable in `backend\.env` first, or put
them in each window; the API needs `LOGIMIND_WORKER=external` when a separate worker runs):
```
:: 1. API         (folder: backend)
cd backend
set LOGIMIND_WORKER=external
%TEMP%\lmv\Scripts\python -m uvicorn app.main:app --reload --port 8000

:: 2. Worker      (folder: backend)
cd backend
%TEMP%\lmv\Scripts\python -m app.jobs.worker

:: 3. Console     (folder: frontend; npm install once)
cd frontend
npm install
npm run dev

:: 4. Driver app  (folder: driver; npm install once)
cd driver
npm install
npm run dev
```
Without a worker, set `LOGIMIND_WORKER=inline` for the API instead and skip window 2 (plans would otherwise stay
`queued`). `backend\package.json` (`npm run dev` in backend, decision 0026) still works but is optional; the backend
itself needs only Python.

Backend setup and manual commands:
```
python -m venv %TEMP%\lmv
%TEMP%\lmv\Scripts\activate
pip install -r backend\requirements.txt
cd backend
python -m pytest -q
uvicorn app.main:app --port 8000
python -m app.jobs.worker        # second terminal, also from backend\: runs the solver jobs
```
API docs: http://localhost:8000/docs

Plans, replans and research runs are jobs in a database queue (decision 0021). The API never runs a solver itself: without a worker, plans stay `queued`. For a one-process development setup, `set LOGIMIND_WORKER=inline` before starting uvicorn (the API then runs the same worker loop in a thread). Benchmark (research) jobs always run alone; `GET /api/health` shows the queue (`jobs`).

The research endpoints used by the ops console (`/api/instances`, `/api/runs`, `/api/experiments`, `/api/benchmarks`) have no tenants and are OFF by default. For local development only, start the backend with `set LOGIMIND_DEV_RESEARCH_ENDPOINTS=1` first (decision 0011). Tenant endpoints (`/api/plans`, `/api/orders/import`, `/api/webhooks`, `/api/audit`, `/api/contacts`, `/api/notifications`) need an `X-API-Key` from `python manage.py create-tenant "<name>"`.

Public benchmarks (needs internet once; files stay out of git):
```
python experiments\benchmarks\fetch_benchmarks.py
```

OR-Tools audit (P2; the full grid takes about 1 h 50 min, one run at a time; `--resume` continues an interrupted audit):
```
python experiments\ortools_audit.py --estimate-only
python experiments\ortools_audit.py --out %TEMP%\ortools_audit
```
Committed results: `experiments/results/ortools_audit_2026-11-02/report.md`.

Engine comparison and ablation (P3; about 26 min with `--seeds 2`; `--estimate-only` prints the time first):
```
python experiments\compare_engines.py --seeds 2 --out %TEMP%\compare
```
Committed results: `experiments/results/compare_2026-11-02/report.md`.

Lint: `python -m ruff check .` (from the repository root).

Frontend (Node 18+): `cd frontend`, `npm install`, `npm run dev` (http://localhost:5173), `npm test`.

Driver app (P9 PWA, decisions 0015-0016): copy `driver/` outside OneDrive, then `npm ci`, `npm run dev` (http://localhost:5174, proxies `/api` to :8000), `npm test`, `npm run build && npm run preview` to try the service worker. A dispatcher makes a link per route on the plan page (or `POST /api/plans/{id}/driver-links`); set `LOGIMIND_DRIVER_LINK_SECRET` (32+ characters) so links survive a restart. Customer ETA messages use a stub sender that only logs (decision 0017).

## Optional hosted copilot model (Groq or Gemini, decision 0032)
The copilot uses a **local** Ollama model by default. If you cannot run Ollama, you can use a **free tier** of a
hosted model service instead. Planning, the solvers and all tests work without it.

1. **Create a key** (both have a free tier; the pages may change):
   - Groq: sign in at https://console.groq.com, open **API Keys**, press **Create API Key**, copy it once.
   - Gemini: sign in at https://aistudio.google.com, open **Get API key**, press **Create API key**, copy it.
2. **Put it in `backend\.env` only** (open it with `notepad backend\.env`), for example for Groq:
   ```
   LOGIMIND_LLM_PROVIDER=groq
   GROQ_API_KEY=<paste the key here>
   GROQ_MODEL=<a model id from the provider's model list>
   ```
   For Gemini use `LOGIMIND_LLM_PROVIDER=gemini`, `GEMINI_API_KEY` and `GEMINI_MODEL`. Choose a model that supports
   structured (JSON-schema) output; at the time of writing, for example, `openai/gpt-oss-20b` on Groq or
   `gemini-2.5-flash` on Gemini. Check the provider's current model list.
3. **Restart** (close the LogiMind windows, run `start-dev.bat`). The copilot panel shows the provider and model,
   for example `groq · openai/gpt-oss-20b`, or a plain message such as "Groq key missing or rejected".

> **Warning: never commit, paste or share a key.** `backend\.env` is git-ignored; keep the key there and nowhere
> else (not in chat, screenshots, the README or another file). If a key leaks, delete it in the provider's console
> at once and create a new one. Free tiers have small per-minute limits ("rate limit reached" in the panel), and
> what you send (your messages and your plans' names and ids, never routes) goes to the provider, which may use it
> to improve its models: use synthetic data only. Hosted answers have **not** been measured (see the evaluation
> report).

## Road distances (P4, decision 0019)
`POST /api/plans` takes `distance_source`: `straight_line` (default), `osrm` (road distances and travel times from a **self-hosted** OSRM at `LOGIMIND_OSRM_URL`), or `estimate` (straight line x 1.3 at 25 km/h, labelled as not road data). If OSRM is not set, not running, or cannot route a pair, the plan uses the estimate and says so (`distance_source.fallback: true` with the reason, and a warning on the plan page). Matrices are cached in `matrix_cache.sqlite` in the data dir. Tests replay recorded OSRM answers and run offline. Re-record a fixture from your own OSRM with `python experiments\osrm\record_fixture.py --base-url http://localhost:5000 --out <file>`.

## Docker Compose (UNTESTED)
**These files were written without Docker (it is not installed on the development laptop) and have never been run** (decision 0020). Check them on a machine with Docker Desktop (WSL2) first.

One-command start (from the repository root):
```
copy .env.example .env
rem edit .env: set POSTGRES_PASSWORD and LOGIMIND_DRIVER_LINK_SECRET (32+ characters)
docker compose up --build
docker compose exec api python manage.py create-tenant "My fleet"
```
Then: ops console http://localhost:8080, driver app http://localhost:8081, API docs http://localhost:8000/docs. Services: `postgres` (data in the `pgdata` volume), `api` (FastAPI; matrix cache and photos in the `appdata` volume), `worker` (runs the queued solver jobs; `--scale worker=2` for more planning capacity; decision 0021), `console` and `driver` (nginx serving the builds and proxying `/api`). Copilot: Ollama runs on the host, not in Compose.

Optional OSRM (profile `osrm`):
1. Put an OpenStreetMap extract at `osrm-data\region.osm.pbf`. No small official Bengaluru extract was found: Geofabrik's smallest file that contains Bengaluru, `https://download.geofabrik.de/asia/india/southern-zone-latest.osm.pbf`, was 559 MB on 5 Nov 2026 (not downloaded; see decision 0020). Record the URL, the date and `certutil -hashfile osrm-data\region.osm.pbf SHA256` when you download one.
2. `docker compose --profile osrm run --rm osrm-prepare` (extract, partition, customize; needs several GB of RAM for a large file).
3. Set `LOGIMIND_OSRM_URL=http://osrm:5000` in `.env`, then `docker compose --profile osrm up --build`.

## Layout
- `backend/app/models`: shared problem model (CVRP and CVRPTW)
- `backend/app/solvers`: OR-Tools, the genetic algorithm, local search, the hybrid
- `backend/app/evaluation`: independent validator and metrics
- `backend/app/benchmarks`: Solomon / CVRPLIB parsers, best-known solutions, gap
- `experiments/`: benchmark runner, OR-Tools audit, engine comparison, benchmark download; `experiments/results/`: committed results
- `frontend/`: React ops console
- `driver/`: driver PWA (stop list, delivered/failed, photos, offline queue)
- `backend/app/driver`, `backend/app/messaging`: driver links and reports; ETA notifications (stub sender)
- `docs/context/`: read-only inputs; `docs/decisions/`: decision records
