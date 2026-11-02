# LogiMind

An API-first hybrid optimization platform with an AI dispatch copilot for small-fleet logistics (Capstone ASAC-CP-056).

**Status:** P1 of 10 done: route solvers (OR-Tools and our own genetic algorithm) with time windows, plus public benchmark import. See `PROGRESS.md` for what works and what does not yet. `PLAN.md` has the roadmap.

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

Frontend (Node 18+): `cd frontend`, `npm install`, `npm run dev` (http://localhost:5173), `npm test`.

## Layout
- `backend/app/models`: shared problem model (CVRP and CVRPTW)
- `backend/app/solvers`: OR-Tools and the genetic algorithm
- `backend/app/evaluation`: independent validator and metrics
- `backend/app/benchmarks`: Solomon / CVRPLIB parsers, best-known solutions, gap
- `experiments/`: benchmark runner and benchmark download
- `frontend/`: React ops console (baseline)
- `docs/context/`: read-only inputs; `docs/decisions/`: decision records
