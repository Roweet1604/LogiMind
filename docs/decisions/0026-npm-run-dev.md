# 0026: `npm run dev` starts the backend and the frontend

Date: 10 Nov 2026. Status: accepted (asked for by the team: "backend will start with npm run dev and the frontend will start with npm run dev").

## Decision
- `frontend/`: unchanged; `npm run dev` already runs Vite on http://localhost:5173 and proxies `/api` to :8000.
- `backend/package.json` (new, no Node dependencies) with `dev`, `worker` and `test` scripts. They call `backend/scripts/dev.mjs`, which:
  - finds Python in `LOGIMIND_PYTHON`, then `%TEMP%\lmv` (the venv from CLAUDE.md), then `backend/.venv` or `.venv`, then `python` / `python3` on the PATH;
  - checks that FastAPI and uvicorn import, and otherwise prints the `pip install -r backend/requirements.txt` command;
  - `dev`: `python -m uvicorn app.main:app --reload --port 8000` (`PORT` overrides the port);
  - sets `LOGIMIND_WORKER=inline` unless it is already set. Otherwise, with the API's default (`external`), plans stay `queued` until a second process runs the worker, and "one command" would not give a working app. `inline` is the documented one-process development mode (decision 0021); production and Docker Compose still use `external` plus the worker service.
- Nothing else changes: the database, research endpoints (still OFF), OSRM and copilot settings remain environment variables with the same defaults. The Python stack is unchanged; Node is only the launcher.

## Checked
- 10 Nov 2026, Windows: `cd backend && npm run dev` answered `GET /api/health` with 200 (it used `%TEMP%\lmv`, worker inline, auto-reload on). `cd frontend && npm run dev` served the console on 5173, its `/api/health` proxy returned 200, and `design/tokens.js` was served.
- Not checked: macOS/Linux, and Ctrl+C in an interactive terminal (the tool used here stops processes differently).
