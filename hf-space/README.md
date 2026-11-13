---
title: LogiMind API
emoji: 🚚
colorFrom: gray
colorTo: green
sdk: gradio
sdk_version: 6.32.0
python_version: "3.12"
app_file: app.py
pinned: false
short_description: Route planning API (public demo, synthetic data only)
---

# LogiMind API (public demo)

Backend of LogiMind, a route-planning platform for small fleets (Capstone Project, batch ASAC-CP-056). The ops console
is at https://logi-mind-ten.vercel.app. This Space serves the API only (no Gradio page): `GET /health`, docs at `/docs`.

- **Synthetic data only.** Anyone with the console link uses the synthetic demo tenant. Do not enter real data.
- **The disk resets** on every restart. The demo tenant and its three plans are created again at start-up.
- Plans come from the OR-Tools, GA or hybrid solvers on the CPU and pass the independent validator; the copilot never
  makes routes. The copilot uses Groq (`llama-3.3-70b-versatile`) when the Space secret `GROQ_API_KEY` is set;
  without it the copilot says it is not configured. Messages are rate-limited per visitor and for the whole Space
  and capped at 500 characters, because every visitor uses the Space's key (decision 0046).
- `app.py` defines one empty `@spaces.GPU` function only because ZeroGPU hardware requires one; nothing uses a GPU.

Generated from the main repository (`python backend/scripts/build_hf_space.py`, decision 0045); change the backend
there, not here.
