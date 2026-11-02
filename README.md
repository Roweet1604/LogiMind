# LogiMind

An API-first hybrid optimization platform with an AI dispatch copilot for small-fleet logistics (Capstone ASAC-CP-056).

**Status:** P2 of 10 done: route solvers (OR-Tools and our own genetic algorithm) with time windows, public benchmark import, and an OR-Tools settings audit whose results pick OR-Tools' defaults per time budget. See `PROGRESS.md` for what works and what does not yet. `PLAN.md` has the roadmap.

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

Frontend (Node 18+): `cd frontend`, `npm install`, `npm run dev` (http://localhost:5173), `npm test`.

## Layout
- `backend/app/models`: shared problem model (CVRP and CVRPTW)
- `backend/app/solvers`: OR-Tools and the genetic algorithm
- `backend/app/evaluation`: independent validator and metrics
- `backend/app/benchmarks`: Solomon / CVRPLIB parsers, best-known solutions, gap
- `experiments/`: benchmark runner, OR-Tools audit, benchmark download; `experiments/results/`: committed audit results
- `frontend/`: React ops console (baseline)
- `docs/context/`: read-only inputs; `docs/decisions/`: decision records
