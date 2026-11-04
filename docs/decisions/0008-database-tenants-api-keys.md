# 0008: Database, tenants and API keys (P6a)

Date: 4 Nov 2026. Status: accepted (decided unattended by Claude Code).

## Decision
- **SQLAlchemy 2 + Alembic**, SQLite in development (`LOGIMIND_DATABASE_URL`, default `experiments/results/api_data/logimind.db`, git-ignored with the rest of api_data); Postgres later through the same URL. Schema in `backend/app/db/models.py`, first migration `backend/migrations/versions/0001_*.py`. A test checks that the migration creates exactly the model's tables and columns.
- **Tenants**: every tenant-owned table has `tenant_id` (mixin `TenantOwned`).
- **Isolation at the data layer** (`app/db/session.py`): a tenant session adds `tenant_id = :tenant` to every ORM SELECT, UPDATE and DELETE on tenant-owned tables (`with_loader_criteria`), and a `before_flush` hook rejects new, changed or deleted rows of another tenant. Tests in `tests/test_tenancy.py` try to read by primary key, filter explicitly on the other tenant, bulk-update, bulk-delete, insert for another tenant and move a row to another tenant.
- **Known limit:** raw SQL (`text(...)`) bypasses the ORM hooks. Rule: request-handling code uses ORM statements only; raw SQL is allowed only in migrations and admin tooling.
- **API keys**: format `lm_<12 hex prefix>_<43 char secret>`, made with `secrets`. Only SHA-256(key) is stored; the plaintext is returned once. Lookup by prefix, then constant-time comparison (`hmac.compare_digest`). SHA-256 instead of bcrypt/argon2 because keys are 256-bit random values, not passwords; a slow hash adds no protection and costs every request. Revoked keys are rejected.
- New dependencies (free, open source, offline): `sqlalchemy`, `alembic`, `scikit-learn` (P5), `openpyxl` (planned for 6c Excel import).
