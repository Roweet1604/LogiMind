# LogiMind

An API-first hybrid optimization platform with an AI dispatch copilot for small-fleet logistics (Capstone ASAC-CP-056).

**Status:** P1-P3, P5, P7 and P9 done; P4 road matrix done offline (not yet run against a self-hosted OSRM); P6 partly (Docker Compose files written but UNTESTED, no job queue yet); P8 copilot built but tested only with a fake LLM (no real model run yet). Route solvers (OR-Tools, our own GA, a hybrid), an engine picker, a tenant API with plans, imports, webhooks and replanning, a dispatch copilot, a driver PWA and stub ETA notifications. See `PROGRESS.md` for what works and what does not yet; `PLAN.md` has the roadmap.

## Quick start (Windows)
Keep the virtual environment and `node_modules` **outside OneDrive** (OneDrive sync and long paths break installs).

Backend:
```
python -m venv %TEMP%\lmv
%TEMP%\lmv\Scripts\activate
pip install -r backend\requirements.txt
cd backend
python -m pytest -q
uvicorn app.main:app --port 8000
```
API docs: http://localhost:8000/docs

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
Then: ops console http://localhost:8080, driver app http://localhost:8081, API docs http://localhost:8000/docs. Services: `postgres` (data in the `pgdata` volume), `api` (FastAPI and its solver worker process; matrix cache and photos in the `appdata` volume), `console` and `driver` (nginx serving the builds and proxying `/api`). There is **no separate worker service** yet: jobs run in the API container, one at a time (decision 0020). Copilot: Ollama runs on the host, not in Compose.

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
