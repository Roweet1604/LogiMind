# 0028: `start-dev.bat` starts the whole app locally (Windows)

Date: 10 Nov 2026. Status: accepted (asked for by the team).

## Decision
- `start-dev.bat` in the repository root opens four windows: API (`python -m uvicorn app.main:app --reload`, from
  `backend\`), worker (`python -m app.jobs.worker`), console (`npm run dev` in `frontend\`) and driver app
  (`npm run dev` in `driver\`). npm runs only in `frontend\` and `driver\`; the backend needs only Python.
- It reads `backend\.env` (git-ignored; variables already set win), uses Python from `LOGIMIND_PYTHON` or
  `%TEMP%\lmv`, and checks that FastAPI and uvicorn import. The API runs with `LOGIMIND_WORKER=external`, because a
  worker window is started. `LOGIMIND_DRIVER_APP_URL` and the console/driver proxy target follow the chosen ports.
- It refuses to start when a port is already listening. On Windows a second uvicorn on the same port does not fail, and
  requests can reach the old server (seen in this project, decision 0026).
- `start-dev.bat tenant "<name>"` runs `manage.py create-tenant` with the same `.env`, so the tenant lands in the same
  database as the API. `--dry-run` prints the four commands. Ports: `API_PORT`, `CONSOLE_PORT`, `DRIVER_PORT`.
- `.gitattributes` keeps `*.bat` files with CRLF line endings.

## Checked (10 Nov 2026, this laptop, throwaway database, ports 8031/5183/5184)
- Dry run; `tenant` (key printed once); exit codes 2 (no name), 1 (port busy), 1 (no Python).
- Real start: API health 200, console 200, console `/api` proxy 200, driver 200 (after its first `npm install`), and a
  synthetic plan was solved by the separate worker (worker id recorded on the job, 1 attempt).
- Found and fixed: the first version launched the console/driver with `if not exist node_modules (npm install) & npm run
  dev` inside `cmd /k`, and npm never ran; the script now decides in advance and launches one plain command.
- Not checked: closing the windows by hand with the mouse (the test windows were closed by process id).
