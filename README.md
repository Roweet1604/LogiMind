# LogiMind

An API-first hybrid optimization platform with an AI dispatch copilot for small-fleet logistics (Capstone ASAC-CP-056).

**Status:** P1-P3, P5, P7 and P9 done; P6 partly (no Docker Compose or job queue yet); P8 copilot built but tested only with a fake LLM (no real model run yet). Route solvers (OR-Tools, our own GA, a hybrid), an engine picker, a tenant API with plans, imports, webhooks and replanning, a dispatch copilot, a driver PWA and stub ETA notifications. See `PROGRESS.md` for what works and what does not yet; `PLAN.md` has the roadmap.

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
