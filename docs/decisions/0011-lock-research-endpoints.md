# 0011: Lock the research endpoints (dev-only switch, off by default)

Date: 4 Nov 2026. Status: accepted (decided unattended by Claude Code).

## Context
`/api/instances`, `/api/runs`, `/api/experiments` and `/api/benchmarks` (the P1 to P3 ops console) keep their data in the in-memory/JSON store, which has no tenants. If they simply required an API key, every tenant could still read every other tenant's instances and runs. That would break invariant 7.

## Decision
- These 15 routes are **OFF by default**. They return 403 with a clear message unless `LOGIMIND_DEV_RESEARCH_ENDPOINTS=1` is set; only the exact value `1` counts. `create_app(..., legacy_open=...)` can override this in code and tests. `/api/health` stays open.
- They are labelled `research (dev only, off by default)` in OpenAPI.
- Tenant work uses the authenticated, tenant-scoped endpoints: `/api/plans`, `/api/orders/import`, `/api/webhooks`, `/api/audit`.
- The test suite turns the switch on in `conftest.py` so the existing research-endpoint tests keep running. `tests/test_research_lock.py` checks the default is off, that other values do not turn it on, and the override.

## Consequences
- The React ops console only works against a backend started with the dev switch. Moving the console to tenant plans (`/api/plans` with a key) is open frontend work.
- The benchmark and experiment scripts call the Python modules directly, not these endpoints, so they are not affected.
