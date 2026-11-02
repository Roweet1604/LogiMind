# Route Optimization: OR-Tools vs custom Genetic Algorithm (CVRP)

Status: **working end to end**: Python backend + FastAPI + React frontend (7 areas: overview, setup, run, results map, compare, benchmark lab, methodology).
Not built: CVRPTW, public benchmark-instance import, deployment.

## Setup
```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m pytest -q                                  # 54 tests
```

## Run the API (from backend/, venv active)
```bash
uvicorn app.main:app --reload --port 8000
```
Interactive docs: http://localhost:8000/docs. Env vars: `ROUTEOPT_DATA_DIR` (default `experiments/results/api_data`),
`ROUTEOPT_CORS_ORIGINS` (default `http://localhost:5173`), `ROUTEOPT_MAX_TIME_LIMIT_S` (default 300).

| Endpoint | Purpose |
| --- | --- |
| `POST /api/instances`, `POST /api/instances/generate` | register / generate an instance (422 with reasons if invalid) |
| `GET /api/instances`, `GET /api/instances/{id}` | list / fetch |
| `POST /api/runs` -> `GET /api/runs/{id}`, `/metrics` | start one solver run (202), poll state queued/running/completed/failed |
| `POST /api/experiments` -> `GET /api/experiments/{id}` | fair comparison: OR-Tools + GA seeds, same time budget; summary included |
| `GET /api/experiments` (list), `GET /api/experiments/{id}/export?kind=raw\|summary`, `GET /api/runs/export` | CSV |

Jobs run on a single worker thread, one at a time, so wall-clock comparisons are not distorted by concurrent runs.
Completed runs, instances and experiments are saved as JSON and reloaded on restart; queued runs are lost on restart.

## Run the frontend (needs Node 18+; second terminal)
```bash
cd frontend
npm install
npm run dev          # http://localhost:5173 (proxies /api to http://localhost:8000)
npm test             # 13 tests (vitest)
npm run build
```
Start the backend first. Typical flow: Problem setup -> Run optimization (both algorithms, same time budget) -> Route results -> Compare -> Benchmark lab.
Map tiles come from OpenStreetMap and need internet; route lines are straight segments either way.
Optional: set `VITE_BACKEND_URL` if the API is not on `http://localhost:8000` (dev proxy), or `VITE_API_BASE` for a deployed build.

## Run a benchmark (from repo root)
```bash
python experiments/run_benchmarks.py --sizes 10 25 50 --ga-seeds 5 --time-budget 10 --out experiments/results/run1
```
Writes `raw.csv`, `summary.csv`, `manifest.json` (environment, args, versions) and `instances/*.json`.

## Layout
- `backend/app/models/problem.py`: shared `Instance` (depot, customers, fleet, distance matrix, cost model, validation)
- `backend/app/solvers/ortools_solver.py`: OR-Tools CVRP (PATH_CHEAPEST_ARC + GUIDED_LOCAL_SEARCH, wall-clock limit)
- `backend/app/solvers/genetic_algorithm.py`: custom GA (giant-tour permutation + optimal split decoder, OX, tournament, elitism)
- `backend/app/evaluation/`: independent validator and shared metrics
- `backend/app/services/`: generator, runner (solver + validator + metrics), CSV export/summary
- `experiments/run_benchmarks.py`: repeatable benchmark runner (CLI)
- `frontend/`: React + Vite + Tailwind + Leaflet + Recharts UI (JavaScript only)

## Methodology (short)
- Both solvers get the same `Instance` and the same distance matrix. Objective for both: `fixed_vehicle_cost * vehicles_used + cost_per_distance * distance` (synthetic cost units, not currency).
- Distances are straight-line (Euclidean or haversine km), not road distances.
- Same wall-clock budget per run for both algorithms. GA runs repeat over seeds 0..k-1; OR-Tools repeats are configurable.
- Reported distance/cost is always recomputed by the shared evaluator; solver objectives are never compared.
- Summary statistics use feasible runs only; infeasible/failed runs are counted, never turned into zeros.
- GA constraint handling: permutation encoding guarantees coverage; split guarantees capacity; fleet limit is penalised and then independently validated.

## Time budget
`time_limit_s` is the total wall-clock budget for each run. OR-Tools' own limit covers only its search, so its model-build time is measured and subtracted (recorded in the run diagnostics as `build_seconds` and `search_limit_s`). The GA checks its clock between generations, so on very large instances with very small budgets it can overshoot while building its first population.

## Known limitations
- CVRP only (no time windows). Time limit measured in wall-clock, so results depend on the machine.
- The GA decoder does not enforce the fleet limit inside the split; instances with a very tight fleet may yield a fleet-limit violation (reported by the validator).
- Benchmarks in the UI use one generated instance per size; a few instances cannot support a general claim.
- No public benchmark instances (e.g. CVRPLIB) are imported yet.
