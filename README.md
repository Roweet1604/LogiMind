# LogiMind

An API-first hybrid optimization platform with an AI dispatch copilot for small-fleet logistics (Capstone ASAC-CP-056).

**Status:** P3 of 10 done: route solvers (OR-Tools, our own genetic algorithm with optional local search, and a hybrid where OR-Tools seeds the GA) with time windows, public benchmark import, an OR-Tools settings audit, an equal-clock engine comparison, and a wall-clock guard that stops runs that hang. See `PROGRESS.md` for what works and what does not yet. `PLAN.md` has the roadmap.

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

## Layout
- `backend/app/models`: shared problem model (CVRP and CVRPTW)
- `backend/app/solvers`: OR-Tools, the genetic algorithm, local search, the hybrid
- `backend/app/evaluation`: independent validator and metrics
- `backend/app/benchmarks`: Solomon / CVRPLIB parsers, best-known solutions, gap
- `experiments/`: benchmark runner, OR-Tools audit, engine comparison, benchmark download; `experiments/results/`: committed results
- `frontend/`: React ops console (baseline)
- `docs/context/`: read-only inputs; `docs/decisions/`: decision records
