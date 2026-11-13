# 0041: Driver links open on a phone: the driver app at /driver/ on the console's site

Date: 13 Nov 2026. Status: accepted (asked for by the team: driver links from the Drivers page read
`http://localhost:.../#t=...`, which a phone cannot open).

## Decision
- **The Vercel build serves the driver PWA too**, at `/driver/` on the console's site.
  `frontend/scripts/build-vercel.mjs` (Vercel's build command, `frontend/vercel.json`) builds the console with
  `VITE_DRIVER_PATH=/driver/`, then `driver/` with `DRIVER_BASE=/driver/` into `dist/driver/`. `vercel.json`
  rewrites `/driver/...` to the driver's `index.html`. The driver's manifest `start_url` and `scope` and its
  service worker follow the base.
- **The console builds the link** (`driverLinkUrl` in `frontend/src/lib/api.js`). When it serves the driver app
  (`VITE_DRIVER_PATH`), the link is `window.location.origin` + `/driver/`. Otherwise (local dev, Docker) it is the
  backend's `LOGIMIND_DRIVER_APP_URL` address as before.
- **Laptop tunnel:** when the console uses a `?api=` server (decision 0040), the link carries the same
  `?api=<tunnel>` before `#t=`. The signed token is the backend's, unchanged, and stays in the fragment, so it is
  never sent to the site's server.
- **The driver app reads `?api=`** with the console's allow-list (`*.trycloudflare.com`, localhost). It removes the
  address from the address bar and keeps it in localStorage, because the installed app opens at its start URL
  without it. A new link (`#t=`) without `?api=` forgets an old tunnel address.
- Docker Compose and the backend are unchanged.

## Why
A phone can open only a public address. The console's own site is already public (Vercel) and free, so the
driver app is served from it. A second Vercel project would also cost nothing, but it is one more thing to set up.

## Limits
- The backend's own `url` field (API clients, `POST /api/plans/{id}/driver-links`) still uses
  `LOGIMIND_DRIVER_APP_URL`; only the console's link follows the site.
- A link made on a laptop tunnel stops working when that `npm run dev` stops; the token is still valid but the
  server it names is gone.
