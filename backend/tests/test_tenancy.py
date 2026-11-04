"""P6a: tenants, hashed API keys and tenant isolation at the data layer (tests that try to break it)."""
import pytest
from app.db.keys import authenticate, create_tenant, hash_key, issue_key, revoke_key
from app.db.models import ApiKey, AuditLog, Plan
from app.db.session import TenantIsolationError, admin_session, make_engine, make_session_factory, tenant_session
from sqlalchemy import delete, func, select, text, update


@pytest.fixture
def db(tmp_path):
    engine = make_engine(f"sqlite:///{(tmp_path / 't.db').as_posix()}", create_tables=True)
    factory = make_session_factory(engine)
    with admin_session(factory) as s:
        a, b = create_tenant(s, "Tenant A"), create_tenant(s, "Tenant B")
        _, key_a = issue_key(s, a.id, "a-key")
        _, key_b = issue_key(s, b.id, "b-key")
        s.commit()
    for tid, pid in ((a.id, "plan-a"), (b.id, "plan-b")):
        with tenant_session(factory, tid) as s:
            s.add(Plan(id=pid, tenant_id=tid, instance={}, requested_engine="auto", engine="ortools",
                       time_limit_s=1.0))
            s.add(AuditLog(tenant_id=tid, actor="system", action="test"))
            s.commit()
    yield factory, a.id, b.id, key_a, key_b
    engine.dispose()


def test_keys_are_stored_hashed_and_authenticate(db):
    factory, a, b, key_a, key_b = db
    with admin_session(factory) as s:
        rows = s.scalars(select(ApiKey)).all()
        assert all(key_a not in (r.key_hash, r.prefix, r.label) for r in rows)
        assert {r.key_hash for r in rows} == {hash_key(key_a), hash_key(key_b)}
        raw = s.execute(text("select * from api_keys")).fetchall()
        assert key_a not in str(raw) and key_b not in str(raw)
        assert authenticate(s, key_a).tenant_id == a
        assert authenticate(s, key_b).tenant_id == b


@pytest.mark.parametrize("bad", [None, "", "lm_", "nope", "lm_deadbeef_x", "Bearer lm_x_y"])
def test_bad_keys_are_rejected(db, bad):
    factory, *_ = db
    with admin_session(factory) as s:
        assert authenticate(s, bad) is None


def test_tampered_and_revoked_keys_are_rejected(db):
    factory, a, b, key_a, key_b = db
    prefix_a = key_a.split("_")[1]
    forged = f"lm_{prefix_a}_{key_b.split('_', 2)[2]}"  # A's prefix with B's secret
    with admin_session(factory) as s:
        assert authenticate(s, forged) is None
        assert authenticate(s, key_a[:-1] + ("A" if key_a[-1] != "A" else "B")) is None
        key_id = authenticate(s, key_a).key_id
        assert revoke_key(s, key_id)
        s.commit()
        assert authenticate(s, key_a) is None


def test_tenant_sees_only_its_own_rows(db):
    factory, a, b, *_ = db
    with tenant_session(factory, a) as s:
        assert [p.id for p in s.scalars(select(Plan)).all()] == ["plan-a"]
        assert s.get(Plan, "plan-b") is None  # primary-key lookup of another tenant's plan
        assert s.scalars(select(Plan).where(Plan.id == "plan-b")).first() is None
        assert s.scalars(select(Plan).where(Plan.tenant_id == b)).all() == []  # explicit filter on B
        assert s.scalar(select(func.count()).select_from(Plan)) == 1
        assert s.scalars(select(AuditLog)).all()[0].tenant_id == a
        assert {k.tenant_id for k in s.scalars(select(ApiKey)).all()} == {a}


def test_tenant_cannot_update_or_delete_other_tenants_rows(db):
    factory, a, b, *_ = db
    with tenant_session(factory, a) as s:
        s.execute(update(Plan).where(Plan.id == "plan-b").values(state="hijacked"))
        s.execute(delete(Plan).where(Plan.id == "plan-b"))
        s.commit()
    with tenant_session(factory, b) as s:
        plan = s.get(Plan, "plan-b")
        assert plan is not None and plan.state == "queued"


def test_tenant_cannot_write_rows_for_another_tenant(db):
    factory, a, b, *_ = db
    with tenant_session(factory, a) as s:
        s.add(Plan(id="sneaky", tenant_id=b, instance={}, requested_engine="auto", engine="ortools",
                   time_limit_s=1.0))
        with pytest.raises(TenantIsolationError):
            s.flush()
        s.rollback()
    with tenant_session(factory, a) as s:
        plan = s.get(Plan, "plan-a")
        plan.tenant_id = b  # try to move own plan to another tenant
        with pytest.raises(TenantIsolationError):
            s.flush()
        s.rollback()
    with admin_session(factory) as s:
        assert s.get(Plan, "sneaky") is None
        assert s.get(Plan, "plan-a").tenant_id == a


def test_tenant_session_requires_a_tenant(db):
    factory, *_ = db
    with pytest.raises(TenantIsolationError):
        with tenant_session(factory, ""):
            pass


def test_alembic_migration_creates_the_same_tables(tmp_path, monkeypatch):
    from pathlib import Path

    from alembic import command
    from alembic.config import Config
    from app.db.models import Base
    from sqlalchemy import inspect

    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    monkeypatch.setenv("LOGIMIND_DATABASE_URL", url)
    backend = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend / "migrations"))
    command.upgrade(cfg, "head")
    engine = make_engine(url)
    insp = inspect(engine)
    assert set(Base.metadata.tables) <= set(insp.get_table_names())
    for name, table in Base.metadata.tables.items():
        assert {c["name"] for c in insp.get_columns(name)} == set(table.columns.keys()), name
    engine.dispose()
