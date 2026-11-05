# Demo script (about 10 minutes)

Only features that were **verified** are in the main path. Each step says how it was verified. Items marked *(optional, tests only)* passed automated tests but were not walked through by hand; show them only if asked, and say so. Do not demo the copilot answering, road distances from OSRM, Docker Compose or the driver app on a phone: none of these were verified (see [limitations.md](limitations.md)).

## Before the demo (once, about 10 minutes)
1. Windows laptop, Python venv and node_modules outside OneDrive (see README).
2. Make a throwaway data folder and a tenant (Git Bash, from `backend/`):
   ```
   export ROUTEOPT_DATA_DIR="$TEMP/lm_demo"
   export LOGIMIND_DATABASE_URL="sqlite:///$(cygpath -m "$TEMP/lm_demo")/logimind.db"
   export LOGIMIND_DRIVER_LINK_SECRET="$(python -c 'import secrets;print(secrets.token_urlsafe(48))')"
   python manage.py create-tenant "Demo fleet"      # copy the printed key; it is shown once
   ```
3. Three terminals with those variables set:
   - API: `uvicorn app.main:app --port 8000`
   - worker: `python -m app.jobs.worker`
   - console: in the console copy outside OneDrive, `npx vite --port 5173`
4. Have two order files ready: one with an error (for example a demand `abc` and a duplicate id) and one valid lon/lat file (8 synthetic Bengaluru orders). Say that they are synthetic.

## The demo
1. **Health** (10 s). Open `http://localhost:8000/api/health`: versions, research endpoints off, `jobs.worker_mode = external`. *Say:* "The API never runs a solver itself; the worker in the second terminal does." *(Verified: live, 5 Nov 2026.)*
2. **Sign in** (20 s). `http://localhost:5173/login`, paste the key. The tenant name appears in the sidebar. *(Verified in Chrome.)*
3. **Import with errors** (40 s). Plans -> choose the bad file. Every problem is listed with its spreadsheet row; nothing is imported. *(Verified in Chrome.)*
4. **Import the valid file** (20 s). "8 orders ready". Set the depot to 77.5946 / 12.9716. The "Distances and travel times" choice appears for lon/lat orders. *(Verified in Chrome.)*
5. **Create a plan with road distances requested** (60 s). Choose "Road network (OSRM)", engine Auto, budget 3 s, Create. Point out:
   - the plan was `queued`, then solved by the worker;
   - **"feasible"** comes from the independent validator;
   - "Why this engine": the picker's explanation, including that the instance is outside its training range when that is true;
   - the yellow **"Fallback distances: not road data"** notice: OSRM is not running, so the plan says so instead of pretending. *(Verified in Chrome with a separate worker process, 5 Nov 2026.)*
6. **Urgent order replan** (90 s). On the plan page: Replan -> Urgent order, 2 completed stops on vehicle 0, order 9 at 77.6974 / 12.9591, OR-Tools, Replan. Point out: the first two stops stay in place (frozen), the new stop is served, "warm start: used", time to a feasible plan, the link to the previous plan. *(Verified in Chrome with a separate worker process, 5 Nov 2026.)*
7. **Driver link** (60 s). On the plan page, Drivers -> "Driver link for route 0". Open it in a second browser window: the driver's stop list. Mark one stop delivered and one failed ("Nobody home"); back in the console, the Drivers panel shows the reports. *(Verified in desktop Chrome on 4 Nov 2026; not on a phone.)*
8. **Copilot status** (20 s). Copilot page: "No local model available". *Say:* "The copilot is built and tested with a fake model; the real-model evaluation has not been run." *(Verified in Chrome.)*
9. **Evaluation** (2 min). Open `docs/report/evaluation.md`: the held-out benchmark table and figure, the significance tests, and the negative results (hybrid not a clear win; picker not a proven gain). *Say:* which results are synthetic.

6b. **Breakdown and failed delivery** (optional, 60 s). On the replanned plan: Vehicle breakdown, vehicle 0 after 3 completed stops -> its unfinished stops move to another vehicle, the 3 done stops stay. Failed delivery: say plainly that the planner may schedule the retry as the very next stop (known limit). *(Verified in Chrome with a separate worker process, 5 Nov 2026.)*

## Optional, tests only (say so if shown)
- Webhooks with signed deliveries (`GET /api/webhooks/{id}/deliveries`).
- Killing the worker in the middle of a job: another worker finishes it after 30 s (`tests/test_jobs.py`, real processes).

## If something goes wrong
- Plan stays `queued`: the worker is not running (terminal 2), or it waits for a running benchmark job.
- Driver link says expired: links last at most 24 h; make a new one.
- Copilot page spins for a few seconds: it is checking for Ollama; then it says no model is available.
