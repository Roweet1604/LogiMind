# 0029: Local demo mode (ready demo tenant, console signs in by itself)

Date: 10 Nov 2026. Status: accepted (asked for by the team for the final-year demo).

## Decision
- **Off in the code.** Demo mode runs only if `LOGIMIND_DEMO_MODE` is exactly `1` **and** `LOGIMIND_BIND_HOST` is a
  loopback address (`127.0.0.1`, `::1`, `localhost`). Unset or any other value: off, and nothing is created.
  `start-dev.bat` sets both and starts uvicorn with `--host 127.0.0.1`. Docker Compose, `.env.example` and the API
  Dockerfile never mention it (a test checks this), and the container listens on `0.0.0.0`, which is refused anyway.
- **Start-up** (`backend/app/demo.py`): creates tenant `ten-demo-local` "Demo Fleet (synthetic)" if missing; revokes
  the demo keys of earlier starts; issues a new key that lives **in memory only** (only its hash is in the database,
  as for every key). If the tenant has no plans, it queues three plans on a seeded **synthetic** data set (stops near
  central Bengaluru, not real addresses; names end in "(synthetic demo)", `source = synthetic`):
  12 stops with OR-Tools, 15 stops with two-hour time windows with `engine=auto`, 10 stops with GA + local search,
  2 s each. They go through the normal queue, solver and validator; nothing is marked feasible by the demo code.
- **Hand-out:** `GET /api/demo/session` returns the key only when the client address, the server socket and the
  `Host` header are all local and no proxy header (`X-Forwarded-For`, `Forwarded`, `X-Real-IP`) is present. The
  `Host` check blocks DNS-rebinding pages; the Vite dev proxy keeps the browser's `localhost:5173` Host. Off: 404.
  `/api/health` reports `demo_mode`.
- **Console:** with no working key in the tab it asks for the demo session; if that works it signs in and shows a
  "Demo mode" label in the top bar. A valid normal key in the tab is kept. "Sign out" from the demo keeps that tab
  signed out, so normal API-key sign-in can be shown. Normal sign-in is unchanged.

## Why
The demo needs "open the browser and see plans" without copying a key from a terminal. Keeping the key in memory
and handing it out only to this computer means a laptop on a shared network does not expose the tenant.

## Limits
- If someone runs `vite --host` (console on the LAN) **and** the Vite proxy forwards requests, a LAN user's browser
  sends its own Host (the laptop's IP), which is refused; but any program on the laptop itself can read the key.
  Demo mode is for a single-user laptop only.
- `uvicorn --reload` rotates the key on every reload; the console fetches the new one on the next page load.

## Tests
`backend/tests/test_demo_mode.py` (off by default, flag and bind-host matrix, refusal creates nothing, plans are
synthetic and validator-feasible, non-local/rebinding/proxied requests refused, restart rotates the key without
duplicating data, normal keys and tenant isolation unchanged, Compose never enables it);
`frontend/src/test/demo.test.jsx` (off = no auto sign-in, on = signed in with the label, a normal key wins, sign-out).
