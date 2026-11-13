# 0040: The deployed console reaches the API on this PC (npm run dev + ?api= link)

Date: 13 Nov 2026. Status: accepted (asked for by the team: run the backend on the laptop with plain `npm run dev`
and use the console deployed on Vercel, signed in to the demo tenant).

## Decision
- `npm run dev` (backend) also starts a free Cloudflare quick tunnel to the API when `backend/.env` has
  `LOGIMIND_PUBLIC_DEMO=1` and `FRONTEND_URL` (decision 0039). It prints `<FRONTEND_URL>/?api=<tunnel address>`
  and stops the tunnel when the API stops. `LOGIMIND_TUNNEL=0` turns this off; `start-demo.bat` sets it, because it
  runs its own tunnel. Without cloudflared it says how to install it and runs the API as before.
- cloudflared is found without the PATH too (VS Code's terminal may keep an old PATH): `LOGIMIND_CLOUDFLARED`, the
  PATH, Program Files (x86) / Program Files, the WinGet links and package folders, scoop and chocolatey.
- Port check first (13 Nov 2026): a LogiMind API already on the port (`uvicorn app.main:app`, e.g. an earlier
  `npm run dev` left open) is stopped with its reloader; any other program is named with its PID and nothing starts.
  Before this, a busy port made uvicorn exit at once and took the tunnel with it, so no link was printed.
- The link is printed only after `<tunnel>/health` answers from this PC; if cloudflared or the API fails, its last
  lines are shown.
- The console takes the API address at run time from `?api=`. It is kept in this browser's localStorage (a
  convenience, not a secret) until `?api=default`, and removed from the address bar. The header shows
  "Server: <host> · use the default server". Without `?api=` the build-time `VITE_API_URL` is used as before.
- Only `https://<name>.trycloudflare.com` and `http://localhost` / `127.0.0.1` are accepted, so a link cannot point
  the console at an arbitrary server. When the address changes, the tab's sessionStorage (tenant key, copilot
  settings) is cleared, so a key meant for one server is never sent to another.

## Why
Quick tunnels need no account (invariant 12) but get a new address on every start; a build-time `VITE_API_URL`
would need a Vercel redeploy each time. A stable address needs a domain (named Cloudflare tunnel) or an account
with a key (ngrok), which the project does not require.

## Limits
- The link changes on every start of `npm run dev`; share the new one.
- Anyone with the link uses the synthetic demo tenant on this PC while it runs (same limits as decision 0039).
- Any quick tunnel is accepted, so someone can still send a link to their own tunnel; the header shows which server
  is in use and nothing from another server's session is sent to it.
