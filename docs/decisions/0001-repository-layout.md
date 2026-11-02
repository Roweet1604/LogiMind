# 0001: Repository layout and baseline handling

Date: 2 Nov 2026. Status: accepted (Phase 0).

## Decision
- The new code lives at the repository root: `backend/`, `frontend/` (ops console), `driver/` (PWA), `experiments/`, plus `docker-compose.yml` and `.env.example`.
- `docs/context/prior-code/` stays an untouched reference copy of route-optimization v3. P1 copies its backend, frontend and experiments into the root layout and keeps its tests green there.
- `docs/context/` is read-only input material.

## Why
- One obvious place for new code; the original stays available to compare against and to quote in the report.
- Keeping git history simple: the migration is one visible commit in P1.
