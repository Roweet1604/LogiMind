# 0013: Ops console on the tenant API

Date: 4 Nov 2026. Status: accepted (decided unattended by Claude Code).

## Decision
- **Sign-in with an API key** (`/login`). The key is checked with the new `GET /api/whoami`, then kept in memory and in `sessionStorage` only (cleared when the tab closes, never in `localStorage`), and sent as `X-API-Key`. A rejected key is not kept.
- **Operations pages:** `/plans` (new plan from a CSV/Excel import, or a seeded synthetic sample labelled "synthetic sample"; list of the tenant's plans from the new `GET /api/plans`) and `/plans/:id` (validator verdict, solver status, metrics, engine explanation, replan lineage and timing, map, route table, and the replan form for breakdown, failed delivery and urgent order).
  - The import shows the backend's row-level report, and a plan cannot be created until every row is valid.
  - The replan form sends the completed stops per vehicle and disables the GA when any stop is completed, matching the backend rule (decision 0012).
  - Infeasible plans are shown as infeasible with the validator's reasons, and the replan form is replaced by an explanation.
- `GET /api/plans/{id}` now also returns the stored instance (needed for the map and the replan form). `GET /api/health` reports `research_endpoints` so the console can say plainly when the research pages are off.
- The research pages (problem setup, run, results, compare, benchmark lab) stay, grouped as "Research workflow (dev only)". With the research endpoints off, they show a banner that points to Plans.
- Engine identity on the map: OR-Tools solid blue, GA + local search dashed orange, hybrid dotted blue labelled "Hybrid (OR-Tools seed + GA)".

## Known limits
- Checked with component tests (mocked API) and a production build, **not in a real browser against a live backend** in this session.
- Fleet and depot are typed in by hand on the new-plan form (the import file only has orders).
