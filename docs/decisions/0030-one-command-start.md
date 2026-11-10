# 0030: `start-dev.bat` with no arguments sets up and starts everything

Date: 10 Nov 2026. Status: accepted (asked for by the team for the demo). Extends decision 0028.

## Decision
- `start-dev.bat` (no arguments) does the one-time set-up when something is missing, then starts the app:
  1. Python environment in `%TEMP%\lmv` (outside OneDrive), made with `py -3` or `python` (3.12 or newer), then
     `pip install -r backend\requirements.txt` when FastAPI/uvicorn/OR-Tools/SQLAlchemy/Alembic do not import.
     A `LOGIMIND_PYTHON` the user set is used as given and never created.
  2. `backend\.env` from `backend\.env.example` if missing, and an empty `LOGIMIND_DRIVER_LINK_SECRET` filled with
     `secrets.token_urlsafe(48)`. Existing values are never changed and the secret is never printed.
  3. `npm install` in `frontend\` and `driver\` where `node_modules` is missing (npm runs nowhere else).
  4. Port check: if 8000/5173/5174 (or `API_PORT`/`CONSOLE_PORT`/`DRIVER_PORT`) answer, it names the port and, when
     Windows shows it, the program and process id, stops NOTHING, and exits 1.
  5. Opens the API (`--host 127.0.0.1`, demo mode on, decision 0029), worker, console and driver windows, waits until
     `/api/health` and the console answer (180 s / 120 s), then opens `http://localhost:<console>/plans`.
- The set-up, port and wait steps are in `backend/scripts/devtools.py` (standard library only, so it runs right after
  the venv exists) and tested in `backend/tests/test_devtools.py`. `--dry-run` changes and starts nothing;
  `--no-browser` skips the browser; `tenant "<name>"` is unchanged.
- The Vite proxies point at `http://127.0.0.1:<api>`: the API listens on IPv4 loopback only.

## Found while building it
- A Vite server answering on `[::1]:5173` had no LISTENING row in `netstat` on this laptop, only its connections; the
  port check uses a real connection attempt (127.0.0.1 and ::1) and names the program from any of its rows.
- **The main `%TEMP%\lmv` was damaged during this session** (10 Nov 2026, folders last written 14:26): most `.py`
  files in `site-packages` were gone and only `__pycache__` folders were left, so `python -m pytest` and `python -m
  ruff` failed with "is a package and cannot be directly executed". This session did not touch that folder; the
  cause was NOT found (Windows' automatic clean-up of old temporary files is a guess, not proven). It was rebuilt
  with `py -3 -m venv --clear` and `pip install -r backend\requirements.txt`. Consequences in the script:
  - the readiness check imports names (`from fastapi import FastAPI`, ...), because a folder without its `.py`
    files still imports as an empty namespace package (checked: the old `import fastapi` check passed on such a
    folder, the new one fails);
  - if pip still lists the packages, it reinstalls with `--force-reinstall` (plain `pip install` would report
    "already satisfied").
  - Team: consider a venv location outside `%TEMP%` (for example `%LOCALAPPDATA%\LogiMind\venv`) for the demo
    laptop; `LOGIMIND_PYTHON` already allows it.

## Checked (10 Nov 2026)
- A fresh clone in the scratch folder with an empty TEMP folder and ports 8040/5185/5186: the script made the venv
  with `py -3` (Python 3.14), installed the packages (slow download on this connection, about 25 minutes), created
  `backend\.env` with a generated secret, ran `npm install` in both apps, started the four windows, waited for the
  API and the console, and printed the addresses. `/api/health` reported `demo_mode: true`.
- On the real repository, the port check found the developer's own Vite server on 5173 and stopped nothing.
- Not checked: a computer with no Python or no Node.js at all (the error messages for those cases were not seen).
