"""Alembic environment. Run from backend/:  alembic upgrade head
The URL comes from LOGIMIND_DATABASE_URL (default SQLite, see app/db/session.py)."""
from __future__ import annotations

import sys
from pathlib import Path

from alembic import context

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import Base  # noqa: E402
from app.db.session import make_engine  # noqa: E402

target_metadata = Base.metadata
# app/db/migrate.py passes the URL in; the CLI uses LOGIMIND_DATABASE_URL.
URL = context.config.attributes.get("database_url")


def run_migrations_offline() -> None:
    from app.db.session import database_url
    context.configure(url=URL or database_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = make_engine(URL)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
