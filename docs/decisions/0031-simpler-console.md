# 0031: A simpler console for the demo

Date: 10 Nov 2026. Status: accepted (asked for by the team). Look only; no backend feature removed.

## Decision
- Sidebar: Overview, Plans, Drivers, Copilot, and Account. The research workflow (problem setup, run, results,
  compare), Benchmark lab and Methodology sit behind one "Research" link that appears only when `/api/health`
  reports `research_endpoints: true` (`LOGIMIND_DEV_RESEARCH_ENDPOINTS=1`). Their sub-links show while one of them is
  open. The routes still exist; with the switch off they show "switched off on this server".
- "Current research instance" footer only in research mode. The console no longer asks for `/api/instances` when the
  research endpoints are off (it used to get a 403 on every page load).
- New Overview for dispatchers (plan counts from the validator's verdicts, latest plans, what to do next). The old
  research overview moved unchanged to `/research`. New Drivers page: pick a feasible plan, then the existing driver
  link panel.
- Plain error messages (`frontend/src/lib/api.js`): no answer, or the dev proxy's 5xx without a body, becomes "The
  server isn't running. Run start-dev.bat, then press Retry."; 401/403/404/429/5xx have plain sentences; server
  messages with a reason are still shown. No commands (uvicorn, env variables, manage.py, ollama) in the UI; the
  copilot's technical reason sits under "Technical details" without its setup command.
- Server unreachable: the sign-in is kept (state `offline`), a banner and the pages show a Retry button. Only a key
  the server rejects (401) signs the tab out. This changes the `AuthContext` behaviour noted in PROGRESS (decision 0027).

## Tests
`frontend/src/test/simple.test.jsx` (7). Two assertions in `lib.test.js` were updated because the message text
changed; they check the new text, the status and the `unreachable` flag (not weaker).
