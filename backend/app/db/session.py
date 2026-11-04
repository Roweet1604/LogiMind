"""Engine and sessions. Tenant isolation is enforced here, at the data layer:

* A *tenant session* (`tenant_session(factory, tenant_id)`) adds `tenant_id = :tenant`
  to every SELECT/UPDATE/DELETE on a tenant-owned model (`with_loader_criteria`), so
  even a bare `select(Plan)` or `session.get(Plan, other_tenants_id)` cannot see
  another tenant's rows.
* Before every flush it rejects new, changed or deleted tenant-owned rows whose
  tenant_id is not the session's tenant (`TenantIsolationError`).
* An *admin session* (no tenant) is only used for tenant creation and API-key lookup.

Database URL: env LOGIMIND_DATABASE_URL (default: SQLite file under experiments/results/api_data).
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import ORMExecuteState, Session, sessionmaker, with_loader_criteria

from app.db.models import Base, TenantOwned

DEFAULT_SQLITE = Path(__file__).resolve().parents[3] / "experiments" / "results" / "api_data" / "logimind.db"


class TenantIsolationError(PermissionError):
    pass


def database_url() -> str:
    return os.environ.get("LOGIMIND_DATABASE_URL", f"sqlite:///{DEFAULT_SQLITE.as_posix()}")


def make_engine(url: str | None = None, create_tables: bool = False) -> Engine:
    url = url or database_url()
    if url.startswith("sqlite:///"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
    engine = create_engine(url, **kwargs)
    if create_tables:  # dev/tests; production schema changes go through Alembic
        Base.metadata.create_all(engine)
    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@event.listens_for(Session, "do_orm_execute")
def _scope_queries(state: ORMExecuteState) -> None:
    tenant = state.session.info.get("tenant_id")
    if tenant is None or state.is_column_load or state.is_relationship_load:
        return
    if state.is_select or state.is_update or state.is_delete:
        state.statement = state.statement.options(
            with_loader_criteria(TenantOwned, lambda cls: cls.tenant_id == tenant, include_aliases=True))


@event.listens_for(Session, "before_flush")
def _check_writes(session: Session, flush_context, instances) -> None:
    tenant = session.info.get("tenant_id")
    if tenant is None:
        return
    for obj in list(session.new) + list(session.dirty) + list(session.deleted):
        if isinstance(obj, TenantOwned) and obj.tenant_id != tenant:
            raise TenantIsolationError(f"{type(obj).__name__} belongs to another tenant")


@contextmanager
def tenant_session(factory: sessionmaker[Session], tenant_id: str) -> Iterator[Session]:
    if not tenant_id:
        raise TenantIsolationError("a tenant session needs a tenant id")
    with factory() as s:
        s.info["tenant_id"] = tenant_id
        yield s


@contextmanager
def admin_session(factory: sessionmaker[Session]) -> Iterator[Session]:
    with factory() as s:
        yield s
