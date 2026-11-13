---
title: LogiMind API
emoji: 🚚
colorFrom: gray
colorTo: green
sdk: docker
app_port: 7860
pinned: false
short_description: Route planning API (public demo, synthetic data only)
---

# LogiMind API (public demo)

Backend of LogiMind, a route-planning platform for small fleets (Capstone Project, batch ASAC-CP-056). The ops console
is at https://logi-mind-ten.vercel.app.

- **Synthetic data only.** This Space runs the public demo: anyone with the console link uses the synthetic demo
  tenant. Do not enter real customer data.
- **The disk resets** on every restart or rebuild. The demo tenant and its three plans are created again at start-up.
- Health check: `GET /health`. API documentation: `/docs`.
- Plans come from the OR-Tools, GA or hybrid solvers and pass the independent validator; the copilot never makes
  routes. No local model runs here, so the copilot is off unless a viewer pastes a free hosted key in the console.

This folder is generated from the main repository (`python backend/scripts/build_hf_space.py`, decision 0044); change
the backend there, not here.
