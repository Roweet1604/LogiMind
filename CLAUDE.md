# LogiMind: rules for every session

LogiMind: An API-First Hybrid Optimization Platform with an AI Dispatch Copilot for Small-Fleet Logistics.
Capstone Project - I (7CS1999), batch ASAC-CP-056. Team: Rohit Raj, Pragya, Ishika. Mentor: Dr. M. Selvam.

Start every session by reading this file, `PLAN.md` and `PROGRESS.md`, then run the tests and report the real result.

## Non-negotiable invariants
1. The LLM never generates, edits or invents routes. Every plan comes from a solver and passes the independent validator before it is shown or stored as "feasible". The LLM only parses instructions into validated schemas, chooses and calls tools, and explains results using the tools' own numbers.
2. No infeasible plan is ever presented as a success. Timeouts, "no solution" and provider failures are shown as what they are.
3. Nothing fabricated: no invented results, benchmark values, best-known solutions or pilot data. Synthetic or simulated data is always labelled. Best-known values come only from official sources (URL and date recorded).
4. Fair engine comparisons: same instance, same distance matrix, same objective, same TOTAL wall-clock budget (set-up included), one benchmark job at a time.
5. Reproducibility: every run stores seed, configuration, software versions and an instance identity.
6. The hybrid is labelled as a hybrid. The standalone GA stays a real search of its own. Report ablations.
7. Tenant isolation is enforced at the data layer and covered by tests that try to break it.
8. Secrets only through environment variables. Never commit a secret; never ask for one in chat or in a committed file.
9. Every external service (LLM, OSRM, notifications) sits behind an adapter with a deterministic fake, so tests and CI run offline.
10. When a fallback is used (e.g. straight-line distance because OSRM is down), the plan says so.
11. Never claim something is done if it is not. Keep `PROGRESS.md` truthful.
12. Zero cost: no paid or key-gated service anywhere. New dependencies must be free, open source and runnable offline. Do not set `ANTHROPIC_API_KEY` globally (Claude Code would bill the API instead of the Pro plan).

## Working rules
- Preserve working code; evolve the baseline instead of rewriting it.
- Make ordinary decisions yourself and record them in `docs/decisions/` (one short file per decision, numbered `NNNN-title.md`). Ask the team only about blockers and the cut line.
- Read real errors, fix the cause, rerun the affected tests. Never skip or weaken tests to make something pass.
- Never pipe or wrap a test or lint command in a way that hides its exit code (no `| tail`, `| grep`, `|| true` on the command itself). Write output to a file if it is long, then check the exit code (`echo $?`). Run ruff and the tests directly, and check that they pass, before each commit.
- No must-have functionality left as TODOs or placeholders.
- Each phase ends with passing tests, a commit and a `PROGRESS.md` update. If context or usage runs low, stop at a clean point and write the handoff in `PROGRESS.md` first.

## Repository layout
- `docs/context/`: read-only inputs (pivot, Review 2 deck, Product Guide, measured evidence, prompt pack). Do not edit.
- `docs/context/prior-code/`: the route-optimization v3 baseline (reference copy; do not edit). Migrated to the root in P1.
- `docs/decisions/`: decision records.
- `backend/`: FastAPI app. `app/models` (CVRP/CVRPTW model), `app/solvers` (OR-Tools, GA), `app/evaluation` (validator, metrics), `app/benchmarks` (parsers, BKS, gap), `app/services`, `app/api`.
- `frontend/`: React ops console (baseline). `experiments/`: benchmark runner; `experiments/benchmarks/` (fetch script, committed `bks.csv`, git-ignored `data/`).
- Planned: `driver/` (PWA), `docker-compose.yml`, `.env.example`.

## Commands (Windows; keep venvs and node_modules OUTSIDE OneDrive, e.g. %TEMP%)
```
python -m venv %TEMP%\lmv
%TEMP%\lmv\Scripts\python -m pip install -r backend\requirements.txt
cd backend && %TEMP%\lmv\Scripts\python -m pytest -q          # backend tests
python experiments\benchmarks\fetch_benchmarks.py              # download benchmark files (once)
%TEMP%\lmv\Scripts\python experiments\run_benchmarks.py --sizes 10 --ga-seeds 1 --time-budget 1 --out %TEMP%\bench
```
Frontend tests: copy `frontend/` to %TEMP%, then `npm ci` and `npm test` there.
Tests must pass offline; tests needing downloaded benchmark files skip when they are missing.

## Stack (change only with a written reason in docs/decisions/)
Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2 + Alembic (SQLite dev, Postgres in Docker Compose), OR-Tools, own GA (NumPy), scikit-learn, LangGraph/LangChain with `langchain-ollama` behind a provider-agnostic interface, httpx, JSON logging, pytest, ruff. Frontend: React + Vite (JS/JSX), Tailwind, Leaflet + OSM tiles, vite-plugin-pwa. Self-hosted OSRM (no hosted routing services). Docker Compose.

UI look: warm neutral background, charcoal text, one teal accent; solid blue = OR-Tools, dashed orange = GA. No gradients, glass, glow or decorative widgets. Driver PWA is mobile-first with large touch targets.
