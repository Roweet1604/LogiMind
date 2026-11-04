"""Admin CLI (run from backend/). The database URL comes from LOGIMIND_DATABASE_URL.

  python manage.py migrate                     apply Alembic migrations
  python manage.py create-tenant "Acme Fleet"  create a tenant and print its first API key ONCE
  python manage.py issue-key <tenant_id>       print a new API key ONCE
  python manage.py revoke-key <key_id>
"""
from __future__ import annotations

import sys

from app.db.keys import create_tenant, issue_key, revoke_key
from app.db.migrate import upgrade_to_head
from app.db.session import admin_session, database_url, make_engine, make_session_factory


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in {"migrate", "create-tenant", "issue-key", "revoke-key"} or (
            argv[0] != "migrate" and len(argv) < 2):
        print(__doc__)
        return 2
    url = database_url()
    upgrade_to_head(url)
    if argv[0] == "migrate":
        print(f"database at head: {url}")
        return 0
    engine = make_engine(url)
    with admin_session(make_session_factory(engine)) as s:
        if argv[0] == "create-tenant":
            tenant = create_tenant(s, argv[1])
            row, key = issue_key(s, tenant.id, "first key")
            print(f"tenant_id={tenant.id} key_id={row.id}")
        elif argv[0] == "issue-key":
            row, key = issue_key(s, argv[1], argv[2] if len(argv) > 2 else "")
            print(f"key_id={row.id}")
        else:
            ok = revoke_key(s, argv[1])
            s.commit()
            print("revoked" if ok else "no such key")
            return 0 if ok else 1
        s.commit()
    print(f"API key (shown once, store it in an environment variable, never commit it): {key}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
