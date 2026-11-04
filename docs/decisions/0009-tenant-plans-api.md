# 0009: Tenant plans API (P6b)

Date: 4 Nov 2026. Status: accepted (decided unattended by Claude Code).

## Decision
- `POST /api/plans` and `GET /api/plans/{plan_id}` need an `X-API-Key` header (OpenAPI security scheme `APIKeyHeader`, so the Swagger UI at `/docs` has an Authorize button). A missing, wrong or revoked key gives 401.
- The plan request carries the **instance inline**. It is validated (`Instance.validate`) and stored in the tenant-owned `plans` row. Plans do **not** reference the older in-memory `/api/instances` store, because that store has no tenants and would let one tenant plan on another tenant's instance.
- Another tenant's plan gives the same 404 as a missing plan, so plan ids cannot be probed.
- Execution reuses the store's single solver thread and guarded worker process, so solver jobs still run one at a time. The result stores the solver status, the validator's verdict (`feasible`) and the metrics. Timeouts and failures are stored as what they are.
- Audit log rows: `plan.create` (actor = API key id), `plan.completed` / `plan.failed` (actor = system).
- The database is migrated to the Alembic head when the app starts. The default is SQLite `logimind.db` in the data dir; `LOGIMIND_DATABASE_URL` overrides it.
- Tenants and keys are created with `python manage.py create-tenant "<name>"` (the key is printed once). There is no HTTP endpoint for creating tenants.
- This replaces the unauthenticated `/api/plans` from the P5 commit. The research endpoints (`/api/instances`, `/api/runs`, `/api/experiments`, used by the ops console and the experiments) stay unauthenticated, as local research tools; they must not be exposed publicly until they are put behind tenants too (open item).
