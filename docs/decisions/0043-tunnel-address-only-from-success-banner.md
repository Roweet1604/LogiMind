# 0043: npm run dev takes the tunnel address only from cloudflared's success banner, and retries

Date: 13 Nov 2026. Status: accepted (asked for by the team after a bad link).

## Problem
`npm run dev` printed `https://logi-mind-ten.vercel.app/?api=https://api.trycloudflare.com` after cloudflared failed
with `failed to request quick Tunnel: Post "https://api.trycloudflare.com/tunnel": context deadline exceeded`.
`dev.mjs` took the first `https://*.trycloudflare.com` anywhere in cloudflared's output, which here was the error text.

## Decision
- The address is parsed in `backend/scripts/tunnel.mjs` (pure functions). It is accepted only after the success banner
  "Your quick Tunnel has been created", must be `https://<word>-<word>[-...].trycloudflare.com`, and `api` / `www` are
  rejected explicitly. Output is joined per cloudflared run, so a banner split across chunks is still found.
- A link is printed only when that address's `/health` answers from this PC. A failed health check is a failed try
  (decision 0040 printed the link anyway with "may still work"; it no longer does).
- Up to 3 tries. A try fails on "failed to request quick Tunnel", a QUIC timeout, cloudflared exiting, no address
  within 60 s, or the health check failing. After a QUIC timeout the next tries add `--protocol http2`
  (UDP is often blocked). Pauses of 3 s and 6 s between tries.
- After 3 failed tries it says so plainly ("no console link this time"), shows cloudflared's last lines, and leaves the
  API running on localhost.
- Tests: `backend/scripts/tunnel.test.mjs` (node:test, no dependencies), run by `backend/tests/test_dev_tunnel.py`
  (skipped without Node) so the backend suite covers it.

## Limits
- If cloudflared stops after a working link was printed, it is reported but not restarted (a new tunnel would have a
  new address, so the shared link would be stale anyway).
