# LogiMind progress

Last updated: 2 Nov 2026, end of Phase 0. Current phase: **P0 done; waiting for team answers before P1.**

## Done and verified
- `docs/context/` assembled: PIVOT.md, Review 2 deck, Product Guide PDF, measured evidence zip, prompt pack, and the route-optimization v3 baseline as `prior-code/` (without node_modules/.venv/.git). Committed.
- Read the baseline README, models, solvers, validator, runner, store, API, tests, the measured evidence and the Review 2 deck.
- Baseline facts checked against the code: CVRP only (no time windows), straight-line distances only, OR-Tools PATH_CHEAPEST_ARC + GLS with build time subtracted from the budget, own GA (giant tour + split, OX, tournament, swap/inversion/relocate, elitism, NN seeding, fleet penalty), independent validator, JSON-file store with one worker thread. 54 backend test functions and 13 frontend tests exist.
- Measured evidence zip matches the numbers quoted in the prompt pack (gap by size; same-instance budget ladder for Results A and B; NN-seeding ablation).
- Baseline backend tests run on this laptop: **54 passed** (Python 3.14.7, OR-Tools 9.15.6755, NumPy 2.5.4, pandas 3.1.0, FastAPI 0.162.0, Pydantic 2.14.2; temporary venv outside the repo). Only deprecation warnings.
- Product Guide PDF (23 pages) read. It refers to three demo CSV files (e.g. `demo_n200_veh26_cap58.csv`) that are not in `docs/context/`.
- Created CLAUDE.md, PLAN.md, PROGRESS.md, docs/decisions/0001 (layout) and 0002 (answers and defaults).

## Not done / not verified
- Frontend tests not run (needs `npm install`).
- The three demo CSV files from the Product Guide are missing from `docs/context/`.
- Cut line approach approved (all must-haves kept). Still unanswered: weeks remaining, review dates, workstream owners, pilot data, mentor deliverables (docs/decisions/0002).
- Nothing from P1 to P10 has started.

## Environment (Rohit's laptop, 2 Nov 2026)
git 2.48.1, Python 3.14.7, Node v24.21.0, Claude Code 2.1.312. Docker: not installed. Ollama: not installed. ANTHROPIC_API_KEY: not set (correct).

## Next steps
1. Team fills in the five open answers in docs/decisions/0002.
2. Install Docker Desktop (with WSL2) and Ollama on every laptop that will run the demo.
3. Start P1: migrate the baseline, then add time windows.
