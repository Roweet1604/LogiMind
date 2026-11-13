# 0044: The public demo API on a Hugging Face Space (Docker SDK, free CPU)

Date: 13 Nov 2026. Status: accepted (asked for by the team: a free host for the backend that does not need the laptop).

## Decision
- `hf-space/` holds the Space-only files: `Dockerfile`, `README.md` (front matter `sdk: docker`, `app_port: 7860`) and
  `.dockerignore`. `backend/scripts/build_hf_space.py` copies what the API needs next to them: `app/`, `migrations/`,
  `alembic.ini` and `requirements.txt` without pytest and ruff. In this repository those copies are git-ignored, so
  the backend has one source; `--out <folder>` fills a clone of the Space instead (also copies the three files).
  The script never copies tests, `.env`, caches, experiments or results, and stops if a `.env` would end up there.
- Image: `python:3.14.7-slim` (the version the suite runs on), non-root user UID 1000 (what Spaces use), app in
  `/home/user/app`, SQLite in `/home/user/data`, `uvicorn app.main:app --host 0.0.0.0 --port 7860`, one worker.
- Defaults in the image: `LOGIMIND_DEMO_MODE=1`, `LOGIMIND_PUBLIC_DEMO=1`, `LOGIMIND_WORKER=inline`,
  `FRONTEND_URL=https://logi-mind-ten.vercel.app` (CORS; a Space variable of the same name overrides it). Start-up
  seeds the SYNTHETIC demo tenant and its three plans (existing code, decision 0039), so a reset disk is fine.
- Optional Space secret `LOGIMIND_DRIVER_LINK_SECRET` (>= 32 characters). Without it driver links stop working on a
  restart, which also wipes the plans they point to, so it is not required.
- The console on Vercel uses the Space through its build-time `VITE_API_URL=https://<owner>-<space>.hf.space`.
  `render.yaml` (decision 0039) is kept; the laptop tunnel (decisions 0040, 0043) still works through `?api=`.

## Why
Free (invariant 12), no card, no sleep after 15 minutes like Render's free plan (Spaces sleep after about 48 hours
without visits), and enough memory for OR-Tools.

## Limits
- Not built with Docker here (no Docker on the development laptop). Verified instead: the generated folder alone
  (fresh copy, no backend/.env, clean environment with the image's variables) ran the image's command on port 7860.
- Anyone with the link uses the synthetic demo tenant (same limits as decision 0039). The disk resets on restart.
- No Ollama on the Space: the copilot is off unless a viewer pastes a free hosted key in the console (decision 0033);
  `LOGIMIND_LLM_PROVIDER=scripted` (decision 0042) can be set as a Space variable for the labelled stand-in.
