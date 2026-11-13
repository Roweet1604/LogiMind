# Deploy checklist: public demo (Vercel console + Hugging Face Space API)

Last updated: 13 Nov 2026 (decision 0045). No tokens or keys belong in this file.

## Where things run
| Part | Where | Address |
| --- | --- | --- |
| Ops console + driver app | Vercel project `logi-mind` (root directory `frontend`) | https://logi-mind-ten.vercel.app (driver app at `/driver/`) |
| API (FastAPI, solvers, SQLite in /tmp) | Hugging Face Space `Rohti/logimind`, Gradio SDK, ZeroGPU hardware | https://rohti-logimind.hf.space |

## Settings
- Vercel, Production: `VITE_API_URL=https://rohti-logimind.hf.space` (set 13 Nov 2026 with `npx vercel env add`).
  A change needs a new production build (push to `main`, or `npx vercel --prod`).
- Space: nothing is required. Optional Space variables/secrets (names only): `FRONTEND_URL` (default already
  https://logi-mind-ten.vercel.app), `LOGIMIND_DRIVER_LINK_SECRET` (secret, 32+ characters),
  `LOGIMIND_LLM_PROVIDER=scripted` (labelled copilot stand-in, decision 0042).

## Update the API
```
%TEMP%\lmv\Scripts\python backend\scripts\build_hf_space.py
C:\Users\rohit\AppData\Roaming\Python\Python314\Scripts\hf.exe upload Rohti/logimind hf-space . --repo-type=space --commit-message "Deploy LogiMind backend"
```
Then watch https://huggingface.co/spaces/Rohti/logimind (Logs). Check: https://rohti-logimind.hf.space/health gives
`{"status":"ok"}`. If `hf.exe upload` says permission denied: create a Write token at
https://huggingface.co/settings/tokens and run `hf.exe auth login` yourself (paste it only at that prompt).

## Problems met on 13 Nov 2026 (and fixed)
1. Build 1: `ResolutionImpossible`, `spaces==0.51.3` (added by the Space build) vs our `spaces==0.52.0`.
   Fix: `gradio` and `spaces` listed without versions in the Space requirements.
2. Build 2: `gradio[mcp]==6.32.0` needs `pydantic>=2.11.10,<=2.12.5`; we pin 2.14.3. Fix: the Space uses
   `pydantic==2.12.5` (override in `build_hf_space.py`), checked offline with `uv pip compile` for Python 3.12 on
   Linux together with the Space's own pins.
3. Build 3 started, then `RUNTIME_ERROR: No @spaces.GPU function detected during startup`: `spaces` sends ZeroGPU's
   start-up report only from gradio's `launch()`, which we do not call. Fix: `app.py` sends it itself
   (`report_zero_gpu_startup`, same steps as spaces 0.51.3). If a later `spaces` version breaks this, the Space log
   shows it; the fallback is Render (`render.yaml`, decision 0039).
4. Build 4: RUNNING (13 Nov 2026, 22:25).

## Status (13 Nov 2026, end of session)
- LIVE: API https://rohti-logimind.hf.space (`/health` 200) and console https://logi-mind-ten.vercel.app
  (production build from commit 043ca47, built by Vercel's GitHub integration after the push; `npx vercel --prod`
  was not needed, so no local files were uploaded).
- Checked against the live Space: CORS from the console, demo sign-in, plans list, a new plan solved and validated,
  a vehicle-breakdown replan solved and validated. Checked in Chrome: the console shows "server connected",
  "Demo Fleet (synthetic)", Demo mode, and lists the plans on Overview and Plans.
- Hugging Face upload worked with the saved login (no permission problem).
- Note: a browser that once opened the console with a tunnel link (`?api=https://...trycloudflare.com`) keeps using
  that tunnel. Open https://logi-mind-ten.vercel.app/?api=default once in that browser.
- The Space sleeps after 48 hours without visits; the first request then waits while it starts, and the data is
  reset (the demo tenant is seeded again).
