# 0045: The public demo API on the team's Gradio-SDK Space (ZeroGPU), replacing the Docker Space of 0044

Date: 13 Nov 2026. Status: accepted (the team's Space `Rohti/logimind` uses the Gradio SDK with ZeroGPU hardware and
the team asked not to use the Docker SDK). Supersedes the Docker layout of decision 0044; its build script stays.

## Decision
- `hf-space/` holds `README.md` (front matter `sdk: gradio`, `sdk_version: 6.32.0` as the Space already had,
  `python_version: "3.12"`, `app_file: app.py`) and `app.py`. `backend/scripts/build_hf_space.py` copies `app/`,
  `migrations/`, `alembic.ini` and the runtime `requirements.txt` next to them (git-ignored copies; never tests,
  `.env`, experiments or results). The Dockerfile and `.dockerignore` of decision 0044 are removed.
- `app.py` imports `spaces` first and defines one trivial `@spaces.GPU` function, because ZeroGPU only starts a Space
  that has one. Nothing uses a GPU; the solvers run on the CPU. It sets the public-demo defaults (demo mode and public
  demo on, inline worker, SQLite in `/tmp/logimind-data`, `FRONTEND_URL=https://logi-mind-ten.vercel.app` for CORS;
  Space variables of the same names win) and runs the FastAPI app with uvicorn on `0.0.0.0:7860` in the foreground.
  No Gradio UI. Start-up seeds the SYNTHETIC demo tenant (existing code, decision 0039).
- `spaces` sends ZeroGPU's start-up report only from its hook on gradio's `Blocks.launch()`, which this app never
  calls; the third build stopped with "No @spaces.GPU function detected during startup". `app.py` runs the same
  steps as spaces 0.51.3's hook (`spaces.zero.torch.pack()`, then `spaces.zero.client.startup_report()`) before
  uvicorn starts, only when ZeroGPU is active. These are `spaces` internals: a `spaces` upgrade by Hugging Face
  can break this, and the Space log then shows the error.
- Space only: `pydantic==2.12.5` instead of our 2.14.3, because `gradio[mcp]==6.32.0` (installed by the Space
  build) needs `pydantic>=2.11.10,<=2.12.5` (second build). Checked offline with `uv pip compile` for Python 3.12 on
  Linux together with the Space's own pins.
- `requirements.txt` lists `gradio` and `spaces` WITHOUT versions: the Space build installs `gradio[oauth,mcp]==<
  sdk_version>` and its own `spaces==...` in the same pip call, and our `spaces==0.52.0` pin made the first build fail
  (`ResolutionImpossible`: spaces 0.51.3 vs 0.52.0).
- Deploy: `hf.exe upload Rohti/logimind hf-space . --repo-type=space` (no git push to the Space).
- Console (Vercel): `VITE_API_URL=https://rohti-logimind.hf.space` (Production) is the default API. `?api=` still
  accepts a laptop tunnel; `?api=<the built API>` now means the default. Driver links always carry the API in use as
  `?api=` before `#t=`; the driver app accepts its own built API there as its default.

## Why
Zero cost on the team's existing Space, no laptop needed. ZeroGPU Spaces run `python app.py` and route port 7860, so
any web server there works; the GPU function is only a start-up requirement.

## Limits
- This relies on ZeroGPU accepting a Space whose server is not a Gradio app. If Hugging Face changes that, the Space
  stops starting; the Render blueprint (`render.yaml`, decision 0039) is the fallback.
- The build also installs torch (the platform adds it), which makes builds slow; LogiMind does not use it.
- Anyone with the link uses the synthetic demo tenant; the disk resets on restart (same limits as decision 0039).
